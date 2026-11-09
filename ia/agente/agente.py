"""Agente analista: um modelo orquestrador (trocável) + ferramentas sobre a camada semântica (Genie primeiro).

Loop: pergunta → turno do modelo → ferramentas pedidas → resultados reduzidos pela política de dados → próximo turno,
até uma resposta sem chamada de ferramenta ou o limite de turnos. A conversa é guardada num formato NEUTRO; cada adapter
traduz para o seu provedor. O conteúdo bruto de um provedor (raciocínio, blocos de fallback) só volta para o MESMO
adapter, sem alteração.

Fallback do orquestrador: a cadeia (ia/config/agente.yaml) é tentada em ordem; o adapter que falha N vezes seguidas
sai da rodada (circuit breaker), e o seguinte continua a mesma conversa a partir do formato neutro.
Telemetria: cada turno vira um LLMCallRecord (mesmo formato da F3/F7), e cada ferramenta fica no rastro da resposta.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..ports import AgenteLLMPort
from ..roteador import carregar_politica, permitido
from . import semantica
from .ferramentas import Ferramentas, serializar

PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "agente_analista_v1.md"


def carregar_prompt(caminho: Path = PROMPT) -> tuple[str, str, str]:
    txt = caminho.read_text("utf-8")
    meta = dict(re.findall(r"^(prompt_id|versao):\s*(\S+)", txt, flags=re.M))
    corpo = re.sub(r"\A---.*?---\s*", "", txt, flags=re.S)
    return meta["prompt_id"], meta["versao"], corpo


def _sem_credencial(erro: str | None) -> bool:
    e = (erro or "").lower()
    return any(x in e for x in ("authentication", "authenticationerror", "permissiondenied", "api_key", "401", "403"))


@dataclass
class Resposta:
    pergunta: str
    texto: str
    ok: bool
    run_id: str
    rastro: list[dict] = field(default_factory=list)     # cada ferramenta: nome, argumentos, fonte, sql, ok, erro
    modelos: list[str] = field(default_factory=list)     # adapter de cada turno (mostra fallback, se houve)
    turnos: int = 0
    erro: str | None = None


class Agente:
    def __init__(self, cadeia: list[AgenteLLMPort], ferramentas: Ferramentas, sink=None, max_turnos: int = 8,
                 limite_falhas: int = 2, politica: dict | None = None):
        self.cadeia, self.ferramentas, self.sink = cadeia, ferramentas, sink
        self.max_turnos, self.limite_falhas = max_turnos, limite_falhas
        self.politica = politica or carregar_politica()
        self.prompt_id, self.prompt_versao, corpo = carregar_prompt()
        catalogo = semantica.descrever(ferramentas.catalogo)
        self.system = f"{corpo.rstrip()}\n\n## Catálogo semântico (metric views publicadas)\n{catalogo}\n"
        self.falhas: dict[str, int] = {}

    def _gravar(self, rec) -> None:
        rec.prompt_id, rec.prompt_versao = self.prompt_id, self.prompt_versao
        if self.sink is not None:
            self.sink.gravar(rec)

    def _turno(self, conversa: list[dict], run_id: str, resposta: Resposta):
        defs = self.ferramentas.definicoes()
        erros = []
        for adapter in self.cadeia:
            # a conversa só carrega classes 'publico', 'contratual', 'catalogo' e 'agregado' (redução nas ferramentas)
            if not all(permitido(self.politica, c, adapter.perimetro) for c in ("contratual", "catalogo", "agregado")):
                erros.append(f"{adapter.nome}: perímetro {adapter.perimetro} não permitido")
                continue
            if self.falhas.get(adapter.nome, 0) >= self.limite_falhas:
                continue
            t = adapter.turno(self.system, conversa, defs, run_id)
            self._gravar(t.record)
            if t.ok:
                self.falhas[adapter.nome] = 0
                resposta.modelos.append(adapter.nome)
                return t, adapter
            self.falhas[adapter.nome] = self.falhas.get(adapter.nome, 0) + 1
            if _sem_credencial(t.erro):          # sem credencial não adianta tentar de novo nesta rodada
                self.falhas[adapter.nome] = self.limite_falhas
            erros.append(f"{adapter.nome}: {t.erro}")
        resposta.erro = "; ".join(erros) or "nenhum modelo disponível"
        return None, None

    def perguntar(self, pergunta: str) -> Resposta:
        run_id = f"agente-{uuid.uuid4().hex[:12]}"
        resposta = Resposta(pergunta, "", False, run_id)
        conversa: list[dict] = [{"papel": "usuario", "texto": pergunta}]
        for _ in range(self.max_turnos):
            t, adapter = self._turno(conversa, run_id, resposta)
            if t is None:
                resposta.texto = f"Não consegui responder: {resposta.erro}"
                return resposta
            resposta.turnos += 1
            conversa.append({"papel": "assistente", "texto": t.texto,
                             "chamadas": [{"id": c.id, "nome": c.nome, "argumentos": c.argumentos} for c in t.chamadas],
                             "nativo": {"adapter": adapter.nome, "conteudo": t.nativo} if t.nativo else None})
            if not t.chamadas:
                resposta.texto, resposta.ok = t.texto, bool(t.texto)
                return resposta
            for c in t.chamadas:
                r = self.ferramentas.executar(c.nome, c.argumentos)
                resposta.rastro.append({"ferramenta": c.nome, "argumentos": c.argumentos, "ok": r.get("ok", False),
                                        "fonte": r.get("fonte"), "sql": r.get("sql"), "erro": r.get("erro"),
                                        "linhas": len(r.get("linhas", []) or []),
                                        "colunas_removidas": r.get("colunas_removidas_pela_politica", [])})
                conversa.append({"papel": "ferramenta", "id": c.id, "nome": c.nome, "conteudo": serializar(r),
                                 "erro": not r.get("ok", False)})
        resposta.texto = f"Parei após {self.max_turnos} turnos sem uma resposta final."
        resposta.erro = "limite de turnos"
        return resposta
