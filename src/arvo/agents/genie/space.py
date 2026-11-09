"""Espaço Genie como código: monta o `serialized_space` a partir de src/arvo/agents/genie/espaco.yaml e do benchmark,
e cria ou atualiza o espaço no workspace (API de gerenciamento do Genie).

  python -m arvo.agents.genie.space montar      # imprime o JSON que seria publicado (não chama o workspace)
  python -m arvo.agents.genie.space publicar    # cria ou atualiza; grava o space_id em src/arvo/agents/genie/estado.json

Formato (versão 2 do serialized_space, conferido num espaço existente em 09/11/2026): ids de 32 hex minúsculos,
coleções ordenadas, tabelas com nome de três partes, texto em listas de linhas, um benchmark = uma resposta SQL.
Os ids são derivados do conteúdo: publicar duas vezes o mesmo arquivo gera o mesmo espaço.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import yaml

from arvo.agents.analyst import RAIZ, carregar_config

AQUI = Path(__file__).resolve().parent


def _id(*partes: str) -> str:
    return hashlib.md5("|".join(partes).encode("utf-8")).hexdigest()


def _linhas(texto: str) -> list[str]:
    return texto.strip("\n").splitlines(keepends=True)


def montar(catalogo: str, espaco: dict | None = None, benchmark: dict | None = None) -> dict:
    espaco = espaco or yaml.safe_load((AQUI / "espaco.yaml").read_text("utf-8"))
    benchmark = benchmark or yaml.safe_load((AQUI.parent / "analyst" / "benchmark.yaml").read_text("utf-8"))
    sub = lambda s: s.replace("<catalogo>", catalogo)  # noqa: E731
    return {
        "version": "2",
        "config": {"sample_questions": sorted(
            [{"id": _id("sugerida", q), "question": [q]} for q in espaco.get("perguntas_sugeridas", [])],
            key=lambda x: x["id"])},
        "data_sources": {"tables": sorted([{"identifier": sub(t)} for t in espaco["tabelas"]],
                                          key=lambda x: x["identifier"])},
        "instructions": {
            "text_instructions": [{"id": _id("instrucoes"), "content": _linhas(sub(espaco["instrucoes"]))}],
            "example_question_sqls": sorted(
                [{"id": _id("exemplo", e["pergunta"]), "question": [e["pergunta"]], "sql": _linhas(sub(e["sql"]))}
                 for e in espaco.get("exemplos", [])], key=lambda x: x["id"])},
        "benchmarks": {"questions": sorted(
            [{"id": _id("benchmark", b["id"]), "question": [b["pergunta"]],
              "answer": [{"format": "SQL", "content": _linhas(sub(b["sql"]))}]} for b in benchmark["perguntas"]],
            key=lambda x: x["id"])},
    }


def publicar(cfg: dict | None = None, client=None) -> str:
    from arvo.agents.providers.databricks_dados import cliente_workspace, warehouse_por_nome

    cfg = cfg or carregar_config()
    db, perfil = cfg["databricks"], cfg["databricks"].get("perfil") or None
    espaco = yaml.safe_load((RAIZ / cfg["genie"]["espaco"]).read_text("utf-8"))
    client = client or cliente_workspace(perfil)
    serial = json.dumps(montar(db["catalogo"], espaco), ensure_ascii=False)
    descricao = espaco["descricao"].replace("<catalogo>", db["catalogo"])
    titulo = espaco["titulo"].replace("<ambiente>", db["catalogo"].removeprefix("arvo_"))
    wh = warehouse_por_nome(db["warehouse"], perfil, client)
    estado_p = RAIZ / cfg["genie"]["estado"]
    estado = json.loads(estado_p.read_text("utf-8")) if estado_p.exists() else {}
    chave = perfil or "workspace"
    sid = estado.get(chave, {}).get("space_id")
    if sid:
        client.genie.update_space(sid, serialized_space=serial, title=titulo, description=descricao,
                                  warehouse_id=wh)
    else:
        sid = client.genie.create_space(wh, serial, title=titulo, description=descricao).space_id
    estado[chave] = {"space_id": sid, "publicado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "sha256_conteudo": hashlib.sha256(serial.encode("utf-8")).hexdigest()}
    estado_p.write_text(json.dumps(estado, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return sid


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "montar"
    if cmd == "publicar":
        print("espaço Genie:", publicar())
    else:
        print(json.dumps(montar(carregar_config()["databricks"]["catalogo"]), ensure_ascii=False, indent=2))
