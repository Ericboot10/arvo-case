# F8 · Avaliação científica do agente de glosa

> Gerado por `python -m arvo.evaluation.relatorio`. Motor da F6 (regras v1.0.0, contrato `rascunho-F2`) sobre 1696 itens do sinistro, comparado com os 263 itens do gabarito.

## 1. Resposta à pergunta 3 do case

**Precisão 94,4% [89,3% – 97,1%] · Recall 90,0% [84,2% – 93,8%]** (na amostra do gabarito, IC 95% de Wilson). TP 135 · FP 8 · FN 15 · TN 105.

**O que cada uma significa para o negócio:**
- **Precisão** = de cada R$ 100 glosados, quanto é de fato indevido. Um FP é uma glosa errada: vira recurso, custo operacional, desgaste com o hospital e, principalmente, **perda de confiança da auditoria médica**. Retenção pela auditoria é a segunda maior perda do funil (22% do identificado).
- **Recall** = de cada R$ 100 indevidos, quanto o agente pega. Um FN é dinheiro deixado na mesa, mas é recuperável (nova regra, nova rodada) e não gera conflito.

**Qual priorizar: precisão.** E não por preferência, mas pela matriz de custo (seção 4):
- uma glosa indevida custa operação e atrito;
- uma glosa devida que não foi feita só deixa de ganhar e pode ser recuperada depois;
- o agente opera sobre o funil da Parte 2, em que a efetivação depende da confiança de quem envia.

**Por que não dá 100%:**
- Todas as 23 divergências têm causa provável identificada.
- Os FP são regras contratuais de condição objetiva que o gabarito marcou como "Não".
- Os FN não têm nenhuma base contratual.
- O teste de permutação (p = 0.85) **não** mostra concentração dos FN em nenhum conceito: o padrão é de **ruído de rotulagem**, não de regra escondida (seção 5).

**O que falta para decidir:**
1. A **adjudicação cega** das divergências por dois revisores. O pacote está pronto: 46 casos, com controles misturados.
2. O **shadow**, com a amostra auditada por regra da seção 7. Com o gabarito atual, **nenhuma regra atinge o piso de 95% no limite inferior do IC**, porque há poucos itens rotulados por regra.

## 2. Métricas na amostra

| Métrica | Valor | IC 95% |
|---|---|---|
| Precisão (contagem) | 94,4% | [89,3% – 97,1%] |
| Recall (contagem) | 90,0% | [84,2% – 93,8%] |
| Precisão em R$ | 92,8% | [84,6% – 99,2%] (bootstrap por conta) |
| Recall em R$ (limite inferior: FN valorado pelo cobrado) | 74,2% | [58,4% – 90,5%] |
| R$ glosado corretamente / indevidamente | R$ 45.598,04 / R$ 3.527,60 | |

## 3. Estimativa para o sinistro inteiro (o gabarito é enriquecido)

| Código | % na população | % no gabarito | Super-representação |
|---|---|---|---|
| 20103077 | 1,9% | 6,1% | 3,1× |
| 70520020 | 2,6% | 6,1% | 2,3× |
| 99999001 | 6,5% | 11,4% | 1,8× |
| 70402600 | 3,2% | 4,6% | 1,4× |
| 20103050 | 2,2% | 2,7% | 1,2× |
| 31001012 | 3,7% | 4,2% | 1,1× |

| Método | Válido? | Precisão | Recall | Glosas previstas × reais |
|---|---|---|---|---|
| Reponderação por código TUSS | **NÃO** | 93,7% | 86,6% | 791 × 369 |
| Pós-estratificação código × decisão do motor | **sim** | 94,5% [90,8% – 97,9%] | 65,5% [57,5% – 74,2%] | 369 × 369 |

**Leitura:**
- Reponderar só por código **falha no teste de validade**: prevê 791 glosas onde o motor faz 369. O gabarito foi selecionado de forma correlacionada com o resultado, então tratar a amostra como aleatória **superestima o recall**.
- Pós-estratificar pela decisão do motor, que é conhecida para os 1.696 itens, corrige isso e passa no teste.
- A **precisão populacional é estável** (94,5%). O **recall populacional cai para 65,5%**, **se** os FN do gabarito estiverem certos: os ~12,5% de "Sim" entre os não glosados, escalados para 1327 itens, viram muitos FN estimados.
- **A qualidade do rótulo domina o resultado.** Isso torna a adjudicação a primeira decisão a tomar.

## 4. Por regra e ponto de operação (matriz de custo, premissas AMB-20)

| Regra | Rotulados | Precisão | IC 95% | Valor médio | Custo do FP | Custo esperado automático | Modo |
|---|---|---|---|---|---|---|---|
| R1 | 67 | 92,5% | [83,7% – 96,8%] | R$ 227,86 | R$ 105,57 | R$ 17,22 | **REVISAO_HUMANA** |
| R2 | 22 | 90,9% | [72,2% – 97,5%] | R$ 1.021,64 | R$ 264,33 | R$ 73,52 | **REVISAO_HUMANA** |
| R3 | 25 | 96,0% | [80,5% – 99,3%] | R$ 65,71 | R$ 73,14 | R$ 14,29 | **REVISAO_HUMANA** |
| R4 | 29 | 100,0% | [88,3% – 100,0%] | R$ 345,32 | R$ 129,06 | R$ 15,10 | **REVISAO_HUMANA** |

**Como ler:**
- Todas as regras têm **ganho esperado positivo** (enviar vale mais que não enviar). Nenhuma está BLOQUEADA.
- Mas nenhuma atinge o piso de precisão para envio **automático**: o limite inferior do IC é largo com tão poucos rotulados. Até a R4, 29/29 corretos, tem limite inferior abaixo de 95%.
- A decisão de "ir para produção" depende do **tamanho da amostra auditada**, não de mais modelagem.
- Recall por regra não existe com este gabarito, porque ele não diz qual regra deveria ter disparado.

## 5. Divergências e causas

| Item | Tipo | Regra do motor | Causa provável | Evidência | R$ |
|---|---|---|---|---|---|
| IT00564 | FP | R1 | REGRA_CONTRATUAL_LITERAL | Glosa parcial de R$ 51,55 no item IT00564 (cód. 60012010): valor unitário cobrado R$ 531,55 acima do pactuado  | R$ 51,55 |
| IT00800 | FP | R2 | REGRA_CONTRATUAL_LITERAL | Glosa integral de R$ 602,29 no item IT00800: taxa de sala (cód. 20103050) inclusa no pacote do procedimento 31 | R$ 602,29 |
| IT00970 | FP | R1 | REGRA_CONTRATUAL_LITERAL | Glosa parcial de R$ 60,86 no item IT00970 (cód. 60012010): valor unitário cobrado R$ 540,86 acima do pactuado  | R$ 60,86 |
| IT01140 | FP | R1 | REGRA_CONTRATUAL_LITERAL | Glosa parcial de R$ 100,37 no item IT01140 (cód. 60012010): valor unitário cobrado R$ 580,37 acima do pactuado | R$ 100,37 |
| IT01243 | FP | R1 | REGRA_CONTRATUAL_LITERAL | Glosa parcial de R$ 62,48 no item IT01243 (cód. 10101039): valor unitário cobrado R$ 151,24 acima do pactuado  | R$ 62,48 |
| IT00136 | FP | R2 | REGRA_CONTRATUAL_LITERAL | Glosa integral de R$ 1.226,03 no item IT00136: taxa de sala (cód. 20103077) inclusa no pacote do procedimento  | R$ 1.226,03 |
| IT00228 | FP | R1 | REGRA_CONTRATUAL_LITERAL | Glosa parcial de R$ 1.334,22 no item IT00228 (cód. 30715016): valor unitário cobrado R$ 5.134,22 acima do pact | R$ 1.334,22 |
| IT00522 | FP | R3 | REGRA_CONTRATUAL_LITERAL | Glosa integral de R$ 89,80 no item IT00522: material de rotina (cód. 70520020) incluso no pacote do procedimen | R$ 89,80 |
| IT00851 | FN | nan | SEM_BASE_CONTRATUAL | preço 98.6% do teto; código repetido 2× na conta | R$ 473,17 |
| IT01074 | FN | nan | SEM_BASE_CONTRATUAL | preço 98.3% do teto; código repetido 3× na conta | R$ 471,70 |
| IT01097 | FN | nan | SEM_BASE_CONTRATUAL | preço 99.1% do teto | R$ 35,68 |
| IT01666 | FN | nan | SEM_BASE_CONTRATUAL | preço 98.4% do teto; conflito semântico PS × Eletivo | R$ 275,60 |
| IT00196 | FN | nan | SEM_BASE_CONTRATUAL | preço 97.4% do teto; código repetido 3× na conta | R$ 467,44 |
| IT00979 | FN | nan | SEM_BASE_CONTRATUAL | preço 97.4% do teto | R$ 623,64 |
| IT00987 | FN | nan | SEM_BASE_CONTRATUAL | preço 99.7% do teto; é o próprio procedimento do pacote | R$ 3.789,15 |
| IT01047 | FN | nan | SEM_BASE_CONTRATUAL | preço 99.1% do teto; é o próprio procedimento do pacote | R$ 3.073,20 |
| IT01077 | FN | nan | SEM_BASE_CONTRATUAL | preço 99.4% do teto | R$ 15,91 |
| IT01167 | FN | nan | SEM_BASE_CONTRATUAL | preço 97.5% do teto | R$ 7,80 |
| IT00492 | FN | nan | SEM_BASE_CONTRATUAL | preço 98.4% do teto; é o próprio procedimento do pacote | R$ 4.131,92 |
| IT00143 | FN | nan | SEM_BASE_CONTRATUAL | preço 98.4% do teto; código repetido 3× na conta | R$ 472,23 |
| IT00284 | FN | nan | SEM_BASE_CONTRATUAL | preço 98.2% do teto | R$ 1.256,56 |
| IT00442 | FN | nan | SEM_BASE_CONTRATUAL | preço 98.9% do teto | R$ 474,60 |
| IT01384 | FN | nan | SEM_BASE_CONTRATUAL | preço 99.0% do teto | R$ 277,08 |

**Regra escondida × ruído de rotulagem:** entre os 120 rotulados não glosados, 12,5% estão marcados como "Sim".
- O teste de permutação do qui-quadrado (H0: a taxa independe do conceito) dá **p = 0.85**.
- Uma regra fora do contrato concentraria os "Sim" num conceito. Não é o que acontece: a taxa por conceito acompanha a base.
- Conclusão: é compatível com **ruído de rotulagem**. Mesmo assim, a pergunta AMB-03 vai para o Auditor.

## 6. Sensibilidade ao rótulo (simulação, NÃO é resultado de adjudicação)

| Cenário de adjudicação | Precisão (amostra) | Recall (amostra) | Recall (população) |
|---|---|---|---|
| Revisores concordam com o gabarito | 94,4% | 90,0% | 65,5% |
| Revisores aplicam a letra do contrato | 100,0% | 100,0% | 100,0% |

- A verdade está entre as duas linhas. A adjudicação cega diz onde.
- Mesmo no melhor cenário, o limite inferior do IC por regra continua abaixo de 95%, porque n é pequeno: R1 67/67 → 94,6%, R2 22/22 → 85,1%, R3 25/25 → 86,7%, R4 29/29 → 88,3%.
- O gabarito não substitui o shadow.

## 7. Plano amostral do shadow e da auditoria contínua (alimenta gold.fato_auditoria_amostral)

| Estrato | População/mês | Amostra auditada | Objetivo |
|---|---|---|---|
| GLOSADO · R1 | 175 | 91 | precisão ±2 p.p. (p≈98%, IC 95%, correção de população finita) |
| GLOSADO · R2 | 50 | 40 | precisão ±2 p.p. (p≈98%, IC 95%, correção de população finita) |
| GLOSADO · R3 | 67 | 50 | precisão ±2 p.p. (p≈98%, IC 95%, correção de população finita) |
| GLOSADO · R4 | 77 | 55 | precisão ±2 p.p. (p≈98%, IC 95%, correção de população finita) |
| NAO_GLOSADO (estratificado por conceito, mínimo de 10) | 1327 | 360 | indevido não detectado ±2 p.p. (estimador de recall) |

- Todo item sorteado leva o **peso amostral**, e M10 e M25 são estimadas com esse peso. É o que faltou no gabarito do case.
- O critério de go-live da regra (F10) é: limite inferior do IC ≥ 95% **e** o modo da matriz de custo = AUTOMATICO.

## 8. Premissas e limitações

- O contrato usado é a versão `rascunho-F2`: falta a aprovação do Jurídico (G3).
- As premissas de custo são da AMB-20 e não estão validadas.
- A estimativa populacional assume seleção aleatória **dentro** de cada célula código × decisão do motor.
- O recall em R$ é um limite inferior: o FN é valorado pelo valor cobrado, e não pela glosa que caberia.
- A seção 6 é uma **simulação** do fluxo de adjudicação, sem revisores reais.
- A adjudicação real usa as planilhas em `adjudicacao/`. A chave fica com o Cientista de Dados.
