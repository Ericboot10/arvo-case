# Case Arvo × Parthenon · Hospital São Rafael: respostas

**Valor glosado total: R$ 121.948,93 em 369 itens** (10,2% do sinistro de R$ 1.194.396,92). É valor identificado, não economia, e é alto por construção do extrato: ver [como ler os 10,2%](#4-valor-de-glosa-total-f6).
**Precisão 94,4% e recall 90,0%** contra o gabarito. Prioridade: precisão.
**Go-live:** nenhuma regra vai a envio automático antes do shadow.

Cada resposta aponta para a fase do projeto onde está o detalhe e o código. Tudo roda com um comando (`python -m arvo.deliverables.rodar_tudo`, ver [README](../README.md)).

---

## 1. Regras do contrato (F2, F3, F6)

O contrato PRT-2025-0417 (Curitiba/PR, vigência de 24 meses a partir de 01/01/2025) gera **cinco regras**. Cada uma é uma linha de [`src/arvo/rules/regras.yaml`](../src/arvo/rules/regras.yaml) e fundamenta a glosa numa cláusula.

| Regra | Cláusula | Quando glosa | Quanto glosa |
|---|---|---|---|
| R1 · preço acima do pactuado | 2.2 | Código do Anexo I com valor unitário acima do teto | Só o excedente: (cobrado − teto) × quantidade |
| R2 · taxa de sala inclusa no pacote | 3.3 | Conta com procedimento do Anexo II cobra a taxa de sala do porte correspondente | Integral |
| R2B · taxa de sala de outro porte | 3.3 | Conta com pacote cobra taxa de sala de outro porte | Integral, sempre em revisão humana (AMB-11) |
| R3 · material de rotina | 3.3 | Material da lista fechada (70520020, 70402600) em conta com pacote | Integral |
| R4 · taxa de urgência em eletivo | 4.2 | Taxa 99999001 em atendimento de caráter eletivo | Integral |

**Pré-condições e exclusões:**
- **Vigência:** atendimento fora da vigência não é glosado.
- **Cláusula 2.3:** código fora do Anexo I não entra na auditoria automática de preço.
- **Cláusula 3.4:** diárias, materiais especiais, medicamentos e SADT ficam fora do pacote.

**Toda glosa traz uma frase com a cláusula, os valores e o cálculo.** Exemplo real: *"Glosa parcial de R$ 1.129,77 no item IT00001 (cód. 31001012): valor unitário cobrado R$ 5.329,77 acima do pactuado R$ 4.200,00 no Anexo I, multiplicado por 1 unidade(s). Fundamento: Cláusula 2.2."*

**A semântica veio antes do código (F2).** Termos como "urgência", "conta" e "porte" foram definidos num glossário de 51 termos. Cada ambiguidade virou uma decisão registrada no decision log (AMB-01 a AMB-21). Exemplo: "Pronto Socorro" é **regime**, não caráter. Por isso um atendimento eletivo em PS não é glosado automaticamente: vai para revisão (AMB-01).

## 2. O agente (F3, F6, F7)

O agente roda em Python e PySpark, em duas partes:

**1. Contrato como dado (F3).**
- **Leitura:** um extrator determinístico e dois modelos de IA de **famílias diferentes** leem os Anexos I e II.
- **Revisão:** um juiz, de família diferente dos extratores, revisa.
- **Evidência:** cada valor precisa de um trecho literal do PDF que o contenha (grounding). Valor sem trecho é recusado.
- **Aprovação:** divergências vão para revisão humana, e os parâmetros só valem depois de aprovação do Jurídico.
- **Independência de provedor:** a arquitetura não depende de um provedor de IA. Há adapters trocáveis, roteador com fallback e circuit breaker, e um golden set de aceite para cada provedor (F7).
- **Privacidade:** dados do sinistro **nunca** vão para um modelo externo. A política de dados bloqueia isso no roteador, e um teste garante.

**2. Motor determinístico (F6).** As regras leem só colunas semânticas e papéis contratuais, nunca o código cru do hospital. É o mesmo resultado em toda execução: reprodutível por versão de contrato, semântica e regras, todas gravadas em cada apontamento.

**Lista de apontamentos:** [`apontamentos.csv`](apontamentos.csv), com 369 linhas: `id_item`, regra, cláusula principal e subsidiárias, cobrado, referência, **valor glosado**, justificativa e destino de envio.

## 3. Precisão e recall (F8)

| Métrica | Valor | IC 95% |
|---|---|---|
| Precisão | **94,4%** (135 de 143) | 89,3% – 97,1% |
| Recall | **90,0%** (135 de 150) | 84,2% – 93,8% |
| Precisão em R$ | 92,8% | 84,6% – 99,2% |

O intervalo de confiança é de Wilson, com bootstrap por conta para os valores em R$.

**O que significam:**
- **Precisão** é quanto do que glosamos é de fato indevido. O erro aqui é um **falso positivo**, e ele custa recurso, atrito com o hospital e a confiança do Dr. Ary.
- **Recall** é quanto do indevido pegamos. O erro aqui é um **falso negativo**: dinheiro deixado na mesa, mas recuperável depois.

**Qual priorizar: precisão.** Uma glosa errada enviada custa mais que uma glosa não feita, e a confiança perdida trava o funil inteiro, como mostra a Parte 2. Isso virou um critério verificável, e não uma opinião:
- **matriz de custo** (AMB-20): custo esperado do falso positivo contra custo da revisão humana;
- **piso de 95%** no limite inferior do IC da precisão para envio automático.

**Divergências e causas:**
- **8 falsos positivos:** todos são regras de condição objetiva no contrato que o gabarito marcou "Não".
- **15 falsos negativos:** nenhum tem base contratual. O preço está dentro do teto em todos.
- **Teste de permutação (p ≈ 0,85):** as divergências não se concentram em nenhum conceito. É o padrão de **ruído de rotulagem**, e não de uma regra escondida.
- **Adjudicação cega:** há um pacote pronto para dois revisores, com 46 casos.

**O gabarito não é amostra aleatória.** Ele foi escolhido de forma ligada à própria decisão do motor. Corrigindo isso (pós-estratificação por código × decisão do motor), o resultado para o sinistro inteiro é:
- precisão de **94,5%**;
- recall de **65,5%**, se o gabarito estiver certo.

Relatório completo: [`RELATORIO_AVALIACAO.md`](../src/arvo/evaluation/RELATORIO_AVALIACAO.md).

## 4. Valor de glosa total (F6)

**R$ 121.948,93 em 369 itens**, de 1.696 itens e 320 contas.

| Regra | Itens | Valor |
|---|---|---|
| R1 · preço acima do pactuado (2.2) | 175 | R$ 39.875,41 |
| R2 · taxa de sala no pacote (3.3) | 50 | R$ 51.081,77 |
| R3 · material de rotina no pacote (3.3) | 67 | R$ 4.402,40 |
| R4 · urgência em eletivo (4.2) | 77 | R$ 26.589,35 |
| **Total** | **369** | **R$ 121.948,93** |

Do total, 9 itens (R$ 3.087,98) são taxa de urgência em conta de Pronto Socorro com caráter eletivo. Eles **vão para revisão humana** (AMB-01).

**Como ler os 10,2%: é alto, e não deve ser projetado para a rede.**
- **O extrato foi feito para testar o agente.** O gabarito rotula 263 itens, e 150 deles (57%) são indevidos. Nenhuma auditoria real acha erro em mais da metade do que olha. As quatro regras disparam dezenas de vezes no mesmo mês. A taxa diz mais sobre o exercício do que sobre a rede.
- **Um hospital pode estar fora da média sem puxar a rede.** O contrato tem tabela de preços (Anexo I) e pacotes (Anexo II) desde 01/01/2025. O erro típico é o faturamento do hospital não ter absorvido o contrato: preço antigo e taxa de sala cobrada fora do pacote, exatamente o que R1 e R2 pegam. É um erro sistemático, que deve cair depois dos primeiros ciclos de glosa. Na Parte 2, a rede inteira fica em 2,77% identificado.
- **É valor identificado, não economia.** No funil da Parte 2, de cada R$ 1 identificado, só R$ 0,17 vira economia (0,48 ÷ 2,77).
- **Nem todo o valor tem a mesma força.** R$ 51 mil (42%) vêm da R2, que glosa a taxa de sala inteira, e R$ 26,6 mil da R4, a regra mais frágil em recurso (seção 5). A parte mais firme é a R1, que glosa só o excedente sobre a tabela: R$ 39,9 mil, 3,3% do sinistro.
- **O que acompanhar:** a taxa de glosa por hospital, mês a mês. Se ela não cair depois que o hospital recebe as primeiras glosas, deixa de ser erro de implantação e vira assunto de relacionamento com o prestador.

## 5. Defensabilidade em recurso (F2, F6)

| Regra | Posição | Por quê |
|---|---|---|
| R1 · preço (2.2) | **Mais defensável** | É um número contra uma tabela assinada, e glosamos só o excedente. Não há espaço clínico. O ataque possível é reajuste ou aditivo; por isso o motor aplica a versão vigente do contrato (SCD2) e confere a vigência |
| R3 · material de rotina (3.3) | Muito forte | A lista de códigos é fechada, e o contrato diz "integralmente" |
| R2 · taxa de sala (3.3) | Forte, com ressalva | Depende de "porte correspondente" e do escopo "conta" do pacote (AMB-02) |
| R4 · urgência em eletivo (4.2) | **Mais frágil**, no subconjunto Pronto Socorro | Depende do caráter informado. Em PS, o hospital alega urgência clínica e leva a discussão para o campo médico (AMB-01) |

**Item com várias regras:** a regra principal é a de texto mais literal e cálculo mais objetivo. As outras ficam registradas como subsidiárias. Assim o recurso enfrenta o argumento mais forte, e as subsidiárias sustentam uma segunda defesa sem reabrir a glosa.

**Indicadores de decisão:** taxa de recurso e taxa de reversão por regra (S08 e S09 no painel da F9). Uma regra com reversão acima de 5% é desligada automaticamente (F10).

## 6. Parâmetros que mudam por prestador (F2, F3)

O desenho separa o que é **universal** do que é **do contrato** ([`src/arvo/semantic/vinculos/PRT-2025-0417.yaml`](../src/arvo/semantic/vinculos/PRT-2025-0417.yaml)):

| Muda por contrato e prestador | Exemplo neste contrato |
|---|---|
| Itens com preço pactuado e tetos (Anexo I) | 17 códigos, de R$ 4,00 a R$ 4.200,00 |
| Procedimentos em pacote e o que cada um inclui (Anexo II) | 3 procedimentos; taxa de sala de cada porte |
| Escopo do pacote | "conta" (pode ser "atendimento" em outro contrato; AMB-02) |
| Itens inclusos e conceitos excluídos do pacote | 2 materiais de rotina; diária, material especial, medicamento e SADT excluídos |
| Taxas condicionadas ao caráter | 99999001 só em urgência ou emergência |
| Vigência, reajuste e aditivos | 24 meses a partir de 01/01/2025, renovação automática |
| Tratamento de código fora da tabela | Cl. 2.3: fora da auditoria automática de preço |
| **Dialeto do prestador** (mapa semântico) | Como o hospital escreve caráter e regime, e o mapa de código TUSS para conceito |

**Universal (não muda):** conceitos de negócio, regras escritas sobre **papéis contratuais** (o R1 vale para qualquer "item com preço pactuado"), templates de justificativa e métricas.

**Um hospital novo é um arquivo de vínculos, um mapa semântico e a extração do contrato pela F3. Nenhuma linha de código muda.**

**Priorização:** a métrica de recorrência (M27, prestador × conceito × cláusula em vários meses) mostra onde o problema se repete. Lá entra primeiro a regra nova ou a pauta de renegociação.

## 7. Produção: sombra antes, e como decidir que está pronto (F4, F10)

**Sombra antes, sempre.** Ligar submetendo glosas seria apostar a confiança do Dr. Ary numa precisão que o gabarito não sustenta: nenhuma regra tem limite inferior do IC acima de 95%.

**Ambientes (F4):**
- **Medalhão em três catálogos:** dev, stg e prod (bronze, silver, gold).
- **Isolamento:** o workspace de prod é isolado, e dev só tem dado sintético.
- **Dado pessoal:** o identificador do beneficiário só existe na bronze.
- **Deploy:** bundle com CI que testa antes de qualquer deploy.

**Rollout (F10):**
1. Backtest contra 3 a 6 meses de decisões reais da auditoria.
2. Regressão em stg: toda diferença entre versões precisa de explicação.
3. **Shadow em prod** (`gold_shadow`, 4 a 8 semanas): nada é enviado, e o time do Dr. Ary audita uma amostra estratificada (R1 91, R2 40, R3 50, R4 55, mais 360 não glosados).
4. **Canário por regra:** R1 e R3 primeiro, com revisão humana de 100%.
5. **Automático com guarda-corpos:**
   - envio direto até um teto de valor que a matriz de custo calcula;
   - revisão humana acima dele ou em conflito semântico;
   - kill switch por regra.

**Pronto para envio automático** quando, por regra:
- precisão auditada ≥ 98%, com limite inferior do IC ≥ 95%;
- zero violação de invariante;
- reversão ≤ 5%;
- aderência semântica de 100%;
- telemetria completa;
- integração ponta a ponta testada;
- aprovação do Auditor, do Jurídico e do PM.

**Promover é decisão humana registrada; rebaixar é automático.**

## 8. Monitoramento depois do go-live (F9)

São 38 indicadores, **negócio primeiro**, cada um com dono, banda, alerta e runbook.

| Camada | Indicadores |
|---|---|
| **Valor** | Parte I (São Rafael): taxa de glosa identificada, por regra e total, e gap cobrado vs pactuado. Parte II (rede): índice-norte (efetivado ÷ sinistro da rede, meta 2%) e atingimento da meta |
| **Qualidade da decisão** | Precisão auditada por regra (com IC), indevido não detectado (recall), **taxa de recurso**, **taxa de reversão** |
| **Funil** | Ativação, envio à operadora, perda de registro, efetivação vs benchmark |
| **Prestador e comportamento** | % de contas glosadas por prestador, concentração da glosa, hit rate por regra, cobertura do Anexo I |
| **Invariantes** (sempre 0) | Glosa maior que o cobrado, item com duas glosas, glosa sem cláusula ou evidência. **Qualquer um ≠ 0 bloqueia o envio** |
| **Semântica** | Aderência (meta 100%), conflitos como PS × Eletivo, uma versão de glossário e de contrato por run |
| **Dados** | Expectations reprovadas, quarentena, pass rate por dimensão de qualidade |
| **IA** | Schema válido, recusa, truncamento, erro, fallback, bloqueio por política de dados, latência, **parâmetro pedido e não aplicado** (ex.: temperatura ignorada), drift de modelo, tokens e custo |

O painel roda localmente e no Databricks com o mesmo SQL: metric views do Unity Catalog, alertas SQL e um dashboard AI/BI. Com os dados do case:
- **Portão liberado:** todos os invariantes estão em 0.
- **Alertas:**
  - índice-norte em 0,48%;
  - perda de registro de 30%;
  - nenhuma regra no piso de precisão.

---

## Parte 2 · Funil de economia (F11)
- Memo: [Parte 2 · Funil de economia Parthenon](https://claude.ai/artifact/Y3i8MpGuPeFnxUxc7BxnCf)
- Deck: [10 slides](https://claude.ai/artifact/Duao3bxGMDvN5R9Uq6jTTs)

**Tese:** a Arvo identifica 2,77% do sinistro, e a Parthenon efetiva 0,48%. O gargalo é converter, não detectar.

**As três perdas, cada uma com um dono:**
- inteligências desligadas: R$ 966 mil;
- retenção técnica pela auditoria: R$ 434 mil;
- perda de registro: R$ 163 mil.

As três frentes levam a 1,90% no cenário agressivo. O resto vem de identificar mais.

## O que está implementado e o que está especificado
| Implementado e testado (214 testes locais) | Especificado, aguardando ambiente ou pessoas |
|---|---|
| Semântica, motor, avaliação, painel, rollout, análise da Parte 2 | Ambientes stg e prod (exigem account console e service principals) |
| Execução no Databricks Free Edition com os dados do case: medalhão, motor, precisão e recall, sanidade, rollout e painel, com os mesmos números | |
| Extração do contrato com replay determinístico | Extração com provedores reais (sem chaves de API) |
| Pacote de adjudicação cega | Adjudicação pelos dois revisores |
| Critérios de go-live e o que falta por regra | Shadow e backtest reais (histórico da Parthenon) |
| Decision log com AMB-01 a AMB-21 | Decisões e assinaturas de Negócio, Jurídico e Auditoria |
