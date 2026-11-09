"""Testes da F12: os entregáveis batem entre si (CSV, resumo, relatório da F8 e respostas). Sem Spark."""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

AQUI = Path(__file__).resolve().parents[2] / "deliverables"
RAIZ = AQUI.parent


def _linhas():
    with (AQUI / "apontamentos.csv").open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_csv_tem_o_minimo_pedido_pelo_case():
    ln = _linhas()
    assert len(ln) == 369 and len({r["id_item"] for r in ln}) == 369          # no máximo 1 glosa por item
    for r in ln:
        assert r["id_item"] and r["clausula_principal"] and Decimal(r["vl_glosado"]) > 0
        assert "Cláusula" in r["justificativa"] and Decimal(r["vl_glosado"]) <= Decimal(r["vl_cobrado"])


def test_total_do_csv_bate_com_resumo_e_respostas():
    total = sum(Decimal(r["vl_glosado"]) for r in _linhas())
    resumo = json.loads((AQUI / "resumo_glosa.json").read_text("utf-8"))
    assert total == Decimal("121948.93") and Decimal(str(resumo["vl_glosado_total"])) == total
    md = (AQUI / "RESPOSTAS_CASE.md").read_text("utf-8")
    assert "R$ 121.948,93 em 369 itens" in md
    for regra, v in resumo["por_regra"].items():
        assert f"{v['vl_glosado']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") in md, regra


def test_metricas_das_respostas_batem_com_a_f8():
    r = json.loads((RAIZ / "src" / "arvo" / "evaluation" / "resultados.json").read_text("utf-8"))["amostra"]
    md = (AQUI / "RESPOSTAS_CASE.md").read_text("utf-8")
    assert (r["TP"], r["FP"], r["FN"]) == (135, 8, 15)
    assert f"{100 * r['precisao']:.1f}%".replace(".", ",") in md and f"{100 * r['recall']:.1f}%".replace(".", ",") in md


def test_respostas_cobrem_as_oito_perguntas():
    md = (AQUI / "RESPOSTAS_CASE.md").read_text("utf-8")
    for n in range(1, 9):
        assert f"\n## {n}. " in md, n
