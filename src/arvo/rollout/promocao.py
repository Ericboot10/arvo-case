"""F10 · Promoção (humana) e rebaixamento (automático) de regras entre estágios.

- avaliar_promocao: confere TODOS os critérios de estagios.yaml para o próximo estágio e diz o que falta.
  Nunca muda o estado: promover exige os aprovadores listados, registrados por eles em estado_regras.yaml.
- rebaixar: lê as linhas do painel de sanidade (ops.v_sanidade_status) e rebaixa a regra cujo recorte está em ALERTA.
  É automático e só desce; o histórico registra o indicador que disparou.
"""
from __future__ import annotations

import copy
from datetime import date

import pandas as pd

from arvo.evaluation.metricas import wilson
from arvo.rollout.envio import carregar

PROXIMO = {"SHADOW": "CANARIO", "CANARIO": "AUTOMATICO"}


def evidencias_auditoria(auditoria: pd.DataFrame) -> dict[str, dict]:
    """Da amostra auditada (gold.fato_auditoria_amostral, estrato GLOSADO): n, confirmados, precisão e limite do IC."""
    gl = auditoria[auditoria.estrato == "GLOSADO"]
    out = {}
    for regra, g in gl.groupby("regra_principal"):
        n, k = int(len(g)), int(g.auditor_indevido.sum())
        out[regra] = {"n_auditado": n, "confirmados": k, "precisao": k / n if n else None,
                      "precisao_inf": wilson(k, n)[0] if n else None}
    return out


def _fmt(v) -> str:
    if v is None:
        return "sem dado"
    if isinstance(v, float):
        return f"{v:.3f}".replace(".", ",")
    return str(v)


def _falta(r: dict) -> str:
    if r["id"] == "amostra" and r["limite"] is None:
        return "amostra: regra sem apontamentos no período (sem plano amostral)"
    alvo = "verdadeiro" if r["limite"] is None else _fmt(r["limite"])
    return f"{r['id']}: {_fmt(r['valor'])} (precisa {alvo})"


def avaliar_promocao(regra: str, estagio: str, evid: dict, n_plano: int | None = None, cfg: dict | None = None) -> dict:
    cfg = cfg or carregar()
    para = PROXIMO.get(estagio)
    if not para:
        return {"regra": regra, "de": estagio, "para": None, "apta": False, "criterios": [],
                "faltam": [f"estágio {estagio} não tem promoção automática prevista"]}
    regras = cfg["promocao"][f"{estagio}->{para}"]
    res = []
    for c in regras["criterios"]:
        if c["tipo"] == "n_auditado_vs_plano":
            v, lim = evid.get("n_auditado"), n_plano
            ok = v is not None and lim is not None and v >= lim
        else:
            v, lim = evid.get(c["campo"]), c.get("limite")
            ok = (v is not None) and ((c["tipo"] == "min" and v >= lim) or (c["tipo"] == "max" and v <= lim)
                                      or (c["tipo"] == "verdadeiro" and v is True))
        res.append({"id": c["id"], "descricao": c["descricao"], "valor": v, "limite": lim, "ok": bool(ok)})
    faltam = [_falta(r) for r in res if not r["ok"]]
    return {"regra": regra, "de": estagio, "para": para, "apta": not faltam, "criterios": res, "faltam": faltam,
            "aprovadores": regras["aprovadores"]}


def rebaixar(estado: dict, linhas_sanidade: list[dict], hoje: str | None = None, cfg: dict | None = None) -> tuple[dict, list[dict]]:
    """Aplica o rebaixamento automático. Devolve (novo estado, mudanças). Só desce de estágio, nunca sobe."""
    cfg = cfg or carregar()
    ordem = {k: v["ordem"] for k, v in cfg["estagios"].items()}
    gatilhos = {g["indicador"]: g for g in cfg["rebaixamento"]}
    novo, mudancas = copy.deepcopy(estado), []
    hoje = hoje or date.today().isoformat()
    for ln in linhas_sanidade:
        g = gatilhos.get(ln["id_indicador"])
        if not g or ln["status"] != "ALERTA" or not str(ln.get("recorte", "")).startswith("regra_principal="):
            continue
        regra = ln["recorte"].split("=", 1)[1]
        atual = novo["regras"].get(regra, {}).get("estagio")
        if atual is None or ordem[g["para"]] >= ordem[atual]:
            continue
        novo["regras"][regra] = {**novo["regras"][regra], "estagio": g["para"], "desde": hoje}
        m = {"data": hoje, "mudanca": f"{regra}: {atual} → {g['para']}", "motivo": f"{g['indicador']} em ALERTA: {g['motivo']}",
             "aprovado_por": [f"automatico:{g['indicador']}"]}
        novo["historico"].append(m)
        mudancas.append(m)
    return novo, mudancas
