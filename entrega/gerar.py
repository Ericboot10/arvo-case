"""F12 · Entregáveis da Parte 1 a partir de UMA execução do agente sobre o sinistro real.

  python -m entrega.gerar

Grava em entrega/:
  apontamentos.csv     1 linha por item glosado: id_item, regra, cláusula, valores, justificativa e destino de envio
  resumo_glosa.json    total glosado, por regra e por cláusula, itens em revisão humana e versões usadas
O agente é determinístico: duas execuções com as mesmas versões (contrato, semântica, regras) dão o mesmo arquivo.
"""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from pyspark.sql import functions as F

RAIZ = Path(__file__).resolve().parents[1]
AQUI = Path(__file__).resolve().parent
SINISTRO = RAIZ / "arvo.case" / "sinistro-hospital-saorafael.csv"
COLUNAS = ["id_apontamento", "id_item", "id_conta", "regra_principal", "clausula_principal", "clausulas_subsidiarias",
           "vl_cobrado", "vl_referencia", "vl_glosado", "justificativa", "status_envio", "motivo_revisao",
           "estagio_regra", "destino_envio", "versao_regra", "versao_contrato", "versao_semantica"]


def gerar(spark, saida: Path = AQUI) -> dict:
    from medalhao.local import executar, liberar
    from rollout import envio

    out = executar(spark, str(SINISTRO), run_id="entrega-parte1")
    try:
        ap = out["gold.fato_apontamento"]
        dest = envio.decidir(ap, out["gold.fato_item_auditado"], envio.carregar_estado(), True) \
            .select("id_apontamento", "estagio_regra", "destino_envio")
        linhas = [r.asDict() for r in ap.join(dest, "id_apontamento")
                  .withColumn("clausulas_subsidiarias", F.array_join("clausulas_subsidiarias", "; "))
                  .select(*COLUNAS).orderBy("id_item").collect()]
    finally:
        liberar(out)
    saida.mkdir(exist_ok=True)
    with (saida / "apontamentos.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        for ln in linhas:
            w.writerow({k: (f"{v:.2f}" if isinstance(v, Decimal) else ("" if v is None else v)) for k, v in ln.items()})
    total = sum(Decimal(ln["vl_glosado"]) for ln in linhas)

    def agrupar(chave: str) -> dict:
        g: dict = {}
        for ln in linhas:
            k = ln[chave]
            g.setdefault(k, {"apontamentos": 0, "vl_glosado": Decimal("0")})
            g[k]["apontamentos"] += 1
            g[k]["vl_glosado"] += ln["vl_glosado"]
        return {k: {"apontamentos": v["apontamentos"], "vl_glosado": float(v["vl_glosado"])} for k, v in sorted(g.items())}

    resumo = {"apontamentos": len(linhas), "itens_distintos": len({ln["id_item"] for ln in linhas}),
              "vl_glosado_total": float(total), "por_regra": agrupar("regra_principal"),
              "por_clausula": agrupar("clausula_principal"),
              "revisao_humana_pelo_motor": sum(ln["status_envio"] == "REVISAO_HUMANA" for ln in linhas),
              "destino_hoje": agrupar("destino_envio"),
              "versoes": {k: sorted({ln[k] for ln in linhas}) for k in ("versao_regra", "versao_contrato", "versao_semantica")}}
    (saida / "resumo_glosa.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), "utf-8")
    return resumo


def main() -> None:
    from medalhao.local import spark_local

    s = spark_local()
    s.sparkContext.setLogLevel("ERROR")
    r = gerar(s)
    print(json.dumps({k: r[k] for k in ("apontamentos", "vl_glosado_total", "por_regra", "revisao_humana_pelo_motor")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
