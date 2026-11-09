"""Adapters de DADOS do Databricks para o agente analista (SDK oficial `databricks-sdk`).

1. `GenieConsultaAdapter` (ConsultaDadosPort, prioridade): pergunta em linguagem natural → Genie (Conversation API).
   O Genie lê a camada semântica publicada no Unity Catalog (metric views, comentários, tags) e as instruções do espaço
   (ia/agente/genie/espaco.yaml). Devolve o SQL que gerou e as linhas do resultado.
2. `DatabricksSQLExecutor` (ExecutorSQLPort): executa o SQL determinístico montado a partir do catálogo semântico
   (ia/agente/semantica.py) num SQL warehouse. É a alternativa estruturada quando o Genie falha ou não está configurado.

Os dois rodam DENTRO da plataforma (perímetro "plataforma"): o dado não sai do workspace para ser consultado.
O que volta para o modelo orquestrador passa antes pela redução da política de dados (ia/agente/ferramentas.py).
Credencial: perfil da CLI (`databricks auth login --profile arvo-free`) ou a identidade do job, no workspace.
"""
from __future__ import annotations

import time
from datetime import timedelta

from ..ports import ResultadoConsulta


def cliente_workspace(perfil: str | None):
    from databricks.sdk import WorkspaceClient  # import tardio: só quem usa o adapter precisa do SDK
    return WorkspaceClient(profile=perfil) if perfil else WorkspaceClient()


def _tabela(statement_response) -> tuple[list[str], list[list]]:
    if statement_response is None:
        return [], []
    manifesto = getattr(statement_response, "manifest", None)
    esquema = getattr(manifesto, "schema", None)
    colunas = [c.name for c in (getattr(esquema, "columns", None) or [])]
    resultado = getattr(statement_response, "result", None)
    return colunas, [list(r) for r in (getattr(resultado, "data_array", None) or [])]


class GenieConsultaAdapter:
    nome = "genie"
    perimetro = "plataforma"

    def __init__(self, space_id: str, perfil: str | None = None, client=None, timeout_s: int = 180):
        self.space_id, self.perfil, self.timeout_s = space_id, perfil, timeout_s
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = cliente_workspace(self.perfil)
        return self._client

    def consultar(self, pergunta: str) -> ResultadoConsulta:
        t0 = time.time()
        try:
            msg = self.client.genie.start_conversation_and_wait(self.space_id, pergunta,
                                                                timeout=timedelta(seconds=self.timeout_s))
        except Exception as e:  # o adapter nunca derruba o agente: a falha volta como resultado e o modelo usa a alternativa
            return ResultadoConsulta(False, self.nome, pergunta, erro=f"{type(e).__name__}: {e}",
                                     latencia_ms=round((time.time() - t0) * 1000, 1))
        status = getattr(getattr(msg, "status", None), "name", str(getattr(msg, "status", "")))
        ref = {"space_id": self.space_id, "conversation_id": msg.conversation_id,
               "message_id": getattr(msg, "message_id", None) or getattr(msg, "id", None), "status": status}
        sql = texto = anexo = None
        for a in getattr(msg, "attachments", None) or []:
            if getattr(a, "query", None) is not None:
                sql, anexo = a.query.query, a.attachment_id
                texto = texto or a.query.description
            if getattr(a, "text", None) is not None and getattr(a.text, "content", None):
                texto = a.text.content
        colunas, linhas, erro = [], [], None
        if anexo:
            try:
                r = self.client.genie.get_message_attachment_query_result(
                    self.space_id, msg.conversation_id, ref["message_id"], anexo)
                colunas, linhas = _tabela(r.statement_response)
            except Exception as e:
                erro = f"resultado da consulta indisponível: {type(e).__name__}: {e}"
        if status != "COMPLETED":
            erro = erro or f"Genie terminou com status {status}: {getattr(msg, 'error', None)}"
        ok = status == "COMPLETED" and sql is not None and erro is None
        if status == "COMPLETED" and sql is None and not erro:
            erro = "o Genie respondeu sem consulta SQL (sem número auditável)"
        return ResultadoConsulta(ok, self.nome, pergunta, sql=sql, colunas=colunas, linhas=linhas, texto=texto,
                                 erro=erro, latencia_ms=round((time.time() - t0) * 1000, 1), referencia=ref)


class DatabricksSQLExecutor:
    nome = "sql_warehouse"
    perimetro = "plataforma"

    def __init__(self, warehouse_id: str, catalogo: str, perfil: str | None = None, client=None, timeout_s: int = 120):
        self.warehouse_id, self.catalogo, self.perfil, self.timeout_s = warehouse_id, catalogo, perfil, timeout_s
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = cliente_workspace(self.perfil)
        return self._client

    def executar(self, sql: str) -> tuple[list[str], list[list]]:
        r = self.client.statement_execution.execute_statement(sql, self.warehouse_id, catalog=self.catalogo,
                                                              wait_timeout="30s")
        fim = time.time() + self.timeout_s
        while r.status and r.status.state and r.status.state.name in ("PENDING", "RUNNING"):
            if time.time() > fim:
                raise TimeoutError(f"consulta passou de {self.timeout_s} s")
            time.sleep(2)
            r = self.client.statement_execution.get_statement(r.statement_id)
        if r.status and r.status.state and r.status.state.name != "SUCCEEDED":
            raise RuntimeError(f"{r.status.state.name}: {getattr(r.status.error, 'message', r.status.error)}")
        return _tabela(r)


def warehouse_por_nome(nome: str, perfil: str | None = None, client=None) -> str:
    w = client or cliente_workspace(perfil)
    for wh in w.warehouses.list():
        if wh.name == nome:
            return wh.id
    raise LookupError(f"SQL warehouse '{nome}' não encontrado")
