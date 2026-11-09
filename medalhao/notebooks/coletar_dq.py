# Databricks notebook source
# MAGIC %md
# MAGIC # F5 · Event log do pipeline → `ops.dq_resultados`
# MAGIC As métricas de expectations ficam no event log do Lakeflow (eventos `flow_progress`, campo `data_quality.expectations`).
# MAGIC Este notebook as normaliza no mesmo schema que o harness local grava. Assim o painel de sanidade (F9) lê um lugar só.
# MAGIC **Validar no workspace** o acesso ao event log (`event_log(<pipeline_id>)`) e o caminho JSON dos campos.

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
dbutils.widgets.text("pipeline_id", "")
CATALOG, PIPELINE = dbutils.widgets.get("catalog"), dbutils.widgets.get("pipeline_id")

import yaml, os
from pathlib import Path
EXP = yaml.safe_load((Path(os.getcwd()).parent / "expectations.yaml").read_text("utf-8"))
meta = {r["id"]: (t, r["dimensao"], r["acao"]) for t, regras in EXP.items() if t != "versao" for r in regras}

# COMMAND ----------

ev = spark.sql(f"""
  SELECT origin.update_id AS run_id, origin.flow_name AS fluxo, timestamp AS executado_em,
         explode(from_json(details:flow_progress.data_quality.expectations,
                 'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) AS e
  FROM event_log('{PIPELINE}')
  WHERE event_type = 'flow_progress' AND details:flow_progress.data_quality IS NOT NULL
""")
linhas = []
for r in ev.collect():
    t, dim, acao = meta.get(r.e.name, (r.e.dataset, None, None))
    av = (r.e.passed_records or 0) + (r.e.failed_records or 0)
    linhas.append({"run_id": r.run_id, "tabela": t, "expectation": r.e.name, "dimensao": dim, "acao": acao,
                   "avaliados": av, "reprovados": r.e.failed_records or 0,
                   "taxa_reprovacao": (r.e.failed_records or 0) / av if av else 0.0, "executado_em": r.executado_em})
if linhas:
    spark.createDataFrame(linhas).write.mode("append").saveAsTable(f"{CATALOG}.ops.dq_resultados")
print(len(linhas), "métricas de expectation gravadas")
