"""Testes da F8 (avaliação científica). Rodar a partir de Arvo_Case:  pytest tests/evaluation -v (Spark local)"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from arvo.evaluation import adjudicacao as ad
from arvo.evaluation import amostragem as am
from arvo.evaluation import decisao as dc
from arvo.evaluation import divergencias as dv
from arvo.evaluation import metricas as m
from arvo.evaluation import relatorio as rel
from arvo.evaluation.dados import base_avaliacao
from arvo.medallion.local import liberar, spark_local


@pytest.fixture(scope="module")
def base():
    s = spark_local()
    s.sparkContext.setLogLevel("ERROR")
    b, out = base_avaliacao(s)
    yield b
    liberar(out)


# ============================================================== estatística básica
def test_wilson_e_kappa():
    lo, hi = m.wilson(135, 143)
    assert lo == pytest.approx(0.8935, abs=1e-3) and hi == pytest.approx(0.9714, abs=1e-3)
    assert m.wilson(29, 29)[0] == pytest.approx(0.883, abs=1e-3)               # 100% observado ≠ 100% garantido
    assert m.kappa(list("AABB"), list("AABB")) == 1.0
    assert m.kappa(list("AAAB"), list("AABA")) == pytest.approx(-1 / 3, abs=1e-9)


def test_matriz_real(base):
    r = m.precisao_recall(m.matriz(base[base.rotulado]))
    assert (r["TP"], r["FP"], r["FN"], r["TN"]) == (135, 8, 15, 105)


# ============================================================== estimativa populacional
def test_reponderacao_ingenua_invalida_e_pos_estratificada_valida(base):
    rot = base[base.rotulado]
    ing = m.estimativa_populacional(base, rot, "cod_tuss", bootstrap=50)
    pos = m.estimativa_populacional(base, rot, ["cod_tuss", "pred"], bootstrap=50)
    assert not ing["valida"] and round(ing["glosas_estimadas_pela_amostra"]) == 791
    assert pos["valida"] and round(pos["glosas_estimadas_pela_amostra"]) == pos["glosas_reais_do_motor"] == 369


def test_pos_estratificacao_corrige_amostra_enriquecida_em_populacao_conhecida():
    """Propriedade: numa população SINTÉTICA com verdade conhecida e amostra enriquecida em glosados,
    a pós-estratificação recupera a precisão e o recall reais, e a ingênua erra."""
    rng = np.random.default_rng(0)
    n = 6000
    pop = pd.DataFrame({"id_item": range(n), "id_conta": rng.integers(0, 1500, n),
                        "cod_tuss": rng.choice(["a", "b", "c"], n), "pred": rng.random(n) < 0.2})
    ruido = rng.random(n)
    pop["real"] = np.where(pop.pred, ruido > 0.05, ruido < 0.08)        # P real ≈ 95%, FN entre não glosados ≈ 8%
    verdade = m.precisao_recall(m.matriz(pop))
    pesos = np.where(pop.pred, 0.25, 0.10)                               # seleção depende da decisão do motor
    amostra = pop[rng.random(n) < pesos]
    pos = m.estimativa_populacional(pop, amostra, ["cod_tuss", "pred"], bootstrap=300)
    ing = m.estimativa_populacional(pop, amostra, "cod_tuss", bootstrap=300)
    # critério estatístico: a verdade cai DENTRO do IC da pós-estratificação, e FORA do IC da ingênua (viés)
    assert pos["precisao_ic95"][0] <= verdade["precisao"] <= pos["precisao_ic95"][1]
    assert pos["recall_ic95"][0] <= verdade["recall"] <= pos["recall_ic95"][1]
    assert not (ing["recall_ic95"][0] <= verdade["recall"] <= ing["recall_ic95"][1])
    assert pos["valida"] and not ing["valida"]


# ============================================================== divergências
def test_causas_das_divergencias(base):
    d = dv.classificar(base)
    assert (d[d.tipo == "FP"].causa == "REGRA_CONTRATUAL_LITERAL").all() and (d.tipo == "FP").sum() == 8
    assert (d[d.tipo == "FN"].causa == "SEM_BASE_CONTRATUAL").all() and (d.tipo == "FN").sum() == 15
    assert d[d.tipo == "FN"].evidencia.str.contains("do teto").all()      # todos os FN têm preço ≤ teto


def test_sem_concentracao_dos_fn_compativel_com_ruido(base):
    c = dv.teste_concentracao(base, n=1000)
    assert c["p_valor_permutacao"] > 0.05 and c["taxa_sim_entre_nao_glosados"] == pytest.approx(0.125)


# ============================================================== adjudicação cega
def test_pacote_de_adjudicacao_e_cego(base, tmp_path):
    info = ad.gerar_pacote(base, tmp_path)
    assert info == {"casos": 46, "divergencias": 23, "controles": 23}
    planilha = pd.read_csv(tmp_path / "planilha_cega_revisor_A.csv", encoding="utf-8-sig")
    proibidas = {"indevido", "glosado", "regra_principal", "justificativa", "pred", "real", "tipo", "vl_glosado"}
    assert not (proibidas & set(planilha.columns))
    assert planilha.decisao.isna().all()
    chave = pd.read_csv(tmp_path / "CHAVE_NAO_COMPARTILHAR.csv", encoding="utf-8-sig")
    assert set(chave.tipo) == {"FP", "FN", "CONTROLE"}


def test_adjudicacao_kappa_terceiro_revisor_e_validacao(base, tmp_path):
    ad.gerar_pacote(base, tmp_path)
    chave = pd.read_csv(tmp_path / "CHAVE_NAO_COMPARTILHAR.csv", encoding="utf-8-sig")
    a = rel.simular_revisores(chave, "contrato")
    b = a.copy()
    b.loc[0, "decisao"] = "INCONCLUSIVO"
    r = ad.adjudicar(a, b, chave)
    assert r["pendentes_terceiro"] == 1 and 0.9 < r["kappa"] < 1.0
    assert r["concordancia_adjudicado_x_motor"] == 1.0
    vazio = a.copy()
    vazio.loc[3, "decisao"] = ""
    with pytest.raises(ValueError, match="sem decisão"):
        ad.adjudicar(vazio, a, chave)


# ============================================================== decisão por custo
def test_ponto_de_operacao():
    c = dc.carregar_custos()
    assert dc.decidir(0.99, 300.0, c)["modo"] == "AUTOMATICO"
    assert dc.decidir(0.90, 300.0, c)["modo"] == "REVISAO_HUMANA"
    assert dc.decidir(0.10, 50.0, c)["modo"] == "BLOQUEADO"


def test_nenhuma_regra_vai_automatica_com_o_gabarito_atual(base):
    rot = base[base.rotulado]
    vm = base[base.pred].groupby("regra_principal").vl_glosado.mean().to_dict()
    assert {x["modo"] for x in dc.tabela(m.por_regra(rot), vm)} == {"REVISAO_HUMANA"}


# ============================================================== plano amostral
def test_plano_amostral_e_pesos(base):
    assert am.n_proporcao(0.98, 0.02) == 189 and am.n_proporcao(0.98, 0.02, N=175) == 91
    pl = am.plano(base)
    s1, s2 = am.selecionar(base, pl, "r1", semente=5), am.selecionar(base, pl, "r1", semente=5)
    assert s1.equals(s2)                                                  # reprodutível
    soma = s1.groupby("estrato").peso_amostral.sum()
    assert soma["GLOSADO"] == pytest.approx(base.pred.sum()) and soma["NAO_GLOSADO"] == pytest.approx((~base.pred).sum())
    assert s1.id_item.is_unique


# ============================================================== relatório
def test_relatorio_responde_a_pergunta_3(base):
    r = rel.calcular(base, bootstrap=100)
    md = rel.gerar_md(r)
    for trecho in ("Resposta à pergunta 3", "Qual priorizar: precisão", "Divergências e causas", "pós-estratificação".capitalize(),
                   "Plano amostral", "Premissas e limitações"):
        assert trecho.lower() in md.lower(), trecho
