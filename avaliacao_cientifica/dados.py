"""Base de avaliação: resultado do motor (F6) sobre o sinistro real + gabarito. Um único lugar monta o insumo."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SINISTRO = RAIZ / "arvo.case" / "sinistro-hospital-saorafael.csv"
GABARITO = RAIZ / "arvo.case" / "gabarito-auditoria.csv"


def base_avaliacao(spark=None, out: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Retorna (base, out). base: 1 linha por item do sinistro, com a decisão do motor e o rótulo (quando houver)."""
    from medalhao.local import executar, spark_local

    if out is None:
        out = executar(spark or spark_local(), str(SINISTRO), run_id="f8-avaliacao")
    cols = ["id_item", "id_conta", "cod_tuss", "conceito", "regime", "carater_canonico", "vl_cobrado", "vl_unitario",
            "vl_teto_unitario", "conta_tem_pacote", "glosado", "regra_principal", "clausula_principal", "vl_glosado"]
    itens = pd.DataFrame([r.asDict() for r in out["gold.fato_item_auditado"].select(*cols).collect()])
    ap = pd.DataFrame([r.asDict() for r in out["gold.fato_apontamento"]
                      .select("id_item", "status_envio", "motivo_revisao", "justificativa").collect()])
    base = itens.merge(ap, on="id_item", how="left")
    for c in ("vl_cobrado", "vl_unitario", "vl_teto_unitario", "vl_glosado"):
        base[c] = base[c].astype(float)
    gab = pd.read_csv(GABARITO, dtype=str, encoding="utf-8-sig")[["id_item", "indevido"]]
    base = base.merge(gab, on="id_item", how="left")
    base["rotulado"] = base.indevido.notna()
    base["pred"] = base.glosado.astype(bool)
    base["real"] = base.indevido.eq("Sim")
    return base, out
