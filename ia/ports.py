"""Ports (interfaces) da arquitetura hexagonal. O core depende só destes contratos."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from .telemetria import LLMCallRecord


@dataclass(frozen=True)
class LLMParams:
    """Parâmetros PEDIDOS. Cada adapter decide o que consegue aplicar e registra o resto como ignorado."""
    max_output_tokens: int = 16000
    temperature: float | None = 0.0      # pedido por padrão; muitos modelos atuais NÃO aceitam (fica registrado)
    top_p: float | None = None
    seed: int | None = None
    reasoning_effort: str | None = "high"  # low | medium | high | ...

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass(frozen=True)
class LLMRequest:
    task_id: str
    system: str
    user: str
    schema_id: str
    schema_version: str
    schema: dict
    prompt_id: str
    prompt_version: str
    params: LLMParams
    run_id: str
    documento_sha256: str
    classe_dados: str = "contratual"   # política de dados (ia/config/politica_dados.yaml): o roteador checa ANTES de chamar


@dataclass
class LLMResult:
    ok: bool
    data: dict | None
    raw_text: str | None
    error: str | None
    record: LLMCallRecord


@runtime_checkable
class LLMPort(Protocol):
    nome: str          # nome do adapter na configuração (ex.: "anthropic_opus")
    provedor: str      # ex.: "anthropic", "openai", "databricks_gateway", "simulado"
    familia: str       # família do modelo (independência entre extratores): "anthropic", "openai", "google", ...
    modelo: str
    perimetro: str     # "local" | "plataforma" | "externo": para onde o dado vai (define o que pode ser enviado)

    def generate_structured(self, req: LLMRequest) -> LLMResult: ...


@dataclass
class ParsedDoc:
    """Saída de qualquer DocumentParserPort."""
    parser: str
    parser_versao: str
    sha256: str
    paginas: list[str]
    texto_limpo: str                       # cabeçalhos/rodapés repetidos removidos
    tabelas: list[dict]                    # {pagina, cabecalho: [..], linhas: [[..], ..]}
    clausulas: dict[str, str]              # "2.2" -> texto da cláusula
    artefatos: dict[str, int] = field(default_factory=dict)  # ex.: {"nul_chars": 3, "rodapes_removidos": 4}


@runtime_checkable
class DocumentParserPort(Protocol):
    nome: str

    def parse(self, caminho: Path) -> ParsedDoc: ...
