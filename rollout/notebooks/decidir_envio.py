# Databricks notebook source
# MAGIC %md
# MAGIC # F10 · Decidir o destino de cada apontamento do run
# MAGIC Lê o estado das regras (rollout/estado_regras.yaml), o portão de sanidade (ops.v_sanidade_status) e o motor
# MAGIC (gold.fato_apontamento) e grava ops.rollout_destino. Em prod, o que fica em SHADOW vai para gold_shadow.
# MAGIC NÃO envia nada ao cliente: o envio lê ops.rollout_destino onde destino_envio = 'ENVIO_AUTOMATICO' ou aprovado na fila.

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
CATALOG = dbutils.widgets.get("catalog")
assert CATALOG in {"arvo_dev", "arvo_stg", "arvo_prod"}

# COMMAND ----------

import os, sys
sys.path.insert(0, os.path.abspath("../.."))          # raiz do bundle
from pyspark.sql import functions as F                 # noqa: E402
from rollout import envio                              # noqa: E402
from sanidade.portao import avaliar_portao             # noqa: E402

portao = avaliar_portao([r.asDict() for r in spark.table(f"{CATALOG}.ops.v_sanidade_status").collect()])
ap = spark.table(f"{CATALOG}.gold.fato_apontamento")
itens = spark.table(f"{CATALOG}.gold.fato_item_auditado")
destinos = envio.decidir(ap, itens, envio.carregar_estado(), portao["liberado"]).withColumn("decidido_em", F.current_timestamp())
destinos.write.mode("append").saveAsTable(f"{CATALOG}.ops.rollout_destino")
if CATALOG == "arvo_prod":
    shadow = (ap.join(destinos.where("destino_envio = 'NAO_ENVIAR'").select("id_apontamento", "estagio_regra", "destino_envio"),
                      "id_apontamento"))
    shadow.write.mode("append").saveAsTable("arvo_prod.gold_shadow.fato_apontamento")
display(destinos.groupBy("regra_principal", "estagio_regra", "destino_envio").count())
