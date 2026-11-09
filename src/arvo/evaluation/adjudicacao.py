"""Adjudicação CEGA das divergências por dois revisores (Auditor Médico e Especialista em Contas Médicas).

Desenho:
- casos = todas as divergências + igual número de CONTROLES (concordâncias sorteadas), embaralhados com semente;
  assim o revisor não sabe quais itens são divergentes;
- a planilha NÃO mostra nem a decisão do motor nem o rótulo do gabarito; mostra só o item, o contexto da conta
  e as cláusulas;
- a chave (caso → item, tipo) fica separada, com o Cientista de Dados;
- concordância entre revisores medida por Cohen's κ. Discordância vai para um terceiro revisor (Jurídico).
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from arvo.evaluation.metricas import kappa

CLAUSULAS = ("2.2: cobrança acima do valor do Anexo I glosa o excedente · 3.2/3.3: taxa de sala e materiais de rotina "
             "(70520020, 70402600) inclusos no pacote não podem ser cobrados à parte · 4.1/4.2: taxa de urgência "
             "(99999001) só em caráter urgência/emergência")
DECISOES = {"INDEVIDO", "DEVIDO", "INCONCLUSIVO"}


def gerar_pacote(base: pd.DataFrame, pasta: Path, semente: int = 2026) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    rot = base[base.rotulado]
    div = rot[rot.pred != rot.real]
    conc = rot[rot.pred == rot.real].sample(len(div), random_state=semente)
    casos = pd.concat([div.assign(tipo=np.where(div.pred, "FP", "FN")), conc.assign(tipo="CONTROLE")])
    casos = casos.sample(frac=1, random_state=semente).reset_index(drop=True)
    casos["id_caso"] = [f"C{i + 1:03d}" for i in range(len(casos))]
    brl = lambda v: "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
    contexto = base.groupby("id_conta").apply(
        lambda g: " · ".join(f"{r.cod_tuss}({r.conceito}) {brl(r.vl_unitario)}" for r in g.itertuples()),
        include_groups=False)
    linhas = [{"id_caso": c.id_caso, "id_item": c.id_item, "id_conta": c.id_conta, "cod_tuss": c.cod_tuss,
               "conceito": c.conceito, "regime": c.regime, "carater": c.carater_canonico,
               "vl_unitario": f"{c.vl_unitario:.2f}", "teto_anexo_i": f"{c.vl_teto_unitario:.2f}",
               "itens_da_conta": contexto[c.id_conta], "clausulas_de_referencia": CLAUSULAS,
               "revisor": "", "decisao": "", "clausula_fundamento": "", "comentario": ""} for c in casos.itertuples()]
    for rev in ("A", "B"):
        with open(pasta / f"planilha_cega_revisor_{rev}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0]))
            w.writeheader()
            w.writerows(linhas)
    chave = casos[["id_caso", "id_item", "tipo", "pred", "real"]].rename(
        columns={"pred": "motor_glosou", "real": "gabarito_indevido"})
    chave.to_csv(pasta / "CHAVE_NAO_COMPARTILHAR.csv", index=False, encoding="utf-8-sig")
    return {"casos": len(casos), "divergencias": len(div), "controles": len(conc)}


def adjudicar(planilha_a: pd.DataFrame, planilha_b: pd.DataFrame, chave: pd.DataFrame) -> dict:
    a = planilha_a.set_index("id_caso").decisao.str.strip().str.upper()
    b = planilha_b.set_index("id_caso").decisao.str.strip().str.upper()
    faltando = sorted(set(chave.id_caso) - set(a[a.isin(DECISOES)].index) | set(chave.id_caso) - set(b[b.isin(DECISOES)].index))
    if faltando:
        raise ValueError(f"casos sem decisão válida: {faltando[:10]}")
    k = kappa(list(a[chave.id_caso]), list(b[chave.id_caso]))
    res = chave.set_index("id_caso").assign(revisor_a=a, revisor_b=b)
    res["consenso"] = np.where(res.revisor_a == res.revisor_b, res.revisor_a, "TERCEIRO_REVISOR")
    res["rotulo_adjudicado"] = res.consenso.map({"INDEVIDO": True, "DEVIDO": False})
    decididos = res[res.rotulo_adjudicado.notna()]
    concordancia_gabarito = float((decididos.rotulo_adjudicado == decididos.gabarito_indevido).mean())
    concordancia_motor = float((decididos.rotulo_adjudicado == decididos.motor_glosou).mean())
    return {"kappa": k, "pendentes_terceiro": int((res.consenso == "TERCEIRO_REVISOR").sum()),
            "concordancia_adjudicado_x_gabarito": concordancia_gabarito,
            "concordancia_adjudicado_x_motor": concordancia_motor, "resultado": res.reset_index()}


def aplicar_rotulos(base: pd.DataFrame, adjudicado: pd.DataFrame) -> pd.DataFrame:
    """Base com o rótulo adjudicado no lugar do gabarito (onde houver adjudicação conclusiva)."""
    m = adjudicado.dropna(subset=["rotulo_adjudicado"]).set_index("id_item").rotulo_adjudicado.astype(bool)
    b = base.copy()
    b.loc[b.id_item.isin(m.index), "real"] = b.loc[b.id_item.isin(m.index), "id_item"].map(m)
    return b
