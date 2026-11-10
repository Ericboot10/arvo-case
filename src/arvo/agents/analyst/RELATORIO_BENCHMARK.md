# Benchmark do agente analista

Gerado por `python -m arvo.agents.analyst.benchmark`. A resposta certa de cada pergunta é o resultado do SQL de referência em `src/arvo/agents/analyst/benchmark.yaml`, executado no workspace com os dados do case.

| Alvo | Acertos | Executado em |
|---|---|---|
| metrica | 7/7 | 2026-11-09 19:22 |
| genie | 8/8 | 2026-11-10 15:13 |
| agente (databricks_gpt_oss) | 7/8 | 2026-11-09 19:43 |

## metrica

| Pergunta | Resultado | Referência | Faltou | Tempo |
|---|---|---|---|---|
| B01 · Quanto foi glosado no mês por cláusula do contrato, em valor e em número de itens? | ✅ | 55484.2, 39875.4, 26589.3 | — | 1.0 s |
| B02 · Qual o valor total glosado e qual a taxa de glosa sobre o valor apresentado no mês? | ✅ | 121949, 0.102101 | — | 1.0 s |
| B03 · Qual código TUSS tem o maior gap entre o valor cobrado e o pactuado no contrato, e de quanto? | ✅ | 13132.9 | — | 0.7 s |
| B04 · Que fração das contas do prestador recebeu ao menos uma glosa no mês? | ✅ | 0.65 | — | 1.0 s |
| B05 · Quanto do sinistro tem conflito semântico (Pronto Socorro com caráter Eletivo)? Dê a taxa sobre os itens. | ✅ | 0.067217 | — | 0.9 s |
| B06 · Na competência mais recente da planilha da rede, qual o índice-norte e o atingimento da meta de 2%? | ✅ | 0.00479671, 0.239836 | — | 0.6 s |
| B07 · Qual a economia efetivada por tipo de inteligência, somando todas as competências da planilha? | ✅ | 196874, 138896 | — | 1.0 s |

## genie

| Pergunta | Resultado | Referência | Faltou | Tempo |
|---|---|---|---|---|
| B01 · Quanto foi glosado no mês por cláusula do contrato, em valor e em número de itens? | ✅ | 55484.2, 39875.4, 26589.3 | — | 18.2 s |
| B02 · Qual o valor total glosado e qual a taxa de glosa sobre o valor apresentado no mês? | ✅ | 121949, 0.102101 | — | 14.6 s |
| B03 · Qual código TUSS tem o maior gap entre o valor cobrado e o pactuado no contrato, e de quanto? | ✅ | 13132.9 | — | 13.2 s |
| B04 · Que fração das contas do prestador recebeu ao menos uma glosa no mês? | ✅ | 0.65 | — | 14.5 s |
| B05 · Quanto do sinistro tem conflito semântico (Pronto Socorro com caráter Eletivo)? Dê a taxa sobre os itens. | ✅ | 0.067217 | — | 14.4 s |
| B06 · Na competência mais recente da planilha da rede, qual o índice-norte e o atingimento da meta de 2%? | ✅ | 0.00479671, 0.239836 | — | 14.4 s |
| B07 · Qual a economia efetivada por tipo de inteligência, somando todas as competências da planilha? | ✅ | 196874, 138896 | — | 18.6 s |
| B08 · Qual a precisão e o recall do motor de regras contra o gabarito do case? | ✅ | 0.944056, 0.9 | — | 19.8 s |

## agente (databricks_gpt_oss)

| Pergunta | Resultado | Referência | Faltou | Tempo |
|---|---|---|---|---|
| B01 · Quanto foi glosado no mês por cláusula do contrato, em valor e em número de itens? | ✅ | 55484.2, 39875.4, 26589.3 | — | 13.1 s |
| B02 · Qual o valor total glosado e qual a taxa de glosa sobre o valor apresentado no mês? | ✅ | 121949, 0.102101 | — | 19.5 s |
| B03 · Qual código TUSS tem o maior gap entre o valor cobrado e o pactuado no contrato, e de quanto? | ✅ | 13132.9 | — | 8.9 s |
| B04 · Que fração das contas do prestador recebeu ao menos uma glosa no mês? | ✅ | 0.65 | — | 5.9 s |
| B05 · Quanto do sinistro tem conflito semântico (Pronto Socorro com caráter Eletivo)? Dê a taxa sobre os itens. | ❌ | 0.067217 | 0.067217 | 4.5 s |
| B06 · Na competência mais recente da planilha da rede, qual o índice-norte e o atingimento da meta de 2%? | ✅ | 0.00479671, 0.239836 | — | 6.1 s |
| B07 · Qual a economia efetivada por tipo de inteligência, somando todas as competências da planilha? | ✅ | 196874, 138896 | — | 5.9 s |
| B08 · Qual a precisão e o recall do motor de regras contra o gabarito do case? | ✅ | 0.944056, 0.9 | — | 17.4 s |
