"""Testes da F6 (motor de regras). Rodar a partir de Arvo_Case:  pytest tests/rules -v   (Spark local)"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
import yaml
from pyspark.sql import functions as F

from arvo.medallion import transformacoes as tf
from arvo.medallion.local import executar, liberar, spark_local
from arvo.rules import motor
from arvo.platform.sinteticos.gerar_sinistro_sintetico import COLUNAS, Gerador

RAIZ = Path(__file__).resolve().parents[2]
REAL = str(RAIZ / "data" / "case" / "sinistro-hospital-saorafael.csv")
CFG = motor.carregar_regras()


@pytest.fixture(scope="session")
def spark():
    s = spark_local()
    s.sparkContext.setLogLevel("ERROR")
    return s


@pytest.fixture(scope="session")
def real(spark):
    out = executar(spark, REAL, run_id="f6-real")
    yield out
    liberar(out)


@pytest.fixture(scope="session")
def sint(spark, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("sint6")
    g = Gerador(42, 400, 2025, 6)
    g.gerar()
    man = g.gravar(pasta)
    out = executar(spark, str(pasta / "sinistro_sintetico.csv"), run_id="f6-sint")
    gab = pd.read_csv(pasta / "gabarito_sintetico.csv", dtype=str, encoding="utf-8-sig", keep_default_na=False)
    yield out, gab, man
    liberar(out)


def _csv(tmp_path: Path, linhas: list[dict]) -> str:
    """Escreve um sinistro mínimo no MESMO formato da origem (decimal com vírgula, data por extenso, BOM)."""
    base = {"id_prestador": "P001", "nome_prestador": "Hospital Sao Rafael", "id_beneficiario": "BX0001"}
    df = pd.DataFrame([{**base, **l} for l in linhas])[COLUNAS]
    for c in ("vl_unitario", "vl_total"):
        df[c] = df[c].map(lambda v: f"{v:.2f}".replace(".", ","))
    arq = tmp_path / "borda.csv"
    arq.write_bytes(("﻿" + df.to_csv(index=False)).encode("utf-8"))
    return str(arq)


def _item(i, conta, cod, desc, tipo, vu, qtd=1, carater="Eletivo", regime="Internação", data="10 de junho de 2025"):
    return {"id_item": i, "id_conta": conta, "cod_tuss": cod, "desc_item": desc, "tipo_item": tipo, "qtd": str(qtd),
            "vl_unitario": vu, "vl_total": round(vu * qtd, 2), "carater_atendimento": carater, "tipo_conta": regime,
            "dt_atendimento": data}


# ============================================================== dado REAL
def test_real_reproduz_o_protótipo_e_respeita_a_hierarquia(real):
    r = real["_resumo_motor"]
    assert r["apontamentos"] == 369 and round(r["vl_glosado"], 2) == 121948.93
    por = {k: (n, round(v, 2)) for k, (n, v) in r["por_regra"].items()}
    assert por == {"R1": (175, 39875.41), "R2": (50, 51081.77), "R3": (67, 4402.4), "R4": (77, 26589.35)}
    assert r["fora_vigencia"] == 0


def test_real_revisao_humana_so_nos_casos_do_decision_log(real):
    ap = real["gold.fato_apontamento"]
    rev = ap.where("status_envio = 'REVISAO_HUMANA'")
    assert rev.count() == 9 and rev.where("regra_principal = 'R4' AND motivo_revisao LIKE 'AMB-01%'").count() == 9
    ps_r4 = real["gold.fato_item_auditado"].where("regra_principal = 'R4' AND regime = 'PRONTO_SOCORRO'").count()
    assert ps_r4 == 9


def test_real_justificativas_deterministicas(real):
    j = {r.id_item: r.justificativa for r in real["gold.fato_apontamento"]
         .where("id_item IN ('IT00136', 'IT00856')").collect()}
    assert j["IT00136"] == ("Glosa integral de R$ 1.226,03 no item IT00136: taxa de sala (cód. 20103077) inclusa no pacote "
                            "do procedimento 30715016 (Anexo II), cobrado na mesma conta G00021. Fundamento: Cláusulas 3.2(a) e 3.3.")
    assert "R$ 4.892,63 acima do pactuado R$ 4.200,00" in j["IT00856"] and j["IT00856"].endswith("Cláusula 2.2.")


def test_real_invariante_M26_zero_pela_formula_do_contrato(real):
    met = {m["id"]: m for m in yaml.safe_load((RAIZ / "src" / "arvo" / "semantic" / "metricas.yaml").read_text("utf-8"))["metricas"]}
    assert real["gold.fato_apontamento"].agg(F.expr(met["M26"]["formula"])).first()[0] == 0


def test_real_item_auditado_fecha_com_apontamentos(real):
    ia, fi = real["gold.fato_item_auditado"], real["gold.fato_item"]
    assert ia.count() == fi.count() == 1696 and ia.where("glosado").count() == 369
    assert ia.agg(F.sum("vl_glosado")).first()[0] == Decimal("121948.93")
    assert ia.where("NOT glosado AND vl_glosado <> 0").count() == 0


# ============================================================== dado SINTÉTICO (verdade por construção)
def test_sintetico_precisao_e_recall_100_nos_rotulos_por_construcao(sint):
    out, gab, man = sint
    glosados = {r[0] for r in out["gold.fato_apontamento"].select("id_item").collect()}
    limpos = gab[(gab.erro_dq == "")]
    esperados = set(limpos[limpos.indevido_por_contrato == "True"].id_item)
    assert glosados == esperados, {"FP": sorted(glosados - esperados)[:5], "FN": sorted(esperados - glosados)[:5]}
    total = out["gold.fato_apontamento"].agg(F.sum("vl_glosado")).first()[0]
    assert float(total) == pytest.approx(man["vl_glosa_esperado_total"], abs=0.01)


def test_sintetico_casos_de_borda_seguem_o_decision_log(sint):
    out, gab, _ = sint
    ap = {r.id_item: r for r in out["gold.fato_apontamento"].collect()}
    for _, r in gab.iterrows():
        if r.rotulo == "borda_AMB01_ps_eletivo_com_taxa":
            assert ap[r.id_item].status_envio == "REVISAO_HUMANA"        # glosa literal, com revisão humana
        if r.rotulo in ("borda_AMB02_fragmentacao", "borda_AMB04_sala_sem_pacote"):
            assert r.id_item not in ap                                     # fora da regra (escopo = conta)


# ============================================================== casos de borda construídos
def test_bordas_construidas(spark, tmp_path):
    linhas = [
        # C1: herniorrafia (pacote porte 2) + sala porte 4 (AMB-11) + fio acima do teto (R3 integral, 2.2 subsidiária)
        _item("X01", "C1", "31309062", "Herniorrafia inguinal unilateral", "Procedimento", 3000.00),
        _item("X02", "C1", "20103077", "Taxa de sala cirúrgica — porte 4", "Taxa", 1200.00),
        _item("X03", "C1", "70520020", "Fio de sutura agulhado", "Material", 60.00, qtd=2),
        # C2: ambulatorial sem pacote. Sala e compressa NÃO são glosadas (AMB-04)
        _item("X04", "C2", "20103050", "Taxa de sala cirúrgica — porte 2", "Taxa", 600.00, regime="Ambulatorial"),
        _item("X05", "C2", "70402600", "Compressa cirúrgica estéril", "Material", 9.00, regime="Ambulatorial"),
        # C3: PS com urgência: taxa devida
        _item("X06", "C3", "99999001", "Taxa de urgência/emergência", "Taxa", 350.00, carater="Urgência", regime="Pronto Socorro"),
        # C4: diária a mais de 5× o teto (provável digitação) → R1 com revisão humana (E30)
        _item("X07", "C4", "60012010", "Diária de enfermaria", "Taxa", 3000.00),
        # C5: fora da vigência (contrato até 31/12/2026). Nenhuma glosa (AMB-13)
        _item("X08", "C5", "31001012", "Colecistectomia videolaparoscópica", "Procedimento", 4000.00, data="10 de março de 2027"),
        _item("X09", "C5", "70520020", "Fio de sutura agulhado", "Material", 40.00, data="10 de março de 2027"),
    ]
    out = executar(spark, _csv(tmp_path, linhas), run_id="borda")
    ap = {r.id_item: r for r in out["gold.fato_apontamento"].collect()}
    fora_vigencia = out["_resumo_motor"]["fora_vigencia"]
    liberar(out)
    assert set(ap) == {"X02", "X03", "X07"}
    assert ap["X02"].regra_principal == "R2B" and ap["X02"].status_envio == "REVISAO_HUMANA"
    assert ap["X03"].regra_principal == "R3" and ap["X03"].clausulas_subsidiarias == ["2.2"]
    assert ap["X03"].vl_glosado == Decimal("120.00")                     # integral prevalece; nunca soma excedente
    assert ap["X07"].regra_principal == "R1" and "E30" in ap["X07"].motivo_revisao
    assert ap["X07"].vl_glosado == Decimal("2520.00")                    # só o excedente: 3000 − 480
    assert fora_vigencia == 2


# ============================================================== regras como dados
_PALAVRAS = {"and", "or", "not", "true", "false", "null", "is", "in", "pronto_socorro"}


def test_regras_so_usam_colunas_semanticas_e_papeis_contratuais():
    permitidas = set(CFG["colunas_permitidas"])
    exprs = [CFG["pre_condicao_global"]]
    for r in CFG["regras"]:
        exprs += [r["condicao"], r["valor"], r["referencia"]] + [c["condicao"] for c in r.get("revisao_humana", [])]
    for e in exprs:
        ids = set(re.findall(r"[a-z_]+", re.sub(r"'[^']*'", "", e.lower()))) - _PALAVRAS
        assert ids <= permitidas, f"'{e}' usa colunas fora do permitido: {ids - permitidas}"


def test_templates_usam_campos_existentes(real, spark):
    enr = motor.enriquecer(real["gold.fato_item"], real["silver.conta"], real["gold.dim_item_contratado"],
                           real["gold.dim_contrato"], tf.carregar_parametros_contrato())
    disponiveis = set(enr.columns) | {"vl_glosado"}
    for r in CFG["regras"]:
        campos = motor.campos_do_template(r["justificativa"])
        for e in r["evidencia"]:
            campos |= motor.campos_do_template(e)
        assert campos <= disponiveis, (r["id"], campos - disponiveis)
        assert r["clausula"] in r["justificativa"] or any(c in r["justificativa"] for c in r["clausulas_base"])


def test_mudar_o_contrato_muda_a_glosa_sem_mudar_codigo(spark, tmp_path, real):
    p = tf.carregar_parametros_contrato()
    p["anexo_i"] = [{**i, "valor_teto": 400.0} if i["codigo"] == "60012010" else i for i in p["anexo_i"]]
    p["versao_contrato"] = "PRT-2025-0417@teste-aditivo"
    arq = tmp_path / "cp.json"
    arq.write_text(json.dumps(p), "utf-8")
    out = executar(spark, REAL, contrato_aprovado=str(arq), run_id="aditivo")
    antes = real["gold.fato_apontamento"].where("regra_principal = 'R1'").count()
    depois = out["gold.fato_apontamento"].where("regra_principal = 'R1'").count()
    assert depois > antes
    versao = out["gold.fato_apontamento"].select("versao_contrato").distinct().first()[0]
    liberar(out)
    assert versao == "PRT-2025-0417@teste-aditivo"


def test_reprocessamento_gera_os_mesmos_apontamentos(spark, real):
    out2 = executar(spark, REAL, run_id="f6-real-2")
    cols = [c for c in motor.COLUNAS_APONTAMENTO if c != "run_id"]
    a, b = real["gold.fato_apontamento"].select(*cols), out2["gold.fato_apontamento"].select(*cols)
    dif = a.exceptAll(b).count() + b.exceptAll(a).count()
    liberar(out2)
    assert dif == 0


def test_dim_regra_e_ponte_cobrem_todas_as_regras(real):
    ids = {r["id"] for r in CFG["regras"]}
    assert {r[0] for r in real["gold.dim_regra"].select("regra_id").collect()} == ids
    assert {r[0] for r in real["gold.ponte_regra_inteligencia"].select("regra_id").collect()} == ids
