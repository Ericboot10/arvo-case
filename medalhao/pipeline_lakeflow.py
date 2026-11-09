# Databricks notebook source
# =====================================================================================================
# F5 · Pipeline Lakeflow Declarative Pipelines: bronze → silver → gold (+ quarentena)
#
# Usa as MESMAS funções de medalhao/transformacoes.py que o harness local testa.
# Expectations vêm de medalhao/expectations.yaml. Padrão de quarentena da doc Databricks: a view marcada recebe
# expect_all (métricas no event log); válidos e reprovados seguem para tabelas separadas.
#
# Configuração (bundle → resources/pipelines.yml):
#   arvo.catalog, arvo.landing, arvo.repo_root
# Publicação em vários schemas (bronze/silver/gold/quarantine) por nomes totalmente qualificados.
# Requer o modo de publicação padrão do Unity Catalog. VALIDAR no workspace.
# =====================================================================================================
import json
import sys

try:                                     # nome atual do módulo (Spark Declarative Pipelines)
    from pyspark import pipelines as dp
except ImportError:                      # runtime mais antigo
    import dlt as dp
from pyspark.sql import functions as F
from pyspark.sql import types as T

CAT = spark.conf.get("arvo.catalog")
LANDING = spark.conf.get("arvo.landing")
sys.path.insert(0, spark.conf.get("arvo.repo_root"))
from medalhao import transformacoes as tf  # noqa: E402
from motor import motor  # noqa: E402

EXP = tf.carregar_expectations()


def _regras(tabela: str, *acoes: str) -> dict:
    return {r["id"]: r["expr"] for r in EXP[tabela] if r["acao"] in acoes}


def _todas(tabela: str) -> dict:
    return {r["id"]: r["expr"] for r in EXP[tabela]}


def _params() -> dict:
    """Contrato APROVADO e vigente (F3). Fora de prod, sem aprovação, usa o rascunho (sinalizado na dim_contrato)."""
    # spark.catalog.tableExists é bloqueado no Lakeflow serverless (py4j whitelist): tenta ler e trata a ausência.
    try:
        r = spark.table(f"{CAT}.contracts.contract_params").where("vigente").select("params_json").limit(1).collect()
    except Exception:            # tabela ainda não existe (contrato não aprovado no ambiente)
        r = []
    if r:
        p = json.loads(r[0][0])
        p["_status"] = "aprovado"
        return p
    return tf.carregar_parametros_contrato(CAT)


PARAMS = _params()
MASCARA = "" if CAT == "arvo_dev" else f" MASK {CAT}.ops.mask_id_pessoa"   # ADR-006: só a bronze tem o id em claro
SCHEMA_BRONZE = ", ".join(
    [f"{c} STRING{MASCARA if c == 'id_beneficiario' else ''}" for c in tf.COLUNAS_ORIGEM]
    + ["_arquivo STRING", "_hash_linha STRING", "_ingest_ts TIMESTAMP"])


# ------------------------------------------------------------------------------------------------ BRONZE
@dp.table(name=f"{CAT}.bronze.sinistro_raw", schema=SCHEMA_BRONZE,
          comment="Itens de conta brutos, append-only, fiéis à origem (F5). id_beneficiario mascarado fora de dev.")
def sinistro_raw():
    origem = (spark.readStream.format("cloudFiles").option("cloudFiles.format", "csv").option("header", True)
              .schema(T.StructType([T.StructField(c, T.StringType()) for c in tf.COLUNAS_ORIGEM]))
              .load(f"{LANDING}sinistro/"))
    return tf.bronze_sinistro(origem, F.col("_metadata.file_path"))


# ------------------------------------------------------------------------------------------------ SILVER
@dp.view(name="item_conta_marcado")
@dp.expect_all(_todas("silver.item_conta"))          # métricas de TODAS as regras no event log
def item_conta_marcado():
    cand = tf.silver_item_conta_candidatos(spark.read.table(f"{CAT}.bronze.sinistro_raw"),
                                           spark.read.table(f"{CAT}.semantic.map_tuss_conceito"),
                                           spark.read.table(f"{CAT}.semantic.dim_dominio_valor"),
                                           tf.versao_semantica())
    return tf.marcar_violacoes(cand, EXP["silver.item_conta"], "quarentena")


@dp.materialized_view(name=f"{CAT}.silver.item_conta", comment="Itens válidos, tipados e enriquecidos com a semântica (F5)")
def item_conta():
    return spark.read.table("item_conta_marcado").where(F.size("_motivos") == 0).select(*tf.COLUNAS_SILVER_ITEM)


@dp.materialized_view(name=f"{CAT}.quarantine.item_conta_rejeitado",
                      comment="Linhas reprovadas, com o motivo (ids de expectations). Não alimentam glosa.")
def item_conta_rejeitado():
    return tf.quarentena(spark.read.table("item_conta_marcado"))


@dp.view(name="conta_marcada")
@dp.expect_all(_regras("silver.conta", "warn"))
def conta_marcada():
    return tf.silver_conta(spark.read.table(f"{CAT}.silver.item_conta"), PARAMS)


@dp.materialized_view(name=f"{CAT}.silver.conta", comment="1 linha por conta, com pacote e conflito semântico")
def conta():
    return spark.read.table("conta_marcada").select(*tf.COLUNAS_SILVER_CONTA)


@dp.materialized_view(name=f"{CAT}.silver.atendimento", comment="Beneficiário × dia (T11): fragmentação e cirurgia repetida")
def atendimento():
    return tf.silver_atendimento(spark.read.table(f"{CAT}.silver.conta"), spark.read.table(f"{CAT}.silver.item_conta"), PARAMS)


@dp.materialized_view(name=f"{CAT}.silver.funil_inteligencia", comment="Funil de economia tipado (Parte 2)")
def funil_inteligencia():
    return tf.silver_funil(spark.read.table(f"{CAT}.bronze.inteligencias_raw"))


# ------------------------------------------------------------------------------------------------ GOLD · dimensões
@dp.materialized_view(name=f"{CAT}.gold.dim_data")
def dim_data():
    return tf.dim_data(spark.read.table(f"{CAT}.silver.item_conta"))


@dp.materialized_view(name=f"{CAT}.gold.dim_prestador")
def dim_prestador():
    return tf.dim_prestador(spark.read.table(f"{CAT}.silver.item_conta"))


@dp.materialized_view(name=f"{CAT}.gold.dim_item_tuss")
def dim_item_tuss():
    return tf.dim_item_tuss(spark.read.table(f"{CAT}.semantic.map_tuss_conceito"))


@dp.materialized_view(name=f"{CAT}.gold.dim_perfil_atendimento")
def dim_perfil_atendimento():
    return tf.dim_perfil_atendimento(spark.read.table(f"{CAT}.semantic.dim_dominio_valor"))


@dp.materialized_view(name=f"{CAT}.gold.dim_contrato", comment="SCD2 por versão. Rascunho-F2 identificado na versão")
def dim_contrato():
    return tf.dim_contrato(spark, PARAMS)


@dp.materialized_view(name=f"{CAT}.gold.dim_item_contratado")
def dim_item_contratado():
    return tf.dim_item_contratado(spark, PARAMS)


@dp.materialized_view(name=f"{CAT}.gold.dim_inteligencia")
def dim_inteligencia():
    return tf.dim_inteligencia(spark.read.table(f"{CAT}.silver.funil_inteligencia"))


# ------------------------------------------------------------------------------------------------ GOLD · fatos
@dp.materialized_view(name=f"{CAT}.gold.fato_item", comment="Fato transacional: 1 linha por item, antes do motor de regras")
@dp.expect_all(_regras("gold.fato_item", "warn"))
@dp.expect_all_or_fail(_regras("gold.fato_item", "fail"))
def fato_item():
    run_id = spark.conf.get("pipelines.id", "lakeflow")
    return tf.fato_item(spark.read.table(f"{CAT}.silver.item_conta"), spark.read.table(f"{CAT}.silver.conta"),
                        spark.read.table(f"{CAT}.gold.dim_item_contratado"), run_id)


@dp.materialized_view(name=f"{CAT}.gold.fato_funil_economia", comment="Snapshot periódico do funil (inteligência × competência)")
def fato_funil_economia():
    return tf.fato_funil_economia(spark.read.table(f"{CAT}.silver.funil_inteligencia"))


# ------------------------------------------------------------------------------------------------ F6 · motor de regras
REGRAS = motor.carregar_regras()


@dp.materialized_view(name=f"{CAT}.gold.dim_regra", comment="Regras de glosa versionadas (motor/regras.yaml) × contrato")
def dim_regra():
    return motor.dim_regra(spark, REGRAS, PARAMS)


@dp.materialized_view(name=f"{CAT}.gold.ponte_regra_inteligencia",
                      comment="Regra contratual ↔ inteligência Arvo (proposta, AMB-17)")
def ponte_regra_inteligencia():
    return motor.ponte_regra_inteligencia(spark)


@dp.materialized_view(name=f"{CAT}.gold.fato_apontamento",
                      comment="1 glosa por item: cláusula principal e subsidiárias, evidência, justificativa e status de envio")
@dp.expect_all(_regras("gold.fato_apontamento", "warn"))
@dp.expect_all_or_fail(_regras("gold.fato_apontamento", "fail"))
def fato_apontamento():
    enr = motor.enriquecer(spark.read.table(f"{CAT}.gold.fato_item"), spark.read.table(f"{CAT}.silver.conta"),
                           spark.read.table(f"{CAT}.gold.dim_item_contratado"), spark.read.table(f"{CAT}.gold.dim_contrato"),
                           PARAMS)
    return motor.avaliar(enr, REGRAS, spark.conf.get("pipelines.id", "lakeflow"))


@dp.materialized_view(name=f"{CAT}.gold.fato_item_auditado",
                      comment="Todos os itens com o resultado do motor (fonte de mv_auditoria_glosa)")
def fato_item_auditado():
    return motor.item_auditado(spark.read.table(f"{CAT}.gold.fato_item"), spark.read.table(f"{CAT}.gold.fato_apontamento"))
