"""Adapter Anthropic (Messages API, SDK oficial `anthropic`).

Conforme a documentação vigente (nov/2026), para claude-opus-5-5:
- structured outputs: `output_config.format = {"type": "json_schema", "schema": ...}` (`output_format` está depreciado);
- `temperature`/`top_p`/`top_k` são REMOVIDOS (HTTP 400). O adapter não os envia, e a telemetria registra
  "pedido mas não aplicado". O controle de profundidade é `output_config.effort` (padrão `medium` neste modelo; definimos explicitamente);
- thinking é sempre adaptativo (não enviar `thinking: disabled`, que retorna 400);
- `stop_reason`: `end_turn` | `max_tokens` (saída truncada) | `refusal` (HTTP 200, com `stop_details`);
- prompt caching: `cache_control` no bloco de system estável (instruções + contrato), leitura em `usage.cache_read_input_tokens`;
- fallback de recusa no servidor: beta `server-side-fallback-2026-07-01` + `fallbacks: "default"`
  (não suportado no Batches API, Bedrock, Vertex nem Foundry, onde fica desligado por configuração).
  O modelo que de fato respondeu é registrado em `modelo_servido`.
"""
from __future__ import annotations

from . import BaseAdapter
from ..telemetria import STOP_COMPLETO, STOP_RECUSA, STOP_TRUNCADO


class AnthropicAdapter(BaseAdapter):
    provedor = "anthropic"

    def __init__(self, nome: str, modelo: str = "claude-opus-5-5", familia: str = "anthropic",
                 effort: str = "high", server_fallbacks: bool = True, suporta: dict | None = None, client=None,
                 perimetro: str = "externo"):
        self.nome, self.modelo, self.familia = nome, modelo, familia
        self.effort, self.server_fallbacks, self.perimetro = effort, server_fallbacks, perimetro
        self.suporta = suporta or {"temperature": False, "top_p": False, "seed": False, "reasoning_effort": True}
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import anthropic  # import tardio: só quem usa este adapter precisa do SDK
            self._client = anthropic.Anthropic()  # credencial: ANTHROPIC_API_KEY ou perfil `ant auth login`
        return self._client

    def montar_requisicao(self, req, aplicados: dict) -> dict:
        kwargs = {
            "model": self.modelo,
            "max_tokens": aplicados["max_output_tokens"],
            "system": [{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": req.user}],
            "output_config": {
                "effort": aplicados.get("reasoning_effort", self.effort),
                "format": {"type": "json_schema", "schema": req.schema},
            },
        }
        if self.server_fallbacks:
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        return kwargs

    def _chamar(self, req, aplicados: dict, rec) -> str:
        kwargs = self.montar_requisicao(req, aplicados)
        api = self.client.beta.messages if self.server_fallbacks else self.client.messages
        if not self.server_fallbacks:
            kwargs.pop("betas", None)
        resp = api.create(**kwargs)
        return self.ler_resposta(resp, rec)

    @staticmethod
    def ler_resposta(resp, rec) -> str:
        rec.modelo_servido = getattr(resp, "model", None)
        rec.request_id = getattr(resp, "_request_id", None)
        rec.stop_bruto = resp.stop_reason
        if resp.stop_reason == "refusal":
            det = getattr(resp, "stop_details", None)
            rec.stop_normalizado = STOP_RECUSA
            rec.stop_detalhe = getattr(det, "category", None) if det else None
        elif resp.stop_reason == "max_tokens":
            rec.stop_normalizado = STOP_TRUNCADO
        else:
            rec.stop_normalizado = STOP_COMPLETO
        u = resp.usage
        rec.input_tokens = getattr(u, "input_tokens", None)
        rec.output_tokens = getattr(u, "output_tokens", None)          # inclui tokens de raciocínio
        rec.cache_read_tokens = getattr(u, "cache_read_input_tokens", None)
        rec.cache_write_tokens = getattr(u, "cache_creation_input_tokens", None)
        return next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
