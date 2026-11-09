# Databricks notebook source
# MAGIC %md
# MAGIC # F9 · Portão de envio
# MAGIC Falha a task (e portanto o job de envio) se algum indicador **CRÍTICO** de `ops.v_sanidade_status` estiver em ALERTA.
# MAGIC Mesma função do teste local (`sanidade.portao.avaliar_portao`). Colocar como dependência de qualquer task que envie apontamentos.

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
CATALOG = dbutils.widgets.get("catalog")
assert CATALOG in {"arvo_dev", "arvo_stg", "arvo_prod"}

# COMMAND ----------

import json, os, sys
sys.path.insert(0, os.path.abspath("../../.."))    # src/ do bundle (pacote arvo)
from arvo.monitoring.portao import avaliar_portao          # noqa: E402

linhas = [r.asDict() for r in spark.table(f"{CATALOG}.ops.v_sanidade_status").collect()]
resultado = avaliar_portao(linhas)
print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
if not resultado["liberado"]:
    raise Exception("ENVIO BLOQUEADO pelo portão de sanidade: " +
                    "; ".join(f"{b['id_indicador']} {b['recorte']} (runbook {b['runbook']})" for b in resultado["bloqueios"]))
