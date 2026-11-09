"""Testes da plataforma (F4), estáticos e locais. Rodar a partir de Arvo_Case:  pytest plataforma/tests -v

Eles NÃO substituem o `databricks bundle validate` nem o job `plataforma_hello`, que exigem um workspace.
Pegam antes do deploy o que dá para pegar sem workspace: caminhos quebrados, ambiente sem isolamento,
privilégio excessivo, dado real indo para o workspace, gerador sintético inconsistente.
"""
from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

import pandas as pd
import pytest
import yaml

from plataforma.sinteticos.gerar_sinistro_sintetico import COLUNAS, Gerador
from plataforma.sqlutil import dividir_sql

RAIZ = Path(__file__).resolve().parents[2]
SQL = RAIZ / "plataforma" / "sql"
CATALOGOS = {"dev": "arvo_dev", "stg": "arvo_stg", "prod": "arvo_prod"}
BASE = {"bronze", "silver", "gold", "semantic", "contracts", "ops", "quarantine"}


@pytest.fixture(scope="module")
def bundle():
    return yaml.safe_load((RAIZ / "databricks.yml").read_text("utf-8"))


@pytest.fixture(scope="module")
def jobs():
    return yaml.safe_load((RAIZ / "resources" / "jobs.yml").read_text("utf-8"))["resources"]["jobs"]


# ============================================================== bundle
def test_targets_e_modos(bundle):
    t = bundle["targets"]
    assert set(t) == {"dev", "free", "stg", "prod"}
    assert t["free"]["mode"] == "development" and t["free"]["variables"]["catalog"] == "arvo_dev"   # Free Edition: só dev
    assert t["dev"]["mode"] == "development" and t["dev"].get("default") is True
    for alvo in ("stg", "prod"):
        assert t[alvo]["mode"] == "production"
        assert "service_principal_name" in t[alvo]["run_as"], "stg/prod rodam como service principal"
        assert t[alvo]["git"]["branch"] == "main"
        assert t[alvo]["workspace"]["root_path"].startswith("/Workspace/Shared/")
    for alvo, cat in CATALOGOS.items():
        assert t[alvo]["variables"]["catalog"] == cat
    assert t["prod"]["workspace"]["host"] != t["stg"]["workspace"]["host"], "prod em workspace próprio"


def test_dados_do_case_nao_sobem_para_o_workspace(bundle):
    excl = bundle["sync"]["exclude"]
    sensiveis = ["arvo.case/sinistro-hospital-saorafael.csv", "arvo.case/gabarito-auditoria.csv",
                 "arvo.case/Inteligencias_apos_6_meses.xlsx", "arvo.case/Contrato-parthenon-x-hospital-sao-rafael.pdf",
                 "dados_sinteticos/sinistro_sintetico.csv",
                 "contratos/runs/PRT-2025-0417/x/extracao_A.json"]
    for arq in sensiveis:
        assert any(fnmatch.fnmatch(arq, p) for p in excl), f"{arq} seria sincronizado"


def test_caminhos_dos_jobs_existem(jobs):
    base = RAIZ / "resources"
    for nome, job in jobs.items():
        for t in job["tasks"]:
            nb = (base / t["notebook_task"]["notebook_path"]).resolve()
            assert nb.exists(), f"{nome}.{t['task_key']}: {nb}"
            assert nb.read_text("utf-8").startswith("# Databricks notebook source"), nb
            arq = t["notebook_task"].get("base_parameters", {}).get("arquivo")
            if arq:  # relativo ao notebook executor
                assert (nb.parent / arq).resolve().exists(), f"{nome}: SQL {arq} não existe"


def test_jobs_parametrizados_pelo_catalogo_do_alvo(jobs):
    for nome, job in jobs.items():
        for t in job["tasks"]:
            assert t["notebook_task"]["base_parameters"]["catalog"] == "${var.catalog}", nome


# ============================================================== catálogos, schemas, volumes
def _schemas(sql: str) -> dict[str, set]:
    out: dict[str, set] = {}
    for cat, sch in re.findall(r"CREATE SCHEMA IF NOT EXISTS (\w+)\.(\w+)", sql):
        out.setdefault(cat, set()).add(sch)
    return out


def test_medalhao_completo_por_ambiente():
    s = _schemas((SQL / "00_catalogos_schemas.sql").read_text("utf-8"))
    assert s["arvo_dev"] == BASE | {"sandbox"}
    assert s["arvo_stg"] == BASE
    assert s["arvo_prod"] == BASE | {"gold_shadow"}


def test_volumes_usados_pelos_notebooks_existem():
    sql = (SQL / "00_catalogos_schemas.sql").read_text("utf-8")
    vols = set(re.findall(r"CREATE VOLUME IF NOT EXISTS (\w+\.\w+\.\w+)", sql))
    for cat in CATALOGOS.values():
        assert {f"{cat}.contracts.raw", f"{cat}.contracts.revisao", f"{cat}.bronze.landing"} <= vols


# ============================================================== permissões
def _grants(sql: str):
    sql = re.sub(r"--.*", "", sql)
    for privs, objeto, quem in re.findall(r"GRANT\s+(.+?)\s+ON\s+(.+?)\s+TO\s+`([^`]+)`", sql, flags=re.S):
        yield [p.strip() for p in privs.replace("\n", " ").split(",")], " ".join(objeto.split()), quem


def test_sem_all_privileges_e_escrita_em_stg_prod_so_por_sp():
    sql = (SQL / "01_grants.sql").read_text("utf-8")
    assert "ALL PRIVILEGES" not in re.sub(r"--.*", "", sql)
    grupos_validos = set(re.findall(r"arvo-[\w-]+|sp-arvo-\w+", sql.split("Regras")[0])) | {"account users"}
    for privs, obj, quem in _grants(sql):
        assert quem in grupos_validos, f"grantee não declarado: {quem}"
        if "arvo_stg" in obj or "arvo_prod" in obj:
            if "MODIFY" in privs or "CREATE TABLE" in privs:
                assert quem.startswith("sp-arvo-"), f"{quem} escreve em {obj}"
            if "WRITE VOLUME" in privs and not quem.startswith("sp-arvo-"):
                assert obj == "VOLUME arvo_prod.contracts.revisao" and quem == "arvo-juridico", (quem, obj)
        if "arvo_prod" in obj:
            assert not quem.startswith("sp-arvo-stg"), "SP de stg não acessa prod"


def test_negocio_nao_le_camadas_com_identificador():
    for privs, obj, quem in _grants((SQL / "01_grants.sql").read_text("utf-8")):
        if quem in ("arvo-negocio-leitura", "arvo-engenharia") and "arvo_prod" in obj:
            assert not any(s in obj for s in ("bronze", "silver")), (quem, obj)


# ============================================================== LGPD
def test_lgpd_colunas_sensiveis_coerentes_com_semantica_e_schemas():
    lg = yaml.safe_load((RAIZ / "plataforma" / "lgpd" / "colunas_sensiveis.yaml").read_text("utf-8"))
    met = yaml.safe_load((RAIZ / "semantic" / "metricas.yaml").read_text("utf-8"))
    for tabela in met["tabelas_base"].values():
        assert "id_beneficiario" not in tabela["colunas"], "gold não pode ter o identificador em claro"
    sch = _schemas((SQL / "00_catalogos_schemas.sql").read_text("utf-8"))["arvo_prod"]
    for c in lg["colunas_mascaradas"]:
        assert c["tabela"].split(".")[0] in sch
    assert "mask_id_pessoa" in (SQL / "02_mascaras_lgpd.sql").read_text("utf-8")


# ============================================================== executor SQL
def test_divisor_sql_respeita_dolar_e_comentarios():
    mv = dividir_sql((RAIZ / "semantic" / "databricks" / "02_metric_views.sql").read_text("utf-8"))
    tabs = yaml.safe_load((RAIZ / "arquitetura" / "modelo.yaml").read_text("utf-8"))["tabelas"]
    # só as views com fonte implementada são executáveis; as demais ficam comentadas (PENDENTE) no arquivo
    n_views = sum(1 for t in tabs.values() if t["tipo"] == "metric_view" and tabs[t["origem"][0]]["status"] == "implementado")
    assert n_views >= 3 and len(mv) == 2 + n_views and sum(c.startswith("CREATE OR REPLACE VIEW") for c in mv) == n_views
    assert all("$$" not in c or c.count("$$") == 2 for c in mv)
    f3 = dividir_sql((RAIZ / "arvo_contrato" / "databricks" / "f3_tabelas.sql").read_text("utf-8"))
    assert sum(c.startswith("CREATE TABLE") for c in f3) == 4
    assert dividir_sql("SELECT 'a;b'; -- x; y\nSELECT 2;") == ["SELECT 'a;b'", "SELECT 2"]


# ============================================================== CI/CD
def test_ci_testa_antes_de_deploy_e_prod_exige_aprovacao():
    ci = yaml.safe_load((RAIZ / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    j = ci["jobs"]
    assert j["validar_bundle"]["needs"] == "testes" and j["deploy_stg"]["needs"] == "validar_bundle"
    assert j["deploy_prod"]["needs"] == "deploy_stg" and j["deploy_prod"]["environment"] == "prod"
    assert ci["permissions"]["id-token"] == "write"
    txt = (RAIZ / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    assert "DATABRICKS_TOKEN" not in txt, "usar OIDC (workload identity federation), não token"


# ============================================================== dados sintéticos
@pytest.fixture(scope="module")
def sint(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("sint")
    g = Gerador(semente=7, n_contas=300, ano=2025, mes=6)
    g.gerar()
    man = g.gravar(pasta)
    s = pd.read_csv(pasta / "sinistro_sintetico.csv", dtype=str, encoding="utf-8-sig")
    gab = pd.read_csv(pasta / "gabarito_sintetico.csv", dtype=str, encoding="utf-8-sig", keep_default_na=False)
    return s, gab, man, pasta


def test_sintetico_reprodutivel(tmp_path):
    shas = []
    for i in range(2):
        g = Gerador(semente=7, n_contas=50, ano=2025, mes=6)
        g.gerar()
        shas.append(g.gravar(tmp_path / str(i))["sha256"])
    assert shas[0] == shas[1]


def test_sintetico_tem_formato_do_real_e_ids_que_nao_colidem(sint):
    s, *_ = sint
    real = pd.read_csv(RAIZ / "arvo.case" / "sinistro-hospital-saorafael.csv", dtype=str, encoding="utf-8-sig")
    assert list(s.columns) == list(real.columns) == COLUNAS
    assert not set(s.id_beneficiario) & set(real.id_beneficiario)
    assert s.id_beneficiario.str.startswith("SB").all() and s.id_item.str.startswith("SX").all()
    assert s.dt_atendimento.str.fullmatch(r"\d{1,2} de junho de 2025").all()
    assert s.vl_unitario.str.fullmatch(r"\d+(,\d{1,2})?").all()


def test_sintetico_aderente_a_semantica_exceto_erros_injetados(sint):
    s, gab, *_ = sint
    mapa = {m["codigo"] for m in yaml.safe_load((RAIZ / "semantic" / "map_tuss_conceito.yaml").read_text())["codigos"]}
    dom = yaml.safe_load((RAIZ / "semantic" / "dominios.yaml").read_text())["dominios"]
    carateres = {m["valor_origem"] for m in dom["carater_atendimento"]["mapeamento_origem"]}
    regimes = {m["valor_origem"] for m in dom["regime_atendimento"]["mapeamento_origem"]}
    assert set(s.tipo_conta) <= regimes
    fora_cod = set(s.loc[~s.cod_tuss.isin(mapa), "id_item"])
    fora_car = set(s.loc[~s.carater_atendimento.isin(carateres), "id_item"])
    dq = gab[gab.erro_dq != ""]
    assert fora_cod <= set(dq[dq.erro_dq == "dq_codigo_invalido"].id_item)
    assert fora_car <= set(dq[dq.erro_dq == "dq_carater_desconhecido"].id_item)


def test_rotulos_sinteticos_conferem_com_aplicacao_independente_do_contrato(sint):
    """Consistência: o rótulo POR CONSTRUÇÃO bate com uma aplicação independente e literal das cláusulas."""
    s, gab, man, _ = sint
    v = yaml.safe_load((RAIZ / "semantic" / "vinculos" / "PRT-2025-0417.yaml").read_text("utf-8"))
    teto = {i["codigo"]: i["teto"] for i in v["itens_com_preco_pactuado"]}
    pac = {p["codigo"]: p["taxa_sala_inclusa"] for p in v["pacotes"]["procedimentos"]}
    rot_mat = set(v["pacotes"]["itens_inclusos_comuns"])
    df = s.merge(gab[["id_item", "rotulo", "erro_dq"]], on="id_item", how="left")
    df = df[(df.erro_dq.fillna("") == "") & ~df.id_item.duplicated(keep=False)]
    num = lambda x: float(x.replace(",", "."))
    contas = df.groupby("id_conta").cod_tuss.apply(set)
    for _, r in df.iterrows():
        cods = contas[r.id_conta]
        pk = [p for p in pac if p in cods]
        esperado = "nenhum"
        if r.cod_tuss == "99999001" and r.carater_atendimento == "Eletivo":
            esperado = "R4"
        elif pk and (r.cod_tuss in rot_mat):
            esperado = "R3"
        elif pk and r.cod_tuss in {pac[p] for p in pk}:
            esperado = "R2"
        elif num(r.vl_unitario) > teto[r.cod_tuss] + 1e-9:
            esperado = "R1"
        obtido = {"R1_preco_acima_teto": "R1", "R2_sala_em_pacote": "R2", "R3_material_em_pacote": "R3",
                  "R4_urgencia_em_eletivo": "R4", "borda_AMB01_ps_eletivo_com_taxa": "R4"}.get(r.rotulo, "nenhum")
        assert esperado == obtido, (r.id_item, r.rotulo, esperado)


def test_manifesto_bate_com_gabarito(sint):
    _, gab, man, _ = sint
    for rotulo, n in man["contagens"].items():
        if rotulo.startswith("dq_"):
            assert (gab.erro_dq == rotulo).sum() == n
        else:
            assert (gab.rotulo == rotulo).sum() == n
    total = gab.loc[gab.indevido_por_contrato == "True", "vl_glosa_esperado"].astype(float).sum()
    assert round(total, 2) == man["vl_glosa_esperado_total"]
