"""F10 · Backtest: o motor contra as decisões REAIS da auditoria da Parthenon nos últimos 3 a 6 meses.

Contrato do histórico (fonte.historico_auditoria, a pedir à Parthenon):
  id_item, competencia, auditoria_glosou (bool), vl_glosado_auditoria (decimal), motivo_auditoria (texto)
Diferente do gabarito do case, o histórico é o universo auditado, não uma amostra: as métricas valem para o período,
com IC por conta (cluster bootstrap, F8). Concordância baixa NÃO prova que o motor erra: a auditoria também retém
glosa devida (Parte 2). Por isso cada divergência entra na adjudicação cega (F8) antes de virar conclusão.
"""
from __future__ import annotations

import pandas as pd

from arvo.evaluation import metricas as m

COLUNAS = ["id_item", "competencia", "auditoria_glosou", "vl_glosado_auditoria"]


def validar_historico(h: pd.DataFrame) -> None:
    faltam = set(COLUNAS) - set(h.columns)
    if faltam:
        raise ValueError(f"histórico sem as colunas {sorted(faltam)}")
    if h.id_item.duplicated().any():
        raise ValueError("histórico com id_item duplicado")


def avaliar(motor: pd.DataFrame, historico: pd.DataFrame) -> dict:
    """motor: id_item, id_conta, pred (bool), regra_principal, vl_glosado. Só itens presentes no histórico entram."""
    validar_historico(historico)
    b = motor.merge(historico, on="id_item", how="inner")
    b = b.assign(real=b.auditoria_glosou.astype(bool), vl_glosado=b.vl_glosado.fillna(0).astype(float))
    r = m.precisao_recall(m.matriz(b))
    divergencias = b[b.pred != b.real]
    return {
        "itens": int(len(b)), "competencias": sorted(map(str, b.competencia.unique())),
        "matriz": {k: r[k] for k in ("TP", "FP", "FN", "TN")},
        "concordancia": float((b.pred == b.real).mean()),
        "precisao_vs_auditoria": r["precisao"], "recall_vs_auditoria": r["recall"],
        "por_regra": m.por_regra(b[b.pred]),
        "vl_motor": round(float(b.loc[b.pred, "vl_glosado"].sum()), 2),
        "vl_auditoria": round(float(b.loc[b.real, "vl_glosado_auditoria"].astype(float).sum()), 2),
        "divergencias_para_adjudicacao": int(len(divergencias)),
    }
