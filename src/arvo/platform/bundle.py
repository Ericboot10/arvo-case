"""Leitura dos recursos do bundle (resources/<tipo>/<domínio>.yml), para testes e scripts.

Os recursos ficam um arquivo por domínio (docs/conventions.md). Os caminhos dentro de cada arquivo são relativos a ele;
por isso cada recurso devolvido carrega `_base`, a pasta do arquivo onde foi declarado.
"""
from __future__ import annotations

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]


def recursos(tipo: str) -> dict[str, dict]:
    """Todos os recursos de um tipo ('jobs', 'pipelines', 'dashboards', 'alerts'), de todos os arquivos."""
    out: dict[str, dict] = {}
    for arq in sorted((RAIZ / "resources").glob("*/*.yml")):
        for chave, definicao in ((yaml.safe_load(arq.read_text("utf-8")) or {}).get("resources") or {}).get(tipo, {}).items():
            if chave in out:
                raise ValueError(f"recurso '{chave}' declarado duas vezes")
            out[chave] = {**definicao, "_base": arq.parent}
    return out
