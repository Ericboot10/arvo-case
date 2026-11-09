# F11: Parte 2 · funil de economia

> **Status:** memo e deck prontos. Os números saem de [`analise_funil.py`](analise_funil.py) e estão cobertos por 4 testes.
> **Escopo confirmado (AMB-06):** a planilha é da operação inteira, com toda a rede; o extrato da Parte 1 é de um mês de um único prestador, e os números não precisam bater. Valores tratados como mensais (sinistro de R$ 70 mi = sinistro médio mensal).
> **Ainda aberto:** AMB-05, a definição exata de cada etapa do funil.

## Entregáveis
- **Memo:** [Parte 2 · Funil de economia Parthenon: diagnóstico e plano para 2%](https://claude.ai/artifact/Y3i8MpGuPeFnxUxc7BxnCf)
- **Deck, 10 slides:** [Parte 2 · Funil de economia Parthenon](https://claude.ai/artifact/Duao3bxGMDvN5R9Uq6jTTs)

Os dois links são privados até serem compartilhados pelo menu Share.

## Tese em uma linha
A Arvo identifica 2,77% do sinistro e a Parthenon efetiva 0,48%. O gargalo é converter, não detectar.

## Números principais (R$ por mês, junho de 2025)
| Etapa | Valor |
|---|---|
| Identificado | 1.936.700 (2,77%) |
| − Inteligências desligadas | 966.000 |
| − Retido na operadora | 433.720 |
| − Perda de registro | 163.065 |
| − Perda em recurso | 38.145 |
| **Efetivado** | **335.770 (0,48%)** |

| Cenário | Efetivado | % do sinistro |
|---|---|---|
| Conservador | R$ 842 mil | 1,20% |
| Base | R$ 1,12 mi | 1,60% |
| Agressivo | R$ 1,33 mi | 1,90% |

Nenhum cenário chega a 2% só convertendo melhor: o resto depende de identificar mais.

## Rodar
```bash
python -m arvo.funnel.analise_funil
```
```bash
pytest tests/funnel -v
```
