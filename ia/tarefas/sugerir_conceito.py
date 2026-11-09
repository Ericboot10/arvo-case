"""Tarefa de IA nº 2: sugerir o CONCEITO semântico de códigos TUSS novos (quarentena E03), com humano no circuito.

Prova que a camada ia/ é genérica: outra tarefa, outro schema, outra classe de dado (catalogo), o mesmo roteador
(política de dados, circuit breaker, cache, orçamento, telemetria) e o mesmo padrão de degradação graciosa:
  1. cadeia de LLMs (tier pequeno: tarefa simples, alto volume)
  2. se todos falharem, ou a resposta vier fora do domínio: fallback DETERMINÍSTICO por similaridade de descrição
  3. SEMPRE status PENDENTE_ESPECIALISTA: nada é escrito no mapa semântico sem aprovação (F2 / Gate G2)
Quando LLM e determinístico discordam, a sugestão sobe na fila de revisão.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

import yaml

from ia import esquemas
from ia.ports import LLMParams, LLMRequest

RAIZ = Path(__file__).resolve().parents[2]
SCHEMA_ID, SCHEMA_VERSAO = "sugestao_conceito", "1.0.0"
CONFIANCAS = ["ALTA", "MEDIA", "BAIXA"]


def _conceitos() -> list[dict]:
    return yaml.safe_load((RAIZ / "semantic" / "conceitos.yaml").read_text("utf-8"))["conceitos"]


def _mapa() -> list[dict]:
    return yaml.safe_load((RAIZ / "semantic" / "map_tuss_conceito.yaml").read_text("utf-8"))["codigos"]


def schema() -> dict:
    ids = [c["id"] for c in _conceitos()]
    item = {"type": "object", "additionalProperties": False,
            "required": ["cod_tuss", "conceito", "confianca", "justificativa", "termos_chave"],
            "properties": {"cod_tuss": {"type": "string"},
                           "conceito": {"type": "string", "enum": ids},
                           "confianca": {"type": "string", "enum": CONFIANCAS},
                           "justificativa": {"type": "string"},
                           "termos_chave": {"type": "array", "items": {"type": "string"}}}}
    return {"type": "object", "additionalProperties": False, "required": ["sugestoes"],
            "properties": {"sugestoes": {"type": "array", "items": item}}}


SCHEMA = schema()
esquemas.registrar(SCHEMA_ID, SCHEMA_VERSAO, lambda d: esquemas.validar_estrutura(d, SCHEMA))


def _norm(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def fallback_deterministico(cod: str, desc: str) -> dict:
    """Similaridade da descrição contra as descrições já aprovadas (canônica e observadas)."""
    melhor = (0.0, None, None)
    for m in _mapa():
        for ref in [m["descricao_canonica"], *m["descricoes_observadas"]]:
            r = difflib.SequenceMatcher(None, _norm(desc), _norm(ref)).ratio()
            if r > melhor[0]:
                melhor = (r, m, ref)
    r, m, ref = melhor
    conf = "ALTA" if r >= 0.85 else "MEDIA" if r >= 0.6 else "BAIXA"
    return {"cod_tuss": cod, "conceito": m["conceito"], "confianca": conf,
            "justificativa": f"similaridade {r:.2f} com '{ref}' ({m['codigo']} → {m['conceito']})",
            "termos_chave": sorted(set(_norm(desc).split()) & set(_norm(ref).split())), "origem": "deterministico"}


def _prompt() -> dict:
    txt = (RAIZ / "ia" / "prompts" / "sugerir_conceito_v1.md").read_text("utf-8")
    meta = dict(re.findall(r"^(prompt_id|versao):\s*(\S+)", txt, flags=re.M))
    system = txt.split("## system", 1)[1].split("## user", 1)[0].strip()
    user = txt.split("## user", 1)[1].strip()
    conceitos = "\n".join(f"- {c['id']}: {c['definicao']}" for c in _conceitos())
    exemplos = "\n".join(f"- {m['codigo']} | {m['descricao_canonica']} → {m['conceito']}" for m in _mapa())
    return {"id": meta["prompt_id"], "versao": meta["versao"],
            "system": system.replace("{{conceitos}}", conceitos).replace("{{exemplos}}", exemplos), "user": user}


def montar_requisicao(itens: list[tuple[str, str]], run_id: str) -> LLMRequest:
    p = _prompt()
    corpo = json.dumps([{"cod_tuss": c, "descricao": d} for c, d in itens], ensure_ascii=False)
    return LLMRequest(task_id="sugerir_conceito", system=p["system"], user=p["user"].replace("{{itens}}", corpo),
                      schema_id=SCHEMA_ID, schema_version=SCHEMA_VERSAO, schema=SCHEMA, prompt_id=p["id"],
                      prompt_version=p["versao"], params=LLMParams(max_output_tokens=4000, reasoning_effort="low"),
                      run_id=run_id, documento_sha256="catalogo", classe_dados="catalogo")


def sugerir(itens: list[tuple[str, str]], roteador=None, cadeia: list | None = None, run_id: str = "local") -> list[dict]:
    por_cod: dict[str, dict] = {}
    if roteador and cadeia:
        res, usado = roteador.gerar(montar_requisicao(itens, run_id), cadeia)
        if res and res.ok:
            pedidos = {c for c, _ in itens}
            for s in res.data["sugestoes"]:
                if s["cod_tuss"] in pedidos:          # resposta para código não pedido é descartada
                    por_cod[s["cod_tuss"]] = {**s, "origem": f"llm:{usado.nome}"}
    saida = []
    for cod, desc in itens:
        det = fallback_deterministico(cod, desc)
        sug = por_cod.get(cod, det)
        saida.append({**sug, "descricao": desc, "status": "PENDENTE_ESPECIALISTA",
                      "segunda_opiniao": None if sug is det else {"conceito": det["conceito"], "confianca": det["confianca"]},
                      "concorda_com_deterministico": sug["conceito"] == det["conceito"],
                      "prioridade_revisao": "ALTA" if (sug["conceito"] != det["conceito"] or sug["confianca"] == "BAIXA")
                      else "NORMAL"})
    return saida


def itens_da_quarentena(linhas_quarentena: list[dict]) -> list[tuple[str, str]]:
    """De quarantine.item_conta_rejeitado: códigos com 8 dígitos reprovados SÓ por falta de conceito (E03)."""
    vistos = {}
    for l in linhas_quarentena:
        motivos = set(l["motivos"])
        orig = json.loads(l["linha_original"])
        if "E03" in motivos and "E02" not in motivos:
            vistos.setdefault(orig["cod_tuss"], orig.get("desc_item_origem") or "")
    return sorted(vistos.items())
