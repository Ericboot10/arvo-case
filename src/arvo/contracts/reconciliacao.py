"""Reconciliação campo a campo entre extratores independentes (D determinístico, A e B via LLM).

Status por campo:
- CONSENSO_VERIFICADO: todos os extratores trazem o campo, os valores coincidem e TODA citação foi verificada
  (quote ⊂ documento e valor ⊂ quote). É o único status que dispensa decisão humana campo a campo.
- CONSENSO_SEM_EVIDENCIA: os valores coincidem, mas alguma citação não se verificou. Vai para revisão.
- DIVERGENTE: valores diferentes. Vai para o juiz e para revisão.
- INCOMPLETO: algum extrator não trouxe o campo. Vai para revisão.

Independência: se A e B forem da mesma família de modelo (ex.: um fallback caiu no mesmo provedor),
o consenso vale menos, e a reconciliação registra `independencia_reduzida`.
"""
from __future__ import annotations

from arvo.contracts.grounding import Corpus, normalizar, verificar

CONSENSO_VERIFICADO = "CONSENSO_VERIFICADO"
CONSENSO_SEM_EVIDENCIA = "CONSENSO_SEM_EVIDENCIA"
DIVERGENTE = "DIVERGENTE"
INCOMPLETO = "INCOMPLETO"


def achatar(dados: dict) -> dict[str, tuple]:
    """Campo canônico -> (valor comparável, quote). A mesma chave usada em grounding.verificar."""
    out: dict[str, tuple] = {}
    c = dados["contrato"]
    out["contrato.id_contrato"] = (c["id_contrato"].strip().upper(), c["quote_id"])
    out["contrato.operadora"] = (normalizar(c["operadora"]), c["quote_partes"])
    out["contrato.prestador"] = (normalizar(c["prestador"]), c["quote_partes"])
    out["contrato.modelo_remuneracao"] = (c["modelo_remuneracao"], c["quote_modelo"])
    out["contrato.vigencia_inicio"] = (c["vigencia_inicio"], c["quote_vigencia"])
    out["contrato.vigencia_meses"] = (c["vigencia_meses"], c["quote_vigencia"])
    for it in dados["anexo_i"]:
        out[f"anexo_i.{it['codigo']}.valor_teto"] = (round(float(it["valor_teto"]), 2), it["quote"])
    for p in dados["anexo_ii"]:
        k = p["codigo_procedimento"]
        out[f"anexo_ii.{k}.taxa_sala_codigo"] = (p["taxa_sala_codigo"], p["quote"])
        out[f"anexo_ii.{k}.materiais_rotina"] = (tuple(sorted(p["materiais_rotina"])), p["quote"])
    for t in dados["taxas_condicionadas"]:
        out[f"taxa_condicionada.{t['codigo']}.carater_permitido"] = (tuple(sorted(t["carater_permitido"])), t["quote"])
    for r in dados["regras"]:
        out[f"regra.{r['clausula']}.tipo"] = (r["tipo"], r["quote"])
        out[f"regra.{r['clausula']}.tipo_glosa"] = (r["tipo_glosa"], r["quote"])
    return out


def reconciliar(extracoes: dict[str, dict], familias: dict[str, str], corpus: Corpus) -> dict:
    """extracoes: {"D": dados, "A": dados, "B": dados} (somente as que produziram JSON válido)."""
    planos = {k: achatar(v) for k, v in extracoes.items()}
    evid = {k: verificar(v, corpus) for k, v in extracoes.items()}
    campos = sorted(set().union(*[set(p) for p in planos.values()])) if planos else []
    linhas = []
    for campo in campos:
        por_fonte = {}
        for fonte, plano in planos.items():
            if campo in plano:
                valor, quote = plano[campo]
                e = evid[fonte].get(campo, {"quote_ok": False, "valor_ok": False})
                por_fonte[fonte] = {"valor": valor, "quote": quote, **e}
        valores = {repr(v["valor"]) for v in por_fonte.values()}
        if len(por_fonte) < len(planos):
            status = INCOMPLETO
        elif len(valores) > 1:
            status = DIVERGENTE
        elif all(v["quote_ok"] and v["valor_ok"] for v in por_fonte.values()):
            status = CONSENSO_VERIFICADO
        else:
            status = CONSENSO_SEM_EVIDENCIA
        linhas.append({"campo": campo, "status": status, "fontes": por_fonte,
                       "valor_proposto": next(iter(por_fonte.values()))["valor"] if status == CONSENSO_VERIFICADO else None})

    llm = [f for f in extracoes if f != "D"]
    fams = [familias.get(f) for f in llm]
    resumo = {s: sum(1 for l in linhas if l["status"] == s)
              for s in (CONSENSO_VERIFICADO, CONSENSO_SEM_EVIDENCIA, DIVERGENTE, INCOMPLETO)}
    return {
        "fontes": list(extracoes), "familias": {f: familias.get(f) for f in extracoes},
        "independencia_reduzida": len(llm) >= 2 and len(set(fams)) < len(fams),
        "n_campos": len(linhas), "resumo": resumo,
        "taxa_consenso_verificado": round(resumo[CONSENSO_VERIFICADO] / len(linhas), 4) if linhas else 0.0,
        "campos": linhas,
    }
