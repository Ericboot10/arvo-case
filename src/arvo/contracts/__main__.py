"""CLI da F3.

  python -m arvo.contracts extrair --pdf Contrato-...pdf [--modo simulado|real] [--saida outputs/runs]
  python -m arvo.contracts aprovar --run outputs/runs/PRT-2025-0417/<chave> --aprovacao <arquivo.yaml>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from arvo.contracts.estado import EstadoExtracao
from arvo.contracts.pipeline import executar
from arvo.contracts.revisao import aprovar


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m arvo.contracts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extrair")
    e.add_argument("--pdf", required=True, type=Path)
    e.add_argument("--modo", default="simulado", choices=["simulado", "real"])
    e.add_argument("--saida", default=Path("outputs/runs"), type=Path)
    a = sub.add_parser("aprovar")
    a.add_argument("--run", required=True, type=Path)
    a.add_argument("--aprovacao", required=True, type=Path)
    a.add_argument("--sinistro", default=Path("data/case/sinistro-hospital-saorafael.csv"), type=Path)
    args = ap.parse_args()

    if args.cmd == "extrair":
        pasta = executar(args.pdf, args.saida, modo=args.modo)
        est = json.loads((pasta / "estado.json").read_text("utf-8"))
        print(f"run: {pasta}\nestado: {est['estado']}\nrevisão: {pasta / 'revisao.md'}\naprovação: {pasta / 'aprovacao.yaml'}")
    else:
        pasta = args.run
        est_dados = json.loads((pasta / "estado.json").read_text("utf-8"))
        estado = EstadoExtracao(pasta / "estado.json", est_dados["chave_idempotencia"], est_dados["contrato"])
        rec = json.loads((pasta / "reconciliacao.json").read_text("utf-8"))
        for l in rec["campos"]:  # JSON serializa tuplas como listas; o valor proposto volta a ser comparável
            if isinstance(l.get("valor_proposto"), list):
                l["valor_proposto"] = tuple(l["valor_proposto"])
        extracoes = {p.stem.split("_")[1]: json.loads(p.read_text("utf-8")) for p in pasta.glob("extracao_*.json")}
        doc_sha = json.loads((pasta / "parse.json").read_text("utf-8"))["sha256"]
        cods = set(pd.read_csv(args.sinistro, dtype=str, encoding="utf-8-sig")["cod_tuss"]) if args.sinistro.exists() else None
        print(aprovar(pasta, extracoes, rec, yaml.safe_load(args.aprovacao.read_text("utf-8")), estado, doc_sha, cods))


if __name__ == "__main__":
    main()
