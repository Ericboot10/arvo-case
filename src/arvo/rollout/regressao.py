"""F10 · Regressão entre versões do motor (gate de stg): toda diferença de apontamentos precisa de explicação.

  diff(antes, depois)          → NOVO | REMOVIDO | REGRA_MUDOU | VALOR_MUDOU, por item
  sem_explicacao(diff, expl)   → o que nenhuma explicação cobre (o gate falha se não for vazio)

Explicações = lista versionada junto com a mudança (src/arvo/rollout/explicacoes/<versao>.yaml), cada uma com
`motivo` e um filtro: `tipo`, `regra_antes`, `regra_depois`, `id_item` (lista). Filtro vazio não vale: explicar tudo
de uma vez é não explicar nada.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

CHAVES = ("tipo", "regra_antes", "regra_depois", "id_item")


def diff(antes: pd.DataFrame, depois: pd.DataFrame, tolerancia: float = 0.005) -> pd.DataFrame:
    cols = ["id_item", "regra_principal", "vl_glosado"]
    m = antes[cols].merge(depois[cols], on="id_item", how="outer", suffixes=("_antes", "_depois"), indicator=True)
    m["vl_glosado_antes"] = m.vl_glosado_antes.astype(float)
    m["vl_glosado_depois"] = m.vl_glosado_depois.astype(float)
    tipo = pd.Series(None, index=m.index, dtype=object)
    tipo[m._merge == "right_only"] = "NOVO"
    tipo[m._merge == "left_only"] = "REMOVIDO"
    ambos = m._merge == "both"
    tipo[ambos & (m.regra_principal_antes != m.regra_principal_depois)] = "REGRA_MUDOU"
    tipo[ambos & tipo.isna() & ((m.vl_glosado_antes - m.vl_glosado_depois).abs() > tolerancia)] = "VALOR_MUDOU"
    out = m.assign(tipo=tipo)[tipo.notna()].rename(columns={"regra_principal_antes": "regra_antes",
                                                            "regra_principal_depois": "regra_depois"})
    out["delta_vl"] = out.vl_glosado_depois.fillna(0) - out.vl_glosado_antes.fillna(0)
    return out[["id_item", "tipo", "regra_antes", "regra_depois", "vl_glosado_antes", "vl_glosado_depois", "delta_vl"]] \
        .sort_values(["tipo", "id_item"]).reset_index(drop=True)


def carregar_explicacoes(caminho: Path) -> list[dict]:
    return yaml.safe_load(Path(caminho).read_text("utf-8"))["explicacoes"]


def _cobre(e: dict, linha: pd.Series) -> bool:
    filtros = {k: e[k] for k in CHAVES if k in e}
    if not filtros or not e.get("motivo"):
        raise ValueError(f"explicação sem filtro ou sem motivo: {e}")
    for k, v in filtros.items():
        valores = v if isinstance(v, list) else [v]
        if linha[k] not in valores:
            return False
    return True


def sem_explicacao(d: pd.DataFrame, explicacoes: list[dict]) -> pd.DataFrame:
    if d.empty:
        return d
    coberto = d.apply(lambda ln: any(_cobre(e, ln) for e in explicacoes), axis=1)
    return d[~coberto].reset_index(drop=True)


def resumo(d: pd.DataFrame) -> dict:
    if d.empty:
        return {"diferencas": 0}
    return {"diferencas": int(len(d)), "por_tipo": d.tipo.value_counts().to_dict(),
            "delta_vl_total": round(float(d.delta_vl.sum()), 2)}
