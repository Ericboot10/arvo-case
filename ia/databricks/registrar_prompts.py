# Databricks notebook source
# MAGIC %md
# MAGIC # F7 · Publicar prompts travados no MLflow Prompt Registry (Unity Catalog)
# MAGIC Publica cada `prompt_id@versao` de `ia/prompts.lock.json` como prompt em `<catalog>.ops.<prompt_id>`,
# MAGIC com tags (versão semântica, sha256, arquivo). O alias `production` só é movido em prod.
# MAGIC API conforme a doc (Prompt Registry, Beta): `mlflow.genai.register_prompt`, `load_prompt`, `set_prompt_alias`.
# MAGIC **Validar no workspace:** assinatura exata de `register_prompt` na versão do MLflow instalada.

# COMMAND ----------

# MAGIC %pip install "mlflow>=3" pyyaml==6.0.2

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
CATALOG = dbutils.widgets.get("catalog")

import json, os, sys
from pathlib import Path
import mlflow

RAIZ = Path(os.getcwd()).parents[1]
sys.path.insert(0, str(RAIZ))
from ia import prompts  # noqa: E402

problemas = prompts.verificar()
assert not problemas, f"prompts não travados ou alterados sem versão: {problemas}"
lock = json.loads((RAIZ / "ia" / "prompts.lock.json").read_text())

for chave, info in lock.items():
    prompt_id, versao = chave.split("@")
    texto = (RAIZ / info["arquivo"]).read_text("utf-8")
    nome = f"{CATALOG}.ops.{prompt_id}"
    p = mlflow.genai.register_prompt(name=nome, template=texto, commit_message=f"{chave} sha256={info['sha256'][:12]}",
                                     tags={"versao_semantica": versao, "sha256": info["sha256"], "arquivo": info["arquivo"]})
    print("registrado", nome, "→ versão MLflow", p.version)
    if CATALOG == "arvo_prod":
        mlflow.genai.set_prompt_alias(name=nome, alias="production", version=p.version)
