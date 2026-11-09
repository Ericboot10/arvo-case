"""Catálogo semântico do agente: o que pode ser perguntado, lido da camada semântica PUBLICADA.

Fonte: semantic/databricks/02_metric_views.sql (gerado de semantic/metricas.yaml). Só entram as metric views ativas
(não comentadas), com as suas dimensões e medidas. É a "descoberta estruturada": o modelo só consegue pedir
medida e dimensão que existem, e o SQL é montado por código, nunca escrito pelo modelo.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
METRIC_VIEWS = RAIZ / "semantic" / "databricks" / "02_metric_views.sql"
SCHEMA = "semantic"
LIMITE_MAXIMO = 50


@dataclass
class MetricView:
    nome: str
    descricao: str
    fonte: str
    dimensoes: dict[str, str] = field(default_factory=dict)   # nome -> comentário
    medidas: dict[str, str] = field(default_factory=dict)     # nome -> comentário (começa com o id Mxx)


def carregar_catalogo(caminho: Path = METRIC_VIEWS) -> dict[str, MetricView]:
    sql = Path(caminho).read_text("utf-8")
    ativo = "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))
    out: dict[str, MetricView] = {}
    padrao = r"CREATE OR REPLACE VIEW (\w+)\s+COMMENT '([^']*)'\s+WITH METRICS LANGUAGE YAML AS \$\$(.*?)\$\$"
    for nome, comentario, corpo in re.findall(padrao, ativo, flags=re.S):
        y = yaml.safe_load(corpo)
        out[nome] = MetricView(
            nome=nome, descricao=comentario, fonte=y["source"],
            dimensoes={d["name"]: d.get("comment", "") for d in y.get("dimensions", y.get("fields", []))},
            medidas={m["name"]: m.get("comment", "") for m in y.get("measures", [])})
    return out


def descrever(catalogo: dict[str, MetricView]) -> str:
    """Texto estável (mesma ordem sempre) para o prompt do orquestrador: entra no prefixo em cache."""
    linhas = []
    for v in sorted(catalogo.values(), key=lambda v: v.nome):
        linhas.append(f"### {v.nome} ({v.descricao}; fonte {v.fonte})")
        linhas.append("dimensões: " + ", ".join(sorted(v.dimensoes)))
        for m in sorted(v.medidas):
            linhas.append(f"- medida `{m}`: {v.medidas[m]}")
    return "\n".join(linhas)


class ConsultaInvalida(ValueError):
    pass


def _literal(valor) -> str:
    return "'" + str(valor).replace("\\", "\\\\").replace("'", "''") + "'"


def montar_sql(catalogo: dict[str, MetricView], view: str, medidas: list[str], dimensoes: list[str],
               filtros: list[dict], ordenar_por: str = "", decrescente: bool = True, limite: int = 20,
               catalogo_uc: str | None = None) -> str:
    """SELECT <dimensões>, MEASURE(<medidas>) FROM semantic.<view> [WHERE ...] GROUP BY ALL [ORDER BY] LIMIT n.
    Todo nome é conferido contra o catálogo; os valores de filtro entram como literal com aspas escapadas."""
    if view not in catalogo:
        raise ConsultaInvalida(f"view '{view}' não existe. Views: {sorted(catalogo)}")
    v = catalogo[view]
    if not medidas:
        raise ConsultaInvalida("informe ao menos uma medida")
    for m in medidas:
        if m not in v.medidas:
            raise ConsultaInvalida(f"medida '{m}' não existe em {view}. Medidas: {sorted(v.medidas)}")
    for d in dimensoes + [f["dimensao"] for f in filtros]:
        if d not in v.dimensoes:
            raise ConsultaInvalida(f"dimensão '{d}' não existe em {view}. Dimensões: {sorted(v.dimensoes)}")
    if ordenar_por and ordenar_por not in set(medidas) | set(dimensoes):
        raise ConsultaInvalida("ordenar_por precisa ser uma das medidas ou dimensões pedidas")
    limite = max(1, min(int(limite or LIMITE_MAXIMO), LIMITE_MAXIMO))
    origem = f"{catalogo_uc + '.' if catalogo_uc else ''}{SCHEMA}.{view}"
    campos = [f"`{d}`" for d in dimensoes] + [f"MEASURE(`{m}`) AS `{m}`" for m in medidas]
    sql = f"SELECT {', '.join(campos)}\nFROM {origem}"
    if filtros:
        sql += "\nWHERE " + " AND ".join(f"`{f['dimensao']}` = {_literal(f['valor'])}" for f in filtros)
    if dimensoes:
        sql += "\nGROUP BY ALL"
    if ordenar_por:
        sql += f"\nORDER BY `{ordenar_por}` {'DESC' if decrescente else 'ASC'}"
    return sql + f"\nLIMIT {limite}"


# --------------------------------------------------------------------------------------------- glossário e decisões
def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def entradas_semanticas() -> list[dict]:
    """Glossário, conceitos, métricas e decisões AMB como uma lista pesquisável."""
    sem = RAIZ / "semantic"
    out = []
    for t in yaml.safe_load((sem / "glossario.yaml").read_text("utf-8"))["termos"]:
        out.append({"tipo": "termo", "id": t["id"], "nome": t["termo"], "texto": t["definicao"],
                    "extra": {k: t[k] for k in ("sinonimos", "nao_confundir_com", "fonte", "pendencias") if k in t}})
    for c in yaml.safe_load((sem / "conceitos.yaml").read_text("utf-8"))["conceitos"]:
        out.append({"tipo": "conceito", "id": c["id"], "nome": c["id"], "texto": c.get("definicao", ""),
                    "extra": {"pai": c.get("pai")}})
    for m in yaml.safe_load((sem / "metricas.yaml").read_text("utf-8"))["metricas"]:
        out.append({"tipo": "metrica", "id": m["id"], "nome": m["nome"], "texto": m.get("definicao", ""),
                    "extra": {"formula": m.get("formula"), "disponibilidade": m.get("disponibilidade"),
                              "meta": m.get("meta")}})
    for r in yaml.safe_load((RAIZ / "motor" / "regras.yaml").read_text("utf-8"))["regras"]:
        out.append({"tipo": "regra", "id": r["id"], "nome": r["nome"],
                    "texto": f"cláusula {r['clausula']}; glosa {r['tipo_glosa']}; defensabilidade em recurso: "
                             f"{r.get('defensabilidade')}",
                    "extra": {"clausulas_base": r.get("clausulas_base"), "prioridade": r.get("prioridade")}})
    for ln in (sem / "decision_log.md").read_text("utf-8").splitlines():
        cel = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cel) >= 5 and re.fullmatch(r"AMB-\d+", cel[0]):
            out.append({"tipo": "decisao", "id": cel[0], "nome": cel[1], "texto": f"afeta: {cel[2]}",
                        "extra": {"donos": cel[3], "status": cel[4]}})
    return out


def buscar(termo: str, entradas: list[dict] | None = None, limite: int = 8) -> list[dict]:
    entradas = entradas if entradas is not None else entradas_semanticas()
    # radical simples: "defensável" acha "defensabilidade", "recursos" acha "recurso"
    palavras = [p[:6] if len(p) > 6 else p for p in re.findall(r"\w+", _norm(termo)) if len(p) > 2]
    if not palavras:
        return []
    pontuadas = []
    for e in entradas:
        nome, corpo = _norm(e["id"] + " " + e["nome"]), _norm(e["texto"] + " " + str(e["extra"]))
        p = sum(3 * (w in nome) + (w in corpo) for w in palavras)
        if p:
            pontuadas.append((p, e))
    pontuadas.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [e for _, e in pontuadas[:limite]]
