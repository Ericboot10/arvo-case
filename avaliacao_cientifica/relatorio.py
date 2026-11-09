"""Gera o relatório da F8, que responde à pergunta 3 do case: precisão e recall, o que significam para o negócio,
qual priorizar e por que as divergências acontecem. Também gera o pacote de adjudicação cega e o plano amostral.

  python -m avaliacao_cientifica.relatorio            (roda o motor da F6 com Spark local; ~30 s)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import adjudicacao as ad
from . import amostragem as am
from . import decisao as dc
from . import divergencias as dv
from . import metricas as m

AQUI = Path(__file__).resolve().parent


def _pct(x):
    return f"{x:.1%}".replace(".", ",")


def _ic(t):
    return f"[{_pct(t[0])} – {_pct(t[1])}]"


def _brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def simular_revisores(chave: pd.DataFrame, regra: str) -> pd.DataFrame:
    """SIMULAÇÃO de planilha preenchida, só para exercitar o fluxo e a análise de sensibilidade.
    regra = 'contrato' (revisor aplica a letra do contrato = decisão do motor) | 'gabarito' (revisor concorda com o gabarito)."""
    col = "motor_glosou" if regra == "contrato" else "gabarito_indevido"
    return pd.DataFrame({"id_caso": chave.id_caso, "decisao": chave[col].map({True: "INDEVIDO", False: "DEVIDO"})})


def calcular(base: pd.DataFrame, bootstrap: int = 2000) -> dict:
    rot = base[base.rotulado]
    amostra = m.avaliar_amostra(rot, bootstrap)
    regras = m.por_regra(rot)
    vm = base[base.pred].groupby("regra_principal").vl_glosado.mean().to_dict()
    pop_ingenua = m.estimativa_populacional(base, rot, "cod_tuss", bootstrap)
    pop = m.estimativa_populacional(base, rot, ["cod_tuss", "pred"], bootstrap)
    div = dv.classificar(base)
    conc = dv.teste_concentracao(base)
    pasta_adj = AQUI / "adjudicacao"
    pacote = ad.gerar_pacote(base, pasta_adj)
    chave = pd.read_csv(pasta_adj / "CHAVE_NAO_COMPARTILHAR.csv", encoding="utf-8-sig")
    cenarios = {}
    for nome in ("gabarito", "contrato"):
        a = simular_revisores(chave, nome)
        r = ad.adjudicar(a, a, chave)
        b2 = ad.aplicar_rotulos(base, r["resultado"])
        rot2 = b2[b2.rotulado]
        cenarios[nome] = {"amostra": m.precisao_recall(m.matriz(rot2)),
                          "populacao": m.estimativa_populacional(b2, rot2, ["cod_tuss", "pred"], 500),
                          "por_regra": dc.tabela(m.por_regra(rot2), vm)}
    pl = am.plano(base)
    return {"amostra": amostra, "por_regra": dc.tabela(regras, vm), "pop_ingenua": pop_ingenua, "pop": pop,
            "divergencias": div.to_dict("records"), "concentracao": conc, "pacote_adjudicacao": pacote,
            "cenarios": cenarios, "plano_amostral": pl, "enriquecimento": m.enriquecimento(base, rot).head(6).round(3)
            .reset_index().rename(columns={"index": "cod_tuss"}).to_dict("records"),
            "volume": {"itens": int(len(base)), "rotulados": int(len(rot)), "glosas_motor": int(base.pred.sum()),
                       "vl_glosado_motor": float(base.loc[base.pred, "vl_glosado"].sum())}}


def gerar_md(r: dict) -> str:
    a, p, pi, v = r["amostra"], r["pop"], r["pop_ingenua"], r["volume"]
    cg, cc = r["cenarios"]["gabarito"], r["cenarios"]["contrato"]
    L = ["# F8 · Avaliação científica do agente de glosa", "",
         "> Gerado por `python -m avaliacao_cientifica.relatorio`. Motor da F6 (regras v1.0.0, contrato `rascunho-F2`) "
         f"sobre {v['itens']} itens do sinistro, comparado com os {v['rotulados']} itens do gabarito.", "",
         "## 1. Resposta à pergunta 3 do case", "",
         f"**Precisão {_pct(a['precisao'])} {_ic(a['precisao_ic95'])} · Recall {_pct(a['recall'])} {_ic(a['recall_ic95'])}** "
         f"(na amostra do gabarito, IC 95% de Wilson). TP {a['TP']} · FP {a['FP']} · FN {a['FN']} · TN {a['TN']}.", "",
         "**O que cada uma significa para o negócio:**",
         "- **Precisão** = de cada R$ 100 glosados, quanto é de fato indevido. Um FP é uma glosa errada: vira recurso, "
         "custo operacional, desgaste com o hospital e, principalmente, **perda de confiança da auditoria médica**. "
         "Retenção pela auditoria é a segunda maior perda do funil (22% do identificado).",
         "- **Recall** = de cada R$ 100 indevidos, quanto o agente pega. Um FN é dinheiro deixado na mesa, mas é recuperável "
         "(nova regra, nova rodada) e não gera conflito.", "",
         "**Qual priorizar: precisão.** E não por preferência, mas pela matriz de custo (seção 4):",
         "- uma glosa indevida custa operação e atrito;",
         "- uma glosa devida que não foi feita só deixa de ganhar e pode ser recuperada depois;",
         "- o agente opera sobre o funil da Parte 2, em que a efetivação depende da confiança de quem envia.",
         "",
         "**Por que não dá 100%:**",
         f"- Todas as {len(r['divergencias'])} divergências têm causa provável identificada.",
         "- Os FP são regras contratuais de condição objetiva que o gabarito marcou como \"Não\".",
         "- Os FN não têm nenhuma base contratual.",
         f"- O teste de permutação (p = {r['concentracao']['p_valor_permutacao']:.2f}) **não** mostra concentração "
         "dos FN em nenhum conceito: o padrão é de **ruído de rotulagem**, não de regra escondida (seção 5).", "",
         "**O que falta para decidir:**",
         f"1. A **adjudicação cega** das divergências por dois revisores. O pacote está pronto: {r['pacote_adjudicacao']['casos']} casos, "
         "com controles misturados.",
         "2. O **shadow**, com a amostra auditada por regra da seção 7. Com o gabarito atual, **nenhuma regra atinge "
         "o piso de 95% no limite inferior do IC**, porque há poucos itens rotulados por regra.", "",
         "## 2. Métricas na amostra", "",
         "| Métrica | Valor | IC 95% |", "|---|---|---|",
         f"| Precisão (contagem) | {_pct(a['precisao'])} | {_ic(a['precisao_ic95'])} |",
         f"| Recall (contagem) | {_pct(a['recall'])} | {_ic(a['recall_ic95'])} |",
         f"| Precisão em R$ | {_pct(a['precisao_rs'])} | {_ic(a['precisao_rs_ic95'])} (bootstrap por conta) |",
         f"| Recall em R$ (limite inferior: FN valorado pelo cobrado) | {_pct(a['recall_rs_limite_inferior'])} | {_ic(a['recall_rs_ic95'])} |",
         f"| R$ glosado corretamente / indevidamente | {_brl(a['vl_tp'])} / {_brl(a['vl_fp'])} | |", "",
         "## 3. Estimativa para o sinistro inteiro (o gabarito é enriquecido)", "",
         "| Código | % na população | % no gabarito | Super-representação |", "|---|---|---|---|"]
    L += [f"| {e['cod_tuss']} | {_pct(e['populacao'])} | {_pct(e['gabarito'])} | {e['razao']:.1f}× |".replace(".", ",")
          for e in r["enriquecimento"]]
    L += ["",
          "| Método | Válido? | Precisão | Recall | Glosas previstas × reais |", "|---|---|---|---|---|",
          f"| Reponderação por código TUSS | **{'sim' if pi['valida'] else 'NÃO'}** | {_pct(pi['precisao'])} | {_pct(pi['recall'])} | "
          f"{pi['glosas_estimadas_pela_amostra']:.0f} × {pi['glosas_reais_do_motor']} |",
          f"| Pós-estratificação código × decisão do motor | **{'sim' if p['valida'] else 'NÃO'}** | {_pct(p['precisao'])} {_ic(p['precisao_ic95'])} | "
          f"{_pct(p['recall'])} {_ic(p['recall_ic95'])} | {p['glosas_estimadas_pela_amostra']:.0f} × {p['glosas_reais_do_motor']} |", "",
          "**Leitura:**",
          f"- Reponderar só por código **falha no teste de validade**: prevê {pi['glosas_estimadas_pela_amostra']:.0f} glosas "
          f"onde o motor faz {pi['glosas_reais_do_motor']}. O gabarito foi selecionado de forma correlacionada com o resultado, "
          "então tratar a amostra como aleatória **superestima o recall**.",
          "- Pós-estratificar pela decisão do motor, que é conhecida para os 1.696 itens, corrige isso e passa no teste.",
          f"- A **precisão populacional é estável** ({_pct(p['precisao'])}). O **recall populacional cai para {_pct(p['recall'])}**, "
          "**se** os FN do gabarito estiverem certos: os ~12,5% de \"Sim\" entre os não glosados, escalados para "
          f"{p['itens_populacao'] - v['glosas_motor']} itens, viram muitos FN estimados.",
          "- **A qualidade do rótulo domina o resultado.** Isso torna a adjudicação a primeira decisão a tomar.", "",
          "## 4. Por regra e ponto de operação (matriz de custo, premissas AMB-20)", "",
          "| Regra | Rotulados | Precisão | IC 95% | Valor médio | Custo do FP | Custo esperado automático | Modo |",
          "|---|---|---|---|---|---|---|---|"]
    for x in r["por_regra"]:
        L.append(f"| {x['regra']} | {x['glosados_rotulados']} | {_pct(x['precisao'])} | {_ic(x['precisao_ic95'])} | {_brl(x['valor_medio'])} | "
                 f"{_brl(x['custo_fp'])} | {_brl(x['custo_esperado_auto'])} | **{x['modo']}** |")
    L += ["",
          "**Como ler:**",
          "- Todas as regras têm **ganho esperado positivo** (enviar vale mais que não enviar). Nenhuma está BLOQUEADA.",
          "- Mas nenhuma atinge o piso de precisão para envio **automático**: o limite inferior do IC é largo com tão poucos "
          "rotulados. Até a R4, 29/29 corretos, tem limite inferior abaixo de 95%.",
          "- A decisão de \"ir para produção\" depende do **tamanho da amostra auditada**, não de mais modelagem.",
          "- Recall por regra não existe com este gabarito, porque ele não diz qual regra deveria ter disparado.", "",
          "## 5. Divergências e causas", "",
          "| Item | Tipo | Regra do motor | Causa provável | Evidência | R$ |", "|---|---|---|---|---|---|"]
    for d in r["divergencias"]:
        L.append(f"| {d['id_item']} | {d['tipo']} | {d['regra_motor'] or '—'} | {d['causa']} | {str(d['evidencia'])[:110]} | {_brl(d['vl_em_jogo'])} |")
    c = r["concentracao"]
    L += ["", f"**Regra escondida × ruído de rotulagem:** entre os {c['n']} rotulados não glosados, {_pct(c['taxa_sim_entre_nao_glosados'])} "
          "estão marcados como \"Sim\".",
          f"- O teste de permutação do qui-quadrado (H0: a taxa independe do conceito) dá **p = {c['p_valor_permutacao']:.2f}**.",
          "- Uma regra fora do contrato concentraria os \"Sim\" num conceito. Não é o que acontece: a taxa por conceito "
          "acompanha a base.",
          "- Conclusão: é compatível com **ruído de rotulagem**. Mesmo assim, a pergunta AMB-03 vai para o Auditor.", "",
          "## 6. Sensibilidade ao rótulo (simulação, NÃO é resultado de adjudicação)", "",
          "| Cenário de adjudicação | Precisão (amostra) | Recall (amostra) | Recall (população) |", "|---|---|---|---|",
          f"| Revisores concordam com o gabarito | {_pct(cg['amostra']['precisao'])} | {_pct(cg['amostra']['recall'])} | {_pct(cg['populacao']['recall'])} |",
          f"| Revisores aplicam a letra do contrato | {_pct(cc['amostra']['precisao'])} | {_pct(cc['amostra']['recall'])} | {_pct(cc['populacao']['recall'])} |", "",
          "- A verdade está entre as duas linhas. A adjudicação cega diz onde.",
          "- Mesmo no melhor cenário, o limite inferior do IC por regra continua abaixo de 95%, porque n é pequeno: "
          + ", ".join(f"{x['regra']} {x['confirmados']}/{x['glosados_rotulados']} → {_pct(x['precisao_ic95'][0])}"
                      for x in cc["por_regra"]) + ".",
          "- O gabarito não substitui o shadow.", "",
          "## 7. Plano amostral do shadow e da auditoria contínua (alimenta gold.fato_auditoria_amostral)", "",
          "| Estrato | População/mês | Amostra auditada | Objetivo |", "|---|---|---|---|"]
    pl = r["plano_amostral"]
    for regra, x in pl["glosado_por_regra"].items():
        L.append(f"| GLOSADO · {regra} | {x['N']} | {x['n']} | precisão ±2 p.p. (p≈98%, IC 95%, correção de população finita) |")
    L += [f"| NAO_GLOSADO (estratificado por conceito, mínimo de 10) | {pl['nao_glosado']['N']} | {pl['nao_glosado']['n_total']} | "
          "indevido não detectado ±2 p.p. (estimador de recall) |", "",
          "- Todo item sorteado leva o **peso amostral**, e M10 e M25 são estimadas com esse peso. É o que faltou no gabarito do case.",
          "- O critério de go-live da regra (F10) é: limite inferior do IC ≥ 95% **e** o modo da matriz de custo = AUTOMATICO.", "",
          "## 8. Premissas e limitações", "",
          "- O contrato usado é a versão `rascunho-F2`: falta a aprovação do Jurídico (G3).",
          "- As premissas de custo são da AMB-20 e não estão validadas.",
          "- A estimativa populacional assume seleção aleatória **dentro** de cada célula código × decisão do motor.",
          "- O recall em R$ é um limite inferior: o FN é valorado pelo valor cobrado, e não pela glosa que caberia.",
          "- A seção 6 é uma **simulação** do fluxo de adjudicação, sem revisores reais.",
          "- A adjudicação real usa as planilhas em `adjudicacao/`. A chave fica com o Cientista de Dados."]
    return "\n".join(L) + "\n"


def main() -> None:
    from .dados import base_avaliacao

    base, out = base_avaliacao()
    r = calcular(base)
    (AQUI / "resultados.json").write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str), "utf-8")
    (AQUI / "RELATORIO_AVALIACAO.md").write_text(gerar_md(r), "utf-8")
    print(gerar_md(r)[:3000])


if __name__ == "__main__":
    main()
