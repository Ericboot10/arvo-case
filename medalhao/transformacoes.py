"""Transformações da F5: funções PURAS de DataFrame (entrada → saída), sem efeito colateral.

As MESMAS funções são usadas por:
  - medalhao/pipeline_lakeflow.py (Databricks, Lakeflow Declarative Pipelines, com expectations nativas)
  - medalhao/local.py              (harness local com Spark, nos testes e na demo)
Assim não existe uma "versão de teste" que diverge da versão de produção.

Colunas de saída = arquitetura/modelo.yaml (testado em medalhao/tests).
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

RAIZ = Path(__file__).resolve().parents[1]
COLUNAS_ORIGEM = ["id_prestador", "id_item", "id_conta", "id_beneficiario", "dt_atendimento", "carater_atendimento",
                  "tipo_conta", "cod_tuss", "desc_item", "tipo_item", "qtd", "vl_unitario", "vl_total", "nome_prestador"]
MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
         "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
SAL_PSEUDONIMO = "arvo:"  # MESMA fórmula de plataforma/sql/02_mascaras_lgpd.sql: o hash da silver casa com a máscara


# ============================================================================== insumos (semântica e contrato)
def carregar_expectations() -> dict:
    return yaml.safe_load((RAIZ / "medalhao" / "expectations.yaml").read_text("utf-8"))


def carregar_parametros_contrato(catalogo: str = "arvo_dev", caminho_aprovado: Path | None = None) -> dict:
    """Parâmetros APROVADOS (F3). Fora de prod, se ainda não houver aprovação, usa a transcrição da F2 marcada como
    rascunho. Em prod, sem aprovação, falha: nada roda em produção com contrato não aprovado."""
    if caminho_aprovado and Path(caminho_aprovado).exists():
        p = json.loads(Path(caminho_aprovado).read_text("utf-8"))
        p["_status"] = "aprovado"
        return p
    if catalogo == "arvo_prod":
        raise RuntimeError("arvo_prod exige contract_params aprovado pelo Jurídico (G3)")
    v = yaml.safe_load((RAIZ / "semantic" / "vinculos" / "PRT-2025-0417.yaml").read_text("utf-8"))
    mats = v["pacotes"]["itens_inclusos_comuns"]
    return {
        "versao_contrato": f"{v['id_contrato']}@rascunho-F2", "_status": "rascunho", "aprovado_por": None,
        "data_aprovacao": None, "id_prestador": v["prestador"],
        "contrato": {"id_contrato": v["id_contrato"], "vigencia_inicio": v["vigencia"]["inicio"],
                     "vigencia_meses": v["vigencia"]["meses"]},
        "anexo_i": [{"codigo": i["codigo"], "valor_teto": float(i["teto"])} for i in v["itens_com_preco_pactuado"]],
        "anexo_ii": [{"codigo_procedimento": p["codigo"], "taxa_sala_codigo": p["taxa_sala_inclusa"],
                      "materiais_rotina": mats} for p in v["pacotes"]["procedimentos"]],
        "taxas_condicionadas": [{"codigo": t["codigo"], "carater_permitido": t["carater_permitido"]}
                                for t in v["taxas_condicionadas_ao_carater"]],
    }


def versao_semantica() -> str:
    return yaml.safe_load((RAIZ / "semantic" / "glossario.yaml").read_text("utf-8"))["versao"]


def df_map_tuss(spark: SparkSession) -> DataFrame:
    """Mesmo conteúdo de <catalog>.semantic.map_tuss_conceito (F2). No Databricks, lê-se a tabela."""
    conc = yaml.safe_load((RAIZ / "semantic" / "conceitos.yaml").read_text("utf-8"))["conceitos"]
    pai = {c["id"]: c["pai"] for c in conc}

    def raiz(c):
        while pai.get(c):
            c = pai[c]
        return c

    m = yaml.safe_load((RAIZ / "semantic" / "map_tuss_conceito.yaml").read_text("utf-8"))
    linhas = [(x["codigo"], x["descricao_canonica"], x["conceito"], raiz(x["conceito"]), x["tipo_item_origem"],
               (x.get("atributos") or {}).get("porte_sala"), m["vigencia_inicio"]) for x in m["codigos"]]
    return spark.createDataFrame(linhas, "cod_tuss string, descricao_canonica string, conceito string, conceito_pai string,"
                                         " tipo_item_origem string, porte_sala int, vigencia_inicio string")


def df_dominios(spark: SparkSession) -> DataFrame:
    d = yaml.safe_load((RAIZ / "semantic" / "dominios.yaml").read_text("utf-8"))["dominios"]
    linhas = [(n, x["coluna_origem"], m["valor_origem"], m["canonico"]) for n, x in d.items() for m in x["mapeamento_origem"]]
    return spark.createDataFrame(linhas, "dominio string, coluna_origem string, valor_origem string, canonico string")


# ============================================================================== BRONZE
def bronze_sinistro(df_csv: DataFrame, arquivo_col: F.Column) -> DataFrame:
    """Recebe o CSV lido com TODAS as colunas como string. Só limpa o BOM do nome da 1ª coluna e adiciona metadados."""
    for c in df_csv.columns:
        if c.startswith("﻿"):
            df_csv = df_csv.withColumnRenamed(c, c.lstrip("﻿"))
    faltando = set(COLUNAS_ORIGEM) - set(df_csv.columns)
    if faltando:
        raise ValueError(f"schema de origem mudou (contrato de dados F1): faltando {sorted(faltando)}")
    return (df_csv.select(*COLUNAS_ORIGEM)
            .withColumn("_arquivo", arquivo_col)
            .withColumn("_hash_linha", F.sha2(F.concat_ws("|", *[F.coalesce(F.col(c), F.lit("∅")) for c in COLUNAS_ORIGEM]), 256))
            .withColumn("_ingest_ts", F.current_timestamp()))


def ler_csv_origem(spark: SparkSession, caminho: str) -> DataFrame:
    return (spark.read.option("header", True).option("encoding", "UTF-8").option("quote", '"')
            .option("escape", '"').schema(T.StructType([T.StructField(c, T.StringType()) for c in COLUNAS_ORIGEM]))
            .option("enforceSchema", True).csv(caminho))


# ============================================================================== SILVER
def _decimal_ptbr(col: str, precisao: str) -> F.Column:
    return F.regexp_replace(F.trim(F.col(col)), ",", ".").cast(precisao)


def _data_extenso(col: str) -> F.Column:
    meses = F.create_map(*[x for k, v in MESES.items() for x in (F.lit(k), F.lit(v))])
    rx = r"^\s*(\d{1,2})\s+de\s+(\S+)\s+de\s+(\d{4})\s*$"
    dia = F.regexp_extract(F.col(col), rx, 1).cast("int")
    mes = meses[F.lower(F.regexp_extract(F.col(col), rx, 2))]
    ano = F.regexp_extract(F.col(col), rx, 3).cast("int")
    return F.when(dia.isNotNull() & mes.isNotNull() & ano.isNotNull(), F.make_date(ano, mes, dia))


def silver_item_conta_candidatos(bronze: DataFrame, map_tuss: DataFrame, dominios: DataFrame, versao_sem: str) -> DataFrame:
    """Tipa, normaliza e enriquece com a semântica. Ainda contém as linhas inválidas: as expectations decidem o destino."""
    car = dominios.where("dominio = 'carater_atendimento'").select(
        F.col("valor_origem").alias("_car_o"), F.col("canonico").alias("carater_canonico"))
    reg = dominios.where("dominio = 'regime_atendimento'").select(
        F.col("valor_origem").alias("_reg_o"), F.col("canonico").alias("regime"))
    mp = map_tuss.select("cod_tuss", "conceito", "conceito_pai")
    df = (bronze
          .withColumn("carater_origem", F.col("carater_atendimento"))
          .withColumn("regime_origem", F.col("tipo_conta"))
          .withColumn("dt", _data_extenso("dt_atendimento"))
          .join(F.broadcast(car), F.col("carater_atendimento") == F.col("_car_o"), "left")
          .join(F.broadcast(reg), F.col("tipo_conta") == F.col("_reg_o"), "left")
          .join(F.broadcast(mp), "cod_tuss", "left")
          .withColumn("_n_id_item", F.count("*").over(Window.partitionBy("id_item"))))
    return df.select(
        "id_item", "id_conta", "id_prestador", "id_beneficiario",
        F.substring(F.sha2(F.concat(F.lit(SAL_PSEUDONIMO), F.col("id_beneficiario")), 256), 1, 16).alias("id_beneficiario_hash"),
        F.col("dt").alias("dt_atendimento"), F.trunc("dt", "month").alias("competencia"),
        "carater_origem", "carater_canonico", "regime_origem", "regime", "cod_tuss",
        F.col("desc_item").alias("desc_item_origem"), F.col("tipo_item").alias("tipo_item_origem"),
        "conceito", "conceito_pai",
        F.when(F.trim("qtd").rlike(r"^-?\d+$"), F.trim("qtd").cast("int")).alias("qtd"),
        _decimal_ptbr("vl_unitario", "decimal(12,2)").alias("vl_unitario"),
        _decimal_ptbr("vl_total", "decimal(14,2)").alias("vl_total"),
        "nome_prestador", F.lit(versao_sem).alias("versao_semantica"), "_arquivo", "_ingest_ts", "_hash_linha",
        "_n_id_item")


# ADR-006: sem id_beneficiario em claro a partir da silver (só o pseudônimo)
COLUNAS_SILVER_ITEM = ["id_item", "id_conta", "id_prestador", "id_beneficiario_hash", "dt_atendimento",
                       "competencia", "carater_origem", "carater_canonico", "regime_origem", "regime", "cod_tuss",
                       "desc_item_origem", "tipo_item_origem", "conceito", "conceito_pai", "qtd", "vl_unitario",
                       "vl_total", "nome_prestador", "versao_semantica", "_arquivo", "_ingest_ts"]


def marcar_violacoes(df: DataFrame, regras: list[dict], acao: str) -> DataFrame:
    """Adiciona `_motivos` (ids das expectations da ação indicada que a linha viola). NULL na expressão conta como violação."""
    alvos = [r for r in regras if r["acao"] == acao]
    motivos = [F.when(~F.coalesce(F.expr(r["expr"]), F.lit(False)), F.lit(r["id"])) for r in alvos]
    return df.withColumn("_motivos", F.filter(F.array(*motivos), lambda x: x.isNotNull()) if motivos else F.array())


def quarentena(df_marcado: DataFrame) -> DataFrame:
    return (df_marcado.where(F.size("_motivos") > 0)
            .select("_arquivo", "_hash_linha", "id_item", F.col("_motivos").alias("motivos"),
                    # ADR-006: a quarentena também não guarda o identificador em claro
                    F.to_json(F.struct(*[c for c in df_marcado.columns
                                         if not c.startswith("_n_") and c != "id_beneficiario"])).alias("linha_original"),
                    F.current_timestamp().alias("_rejeitado_em")))


def pacote_codigos(params: dict) -> dict:
    proc = [p["codigo_procedimento"] for p in params["anexo_ii"]]
    inclusos = sorted({p["taxa_sala_codigo"] for p in params["anexo_ii"]} |
                      {m for p in params["anexo_ii"] for m in p["materiais_rotina"]})
    return {"procedimentos": proc, "inclusos": inclusos}


def silver_conta(item: DataFrame, params: dict) -> DataFrame:
    proc = pacote_codigos(params)["procedimentos"]
    eh_pac = F.col("cod_tuss").isin(proc)
    return (item.groupBy("id_conta").agg(
        F.first("id_prestador").alias("id_prestador"), F.first("id_beneficiario_hash").alias("id_beneficiario_hash"),
        F.min("dt_atendimento").alias("dt_atendimento"), F.min("competencia").alias("competencia"),
        F.first("carater_canonico").alias("carater_canonico"), F.first("regime").alias("regime"),
        F.count("*").cast("int").alias("n_itens"), F.sum("vl_total").cast("decimal(16,2)").alias("vl_total_conta"),
        F.array_sort(F.collect_set(F.when(eh_pac, F.col("cod_tuss")))).alias("procedimentos_pacote"),
        F.countDistinct("carater_canonico").alias("_n_carater"), F.countDistinct("regime").alias("_n_regime"),
        F.countDistinct("id_beneficiario_hash").alias("_n_benef"), F.countDistinct("dt_atendimento").alias("_n_data"))
        .withColumn("tem_pacote", F.size("procedimentos_pacote") > 0)
        .withColumn("conflito_semantico", (F.col("regime") == "PRONTO_SOCORRO") & (F.col("carater_canonico") == "ELETIVO")))


COLUNAS_SILVER_CONTA = ["id_conta", "id_prestador", "id_beneficiario_hash", "dt_atendimento", "competencia",
                        "carater_canonico", "regime", "n_itens", "vl_total_conta", "tem_pacote", "procedimentos_pacote",
                        "conflito_semantico"]


def silver_atendimento(conta: DataFrame, item: DataFrame, params: dict) -> DataFrame:
    """Conceito derivado T11 (beneficiário × dia): detecta fragmentação (AMB-02) e cirurgia repetida (AMB-08)."""
    inclusos = pacote_codigos(params)["inclusos"]
    k = ["id_beneficiario_hash", "dt_atendimento"]
    item_c = item.join(conta.select("id_conta", "tem_pacote"), "id_conta")
    sinais = item_c.groupBy(*k).agg(
        F.max(F.when(~F.col("tem_pacote") & F.col("cod_tuss").isin(inclusos), 1).otherwise(0)).alias("_incluso_fora"),
        F.max(F.when(F.col("conceito") == "PROCEDIMENTO_CIRURGICO", 1).otherwise(0)).alias("_tem_cir"),
        F.count(F.when(F.col("conceito") == "PROCEDIMENTO_CIRURGICO", 1)).alias("_n_cir"),
        F.countDistinct(F.when(F.col("conceito") == "PROCEDIMENTO_CIRURGICO", F.col("cod_tuss"))).alias("_n_cir_dist"))
    base = conta.groupBy(*k).agg(F.count("*").cast("int").alias("n_contas"),
                                 F.array_sort(F.collect_list("id_conta")).alias("contas"),
                                 F.max(F.col("tem_pacote").cast("int")).cast("boolean").alias("alguma_conta_com_pacote"))
    return (base.join(sinais, k, "left")
            .withColumn("suspeita_fragmentacao",
                        (F.col("n_contas") > 1) & F.col("alguma_conta_com_pacote") & (F.col("_incluso_fora") == 1))
            .withColumn("procedimento_cirurgico_repetido", (F.col("n_contas") > 1) & (F.col("_n_cir") > F.col("_n_cir_dist")))
            .select(*k, "n_contas", "contas", "alguma_conta_com_pacote", "suspeita_fragmentacao",
                    "procedimento_cirurgico_repetido"))


# ============================================================================== GOLD · dimensões
def dim_data(item: DataFrame) -> DataFrame:
    lim = item.agg(F.trunc(F.min("dt_atendimento"), "month").alias("i"),
                   F.last_day(F.max("dt_atendimento")).alias("f"))
    return (lim.select(F.explode(F.sequence("i", "f")).alias("data"))
            .select("data", F.trunc("data", "month").alias("competencia"), F.year("data").alias("ano"),
                    F.month("data").alias("mes"), F.date_format("data", "MMMM").alias("nome_mes"),
                    F.dayofweek("data").alias("dia_semana"), F.dayofweek("data").isin(1, 7).alias("fim_de_semana")))


def dim_prestador(item: DataFrame) -> DataFrame:
    return item.groupBy("id_prestador").agg(F.max("nome_prestador").alias("nome_prestador"))


def dim_item_tuss(map_tuss: DataFrame) -> DataFrame:
    return map_tuss.select("cod_tuss", "descricao_canonica", "conceito", "conceito_pai", "tipo_item_origem", "porte_sala")


def dim_perfil_atendimento(dominios: DataFrame) -> DataFrame:
    car = dominios.where("dominio = 'carater_atendimento'").select(F.col("canonico").alias("carater_canonico")).distinct()
    reg = dominios.where("dominio = 'regime_atendimento'").select(F.col("canonico").alias("regime")).distinct()
    conflito = (F.col("regime") == "PRONTO_SOCORRO") & (F.col("carater_canonico") == "ELETIVO")
    return (car.crossJoin(reg)
            .withColumn("sk_perfil", F.concat_ws("|", "carater_canonico", "regime"))
            .withColumn("conflito_semantico", conflito)
            .withColumn("descricao", F.when(conflito, F.lit("Conflito: regime PS com caráter eletivo (AMB-01)"))
                        .otherwise(F.concat_ws(" em ", "carater_canonico", "regime")))
            .select("sk_perfil", "carater_canonico", "regime", "conflito_semantico", "descricao"))


def dim_contrato(spark: SparkSession, params: dict) -> DataFrame:
    c = params["contrato"]
    linha = [(params["versao_contrato"], c["id_contrato"], params.get("id_prestador", "P001"), c["vigencia_inicio"],
              int(c["vigencia_meses"]), params.get("aprovado_por"), params.get("data_aprovacao"))]
    return (spark.createDataFrame(linha, "versao_contrato string, id_contrato string, id_prestador string, ini string,"
                                         " meses int, aprovado_por string, data_aprovacao string")
            .withColumn("vigencia_inicio", F.to_date("ini"))
            .withColumn("vigencia_fim", F.date_sub(F.add_months("vigencia_inicio", F.col("meses")), 1))
            .withColumn("vigente", F.lit(True))
            .select("versao_contrato", "id_contrato", "id_prestador", "vigencia_inicio", "vigencia_fim", "aprovado_por",
                    "data_aprovacao", "vigente"))


def dim_item_contratado(spark: SparkSession, params: dict) -> DataFrame:
    proc = {p["codigo_procedimento"]: p["taxa_sala_codigo"] for p in params["anexo_ii"]}
    mats = {m for p in params["anexo_ii"] for m in p["materiais_rotina"]}
    cond = {t["codigo"]: t["carater_permitido"] for t in params["taxas_condicionadas"]}
    linhas = [(params["versao_contrato"], i["codigo"], float(i["valor_teto"]), i["codigo"] in proc, proc.get(i["codigo"]),
               i["codigo"] in mats, cond.get(i["codigo"])) for i in params["anexo_i"]]
    return (spark.createDataFrame(linhas, "versao_contrato string, cod_tuss string, vl_teto double, procedimento_em_pacote boolean,"
                                          " taxa_sala_do_pacote string, material_incluso_no_pacote boolean,"
                                          " carater_permitido array<string>")
            .withColumn("vl_teto", F.col("vl_teto").cast("decimal(12,2)")))


# ============================================================================== GOLD · fato_item
def fato_item(item: DataFrame, conta: DataFrame, item_contratado: DataFrame, run_id: str) -> DataFrame:
    ic = item_contratado.select("cod_tuss", F.col("vl_teto").alias("vl_teto_unitario"))
    # Sem ação imediata (.first()): num pipeline Lakeflow a dimensão pode estar vazia na montagem do grafo.
    versao = item_contratado.agg(F.max("versao_contrato").alias("versao_contrato"))   # 1 linha
    df = (item.join(conta.select("id_conta", F.col("tem_pacote").alias("conta_tem_pacote"), "conflito_semantico"), "id_conta")
          .join(F.broadcast(ic), "cod_tuss", "left")
          .crossJoin(F.broadcast(versao))
          .withColumn("tem_preco_pactuado", F.col("vl_teto_unitario").isNotNull())
          .withColumn("vl_cobrado", F.col("vl_total"))
          .withColumn("vl_excedente_potencial",
                      F.when(F.col("tem_preco_pactuado"),
                             F.greatest(F.lit(0), F.col("vl_unitario") - F.col("vl_teto_unitario")) * F.col("qtd"))
                      .otherwise(F.lit(0)).cast("decimal(14,2)"))
          .withColumn("sk_perfil", F.concat_ws("|", "carater_canonico", "regime"))
          .withColumn("run_id", F.lit(run_id)))
    return df.select(*COLUNAS_FATO_ITEM)


COLUNAS_FATO_ITEM = ["id_item", "id_conta", "id_prestador", "id_beneficiario_hash", "competencia", "dt_atendimento",
                     "sk_perfil", "carater_canonico", "carater_origem", "regime", "cod_tuss", "conceito", "conceito_pai",
                     "qtd", "vl_unitario", "vl_cobrado", "tem_preco_pactuado", "vl_teto_unitario",
                     "vl_excedente_potencial", "conta_tem_pacote", "conflito_semantico", "versao_contrato",
                     "versao_semantica", "run_id"]


# ============================================================================== Parte 2 · funil
def bronze_inteligencias_de_planilha(spark: SparkSession, caminho_xlsx: str) -> DataFrame:
    """A planilha não é lida pelo Spark nativamente: openpyxl → linhas de texto (bronze = fiel à origem)."""
    import openpyxl

    wb = openpyxl.load_workbook(caminho_xlsx, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    sinistro = str(rows[0][1])
    mes = str(rows[1][1])
    cab = rows[3]
    linhas = []
    for r in rows[4:]:
        if not r[0] or str(r[0]).strip().lower() == "total" or r[1] is None:
            continue
        linhas.append(tuple(None if v is None else str(v) for v in (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[8]))
                      + (sinistro, mes, Path(caminho_xlsx).name))
    assert cab[0] == "Inteligencias", f"layout da planilha mudou: {cab}"
    return (spark.createDataFrame(linhas, "inteligencia string, tipo string, status string, economia_identificada string,"
                                          " economia_enviada_operadora string, economia_enviada_prestador string,"
                                          " economia_efetivado string, media_efetivacao_arvo string,"
                                          " sinistro_processado string, mes_sinistro string, _arquivo string")
            .withColumn("_ingest_ts", F.current_timestamp()))


def silver_funil(bronze: DataFrame, cliente: str = "Parthenon") -> DataFrame:
    return bronze.select(
        F.trunc(F.to_date(F.substring("mes_sinistro", 1, 10)), "month").alias("competencia"),
        F.lit(cliente).alias("cliente"), F.trim("inteligencia").alias("inteligencia"),
        F.trim("tipo").alias("tipo_inteligencia"),
        F.when(F.lower(F.trim("status")).startswith("ligad"), "Ligada").otherwise("Desligada").alias("status_inteligencia"),
        *[F.col(o).cast("double").cast("decimal(16,2)").alias(d) for o, d in [
            ("economia_identificada", "vl_identificado"), ("economia_enviada_operadora", "vl_enviado_operadora"),
            ("economia_enviada_prestador", "vl_enviado_prestador"), ("economia_efetivado", "vl_efetivado")]],
        F.col("media_efetivacao_arvo").cast("double").alias("taxa_efetivacao_benchmark"),
        F.col("sinistro_processado").cast("double").cast("decimal(18,2)").alias("sinistro_processado"))


def fato_funil_economia(silver: DataFrame) -> DataFrame:
    """Mantém o sinistro processado como denominador do indicador-norte (M20). É SEMIADITIVO: as metric views
    usam MAX por competência, nunca SUM."""
    return silver.withColumnRenamed("sinistro_processado", "vl_sinistro_processado")


def dim_inteligencia(silver: DataFrame) -> DataFrame:
    return silver.groupBy("inteligencia").agg(F.first("tipo_inteligencia").alias("tipo_inteligencia"))
