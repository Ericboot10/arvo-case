"""A documentação de arquitetura não pode mentir. Rodar a partir de Arvo_Case:  pytest arquitetura/tests -v"""
from __future__ import annotations

import json
import xml.dom.minidom
from pathlib import Path

import yaml

from arquitetura import gerar
from arquitetura.consultar import alcancaveis

RAIZ = Path(__file__).resolve().parents[2]
M = yaml.safe_load((RAIZ / "arquitetura" / "modelo.yaml").read_text("utf-8"))
T = M["tabelas"]
MET = yaml.safe_load((RAIZ / "semantic" / "metricas.yaml").read_text("utf-8"))


def test_linhagem_e_fks_apontam_para_tabelas_e_colunas_existentes():
    for tid, t in T.items():
        assert t["camada"] in M["camadas"], tid
        for o in t.get("origem", []):
            assert o in T, f"{tid}: origem inexistente {o}"
        for col, alvo in (t.get("fks") or {}).items():
            tabela, coluna = alvo.rsplit(".", 1)
            assert col in t["colunas"], f"{tid}: FK em coluna inexistente {col}"
            assert tabela in T and coluna in T[tabela].get("colunas", {}), f"{tid}: FK → {alvo}"
            assert coluna in T[tabela].get("chave", []), f"{tid}: FK deve apontar para a chave de {tabela}"


def test_fatos_e_dimensoes_bem_definidos():
    for tid, t in T.items():
        if t["tipo"].startswith("fato") or t["tipo"] == "dimensao":
            assert t.get("grao") and t.get("chave"), f"{tid}: grão e chave são obrigatórios"
            assert set(t["chave"]) <= set(t["colunas"]), tid
        if t["tipo"] == "dimensao":
            assert t.get("scd") in (0, 1, 2), f"{tid}: tipo de SCD"
        for m in t.get("medidas", []):
            assert m in t["colunas"], f"{tid}: medida {m}"


def test_modelo_igual_ao_contrato_semantico():
    for nome, base in MET["tabelas_base"].items():
        tid = f"gold.{nome}"
        assert tid in T, tid
        assert set(T[tid]["colunas"]) == set(base["colunas"]), {
            "so_no_modelo": set(T[tid]["colunas"]) - set(base["colunas"]),
            "so_no_contrato": set(base["colunas"]) - set(T[tid]["colunas"])}
    for mm in MET["metricas"]:
        assert f"gold.{mm['tabela']}" in T, mm["id"]


def test_fato_item_e_subconjunto_do_auditado():
    base = set(T["gold.fato_item"]["colunas"]) - {"sk_perfil"}
    auditado = set(T["gold.fato_item_auditado"]["colunas"])
    assert base <= auditado and auditado - base == {"glosado", "regra_principal", "clausula_principal", "vl_glosado"}


def test_lgpd_identificador_so_na_bronze():
    lg = yaml.safe_load((RAIZ / "plataforma" / "lgpd" / "colunas_sensiveis.yaml").read_text("utf-8"))
    for tid, t in T.items():
        if t["camada"] in lg["proibido_em"]:
            assert "id_beneficiario" not in (t.get("colunas") or {}), tid
    for c in lg["colunas_mascaradas"]:
        assert c["coluna"] in T[c["tabela"]]["colunas"] and c["coluna"] in T[c["tabela"]].get("lgpd", [])


def test_documentacao_gerada_esta_atualizada():
    d = gerar.carregar()
    g = gerar.construir_grafo(d)
    pasta = RAIZ / "arquitetura"
    msg = "rode `python -m arquitetura.gerar` e versione o resultado"
    assert (pasta / "ARQUITETURA.md").read_text("utf-8") == gerar.gerar_md(d, g), msg
    assert (pasta / "arquitetura.drawio").read_text("utf-8") == gerar.gerar_drawio(d, g), msg
    assert json.loads((pasta / "grafo.json").read_text("utf-8")) == g, msg


def test_drawio_valido_com_duas_paginas_e_todas_as_tabelas():
    dom = xml.dom.minidom.parse(str(RAIZ / "arquitetura" / "arquitetura.drawio"))
    assert len(dom.getElementsByTagName("diagram")) == 2
    ids = {c.getAttribute("id") for c in dom.getElementsByTagName("mxCell")}
    assert {tid.replace(".", "__") for tid in T} <= ids


def test_mermaid_sem_ids_invalidos():
    md = (RAIZ / "arquitetura" / "ARQUITETURA.md").read_text("utf-8")
    blocos = md.split("```mermaid")[1:]
    assert len(blocos) == 3                 # linhagem, estrela gold, árvore do indicador-norte
    for b in blocos:
        corpo = b.split("```")[0]
        for linha in corpo.splitlines():
            ident = linha.strip().split(" ")[0].split("[")[0].split("(")[0]
            if ident and ident not in ("flowchart", "erDiagram", "subgraph", "end", "style", "}") and "{" not in ident:
                assert "." not in ident, linha


def test_grafo_consistente_e_rastreavel():
    g = json.loads((RAIZ / "arquitetura" / "grafo.json").read_text("utf-8"))
    nos = {n["id"] for n in g["nos"]}
    for a in g["arestas"]:
        assert a["de"] in nos and a["para"] in nos, a
    origem_q03 = set(alcancaveis(g, "pergunta.Q03", "acima"))
    assert {"fonte.sinistro_csv", "fonte.contrato_pdf", "fonte.semantica_git"} <= origem_q03
    impacto = set(alcancaveis(g, "semantic.map_tuss_conceito", "abaixo"))
    assert "pergunta.Q03" in impacto and "persona.Paulo Antunes" in impacto


def test_metric_views_geradas_atualizadas_e_aderentes_ao_contrato():
    import re

    from semantic.databricks.gerar_metric_views import SAIDA, gerar

    sql = SAIDA.read_text("utf-8")
    assert sql == gerar(), "rode `python -m semantic.databricks.gerar_metric_views`"
    palavras_sql = {"sum", "count", "count_if", "nullif", "case", "when", "then", "end", "distinct", "max", "avg",
                    "cast", "as", "int", "is", "not", "null", "and", "or", "size", "in", "ligada", "glosado",
                    "nao_glosado", "retida_operadora", "em_recurso"}
    descomentado = re.sub(r"^-- ", "", sql, flags=re.M)        # views PENDENTE (comentadas) também são validadas
    blocos = re.findall(r"AS \$\$(.*?)\$\$;", descomentado, flags=re.S)
    assert len(blocos) == 6
    for bloco in blocos:
        y = yaml.safe_load(bloco)
        cols = set(MET["tabelas_base"][y["source"].split(".", 1)[1]]["colunas"])
        for item in y["fields"] + y["measures"]:
            usados = set(re.findall(r"[a-z_]+", re.sub(r"'[^']*'", "", item["expr"].lower())))
            fora = usados - cols - palavras_sql
            assert not fora, f"{y['source']}.{item['name']}: colunas fora do contrato {fora}"


def test_disponibilidade_coerente_com_a_linhagem():
    """Métrica 'hoje' não pode depender, em nenhum nível acima, de fonte/tabela com status 'futuro'."""
    g = json.loads((RAIZ / "arquitetura" / "grafo.json").read_text("utf-8"))
    status = {n["id"]: n.get("status") for n in g["nos"]}
    for mm in MET["metricas"]:
        acima = alcancaveis(g, f"metrica.{mm['id']}", "acima")
        futuros = [n for n in acima if status.get(n) == "futuro"]
        if mm["disponibilidade"] == "hoje":
            assert not futuros, f"{mm['id']} marcada 'hoje', mas depende de {futuros}"
