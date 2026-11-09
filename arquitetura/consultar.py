"""Consulta o grafo da arquitetura: impacto e rastreabilidade sem abrir diagrama.

  python -m arquitetura.consultar acima gold.fato_item        # tudo de que a tabela depende (até a fonte)
  python -m arquitetura.consultar abaixo silver.item_conta    # tudo o que quebra se ela mudar (até persona)
  python -m arquitetura.consultar caminho pergunta.Q03        # de onde vem a resposta da pergunta Q03
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

GRAFO = Path(__file__).resolve().parent / "grafo.json"
FLUXO = {"deriva_de", "mede", "responde", "interessa_a"}


def carregar(caminho: Path = GRAFO) -> dict:
    return json.loads(caminho.read_text("utf-8"))


def _vizinhos(g: dict, sentido: str) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for a in g["arestas"]:
        if a["rel"] not in FLUXO:
            continue
        de, para = (a["de"], a["para"]) if sentido == "abaixo" else (a["para"], a["de"])
        adj.setdefault(de, []).append(para)
    return adj


def alcancaveis(g: dict, no: str, sentido: str) -> list[str]:
    adj, vistos, fila = _vizinhos(g, sentido), [], deque([no])
    while fila:
        for v in adj.get(fila.popleft(), []):
            if v not in vistos:
                vistos.append(v)
                fila.append(v)
    return vistos


def main() -> None:
    cmd, no = sys.argv[1], sys.argv[2]
    g = carregar()
    sentido = "abaixo" if cmd == "abaixo" else "acima"
    for v in alcancaveis(g, no, sentido):
        print(v)


if __name__ == "__main__":
    main()
