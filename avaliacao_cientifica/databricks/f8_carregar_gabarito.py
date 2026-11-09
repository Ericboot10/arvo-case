# Databricks notebook source
# MAGIC %md
# MAGIC # F8 · Gabarito do case → `bronze.gabarito_raw`
# MAGIC Lê `gabarito-auditoria.csv` (fornecido no case, sem alteração) de `/Volumes/<catalog>/bronze/landing/gabarito/`.
# MAGIC É a rodada 0 de auditoria: alimenta a precisão e o recall (`ops.v_precisao_recall`) e `gold.fato_auditoria_amostral`.
# MAGIC Sobrescreve a tabela a cada execução: o gabarito é uma referência, não um fluxo.

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
CATALOG = dbutils.widgets.get("catalog")
assert CATALOG in {"arvo_dev", "arvo_stg", "arvo_prod"}

# COMMAND ----------

from pyspark.sql import functions as F, types as T

PASTA = f"/Volumes/{CATALOG}/bronze/landing/gabarito/"
COLUNAS = ["id_item", "id_conta", "cod_tuss", "indevido"]
# Esquema explícito e posicional: o cabeçalho do arquivo tem BOM no primeiro nome de coluna.
esquema = T.StructType([T.StructField(c, T.StringType()) for c in COLUNAS])
gab = (spark.read.option("header", True).option("encoding", "UTF-8").schema(esquema).csv(PASTA)
       .withColumn("_arquivo", F.element_at(F.split(F.col("_metadata.file_path"), "/"), -1))
       .withColumn("_ingest_ts", F.current_timestamp()))

n, n_ids = gab.count(), gab.select("id_item").distinct().count()
assert n > 0, f"nenhum gabarito em {PASTA}"
assert n == n_ids, f"id_item repetido no gabarito ({n} linhas, {n_ids} ids)"
assert gab.where("indevido NOT IN ('Sim', 'Não', 'Nao')").count() == 0, "rótulo fora de Sim/Não"

alvo = f"{CATALOG}.bronze.gabarito_raw"
gab.write.mode("overwrite").option("overwriteSchema", True).saveAsTable(alvo)
spark.sql(f"COMMENT ON TABLE {alvo} IS 'Gabarito de auditoria fornecido no case Arvo (dado do case, sem alteração). "
          "Rodada 0 de auditoria: base da precisão e do recall.'")
spark.sql(f"ALTER TABLE {alvo} SET TAGS ('origem_dado' = 'case_arvo')")
print(f"{n} itens rotulados gravados em {alvo}")
