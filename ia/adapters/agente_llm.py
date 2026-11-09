"""Adapters do MODELO ORQUESTRADOR do agente analista: chamada de ferramentas, um turno por chamada.

A conversa chega NEUTRA (lista de dicts, ia/agente/agente.py) e cada adapter traduz para o seu provedor:
  {"papel": "usuario", "texto": ...}
  {"papel": "assistente", "texto": ..., "chamadas": [{"id", "nome", "argumentos"}], "nativo": {"adapter", "conteudo"}}
  {"papel": "ferramenta", "id": ..., "nome": ..., "conteudo": "<json>", "erro": bool}

1. `AnthropicAgenteAdapter` (Messages API, SDK `anthropic`), conforme a documentação vigente para claude-opus-5-5:
   - ferramentas com `strict: true` (schema com additionalProperties false e todos os campos em required);
   - `tool_choice` automático (os modos "any"/"tool" retornam 400 neste modelo);
   - sem temperature/top_p (400); profundidade por `output_config.effort` (padrão do modelo é medium: definimos);
   - thinking adaptativo é sempre ligado neste modelo: o parâmetro é omitido;
   - o conteúdo do assistente (inclusive blocos de raciocínio e de fallback) volta SEM ALTERAÇÃO no turno seguinte;
   - fallback de recusa no servidor (`fallbacks: "default"`, beta server-side-fallback-2026-07-01), desligável;
   - cache do prefixo estável (ferramentas + system) com cache_control.
2. `ChatToolsAdapter` (Chat Completions com `tools`, SDK `openai`): endpoints compatíveis, em especial os modelos
   hospedados no Databricks (`databricks-gpt-oss-120b`), que rodam DENTRO da plataforma (perímetro "plataforma").
"""
from __future__ import annotations

import json
import time

from ..ports import ChamadaFerramenta, LLMParams, LLMRequest, TurnoAgente
from ..telemetria import (STOP_COMPLETO, STOP_ERRO, STOP_FILTRO, STOP_RECUSA, STOP_TRUNCADO, novo_registro,
                          sha256_texto)

MAX_TOKENS = 16000


def _registro(adapter, system: str, conversa: list[dict], ferramentas: list[dict], run_id: str, effort: str | None):
    entrada = json.dumps([{k: v for k, v in m.items() if k != "nativo"} for m in conversa],
                         ensure_ascii=False, default=str)
    req = LLMRequest(task_id="agente_analista", system=system, user=entrada, schema_id="agente_turno",
                     schema_version="1", schema={"ferramentas": sorted(f["nome"] for f in ferramentas)},
                     prompt_id="agente_analista", prompt_version="", run_id=run_id,
                     params=LLMParams(max_output_tokens=MAX_TOKENS, temperature=None, reasoning_effort=effort),
                     documento_sha256=sha256_texto(entrada), classe_dados="agregado")
    rec = novo_registro(req, adapter)
    rec.params_aplicados = {"max_output_tokens": MAX_TOKENS, **({"reasoning_effort": effort} if effort else {})}
    return rec


def _parse_argumentos(bruto) -> dict | None:
    if isinstance(bruto, dict):
        return bruto
    try:
        v = json.loads(bruto or "{}")
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        return None


class AnthropicAgenteAdapter:
    provedor = "anthropic"

    def __init__(self, nome: str, modelo: str = "claude-opus-5-5", familia: str = "anthropic", effort: str = "high",
                 server_fallbacks: bool = True, perimetro: str = "externo", client=None):
        self.nome, self.modelo, self.familia, self.effort = nome, modelo, familia, effort
        self.server_fallbacks, self.perimetro, self._client = server_fallbacks, perimetro, client
        self.endpoint = None

    @property
    def client(self):
        if self._client is None:
            import anthropic  # credencial: ANTHROPIC_API_KEY ou perfil `ant auth login`
            self._client = anthropic.Anthropic()
        return self._client

    def mensagens(self, conversa: list[dict]) -> list[dict]:
        msgs: list[dict] = []
        for m in conversa:
            if m["papel"] == "usuario":
                msgs.append({"role": "user", "content": m["texto"]})
            elif m["papel"] == "assistente":
                nativo = m.get("nativo") or {}
                if nativo.get("adapter") == self.nome and nativo.get("conteudo"):
                    msgs.append({"role": "assistant", "content": nativo["conteudo"]})   # sem alteração
                    continue
                blocos = [{"type": "text", "text": m["texto"]}] if m.get("texto") else []
                blocos += [{"type": "tool_use", "id": c["id"], "name": c["nome"], "input": c["argumentos"]}
                           for c in m.get("chamadas", [])]
                msgs.append({"role": "assistant", "content": blocos})
            elif m["papel"] == "ferramenta":
                bloco = {"type": "tool_result", "tool_use_id": m["id"], "content": m["conteudo"],
                         **({"is_error": True} if m.get("erro") else {})}
                if msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], list) \
                        and all(b.get("type") == "tool_result" for b in msgs[-1]["content"]):
                    msgs[-1]["content"].append(bloco)        # todos os resultados do turno numa só mensagem
                else:
                    msgs.append({"role": "user", "content": [bloco]})
        return msgs

    @staticmethod
    def ferramentas(ferramentas: list[dict]) -> list[dict]:
        return [{"name": f["nome"], "description": f["descricao"], "input_schema": f["schema"], "strict": True}
                for f in ferramentas]

    def montar_requisicao(self, system: str, conversa: list[dict], ferramentas: list[dict]) -> dict:
        kw = {"model": self.modelo, "max_tokens": MAX_TOKENS,
              "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
              "tools": self.ferramentas(ferramentas), "tool_choice": {"type": "auto"},
              "messages": self.mensagens(conversa), "output_config": {"effort": self.effort}}
        if self.server_fallbacks:
            kw["betas"] = ["server-side-fallback-2026-07-01"]
            kw["fallbacks"] = "default"
        return kw

    def turno(self, system: str, conversa: list[dict], ferramentas: list[dict], run_id: str) -> TurnoAgente:
        rec = _registro(self, system, conversa, ferramentas, run_id, self.effort)
        t0 = time.time()
        try:
            kw = self.montar_requisicao(system, conversa, ferramentas)
            api = self.client.beta.messages if self.server_fallbacks else self.client.messages
            resp = api.create(**kw)
        except Exception as e:
            rec.latencia_ms, rec.stop_normalizado, rec.erro = round((time.time() - t0) * 1000, 1), STOP_ERRO, \
                f"{type(e).__name__}: {e}"
            return TurnoAgente(False, "", [], rec, erro=rec.erro)
        return self.ler_resposta(resp, rec, t0)

    @staticmethod
    def ler_resposta(resp, rec, t0: float) -> TurnoAgente:
        rec.latencia_ms = round((time.time() - t0) * 1000, 1)
        rec.modelo_servido, rec.request_id, rec.stop_bruto = getattr(resp, "model", None), \
            getattr(resp, "_request_id", None), resp.stop_reason
        u = resp.usage
        rec.input_tokens, rec.output_tokens = getattr(u, "input_tokens", None), getattr(u, "output_tokens", None)
        rec.cache_read_tokens = getattr(u, "cache_read_input_tokens", None)
        rec.cache_write_tokens = getattr(u, "cache_creation_input_tokens", None)
        nativo = [b.to_dict() if hasattr(b, "to_dict") else b for b in resp.content]
        if resp.stop_reason == "refusal":
            det = getattr(resp, "stop_details", None)
            rec.stop_normalizado, rec.stop_detalhe = STOP_RECUSA, getattr(det, "category", None) if det else None
            return TurnoAgente(False, "", [], rec, nativo, erro=f"recusa ({rec.stop_detalhe})")
        if resp.stop_reason == "max_tokens":
            rec.stop_normalizado = STOP_TRUNCADO
            return TurnoAgente(False, "", [], rec, nativo, erro="resposta truncada (max_tokens)")
        texto = "\n".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        chamadas, invalidas = [], []
        for b in resp.content:
            if getattr(b, "type", None) == "tool_use":
                args = _parse_argumentos(b.input)
                (chamadas if args is not None else invalidas).append(ChamadaFerramenta(b.id, b.name, args or {}))
        rec.stop_normalizado, rec.schema_valido = STOP_COMPLETO, not invalidas
        if invalidas:
            rec.erros_schema = [f"argumentos inválidos em {c.nome}" for c in invalidas]
        return TurnoAgente(True, texto, chamadas + invalidas, rec, nativo)


class ChatToolsAdapter:
    def __init__(self, nome: str, modelo: str, familia: str, provedor: str = "databricks_gateway",
                 perimetro: str = "plataforma", perfil_databricks: str | None = None, client=None):
        self.nome, self.modelo, self.familia, self.provedor = nome, modelo, familia, provedor
        self.perimetro, self.perfil, self._client = perimetro, perfil_databricks, client
        self.endpoint = modelo

    @property
    def client(self):
        if self._client is None:
            from databricks.sdk import WorkspaceClient  # cliente OpenAI já autenticado no workspace
            w = WorkspaceClient(profile=self.perfil) if self.perfil else WorkspaceClient()
            self._client = w.serving_endpoints.get_open_ai_client()
        return self._client

    @staticmethod
    def mensagens(system: str, conversa: list[dict]) -> list[dict]:
        msgs: list[dict] = [{"role": "system", "content": system}]
        for m in conversa:
            if m["papel"] == "usuario":
                msgs.append({"role": "user", "content": m["texto"]})
            elif m["papel"] == "assistente":
                msg = {"role": "assistant", "content": m.get("texto") or None}
                if m.get("chamadas"):
                    msg["tool_calls"] = [{"id": c["id"], "type": "function",
                                          "function": {"name": c["nome"], "arguments": json.dumps(c["argumentos"],
                                                                                                  ensure_ascii=False)}}
                                         for c in m["chamadas"]]
                msgs.append(msg)
            elif m["papel"] == "ferramenta":
                msgs.append({"role": "tool", "tool_call_id": m["id"], "content": m["conteudo"]})
        return msgs

    @staticmethod
    def ferramentas(ferramentas: list[dict]) -> list[dict]:
        return [{"type": "function", "function": {"name": f["nome"], "description": f["descricao"],
                                                  "parameters": f["schema"]}} for f in ferramentas]

    def turno(self, system: str, conversa: list[dict], ferramentas: list[dict], run_id: str) -> TurnoAgente:
        rec = _registro(self, system, conversa, ferramentas, run_id, None)
        t0 = time.time()
        try:
            resp = self.client.chat.completions.create(model=self.modelo, max_tokens=MAX_TOKENS,
                                                       messages=self.mensagens(system, conversa),
                                                       tools=self.ferramentas(ferramentas), tool_choice="auto")
        except Exception as e:
            rec.latencia_ms, rec.stop_normalizado, rec.erro = round((time.time() - t0) * 1000, 1), STOP_ERRO, \
                f"{type(e).__name__}: {e}"
            return TurnoAgente(False, "", [], rec, erro=rec.erro)
        rec.latencia_ms = round((time.time() - t0) * 1000, 1)
        rec.modelo_servido, rec.request_id = getattr(resp, "model", None), getattr(resp, "id", None)
        u = getattr(resp, "usage", None)
        if u is not None:
            rec.input_tokens, rec.output_tokens = getattr(u, "prompt_tokens", None), getattr(u, "completion_tokens", None)
        ch = resp.choices[0]
        rec.stop_bruto = getattr(ch, "finish_reason", None)
        if getattr(ch.message, "refusal", None):
            rec.stop_normalizado = STOP_RECUSA
            return TurnoAgente(False, "", [], rec, erro="recusa")
        if rec.stop_bruto in ("length", "content_filter"):
            rec.stop_normalizado = STOP_TRUNCADO if rec.stop_bruto == "length" else STOP_FILTRO
            return TurnoAgente(False, "", [], rec, erro=f"desfecho {rec.stop_bruto}")
        chamadas = [ChamadaFerramenta(tc.id, tc.function.name, _parse_argumentos(tc.function.arguments) or {})
                    for tc in (getattr(ch.message, "tool_calls", None) or [])]
        rec.stop_normalizado, rec.schema_valido = STOP_COMPLETO, True
        return TurnoAgente(True, (_texto_openai(ch.message.content) or "").strip(), chamadas, rec)


def _texto_openai(conteudo) -> str:
    """Alguns endpoints devolvem o conteúdo em partes (raciocínio + texto). Só o texto final vai para a resposta."""
    if isinstance(conteudo, list):
        return "".join(p.get("text", "") for p in conteudo if isinstance(p, dict) and p.get("type") == "text")
    return conteudo or ""
