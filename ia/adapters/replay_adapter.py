"""Adapter SIMULADO: devolve respostas gravadas (fixtures).

Uso: testes automatizados, demonstração sem chave de API e testes de caos (falha forçada).
Toda chamada é registrada com provedor "simulado". Nunca confundir com resultado de modelo real.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import BaseAdapter
from ..telemetria import STOP_COMPLETO, STOP_RECUSA, STOP_TRUNCADO


class ReplayAdapter(BaseAdapter):
    provedor = "simulado"

    def __init__(self, nome: str, fixture: str | Path | dict, familia: str, modelo: str = "replay",
                 falha: str | None = None, suporta: dict | None = None, perimetro: str = "local"):
        """falha: None | "excecao" | "truncado" | "recusa" | "json_invalido"."""
        self.nome, self.familia, self.modelo, self.falha, self.perimetro = nome, familia, modelo, falha, perimetro
        self.fixture = fixture
        self.suporta = suporta or {"temperature": True, "top_p": False, "seed": False, "reasoning_effort": False}
        self.chamadas = 0

    def _chamar(self, req, aplicados: dict, rec) -> str:
        self.chamadas += 1
        if self.falha == "excecao":
            raise ConnectionError("falha simulada do provedor")
        dados = self.fixture if isinstance(self.fixture, dict) else json.loads(Path(self.fixture).read_text("utf-8"))
        texto = json.dumps(dados, ensure_ascii=False)
        rec.modelo_servido = self.modelo
        rec.input_tokens = (len(req.system) + len(req.user)) // 4
        rec.output_tokens = len(texto) // 4
        rec.stop_normalizado, rec.stop_bruto = STOP_COMPLETO, "replay"
        if self.falha == "truncado":
            rec.stop_normalizado, rec.stop_bruto = STOP_TRUNCADO, "max_tokens"
            return texto[: len(texto) // 2]
        if self.falha == "recusa":
            rec.stop_normalizado, rec.stop_bruto = STOP_RECUSA, "refusal"
            return ""
        if self.falha == "json_invalido":
            return texto[:-5]
        return texto
