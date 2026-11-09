"""Testes da F11: os números do memo e do deck saem da planilha. Rodar: pytest parte2/tests -v"""
from __future__ import annotations

import pytest

from parte2 import analise_funil as af


@pytest.fixture(scope="module")
def r():
    return af.resumo()


def test_funil_fecha_com_a_planilha(r):
    f = r["funil"]
    assert f["identificado"] == 1_936_700 and f["efetivado"] == pytest.approx(335_769.94, abs=0.01)
    perdas = f["desligadas"] + f["retido_operadora"] + f["perda_registro"] + f["perda_recurso"]
    assert f["identificado"] - perdas == pytest.approx(f["efetivado"])
    assert (round(f["desligadas"]), round(f["retido_operadora"]), round(f["perda_registro"]), round(f["perda_recurso"])) \
        == (966_000, 433_720, 163_065, 38_145)


def test_arvore_do_norte(r):
    f = r["funil"]
    produto = f["M21_identificacao"] * f["M22_ativacao"] * f["M23_envio"] * f["M24_registro"] * f["M18_efetivacao"]
    assert produto == pytest.approx(f["M20_norte"]) and round(f["M20_norte"], 4) == 0.0048
    assert round(f["envio_tecnicas"], 2) == 0.45 and round(f["envio_administrativas"], 2) == 0.83


def test_cenarios_e_ponte(r):
    c = r["cenarios"]
    assert round(c["conservador"], -3) == 842_000 and round(c["base"], -3) == 1_118_000
    assert round(c["agressivo"], -3) == 1_330_000 and c["agressivo"] < r["meta"]          # nenhum chega a 2%
    ganhos = dict(r["ponte_agressivo"])
    assert [round(ganhos[k], -3) for k in ("registro", "envio", "ativacao", "markup")] == [123_000, 303_000, 419_000, 150_000]
    assert sum(v for _, v in r["ponte_agressivo"]) == pytest.approx(c["agressivo"])


def test_ondas_cobrem_as_desligadas_com_bom_benchmark():
    df, _ = af.carregar()
    des = df[~df.ligada]
    nas_ondas = set(sum(af.ONDAS.values(), []))
    assert nas_ondas | af.EXCLUIR_DAS_ONDAS == set(des.inteligencia)
    assert des[des.inteligencia.isin(nas_ondas)].bench.min() > 0.7
    assert des[des.inteligencia.isin(af.EXCLUIR_DAS_ONDAS)].bench.max() < 0.2
