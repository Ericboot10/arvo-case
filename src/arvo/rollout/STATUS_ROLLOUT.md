# Situação do rollout (F10)

> GERADO por `python -m arvo.rollout.status` com o sinistro real do case. Evidência de auditoria = gabarito como rodada 0
> (pós-estratificado, F8): serve para exercitar os critérios, não para promover regra.

**Portão de sanidade:** LIBERADO.

## 1. Estado vigente: todas as regras em SHADOW

| Regra | Estágio | Destino | Apontamentos | Valor |
|---|---|---|---|---|
| R1 | SHADOW | NAO_ENVIAR | 175 | R$ 39.875,41 |
| R2 | SHADOW | NAO_ENVIAR | 50 | R$ 51.081,77 |
| R3 | SHADOW | NAO_ENVIAR | 67 | R$ 4.402,40 |
| R4 | SHADOW | NAO_ENVIAR | 77 | R$ 26.589,35 |

Nada é enviado: tudo fica em `gold_shadow` até a regra cumprir os critérios e ser promovida por quem aprova.

## 2. O que falta para SHADOW → CANÁRIO

| Regra | Auditados / plano | Precisão | Limite inferior IC 95% | Apta | O que falta |
|---|---|---|---|---|---|
| R1 | 67 / 91 | 92,5% | 83,7% | não | amostra: 67 (precisa 91); precisao_inf: 0,837 (precisa 0,950); duracao: 0 (precisa 4) |
| R2 | 22 / 40 | 90,9% | 72,2% | não | amostra: 22 (precisa 40); precisao_inf: 0,722 (precisa 0,950); duracao: 0 (precisa 4) |
| R2B | 0 / — | — | — | não | amostra: regra sem apontamentos no período (sem plano amostral); precisao_inf: sem dado (precisa 0,950); duracao: 0 (precisa 4) |
| R3 | 25 / 50 | 96,0% | 80,5% | não | amostra: 25 (precisa 50); precisao_inf: 0,805 (precisa 0,950); duracao: 0 (precisa 4) |
| R4 | 29 / 55 | 100,0% | 88,3% | não | amostra: 29 (precisa 55); precisao_inf: 0,883 (precisa 0,950); duracao: 0 (precisa 4) |

Aprovadores da promoção: auditor_medico, cientista_dados.

## 3. Simulação: e se todas estivessem em AUTOMÁTICO hoje?

Teto de valor do envio automático, pela matriz de custo (AMB-20) e pelo limite inferior do IC de cada regra:

| Regra | Limite inferior IC 95% | Teto do envio automático |
|---|---|---|
| R1 | 83,7% | R$ 0,00 |
| R2 | 72,2% | R$ 0,00 |
| R3 | 80,5% | R$ 0,00 |
| R4 | 88,3% | R$ 0,00 |

Teto zero = abaixo do piso de 95% do comitê: nada sai automático. Com a mesma matriz de custo, o teto seria R$ 1.700,00 com limite inferior de 95%, R$ 4.700,00 com 98% e R$ 9.700,00 com 99% (trava de política em R$ 10.000,00).

| Regra | Destino | Apontamentos | Valor |
|---|---|---|---|
| R1 | REVISAO_HUMANA | 175 | R$ 39.875,41 |
| R2 | REVISAO_HUMANA | 50 | R$ 51.081,77 |
| R3 | REVISAO_HUMANA | 67 | R$ 4.402,40 |
| R4 | REVISAO_HUMANA | 77 | R$ 26.589,35 |

**E o painel de sanidade rebaixaria automaticamente:**

- R1: AUTOMATICO → CANARIO · S05 em ALERTA: precisão auditada abaixo do critério
- R2: AUTOMATICO → CANARIO · S05 em ALERTA: precisão auditada abaixo do critério
- R3: AUTOMATICO → CANARIO · S05 em ALERTA: precisão auditada abaixo do critério
- R4: AUTOMATICO → CANARIO · S06 em ALERTA: precisão sem evidência suficiente para envio direto

Estado depois do rebaixamento: R1 CANARIO, R2 CANARIO, R2B SHADOW, R3 CANARIO, R4 CANARIO.
É o que a F8 já indicava: com a evidência de hoje, nenhuma regra fica em envio direto.
