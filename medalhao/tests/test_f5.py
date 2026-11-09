"""Testes da F5 com Spark local, sobre o sinistro REAL e o SINTÉTICO rotulado. Rodar a partir de Arvo_Case:
    pytest medalhao/tests -v        (requer pyspark 3.5 + Java 11/17)
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
import yaml
from pyspark.sql import functions as F

from medalhao import transformacoes as tf
from medalhao.local import ExpectationFalhou, executar, liberar, spark_local
from plataforma.sinteticos.gerar_sinistro_sintetico import Gerador

RAIZ = Path(__file__).resolve().parents[2]
REAL = str(RAIZ / "arvo.case" / "sinistro-hospital-saorafael.csv")
PLANILHA = str(RAIZ / "arvo.case" / "Inteligencias_apos_6_meses.xlsx")
MODELO = yaml.safe_load((RAIZ / "arquitetura" / "modelo.yaml").read_text("utf-8"))
DIMENSOES_DQ = {"consistencia", "acuracia", "validade", "completude", "tempestividade", "unicidade"}


def _h(id_benef: str) -> str:
    return hashlib.sha256(f"arvo:{id_benef}".encode()).hexdigest()[:16]


@pytest.fixture(scope="session")
def spark():
    s = spark_local()
    s.sparkContext.setLogLevel("ERROR")
    yield s


@pytest.fixture(scope="session")
def real(spark):
    out = executar(spark, REAL, PLANILHA, run_id="teste-real")
    yield out
    liberar(out)


@pytest.fixture(scope="session")
def sint(spark, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("sint")
    g = Gerador(42, 400, 2025, 6)
    g.gerar()
    g.gravar(pasta)
    out = executar(spark, str(pasta / "sinistro_sintetico.csv"), run_id="teste-sint")
    gab = pd.read_csv(pasta / "gabarito_sintetico.csv", dtype=str, encoding="utf-8-sig", keep_default_na=False)
    yield out, gab
    liberar(out)


# ============================================================== dado REAL
def test_real_bronze_silver_sem_perda(real):
    assert real["bronze.sinistro_raw"].count() == 1696
    assert real["silver.item_conta"].count() == 1696 and real["quarantine.item_conta_rejeitado"].count() == 0
    s = real["silver.item_conta"].agg(F.sum("vl_total"), F.min("dt_atendimento"), F.max("dt_atendimento"),
                                      F.count(F.when(F.col("conceito").isNull(), 1))).first()
    assert s[0] == Decimal("1194396.92")                                   # decimal PT-BR exato, sem float
    assert str(s[1]) == "2025-06-01" or str(s[1]).startswith("2025-06")
    assert str(s[2]).startswith("2025-06") and s[3] == 0                  # 100% de aderência semântica


def test_real_conflito_semantico_e_atendimento(real):
    c = real["silver.conta"]
    assert c.count() == 320 and c.where("conflito_semantico").count() == 32          # AMB-01 (F1: 32 contas)
    itens_conflito = real["gold.fato_item"].where("conflito_semantico").count()
    assert itens_conflito == 114
    a = real["silver.atendimento"]
    assert a.count() == 309 and a.where("n_contas > 1").count() == 11
    frag = {r[0] for r in a.where("suspeita_fragmentacao").select("id_beneficiario_hash").collect()}
    rep = {r[0] for r in a.where("procedimento_cirurgico_repetido").select("id_beneficiario_hash").collect()}
    assert frag == {_h("B00152"), _h("B00212")}                            # AMB-02 do decision log
    assert rep == {_h("B00080"), _h("B00134")}                             # AMB-08 do decision log


def test_real_gap_contratual_bate_com_regra_de_preco(real):
    f = real["gold.fato_item"]
    acima = f.where("vl_excedente_potencial > 0")
    assert acima.count() == 175
    assert acima.agg(F.sum("vl_excedente_potencial")).first()[0] == Decimal("39875.41")   # = protótipo (Cl. 2.2)
    assert f.where("NOT tem_preco_pactuado").count() == 0                  # cobertura de preço 100% (Cl. 2.3)


def test_real_funil_bate_com_planilha(real):
    s = real["silver.funil_inteligencia"].agg(F.sum("vl_identificado"), F.sum("vl_efetivado"),
                                              F.countDistinct("competencia")).first()
    assert s[0] == Decimal("1936700.00") and abs(float(s[1]) - 335769.94) < 0.05 and s[2] == 1
    assert real["gold.fato_funil_economia"].where("status_inteligencia = 'Ligada'").count() == 14


def test_real_sem_identificador_em_claro_apos_bronze(real):
    for nome, df in real.items():
        if nome.startswith("_") or nome.startswith("bronze."):
            continue
        assert "id_beneficiario" not in df.columns, nome
    linha = real["silver.item_conta"].select("id_beneficiario_hash").first()[0]
    assert len(linha) == 16 and not linha.startswith("B")


def test_pseudonimo_igual_a_mascara_sql():
    sql = (RAIZ / "plataforma" / "sql" / "02_mascaras_lgpd.sql").read_text("utf-8")
    assert "sha2(concat('arvo:', id), 256), 1, 16" in sql and tf.SAL_PSEUDONIMO == "arvo:"


# ============================================================== dado SINTÉTICO rotulado
def test_sintetico_quarentena_exatamente_os_erros_injetados(sint):
    out, gab = sint
    q = pd.DataFrame([r.asDict() for r in out["quarantine.item_conta_rejeitado"].select("id_item", "motivos").collect()])
    dq = gab[gab.erro_dq != ""]
    esperado = {"dq_codigo_invalido": {"E02", "E03"}, "dq_carater_desconhecido": {"E04"},
                "dq_total_inconsistente": {"E08"}, "dq_qtd_zero": {"E06"}}
    for _, r in dq.iterrows():
        if r.erro_dq == "dq_id_duplicado":
            anterior = f"SX{int(r.id_item[2:]) - 1:06d}"                    # o gerador copiou o id do item anterior
            linhas = q[q.id_item == anterior]
            assert len(linhas) == 2 and all("E01" in set(m) for m in linhas.motivos)
        else:
            linha = q[q.id_item == r.id_item]
            assert len(linha) == 1 and set(linha.motivos.iloc[0]) == esperado[r.erro_dq], (r.erro_dq, linha)
    assert len(q) == len(dq) + 1                                             # +1: a duplicata leva as duas linhas


def test_sintetico_gap_igual_a_glosa_de_preco_rotulada(sint):
    out, gab = sint
    excedente = out["gold.fato_item"].agg(F.sum("vl_excedente_potencial")).first()[0]
    r1 = gab[(gab.rotulo == "R1_preco_acima_teto") & (gab.erro_dq == "")].vl_glosa_esperado.astype(float).sum()
    assert abs(float(excedente) - r1) < 0.01


def test_sintetico_fragmentacao_detectada(sint):
    out, gab = sint
    n_frag = gab[gab.rotulo == "borda_AMB02_fragmentacao"].id_conta.nunique()
    assert out["silver.atendimento"].where("suspeita_fragmentacao").count() == n_frag


# ============================================================== documentação = código
_TIPOS_IMPLEMENTADOS = {k: v for k, v in MODELO["tabelas"].items()
                        if v["status"] == "implementado" and v.get("fase") in ("F5", "F6") and v.get("colunas")}


@pytest.mark.parametrize("tabela", sorted(_TIPOS_IMPLEMENTADOS))
def test_schema_igual_ao_modelo_documentado(real, tabela):
    df = real[tabela]
    obtido = {f.name: f.dataType.simpleString() for f in df.schema.fields}
    esperado = {c: t.replace(" ", "") for c, t in _TIPOS_IMPLEMENTADOS[tabela]["colunas"].items()}
    assert obtido == esperado, {"so_no_codigo": set(obtido) - set(esperado), "so_no_modelo": set(esperado) - set(obtido),
                                "tipos": {c: (obtido[c], esperado[c]) for c in obtido.keys() & esperado.keys()
                                          if obtido[c] != esperado[c]}}


def test_pipeline_lakeflow_declara_as_tabelas_do_modelo():
    src = (RAIZ / "medalhao" / "pipeline_lakeflow.py").read_text("utf-8")
    declaradas = set(re.findall(r'name=f"\{CAT\}\.(\w+\.\w+)"', src))
    fora_do_pipeline = {"bronze.inteligencias_raw", "ops.dq_resultados"}   # gravadas por notebooks do job
    assert declaradas == set(_TIPOS_IMPLEMENTADOS) - fora_do_pipeline


def test_bundle_tem_pipeline_e_caminhos_validos():
    r = yaml.safe_load((RAIZ / "resources" / "pipelines.yml").read_text("utf-8"))["resources"]
    base = RAIZ / "resources"
    for lib in r["pipelines"]["f5_medalhao_pipeline"]["libraries"]:
        assert (base / lib["notebook"]["path"]).resolve().exists()
    for t in r["jobs"]["f5_medalhao"]["tasks"]:
        if "notebook_task" in t:
            assert (base / t["notebook_task"]["notebook_path"]).resolve().exists()


def test_expectations_bem_formadas(spark, real):
    exp = tf.carregar_expectations()
    ids = [r["id"] for t, regras in exp.items() if t != "versao" for r in regras]
    assert len(ids) == len(set(ids))
    cand = tf.silver_item_conta_candidatos(real["bronze.sinistro_raw"], tf.df_map_tuss(spark), tf.df_dominios(spark), "x")
    alvo = {"silver.item_conta": cand, "silver.conta": tf.silver_conta(real["silver.item_conta"],
                                                                      tf.carregar_parametros_contrato()),
            "gold.fato_item": real["gold.fato_item"], "gold.fato_apontamento": real["gold.fato_apontamento"]}
    for t, regras in exp.items():
        if t == "versao":
            continue
        for r in regras:
            assert r["dimensao"] in DIMENSOES_DQ and r["acao"] in {"warn", "quarentena", "fail"}, r
            alvo[t].select(F.expr(r["expr"])).limit(1).collect()            # a expressão compila contra o schema real


# ============================================================== governança e invariantes
def test_prod_exige_contrato_aprovado():
    with pytest.raises(RuntimeError, match="aprovado"):
        tf.carregar_parametros_contrato("arvo_prod")


def test_invariante_fail_interrompe(spark, tmp_path):
    p = tf.carregar_parametros_contrato()
    p["anexo_i"] = [{**i, "valor_teto": -100.0} if i["codigo"] == "60012010" else i for i in p["anexo_i"]]
    p["versao_contrato"] = "TESTE@quebrado"
    arq = tmp_path / "contract_params.json"
    arq.write_text(json.dumps(p), "utf-8")
    with pytest.raises(ExpectationFalhou, match="E31"):
        executar(spark, REAL, contrato_aprovado=str(arq), run_id="teste-fail")


def test_reprocessamento_deterministico(spark, real):
    out2 = executar(spark, REAL, run_id="teste-real")
    cols = [c for c in tf.COLUNAS_FATO_ITEM]
    a = real["gold.fato_item"].select(*cols).exceptAll(out2["gold.fato_item"].select(*cols)).count()
    b = out2["gold.fato_item"].select(*cols).exceptAll(real["gold.fato_item"].select(*cols)).count()
    liberar(out2)
    assert a == b == 0


# ============================================================== indicadores gold calculados das fórmulas do contrato
def test_formulas_do_contrato_rodam_na_gold_e_a_arvore_do_norte_fecha(real):
    """Avalia as fórmulas de semantic/metricas.yaml direto na gold.fato_funil_economia (dado real da planilha)."""
    met = yaml.safe_load((RAIZ / "semantic" / "metricas.yaml").read_text("utf-8"))
    ms = {m["id"]: m for m in met["metricas"] if m["tabela"] == "fato_funil_economia"}
    linha = real["gold.fato_funil_economia"].agg(*[F.expr(m["formula"]).alias(i) for i, m in ms.items()]).first()
    v = {i: float(linha[i]) for i in ms}
    arv = met["arvore_norte"]
    produto = 1.0
    for f in arv["fatores"]:
        produto *= v[f]
    assert abs(produto - v[arv["norte"]]) < 1e-9                        # identidade M20 = Π fatores
    assert abs(v["M20"] - 335769.94 / 70_000_000) < 1e-6                # 0,48% do sinistro
    assert abs(v["M19"] - v["M20"] / 0.02) < 1e-9
    assert abs(v["M16"] - (1 - v["M23"])) < 1e-9 and abs(v["M17"] - (1 - v["M24"])) < 1e-9   # complementos
    esperado = {"M21": 0.02767, "M22": 0.5012, "M23": 0.5532, "M24": 0.6963, "M18": 0.8980}
    for i, x in esperado.items():
        assert abs(v[i] - x) < 5e-4, (i, v[i])
