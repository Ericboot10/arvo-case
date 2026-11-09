# Databricks notebook source
# MAGIC %md
# MAGIC # F5 · Planilha de inteligências → `bronze.inteligencias_raw`
# MAGIC O Spark não lê `.xlsx` nativamente, então este notebook faz openpyxl → bronze, com append e fiel à origem.
# MAGIC A planilha chega em `/Volumes/<catalog>/bronze/landing/inteligencias/`.

# COMMAND ----------

# MAGIC %pip install openpyxl==3.1.5 pyyaml==6.0.2

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
CATALOG = dbutils.widgets.get("catalog")

import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.getcwd()).parents[1]))
from medalhao import transformacoes as tf  # noqa: E402

pasta = Path(f"/Volumes/{CATALOG}/bronze/landing/inteligencias")
arquivos = sorted(pasta.glob("*.xlsx")) if pasta.exists() else []
alvo = f"{CATALOG}.bronze.inteligencias_raw"
ja = set()
if spark.catalog.tableExists(alvo):
    ja = {r[0] for r in spark.table(alvo).select("_arquivo").distinct().collect()}
for arq in arquivos:
    if arq.name in ja:
        print("já ingerido (idempotente):", arq.name)
        continue
    tf.bronze_inteligencias_de_planilha(spark, str(arq)).write.mode("append").saveAsTable(alvo)
    print("ingerido:", arq.name)
