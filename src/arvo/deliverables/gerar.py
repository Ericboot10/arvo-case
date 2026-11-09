"""F12 · Entregáveis da Parte 1 a partir de UMA execução do agente sobre o sinistro real.

  python -m arvo.deliverables.gerar                                         # o sinistro do case → deliverables/
  python -m arvo.deliverables.gerar --sinistro novo_mes.csv                 # outro mês, mesmo layout → outputs/results/novo_mes/
  python -m arvo.deliverables.gerar --sinistro novo_mes.csv --saida pasta/  # escolhe a pasta de saída

Grava na pasta de saída:
  apontamentos.csv     1 linha por item glosado: id_item, regra, cláusula, valores, justificativa e destino de envio
  resumo_glosa.json    total glosado, % do sinistro, por regra e por cláusula, itens em revisão humana, quarentena e versões
  quarentena.csv       itens que o agente NÃO auditou e o motivo (código TUSS novo, caráter fora do domínio, valor
                       inconsistente...). Só é gravado se houver item em quarentena.
O arquivo novo precisa ter as mesmas colunas do sinistro do case (src/arvo/medallion/transformacoes.py: COLUNAS_ORIGEM).
O agente é determinístico: duas execuções com as mesmas versões (contrato, semântica, regras) dão o mesmo arquivo.
"""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from pyspark.sql import functions as F

RAIZ = Path(__file__).resolve().parents[3]
AQUI = RAIZ / "deliverables"            # os entregáveis ficam na raiz do repositório, não no pacote
SINISTRO = RAIZ / "data" / "case" / "sinistro-hospital-saorafael.csv"
COLUNAS = ["id_apontamento", "id_item", "id_conta", "regra_principal", "clausula_principal", "clausulas_subsidiarias",
           "vl_cobrado", "vl_referencia", "vl_glosado", "justificativa", "status_envio", "motivo_revisao",
           "estagio_regra", "destino_envio", "versao_regra", "versao_contrato", "versao_semantica"]


def gerar(spark, saida: Path = AQUI, sinistro: Path = SINISTRO) -> dict:
    from arvo.medallion.local import executar, liberar
    from arvo.rollout import envio

    out = executar(spark, str(sinistro), run_id=f"entrega-{Path(sinistro).stem}")
    try:
        itens_lidos = out["bronze.sinistro_raw"].count()
        vl_sinistro = out["silver.item_conta"].agg(F.sum("vl_total")).first()[0] or Decimal("0")
        quarentena = [r.asDict() for r in out["quarantine.item_conta_rejeitado"]
                      .select("id_item", F.array_join("motivos", "; ").alias("motivos")).orderBy("id_item").collect()]
        ap = out["gold.fato_apontamento"]
        dest = envio.decidir(ap, out["gold.fato_item_auditado"], envio.carregar_estado(), True) \
            .select("id_apontamento", "estagio_regra", "destino_envio")
        linhas = [r.asDict() for r in ap.join(dest, "id_apontamento")
                  .withColumn("clausulas_subsidiarias", F.array_join("clausulas_subsidiarias", "; "))
                  .select(*COLUNAS).orderBy("id_item").collect()]
    finally:
        liberar(out)
    saida.mkdir(parents=True, exist_ok=True)
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

    if quarentena:
        with (saida / "quarentena.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id_item", "motivos"])
            w.writeheader()
            w.writerows(quarentena)
    resumo = {"arquivo_sinistro": Path(sinistro).name, "itens_lidos": itens_lidos,
              "itens_em_quarentena": len(quarentena), "vl_sinistro_auditado": float(vl_sinistro),
              "pct_glosado_do_sinistro": round(float(total / vl_sinistro), 4) if vl_sinistro else None,
              "apontamentos": len(linhas), "itens_distintos": len({ln["id_item"] for ln in linhas}),
              "vl_glosado_total": float(total), "por_regra": agrupar("regra_principal"),
              "por_clausula": agrupar("clausula_principal"),
              "revisao_humana_pelo_motor": sum(ln["status_envio"] == "REVISAO_HUMANA" for ln in linhas),
              "destino_hoje": agrupar("destino_envio"),
              "versoes": {k: sorted({ln[k] for ln in linhas}) for k in ("versao_regra", "versao_contrato", "versao_semantica")}}
    (saida / "resumo_glosa.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), "utf-8")
    return resumo


def main() -> None:
    import argparse

    from arvo.medallion.local import spark_local

    ap = argparse.ArgumentParser(description="Roda o agente de glosa sobre um sinistro no layout do case.")
    ap.add_argument("--sinistro", type=Path, help="CSV do sinistro (padrão: o arquivo do case em data/case/)")
    ap.add_argument("--saida", type=Path, help="pasta de saída (padrão: deliverables/ para o case, outputs/results/<arquivo>/ para outro)")
    a = ap.parse_args()
    sinistro = a.sinistro or SINISTRO
    if not sinistro.exists():
        raise SystemExit(f"arquivo não encontrado: {sinistro}")
    saida = a.saida or (AQUI if a.sinistro is None else RAIZ / "outputs" / "results" / sinistro.stem)

    s = spark_local()
    s.sparkContext.setLogLevel("ERROR")
    r = gerar(s, saida, sinistro)
    print(json.dumps({k: r[k] for k in ("arquivo_sinistro", "itens_lidos", "itens_em_quarentena", "apontamentos",
                                        "vl_glosado_total", "pct_glosado_do_sinistro", "por_regra",
                                        "revisao_humana_pelo_motor")}, ensure_ascii=False, indent=2))
    print(f"Arquivos em {saida}")


if __name__ == "__main__":
    main()
