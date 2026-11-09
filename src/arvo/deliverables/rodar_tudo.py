"""F12 · Um comando roda tudo, localmente, com o mesmo código que vai para o Databricks.

  python -m arvo.deliverables.rodar_tudo            # entregáveis (~4 min)
  python -m arvo.deliverables.rodar_tudo --testes   # + suíte completa (~4 min a mais)

Cada etapa roda num processo próprio: o Spark local de uma não leva a memória da outra.
Nenhuma etapa chama provedor de IA externo: a extração do contrato usa o replay determinístico da F3.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]

ETAPAS = [
    ("Prompts travados (F7)", ["-m", "arvo.ai.prompts", "verificar"]),
    ("Artefatos do painel = indicadores.yaml (F9)", ["-m", "arvo.monitoring.gerar", "--checar"]),
    ("Documentação da arquitetura (doc = código)", ["-m", "arvo.architecture.gerar"]),
    ("Agente sobre o sinistro: apontamentos.csv e total (perguntas 1, 2 e 4)", ["-m", "arvo.deliverables.gerar"]),
    ("Avaliação contra o gabarito (pergunta 3)", ["-m", "arvo.evaluation.relatorio"]),
    ("Painel de sanidade local (pergunta 8)", ["-m", "arvo.monitoring.local"]),
    ("Situação do rollout (pergunta 7)", ["-m", "arvo.rollout.status"]),
    ("Funil da Parte 2", ["-m", "arvo.funnel.analise_funil"]),
]
TESTES = ("Suíte completa de testes", ["-m", "pytest", "-q", "-p", "no:warnings"])


def main() -> int:
    etapas = ETAPAS + ([TESTES] if "--testes" in sys.argv else [])
    total = time.time()
    for i, (nome, args) in enumerate(etapas, 1):
        t = time.time()
        print(f"[{i}/{len(etapas)}] {nome} ...", flush=True)
        r = subprocess.run([sys.executable, "-W", "ignore", *args], cwd=RAIZ, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-3000:], r.stderr[-3000:], sep="\n")
            print(f"FALHOU: {nome}")
            return r.returncode
        print(f"      ok em {time.time() - t:.0f} s")
    print(f"\nTudo pronto em {time.time() - total:.0f} s. Entregáveis em deliverables/; respostas em deliverables/RESPOSTAS_CASE.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
