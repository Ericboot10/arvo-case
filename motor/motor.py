"""F6 · Motor de regras DETERMINÍSTICO (funções puras de DataFrame, como na F5).

Fluxo:
  gold.fato_item + silver.conta + gold.dim_item_contratado + gold.dim_contrato
      → enriquecer()   colunas semânticas e papéis contratuais (as únicas que as regras podem ler)
      → avaliar()      regras.yaml: hits por item → fundamento principal + subsidiárias, valor, revisão, justificativa
      → gold.fato_apontamento (1 por item glosado) e gold.fato_item_auditado (todos os itens + resultado)

Nenhuma IA no caminho da decisão: mesma entrada + mesmas versões = mesmos apontamentos (testado).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

RAIZ = Path(__file__).resolve().parents[1]

COLUNAS_APONTAMENTO = ["id_apontamento", "id_item", "id_conta", "regra_principal", "clausula_principal",
                       "clausulas_subsidiarias", "vl_cobrado", "vl_referencia", "vl_glosado", "justificativa",
                       "evidencia", "versao_regra", "versao_contrato", "versao_semantica", "run_id", "status_envio",
                       "motivo_revisao"]
COLUNAS_ITEM_AUDITADO = ["id_item", "id_conta", "id_prestador", "id_beneficiario_hash", "competencia", "dt_atendimento",
                         "carater_canonico", "carater_origem", "regime", "cod_tuss", "conceito", "conceito_pai", "qtd",
                         "vl_unitario", "vl_cobrado", "tem_preco_pactuado", "vl_teto_unitario", "vl_excedente_potencial",
                         "conta_tem_pacote", "conflito_semantico", "glosado", "regra_principal", "clausula_principal",
                         "vl_glosado", "versao_contrato", "versao_semantica", "run_id"]


def carregar_regras(caminho: Path | None = None) -> dict:
    return yaml.safe_load((caminho or RAIZ / "motor" / "regras.yaml").read_text("utf-8"))


# ============================================================================== enriquecimento
def enriquecer(fato_item: DataFrame, conta: DataFrame, item_contratado: DataFrame, dim_contrato: DataFrame,
               params: dict) -> DataFrame:
    """Traduz o item para colunas semânticas e PAPÉIS CONTRATUAIS. É a única visão que as regras enxergam."""
    sala_do_proc = {p["codigo_procedimento"]: p["taxa_sala_codigo"] for p in params["anexo_ii"]}
    mapa = F.create_map(*[x for k, v in sala_do_proc.items() for x in (F.lit(k), F.lit(v))])
    # Vigência por join de 1 linha, sem ação imediata (.first()): funciona igual no harness local e no Lakeflow.
    vig = dim_contrato.where("vigente").agg(F.min("vigencia_inicio").alias("_vig_ini"), F.max("vigencia_fim").alias("_vig_fim"))
    papeis = item_contratado.select("cod_tuss", "material_incluso_no_pacote", "carater_permitido")
    return (fato_item
            .join(conta.select("id_conta", "procedimentos_pacote"), "id_conta", "left")
            .join(F.broadcast(papeis), "cod_tuss", "left")
            .withColumn("procedimentos_pacote", F.coalesce("procedimentos_pacote", F.array().cast("array<string>")))
            .withColumn("_salas_do_pacote", F.transform("procedimentos_pacote", lambda p: mapa[p]))
            .withColumn("e_sala_do_pacote_da_conta",
                        F.coalesce(F.array_contains("_salas_do_pacote", F.col("cod_tuss")), F.lit(False)))
            .withColumn("e_sala_outro_porte", (F.col("conceito") == "TAXA_SALA_CIRURGICA") & F.col("conta_tem_pacote")
                        & ~F.col("e_sala_do_pacote_da_conta"))
            .withColumn("e_material_incluso_pacote", F.coalesce("material_incluso_no_pacote", F.lit(False)))
            .withColumn("e_taxa_condicionada", F.col("carater_permitido").isNotNull())
            .withColumn("carater_permitido_item",
                        F.coalesce(F.array_contains("carater_permitido", F.col("carater_canonico")), F.lit(False)))
            .crossJoin(F.broadcast(vig))
            .withColumn("dentro_vigencia", F.coalesce(F.col("dt_atendimento").between(F.col("_vig_ini"), F.col("_vig_fim")),
                                                      F.lit(False)))
            .drop("_vig_ini", "_vig_fim"))


# ============================================================================== templates
def _brl(col: F.Column) -> F.Column:
    return F.concat(F.lit("R$ "), F.translate(F.format_number(col, 2), ",.", ".,"))


def _valor_do_campo(nome: str) -> F.Column:
    if nome.startswith("vl_"):
        return _brl(F.col(nome))
    if nome == "procedimentos_pacote":
        return F.array_join(F.col(nome), ", ")
    return F.col(nome).cast("string")


def renderizar(template: str) -> F.Column:
    """'{campo}' vira o valor da coluna (vl_* em R$ pt-BR). Determinístico: sem IA, sem data atual."""
    partes, pos = [], 0
    for m in re.finditer(r"\{(\w+)\}", template):
        if m.start() > pos:
            partes.append(F.lit(template[pos:m.start()]))
        partes.append(_valor_do_campo(m.group(1)))
        pos = m.end()
    if pos < len(template):
        partes.append(F.lit(template[pos:]))
    return F.concat(*partes)


def campos_do_template(template: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", template))


# ============================================================================== avaliação
def avaliar(enriquecido: DataFrame, cfg: dict, run_id: str) -> DataFrame:
    """Retorna gold.fato_apontamento: 1 linha por item com ao menos uma regra disparada."""
    pre = F.expr(cfg.get("pre_condicao_global", "true"))
    regras = cfg["regras"]
    hits = []
    for ordem, r in enumerate(regras):
        revs = [F.when(F.expr(c["condicao"]), F.lit(c["motivo"])) for c in r.get("revisao_humana", [])]
        motivo = F.concat_ws("; ", *revs) if revs else F.lit("")
        hits.append(F.when(pre & F.coalesce(F.expr(r["condicao"]), F.lit(False)), F.struct(
            F.lit(r["prioridade"]).alias("prioridade"), F.lit(ordem).alias("ordem"), F.lit(r["id"]).alias("regra"),
            F.lit(r["clausula"]).alias("clausula"), F.expr(r["valor"]).cast("decimal(14,2)").alias("valor"),
            F.expr(r["referencia"]).cast("decimal(14,2)").alias("referencia"), motivo.alias("motivo_revisao"))))

    df = (enriquecido.withColumn("_hits", F.array_sort(F.filter(F.array(*hits), lambda x: x.isNotNull())))
          .where(F.size("_hits") > 0)
          .withColumn("_p", F.col("_hits")[0])
          .withColumn("regra_principal", F.col("_p.regra"))
          .withColumn("clausula_principal", F.col("_p.clausula"))
          .withColumn("clausulas_subsidiarias", F.array_sort(F.array_except(
              F.array_distinct(F.transform("_hits", lambda x: x["clausula"])), F.array(F.col("_p.clausula")))))
          .withColumn("vl_glosado", F.least(F.col("_p.valor"), F.col("vl_cobrado")).cast("decimal(14,2)"))
          .withColumn("vl_referencia", F.col("_p.referencia"))
          .withColumn("_motivos", F.filter(F.transform("_hits", lambda x: x["motivo_revisao"]), lambda m: m != ""))
          .withColumn("motivo_revisao", F.when(F.size("_motivos") > 0, F.array_join("_motivos", "; ")))
          .withColumn("status_envio", F.when(F.col("motivo_revisao").isNotNull(), "REVISAO_HUMANA").otherwise("PRONTO")))

    just = F.lit(None).cast("string")
    evid = F.lit(None).cast("array<string>")
    for r in regras:
        cond = F.col("regra_principal") == r["id"]
        just = F.when(cond, renderizar(" ".join(r["justificativa"].split()))).otherwise(just)
        evid = F.when(cond, F.array(*[renderizar(e) for e in r["evidencia"]])).otherwise(evid)
    versao = cfg["versao_regras"]
    return (df.withColumn("justificativa", just).withColumn("evidencia", evid)
            .withColumn("versao_regra", F.concat(F.col("regra_principal"), F.lit(f"@{versao}")))
            .withColumn("id_apontamento", F.substring(F.sha2(F.concat_ws(
                "|", "id_item", F.lit(versao), "versao_contrato"), 256), 1, 16))
            .withColumn("run_id", F.lit(run_id))
            .select(*COLUNAS_APONTAMENTO))


def item_auditado(fato_item: DataFrame, apontamento: DataFrame) -> DataFrame:
    a = apontamento.select("id_item", "regra_principal", "clausula_principal",
                           F.col("vl_glosado").alias("_vg"))
    return (fato_item.join(a, "id_item", "left")
            .withColumn("glosado", F.col("regra_principal").isNotNull())
            .withColumn("vl_glosado", F.coalesce("_vg", F.lit(0)).cast("decimal(14,2)"))
            .select(*COLUNAS_ITEM_AUDITADO))


# ============================================================================== dimensões da F6
def dim_regra(spark: SparkSession, cfg: dict, params: dict) -> DataFrame:
    v = cfg["versao_regras"]
    linhas = [(r["id"], f"{r['id']}@{v}", r["nome"], r["clausula"], r["tipo"], r["tipo_glosa"], int(r["prioridade"]),
               params["versao_contrato"], r["defensabilidade"]) for r in cfg["regras"]]
    return spark.createDataFrame(linhas, "regra_id string, versao_regra string, nome string, clausula string, tipo string,"
                                         " tipo_glosa string, prioridade int, versao_contrato string, defensabilidade string")


def ponte_regra_inteligencia(spark: SparkSession) -> DataFrame:
    f = yaml.safe_load((RAIZ / "semantic" / "funil.yaml").read_text("utf-8"))
    linhas = [(x["regra_id"], x["inteligencia"], x["tipo_vinculo"], "proposto") for x in f["regra_inteligencia"]]
    return spark.createDataFrame(linhas, "regra_id string, inteligencia string, tipo_vinculo string, status_validacao string")


def resumo(enriquecido: DataFrame, apontamento: DataFrame) -> dict:
    e = enriquecido.agg(F.count("*").alias("itens"), F.count_if(~F.col("dentro_vigencia")).alias("fora_vigencia")).first()
    a = apontamento.agg(F.count("*").alias("apontamentos"), F.sum("vl_glosado").alias("vl_glosado"),
                        F.count_if(F.col("status_envio") == "REVISAO_HUMANA").alias("revisao_humana")).first()
    por = {r[0]: (r[1], float(r[2])) for r in apontamento.groupBy("regra_principal")
           .agg(F.count("*"), F.sum("vl_glosado")).collect()}
    return {"itens": e["itens"], "fora_vigencia": e["fora_vigencia"], "apontamentos": a["apontamentos"],
            "vl_glosado": float(a["vl_glosado"] or 0), "revisao_humana": a["revisao_humana"], "por_regra": por}
