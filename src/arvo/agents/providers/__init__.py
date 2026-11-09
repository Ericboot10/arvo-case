"""Adapters de provedores. ÚNICO lugar do projeto onde SDKs de provedores podem ser importados (import tardio)."""
from __future__ import annotations

import json
import time

from arvo.ai.ports import LLMRequest, LLMResult
from arvo.ai import esquemas
from arvo.ai.telemetria import STOP_COMPLETO, STOP_ERRO, novo_registro


class BaseAdapter:
    """Comportamento comum: telemetria, separação pedido x aplicado, validação do JSON."""

    nome: str
    provedor: str
    familia: str
    modelo: str
    suporta: dict          # {"temperature": bool, "top_p": bool, "seed": bool, "reasoning_effort": bool}
    endpoint: str | None = None
    perimetro: str = "externo"   # seguro por padrão: assume que o dado sai do perímetro

    def _separar_params(self, req: LLMRequest, rec) -> dict:
        aplicados = {"max_output_tokens": req.params.max_output_tokens}
        for nome in ("temperature", "top_p", "seed", "reasoning_effort"):
            v = getattr(req.params, nome)
            if v is None:
                continue
            if self.suporta.get(nome, False):
                aplicados[nome] = v
            else:
                rec.params_ignorados[nome] = f"não suportado por {self.provedor}/{self.modelo} (configuração 'suporta')"
        rec.params_aplicados = aplicados
        return aplicados

    def _resultado(self, req: LLMRequest, rec, texto: str | None, t0: float, erro: str | None = None) -> LLMResult:
        rec.latencia_ms = round((time.time() - t0) * 1000, 1)
        if erro:
            rec.erro, rec.stop_normalizado, rec.schema_valido = erro, rec.stop_normalizado or STOP_ERRO, False
            return LLMResult(False, None, texto, erro, rec)
        if rec.stop_normalizado != STOP_COMPLETO:
            rec.schema_valido = False
            return LLMResult(False, None, texto, f"desfecho {rec.stop_normalizado}: {rec.stop_bruto}", rec)
        try:
            dados = json.loads(texto or "")
        except json.JSONDecodeError as e:
            rec.schema_valido, rec.erros_schema = False, [f"JSON inválido: {e}"]
            return LLMResult(False, None, texto, "JSON inválido", rec)
        erros = esquemas.validar(rec.schema_id, rec.schema_versao, req.schema, dados)
        rec.schema_valido, rec.erros_schema = not erros, erros
        if erros:
            return LLMResult(False, dados, texto, f"schema inválido ({len(erros)} erros)", rec)
        return LLMResult(True, dados, texto, None, rec)

    def generate_structured(self, req: LLMRequest) -> LLMResult:
        rec = novo_registro(req, self)
        aplicados = self._separar_params(req, rec)
        t0 = time.time()
        try:
            texto = self._chamar(req, aplicados, rec)
        except Exception as e:  # o adapter nunca derruba o pipeline: falha vira registro e o roteador faz fallback
            return self._resultado(req, rec, None, t0, erro=f"{type(e).__name__}: {e}")
        return self._resultado(req, rec, texto, t0)

    def _chamar(self, req: LLMRequest, aplicados: dict, rec) -> str:  # pragma: no cover - abstrato
        raise NotImplementedError
