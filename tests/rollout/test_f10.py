"""Testes da F10 (rollout). Rodar a partir de Arvo_Case:  pytest tests/rollout -v (Spark local)"""
from __future__ import annotations

import copy

import pandas as pd
import pytest
import yaml

from arvo.rollout import backtest, envio, promocao, regressao

RAIZ = envio.AQUI.parents[2]          # raiz do repositório (src/arvo/rollout → raiz)


@pytest.fixture(scope="module")
def spark():
    from arvo.medallion.local import spark_local

    s = spark_local()
    s.sparkContext.setLogLevel("ERROR")
    s.catalog.clearCache()            # suítes anteriores no mesmo processo (pytest de tudo) não podem levar o heap
    return s


def _estado(**regras):
    return {"versao": 1, "regras": {r: {"estagio": e, "desde": "2026-11-01", "precisao_inf": p} for r, (e, p) in regras.items()},
            "historico": []}


# ===================================================================================================== configuração
def test_configuracao_coerente():
    cfg, est = envio.carregar(), envio.carregar_estado()
    ids_motor = {r["id"] for r in yaml.safe_load((RAIZ / "src" / "arvo" / "rules" / "regras.yaml").read_text("utf-8"))["regras"]}
    assert set(est["regras"]) == ids_motor                                      # toda regra do motor tem estado
    assert all(e["estagio"] in cfg["estagios"] for e in est["regras"].values())
    assert {r for o in cfg["ondas_canario"] for r in o["regras"]} == ids_motor
    inds = {i["id"] for i in yaml.safe_load((RAIZ / "src" / "arvo" / "monitoring" / "indicadores.yaml").read_text("utf-8"))["indicadores"]}
    assert {g["indicador"] for g in cfg["rebaixamento"]} <= inds
    donos = set(yaml.safe_load((RAIZ / "src" / "arvo" / "semantic" / "glossario.yaml").read_text("utf-8"))["donos_validos"])
    assert {a for p in cfg["promocao"].values() for a in p["aprovadores"]} <= donos
    assert all(h["aprovado_por"] == [] or all(isinstance(a, str) for a in h["aprovado_por"]) for h in est["historico"])


def test_teto_de_valor_vem_da_matriz_de_custo():
    assert envio.teto_valor(0.95) == pytest.approx(1700) and envio.teto_valor(0.98) == pytest.approx(4700)
    assert envio.teto_valor(0.99) == pytest.approx(9700) and envio.teto_valor(0.999) == 10000   # trava de política
    assert envio.teto_valor(0.94) == 0 and envio.teto_valor(None) == 0                         # abaixo do piso: nada automático


# ===================================================================================================== destino (Spark)
def _ap(spark, linhas):
    return spark.createDataFrame(linhas, "id_apontamento string, id_item string, id_conta string, regra_principal string, "
                                         "vl_glosado decimal(14,2), motivo_revisao string, run_id string")


def test_precedencia_dos_destinos(spark):
    from decimal import Decimal as D
    ap = _ap(spark, [("a1", "i1", "c", "R1", D("100"), None, "r"), ("a2", "i2", "c", "R3", D("100"), None, "r"),
                     ("a3", "i3", "c", "R4", D("100"), "AMB-01: PS", "r"), ("a4", "i4", "c", "R4", D("100"), None, "r"),
                     ("a5", "i5", "c", "R4", D("5000"), None, "r"), ("a6", "i6", "c", "R4", D("100"), None, "r"),
                     ("a7", "i7", "c", "RX", D("100"), None, "r"), ("a8", "i8", "c", "R2", D("100"), None, "r")])
    itens = spark.createDataFrame([(f"i{k}", k == 4) for k in range(1, 9)], "id_item string, conflito_semantico boolean")
    est = _estado(R1=("SHADOW", None), R3=("CANARIO", None), R4=("AUTOMATICO", 0.98), R2=("DESLIGADA", None))
    d = {r.id_apontamento: (r.destino_envio, r.motivo_destino) for r in envio.decidir(ap, itens, est, True).collect()}
    assert d["a1"][0] == "NAO_ENVIAR" and d["a8"][0] == "NAO_ENVIAR"
    assert d["a2"] == ("REVISAO_HUMANA", "regra em CANARIO")
    assert d["a3"] == ("REVISAO_HUMANA", "AMB-01: PS")                          # motivo do motor vence
    assert d["a4"] == ("REVISAO_HUMANA", "conflito semântico no item")
    assert d["a5"][0] == "REVISAO_HUMANA" and "4,700.00" in d["a5"][1]          # acima do teto (p = 0,98)
    assert d["a6"][0] == "ENVIO_AUTOMATICO"
    assert d["a7"] == ("NAO_ENVIAR", "regra em DESLIGADA")                      # regra sem estado não sai
    fechado = {r.destino_envio for r in envio.decidir(ap, itens, est, False).collect()}
    assert fechado == {"BLOQUEADO"}                                             # portão fechado vence tudo


# ===================================================================================================== promoção e rebaixamento
def test_promocao_exige_todos_os_criterios():
    ev = {"n_auditado": 95, "precisao_inf": 0.96, "violacoes_invariantes": 0, "aderencia_semantica": 1.0,
          "telemetria_completa": True, "semanas_no_estagio": 5}
    assert promocao.avaliar_promocao("R1", "SHADOW", ev, n_plano=91)["apta"]
    r = promocao.avaliar_promocao("R1", "SHADOW", {**ev, "n_auditado": 50}, n_plano=91)
    assert not r["apta"] and r["faltam"][0].startswith("amostra: 50")
    can = promocao.avaliar_promocao("R1", "CANARIO", {**ev, "precisao": 0.99, "reversao": 0.02}, n_plano=91)
    assert not can["apta"] and any(f.startswith("integracao") for f in can["faltam"])
    assert set(can["aprovadores"]) == {"auditor_medico", "juridico", "pm_cs"}
    assert not promocao.avaliar_promocao("R1", "AUTOMATICO", ev)["apta"]


def test_rebaixamento_automatico_so_desce():
    est = _estado(R1=("AUTOMATICO", 0.97), R3=("SHADOW", None), R4=("CANARIO", 0.96))
    linhas = [{"id_indicador": "S09", "status": "ALERTA", "recorte": "regra_principal=R1"},
              {"id_indicador": "S06", "status": "ALERTA", "recorte": "regra_principal=R3"},   # SHADOW < CANARIO: não sobe
              {"id_indicador": "S05", "status": "OK", "recorte": "regra_principal=R4"},
              {"id_indicador": "S18", "status": "ALERTA", "recorte": "total"}]               # invariante: é do portão
    novo, mud = promocao.rebaixar(est, linhas, hoje="2026-11-07")
    assert novo["regras"]["R1"]["estagio"] == "DESLIGADA" and novo["regras"]["R3"]["estagio"] == "SHADOW"
    assert novo["regras"]["R4"]["estagio"] == "CANARIO" and len(mud) == 1
    assert mud[0]["aprovado_por"] == ["automatico:S09"] and est["regras"]["R1"]["estagio"] == "AUTOMATICO"   # sem efeito colateral


# ===================================================================================================== regressão e backtest
def test_regressao_exige_explicacao_para_cada_diferenca():
    antes = pd.DataFrame({"id_item": ["i1", "i2", "i3", "i4"], "regra_principal": ["R1", "R3", "R3", "R4"],
                          "vl_glosado": [100.0, 10.0, 12.0, 300.0]})
    depois = pd.DataFrame({"id_item": ["i1", "i4", "i5"], "regra_principal": ["R1", "R2", "R1"], "vl_glosado": [90.0, 300.0, 50.0]})
    d = regressao.diff(antes, depois)
    assert dict(zip(d.id_item, d.tipo)) == {"i1": "VALOR_MUDOU", "i2": "REMOVIDO", "i3": "REMOVIDO", "i4": "REGRA_MUDOU", "i5": "NOVO"}
    assert regressao.resumo(d)["delta_vl_total"] == pytest.approx(18.0)        # −10 −10 −12 +50
    expl = [{"motivo": "R3 desligada por AMB-02", "regra_antes": "R3", "tipo": "REMOVIDO"},
            {"motivo": "teto do item 70520020 corrigido no aditivo", "id_item": ["i1"]}]
    assert set(regressao.sem_explicacao(d, expl).id_item) == {"i4", "i5"}
    with pytest.raises(ValueError, match="sem filtro"):
        regressao.sem_explicacao(d, [{"motivo": "tudo certo"}])
    assert regressao.sem_explicacao(regressao.diff(antes, antes), []).empty


def test_backtest_contra_historico():
    motor = pd.DataFrame({"id_item": ["a", "b", "c", "d"], "id_conta": ["x"] * 4, "pred": [True, True, False, False],
                          "regra_principal": ["R1", "R3", None, None], "vl_glosado": [10.0, 5.0, None, None]})
    hist = pd.DataFrame({"id_item": ["a", "b", "c", "d"], "competencia": ["2025-05"] * 4,
                         "auditoria_glosou": [True, False, True, False], "vl_glosado_auditoria": [10.0, 0.0, 7.0, 0.0]})
    r = backtest.avaliar(motor, hist)
    assert r["matriz"] == {"TP": 1, "FP": 1, "FN": 1, "TN": 1} and r["divergencias_para_adjudicacao"] == 2
    assert r["vl_motor"] == 15.0 and r["vl_auditoria"] == 17.0
    with pytest.raises(ValueError, match="duplicado"):
        backtest.validar_historico(pd.concat([hist, hist]))


# ===================================================================================================== dados reais
def test_estado_vigente_no_sinistro_real_nada_sai(spark):
    from arvo.rollout import status

    s = status.coletar(spark)
    assert {r["destino_envio"] for r in s["vigente"]} == {"NAO_ENVIAR"}
    assert sum(r["apontamentos"] for r in s["vigente"]) == 369
    assert not any(a["apta"] for a in s["avaliacoes"])                         # coerente com a F8
    assert {r["destino_envio"] for r in s["simulado"]} == {"REVISAO_HUMANA"}   # abaixo do piso: teto zero
    assert {m["mudanca"].split(":")[0] for m in s["rebaixamentos"]} == {"R1", "R2", "R3", "R4"}
    assert s["estado_apos_rebaixar"]["R2B"] == "SHADOW"
