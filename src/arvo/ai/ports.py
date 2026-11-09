"""Ports (interfaces) da arquitetura hexagonal. O core depende só destes contratos."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from arvo.ai.telemetria import LLMCallRecord


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
    classe_dados: str = "contratual"   # política de dados (src/arvo/ai/config/politica_dados.yaml): o roteador checa ANTES de chamar


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


# ===================================================================================== agente analista (src/arvo/agents/analyst)
@dataclass
class ResultadoConsulta:
    """Resposta de qualquer ConsultaDadosPort (Genie, SQL sobre a camada semântica)."""
    ok: bool
    fonte: str                                   # adapter que respondeu (ex.: "genie", "sql_semantico")
    pergunta: str
    sql: str | None = None                       # o SQL que gerou o número: toda resposta é auditável
    colunas: list[str] = field(default_factory=list)
    linhas: list[list] = field(default_factory=list)
    texto: str | None = None                     # resumo em linguagem natural, quando a fonte devolve um
    erro: str | None = None
    latencia_ms: float | None = None
    referencia: dict = field(default_factory=dict)   # ids da fonte (conversa/mensagem do Genie, statement_id)


@runtime_checkable
class ConsultaDadosPort(Protocol):
    """Descoberta de dados sobre a camada semântica. Prioridade: Genie; alternativa: SQL determinístico."""
    nome: str
    perimetro: str     # onde a consulta roda ("plataforma" para Genie e SQL warehouse)

    def consultar(self, pergunta: str) -> ResultadoConsulta: ...


@dataclass
class ChamadaFerramenta:
    id: str
    nome: str
    argumentos: dict


@dataclass
class TurnoAgente:
    """Uma resposta do modelo orquestrador, já normalizada entre provedores."""
    ok: bool
    texto: str
    chamadas: list[ChamadaFerramenta]
    record: LLMCallRecord
    nativo: list | None = None    # conteúdo bruto do provedor, reenviado sem alteração no turno seguinte (mesmo adapter)
    erro: str | None = None


@runtime_checkable
class AgenteLLMPort(Protocol):
    """Modelo orquestrador com chamada de ferramentas. A conversa é neutra (src/arvo/agents/analyst/agente.py: Transcricao);
    cada adapter traduz para o formato do seu provedor."""
    nome: str
    provedor: str
    familia: str
    modelo: str
    perimetro: str

    def turno(self, system: str, conversa: list[dict], ferramentas: list[dict], run_id: str) -> TurnoAgente: ...


@runtime_checkable
class ExecutorSQLPort(Protocol):
    """Executa SQL de leitura num warehouse. Usado pela consulta estruturada à camada semântica (consultar_metrica)."""
    nome: str
    perimetro: str

    def executar(self, sql: str) -> tuple[list[str], list[list]]: ...
