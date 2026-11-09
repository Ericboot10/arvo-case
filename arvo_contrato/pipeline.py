"""Orquestração da F3: parse → extração D/A/B → reconciliação → juiz → pacote de revisão (para em REVISAO_HUMANA)."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import yaml

from . import juiz as juiz_mod
from ia.adapters.anthropic_adapter import AnthropicAdapter
from ia.adapters.openai_adapters import OpenAICompatChatAdapter, OpenAIResponsesAdapter
from ia.adapters.replay_adapter import ReplayAdapter
from .extratores import deterministico
from .extratores.llm import carregar_prompt, documento_para_prompt, montar_requisicao
from .estado import EstadoExtracao
from .grounding import Corpus
from .parsing import PdfPlumberParser
from ia.ports import LLMParams
from .reconciliacao import CONSENSO_VERIFICADO, reconciliar
from .revisao import gerar_pacote
from ia.roteador import CacheRespostas, Orcamento, Roteador
from .schema import SCHEMA_VERSAO, validar
from ia.telemetria import TelemetriaJSONL, sha256_json

PACOTE = Path(__file__).resolve().parent


def construir_adapter(nome: str, cfg: dict):
    c = dict(cfg)
    classe = c.pop("classe")
    if classe == "anthropic":
        return AnthropicAdapter(nome, **c)
    if classe == "openai_responses":
        return OpenAIResponsesAdapter(nome, **c)
    if classe == "openai_compat":
        return OpenAICompatChatAdapter(nome, **c)
    if classe == "replay":
        return ReplayAdapter(nome, fixture=PACOTE / c.pop("fixture"), **c)
    raise ValueError(f"classe de adapter desconhecida: {classe}")


def carregar_config(caminho: Path | None = None) -> dict:
    return yaml.safe_load((caminho or PACOTE / "config" / "extracao.yaml").read_text("utf-8"))


def executar(pdf: Path, saida: Path, modo: str = "simulado", config: dict | None = None,
             adapters: dict | None = None, contrato: str = "PRT-2025-0417") -> Path:
    """Retorna a pasta do run. `adapters` permite injetar adapters (testes de caos) sem tocar no core."""
    cfg = config or carregar_config()
    slots = cfg["modos"][modo]
    adapters = adapters or {n: construir_adapter(n, cfg["adapters"][n]) for s in slots.values() for n in s}
    cadeias = {s: [adapters[n] for n in nomes] for s, nomes in slots.items()}
    fam_a = {a.familia for a in cadeias["A"]}
    fam_b = {a.familia for a in cadeias["B"]}
    if fam_a & fam_b:
        raise ValueError(f"A e B compartilham família {fam_a & fam_b}: independência violada na configuração")

    doc = PdfPlumberParser().parse(pdf)
    prompt = carregar_prompt(cfg["prompt_arquivo"])
    chave = sha256_json({"doc": doc.sha256, "schema": SCHEMA_VERSAO, "prompt": [prompt["id"], prompt["versao"]],
                         "config": cfg, "modo": modo, "adapters": sorted(adapters)})
    pasta = Path(saida) / contrato / chave[:12]
    estado = EstadoExtracao(pasta / "estado.json", chave, contrato)
    if estado.estado != "RECEBIDO":
        return pasta  # idempotente: run já existe (retomar via aprovação)

    run_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    (pasta / "parse.json").write_text(json.dumps(
        {"parser": doc.parser, "versao": doc.parser_versao, "sha256": doc.sha256, "artefatos": doc.artefatos,
         "clausulas": doc.clausulas, "tabelas": doc.tabelas}, ensure_ascii=False, indent=2), "utf-8")
    estado.avancar("PARSEADO", f"{doc.parser} {doc.parser_versao}; artefatos {doc.artefatos}")

    sink = TelemetriaJSONL(pasta / "llm_calls.jsonl")
    rot = Roteador(sink, Orcamento(cfg["orcamento"]["max_tokens_run"], cfg["orcamento"]["max_chamadas_run"]),
                   CacheRespostas(Path(saida) / "_cache"), cfg.get("precos_usd_por_mtok"), cfg.get("ambiente", "dev"))
    params = LLMParams(**cfg["params"])

    extracoes, familias, falhas = {}, {"D": deterministico.FAMILIA}, {}
    d = deterministico.extrair(doc)
    if not validar(d):
        extracoes["D"] = d
    else:
        falhas["D"] = validar(d)
    for slot in ("A", "B"):
        req = montar_requisicao(doc, prompt, params, run_id, task_id=f"extracao_{slot}")
        res, usado = rot.gerar(req, cadeias[slot])
        if res and res.ok:
            extracoes[slot], familias[slot] = res.data, usado.familia
        else:
            falhas[slot] = res.error if res else "sem adapter"
    for k, v in extracoes.items():
        (pasta / f"extracao_{k}.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), "utf-8")
    if not extracoes:
        estado.avancar("FALHOU", f"nenhum extrator produziu saída válida: {falhas}")
        return pasta
    estado.avancar("EXTRAIDO", f"fontes válidas {sorted(extracoes)}; falhas {falhas}")

    corpus = Corpus(doc)
    rec = reconciliar(extracoes, familias, corpus)
    rec["falhas_extratores"] = falhas
    estado.avancar("RECONCILIADO", json.dumps(rec["resumo"]))

    pend = [l for l in rec["campos"] if l["status"] != CONSENSO_VERIFICADO]
    if pend and cadeias.get("juiz"):
        familias_usadas = set(familias.values())
        cadeia_juiz = [a for a in cadeias["juiz"] if a.familia not in familias_usadas]
        if cadeia_juiz:
            jr = juiz_mod.montar(pend, documento_para_prompt(doc), run_id, doc.sha256)
            jres, _ = rot.gerar(jr, cadeia_juiz)
            juiz_mod.anotar(rec, jres.data if jres and jres.ok else None, corpus)
            estado.avancar("JULGADO", f"{len(pend)} campos julgados")
    (pasta / "reconciliacao.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2, default=list), "utf-8")

    gerar_pacote(pasta, rec, estado.dados, {"contrato": contrato, "documento": Path(pdf).name,
                                            "documento_sha256": doc.sha256, "run_id": run_id, "modo": modo,
                                            "artefatos": doc.artefatos})
    estado.avancar("REVISAO_HUMANA", f"{len(pend)} campos aguardando decisão do Jurídico")
    return pasta
