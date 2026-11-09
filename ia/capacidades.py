"""Linter de schema × provedor, a partir de ia/config/capacidades.yaml.

Um schema só pode ir para uma cadeia de adapters se for aceito, e respeitado, por TODOS os provedores dela.
Um adapter do AI Gateway que roteia para outro provedor (ex.: Gemini via Vertex) precisa satisfazer as regras do Gateway
E as da família de destino.
"""
from __future__ import annotations

from pathlib import Path

import yaml

CAPACIDADES = Path(__file__).resolve().parent / "config" / "capacidades.yaml"


def carregar(caminho: Path | None = None) -> dict:
    return yaml.safe_load(Path(caminho or CAPACIDADES).read_text("utf-8"))["provedores"]


def provedores_do_adapter(adapter) -> list[str]:
    prov = [adapter.provedor]
    if adapter.provedor == "databricks_gateway" and adapter.familia in ("anthropic", "openai", "google"):
        prov.append(adapter.familia)
    return prov


def _percorrer(no, caminho="$"):
    if isinstance(no, dict):
        yield caminho, no
        for k, v in no.items():
            if isinstance(v, (dict, list)):
                yield from _percorrer(v, f"{caminho}.{k}")
    elif isinstance(no, list):
        for i, v in enumerate(no):
            yield from _percorrer(v, f"{caminho}[{i}]")


def lint(schema: dict, provedores: list[str], caps: dict | None = None) -> list[str]:
    caps = caps or carregar()
    problemas: list[str] = []
    n_chaves = 0
    for caminho, no in _percorrer(schema):
        if no.get("type") == "object" and "properties" in no:
            n_chaves += len(no["properties"])
            for p in provedores:
                c = caps[p]
                if c.get("exige_additional_properties_false") and no.get("additionalProperties") is not False:
                    problemas.append(f"{p}: {caminho} precisa de additionalProperties: false")
                if c.get("exige_todos_required") and set(no.get("required", [])) != set(no["properties"]):
                    problemas.append(f"{p}: {caminho} precisa declarar todos os campos em required")
        for p in provedores:
            c = caps[p]
            for kw in no:
                if kw in c.get("rejeita", []):
                    problemas.append(f"{p}: {caminho} usa '{kw}' (rejeitado: HTTP 400)")
                if kw in c.get("ignora", []):
                    problemas.append(f"{p}: {caminho} usa '{kw}' (IGNORADO em silêncio: valide em código)")
    for p in provedores:
        lim = caps[p].get("max_chaves")
        if lim and n_chaves > lim:
            problemas.append(f"{p}: schema com {n_chaves} chaves > limite {lim}")
    return problemas
