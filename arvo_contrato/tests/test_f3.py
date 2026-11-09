"""Testes da F3 (contrato como dado). Rodar a partir de Arvo_Case:  pytest arvo_contrato/tests -v

Nenhum teste chama provedor real. Os adapters reais são testados na montagem da requisição e na leitura da
resposta (objetos falsos no formato documentado). O fluxo completo roda com adapters simulados.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
import yaml

from ia.adapters.anthropic_adapter import AnthropicAdapter
from ia.adapters.openai_adapters import OpenAICompatChatAdapter, OpenAIResponsesAdapter
from ia.adapters.replay_adapter import ReplayAdapter
from arvo_contrato.estado import EstadoExtracao, TransicaoInvalida
from arvo_contrato.extratores import deterministico
from arvo_contrato.extratores.llm import carregar_prompt, montar_requisicao
from arvo_contrato.grounding import Corpus, verificar
from arvo_contrato.parsing import PdfPlumberParser
from arvo_contrato.pipeline import carregar_config, executar
from ia.ports import LLMParams
from arvo_contrato.reconciliacao import (CONSENSO_SEM_EVIDENCIA, CONSENSO_VERIFICADO, DIVERGENTE, INCOMPLETO,
                                         reconciliar)
from arvo_contrato.revisao import aprovar
from ia.roteador import CacheRespostas, Orcamento, Roteador
from arvo_contrato.sanidade import checar
from arvo_contrato.schema import validar
from ia.telemetria import CAMPOS_OBRIGATORIOS, STOP_RECUSA, STOP_TRUNCADO, chave_cache

RAIZ = Path(__file__).resolve().parents[2]
PDF = RAIZ / "arvo.case" / "Contrato-parthenon-x-hospital-sao-rafael.pdf"
FIX = RAIZ / "arvo_contrato" / "fixtures"


@pytest.fixture(scope="module")
def doc():
    return PdfPlumberParser().parse(PDF)


@pytest.fixture(scope="module")
def d(doc):
    return deterministico.extrair(doc)


@pytest.fixture(scope="module")
def corpus(doc):
    return Corpus(doc)


@pytest.fixture(scope="module")
def fiel():
    return json.loads((FIX / "replay_fiel.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def com_erro():
    return json.loads((FIX / "replay_com_erro.json").read_text("utf-8"))


class Sink:
    def __init__(self):
        self.registros = []

    def gravar(self, r):
        self.registros.append(r)


def _req(doc, task="extracao_A", params=None):
    return montar_requisicao(doc, carregar_prompt("extracao_contrato_v1.md"), params or LLMParams(), "run-teste", task)


# ============================================================== parser e extrator determinístico
def test_parser_remove_rodape_e_reune_clausula_que_cruza_pagina(doc):
    assert doc.artefatos["rodapes_removidos"] >= 4 and doc.artefatos["nul_chars"] > 0
    c22 = doc.clausulas["2.2"]
    assert c22.endswith("multiplicada pela quantidade do item.")           # começou na pág. 1, terminou na 2
    assert "contrato-parthenon-x-hospital-sao-rafael" not in c22
    assert {"2.2", "2.3", "3.2", "3.3", "3.4", "4.1", "4.2"} <= set(doc.clausulas)


def test_deterministico_valido_e_100pct_verificado(d, corpus):
    assert validar(d) == []
    ev = verificar(d, corpus)
    assert ev and all(v["quote_ok"] and v["valor_ok"] for v in ev.values())


def test_deterministico_concorda_com_transcricao_manual_da_F2(d):
    """Dois métodos independentes (transcrição humana da F2 x parser) precisam concordar 100%."""
    v = yaml.safe_load((RAIZ / "semantic" / "vinculos" / "PRT-2025-0417.yaml").read_text("utf-8"))
    assert {i["codigo"]: i["valor_teto"] for i in d["anexo_i"]} == \
           {i["codigo"]: i["teto"] for i in v["itens_com_preco_pactuado"]}
    assert {p["codigo_procedimento"]: p["taxa_sala_codigo"] for p in d["anexo_ii"]} == \
           {p["codigo"]: p["taxa_sala_inclusa"] for p in v["pacotes"]["procedimentos"]}
    assert all(sorted(p["materiais_rotina"]) == sorted(v["pacotes"]["itens_inclusos_comuns"]) for p in d["anexo_ii"])
    assert [(t["codigo"], t["carater_permitido"]) for t in d["taxas_condicionadas"]] == \
           [(t["codigo"], t["carater_permitido"]) for t in v["taxas_condicionadas_ao_carater"]]
    assert d["contrato"]["vigencia_inicio"] == v["vigencia"]["inicio"] and d["contrato"]["vigencia_meses"] == 24


def test_deterministico_e_reprodutivel(doc):
    assert deterministico.extrair(doc) == deterministico.extrair(PdfPlumberParser().parse(PDF))


# ============================================================== schema e grounding
def test_schema_rejeita_campo_extra_ausente_codigo_e_enum(fiel):
    x = copy.deepcopy(fiel)
    x["contrato"]["extra"] = 1
    del x["anexo_i"][0]["quote"]
    x["anexo_i"][1]["codigo"] = "123"
    x["regras"][0]["tipo"] = "INVENTADO"
    erros = " | ".join(validar(x))
    for trecho in ("campo não previsto", "quote: ausente", "fora do domínio"):
        assert trecho in erros
    y = copy.deepcopy(fiel)
    y["anexo_i"][1]["codigo"] = "123"
    assert any("8 dígitos" in e for e in validar(y))


def test_schema_usa_so_o_subconjunto_comum_entre_provedores():
    proibidas = {"pattern", "minimum", "maximum", "minLength", "maxLength", "oneOf", "anyOf", "allOf", "$ref",
                 "format", "minItems", "maxItems"}
    from arvo_contrato.schema import SCHEMA

    def chaves(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from chaves(v)
        elif isinstance(o, list):
            for v in o:
                yield from chaves(v)

    assert not (set(chaves(SCHEMA)) & proibidas)


def test_grounding_aceita_citacao_legitima_com_outra_grafia(fiel, corpus):
    ev = verificar(fiel, corpus)
    assert all(v["quote_ok"] and v["valor_ok"] for v in ev.values()), [k for k, v in ev.items() if not v["valor_ok"]]


def test_grounding_pega_citacao_inventada_e_valor_fora_da_citacao(com_erro, corpus):
    ev = verificar(com_erro, corpus)
    assert ev["regra.4.2.tipo"]["quote_ok"] is False                           # citação inventada
    assert ev["anexo_i.31001012.valor_teto"] == {"quote_ok": True, "valor_ok": False}   # 4300 x "R$ 4.200,00"
    assert ev["anexo_ii.31309062.materiais_rotina"]["valor_ok"] is False      # cateter não está na citação


# ============================================================== reconciliação
def test_reconciliacao_pega_os_5_erros_injetados(d, fiel, com_erro, corpus):
    rec = reconciliar({"D": d, "A": fiel, "B": com_erro}, {"D": "regras", "A": "f1", "B": "f2"}, corpus)
    st = {l["campo"]: l["status"] for l in rec["campos"]}
    assert st["anexo_i.31001012.valor_teto"] == DIVERGENTE                   # 1. valor alucinado
    assert st["regra.4.2.tipo"] == CONSENSO_SEM_EVIDENCIA                    # 2. citação inventada
    assert st["anexo_ii.30715016.taxa_sala_codigo"] == INCOMPLETO            # 3. item omitido
    assert st["anexo_ii.31309062.materiais_rotina"] == DIVERGENTE            # 4. item a mais
    assert st["regra.5.1.tipo"] == INCOMPLETO                                # 5. regra fora do critério
    assert st["anexo_i.40304361.valor_teto"] == CONSENSO_VERIFICADO
    assert not rec["independencia_reduzida"]


def test_reconciliacao_sinaliza_independencia_reduzida(d, fiel, corpus):
    rec = reconciliar({"D": d, "A": fiel, "B": fiel}, {"D": "regras", "A": "anthropic", "B": "anthropic"}, corpus)
    assert rec["independencia_reduzida"] is True


# ============================================================== roteador: cache, fallback, orçamento, telemetria
def test_cache_nao_mistura_adapters_com_mesmo_modelo(doc, fiel, com_erro):
    """Regressão: dois adapters com o mesmo nome de modelo NÃO podem compartilhar resposta pelo cache."""
    a = ReplayAdapter("ra", fiel, familia="f1", modelo="mesmo-modelo")
    b = ReplayAdapter("rb", com_erro, familia="f2", modelo="mesmo-modelo")
    req = _req(doc)
    assert chave_cache(req, a) != chave_cache(req, b)


def test_cache_hit_nao_chama_provedor_e_e_registrado(doc, fiel, tmp_path):
    a = ReplayAdapter("ra", fiel, familia="f1")
    sink = Sink()
    rot = Roteador(sink, Orcamento(10**6, 10), CacheRespostas(tmp_path))
    rot.gerar(_req(doc), [a])
    res, _ = rot.gerar(_req(doc), [a])
    assert res.ok and a.chamadas == 1 and sink.registros[-1].cache_hit_local is True


@pytest.mark.parametrize("falha", ["excecao", "truncado", "recusa", "json_invalido"])
def test_fallback_quando_primario_falha(doc, fiel, falha):
    ruim = ReplayAdapter("primario", fiel, familia="f1", falha=falha)
    bom = ReplayAdapter("secundario", fiel, familia="f1")
    sink = Sink()
    res, usado = Roteador(sink, Orcamento(10**6, 10)).gerar(_req(doc), [ruim, bom])
    assert res.ok and usado is bom
    assert sink.registros[0].schema_valido is False and sink.registros[1].fallback_de == "primario"


def test_orcamento_bloqueia_antes_de_chamar(doc, fiel):
    a = ReplayAdapter("ra", fiel, familia="f1")
    sink = Sink()
    res, usado = Roteador(sink, Orcamento(max_tokens_run=100, max_chamadas_run=10)).gerar(_req(doc), [a])
    assert not res.ok and usado is None and a.chamadas == 0
    assert sink.registros[0].stop_normalizado == "BLOQUEADO_ORCAMENTO"


def test_telemetria_completa_e_parametro_ignorado_registrado(doc, fiel):
    sink = Sink()
    a = ReplayAdapter("ra", fiel, familia="f1", suporta={"temperature": False})
    Roteador(sink, Orcamento(10**6, 10)).gerar(_req(doc, params=LLMParams(temperature=0.0)), [a])
    r = sink.registros[0].to_dict()
    assert all(r.get(c) not in (None, "") for c in CAMPOS_OBRIGATORIOS if c not in ("params_ignorados",))
    assert "temperature" in r["params_ignorados"] and "temperature" not in r["params_aplicados"]


# ============================================================== adapters reais (sem rede)
def test_anthropic_monta_requisicao_conforme_documentacao(doc):
    ad = AnthropicAdapter("anthropic_opus", modelo="claude-opus-5-5")
    req = _req(doc, params=LLMParams(temperature=0.0, top_p=0.9, reasoning_effort="high"))
    from ia.telemetria import novo_registro
    rec = novo_registro(req, ad)
    kw = ad.montar_requisicao(req, ad._separar_params(req, rec))
    assert "temperature" not in kw and "top_p" not in kw                      # 400 em claude-opus-5-5
    assert set(rec.params_ignorados) == {"temperature", "top_p"}
    assert kw["output_config"]["format"]["type"] == "json_schema" and kw["output_config"]["effort"] == "high"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert "output_format" not in kw and "thinking" not in kw


def test_anthropic_le_recusa_truncamento_e_uso():
    from ia.telemetria import LLMCallRecord
    uso = NS(input_tokens=100, output_tokens=50, cache_read_input_tokens=80, cache_creation_input_tokens=0)
    rec = LLMCallRecord()
    AnthropicAdapter.ler_resposta(NS(model="claude-opus-5-5", stop_reason="refusal",
                                     stop_details=NS(category="cyber"), usage=uso, content=[]), rec)
    assert rec.stop_normalizado == STOP_RECUSA and rec.stop_detalhe == "cyber" and rec.cache_read_tokens == 80
    rec2 = LLMCallRecord()
    txt = AnthropicAdapter.ler_resposta(NS(model="m", stop_reason="max_tokens", usage=uso,
                                           content=[NS(type="thinking"), NS(type="text", text="{")]), rec2)
    assert rec2.stop_normalizado == STOP_TRUNCADO and txt == "{"


def test_openai_responses_e_chat_compat_montam_e_leem(doc):
    from ia.telemetria import LLMCallRecord, novo_registro
    req = _req(doc)
    r = OpenAIResponsesAdapter("oa", modelo="modelo-x")
    kw = r.montar_requisicao(req, r._separar_params(req, novo_registro(req, r)))
    assert kw["text"]["format"]["strict"] is True and "temperature" not in kw and kw["reasoning"]["effort"] == "high"
    rec = LLMCallRecord()
    r.ler_resposta(NS(model="modelo-x", id="r1", status="incomplete", incomplete_details=NS(reason="max_output_tokens"),
                      output=[], output_text="", usage=NS(input_tokens=1, output_tokens=2,
                      input_tokens_details=NS(cached_tokens=0), output_tokens_details=NS(reasoning_tokens=2))), rec)
    assert rec.stop_normalizado == STOP_TRUNCADO and rec.reasoning_tokens == 2
    g = OpenAICompatChatAdapter("gw", modelo="endpoint-x", familia="google", base_url="http://x")
    kw = g.montar_requisicao(req, g._separar_params(req, novo_registro(req, g)))
    assert kw["response_format"]["json_schema"]["strict"] is True and kw["temperature"] == 0.0
    rec = LLMCallRecord()
    g.ler_resposta(NS(model="e", id="c1", choices=[NS(finish_reason="content_filter", message=NS(content="", refusal=None))],
                      usage=NS(prompt_tokens=1, completion_tokens=1, prompt_tokens_details=None)), rec)
    assert rec.stop_normalizado == "FILTRO_CONTEUDO"


def test_core_nao_importa_sdk_de_provedor():
    pacote = RAIZ / "arvo_contrato"
    for arq in pacote.rglob("*.py"):
        if "adapters" in arq.parts or "tests" in arq.parts:
            continue
        txt = arq.read_text("utf-8")
        assert not re.search(r"^\s*(import|from)\s+(anthropic|openai|google)", txt, re.M), arq


# ============================================================== pipeline, estado, aprovação, sanidade
def test_config_rejeita_A_e_B_da_mesma_familia(tmp_path, fiel):
    cfg = carregar_config()
    ads = {"x": ReplayAdapter("x", fiel, familia="mesma"), "y": ReplayAdapter("y", fiel, familia="mesma"),
           "j": ReplayAdapter("j", fiel, familia="outra")}
    cfg = {**cfg, "modos": {"t": {"A": ["x"], "B": ["y"], "juiz": ["j"]}}}
    with pytest.raises(ValueError, match="independência"):
        executar(PDF, tmp_path, modo="t", config=cfg, adapters=ads)


def test_maquina_de_estados_nao_pula_revisao(tmp_path):
    e = EstadoExtracao(tmp_path / "e.json", "k", "C")
    with pytest.raises(TransicaoInvalida):
        e.avancar("APROVADO")


def test_pipeline_simulado_idempotente_e_para_em_revisao(tmp_path):
    p1 = executar(PDF, tmp_path, modo="simulado")
    n1 = len((p1 / "llm_calls.jsonl").read_text().splitlines())
    p2 = executar(PDF, tmp_path, modo="simulado")
    assert p1 == p2 and json.loads((p1 / "estado.json").read_text())["estado"] == "REVISAO_HUMANA"
    assert len((p2 / "llm_calls.jsonl").read_text().splitlines()) == n1          # rerun não chamou de novo


def test_caos_provedor_A_fora_do_ar_pipeline_continua(tmp_path, fiel, com_erro):
    cfg = carregar_config()
    ads = {"a": ReplayAdapter("a", fiel, familia="f1", falha="excecao"),
           "b": ReplayAdapter("b", fiel, familia="f2"), "j": ReplayAdapter("j", {"vereditos": []}, familia="f3")}
    cfg = {**cfg, "modos": {"caos": {"A": ["a"], "B": ["b"], "juiz": ["j"]}}}
    pasta = executar(PDF, tmp_path, modo="caos", config=cfg, adapters=ads)
    rec = json.loads((pasta / "reconciliacao.json").read_text())
    assert rec["fontes"] == ["D", "B"] and "A" in rec["falhas_extratores"]
    assert rec["resumo"]["CONSENSO_VERIFICADO"] == rec["n_campos"]          # D e B concordam: degradação graciosa


def _carregar_run(pasta):
    rec = json.loads((pasta / "reconciliacao.json").read_text("utf-8"))
    for l in rec["campos"]:
        if isinstance(l.get("valor_proposto"), list):
            l["valor_proposto"] = tuple(l["valor_proposto"])
    ext = {p.stem.split("_")[1]: json.loads(p.read_text("utf-8")) for p in pasta.glob("extracao_*.json")}
    est = json.loads((pasta / "estado.json").read_text("utf-8"))
    return rec, ext, EstadoExtracao(pasta / "estado.json", est["chave_idempotencia"], est["contrato"])


def test_aprovacao_exige_assinatura_e_decisoes(tmp_path):
    pasta = executar(PDF, tmp_path, modo="simulado")
    rec, ext, est = _carregar_run(pasta)
    modelo = yaml.safe_load((pasta / "aprovacao.yaml").read_text("utf-8"))
    with pytest.raises(ValueError, match="aprovado_por"):
        aprovar(pasta, ext, rec, modelo, est, "sha")
    modelo |= {"aprovado_por": "Teste", "data": "2026-11-06", "decisao_geral": "APROVAR"}
    with pytest.raises(ValueError, match="sem decisão"):
        aprovar(pasta, ext, rec, modelo, est, "sha")


def test_aprovacao_completa_gera_parametros_iguais_a_F2(tmp_path):
    pasta = executar(PDF, tmp_path, modo="simulado")
    rec, ext, est = _carregar_run(pasta)
    ap = yaml.safe_load((pasta / "aprovacao.yaml").read_text("utf-8"))
    decisao_humana = {  # o que o Jurídico decidiria lendo revisao.md (o juiz confirma D nos divergentes)
        "anexo_i.31001012.valor_teto": 4200.0, "anexo_ii.31309062.materiais_rotina": ["70402600", "70520020"],
        "anexo_ii.30715016.materiais_rotina": ["70402600", "70520020"], "anexo_ii.30715016.taxa_sala_codigo": "20103077",
        "regra.4.2.tipo": "TAXA_CONDICIONADA_CARATER", "regra.4.2.tipo_glosa": "INTEGRAL",
        "regra.5.1.tipo": "EXCLUIR", "regra.5.1.tipo_glosa": "EXCLUIR"}
    for c in ap["campos"]:
        c["decisao"] = decisao_humana[c["campo"]]
    ap |= {"aprovado_por": "Teste Jurídico", "data": "2026-11-06", "decisao_geral": "APROVAR",
           "confirmo_consenso_verificado": True}
    out = aprovar(pasta, ext, rec, ap, est, "sha", sinistro_codigos={"31001012", "10101039"})
    assert out["estado"] == "APROVADO"
    params = json.loads((pasta / "contract_params.json").read_text("utf-8"))
    f2 = yaml.safe_load((RAIZ / "semantic" / "vinculos" / "PRT-2025-0417.yaml").read_text("utf-8"))
    assert {i["codigo"]: i["valor_teto"] for i in params["anexo_i"]} == \
           {i["codigo"]: i["teto"] for i in f2["itens_com_preco_pactuado"]}
    assert {r["clausula"] for r in params["regras"]} == {"2.2", "2.3", "3.3", "3.4", "4.2"}
    assert params["origem_campos"]["anexo_i.31001012.valor_teto"] == "DECISAO_HUMANA"


def test_sanidade_bloqueia_pacote_com_sala_sem_preco(d):
    quebrado = copy.deepcopy(d)
    quebrado["anexo_i"] = [i for i in quebrado["anexo_i"] if i["codigo"] != "20103050"]
    falhas = {c["id"] for c in checar(quebrado) if not c["ok"]}
    assert "S04_pacote_31309062_sala_no_anexo_i" in falhas
    assert not [c for c in checar(d) if not c["ok"] and c["severidade"] == "BLOQUEIA"]
