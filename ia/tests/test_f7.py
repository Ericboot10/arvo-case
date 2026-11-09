"""Testes da F7 (camada de IA independente de provedor). Rodar a partir de Arvo_Case:  pytest ia/tests -v
Nenhum teste chama provedor real.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

import arvo_contrato.juiz  # noqa: F401  (registra o schema do juiz)
import arvo_contrato.schema  # noqa: F401  (registra o schema da extração)
from arvo_contrato.pipeline import carregar_config, construir_adapter
from ia import capacidades, esquemas, indicadores, prompts
from ia.adapters.replay_adapter import ReplayAdapter
from ia.avaliacao import golden
from ia.ports import LLMParams, LLMRequest
from ia.roteador import Orcamento, Roteador, carregar_politica, permitido
from ia.tarefas import sugerir_conceito as sc

RAIZ = Path(__file__).resolve().parents[2]
FIX = RAIZ / "ia" / "fixtures" / "replay_sugerir_conceito.json"


class Sink:
    def __init__(self):
        self.r = []

    def gravar(self, x):
        self.r.append(x)


def _req(classe="contratual", schema=None):
    return LLMRequest(task_id="t", system="s", user="u", schema_id="qualquer", schema_version="1",
                      schema=schema or {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
                      prompt_id="p", prompt_version="1", params=LLMParams(max_output_tokens=10), run_id="r",
                      documento_sha256="d", classe_dados=classe)


# ============================================================== arquitetura da camada
def test_nenhum_sdk_de_provedor_fora_de_ia_adapters():
    for arq in RAIZ.rglob("*.py"):
        partes = arq.relative_to(RAIZ).parts
        if partes[:2] == ("ia", "adapters") or "tests" in partes or partes[0].startswith("."):
            continue
        txt = arq.read_text("utf-8", errors="ignore")
        assert not re.search(r"^\s*(import|from)\s+(anthropic|openai|google\.genai|google\.generativeai)\b", txt, re.M), arq


def test_schemas_das_tarefas_registrados():
    reg = set(esquemas.registrados())
    assert {("extracao_contrato", "1.0.0"), ("veredito_campo", "1.0.0"), ("sugestao_conceito", "1.0.0")} <= reg


# ============================================================== política de dados (LGPD)
def test_politica_de_dados():
    pol = carregar_politica()
    for perim in ("local", "plataforma", "externo"):
        assert not permitido(pol, "identificavel", perim)                 # nunca, em perímetro nenhum
    assert permitido(pol, "catalogo", "externo") and permitido(pol, "contratual", "externo")
    assert not permitido(pol, "pseudonimizado", "externo") and permitido(pol, "pseudonimizado", "plataforma")


def test_roteador_bloqueia_antes_de_chamar_e_cai_no_permitido():
    externo = ReplayAdapter("ext", {}, familia="f1", perimetro="externo")
    local = ReplayAdapter("loc", {}, familia="f2", perimetro="local")
    sink = Sink()
    res, usado = Roteador(sink, Orcamento(10**6, 10)).gerar(_req("pseudonimizado"), [externo, local])
    assert usado is local and externo.chamadas == 0 and res.ok
    assert sink.r[0].stop_normalizado == "BLOQUEADO_POLITICA_DADOS" and sink.r[1].fallback_de == "ext"
    sink2 = Sink()
    res, usado = Roteador(sink2, Orcamento(10**6, 10)).gerar(_req("identificavel"), [externo, local])
    assert usado is None and local.chamadas == 1 and all(r.stop_normalizado == "BLOQUEADO_POLITICA_DADOS" for r in sink2.r)


def test_circuit_breaker_abre_apos_falhas_consecutivas_e_fecha_no_sucesso():
    ruim = ReplayAdapter("ruim", {}, familia="f1", falha="excecao")
    bom = ReplayAdapter("bom", {}, familia="f2")
    rot = Roteador(Sink(), Orcamento(10**6, 100), limite_falhas_consecutivas=3)
    for _ in range(3):
        rot.gerar(_req(), [ruim, bom])
    assert ruim.chamadas == 3
    rot.gerar(_req(), [ruim, bom])
    assert ruim.chamadas == 3 and rot.sink.r[-2].stop_normalizado == "BLOQUEADO_CIRCUITO"
    rot.falhas_consecutivas["ruim"] = 0
    ruim.falha = None
    res, usado = rot.gerar(_req(), [ruim, bom])
    assert usado is ruim and rot.falhas_consecutivas["ruim"] == 0


def test_telemetria_registra_classe_e_perimetro():
    sink = Sink()
    Roteador(sink, Orcamento(10**6, 10)).gerar(_req("catalogo"), [ReplayAdapter("x", {}, familia="f")])
    assert sink.r[0].classe_dados == "catalogo" and sink.r[0].perimetro == "local"


# ============================================================== capacidades × schema
def test_schemas_das_tarefas_aceitos_por_todos_os_provedores_das_cadeias():
    cfg = carregar_config()
    cadeias = {n for slot in cfg["modos"]["real"].values() for n in slot}
    provs = sorted({p for n in cadeias for p in capacidades.provedores_do_adapter(construir_adapter(n, cfg["adapters"][n]))})
    from arvo_contrato.juiz import JUIZ_SCHEMA
    from arvo_contrato.schema import SCHEMA
    for nome, s in [("extracao", SCHEMA), ("juiz", JUIZ_SCHEMA), ("sugestao", sc.SCHEMA)]:
        assert capacidades.lint(s, provs) == [], nome
    assert {"anthropic", "openai", "google", "databricks_gateway"} <= set(provs)


def test_linter_pega_palavras_rejeitadas_e_ignoradas():
    ruim = {"type": "object", "properties": {"a": {"type": "string", "minLength": 3, "pattern": "^x"}, "b": {"type": "string"}},
            "required": ["a"]}
    p = " | ".join(capacidades.lint(ruim, ["anthropic", "openai", "google", "databricks_gateway"]))
    assert "anthropic" in p and "minLength" in p and "rejeitado" in p
    assert "google" in p and "IGNORADO" in p
    assert "databricks_gateway" in p and "pattern" in p
    assert "additionalProperties" in p and "required" in p


# ============================================================== golden set de aceite
@pytest.fixture(scope="module")
def aceite():
    return golden.avaliar("simulado")


def test_golden_deterministico_aprovado_em_todas_as_variantes(aceite):
    d = aceite["candidatos"]["deterministico"]
    assert d["_aprovado_em_todas"], {k: v for k, v in d.items() if not k.startswith("_") and not v["aprovado"]}
    assert len([k for k in d if not k.startswith("_")]) == 7


def test_golden_g7_nao_e_atendido_sem_provedor_real(aceite):
    assert aceite["gate_G7_independencia"] == {"provedores_aprovados": [], "atende": False}
    assert aceite["candidatos"]["replay_fiel"]["v0_original"]["aprovado"]


def test_golden_reprova_extrator_com_erro():
    casos = golden.casos()
    doc, esp = casos["v0_original"]
    erro = json.loads((RAIZ / "arvo_contrato" / "fixtures" / "replay_com_erro.json").read_text("utf-8"))
    p = golden.pontuar(erro, esp, doc)
    assert not p["aprovado"] and "anexo_i.31001012.valor_teto" in p["errados"]
    assert "regra.5.1.tipo" in p["inventados"] and "anexo_ii.30715016.taxa_sala_codigo" in p["faltantes"]


# ============================================================== indicadores de sanidade
def _rec(**kw):
    base = {"task_id": "t", "adapter": "a", "provedor": "p", "modelo_pedido": "m", "modelo_servido": "m",
            "stop_normalizado": "COMPLETO", "schema_valido": True, "cache_hit_local": False, "fallback_de": None,
            "params_ignorados": {}, "latencia_ms": 100.0, "input_tokens": 10, "output_tokens": 5,
            "cache_read_tokens": 0, "reasoning_tokens": 0, "custo_estimado_usd": 0.001}
    return {**base, **kw}


def test_indicadores_e_alertas():
    regs = [_rec() for _ in range(8)] + [_rec(stop_normalizado="TRUNCADO", schema_valido=False),
                                         _rec(stop_normalizado="BLOQUEADO_POLITICA_DADOS", schema_valido=False),
                                         _rec(modelo_servido="m-fallback", params_ignorados={"temperature": "x"})]
    ind = indicadores.calcular(regs)[0]
    assert ind["chamadas"] == 11 and ind["chamadas_efetivas"] == 10
    assert ind["taxa_truncamento"] == pytest.approx(0.1) and ind["taxa_schema_valido"] == pytest.approx(0.9)
    assert ind["drift_modelo"] and ind["pct_param_ignorado"] == pytest.approx(0.1)
    nomes = {a["indicador"] for a in indicadores.alertas([ind])}
    assert {"taxa_schema_valido", "taxa_truncamento", "taxa_bloqueio_politica", "drift_modelo"} <= nomes


def test_view_sql_tem_os_mesmos_indicadores_do_python():
    sql = (RAIZ / "ia" / "databricks" / "v_ia_sanidade.sql").read_text("utf-8")
    ind = indicadores.calcular([_rec()])[0]
    for k in ind:
        if k.startswith(("taxa_", "latencia_", "pct_")) or k in ("drift_modelo", "custo_estimado_usd", "chamadas_efetivas"):
            assert f"AS {k}" in sql, k


# ============================================================== governança de prompts
def test_prompts_versionados_e_travados():
    assert prompts.verificar() == []
    assert {p["prompt_id"] for p in prompts.inventario()} == {"extracao_contrato", "juiz_extracao", "sugerir_conceito"}


def test_mudanca_silenciosa_de_prompt_e_detectada(tmp_path, monkeypatch):
    pasta = tmp_path / "prompts"
    shutil.copytree(RAIZ / "ia" / "prompts", pasta)
    lock = tmp_path / "lock.json"
    shutil.copy(prompts.LOCK, lock)
    monkeypatch.setattr(prompts, "PASTAS", [pasta])
    monkeypatch.setattr(prompts, "LOCK", lock)
    monkeypatch.setattr(prompts, "RAIZ", tmp_path)
    arq = pasta / "sugerir_conceito_v1.md"
    arq.write_text(arq.read_text("utf-8").replace("Não crie conceitos.", "Pode criar conceitos."), "utf-8")
    assert any("mudou sem nova versão" in p for p in prompts.verificar())
    with pytest.raises(SystemExit):
        prompts.travar()


# ============================================================== tarefa 2: sugestão de conceito
ITENS = [("70520099", "Fio de sutura agulhado 4-0"), ("40304399", "Dosagem de glicose")]


def test_sugestao_resposta_fora_do_dominio_e_descartada_e_cai_no_deterministico():
    sink = Sink()
    llm = ReplayAdapter("llm_pequeno", FIX, familia="f1", perimetro="externo")
    out = sc.sugerir(ITENS, Roteador(sink, Orcamento(10**6, 10)), [llm], "t")
    assert all(s["origem"] == "deterministico" for s in out)               # enum inválido → resposta inteira rejeitada
    assert sink.r[0].schema_valido is False and any("CODIGO_INEXISTENTE" in e for e in sink.r[0].erros_schema)
    assert all(s["status"] == "PENDENTE_ESPECIALISTA" for s in out)


def test_sugestao_valida_usa_llm_e_prioriza_discordancia():
    dados = json.loads(FIX.read_text("utf-8"))
    dados["sugestoes"] = [s for s in dados["sugestoes"] if s["conceito"] != "CODIGO_INEXISTENTE"]
    llm = ReplayAdapter("llm_pequeno", dados, familia="f1", perimetro="externo")
    sink = Sink()
    out = {s["cod_tuss"]: s for s in sc.sugerir(ITENS, Roteador(sink, Orcamento(10**6, 10)), [llm], "t")}
    assert out["70520099"]["origem"] == "llm:llm_pequeno" and out["70520099"]["concorda_com_deterministico"]
    assert out["40304399"]["conceito"] == "SADT_LABORATORIO" and not out["40304399"]["concorda_com_deterministico"]
    assert out["40304399"]["prioridade_revisao"] == "ALTA"                  # LLM × determinístico discordam
    assert sink.r[0].classe_dados == "catalogo"


def test_sugestao_sem_provedor_degrada_para_deterministico():
    out = {s["cod_tuss"]: s for s in sc.sugerir(ITENS)}
    assert out["70520099"]["conceito"] == "MATERIAL_SUTURA" and out["70520099"]["confianca"] == "ALTA"
    assert out["40304399"]["confianca"] == "BAIXA" and out["40304399"]["prioridade_revisao"] == "ALTA"


def test_itens_da_quarentena_so_falta_de_conceito():
    linhas = [{"motivos": ["E03"], "linha_original": json.dumps({"cod_tuss": "70520099", "desc_item_origem": "Fio"})},
              {"motivos": ["E02", "E03"], "linha_original": json.dumps({"cod_tuss": "1234", "desc_item_origem": "x"})},
              {"motivos": ["E08"], "linha_original": json.dumps({"cod_tuss": "70520020", "desc_item_origem": "y"})}]
    assert sc.itens_da_quarentena(linhas) == [("70520099", "Fio")]
