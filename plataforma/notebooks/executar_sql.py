# Databricks notebook source
# MAGIC %md
# MAGIC # Executor de arquivo SQL parametrizado
# MAGIC Roda um `.sql` do repositório com parâmetros nomeados (`:catalog`) via `spark.sql(..., args=...)`.
# MAGIC Por que existe (ADR-004): os mesmos arquivos SQL rodam no SQL editor (parâmetro `:catalog`) e em Job serverless,
# MAGIC sem depender de warehouse nem de sintaxe de parâmetro diferente entre os dois.

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
dbutils.widgets.text("arquivo", "")
CATALOG, ARQUIVO = dbutils.widgets.get("catalog"), dbutils.widgets.get("arquivo")
assert CATALOG in {"arvo_dev", "arvo_stg", "arvo_prod"} and ARQUIVO.endswith(".sql")

# COMMAND ----------

import os, sys
sys.path.insert(0, os.path.abspath(".."))          # plataforma/
from sqlutil import dividir_sql                    # noqa: E402

with open(ARQUIVO, encoding="utf-8") as f:
    comandos = dividir_sql(f.read())
for i, cmd in enumerate(comandos, 1):
    usa_param = ":catalog" in cmd
    spark.sql(cmd, args={"catalog": CATALOG} if usa_param else None)
    print(f"[{i}/{len(comandos)}] ok: {cmd.splitlines()[0][:90]}")
