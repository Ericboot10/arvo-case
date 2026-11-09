"""F8 no Databricks: o job, o SQL e o painel de precisão e recall existem e apontam para os arquivos certos.
A igualdade numérica com o relatório local (94,4% / 90,0%) foi conferida no workspace Free Edition em 09/11/2026."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]


def _jobs() -> dict:
    from arvo.platform.bundle import recursos
    return recursos("jobs")


def test_job_f8_aponta_para_arquivos_existentes():
    job = _jobs()["evaluation_run"]
    caminhos = [t["notebook_task"]["notebook_path"] for t in job["tasks"]]
    caminhos += [t["notebook_task"]["base_parameters"]["arquivo"] for t in job["tasks"]
                 if "arquivo" in t["notebook_task"].get("base_parameters", {})]
    base, executor = job["_base"], RAIZ / "src" / "arvo" / "platform" / "notebooks"
    for c in caminhos:      # notebook: relativo ao arquivo do job; 'arquivo' SQL: relativo ao notebook executor
        alvo = (base / c) if c.endswith(".py") else (executor / c)
        assert alvo.resolve().exists(), c


def test_sql_f8_cria_avaliacao_metricas_e_auditoria():
    sql = (RAIZ / "src" / "arvo" / "evaluation" / "databricks" / "f8_avaliacao.sql").read_text("utf-8")
    for obj in ("gold.v_avaliacao_gabarito", "ops.v_precisao_recall", "gold.fato_auditoria_amostral"):
        assert re.search(rf"CREATE OR REPLACE (VIEW|TABLE) {re.escape(obj)}\b", sql), obj
    assert "1.959963984540054" in sql          # mesmo z da avaliação local (metricas.Z95)


def test_painel_tem_pagina_de_precisao_e_recall():
    painel = json.loads((RAIZ / "src" / "arvo" / "monitoring" / "dashboard" / "painel_sanidade.lvdash.json").read_text("utf-8"))
    paginas = {p["name"] for p in painel["pages"]}
    assert "precisao_recall" in paginas
    sql = {d["name"]: "".join(d["queryLines"]) for d in painel["datasets"]}
    assert "ops.v_precisao_recall" in sql["ds_pr_total"]
    assert "gold.v_avaliacao_gabarito" in sql["ds_pr_matriz"]


def test_alvo_free_so_tem_dados_do_case():
    cfg = yaml.safe_load((RAIZ / "databricks.yml").read_text("utf-8"))
    free = cfg["targets"]["free"]
    assert free["variables"]["modo_ia"] == "real"          # sem chave, a F3 não roda: nada de telemetria simulada
    tarefas = free["resources"]["jobs"]["platform_setup"]["tasks"]
    assert not any("sintetic" in json.dumps(t) for t in tarefas)
    assert "platform_synthetic_data" not in _jobs()           # o gerador sintético só existe no alvo dev
    assert "platform_synthetic_data" in cfg["targets"]["dev"]["resources"]["jobs"]
