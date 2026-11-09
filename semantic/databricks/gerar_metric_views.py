"""Gera 02_metric_views.sql a partir de semantic/metricas.yaml + arquitetura/modelo.yaml.

Uma metric view por tabela de origem declarada no modelo (tipo metric_view). Campos = dimensões permitidas pelas
métricas daquela tabela. Medidas = as métricas. Assim a fórmula existe em UM lugar só (metricas.yaml).
Sintaxe (doc Databricks, nov/2026): CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML, version 1.1, com
fields/measures e name, expr, comment, display_name e synonyms (até 10).

Rodar a partir de Arvo_Case:  python -m semantic.databricks.gerar_metric_views
"""
from __future__ import annotations

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = Path(__file__).resolve().parent / "02_metric_views.sql"

CABECALHO = """-- =====================================================================================================
-- 02 · UC Metric Views. GERADO por `python -m semantic.databricks.gerar_metric_views`. NÃO EDITE À MÃO.
-- Fonte: semantic/metricas.yaml (fórmulas, dimensões, níveis) + arquitetura/modelo.yaml (view ↔ tabela).
-- Consulta: SELECT <campo>, MEASURE(<medida>) FROM <view> GROUP BY ALL
-- Ref.: https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference
-- Cada view depende da sua tabela gold. Views com status futuro/especificado só criam depois da fase indicada.
-- AMBIENTE: parâmetro :catalog = arvo_dev | arvo_stg | arvo_prod
-- =====================================================================================================

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA semantic;
"""


def _q(s: str) -> str:
    return '"' + " ".join(str(s).split()).replace('"', "'") + '"'


def gerar() -> str:
    met = yaml.safe_load((RAIZ / "semantic" / "metricas.yaml").read_text("utf-8"))
    mod = yaml.safe_load((RAIZ / "arquitetura" / "modelo.yaml").read_text("utf-8"))
    dims = {d["id"]: d for d in met["dimensoes"]}
    partes = [CABECALHO]
    views = [(tid, t) for tid, t in mod["tabelas"].items() if t["tipo"] == "metric_view"]
    for tid, t in views:
        fonte = t["origem"][0]                       # gold.<tabela>
        tabela = fonte.split(".", 1)[1]
        ms = [m for m in met["metricas"] if m["tabela"] == tabela]
        campos = sorted({d for m in ms for d in m["dimensoes"]}, key=lambda x: list(dims).index(x))
        nome_view = tid.split(".", 1)[1]
        L = ["", "-- " + "-" * 101, f"-- {nome_view} · fonte {fonte} · status {t['status']} ({t.get('fase', '')})",
             "-- " + "-" * 101,
             f"CREATE OR REPLACE VIEW {nome_view}",
             f"COMMENT {_q(t['grao']).replace(chr(34), chr(39))}",
             "WITH METRICS LANGUAGE YAML AS $$", "version: 1.1", f"source: {fonte}", "fields:"]
        for c in campos:
            d = dims[c]
            L += [f"  - name: {c}", f"    expr: {c}", f"    comment: {_q(d['descricao'])}"]
            if d.get("sinonimos"):
                L.append("    synonyms: [" + ", ".join(d["sinonimos"][:10]) + "]")
        L.append("measures:")
        for m in ms:
            L += [f"  - name: {m['nome']}", f"    expr: {m['formula']}",
                  f"    comment: {_q(m['id'] + ' · ' + m['nivel'] + ' · ' + m['definicao'])}"]
        L.append("$$;")
        st_fonte = mod["tabelas"].get(fonte, {}).get("status")
        if st_fonte != "implementado":   # o arquivo inteiro precisa ser executável hoje (job F9)
            cab, corpo = L[:4], L[4:]
            L = cab + [f"-- PENDENTE: a fonte {fonte} está com status '{st_fonte}'. Descomente quando ela existir."] \
                + ["-- " + x for x in corpo]
        partes.append("\n".join(L))
    return "\n".join(partes) + "\n"


def main() -> None:
    SAIDA.write_text(gerar(), "utf-8")
    print("gerado", SAIDA)


if __name__ == "__main__":
    main()
