# Databricks notebook source
# MAGIC %md
# MAGIC # dev · Sinistro sintético rotulado (ADR-002)
# MAGIC Grava `sinistro_sintetico.csv`, `gabarito_sintetico.csv` e `manifesto.json` no Volume de landing de **dev**.
# MAGIC Recusa rodar fora de `arvo_dev`: dado sintético não deve se misturar a stg/prod.

# COMMAND ----------

# MAGIC %pip install pyyaml==6.0.2

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
dbutils.widgets.text("semente", "42")
dbutils.widgets.text("contas", "400")
CATALOG = dbutils.widgets.get("catalog")
if CATALOG != "arvo_dev":
    raise Exception(f"dados sintéticos só em arvo_dev (recebido: {CATALOG})")

# COMMAND ----------

import json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(os.getcwd()).parents[3] / "src"))  # src/ do bundle (pacote arvo)
from arvo.platform.sinteticos.gerar_sinistro_sintetico import Gerador  # noqa: E402

g = Gerador(int(dbutils.widgets.get("semente")), int(dbutils.widgets.get("contas")), 2025, 6)
g.gerar()
manifesto = g.gravar(Path(f"/Volumes/{CATALOG}/bronze/landing/sintetico/semente={g.semente}"))
print(json.dumps(manifesto, ensure_ascii=False, indent=2))

# COMMAND ----------

# O pipeline da F5 lê com Auto Loader a pasta landing/sinistro/: entrega lá uma cópia do sinistro sintético.
import shutil  # noqa: E402

origem = Path(f"/Volumes/{CATALOG}/bronze/landing/sintetico/semente={g.semente}/sinistro_sintetico.csv")
destino = Path(f"/Volumes/{CATALOG}/bronze/landing/sinistro/sinistro_sintetico_semente={g.semente}.csv")
destino.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(origem, destino)
print("entregue ao pipeline:", destino)
