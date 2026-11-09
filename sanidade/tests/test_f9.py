"""Testes da F9 (indicadores de sanidade). Rodar a partir de Arvo_Case:  pytest sanidade/tests -v (Spark local)"""
from __future__ import annotations

import copy
import json
import re
from datetime import date

import pytest
import yaml

from sanidade import gerar
from sanidade.portao import avaliar_portao


@pytest.fixture(scope="module")
def c():
    return gerar.carregar()


@pytest.fixture(scope="module")
def spark():
    from medalhao.local import spark_local

    s = spark_local()
    s.sparkContext.setLogLevel("ERROR")
    s.catalog.clearCache()            # suítes anteriores no mesmo processo (pytest de tudo) não podem levar o heap
    return s


def _so(c, *ids):
    """Cópia da configuração com apenas os indicadores pedidos."""
    c2 = copy.deepcopy(c)
    c2["spec"]["indicadores"] = [i for i in c2["spec"]["indicadores"] if i["id"] in ids]
    return c2


# ===================================================================================================== especificação
def test_especificacao_valida_e_negocio_primeiro(c):
    assert gerar.validar(c) == []
    inds = c["spec"]["indicadores"]
    ordem = [c["spec"]["camadas"][i["camada"]]["ordem"] for i in inds]
    assert ordem == sorted(ordem) and inds[0]["camada"] == "negocio"          # negócio primeiro, de fato
    neg = [i for i in inds if i["camada"] == "negocio"]
    assert len(neg) > max(sum(i["camada"] == k for i in inds) for k in ("semantica", "dados", "ia"))
    assert {i["familia"] for i in neg} >= {"valor", "qualidade_decisao", "funil", "relacao_prestador", "invariantes"}


def test_validar_pega_erros_de_governanca(c):
    ruim = copy.deepcopy(c)
    i0 = ruim["spec"]["indicadores"][0]
    i0["dono"] = "fulano"
    i0["banda"] = {"min": 0.02}                     # sem origem
    ruim["spec"]["indicadores"][1]["runbook"] = "RB-INEXISTENTE"
    ruim["spec"]["indicadores"] = [i for i in ruim["spec"]["indicadores"] if i.get("limite_ia") != "taxa_erro"]
    erros = "\n".join(gerar.validar(ruim))
    for trecho in ("fora de glossario.donos_validos", "banda sem origem", "RB-INEXISTENTE", "taxa_erro"):
        assert trecho in erros, trecho


def test_artefatos_gerados_estao_atualizados(c):
    for k, v in gerar.artefatos(c).items():
        assert gerar.SAIDAS[k].read_text("utf-8") == v, f"rode `python -m sanidade.gerar` ({k})"


def test_dialetos_sao_a_mesma_definicao(c):
    """Databricks (MEASURE da metric view) e local (fórmula na tabela) diferem SÓ na tradução métrica → fórmula."""
    disp = {t for t in c["modelo"]} | {"ops.v_ia_sanidade"}
    corpo = lambda d: gerar.select_status(c, d, disp).split("medicoes AS (")[1]  # noqa: E731  (só as medições; meta é igual)
    db, lo = corpo("databricks"), corpo("local")
    traduzido = db
    for m in c["metricas"].values():
        traduzido = traduzido.replace(f"MEASURE({m['nome']})", m["formula"])
    for tabela, view in c["views"].items():
        traduzido = traduzido.replace(f"FROM {view}", f"FROM gold.{tabela}")
    traduzido = re.sub(r"\b(bronze|silver|gold|ops|quarantine)\.([a-z_]+)", r"\1__\2", traduzido)
    assert traduzido == lo
    assert "MEASURE(" in db and "MEASURE(" not in lo


def test_runbooks_completos(c):
    md = gerar.SAIDAS["runbooks"].read_text("utf-8")
    for i in c["spec"]["indicadores"]:
        assert f"| {i['id']} |" in md and f"**{i['id']}**" in md
    for rid, rb in c["spec"]["runbooks"].items():
        assert f"## {rid}" in md and len(rb["passos"]) >= 2


# ===================================================================================================== artefatos Databricks
def test_alertas_do_bundle(c):
    al = yaml.safe_load(gerar.SAIDAS["alertas"].read_text("utf-8"))["resources"]["alerts"]
    nao_info = [i for i in c["spec"]["indicadores"] if i["severidade"] != "INFO"]
    assert set(al) == {f"sanidade_{i['id'].lower()}" for i in nao_info}
    for i in nao_info:
        a = al[f"sanidade_{i['id'].lower()}"]
        assert {"display_name", "query_text", "warehouse_id", "evaluation", "schedule"} <= set(a)   # obrigatórios (doc)
        assert "${var.catalog}.ops.v_sanidade_status" in a["query_text"] and f"'{i['id']}'" in a["query_text"]
        assert a["evaluation"]["comparison_operator"] == "GREATER_THAN" and a["evaluation"]["source"]["name"] == "n_alerta"
        assert a["schedule"]["timezone_id"] == "America/Sao_Paulo"
        assert i["dono"] in a["custom_summary"] and i["runbook"] in a["custom_summary"]
        if i["severidade"] == "CRITICA":
            assert a["schedule"]["quartz_cron_schedule"] == "0 0 * * * ?" and "BLOQUEIA O ENVIO" in a["custom_description"]
    assert "@" not in gerar.SAIDAS["alertas"].read_text("utf-8")                   # nunca e-mail no repositório


def test_painel_lvdash_consistente():
    p = json.loads(gerar.SAIDAS["painel"].read_text("utf-8"))
    ds = {d["name"]: "".join(d["queryLines"]) for d in p["datasets"]}
    assert not any("arvo_" in q for q in ds.values())        # catálogo vem do bundle (dataset_catalog), por target
    assert [pg["displayName"] for pg in p["pages"]][0].endswith("Negócio")
    nomes = []
    for pg in p["pages"]:
        for item in pg["layout"]:
            w, pos = item["widget"], item["position"]
            nomes.append(w["name"])
            assert 0 <= pos["x"] and pos["x"] + pos["width"] <= 6
            if "queries" not in w:
                continue
            q = w["queries"][0]["query"]
            assert q["datasetName"] in ds
            campos = {f["name"] for f in q["fields"]}
            enc = w["spec"]["encodings"]
            usados = {e["fieldName"] for e in enc.get("columns", [])} | {v["fieldName"] for k, v in enc.items() if k != "columns"}
            assert usados <= campos
            for f in campos:                              # o dataset devolve a coluna pedida
                assert re.search(rf"\b{f}\b", ds[q["datasetName"]]), (w["name"], f)
    assert len(nomes) == len(set(nomes))
    bundle = yaml.safe_load(gerar.SAIDAS["painel_bundle"].read_text("utf-8"))["resources"]["dashboards"]["painel_sanidade"]
    assert bundle["dataset_catalog"] == "${var.catalog}" and bundle["file_path"].endswith(".lvdash.json")


def test_view_databricks_marca_sem_fonte_o_que_nao_existe(c):
    sql = gerar.SAIDAS["view"].read_text("utf-8")
    assert "USE CATALOG IDENTIFIER(:catalog)" in sql and "gold.fato_glosa_ciclo" not in sql.split("medicoes AS")[1]
    assert "MEASURE(indice_norte)" in sql and "semantic.mv_funil_economia" in sql


# ===================================================================================================== semântica do status (Spark)
def test_sigma_alerta_ok_e_calibrando(c, spark):
    """S03: banda ±3σ das 6 competências anteriores. R1 estável salta → ALERTA; R2 estável → OK; R3 curta → CALIBRANDO."""
    linhas = []
    for k in range(8):
        comp = date(2025, 1 + k, 1)
        linhas += [(comp, "R1", 1000.0, 100.0 + k if k < 7 else 400.0),
                   (comp, "R2", 1000.0, 50.0 + (k % 2))]
        if k >= 6:
            linhas.append((comp, "R3", 1000.0, 10.0))
    spark.createDataFrame(linhas, "competencia date, regra_principal string, vl_cobrado double, vl_glosado double") \
        .createOrReplaceTempView("gold__fato_item_auditado")
    rows = {r["recorte"]: r for r in (x.asDict() for x in spark.sql(
        gerar.select_status(_so(c, "S03"), "local", {"gold.fato_item_auditado"})).collect())}
    assert rows["regra_principal=R1"]["status"] == "ALERTA" and rows["regra_principal=R1"]["valor"] == pytest.approx(0.4)
    assert rows["regra_principal=R2"]["status"] == "OK" and rows["regra_principal=R2"]["n_historico"] == 6
    assert rows["regra_principal=R3"]["status"] == "CALIBRANDO"


def test_invariante_violado_bloqueia_o_portao(c, spark):
    spark.createDataFrame([("i1", "c1"), ("i1", "c1"), ("i9", "c9")], "id_item string, id_conta string") \
        .createOrReplaceTempView("gold__fato_apontamento")
    spark.createDataFrame([("i1", "c1")], "id_item string, id_conta string").createOrReplaceTempView("gold__fato_item_auditado")
    rows = [r.asDict() for r in spark.sql(gerar.select_status(_so(c, "S19", "S21", "S09"), "local",
                                                              {"gold.fato_apontamento", "gold.fato_item_auditado"})).collect()]
    st = {r["id_indicador"]: r for r in rows}
    assert st["S19"]["status"] == "ALERTA" and st["S19"]["valor"] == 1        # i1 com 2 glosas
    assert st["S21"]["status"] == "ALERTA" and st["S21"]["valor"] == 1        # i9 órfão
    assert st["S09"]["status"] == "SEM_FONTE"                                 # sem fonte não some do painel
    p = avaliar_portao(rows)
    assert not p["liberado"] and {b["id_indicador"] for b in p["bloqueios"]} == {"S19", "S21"}
    assert p["criticos_sem_medicao"] == ["S09"]


def test_avaliacao_local_com_dados_reais(c, spark):
    """O painel inteiro sobre o sinistro real, a planilha do funil, o run demo da F3 e o gabarito (rodada 0)."""
    from medalhao.local import executar, liberar
    from sanidade import local

    out = executar(spark, str(gerar.RAIZ / "arvo.case" / "sinistro-hospital-saorafael.csv"), planilha=str(local.PLANILHA), run_id="t-f9")
    try:
        rows = local.avaliar(spark, local.registrar(spark, out), c)
    finally:
        liberar(out)
    por = {}
    for r in rows:
        por.setdefault(r["id_indicador"], []).append(r)
    um = lambda i: por[i][0]  # noqa: E731
    assert {i["id"] for i in c["spec"]["indicadores"]} == set(por)          # todo indicador aparece
    assert um("S01")["status"] == "ALERTA" and um("S01")["valor"] == pytest.approx(0.0048, abs=1e-4)   # 0,48% vs meta 2%
    assert um("S12")["status"] == "ALERTA" and um("S12")["valor"] == pytest.approx(0.3037, abs=1e-3)   # perda de registro
    for inv in ("S18", "S19", "S20", "S21", "S24", "S25", "S26"):
        assert all(r["status"] == "OK" for r in por[inv]), inv
    assert um("S22")["status"] == "OK" and um("S22")["valor"] == 1.0
    assert {r["status"] for r in por["S06"]} == {"ALERTA"}                  # nenhuma regra no piso: coerente com a F8
    assert {r["status"] for r in por["S03"]} == {"CALIBRANDO"}               # 1 competência: banda sem histórico
    assert {um(i)["status"] for i in ("S08", "S09")} == {"SEM_FONTE"}
    assert {r["status"] for i in ("S30", "S33", "S35") for r in por[i]} <= {"SEM_DADO", "SEM_FONTE"}  # sem IA simulada
    assert avaliar_portao(rows)["liberado"]
