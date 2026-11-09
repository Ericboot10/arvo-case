"""Adapters no formato OpenAI. Cobrem dois casos com o SDK oficial `openai`:

1. `OpenAIResponsesAdapter`: OpenAI direto (Responses API).
   Structured outputs: `text.format = {type: json_schema, name, schema, strict: true}`.
   Desfecho: `status == "incomplete"` com `incomplete_details.reason` (`max_output_tokens` | `content_filter`);
   recusa vem como parte de conteúdo `type: refusal`. Uso: input_tokens, input_tokens_details.cached_tokens,
   output_tokens, output_tokens_details.reasoning_tokens (raciocínio é cobrado como output).
   Modelos de raciocínio usam `reasoning.effort`; `temperature` só é enviado se a config declarar suporte.

2. `OpenAICompatChatAdapter`: QUALQUER endpoint compatível com Chat Completions. É o caminho do
   **Databricks AI Gateway / Model Serving** (`base_url = <host>/serving-endpoints`, `model = <nome do endpoint>`),
   que expõe OpenAI, Anthropic, Vertex/Gemini, Bedrock e modelos abertos atrás de uma API única,
   e também de servidores próprios (vLLM etc.).
   Structured outputs no Databricks: `response_format = {type: json_schema, json_schema: {name, schema, strict: true}}`.
   Atenção (doc Databricks): os modelos `databricks-claude-*-5-5` retornam 400 para `response_format` em
   Chat Completions. Para eles, use o AnthropicAdapter (Messages API) ou outro endpoint.
"""
from __future__ import annotations

import os

from . import BaseAdapter
from ..telemetria import STOP_COMPLETO, STOP_FILTRO, STOP_RECUSA, STOP_TRUNCADO


class OpenAIResponsesAdapter(BaseAdapter):
    provedor = "openai"

    def __init__(self, nome: str, modelo: str, familia: str = "openai", suporta: dict | None = None, client=None,
                 perimetro: str = "externo"):
        self.nome, self.modelo, self.familia, self.perimetro = nome, modelo, familia, perimetro
        self.suporta = suporta or {"temperature": False, "top_p": False, "seed": False, "reasoning_effort": True}
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI()  # OPENAI_API_KEY
        return self._client

    def montar_requisicao(self, req, aplicados: dict) -> dict:
        kw = {
            "model": self.modelo,
            "instructions": req.system,
            "input": [{"role": "user", "content": req.user}],
            "max_output_tokens": aplicados["max_output_tokens"],
            "text": {"format": {"type": "json_schema", "name": req.schema_id, "schema": req.schema, "strict": True}},
        }
        if "reasoning_effort" in aplicados:
            kw["reasoning"] = {"effort": aplicados["reasoning_effort"]}
        for p in ("temperature", "top_p"):
            if p in aplicados:
                kw[p] = aplicados[p]
        return kw

    def _chamar(self, req, aplicados: dict, rec) -> str:
        return self.ler_resposta(self.client.responses.create(**self.montar_requisicao(req, aplicados)), rec)

    @staticmethod
    def ler_resposta(resp, rec) -> str:
        rec.modelo_servido = getattr(resp, "model", None)
        rec.request_id = getattr(resp, "id", None)
        status = getattr(resp, "status", None)
        motivo = getattr(getattr(resp, "incomplete_details", None), "reason", None)
        recusa = any(getattr(c, "type", None) == "refusal"
                     for o in (getattr(resp, "output", None) or []) for c in (getattr(o, "content", None) or []))
        rec.stop_bruto = f"{status}:{motivo}" if motivo else status
        if recusa:
            rec.stop_normalizado = STOP_RECUSA
        elif status == "incomplete":
            rec.stop_normalizado = STOP_FILTRO if motivo == "content_filter" else STOP_TRUNCADO
        else:
            rec.stop_normalizado = STOP_COMPLETO
        u = getattr(resp, "usage", None)
        if u is not None:
            rec.input_tokens = getattr(u, "input_tokens", None)
            rec.output_tokens = getattr(u, "output_tokens", None)
            rec.cache_read_tokens = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", None)
            rec.reasoning_tokens = getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", None)
        return getattr(resp, "output_text", "") or ""


class OpenAICompatChatAdapter(BaseAdapter):
    def __init__(self, nome: str, modelo: str, familia: str, provedor: str = "databricks_gateway",
                 base_url: str | None = None, base_url_env: str | None = "DATABRICKS_HOST",
                 sufixo: str = "/serving-endpoints", token_env: str = "DATABRICKS_TOKEN",
                 suporta: dict | None = None, client=None, perimetro: str = "externo"):
        self.nome, self.modelo, self.familia, self.provedor = nome, modelo, familia, provedor
        self.perimetro = perimetro  # "plataforma" só para modelos hospedados no Databricks (databricks-*)
        self._base_url, self._base_env, self._sufixo, self._token_env = base_url, base_url_env, sufixo, token_env
        self.suporta = suporta or {"temperature": True, "top_p": True, "seed": False, "reasoning_effort": False}
        self._client = client
        self.endpoint = modelo

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            base = self._base_url or (os.environ[self._base_env].rstrip("/") + self._sufixo)
            self._client = OpenAI(base_url=base, api_key=os.environ[self._token_env])
        return self._client

    def montar_requisicao(self, req, aplicados: dict) -> dict:
        kw = {
            "model": self.modelo,
            "messages": [{"role": "system", "content": req.system}, {"role": "user", "content": req.user}],
            "max_tokens": aplicados["max_output_tokens"],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": req.schema_id, "schema": req.schema, "strict": True}},
        }
        for p in ("temperature", "top_p", "seed"):
            if p in aplicados:
                kw[p] = aplicados[p]
        return kw

    def _chamar(self, req, aplicados: dict, rec) -> str:
        return self.ler_resposta(self.client.chat.completions.create(**self.montar_requisicao(req, aplicados)), rec)

    @staticmethod
    def ler_resposta(resp, rec) -> str:
        rec.modelo_servido = getattr(resp, "model", None)
        rec.request_id = getattr(resp, "id", None)
        ch = resp.choices[0]
        fr = getattr(ch, "finish_reason", None)
        rec.stop_bruto = fr
        if getattr(ch.message, "refusal", None):
            rec.stop_normalizado = STOP_RECUSA
        elif fr == "length":
            rec.stop_normalizado = STOP_TRUNCADO
        elif fr == "content_filter":
            rec.stop_normalizado = STOP_FILTRO
        else:
            rec.stop_normalizado = STOP_COMPLETO
        u = getattr(resp, "usage", None)
        if u is not None:
            rec.input_tokens = getattr(u, "prompt_tokens", None)
            rec.output_tokens = getattr(u, "completion_tokens", None)
            rec.cache_read_tokens = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", None)
        return ch.message.content or ""
