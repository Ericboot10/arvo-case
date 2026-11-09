"""Governança de prompts: versão obrigatória e trava de conteúdo.

Todo prompt é um arquivo .md com frontmatter (prompt_id, versao). O conteúdo de cada prompt_id@versao fica travado
por sha256 em src/arvo/ai/prompts.lock.json. Mudar o texto sem subir a versão é erro de CI, porque a telemetria e as avaliações
(golden set) ficariam associadas à versão errada.
No Databricks, os prompts travados são publicados no MLflow Prompt Registry (src/arvo/ai/databricks/registrar_prompts.py).

  python -m arvo.ai.prompts verificar     # falha se houver prompt alterado sem versão nova ou não travado
  python -m arvo.ai.prompts travar        # trava versões NOVAS (nunca sobrescreve uma versão existente)
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent / "prompts.lock.json"
PASTAS = [RAIZ / "src" / "arvo" / "contracts" / "prompts", RAIZ / "src" / "arvo" / "ai" / "prompts"]


def inventario() -> list[dict]:
    out = []
    for pasta in PASTAS:
        for arq in sorted(pasta.glob("*.md")):
            txt = arq.read_text("utf-8")
            meta = dict(re.findall(r"^(prompt_id|versao):\s*(\S+)", txt, flags=re.M))
            out.append({"arquivo": str(arq.relative_to(RAIZ)), "prompt_id": meta.get("prompt_id"),
                        "versao": meta.get("versao"), "sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest()})
    return out


def _lock() -> dict:
    return json.loads(LOCK.read_text("utf-8")) if LOCK.exists() else {}


def verificar() -> list[str]:
    lock, problemas, vistos = _lock(), [], set()
    for p in inventario():
        if not p["prompt_id"] or not p["versao"]:
            problemas.append(f"{p['arquivo']}: frontmatter sem prompt_id/versao")
            continue
        chave = f"{p['prompt_id']}@{p['versao']}"
        if chave in vistos:
            problemas.append(f"{chave}: duplicado em mais de um arquivo")
        vistos.add(chave)
        if chave not in lock:
            problemas.append(f"{chave}: não travado (rode `python -m arvo.ai.prompts travar`)")
        elif lock[chave]["sha256"] != p["sha256"]:
            problemas.append(f"{chave}: conteúdo mudou sem nova versão ({p['arquivo']})")
    return problemas


def travar() -> list[str]:
    lock, novos = _lock(), []
    for p in inventario():
        chave = f"{p['prompt_id']}@{p['versao']}"
        if chave in lock and lock[chave]["sha256"] != p["sha256"]:
            raise SystemExit(f"{chave} já travado com outro conteúdo: suba a versão no frontmatter")
        if chave not in lock:
            lock[chave] = {"arquivo": p["arquivo"], "sha256": p["sha256"]}
            novos.append(chave)
    LOCK.write_text(json.dumps(dict(sorted(lock.items())), ensure_ascii=False, indent=2) + "\n", "utf-8")
    return novos


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verificar"
    if cmd == "travar":
        print("travados:", travar() or "nenhum novo")
    else:
        prob = verificar()
        print("\n".join(prob) or "ok: todos os prompts versionados e travados")
        sys.exit(1 if prob else 0)
