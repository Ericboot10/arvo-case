"""Gera TODA a documentação de arquitetura a partir de arquitetura/modelo.yaml (+ semantic/metricas.yaml e perguntas).

Saídas (nunca editar à mão):
  arquitetura/ARQUITETURA.md     Mermaid (renderiza no GitHub/VS Code) + catálogo de tabelas + rastreabilidade
  arquitetura/arquitetura.drawio duas páginas (linhagem do medalhão, estrela gold), para apresentação e edição visual
  arquitetura/grafo.json         nós e arestas (tabela, métrica, pergunta, persona) para consulta e impacto

Rodar a partir de Arvo_Case:  python -m arquitetura.gerar
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import yaml

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent

CORES = {  # por tipo (draw.io). O status muda a borda
    "fonte": "#E8E8E8", "raw": "#D9C3A5", "quarentena": "#F4B6B6", "conformada": "#C9D6E3", "semantica": "#D5E8D4",
    "contrato": "#E1D5E7", "dimensao": "#FFE6CC", "fato_transacao": "#FFD966", "fato_snapshot_periodico": "#FFD966",
    "fato_snapshot_acumulado": "#FFD966", "metric_view": "#B9E0A5", "operacao": "#F5F5F5", "ponte": "#F8CECC",
}
BORDA = {"implementado": ("#333333", "0"), "especificado": ("#666666", "1"), "futuro": ("#999999", "1")}


def carregar() -> dict:
    m = yaml.safe_load((AQUI / "modelo.yaml").read_text("utf-8"))
    met = yaml.safe_load((RAIZ / "semantic" / "metricas.yaml").read_text("utf-8"))
    per = yaml.safe_load((RAIZ / "semantic" / "perguntas_negocio.yaml").read_text("utf-8"))
    return {"modelo": m, "metricas": met, "perguntas": per}


def _mid(t: str) -> str:
    return t.replace(".", "__")


def _tipo_simples(t: str) -> str:
    return re.sub(r"[<(].*", "", t)


# ---------------------------------------------------------------------------------------------- grafo
def construir_grafo(d: dict) -> dict:
    m, met, per = d["modelo"], d["metricas"], d["perguntas"]
    nos, arestas = [], []
    for tid, t in m["tabelas"].items():
        nos.append({"id": tid, "no": "tabela", "camada": t["camada"], "tipo": t["tipo"], "status": t["status"],
                    "fase": t.get("fase"), "grao": t.get("grao"), "lgpd": t.get("lgpd", [])})
        for o in t.get("origem", []):
            arestas.append({"de": o, "para": tid, "rel": "deriva_de"})
        for col, alvo in (t.get("fks") or {}).items():
            arestas.append({"de": tid, "para": alvo.rsplit(".", 1)[0], "rel": "fk", "coluna": col})
    # cada métrica é servida pela metric view cuja origem é a tabela da métrica (derivado do modelo)
    mv_por_tabela = {t["origem"][0].split(".", 1)[1]: tid for tid, t in m["tabelas"].items() if t["tipo"] == "metric_view"}
    for mm in met["metricas"]:
        mid = f"metrica.{mm['id']}"
        nos.append({"id": mid, "no": "metrica", "nome": mm["nome"], "nivel": mm["nivel"],
                    "disponibilidade": mm["disponibilidade"], "dono": mm["dono"]})
        alvo = mv_por_tabela.get(mm["tabela"], f"gold.{mm['tabela']}")
        arestas.append({"de": alvo, "para": mid, "rel": "mede"})
    personas = set()
    for q in per["perguntas"]:
        qid = f"pergunta.{q['id']}"
        nos.append({"id": qid, "no": "pergunta", "texto": q["pergunta"], "disponibilidade": q["disponibilidade"]})
        for mid in q["metricas"]:
            arestas.append({"de": f"metrica.{mid}", "para": qid, "rel": "responde"})
        p = q["persona"].split(" (")[0]
        personas.add(p)
        arestas.append({"de": qid, "para": f"persona.{p}", "rel": "interessa_a"})
    nos += [{"id": f"persona.{p}", "no": "persona"} for p in sorted(personas)]
    return {"versao_modelo": m["versao"], "nos": nos, "arestas": arestas}


# ---------------------------------------------------------------------------------------------- markdown
def gerar_md(d: dict, g: dict) -> str:
    m = d["modelo"]
    T = m["tabelas"]
    L = ["<!-- GERADO por `python -m arquitetura.gerar` a partir de arquitetura/modelo.yaml. NÃO EDITE À MÃO. -->",
         f"# Arquitetura de dados: {m['projeto']}", "",
         "Fonte da verdade: [`modelo.yaml`](modelo.yaml). Diagrama editável: [`arquitetura.drawio`](arquitetura.drawio). "
         "Grafo consultável: [`grafo.json`](grafo.json) (`python -m arquitetura.consultar`).", "",
         "**Legenda de status:** borda contínua = implementado · tracejada = especificado/futuro (fase indicada).", "",
         "| Camada | Papel |", "|---|---|"]
    camadas = sorted(m["camadas"].items(), key=lambda kv: kv[1]["ordem"])
    L += [f"| `{cam}` | {info['descricao']} |" for cam, info in camadas]
    L += ["", "## 1. Linhagem do medalhão", "", "```mermaid", "flowchart LR"]
    for cam, info in camadas:
        ids = [tid for tid, t in T.items() if t["camada"] == cam]
        if not ids:
            continue
        L.append(f'  subgraph {cam}["{cam}"]')
        for tid in ids:
            t = T[tid]
            forma = ("[(", ")]") if t["tipo"] == "fonte" else ("[[", "]]") if t["tipo"].startswith("fato") else ("[", "]")
            rot = f"{tid}<br/><i>{t['status']}{' · ' + t['fase'] if t.get('fase') else ''}</i>"
            L.append(f'    {_mid(tid)}{forma[0]}"{rot}"{forma[1]}')
        L.append("  end")
    for a in g["arestas"]:
        if a["rel"] == "deriva_de" and a["de"] in T:
            seta = "-->" if T[a["para"]]["status"] == "implementado" else "-.->"
            L.append(f"  {_mid(a['de'])} {seta} {_mid(a['para'])}")
    for tid, t in T.items():
        if t["status"] != "implementado":
            L.append(f"  style {_mid(tid)} stroke-dasharray: 5 5")
    L += ["```", "", "## 2. Modelo dimensional (gold)", "",
          "Estrela: fatos no centro, dimensões conformadas ao redor. `fato_item` (F5) é a base. `fato_item_auditado` e "
          "`fato_apontamento` (F6) adicionam o resultado do motor de regras.", "", "```mermaid", "erDiagram"]
    gold = {tid: t for tid, t in T.items() if t["camada"] == "gold"}
    for tid, t in gold.items():
        fks = set((t.get("fks") or {}).keys())
        L.append(f"  {_mid(tid)} {{")
        for col, tipo in (t.get("colunas") or {}).items():
            marca = " PK" if col in t.get("chave", []) else (" FK" if col in fks else "")
            L.append(f"    {_tipo_simples(tipo)} {col}{marca}")
        L.append("  }")
    for tid, t in gold.items():
        for col, alvo in (t.get("fks") or {}).items():
            dim = alvo.rsplit(".", 1)[0]
            if dim in gold:
                L.append(f'  {_mid(dim)} ||--o{{ {_mid(tid)} : "{col}"')
    L += ["```", "", "## 3. Catálogo de tabelas", "",
          "| Tabela | Tipo | Grão | Chave | Status | Fase | Origem |", "|---|---|---|---|---|---|---|"]
    for tid, t in T.items():
        extra = f" (SCD {t['scd']})" if "scd" in t else ""
        lg = " 🔒" if t.get("lgpd") else ""
        L.append(f"| `{tid}`{lg} | {t['tipo']}{extra} | {t.get('grao', t.get('descricao', ''))} | "
                 f"{', '.join(t.get('chave', [])) or '—'} | {t['status']} | {t.get('fase', '—')} | "
                 f"{', '.join(f'`{o}`' for o in t.get('origem', [])) or '—'} |")
    L += ["", "🔒 = contém identificador de pessoa (LGPD): máscara obrigatória em stg/prod (`plataforma/lgpd`).", ""]
    # ---- indicadores gold (árvore do norte + catálogo por nível)
    arv = d["metricas"]["arvore_norte"]
    metr = {mm["id"]: mm for mm in d["metricas"]["metricas"]}
    nome = lambda i: f"{i} {metr[i]['nome']}"
    L += ["## 4. Indicadores gold", "", f"**Identidade:** {arv['identidade']}", "", "```mermaid", "flowchart LR",
          f'  N["{nome(arv["norte"])}<br/>meta {metr[arv["norte"]].get("meta", "")}"]']
    for f in arv["fatores"]:
        L.append(f'  {f}["{nome(f)}"] --> N')
    L.append('  subgraph G["guardrails"]')
    L += [f'    {g}["{nome(g)}"]' for g in arv["guardrails"]]
    L += ["  end", "  G -. limita .-> N", "```", "",
          "| Nível | Métrica | Definição | Fonte | Disponível | Meta/alerta |", "|---|---|---|---|---|---|"]
    ordem = ["norte", "meta", "fator", "guardrail", "diagnostico", "sanidade", "base"]
    for mm in sorted(d["metricas"]["metricas"], key=lambda x: (ordem.index(x["nivel"]), x["id"])):
        L.append(f"| {mm['nivel']} | **{mm['id']}** {mm['nome']} | {' '.join(mm['definicao'].split())} | "
                 f"`{mm['tabela']}` | {mm['disponibilidade']} | {mm.get('meta') or mm.get('alerta') or '—'} |")
    L += ["", "## 5. Rastreabilidade: persona → pergunta → métrica → tabela", "",
          "| Persona | Pergunta | Métricas | Fonte gold | Disponível |", "|---|---|---|---|---|"]
    met = {mm["id"]: mm for mm in d["metricas"]["metricas"]}
    for q in d["perguntas"]["perguntas"]:
        fontes = sorted({met[x]["tabela"] for x in q["metricas"]})
        L.append(f"| {q['persona']} | {q['pergunta']} | {', '.join(q['metricas'])} | {', '.join(fontes)} | {q['disponibilidade']} |")
    L += ["", "## 6. Colunas por tabela", ""]
    for tid, t in T.items():
        if not t.get("colunas"):
            continue
        fks = t.get("fks") or {}
        L += [f"<details><summary><code>{tid}</code> · {t.get('grao', '')}</summary>", "",
              "| Coluna | Tipo | Papel |", "|---|---|---|"]
        for col, tipo in t["colunas"].items():
            papel = ("PK" if col in t.get("chave", []) else "") + (f" FK→`{fks[col]}`" if col in fks else "")
            papel += " medida" if col in t.get("medidas", []) else ""
            papel += " degenerada" if col in t.get("degeneradas", []) else ""
            papel += " 🔒" if col in t.get("lgpd", []) else ""
            L.append(f"| {col} | `{tipo}` | {papel.strip()} |")
        L += ["", "</details>", ""]
    L += ["## 7. Como manter", "", "1. Mude **só** `modelo.yaml` (ou o contrato semântico).",
          "2. `python -m arquitetura.gerar`, que regenera este arquivo, o `.drawio` e o `grafo.json`.",
          "3. `pytest arquitetura/tests`, que falha se doc, contrato semântico e código da F5 divergirem.", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------- draw.io
def _celula(cid, valor, x, y, w, h, estilo, parent="1"):
    return (f'<mxCell id="{cid}" value="{html.escape(valor, quote=True)}" style="{estilo}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')


def _aresta(cid, de, para, estilo):
    return (f'<mxCell id="{cid}" style="{estilo}" edge="1" parent="1" source="{de}" target="{para}">'
            f'<mxGeometry relative="1" as="geometry"/></mxCell>')


def _pagina(nome, celulas):
    corpo = "".join(celulas)
    return (f'<diagram name="{html.escape(nome)}" id="{_mid(nome)}"><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" '
            f'page="1" pageScale="1" pageWidth="2400" pageHeight="1600"><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            f"{corpo}</root></mxGraphModel></diagram>")


def gerar_drawio(d: dict, g: dict) -> str:
    m, T = d["modelo"], d["modelo"]["tabelas"]
    # página 1: linhagem. Uma coluna (swimlane) por ordem de camada
    colunas: dict[int, list[str]] = {}
    for cam, info in m["camadas"].items():
        colunas.setdefault(info["ordem"], []).append(cam)
    cel, pos = [], {}
    larg, alt, gap_x = 230, 54, 70
    x = 20
    for ordem in sorted(colunas):
        cams = colunas[ordem]
        tabs = [tid for tid, t in T.items() if t["camada"] in cams]
        if not tabs:
            continue
        h = 60 + len(tabs) * (alt + 14)
        lane = f"lane_{ordem}"
        cel.append(_celula(lane, " · ".join(cams), x, 20, larg + 30, h,
                           "swimlane;startSize=30;fillColor=#F8F9FA;strokeColor=#999999;fontStyle=1;"))
        for i, tid in enumerate(tabs):
            t = T[tid]
            cor, tracejado = BORDA[t["status"]]
            estilo = (f"rounded=1;whiteSpace=wrap;html=1;fillColor={CORES[t['tipo']]};strokeColor={cor};"
                      f"dashed={tracejado};fontSize=11;" + ("shape=cylinder3;" if t["tipo"] == "fonte" else ""))
            rot = f"<b>{tid}</b><br>{t['tipo']} · {t['status']}{' · ' + t['fase'] if t.get('fase') else ''}"
            cel.append(_celula(_mid(tid), rot, 15, 40 + i * (alt + 14), larg, alt, estilo, parent=lane))
            pos[tid] = True
        x += larg + 30 + gap_x
    n = 0
    for a in g["arestas"]:
        if a["rel"] == "deriva_de" and a["de"] in pos and a["para"] in pos:
            n += 1
            tr = "0" if T[a["para"]]["status"] == "implementado" else "1"
            cel.append(_aresta(f"e{n}", _mid(a["de"]), _mid(a["para"]),
                               f"edgeStyle=orthogonalEdgeStyle;rounded=1;endArrow=block;strokeColor=#555555;dashed={tr};"))
    p1 = _pagina("Linhagem medalhão", cel)

    # página 2: estrela gold. Fatos no centro, dimensões em anel
    gold = {tid: t for tid, t in T.items() if t["camada"] == "gold"}
    fatos = [t for t in gold if gold[t]["tipo"].startswith("fato")]
    dims = [t for t in gold if gold[t]["tipo"] == "dimensao"]
    cel2 = []
    for i, tid in enumerate(fatos):
        t = gold[tid]
        cols = "<br>".join(f"{c}{' (PK)' if c in t.get('chave', []) else ''}" for c in list(t.get("colunas", {}))[:14])
        cel2.append(_celula(_mid(tid), f"<b>{tid}</b><br><i>{t['grao']}</i><hr>{cols}", 620 + (i % 2) * 330,
                            260 + (i // 2) * 420, 300, 380,
                            f"rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=top;fillColor=#FFD966;"
                            f"dashed={BORDA[t['status']][1]};fontSize=10;"))
    for i, tid in enumerate(dims):
        t = gold[tid]
        lado = i % 2
        cel2.append(_celula(_mid(tid), f"<b>{tid}</b><br>SCD {t.get('scd', '-')} · {', '.join(t['chave'])}",
                            60 if lado == 0 else 1350, 60 + (i // 2) * 170, 260, 80,
                            f"rounded=1;whiteSpace=wrap;html=1;fillColor=#FFE6CC;dashed={BORDA[t['status']][1]};fontSize=10;"))
    n = 0
    for tid in fatos + dims:
        for col, alvo in (gold[tid].get("fks") or {}).items():
            dim = alvo.rsplit(".", 1)[0]
            if dim in gold:
                n += 1
                cel2.append(_aresta(f"f{n}", _mid(tid), _mid(dim),
                                    "endArrow=ERmandOne;startArrow=ERmany;html=1;strokeColor=#996633;"))
    p2 = _pagina("Estrela gold", cel2)
    return f'<mxfile host="arvo-gerador" type="device">{p1}{p2}</mxfile>'


def main() -> None:
    d = carregar()
    g = construir_grafo(d)
    (AQUI / "grafo.json").write_text(json.dumps(g, ensure_ascii=False, indent=2), "utf-8")
    (AQUI / "ARQUITETURA.md").write_text(gerar_md(d, g), "utf-8")
    (AQUI / "arquitetura.drawio").write_text(gerar_drawio(d, g), "utf-8")
    print(f"tabelas: {len(d['modelo']['tabelas'])} · nós: {len(g['nos'])} · arestas: {len(g['arestas'])}")


if __name__ == "__main__":
    main()
