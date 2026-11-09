"""Juiz (LLM-as-judge) para campos sem consenso verificado.

Regras do comitê:
- o juiz é de família DIFERENTE dos extratores (evita que um modelo "confirme a si mesmo");
- o juiz NÃO aprova nada: só prioriza e comenta a revisão humana;
- a citação do juiz também passa pela verificação literal;
- saída estruturada com enum fechado, o que é programático e auditável.
"""
from __future__ import annotations

import json

from .extratores.llm import carregar_prompt
from .grounding import Corpus
from ia.ports import LLMParams, LLMRequest

PROMPT = carregar_prompt("juiz_extracao_v1.md")   # versionado e travado em ia/prompts.lock.json

JUIZ_SCHEMA_ID, JUIZ_SCHEMA_VERSAO = "veredito_campo", "1.0.0"
VEREDITOS = ["CONFIRMA_D", "CONFIRMA_A", "CONFIRMA_B", "NENHUM_CORRETO", "INCONCLUSIVO"]
JUIZ_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["vereditos"],
    "properties": {"vereditos": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["campo", "veredito", "justificativa", "quote"],
        "properties": {
            "campo": {"type": "string"},
            "veredito": {"type": "string", "enum": VEREDITOS},
            "justificativa": {"type": "string"},
            "quote": {"type": "string", "description": "Trecho literal do documento que sustenta o veredito."},
        }}}},
}



def montar(campos_pendentes: list[dict], documento: str, run_id: str, doc_sha: str) -> LLMRequest:
    itens = [{"campo": l["campo"], "candidatos": {f: v["valor"] for f, v in l["fontes"].items()}}
             for l in campos_pendentes]
    return LLMRequest(
        task_id="juiz_extracao", system=PROMPT["system"].replace("{{documento}}", documento),
        user=PROMPT["user"].replace("{{campos}}", json.dumps(itens, ensure_ascii=False, default=list)),
        schema_id=JUIZ_SCHEMA_ID, schema_version=JUIZ_SCHEMA_VERSAO, schema=JUIZ_SCHEMA,
        prompt_id=PROMPT["id"], prompt_version=PROMPT["versao"],
        params=LLMParams(max_output_tokens=8000, reasoning_effort="high"), run_id=run_id, documento_sha256=doc_sha,
    )


def anotar(reconciliacao: dict, resposta: dict | None, corpus: Corpus) -> None:
    """Anexa o veredito (e se a citação do juiz se verificou) a cada campo pendente."""
    if not resposta:
        return
    por_campo = {v["campo"]: v for v in resposta.get("vereditos", []) if v.get("veredito") in VEREDITOS}
    for l in reconciliacao["campos"]:
        if l["campo"] in por_campo:
            v = por_campo[l["campo"]]
            l["juiz"] = {**v, "quote_ok": corpus.contem(v["quote"])}


from ia import esquemas  # noqa: E402

esquemas.registrar(JUIZ_SCHEMA_ID, JUIZ_SCHEMA_VERSAO, lambda d: esquemas.validar_estrutura(d, JUIZ_SCHEMA))
