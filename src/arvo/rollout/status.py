"""F10 · Situação do rollout com os dados do case → src/arvo/rollout/STATUS_ROLLOUT.md

  python -m arvo.rollout.status

1. Estado vigente (estado_regras.yaml) → destino de cada apontamento do sinistro real.
2. Promoção SHADOW → CANARIO: o que cada regra já cumpre e o que falta (evidência = gabarito como rodada 0).
3. Simulação: e se todas as regras estivessem em AUTOMATICO? Mostra o teto de valor e o rebaixamento automático
   que o painel de sanidade (F9) dispararia. É ilustração, não proposta.
"""
from __future__ import annotations

import copy
import json

import pandas as pd

from arvo.evaluation.amostragem import plano
from arvo.evaluation.dados import base_avaliacao
from arvo.rollout import envio, promocao
from arvo.monitoring import gerar as san_gerar
from arvo.monitoring import local as san_local
from arvo.monitoring.portao import avaliar_portao

SAIDA = envio.AQUI / "STATUS_ROLLOUT.md"
INVARIANTES = ("S18", "S19", "S20", "S21")


def pct(v: float) -> str:
    return f"{100 * v:.1f}%".replace(".", ",")


def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def coletar(spark) -> dict:
    from arvo.medallion.local import executar, liberar

    out = executar(spark, str(san_gerar.RAIZ / "data" / "case" / "sinistro-hospital-saorafael.csv"), planilha=str(san_local.PLANILHA),
                   run_id="f10-rollout")
    try:
        base, _ = base_avaliacao(spark, out)
        auditoria = pd.DataFrame([r.asDict() for r in san_local.auditoria_do_gabarito(spark, out).collect()])
        linhas = san_local.avaliar(spark, san_local.registrar(spark, out))
        portao = avaliar_portao(linhas)
        ap, itens = out["gold.fato_apontamento"], out["gold.fato_item_auditado"]
        tel_ok = ap.where("run_id IS NULL OR versao_contrato IS NULL OR versao_semantica IS NULL OR versao_regra IS NULL").count() == 0
        estado = envio.carregar_estado()
        vigente = envio.resumo(envio.decidir(ap, itens, estado, portao["liberado"]))
        evid = promocao.evidencias_auditoria(auditoria)
        pl = plano(base)["glosado_por_regra"]
        inv = sum((r["valor"] or 0) for r in linhas if r["id_indicador"] in INVARIANTES)
        aderencia = next(r["valor"] for r in linhas if r["id_indicador"] == "S22")
        avaliacoes = []
        for regra, e in sorted(estado["regras"].items()):
            ev = {**evid.get(regra, {}), "violacoes_invariantes": inv, "aderencia_semantica": aderencia,
                  "telemetria_completa": tel_ok, "semanas_no_estagio": 0}
            avaliacoes.append(promocao.avaliar_promocao(regra, e["estagio"], ev, pl.get(regra, {}).get("n")))
        hip = copy.deepcopy(estado)
        for regra in evid:                      # só regras com evidência; as demais seguem em SHADOW
            hip["regras"][regra].update(estagio="AUTOMATICO", precisao_inf=evid[regra]["precisao_inf"])
        simulado = envio.resumo(envio.decidir(ap, itens, hip, portao["liberado"]))
        rebaixado, mudancas = promocao.rebaixar(hip, linhas, hoje="2026-11-07")
    finally:
        liberar(out)
    return {"portao": portao, "vigente": vigente, "avaliacoes": avaliacoes, "plano": pl, "evidencias": evid,
            "simulado": simulado, "tetos": {r: envio.teto_valor(v.get("precisao_inf")) for r, v in evid.items()},
            "rebaixamentos": mudancas, "estado_apos_rebaixar": {r: v["estagio"] for r, v in rebaixado["regras"].items()}}


def markdown(s: dict) -> str:
    L = ["# Situação do rollout (F10)", "",
         "> GERADO por `python -m arvo.rollout.status` com o sinistro real do case. Evidência de auditoria = gabarito como rodada 0",
         "> (pós-estratificado, F8): serve para exercitar os critérios, não para promover regra.", "",
         f"**Portão de sanidade:** {'LIBERADO' if s['portao']['liberado'] else 'BLOQUEADO'}.", "",
         "## 1. Estado vigente: todas as regras em SHADOW", "",
         "| Regra | Estágio | Destino | Apontamentos | Valor |", "|---|---|---|---|---|"]
    L += [f"| {r['regra_principal']} | {r['estagio_regra']} | {r['destino_envio']} | {r['apontamentos']} | {brl(float(r['vl_glosado']))} |"
          for r in s["vigente"]]
    L += ["", "Nada é enviado: tudo fica em `gold_shadow` até a regra cumprir os critérios e ser promovida por quem aprova.", "",
          "## 2. O que falta para SHADOW → CANÁRIO", "",
          "| Regra | Auditados / plano | Precisão | Limite inferior IC 95% | Apta | O que falta |", "|---|---|---|---|---|---|"]
    for a in s["avaliacoes"]:
        e = s["evidencias"].get(a["regra"], {})
        n_pl = s["plano"].get(a["regra"], {}).get("n", "—")
        p = pct(e["precisao"]) if e.get("precisao") is not None else "—"
        pi = pct(e["precisao_inf"]) if e.get("precisao_inf") is not None else "—"
        L.append(f"| {a['regra']} | {e.get('n_auditado', 0)} / {n_pl} | {p} | {pi} | {'sim' if a['apta'] else 'não'} | "
                 + "; ".join(a["faltam"]) + " |")
    L += ["", "Aprovadores da promoção: " + ", ".join(s["avaliacoes"][0].get("aprovadores", [])) + ".", "",
          "## 3. Simulação: e se todas estivessem em AUTOMÁTICO hoje?", "",
          "Teto de valor do envio automático, pela matriz de custo (AMB-20) e pelo limite inferior do IC de cada regra:", "",
          "| Regra | Limite inferior IC 95% | Teto do envio automático |", "|---|---|---|"]
    L += [f"| {r} | {pct(s['evidencias'][r]['precisao_inf'])} | {brl(t)} |" for r, t in sorted(s["tetos"].items())]
    L += ["", "Teto zero = abaixo do piso de 95% do comitê: nada sai automático. Com a mesma matriz de custo, o teto seria "
          f"{brl(envio.teto_valor(0.95))} com limite inferior de 95%, {brl(envio.teto_valor(0.98))} com 98% e "
          f"{brl(envio.teto_valor(0.99))} com 99% (trava de política em {brl(envio.carregar()['teto_valor']['teto_maximo'])})."]
    L += ["", "| Regra | Destino | Apontamentos | Valor |", "|---|---|---|---|"]
    L += [f"| {r['regra_principal']} | {r['destino_envio']} | {r['apontamentos']} | {brl(float(r['vl_glosado']))} |" for r in s["simulado"]]
    L += ["", "**E o painel de sanidade rebaixaria automaticamente:**", ""]
    L += [f"- {m['mudanca']} · {m['motivo']}" for m in s["rebaixamentos"]] or ["- nenhuma regra"]
    L += ["", "Estado depois do rebaixamento: " + ", ".join(f"{r} {e}" for r, e in sorted(s["estado_apos_rebaixar"].items())) + ".",
          "É o que a F8 já indicava: com a evidência de hoje, nenhuma regra fica em envio direto."]
    return "\n".join(L) + "\n"


def main() -> None:
    from arvo.medallion.local import spark_local

    spark = spark_local()
    spark.sparkContext.setLogLevel("ERROR")
    s = coletar(spark)
    SAIDA.write_text(markdown(s), "utf-8")
    print(json.dumps({"portao": s["portao"]["liberado"], "rebaixamentos": s["rebaixamentos"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
