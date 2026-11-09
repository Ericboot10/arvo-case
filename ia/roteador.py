"""Roteador da camada de IA: política de dados, circuit breaker, cache por hash, orçamento, fallback e telemetria.

Ordem em cada chamada, para cada adapter da cadeia:
1. POLÍTICA DE DADOS: a classe do dado (req.classe_dados) precisa ser permitida para o perímetro do adapter
   (ia/config/politica_dados.yaml). Se não for, o adapter é pulado e o bloqueio é registrado. Dado identificável nunca sai;
2. CIRCUIT BREAKER: adapter com N falhas consecutivas no run é pulado (não desperdiça tempo nem token num provedor degradado);
3. cache local (chave inclui adapter, modelo, prompt@versão, schema@versão, params e hash da entrada): um hit não gasta token;
4. orçamento: estimativa de tokens ANTES de chamar. Se estourar, bloqueia;
5. adapter; erro, truncamento, recusa ou schema inválido levam ao próximo da cadeia (fallback_de registrado);
6. todo desfecho vira LLMCallRecord no sink.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .ports import LLMPort, LLMRequest, LLMResult
from .telemetria import (STOP_CIRCUITO, STOP_ORCAMENTO, STOP_POLITICA, LLMCallRecord, chave_cache, estimar_custo,
                         novo_registro)

POLITICA_PADRAO = Path(__file__).resolve().parent / "config" / "politica_dados.yaml"


def carregar_politica(caminho: Path | None = None) -> dict:
    return yaml.safe_load(Path(caminho or POLITICA_PADRAO).read_text("utf-8"))


def permitido(politica: dict, classe: str, perimetro: str) -> bool:
    return classe not in politica["nunca"] and classe in politica["permitido"].get(perimetro, [])


@dataclass
class Orcamento:
    max_tokens_run: int
    max_chamadas_run: int
    tokens_usados: int = 0
    chamadas: int = 0

    @staticmethod
    def estimar(req: LLMRequest) -> int:
        return (len(req.system) + len(req.user)) // 3 + req.params.max_output_tokens

    def permite(self, req: LLMRequest) -> bool:
        return (self.chamadas < self.max_chamadas_run
                and self.tokens_usados + self.estimar(req) <= self.max_tokens_run)

    def consumir(self, rec: LLMCallRecord) -> None:
        self.chamadas += 1
        self.tokens_usados += (rec.input_tokens or 0) + (rec.output_tokens or 0)


class CacheRespostas:
    """Cache local em arquivos JSON. No Databricks: tabela Delta ops.llm_cache com a mesma chave."""

    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)

    def ler(self, chave: str) -> dict | None:
        p = self.pasta / f"{chave}.json"
        return json.loads(p.read_text("utf-8")) if p.exists() else None

    def gravar(self, chave: str, dados: dict) -> None:
        (self.pasta / f"{chave}.json").write_text(json.dumps(dados, ensure_ascii=False), "utf-8")


@dataclass
class Roteador:
    sink: object
    orcamento: Orcamento
    cache: CacheRespostas | None = None
    precos: dict = field(default_factory=dict)
    ambiente: str = "dev"
    politica: dict = field(default_factory=carregar_politica)
    limite_falhas_consecutivas: int = 3
    falhas_consecutivas: dict = field(default_factory=dict)

    def _bloqueio(self, req, adapter, stop, erro, anterior):
        rec = novo_registro(req, adapter)
        rec.ambiente, rec.stop_normalizado, rec.schema_valido, rec.erro, rec.fallback_de = \
            self.ambiente, stop, False, erro, anterior
        self.sink.gravar(rec)
        return rec

    def gerar(self, req: LLMRequest, cadeia: list[LLMPort]) -> tuple[LLMResult | None, LLMPort | None]:
        anterior = None
        ultimo: LLMResult | None = None
        for adapter in cadeia:
            perimetro = getattr(adapter, "perimetro", "externo")
            if not permitido(self.politica, req.classe_dados, perimetro):
                rec = self._bloqueio(req, adapter, STOP_POLITICA,
                                     f"classe '{req.classe_dados}' não permitida no perímetro '{perimetro}'", anterior)
                ultimo, anterior = LLMResult(False, None, None, rec.erro, rec), adapter.nome
                continue
            if self.falhas_consecutivas.get(adapter.nome, 0) >= self.limite_falhas_consecutivas:
                rec = self._bloqueio(req, adapter, STOP_CIRCUITO,
                                     f"{self.falhas_consecutivas[adapter.nome]} falhas consecutivas (circuito aberto)", anterior)
                ultimo, anterior = LLMResult(False, None, None, rec.erro, rec), adapter.nome
                continue

            chave = chave_cache(req, adapter)
            if self.cache and (hit := self.cache.ler(chave)) is not None:
                rec = novo_registro(req, adapter)
                rec.ambiente, rec.cache_hit_local, rec.fallback_de = self.ambiente, True, anterior
                rec.stop_normalizado, rec.schema_valido, rec.latencia_ms = "COMPLETO", True, 0.0
                rec.input_tokens = rec.output_tokens = 0
                self.sink.gravar(rec)
                return LLMResult(True, hit, None, None, rec), adapter

            if not self.orcamento.permite(req):
                rec = self._bloqueio(req, adapter, STOP_ORCAMENTO,
                                     f"orçamento: usados {self.orcamento.tokens_usados} + estimados "
                                     f"{self.orcamento.estimar(req)} > {self.orcamento.max_tokens_run} "
                                     f"ou chamadas {self.orcamento.chamadas}/{self.orcamento.max_chamadas_run}", anterior)
                return LLMResult(False, None, None, rec.erro, rec), None

            res = adapter.generate_structured(req)
            res.record.ambiente, res.record.fallback_de = self.ambiente, anterior
            res.record.custo_estimado_usd = estimar_custo(res.record, self.precos)
            self.orcamento.consumir(res.record)
            self.sink.gravar(res.record)
            if res.ok:
                self.falhas_consecutivas[adapter.nome] = 0
                if self.cache:
                    self.cache.gravar(chave, res.data)
                return res, adapter
            self.falhas_consecutivas[adapter.nome] = self.falhas_consecutivas.get(adapter.nome, 0) + 1
            anterior, ultimo = adapter.nome, res
        return ultimo, None
