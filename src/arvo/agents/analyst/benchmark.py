"""Benchmark do agente analista: as perguntas de negócio com resposta conhecida, contra três alvos.

  python -m arvo.agents.analyst.benchmark --alvo metrica          # consulta estruturada às metric views (sem modelo)
  python -m arvo.agents.analyst.benchmark --alvo genie            # o Genie sozinho
  python -m arvo.agents.analyst.benchmark --alvo agente [--orquestrador databricks_gpt_oss] [--sem-genie]

A resposta certa é o resultado do SQL de referência (benchmark.yaml), executado no workspace na hora: nada é
escrito à mão. Uma pergunta passa quando cada número de referência aparece na resposta do alvo, com tolerância de
0,5% (relativa) para arredondamento, inclusive na forma percentual (0,0048 = 0,48%).
Grava src/arvo/agents/analyst/RELATORIO_BENCHMARK.md e src/arvo/agents/analyst/benchmark_resultados.json (o último resultado de cada alvo).
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import yaml

from arvo.agents.analyst import RAIZ, carregar_config, construir, space_id

AQUI = Path(__file__).resolve().parent
TOLERANCIA = 0.005
MULTIPLICADORES = {"mil": 1e3, "mi": 1e6, "milhao": 1e6, "milhão": 1e6, "milhoes": 1e6, "milhões": 1e6}


def _num(token: str) -> float | None:
    t = token.strip().rstrip(".,")
    if not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", t) else t.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def numeros_do_texto(texto: str) -> list[float]:
    """Números escritos em pt-BR ou en, com %, 'mil' e 'mi'. Percentual entra também dividido por 100.
    Espaço (comum ou estreito) entre grupos de milhar é aceito: "R$ 39 875,41"."""
    out = []
    texto = re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))", "", texto or "")
    for m in re.finditer(r"(-?\d[\d.,]*)\s*(%|mil\b|mi\b|milh(?:ão|ao|ões|oes)\b)?", texto or "", flags=re.I):
        v = _num(m.group(1))
        if v is None:
            continue
        suf = (m.group(2) or "").lower()
        if suf == "%":
            out += [v, v / 100]
        elif suf in MULTIPLICADORES:
            out += [v * MULTIPLICADORES[suf], v]
        else:
            out.append(v)
    return out


def numeros_das_linhas(linhas: list[list]) -> list[float]:
    out = []
    for r in linhas:
        for c in r:
            try:
                out.append(float(c))
            except (TypeError, ValueError):
                continue
    return out


def confere(ref: float, candidatos: list[float]) -> bool:
    return any(abs(c - ref) <= max(TOLERANCIA * abs(ref), 0.005 if abs(ref) >= 1 else 0.0005) for c in candidatos)


def referencia(executor, pergunta: dict, catalogo: str) -> list[float]:
    cols, linhas = executor.executar(pergunta["sql"].replace("<catalogo>", catalogo))
    idx = [cols.index(c) for c in pergunta["conferir"]]
    return [float(r[i]) for r in linhas[:6] for i in idx if r[i] is not None]


def avaliar(alvo: str, orquestrador: str | None = None, com_genie: bool = True, ids: list[str] | None = None) -> dict:
    from arvo.agents.providers.databricks_dados import DatabricksSQLExecutor, GenieConsultaAdapter, warehouse_por_nome
    from arvo.agents.analyst import semantica

    cfg = carregar_config()
    db, perfil = cfg["databricks"], cfg["databricks"].get("perfil") or None
    executor = DatabricksSQLExecutor(warehouse_por_nome(db["warehouse"], perfil), db["catalogo"], perfil)
    bench = yaml.safe_load((AQUI / "benchmark.yaml").read_text("utf-8"))["perguntas"]
    bench = [b for b in bench if not ids or b["id"] in ids]
    catalogo_sem = semantica.carregar_catalogo()
    genie = agente = None
    if alvo == "genie":
        sid = space_id(cfg)
        if not sid:
            raise SystemExit("espaço Genie não publicado: rode `python -m arvo.agents.genie.space publicar`")
        genie = GenieConsultaAdapter(sid, perfil)
    if alvo == "agente":
        agente = construir(cfg, orquestrador=orquestrador, com_genie=com_genie)
    resultados = []
    for b in bench:
        ref = referencia(executor, b, db["catalogo"])
        t0, detalhe = time.time(), {}
        if alvo == "metrica":
            if not b.get("metrica"):
                continue
            m = b["metrica"]
            sql = semantica.montar_sql(catalogo_sem, m["view"], m["medidas"], m["dimensoes"], m["filtros"],
                                       m["ordenar_por"], True, m["limite"], db["catalogo"])
            cand = numeros_das_linhas(executor.executar(sql)[1])
            detalhe = {"sql": sql}
        elif alvo == "genie":
            r = genie.consultar(b["pergunta"])
            cand = numeros_das_linhas(r.linhas) + numeros_do_texto(r.texto or "")
            detalhe = {"sql": r.sql, "erro": r.erro, "linhas": r.linhas[:6]}
        else:
            r = agente.perguntar(b["pergunta"])
            cand = numeros_do_texto(r.texto)
            detalhe = {"resposta": r.texto, "modelos": r.modelos, "ferramentas": [x["ferramenta"] for x in r.rastro],
                       "erro": r.erro}
        faltando = [v for v in ref if not confere(v, cand)]
        resultados.append({"id": b["id"], "pergunta": b["pergunta"], "passou": bool(ref) and not faltando,
                           "referencia": ref, "faltando": faltando,
                           "latencia_s": round(time.time() - t0, 1), **detalhe})
        print(f"{b['id']} {'ok  ' if resultados[-1]['passou'] else 'FALHOU'} {b['pergunta'][:70]}", flush=True)
    rotulo = alvo if alvo != "agente" else f"agente ({orquestrador or 'cadeia'}{', sem Genie' if not com_genie else ''})"
    return {"alvo": rotulo, "executado_em": time.strftime("%Y-%m-%d %H:%M"), "resultados": resultados,
            "acertos": sum(r["passou"] for r in resultados), "total": len(resultados)}


def gravar(res: dict) -> None:
    arq = AQUI / "benchmark_resultados.json"
    todos = json.loads(arq.read_text("utf-8")) if arq.exists() else {}
    todos[res["alvo"]] = res
    arq.write_text(json.dumps(todos, ensure_ascii=False, indent=2, default=str) + "\n", "utf-8")
    linhas = ["# Benchmark do agente analista", "",
              "Gerado por `python -m arvo.agents.analyst.benchmark`. A resposta certa de cada pergunta é o resultado do SQL de "
              "referência em `src/arvo/agents/analyst/benchmark.yaml`, executado no workspace com os dados do case.", "",
              "| Alvo | Acertos | Executado em |", "|---|---|---|"]
    for r in todos.values():
        linhas.append(f"| {r['alvo']} | {r['acertos']}/{r['total']} | {r['executado_em']} |")
    for r in todos.values():
        linhas += ["", f"## {r['alvo']}", "", "| Pergunta | Resultado | Referência | Faltou | Tempo |", "|---|---|---|---|---|"]
        for x in r["resultados"]:
            ref = ", ".join(f"{v:.6g}" for v in x["referencia"])
            falta = ", ".join(f"{v:.6g}" for v in x["faltando"]) or "—"
            linhas.append(f"| {x['id']} · {x['pergunta']} | {'✅' if x['passou'] else '❌'} | {ref} | {falta} | "
                          f"{x['latencia_s']} s |")
    (AQUI / "RELATORIO_BENCHMARK.md").write_text("\n".join(linhas) + "\n", "utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alvo", choices=["metrica", "genie", "agente"], required=True)
    ap.add_argument("--orquestrador")
    ap.add_argument("--sem-genie", action="store_true")
    ap.add_argument("--ids", nargs="*")
    a = ap.parse_args()
    res = avaliar(a.alvo, a.orquestrador, not a.sem_genie, a.ids)
    gravar(res)
    print(f"{res['alvo']}: {res['acertos']}/{res['total']}")
