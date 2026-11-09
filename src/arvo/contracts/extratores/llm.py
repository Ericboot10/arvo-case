"""Extrator via LLM (A ou B). Usa só o Port, então não sabe qual provedor está atrás."""
from __future__ import annotations

import re
from pathlib import Path

from arvo.ai.ports import LLMParams, LLMRequest, ParsedDoc
from arvo.contracts.schema import SCHEMA, SCHEMA_ID, SCHEMA_VERSAO

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def carregar_prompt(arquivo: str) -> dict:
    txt = (PROMPTS / arquivo).read_text("utf-8")
    meta = dict(re.findall(r"^(prompt_id|versao):\s*(\S+)", txt, flags=re.M))
    system = txt.split("## system", 1)[1].split("## user", 1)[0].strip()
    user = txt.split("## user", 1)[1].strip()
    return {"id": meta["prompt_id"], "versao": meta["versao"], "system": system, "user": user}


def documento_para_prompt(doc: ParsedDoc) -> str:
    """Texto corrido + tabelas em ordem de leitura. É o mesmo insumo para todos os provedores (comparabilidade)."""
    partes = [doc.texto_limpo, "\n\n[TABELAS EXTRAÍDAS]"]
    for t in doc.tabelas:
        partes.append(" | ".join(" ".join(c.replace("\x00", "").split()) for c in t["cabecalho"]))
        for r in t["linhas"]:
            partes.append(" | ".join(" ".join(c.replace("\x00", "").split()) for c in r))
    return "\n".join(partes).replace("\x00", "")


def montar_requisicao(doc: ParsedDoc, prompt: dict, params: LLMParams, run_id: str, task_id: str) -> LLMRequest:
    return LLMRequest(
        task_id=task_id,
        system=prompt["system"].replace("{{documento}}", documento_para_prompt(doc)),  # prefixo estável (cacheável)
        user=prompt["user"],
        schema_id=SCHEMA_ID, schema_version=SCHEMA_VERSAO, schema=SCHEMA,
        prompt_id=prompt["id"], prompt_version=prompt["versao"],
        params=params, run_id=run_id, documento_sha256=doc.sha256,
    )
