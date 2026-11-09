"""Indicadores de sanidade da camada de IA, calculados da telemetria (LLMCallRecord / ops.llm_calls).

Por tarefa × adapter: qualidade da saída (schema válido, recusa, truncamento, erro), resiliência (fallback, circuito),
governança (bloqueio de política, parâmetro ignorado), custo, tokens, latência e drift de modelo.
Mesmas definições da view SQL ia/databricks/v_ia_sanidade.sql.

  python -m ia.indicadores contratos/runs/PRT-2025-0417/<chave>/llm_calls.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ALERTAS = Path(__file__).resolve().parent / "config" / "alertas_ia.yaml"
BLOQUEIOS = {"BLOQUEADO_POLITICA_DADOS", "BLOQUEADO_CIRCUITO", "BLOQUEADO_ORCAMENTO"}


def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    v = sorted(vals)
    k = (len(v) - 1) * q
    i, f = int(k), k - int(k)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * f


def calcular(registros: list[dict]) -> list[dict]:
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for r in registros:
        grupos[(r["task_id"], r["adapter"])].append(r)
    out = []
    for (task, adapter), rs in sorted(grupos.items()):
        efetivas = [r for r in rs if r["stop_normalizado"] not in BLOQUEIOS and not r.get("cache_hit_local")]
        n, ne = len(rs), len(efetivas)
        taxa = lambda cond, base: (sum(1 for r in base if cond(r)) / len(base)) if base else None  # noqa: E731
        servidos = sorted({r["modelo_servido"] for r in efetivas if r.get("modelo_servido")})
        pedido = rs[0]["modelo_pedido"]
        out.append({
            "task_id": task, "adapter": adapter, "provedor": rs[0]["provedor"], "modelo_pedido": pedido,
            "chamadas": n, "chamadas_efetivas": ne,
            "taxa_schema_valido": taxa(lambda r: r["schema_valido"], efetivas),
            "taxa_recusa": taxa(lambda r: r["stop_normalizado"] == "RECUSA", efetivas),
            "taxa_truncamento": taxa(lambda r: r["stop_normalizado"] == "TRUNCADO", efetivas),
            "taxa_erro": taxa(lambda r: r["stop_normalizado"] == "ERRO", efetivas),
            "taxa_fallback": taxa(lambda r: r.get("fallback_de") is not None, rs),
            "taxa_cache_hit": taxa(lambda r: r.get("cache_hit_local"), rs),
            "taxa_bloqueio_politica": taxa(lambda r: r["stop_normalizado"] == "BLOQUEADO_POLITICA_DADOS", rs),
            "taxa_bloqueio_circuito": taxa(lambda r: r["stop_normalizado"] == "BLOQUEADO_CIRCUITO", rs),
            "pct_param_ignorado": taxa(lambda r: bool(r.get("params_ignorados")), efetivas),
            "latencia_p50_ms": _pct([r["latencia_ms"] for r in efetivas if r.get("latencia_ms") is not None], 0.5),
            "latencia_p95_ms": _pct([r["latencia_ms"] for r in efetivas if r.get("latencia_ms") is not None], 0.95),
            "input_tokens": sum(r.get("input_tokens") or 0 for r in rs),
            "output_tokens": sum(r.get("output_tokens") or 0 for r in rs),
            "cache_read_tokens": sum(r.get("cache_read_tokens") or 0 for r in rs),
            "reasoning_tokens": sum(r.get("reasoning_tokens") or 0 for r in rs),
            "custo_estimado_usd": round(sum(r.get("custo_estimado_usd") or 0 for r in rs), 6),
            "modelos_servidos": servidos,
            "drift_modelo": len(servidos) > 1 or any(s != pedido for s in servidos),
        })
    return out


def alertas(indicadores: list[dict], caminho: Path | None = None) -> list[dict]:
    cfg = yaml.safe_load(Path(caminho or ALERTAS).read_text("utf-8"))
    out = []
    for i in indicadores:
        for nome, lim in cfg["limites"].items():
            v = i.get(nome)
            if v is None:
                continue
            if ("min" in lim and v < lim["min"]) or ("max" in lim and v > lim["max"]):
                out.append({"task_id": i["task_id"], "adapter": i["adapter"], "indicador": nome, "valor": v,
                            "limite": lim, "acao": lim["acao"]})
        if i["drift_modelo"]:
            out.append({"task_id": i["task_id"], "adapter": i["adapter"], "indicador": "drift_modelo",
                        "valor": i["modelos_servidos"], "limite": None, "acao": cfg["drift_modelo"]})
    return out


def main() -> None:
    regs = [json.loads(l) for a in sys.argv[1:] for l in Path(a).read_text("utf-8").splitlines() if l.strip()]
    ind = calcular(regs)
    print(json.dumps({"indicadores": ind, "alertas": alertas(ind)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
