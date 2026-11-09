"""Harness LOCAL da F5: executa as mesmas transformações do pipeline Lakeflow, em batch, com a mesma
semântica de expectations (warn conta; quarentena desvia com motivo; fail interrompe).

  python -m medalhao.local --sinistro arvo.case/sinistro-hospital-saorafael.csv --planilha arvo.case/Inteligencias_apos_6_meses.xlsx
"""
from __future__ import annotations

import argparse
import time
import uuid
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from motor import motor

from . import transformacoes as tf


class ExpectationFalhou(Exception):
    pass


def spark_local() -> SparkSession:
    """Heap EXPLÍCITO: com o padrão (~1 GB), várias execuções no mesmo processo esgotam a memória e o JVM
    entra em GC contínuo (diagnosticado: 5.852 full GCs, 507 s de 600 s em GC). Ajuste por ARVO_SPARK_MEM."""
    import os

    return (SparkSession.builder.master("local[2]").appName("arvo-f5-local")
            .config("spark.driver.memory", os.environ.get("ARVO_SPARK_MEM", "3g"))
            .config("spark.sql.shuffle.partitions", "4").config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "America/Sao_Paulo").getOrCreate())


def liberar(out: dict) -> None:
    """Desfaz o cache de uma execução. Sem isso, cada `executar()` deixa DataFrames presos na memória do driver."""
    for df in out.get("_cache", []):
        df.unpersist()
    out["_cache"] = []


def medir(df, tabela: str, regras: list[dict], run_id: str) -> list[dict]:
    """Conta as violações de TODAS as expectations da tabela numa única passada."""
    if not regras:
        return []
    aggs = [F.sum(F.when(~F.coalesce(F.expr(r["expr"]), F.lit(False)), 1).otherwise(0)).alias(r["id"]) for r in regras]
    linha = df.agg(F.count("*").alias("_n"), *aggs).first()
    ts = time.time()
    return [{"run_id": run_id, "tabela": tabela, "expectation": r["id"], "dimensao": r["dimensao"], "acao": r["acao"],
             "avaliados": int(linha["_n"]), "reprovados": int(linha[r["id"]] or 0),
             "taxa_reprovacao": (int(linha[r["id"]] or 0) / linha["_n"]) if linha["_n"] else 0.0, "executado_em": ts}
            for r in regras]


def executar(spark: SparkSession, sinistro: str, planilha: str | None = None, catalogo: str = "arvo_dev",
             contrato_aprovado: str | None = None, run_id: str | None = None, regras: str | None = None) -> dict:
    run_id = run_id or f"local-{uuid.uuid4().hex[:8]}"
    exp = tf.carregar_expectations()
    params = tf.carregar_parametros_contrato(catalogo, Path(contrato_aprovado) if contrato_aprovado else None)
    mp, dom, ver = tf.df_map_tuss(spark), tf.df_dominios(spark), tf.versao_semantica()
    out, dq = {"_cache": []}, []

    def guardar(df):  # todo cache fica registrado para `liberar()`
        out["_cache"].append(df.cache())
        return out["_cache"][-1]


    out["bronze.sinistro_raw"] = tf.bronze_sinistro(tf.ler_csv_origem(spark, sinistro), F.lit(Path(sinistro).name)).transform(guardar)
    cand = tf.silver_item_conta_candidatos(out["bronze.sinistro_raw"], mp, dom, ver)
    regras_item = exp["silver.item_conta"]
    marcado = tf.marcar_violacoes(cand, regras_item, "quarentena").transform(guardar)
    dq += medir(cand, "silver.item_conta", regras_item, run_id)
    out["quarantine.item_conta_rejeitado"] = tf.quarentena(marcado)
    out["silver.item_conta"] = marcado.where(F.size("_motivos") == 0).select(*tf.COLUNAS_SILVER_ITEM).transform(guardar)

    conta_m = tf.silver_conta(out["silver.item_conta"], params).transform(guardar)
    dq += medir(conta_m, "silver.conta", exp["silver.conta"], run_id)
    out["silver.conta"] = conta_m.select(*tf.COLUNAS_SILVER_CONTA)
    out["silver.atendimento"] = tf.silver_atendimento(out["silver.conta"], out["silver.item_conta"], params)

    out["gold.dim_data"] = tf.dim_data(out["silver.item_conta"])
    out["gold.dim_prestador"] = tf.dim_prestador(out["silver.item_conta"])
    out["gold.dim_item_tuss"] = tf.dim_item_tuss(mp)
    out["gold.dim_perfil_atendimento"] = tf.dim_perfil_atendimento(dom)
    out["gold.dim_contrato"] = tf.dim_contrato(spark, params)
    out["gold.dim_item_contratado"] = tf.dim_item_contratado(spark, params)
    fato = tf.fato_item(out["silver.item_conta"], out["silver.conta"], out["gold.dim_item_contratado"], run_id).transform(guardar)
    medidas_gold = medir(fato, "gold.fato_item", exp["gold.fato_item"], run_id)
    dq += medidas_gold
    falhas = [m for m in medidas_gold if m["acao"] == "fail" and m["reprovados"] > 0]
    if falhas:
        liberar(out)
        raise ExpectationFalhou(f"invariantes violados em gold.fato_item: {falhas}")
    out["gold.fato_item"] = fato

    # ---------------- F6 · motor de regras
    cfg = motor.carregar_regras(regras) if regras else motor.carregar_regras()
    out["gold.dim_regra"] = motor.dim_regra(spark, cfg, params)
    out["gold.ponte_regra_inteligencia"] = motor.ponte_regra_inteligencia(spark)
    enr = motor.enriquecer(fato, out["silver.conta"], out["gold.dim_item_contratado"], out["gold.dim_contrato"], params).transform(guardar)
    apont = motor.avaliar(enr, cfg, run_id).transform(guardar)
    medidas_ap = medir(apont, "gold.fato_apontamento", exp["gold.fato_apontamento"], run_id)
    dq += medidas_ap
    falhas = [m for m in medidas_ap if m["acao"] == "fail" and m["reprovados"] > 0]
    if falhas:
        liberar(out)
        raise ExpectationFalhou(f"invariantes violados em gold.fato_apontamento: {falhas}")
    out["gold.fato_apontamento"] = apont
    out["gold.fato_item_auditado"] = motor.item_auditado(fato, apont)
    out["_resumo_motor"] = motor.resumo(enr, apont)

    if planilha:
        out["bronze.inteligencias_raw"] = tf.bronze_inteligencias_de_planilha(spark, planilha)
        out["silver.funil_inteligencia"] = tf.silver_funil(out["bronze.inteligencias_raw"])
        out["gold.fato_funil_economia"] = tf.fato_funil_economia(out["silver.funil_inteligencia"])
        out["gold.dim_inteligencia"] = tf.dim_inteligencia(out["silver.funil_inteligencia"])

    out["ops.dq_resultados"] = spark.createDataFrame(dq).withColumn("executado_em", F.col("executado_em").cast("timestamp"))
    out["_params_status"] = params["_status"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sinistro", required=True)
    ap.add_argument("--planilha")
    ap.add_argument("--saida", default="dados_medalhao_local")
    a = ap.parse_args()
    spark = spark_local()
    out = executar(spark, a.sinistro, a.planilha)
    for nome, df in out.items():
        if nome.startswith("_"):
            if nome == "_resumo_motor":
                print("motor:", df)
            continue
        df.write.mode("overwrite").parquet(f"{a.saida}/{nome}")
        print(f"{nome:40s} {df.count():>6} linhas")
    print("parâmetros de contrato:", out["_params_status"])
    out["ops.dq_resultados"].where("reprovados > 0").select("tabela", "expectation", "acao", "reprovados").show(truncate=False)


if __name__ == "__main__":
    main()
