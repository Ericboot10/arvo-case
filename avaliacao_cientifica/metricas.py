"""F8 · Métricas de avaliação com incerteza explícita.

Princípio do comitê: métrica sem intervalo de confiança não vai para decisão.
- Wilson para proporções (precisão e recall em contagem);
- bootstrap POR CONTA (cluster) para métricas ponderadas por R$ e para a estimativa populacional, porque itens da
  mesma conta não são independentes (a regra de pacote é no nível da conta);
- estimativa POPULACIONAL reponderada por estrato (código TUSS), porque o gabarito é uma amostra ENRIQUECIDA
  (ex.: taxa de urgência = 11,4% do gabarito x 6,5% do sinistro). Premissa explícita: dentro de cada estrato, os itens
  rotulados são uma amostra aleatória dos itens do estrato. Se a seleção do gabarito tiver outro critério, a
  estimativa populacional é inválida (registrado no relatório).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def matriz(df: pd.DataFrame) -> dict:
    """df: colunas booleanas `pred` (motor glosou) e `real` (rótulo indevido)."""
    tp = int((df.pred & df.real).sum())
    fp = int((df.pred & ~df.real).sum())
    fn = int((~df.pred & df.real).sum())
    tn = int((~df.pred & ~df.real).sum())
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn}


def precisao_recall(m: dict) -> dict:
    tp, fp, fn = m["TP"], m["FP"], m["FN"]
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * p * r / (p + r) if p == p and r == r and p + r else float("nan")
    return {"precisao": p, "precisao_ic95": wilson(tp, tp + fp), "recall": r, "recall_ic95": wilson(tp, tp + fn),
            "f1": f1, **m}


def _valor(df: pd.DataFrame) -> dict:
    """Ponderado por R$: TP e FP pelo valor GLOSADO; FN pelo valor COBRADO (teto do que poderia ter sido glosado)."""
    tp = df.loc[df.pred & df.real, "vl_glosado"].sum()
    fp = df.loc[df.pred & ~df.real, "vl_glosado"].sum()
    fn = df.loc[~df.pred & df.real, "vl_cobrado"].sum()
    return {"precisao_rs": tp / (tp + fp) if tp + fp else float("nan"),
            "recall_rs_limite_inferior": tp / (tp + fn) if tp + fn else float("nan"),
            "vl_tp": float(tp), "vl_fp": float(fp), "vl_fn_cobrado": float(fn)}


def bootstrap_cluster(df: pd.DataFrame, estat, n: int = 2000, semente: int = 7, cluster: str = "id_conta") -> tuple:
    rng = np.random.default_rng(semente)
    grupos = {k: g for k, g in df.groupby(cluster)}
    chaves = np.array(list(grupos))
    vals = []
    for _ in range(n):
        amostra = pd.concat([grupos[k] for k in rng.choice(chaves, size=len(chaves), replace=True)])
        v = estat(amostra)
        if v == v:
            vals.append(v)
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (float("nan"),) * 2


def avaliar_amostra(rotulados: pd.DataFrame, bootstrap: int = 2000) -> dict:
    m = precisao_recall(matriz(rotulados))
    v = _valor(rotulados)
    v["precisao_rs_ic95"] = bootstrap_cluster(rotulados, lambda d: _valor(d)["precisao_rs"], bootstrap)
    v["recall_rs_ic95"] = bootstrap_cluster(rotulados, lambda d: _valor(d)["recall_rs_limite_inferior"], bootstrap)
    return {**m, **v}


def por_regra(rotulados: pd.DataFrame) -> list[dict]:
    """Precisão por regra (entre os itens que a regra glosou). Recall por regra não existe: o gabarito não diz a regra."""
    out = []
    for regra, g in rotulados[rotulados.pred].groupby("regra_principal"):
        tp, n = int(g.real.sum()), len(g)
        out.append({"regra": regra, "glosados_rotulados": n, "confirmados": tp, "precisao": tp / n,
                    "precisao_ic95": wilson(tp, n), "vl_glosado_rotulado": float(g.vl_glosado.sum())})
    return out


def estimativa_populacional(pop: pd.DataFrame, rotulados: pd.DataFrame, estrato: str | list[str] = "cod_tuss",
                            bootstrap: int = 2000, semente: int = 11) -> dict:
    """Horvitz–Thompson estratificado: peso do item rotulado = N_estrato / n_estrato.

    Teste de validade embutido: com os pesos, a amostra deve reproduzir o nº de glosas que o motor faz na população
    (`glosas_estimadas_pela_amostra` ≈ `glosas_reais_do_motor`). Se não reproduzir, a seleção do gabarito depende
    de algo além do estrato e a estimativa é inválida. Pós-estratificar por ["cod_tuss", "pred"] corrige a dependência
    da decisão do motor, que é conhecida para toda a população.
    """
    if isinstance(estrato, list):
        pop = pop.assign(_estrato=pop[estrato].astype(str).agg("|".join, axis=1))
        rotulados = rotulados.assign(_estrato=rotulados[estrato].astype(str).agg("|".join, axis=1))
        estrato = "_estrato"
    N = pop.groupby(estrato).size()
    n = rotulados.groupby(estrato).size()
    cobertos = n.index
    peso = (N[cobertos] / n).rename("peso")
    r = rotulados.join(peso, on=estrato)

    def est(d):
        tp = (d.peso * (d.pred & d.real)).sum()
        fp = (d.peso * (d.pred & ~d.real)).sum()
        fn = (d.peso * (~d.pred & d.real)).sum()
        return tp, fp, fn

    tp, fp, fn = est(r)
    rng = np.random.default_rng(semente)
    ps, rs = [], []
    for _ in range(bootstrap):     # bootstrap estratificado, reamostrando dentro de cada estrato
        amostra = pd.concat([g.sample(len(g), replace=True, random_state=int(rng.integers(1e9)))
                             for _, g in r.groupby(estrato)])
        a, b, c = est(amostra)
        if a + b:
            ps.append(a / (a + b))
        if a + c:
            rs.append(a / (a + c))
    pred_estimado = float((r.peso * r.pred).sum())
    pred_real = int(pop.loc[pop[estrato].isin(cobertos), "pred"].sum())
    return {"valida": abs(pred_estimado - pred_real) <= 0.05 * max(pred_real, 1),
            "precisao": tp / (tp + fp), "precisao_ic95": (float(np.percentile(ps, 2.5)), float(np.percentile(ps, 97.5))),
            "recall": tp / (tp + fn), "recall_ic95": (float(np.percentile(rs, 2.5)), float(np.percentile(rs, 97.5))),
            "estratos_cobertos": int(len(cobertos)), "estratos_total": int(len(N)),
            "itens_populacao_cobertos": int(N[cobertos].sum()), "itens_populacao": int(len(pop)),
            "glosas_estimadas_pela_amostra": pred_estimado, "glosas_reais_do_motor": pred_real,
            "indevidos_estimados_populacao": float(tp + fn)}


def enriquecimento(pop: pd.DataFrame, rotulados: pd.DataFrame, estrato: str = "cod_tuss") -> pd.DataFrame:
    a = pop[estrato].value_counts(normalize=True).rename("populacao")
    b = rotulados[estrato].value_counts(normalize=True).rename("gabarito")
    t = pd.concat([a, b], axis=1).fillna(0)
    t["razao"] = t.gabarito / t.populacao
    return t.sort_values("razao", ascending=False)


def kappa(a: list, b: list) -> float:
    """Cohen's κ entre dois revisores."""
    cats = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0
