# Painel de sanidade · avaliação local

> GERADO por `python -m arvo.monitoring.local`. Mesmo SQL do Databricks (dialeto local). Dados: sinistro real do case,
> planilha do funil, gabarito como rodada 0 de auditoria (não probabilística).

**Portão de envio: LIBERADO**

| Seção | OK | ALERTA | CALIBRANDO | SEM_DADO | SEM_FONTE |
|---|---|---|---|---|---|
| Parte I · Agente · Hospital São Rafael (jun/2025) | 6 | 8 | 12 | 0 | 2 |
| Parte II · Funil da rede Parthenon (6 meses) | 14 | 3 | 27 | 0 | 0 |
| Aderência semântica | 3 | 1 | 0 | 0 | 0 |
| Engenharia de dados | 7 | 0 | 0 | 0 | 0 |
| IA | 0 | 0 | 0 | 10 | 0 |

## Parte I · Agente · Hospital São Rafael (jun/2025)

| Status | Id | Indicador | Recorte | Valor | Banda | Sev. | Dono | Ação |
|---|---|---|---|---|---|---|---|---|
| **CALIBRANDO** | S03 | Taxa de glosa sobre o apresentado, por regra | regra_principal=R1 | 19,93% | histórico 0/6 | MEDIA | analytics_engineer |  |
| **CALIBRANDO** | S03 | Taxa de glosa sobre o apresentado, por regra | regra_principal=R2 | 100,00% | histórico 0/6 | MEDIA | analytics_engineer |  |
| **CALIBRANDO** | S03 | Taxa de glosa sobre o apresentado, por regra | regra_principal=R3 | 100,00% | histórico 0/6 | MEDIA | analytics_engineer |  |
| **CALIBRANDO** | S03 | Taxa de glosa sobre o apresentado, por regra | regra_principal=R4 | 100,00% | histórico 0/6 | MEDIA | analytics_engineer |  |
| **CALIBRANDO** | S04 | Gap cobrado vs pactuado (R$) | total | R$ 39.875,41 | histórico 0/6 | INFO | especialista_contas_medicas |  |
| **CALIBRANDO** | S40 | Taxa de glosa identificada (glosado ÷ apresentado) | total | 10,21% | histórico 0/6 | MEDIA | pm_cs |  |
| **ALERTA** | S05 | Precisão auditada (ponderada), por regra | regra_principal=R1 | 92,38% | ≥ 98,00% | ALTA | cientista_dados | Regra em envio automático cai para REVISAO_HUMANA (kill switch da regra) |
| **ALERTA** | S05 | Precisão auditada (ponderada), por regra | regra_principal=R2 | 90,21% | ≥ 98,00% | ALTA | cientista_dados | Regra em envio automático cai para REVISAO_HUMANA (kill switch da regra) |
| **ALERTA** | S05 | Precisão auditada (ponderada), por regra | regra_principal=R3 | 96,92% | ≥ 98,00% | ALTA | cientista_dados | Regra em envio automático cai para REVISAO_HUMANA (kill switch da regra) |
| **OK** | S05 | Precisão auditada (ponderada), por regra | regra_principal=R4 | 100,00% | ≥ 98,00% | ALTA | cientista_dados |  |
| **ALERTA** | S06 | Limite inferior do IC 95% da precisão, por regra | regra_principal=R1 | 83,69% | ≥ 95,00% | ALTA | cientista_dados | Manter a regra em REVISAO_HUMANA e ampliar a amostra auditada (plano amostral F8) |
| **ALERTA** | S06 | Limite inferior do IC 95% da precisão, por regra | regra_principal=R2 | 72,19% | ≥ 95,00% | ALTA | cientista_dados | Manter a regra em REVISAO_HUMANA e ampliar a amostra auditada (plano amostral F8) |
| **ALERTA** | S06 | Limite inferior do IC 95% da precisão, por regra | regra_principal=R3 | 80,46% | ≥ 95,00% | ALTA | cientista_dados | Manter a regra em REVISAO_HUMANA e ampliar a amostra auditada (plano amostral F8) |
| **ALERTA** | S06 | Limite inferior do IC 95% da precisão, por regra | regra_principal=R4 | 88,30% | ≥ 95,00% | ALTA | cientista_dados | Manter a regra em REVISAO_HUMANA e ampliar a amostra auditada (plano amostral F8) |
| **ALERTA** | S07 | Indevido não detectado (ponderado) | total | 13,98% | ≤ 5,00% | MEDIA | cientista_dados | Abrir os FN da rodada: regra nova (vira AMB) ou ruído de rotulagem (teste de concentração F8) |
| **SEM_FONTE** | S08 | Taxa de recurso | total | — | — | ALTA | juridico |  |
| **SEM_FONTE** | S09 | Taxa de reversão (precisão em campo) | total | — | — | CRITICA | juridico |  |
| **CALIBRANDO** | S14 | Contas com glosa, por prestador | id_prestador=P001 | 65,00% | histórico 0/6 | MEDIA | pm_cs |  |
| **OK** | S15 | Concentração da glosa nas 10 maiores contas | total | 17,69% | ≤ 50,00% | INFO | pm_cs |  |
| **CALIBRANDO** | S16 | Itens glosados, por regra (hit rate) | regra_principal=R1 | 17500,00% | histórico 0/6 | MEDIA | analytics_engineer |  |
| **CALIBRANDO** | S16 | Itens glosados, por regra (hit rate) | regra_principal=R2 | 5000,00% | histórico 0/6 | MEDIA | analytics_engineer |  |
| **CALIBRANDO** | S16 | Itens glosados, por regra (hit rate) | regra_principal=R3 | 6700,00% | histórico 0/6 | MEDIA | analytics_engineer |  |
| **CALIBRANDO** | S16 | Itens glosados, por regra (hit rate) | regra_principal=R4 | 7700,00% | histórico 0/6 | MEDIA | analytics_engineer |  |
| **CALIBRANDO** | S17 | Cobertura de preço pactuado | total | 100,00% | histórico 0/6 | MEDIA | especialista_contas_medicas |  |
| **OK** | S18 | Apontamentos que violam invariantes | total | 0 | ≤ 0 | CRITICA | juridico |  |
| **OK** | S19 | Itens com mais de uma glosa | total | 0 | ≤ 0 | CRITICA | engenheiro_dados |  |
| **OK** | S20 | Contas com glosa maior que o cobrado | total | 0 | ≤ 0 | CRITICA | juridico |  |
| **OK** | S21 | Apontamentos sem item auditado (órfãos) | total | 0 | ≤ 0 | CRITICA | engenheiro_dados |  |

## Parte II · Funil da rede Parthenon (6 meses)

| Status | Id | Indicador | Recorte | Valor | Banda | Sev. | Dono | Ação |
|---|---|---|---|---|---|---|---|---|
| **ALERTA** | S01 | Índice-norte da rede (efetivado ÷ sinistro da rede) | total | 0,48% | ≥ 2,00% | ALTA | pm_cs | Abrir a árvore do norte (M21 × M22 × M23 × M24 × M18) e atacar o fator que mais caiu |
| **ALERTA** | S02 | Atingimento da meta da rede (run-rate) | total | 23,98% | ≥ 80,00% | ALTA | pm_cs | Reprojetar a trajetória com o Paulo; priorizar inteligências desligadas de maior valor |
| **CALIBRANDO** | S10 | Ativação (identificado em ligadas ÷ total) | total | 50,12% | histórico 0/3 | MEDIA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Alto Markup | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Cobrança em excesso de anatomia patológica | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Cobrança inadequada de anatomia patológica | 80,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Cobrança indevida de procedimentos ambulatoriais durante internação | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Conformidade auxiliares | 100,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Conformidade taxas de sala | 94,37% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Conformidade vias de acesso | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Código-descrição divergentes | 90,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Códigos inativos | 90,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Códigos inválidos | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Guias duplicadas | 70,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Pertinencia de Materiais | 25,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Pertinência de taxas | 80,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Pertinência em Pronto Socorro | 50,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Quantidade Excessiva de Materiais | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Quantidade excessiva SADT ambulatorial | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Quantidade excessiva SADT internação | 50,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Quantidade excessiva de taxas | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Quantidade excessiva de terapia internação | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Quantidade excessiva de terapia sequencial | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Reexecução SADT | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Serviço fora do Rol ANS | 100,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Sobreposição de SADT | — | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Sobreposição de consultas | 37,50% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Sobreposição de procedimentos cirúrgicos | 50,00% | histórico 0/3 | ALTA | pm_cs |  |
| **CALIBRANDO** | S11 | Envio à operadora (1 − retenção) | inteligencia=Sobreposição de taxas | 100,00% | histórico 0/3 | ALTA | pm_cs |  |
| **ALERTA** | S12 | Perda de registro no prestador | total | 30,37% | ≤ 5,00% | ALTA | pm_cs | Conciliar enviados × registrados com a TI da Parthenon (Alana): integração, rejeição ou prazo |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Cobrança inadequada de anatomia patológica | 93,95% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Conformidade auxiliares | 93,52% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Conformidade taxas de sala | 102,30% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Código-descrição divergentes | 98,82% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Códigos inativos | 105,96% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Guias duplicadas | 99,89% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Pertinencia de Materiais | 105,87% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Pertinência de taxas | 111,26% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Pertinência em Pronto Socorro | 105,52% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Quantidade excessiva SADT internação | 102,05% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Serviço fora do Rol ANS | 99,99% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Sobreposição de consultas | 103,41% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Sobreposição de procedimentos cirúrgicos | 98,95% | ≥ 80,00% | MEDIA | juridico |  |
| **OK** | S13 | Efetivação ÷ benchmark Arvo, por inteligência | inteligencia=Sobreposição de taxas | 107,85% | ≥ 80,00% | MEDIA | juridico |  |

## Aderência semântica

| Status | Id | Indicador | Recorte | Valor | Banda | Sev. | Dono | Ação |
|---|---|---|---|---|---|---|---|---|
| **OK** | S22 | Aderência semântica (itens com conceito) | total | 100,00% | ≥ 100,00% | ALTA | analytics_engineer |  |
| **ALERTA** | S23 | Conflito semântico (ex.: PS × Eletivo) | total | 6,72% | ≤ 1,00% | MEDIA | especialista_contas_medicas | Conflitos vão para REVISAO_HUMANA (AMB-01); se crescem, o prestador mudou a codificação |
| **OK** | S24 | Versões da semântica num mesmo run | run_id=f9-sanidade | 1 | ≤ 1 | CRITICA | analytics_engineer |  |
| **OK** | S25 | Versões do contrato num mesmo run | run_id=f9-sanidade | 1 | ≤ 1 | CRITICA | engenheiro_dados |  |

## Engenharia de dados

| Status | Id | Indicador | Recorte | Valor | Banda | Sev. | Dono | Ação |
|---|---|---|---|---|---|---|---|---|
| **OK** | S26 | Expectations de falha reprovadas (último run) | total | 0 | ≤ 0 | CRITICA | engenheiro_dados |  |
| **OK** | S27 | Taxa de quarentena (último run) | total | 0,00% | ≤ 2,00% | ALTA | engenheiro_dados |  |
| **OK** | S28 | Pass rate por dimensão de qualidade (último run) | dimensao=acuracia | 100,00% | ≥ 99,00% | MEDIA | engenheiro_dados |  |
| **OK** | S28 | Pass rate por dimensão de qualidade (último run) | dimensao=completude | 100,00% | ≥ 99,00% | MEDIA | engenheiro_dados |  |
| **OK** | S28 | Pass rate por dimensão de qualidade (último run) | dimensao=consistencia | 99,07% | ≥ 99,00% | MEDIA | engenheiro_dados |  |
| **OK** | S28 | Pass rate por dimensão de qualidade (último run) | dimensao=unicidade | 100,00% | ≥ 99,00% | MEDIA | engenheiro_dados |  |
| **OK** | S28 | Pass rate por dimensão de qualidade (último run) | dimensao=validade | 100,00% | ≥ 99,00% | MEDIA | engenheiro_dados |  |

## IA

| Status | Id | Indicador | Recorte | Valor | Banda | Sev. | Dono | Ação |
|---|---|---|---|---|---|---|---|---|
| **SEM_DADO** | S30 | Schema válido | total | — | — | ALTA | cientista_dados |  |
| **SEM_DADO** | S31 | Recusa | total | — | — | MEDIA | cientista_dados |  |
| **SEM_DADO** | S32 | Truncamento | total | — | — | MEDIA | cientista_dados |  |
| **SEM_DADO** | S33 | Erro | total | — | — | ALTA | engenheiro_dados |  |
| **SEM_DADO** | S34 | Fallback de provedor | total | — | — | MEDIA | engenheiro_dados |  |
| **SEM_DADO** | S35 | Bloqueio por política de dados | total | — | — | CRITICA | engenheiro_dados |  |
| **SEM_DADO** | S36 | Bloqueio por circuito | total | — | — | ALTA | engenheiro_dados |  |
| **SEM_DADO** | S37 | Latência p95 (ms) | total | — | — | MEDIA | engenheiro_dados |  |
| **SEM_DADO** | S38 | Parâmetro pedido e não aplicado | total | — | — | INFO | cientista_dados |  |
| **SEM_DADO** | S39 | Drift de modelo | total | — | — | ALTA | cientista_dados |  |
