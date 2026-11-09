# Databricks notebook source
# MAGIC %md
# MAGIC # G4 · Hello pipeline: o ambiente está pronto?
# MAGIC Cada checagem grava uma linha em `<catalog>.ops.plataforma_checks`, que é a **evidência do Gate G4**.
# MAGIC Falha em checagem `BLOQUEIA` faz o job falhar.

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
dbutils.widgets.text("alvo", "dev")
CATALOG, ALVO = dbutils.widgets.get("catalog"), dbutils.widgets.get("alvo")

ESPERADOS = {"bronze", "silver", "gold", "semantic", "contracts", "ops", "quarantine"}
EXTRAS = {"arvo_dev": {"sandbox"}, "arvo_stg": set(), "arvo_prod": {"gold_shadow"}}

# COMMAND ----------

import json
from pyspark.sql import functions as F

checks = []


def check(cid, ok, detalhe, severidade="BLOQUEIA"):
    checks.append({"check_id": cid, "ok": bool(ok), "detalhe": str(detalhe)[:500], "severidade": severidade})
    print(("OK  " if ok else "FALHA ") + cid, "·", detalhe)


check("C01_catalogo_do_alvo", CATALOG == {"dev": "arvo_dev", "stg": "arvo_stg", "prod": "arvo_prod"}.get(ALVO),
      f"alvo={ALVO} catalog={CATALOG}")

schemas = {r.databaseName for r in spark.sql(f"SHOW SCHEMAS IN {CATALOG}").collect()}
falt = (ESPERADOS | EXTRAS.get(CATALOG, set())) - schemas
check("C02_schemas_medalhao", not falt, f"faltando: {sorted(falt) or 'nenhum'}")

usuario = spark.sql("SELECT current_user() AS u").first().u
eh_humano = "@" in usuario
check("C03_execucao_por_service_principal", (ALVO == "dev") or not eh_humano,
      f"current_user={'<humano>' if eh_humano else usuario}")

if CATALOG != "arvo_dev":
    fn = spark.sql(f"SHOW USER FUNCTIONS IN {CATALOG}.ops LIKE 'mask_id_pessoa'").count()
    check("C04_mascara_lgpd_existe", fn == 1, f"{CATALOG}.ops.mask_id_pessoa")
    amostra = spark.sql(f"SELECT {CATALOG}.ops.mask_id_pessoa('B00001') AS m").first().m
    check("C05_mascara_pseudonimiza", amostra != "B00001" or "lgpd" in usuario,
          f"saida={amostra[:12]}…", severidade="ALERTA")

tags = {r.tag_name: r.tag_value for r in spark.sql(
    f"SELECT tag_name, tag_value FROM system.information_schema.catalog_tags WHERE catalog_name = '{CATALOG}'").collect()}
check("C06_tag_ambiente", tags.get("ambiente") == ALVO, f"tags={tags}", severidade="ALERTA")

sem = spark.catalog.tableExists(f"{CATALOG}.semantic.glossario")
check("C07_semantica_carregada", sem, "rode o job f2_semantica se falso", severidade="ALERTA")

# COMMAND ----------

try:
    ver = spark.conf.get("spark.databricks.clusterUsageTags.sparkVersion", "serverless")
except Exception:  # em serverless a conf pode não estar exposta
    ver = "serverless"
df = (spark.createDataFrame(checks)
      .withColumn("alvo", F.lit(ALVO)).withColumn("catalog", F.lit(CATALOG))
      .withColumn("runtime", F.lit(ver)).withColumn("executado_em", F.current_timestamp()))
df.write.mode("append").saveAsTable(f"{CATALOG}.ops.plataforma_checks")            # C08 implícito: escrita em ops

bloqueios = [c for c in checks if not c["ok"] and c["severidade"] == "BLOQUEIA"]
if bloqueios:
    raise Exception("G4 reprovado: " + json.dumps(bloqueios, ensure_ascii=False))
print("G4 aprovado para", ALVO)
