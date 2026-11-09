"""Máquina de estados persistida da extração de contrato (plano v2, F3).

RECEBIDO → PARSEADO → EXTRAIDO → RECONCILIADO → JULGADO → REVISAO_HUMANA → APROVADO | REJEITADO
Qualquer estado pode ir para FALHOU. Transição fora do grafo levanta erro: nada "pula" a revisão humana.
Idempotência: a chave = hash(documento, schema, prompt, config, extratores). Rerodar com a mesma chave retoma o run existente.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

TRANSICOES = {
    "RECEBIDO": {"PARSEADO", "FALHOU"},
    "PARSEADO": {"EXTRAIDO", "FALHOU"},
    "EXTRAIDO": {"RECONCILIADO", "FALHOU"},
    "RECONCILIADO": {"JULGADO", "REVISAO_HUMANA", "FALHOU"},
    "JULGADO": {"REVISAO_HUMANA", "FALHOU"},
    "REVISAO_HUMANA": {"APROVADO", "REJEITADO"},
    "APROVADO": set(),
    "REJEITADO": set(),
    "FALHOU": set(),
}


class TransicaoInvalida(Exception):
    pass


class EstadoExtracao:
    def __init__(self, caminho: Path, chave: str, contrato: str):
        self.caminho = Path(caminho)
        if self.caminho.exists():
            self.dados = json.loads(self.caminho.read_text("utf-8"))
            if self.dados["chave_idempotencia"] != chave:
                raise ValueError("pasta de run pertence a outra chave de idempotência")
        else:
            self.dados = {"contrato": contrato, "chave_idempotencia": chave, "estado": "RECEBIDO",
                          "historico": [{"estado": "RECEBIDO", "ts": time.time(), "detalhe": ""}]}
            self._salvar()

    @property
    def estado(self) -> str:
        return self.dados["estado"]

    def avancar(self, novo: str, detalhe: str = "") -> None:
        if novo not in TRANSICOES[self.estado]:
            raise TransicaoInvalida(f"{self.estado} → {novo} não permitido")
        self.dados["estado"] = novo
        self.dados["historico"].append({"estado": novo, "ts": time.time(), "detalhe": detalhe})
        self._salvar()

    def _salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(json.dumps(self.dados, ensure_ascii=False, indent=2), "utf-8")
