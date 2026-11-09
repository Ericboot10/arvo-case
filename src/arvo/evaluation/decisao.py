"""Ponto de operação por regra: AUTOMATICO | REVISAO_HUMANA | BLOQUEADO, a partir da matriz de custo e da precisão
(limite inferior do IC 95%). Transforma "priorizar precisão" num critério verificável, e não numa opinião."""
from __future__ import annotations

from pathlib import Path

import yaml

CUSTOS = Path(__file__).resolve().parent / "custos.yaml"


def carregar_custos(caminho: Path | None = None) -> dict:
    return yaml.safe_load(Path(caminho or CUSTOS).read_text("utf-8"))


def decidir(precisao_inf: float, valor_medio: float, c: dict) -> dict:
    c_fp = c["custo_fp_operacional"] + c["custo_fp_atrito_pct"] * valor_medio
    custo_auto = (1 - precisao_inf) * c_fp
    beneficio = precisao_inf * valor_medio
    p_equilibrio_envio = c_fp / (valor_medio + c_fp)           # p acima do qual enviar vale mais que não enviar
    p_equilibrio_auto = max(0.0, 1 - c["custo_revisao_humana"] / c_fp)   # p acima do qual revisar não compensa
    if beneficio <= custo_auto:
        modo = "BLOQUEADO"
    elif precisao_inf >= c["piso_precisao_envio_automatico"] and custo_auto <= c["custo_revisao_humana"]:
        modo = "AUTOMATICO"
    else:
        modo = "REVISAO_HUMANA"
    return {"modo": modo, "custo_fp": round(c_fp, 2), "custo_esperado_auto": round(custo_auto, 2),
            "p_equilibrio_envio": round(p_equilibrio_envio, 4), "p_equilibrio_auto": round(p_equilibrio_auto, 4)}


def tabela(por_regra: list[dict], valor_medio_por_regra: dict[str, float], c: dict | None = None) -> list[dict]:
    c = c or carregar_custos()
    return [{**r, "valor_medio": round(valor_medio_por_regra[r["regra"]], 2),
             **decidir(r["precisao_ic95"][0], valor_medio_por_regra[r["regra"]], c)} for r in por_regra]
