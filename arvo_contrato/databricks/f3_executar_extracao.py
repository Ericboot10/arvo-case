# Databricks notebook source
# MAGIC %md
# MAGIC # F3 · Extrair contrato (task de Job)
# MAGIC Roda o mesmo pacote `arvo_contrato` do Git folder. O core não muda entre local e Databricks; muda só onde os resultados são gravados.
# MAGIC
# MAGIC 1. Lê o PDF do Volume (`/Volumes/<catalog>/contracts/raw/`).
# MAGIC 2. Executa `pipeline.executar`, que para em `REVISAO_HUMANA`.
# MAGIC 3. Grava a telemetria em `ops.llm_calls`, os candidatos em `contracts.contract_field_candidates` e o estado em `ops.contract_extraction_state`.
# MAGIC 4. Copia `revisao.md` e `aprovacao.yaml` para o Volume, para o Jurídico revisar.
# MAGIC
# MAGIC **Modo `real`:** as credenciais vêm de secret scopes, nunca do código. Pelo AI Gateway, o próprio token do workspace basta.

# COMMAND ----------

# MAGIC %pip install pdfplumber==0.11.10 pyyaml==6.0.2 anthropic openai

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
dbutils.widgets.dropdown("modo", "simulado", ["simulado", "real"])
dbutils.widgets.text("pdf", "Contrato-parthenon-x-hospital-sao-rafael.pdf")
dbutils.widgets.text("secret_scope", "arvo-ia")
CATALOG, MODO, PDF = dbutils.widgets.get("catalog"), dbutils.widgets.get("modo"), dbutils.widgets.get("pdf")
assert CATALOG in {"arvo_dev", "arvo_stg", "arvo_prod"}

# COMMAND ----------

import json, os, sys, shutil
from pathlib import Path

REPO = Path(os.getcwd()).parents[1]          # .../Arvo_Case (Git folder)
sys.path.insert(0, str(REPO))
from arvo_contrato.pipeline import executar  # noqa: E402

if MODO == "real":
    scope = dbutils.widgets.get("secret_scope")
    # DATABRICKS_TOKEN: token de service principal (OAuth M2M) guardado no scope, nunca token pessoal
    for chave in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DATABRICKS_TOKEN"):
        try:
            os.environ[chave] = dbutils.secrets.get(scope, chave)
        except Exception:
            print(f"{chave}: não configurada no scope {scope}; os adapters correspondentes vão falhar e cair no fallback")
    os.environ.setdefault("DATABRICKS_HOST", "https://" + spark.conf.get("spark.databricks.workspaceUrl"))

VOL = Path(f"/Volumes/{CATALOG}/contracts/raw")
import tempfile  # noqa: E402

# Pasta de trabalho local da execução: no compute serverless /local_disk0 não é gravável; o tmp do sistema é.
pasta = executar(VOL / PDF, Path(tempfile.gettempdir()) / "arvo_runs", modo=MODO)
estado = json.loads((pasta / "estado.json").read_text())
print(pasta, estado["estado"])

# COMMAND ----------

from pyspark.sql import functions as F, types as T

linhas = [json.loads(l) for l in (pasta / "llm_calls.jsonl").read_text().splitlines()]
for r in linhas:
    for k in ("params_pedidos", "params_aplicados", "params_ignorados"):
        r[k] = {a: str(b) for a, b in (r.get(k) or {}).items()}
if linhas:
    (spark.createDataFrame(linhas, schema=spark.table(f"{CATALOG}.ops.llm_calls").schema)
     .write.mode("append").saveAsTable(f"{CATALOG}.ops.llm_calls"))

rec = json.loads((pasta / "reconciliacao.json").read_text())
cand = [{"chave_idempotencia": estado["chave_idempotencia"], "run_id": linhas[0]["run_id"] if linhas else None,
         "contrato": estado["contrato"], "campo": l["campo"], "status": l["status"], "fonte": f,
         "valor": json.dumps(v["valor"], ensure_ascii=False), "quote": v["quote"], "quote_ok": v["quote_ok"],
         "valor_ok": v["valor_ok"], "juiz_veredito": (l.get("juiz") or {}).get("veredito"),
         "juiz_quote_ok": (l.get("juiz") or {}).get("quote_ok")}
        for l in rec["campos"] for f, v in l["fontes"].items()]
spark.createDataFrame(cand).write.mode("append").saveAsTable(f"{CATALOG}.contracts.contract_field_candidates")

spark.createDataFrame([{"chave_idempotencia": estado["chave_idempotencia"], "contrato": estado["contrato"],
                        "estado": estado["estado"], "historico": json.dumps(estado["historico"], ensure_ascii=False)}]) \
     .withColumn("atualizado_em", F.current_timestamp()) \
     .write.mode("append").saveAsTable(f"{CATALOG}.ops.contract_extraction_state")

destino = Path(f"/Volumes/{CATALOG}/contracts/revisao/{estado['contrato']}/{estado['chave_idempotencia'][:12]}")
destino.mkdir(parents=True, exist_ok=True)
for arq in ("revisao.md", "aprovacao.yaml", "reconciliacao.json"):
    shutil.copy(pasta / arq, destino / arq)
print("pacote de revisão em", destino)
