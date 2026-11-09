"""python -m arvo.agents.analyst "pergunta" [--orquestrador NOME] [--sem-genie] [--rastro]"""
from __future__ import annotations

import argparse
import json

from arvo.agents.analyst import construir


def main() -> None:
    ap = argparse.ArgumentParser(description="Agente analista da Arvo sobre a camada semântica")
    ap.add_argument("pergunta")
    ap.add_argument("--orquestrador", help="usa só este adapter da cadeia (ex.: claude_opus, databricks_gpt_oss)")
    ap.add_argument("--sem-genie", action="store_true", help="só a consulta estruturada às metric views")
    ap.add_argument("--rastro", action="store_true", help="mostra ferramentas, fontes e SQL usados")
    a = ap.parse_args()
    r = construir(orquestrador=a.orquestrador, com_genie=not a.sem_genie).perguntar(a.pergunta)
    print(r.texto)
    print(f"\n— {r.turnos} turno(s) · modelo(s): {', '.join(dict.fromkeys(r.modelos)) or 'nenhum'}"
          f" · ferramentas: {', '.join(x['ferramenta'] for x in r.rastro) or 'nenhuma'}")
    if a.rastro:
        print(json.dumps(r.rastro, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
