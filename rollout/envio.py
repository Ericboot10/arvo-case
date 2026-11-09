"""F10 · Destino de cada apontamento: BLOQUEADO | NAO_ENVIAR | REVISAO_HUMANA | ENVIO_AUTOMATICO.

O motor (F6) diz O QUE glosar; esta camada decide SE e COMO sai, a partir de três entradas versionadas:
  - estado de cada regra (rollout/estado_regras.yaml)       → estágio DESLIGADA | SHADOW | CANARIO | AUTOMATICO
  - portão de sanidade do run (sanidade/portao.py, F9)      → invariante violado bloqueia o run inteiro
  - matriz de custo (avaliacao_cientifica/custos.yaml, F8)  → teto de valor do envio automático por regra
Precedência em rollout/estagios.yaml. Mesma função no job de envio e nos testes.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from avaliacao_cientifica.decisao import carregar_custos

AQUI = Path(__file__).resolve().parent
ESTAGIOS = AQUI / "estagios.yaml"
ESTADO = AQUI / "estado_regras.yaml"


def carregar(caminho: Path | None = None) -> dict:
    return yaml.safe_load(Path(caminho or ESTAGIOS).read_text("utf-8"))


def carregar_estado(caminho: Path | None = None) -> dict:
    return yaml.safe_load(Path(caminho or ESTADO).read_text("utf-8"))


def teto_valor(precisao_inf: float | None, custos: dict | None = None, cfg: dict | None = None) -> float:
    """Maior valor de glosa em que o envio automático custa menos, em esperança, que a revisão humana.
    Sem precisão medida, ou abaixo do piso de precisão do comitê → 0: nada sai automático."""
    c, cfg = custos or carregar_custos(), cfg or carregar()
    if precisao_inf is None or precisao_inf < c["piso_precisao_envio_automatico"]:
        return 0.0                     # abaixo do piso do comitê (AMB-20) nada sai automático, qualquer que seja o valor
    teto_max = float(cfg["teto_valor"]["teto_maximo"])
    if precisao_inf >= 1:
        return teto_max
    v = (c["custo_revisao_humana"] / (1 - precisao_inf) - c["custo_fp_operacional"]) / c["custo_fp_atrito_pct"]
    return round(max(0.0, min(v, teto_max)), 2)


def tabela_regras(spark: SparkSession, estado: dict, custos: dict | None = None, cfg: dict | None = None) -> DataFrame:
    linhas = [(r, e["estagio"], e.get("precisao_inf"), teto_valor(e.get("precisao_inf"), custos, cfg))
              for r, e in sorted(estado["regras"].items())]
    return spark.createDataFrame(linhas, "regra_principal string, estagio_regra string, precisao_inf double, teto_valor double")


def decidir(apontamentos: DataFrame, itens: DataFrame, estado: dict, portao_liberado: bool,
            custos: dict | None = None, cfg: dict | None = None) -> DataFrame:
    """1 linha por apontamento com estagio_regra, teto_valor, destino_envio e motivo_destino.
    Regra que não está no estado = DESLIGADA (o que não foi decidido não sai)."""
    spark = apontamentos.sparkSession
    regras = tabela_regras(spark, estado, custos, cfg)
    conflito = itens.select("id_item", F.coalesce("conflito_semantico", F.lit(False)).alias("_conflito"))
    a = (apontamentos.join(F.broadcast(regras), "regra_principal", "left").join(conflito, "id_item", "left")
         .withColumn("estagio_regra", F.coalesce("estagio_regra", F.lit("DESLIGADA")))
         .withColumn("teto_valor", F.coalesce("teto_valor", F.lit(0.0))))
    vl = F.col("vl_glosado").cast("double")
    destino = (F.when(F.lit(not portao_liberado), F.struct(F.lit("BLOQUEADO").alias("d"), F.lit("portão de sanidade fechado").alias("m")))
               .when(F.col("estagio_regra").isin("DESLIGADA", "SHADOW"),
                     F.struct(F.lit("NAO_ENVIAR").alias("d"), F.concat(F.lit("regra em "), F.col("estagio_regra")).alias("m")))
               .when(F.col("estagio_regra") == "CANARIO", F.struct(F.lit("REVISAO_HUMANA").alias("d"), F.lit("regra em CANARIO").alias("m")))
               .when(F.col("motivo_revisao").isNotNull(), F.struct(F.lit("REVISAO_HUMANA").alias("d"), F.col("motivo_revisao").alias("m")))
               .when(F.col("_conflito"), F.struct(F.lit("REVISAO_HUMANA").alias("d"), F.lit("conflito semântico no item").alias("m")))
               .when(vl > F.col("teto_valor"), F.struct(F.lit("REVISAO_HUMANA").alias("d"),
                                                        F.concat(F.lit("valor acima do teto da regra (R$ "),
                                                                 F.format_number(F.col("teto_valor"), 2), F.lit(")")).alias("m")))
               .otherwise(F.struct(F.lit("ENVIO_AUTOMATICO").alias("d"), F.lit("regra em AUTOMATICO, dentro do teto").alias("m"))))
    return (a.withColumn("_dest", destino)
            .select("id_apontamento", "id_item", "id_conta", "regra_principal", "vl_glosado", "estagio_regra", "teto_valor",
                    F.col("_dest.d").alias("destino_envio"), F.col("_dest.m").alias("motivo_destino"), "run_id"))


def resumo(destinos: DataFrame) -> list[dict]:
    return [r.asDict() for r in destinos.groupBy("regra_principal", "estagio_regra", "destino_envio")
            .agg(F.count("*").alias("apontamentos"), F.round(F.sum("vl_glosado"), 2).alias("vl_glosado"))
            .orderBy("regra_principal", "destino_envio").collect()]
