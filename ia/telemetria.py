"""Telemetria obrigatória por chamada de IA (plano v2, seção 9.4).

Cada chamada a um modelo, inclusive cache hit, falha e fallback, gera exatamente um LLMCallRecord.
Localmente vai para JSONL. No Databricks, o notebook da F3 grava em <catalog>.ops.llm_calls.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Desfecho normalizado entre provedores (cada provedor usa nomes diferentes)
STOP_COMPLETO = "COMPLETO"
STOP_TRUNCADO = "TRUNCADO"            # max_tokens / length / incomplete:max_output_tokens
STOP_RECUSA = "RECUSA"                # refusal
STOP_FILTRO = "FILTRO_CONTEUDO"       # content_filter
STOP_ERRO = "ERRO"                    # exceção de rede/API
STOP_ORCAMENTO = "BLOQUEADO_ORCAMENTO"
STOP_POLITICA = "BLOQUEADO_POLITICA_DADOS"   # classe de dado não permitida para o perímetro do adapter
STOP_CIRCUITO = "BLOQUEADO_CIRCUITO"         # adapter com falhas consecutivas acima do limite (circuit breaker)


def sha256_texto(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_json(obj) -> str:
    return sha256_texto(json.dumps(obj, sort_keys=True, ensure_ascii=False))


@dataclass
class LLMCallRecord:
    # identidade
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str = ""
    task_id: str = ""
    chave_idempotencia: str = ""
    ts_inicio: float = field(default_factory=time.time)
    ambiente: str = "dev"
    # modelo
    provedor: str = ""
    adapter: str = ""
    familia: str = ""
    endpoint: str | None = None
    modelo_pedido: str = ""
    modelo_servido: str | None = None      # o provedor pode servir outro (ex.: fallback do servidor)
    fallback_de: str | None = None         # adapter anterior na cadeia, se houve fallback local
    # prompt e schema
    prompt_id: str = ""
    prompt_versao: str = ""
    prompt_hash: str = ""
    system_hash: str = ""
    schema_id: str = ""
    schema_versao: str = ""
    schema_hash: str = ""
    # parâmetros: pedido x aplicado (temperatura em modelo de raciocínio, por exemplo, é ignorada)
    params_pedidos: dict = field(default_factory=dict)
    params_aplicados: dict = field(default_factory=dict)
    params_ignorados: dict = field(default_factory=dict)   # nome -> motivo
    # consumo
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    custo_estimado_usd: float | None = None
    cache_hit_local: bool = False
    # latência
    latencia_ms: float | None = None
    # resultado
    stop_normalizado: str | None = None
    stop_bruto: str | None = None
    stop_detalhe: str | None = None
    schema_valido: bool | None = None
    erros_schema: list = field(default_factory=list)
    erro: str | None = None
    request_id: str | None = None
    # linhagem e política
    documento_sha256: str = ""
    classe_dados: str = ""
    perimetro: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def novo_registro(req, adapter) -> LLMCallRecord:
    """Preenche os campos que não dependem da resposta."""
    return LLMCallRecord(
        run_id=req.run_id,
        task_id=req.task_id,
        chave_idempotencia=chave_cache(req, adapter),
        provedor=adapter.provedor,
        adapter=adapter.nome,
        familia=adapter.familia,
        endpoint=getattr(adapter, "endpoint", None),
        modelo_pedido=adapter.modelo,
        prompt_id=req.prompt_id,
        prompt_versao=req.prompt_version,
        prompt_hash=sha256_texto(req.system + "\n" + req.user),
        system_hash=sha256_texto(req.system),
        schema_id=req.schema_id,
        schema_versao=req.schema_version,
        schema_hash=sha256_json(req.schema),
        params_pedidos=req.params.as_dict(),
        documento_sha256=req.documento_sha256,
        classe_dados=req.classe_dados,
        perimetro=getattr(adapter, "perimetro", ""),
    )


def chave_cache(req, adapter) -> str:
    """Chave de idempotência e cache: mesma entrada + mesmo adapter/modelo/prompt/schema/params = resposta reaproveitada.

    O nome do adapter, a família e o endpoint ENTRAM na chave. Sem isso, dois extratores que usam o mesmo nome
    de modelo (ex.: o mesmo modelo em dois endpoints, ou dois replays) receberiam a resposta um do outro
    pelo cache, e o "consenso" entre eles seria falso. Bug encontrado na primeira execução da demo e coberto por teste.
    """
    return sha256_json({
        "adapter": adapter.nome, "familia": adapter.familia, "endpoint": getattr(adapter, "endpoint", None),
        "provedor": adapter.provedor, "modelo": adapter.modelo, "prompt": [req.prompt_id, req.prompt_version],
        "schema": [req.schema_id, req.schema_version], "params": req.params.as_dict(),
        "system": sha256_texto(req.system), "user": sha256_texto(req.user),
    })


def estimar_custo(rec: LLMCallRecord, tabela_precos: dict) -> float | None:
    """Custo estimado em USD a partir da tabela da config. Sem preço cadastrado, retorna None (não inventa)."""
    p = tabela_precos.get(rec.modelo_servido or rec.modelo_pedido) or tabela_precos.get(rec.modelo_pedido)
    if not p or rec.input_tokens is None or rec.output_tokens is None:
        return None
    custo = rec.input_tokens * p["input"] + rec.output_tokens * p["output"]
    if rec.cache_read_tokens and "cache_read" in p:
        custo += rec.cache_read_tokens * p["cache_read"]
    return round(custo / 1_000_000, 6)


class TelemetriaJSONL:
    """Sink local. Em Databricks, troque por um sink que grava em Delta (ver notebook da F3)."""

    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)

    def gravar(self, rec: LLMCallRecord) -> None:
        with open(self.caminho, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")


CAMPOS_OBRIGATORIOS = [
    "call_id", "run_id", "task_id", "chave_idempotencia", "provedor", "adapter", "familia", "modelo_pedido",
    "prompt_id", "prompt_versao", "prompt_hash", "schema_id", "schema_versao", "schema_hash",
    "params_pedidos", "params_aplicados", "params_ignorados", "latencia_ms", "stop_normalizado",
    "schema_valido", "documento_sha256",
]
