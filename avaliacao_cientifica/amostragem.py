"""Plano amostral da auditoria contínua (shadow F10 e produção), que alimenta gold.fato_auditoria_amostral.

Dois estratos de decisão, porque cada um mede uma coisa:
  GLOSADO      → PRECISÃO por regra: tamanho para ±e com 95% de confiança, com correção de população finita (volume do mês)
  NAO_GLOSADO  → indevido não detectado (estimador de RECALL): amostra estratificada por conceito com mínimo por estrato
Todo item sorteado leva o PESO amostral (N_estrato / n_estrato), e as métricas M10 e M25 são ponderadas. Sem isso, repete-se
o erro do gabarito do case: amostra enriquecida tratada como se fosse aleatória.
"""
from __future__ import annotations

import math

import pandas as pd

from .metricas import Z95


def n_proporcao(p: float, margem: float, N: int | None = None, z: float = Z95) -> int:
    n0 = z * z * p * (1 - p) / (margem * margem)
    if N:
        n0 = n0 / (1 + (n0 - 1) / N)
    return int(math.ceil(n0))


def plano(base: pd.DataFrame, p_precisao: float = 0.98, margem_precisao: float = 0.02,
          p_fn: float = 0.05, margem_fn: float = 0.02, minimo_estrato: int = 10) -> dict:
    gl = base[base.pred]
    ng = base[~base.pred]
    por_regra = {r: {"N": int(len(g)), "n": min(len(g), n_proporcao(p_precisao, margem_precisao, len(g)))}
                 for r, g in gl.groupby("regra_principal")}
    n_ng = n_proporcao(p_fn, margem_fn, len(ng))
    tam = ng.conceito.value_counts()
    alocado = {c: min(int(N), max(minimo_estrato, int(round(n_ng * N / len(ng))))) for c, N in tam.items()}
    return {"glosado_por_regra": por_regra,
            "nao_glosado": {"N": int(len(ng)), "n_total": int(sum(alocado.values())), "por_conceito": alocado},
            "parametros": {"p_precisao": p_precisao, "margem_precisao": margem_precisao, "p_fn": p_fn,
                           "margem_fn": margem_fn, "minimo_estrato": minimo_estrato}}


def selecionar(base: pd.DataFrame, pl: dict, rodada: str, semente: int = 1) -> pd.DataFrame:
    partes = []
    for regra, cfg in pl["glosado_por_regra"].items():
        g = base[base.pred & (base.regra_principal == regra)]
        s = g.sample(cfg["n"], random_state=semente)
        partes.append(s.assign(estrato="GLOSADO", subestrato=regra, peso_amostral=len(g) / cfg["n"]))
    for conceito, n in pl["nao_glosado"]["por_conceito"].items():
        g = base[~base.pred & (base.conceito == conceito)]
        s = g.sample(n, random_state=semente)
        partes.append(s.assign(estrato="NAO_GLOSADO", subestrato=conceito, peso_amostral=len(g) / n))
    out = pd.concat(partes)[["id_item", "estrato", "subestrato", "regra_principal", "peso_amostral"]]
    return out.assign(rodada=rodada).reset_index(drop=True)
