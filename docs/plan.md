# Case Arvo × Parthenon × Hospital São Rafael
## Plano v2: estruturado por um Comitê de Tecnologia, na ordem em que deve ser feito

> **Status:** plano. Nenhuma linha de código de produção deve ser escrita antes do Gate G2 (camada semântica aprovada).
> **Base documental:** documentação Databricks (qualidade de dados, Lakeflow expectations, medalhão, boas práticas do Unity Catalog, metric views, data quality monitoring, Declarative Automation Bundles, AI Gateway, external models, structured outputs, MLflow 3 tracing e avaliação, AI Functions, Prompt Registry) e documentação de OpenAI, Google Gemini e Anthropic sobre structured outputs, reasoning, caching, batch e redução de alucinação. Consultada em 06/11/2026. Links na seção 14.
> **v1** fica em `docs/history/plan-v1.md`. Os números dela passam a ser **hipóteses a validar**, não resultados.

---

## 0. Autocrítica da v1 (por que refazer)

| Problema da v1 | Consequência | Correção na v2 |
|---|---|---|
| Codificou as regras **antes de existir camada semântica** | O número pode bater e ainda assim não responder à pergunta de negócio. Termos como "urgência", "conta" e "porte" foram assumidos, não definidos | Fase 2 inteira para semântica, com sign-off do negócio e da auditoria médica antes do código |
| Não definiu **papéis** | Estrutura rasa: ninguém dono da definição de "glosa efetivada", do contrato de dados ou do risco de IA | Comitê com papéis, entregáveis e decisões (seção 1) |
| Tratou o gabarito como verdade | O gabarito é uma **amostra enriquecida** (ex.: taxa de urgência = 11,4% do gabarito vs 6,5% da população). Precisão e recall medidos nele **não representam a população** | Fase 8: avaliação estratificada, intervalos de confiança e adjudicação das divergências |
| "LLM opcional" sem arquitetura | Sem independência de provedor, telemetria, versionamento de prompt ou critério de aceite | Fase 7: Ports & Adapters, matriz de capacidades por provedor, estado, cache, orçamento e telemetria |
| Medalhão sem ambientes | Sem dev/stg/prod, sem promoção controlada, sem isolamento LGPD | Fase 4: catálogo por ambiente, bundles com targets e CI/CD |
| Indicadores só técnicos | Não respondiam "o agente está gerando economia defensável?" | Fase 9: indicadores de **negócio primeiro**, depois semântica, dados e IA |

---

## 1. O Comitê: papéis, missões e o que cada um decide

| # | Papel | Missão no projeto | Entregáveis | Decide (dono) | Não-negociável do papel |
|---|---|---|---|---|---|
| 1 | **Product Manager / Customer Success** | Traduzir dor do cliente em perguntas de negócio e metas | Árvore de KPIs, mapa de personas, escopo e anti-escopo | Prioridade e escopo | Toda feature responde a uma pergunta de negócio escrita |
| 2 | **Especialista em Contas Médicas / Faturamento hospitalar** (TISS/TUSS, pacotes, taxas) | Dono do **significado** dos termos do domínio | Glossário, mapa TUSS → conceito, regras de domínio | Definição de termos operacionais | Nenhum termo entra no código sem definição aprovada |
| 3 | **Auditor Médico** (par técnico do Dr. Ary) | Validar pertinência clínica e defensabilidade | Revisão dos casos ambíguos, adjudicação do gabarito, limiares | Glosa técnica e casos de PS, urgência e pacote | Glosa que abre discussão clínica passa por revisão humana |
| 4 | **Especialista Jurídico-Contratual** | Interpretar cláusulas e a hierarquia entre elas | Matriz cláusula → regra → evidência exigida, parecer de defensabilidade | Interpretação contratual | Toda glosa cita cláusula, evidência e cálculo (Cláusula 5.2) |
| 5 | **Arquiteto de Soluções / Plataforma** | Desenho ponta a ponta, ambientes e decisões arquiteturais | ADRs, diagrama C4, topologia dev/stg/prod | Arquitetura e padrões | Nenhum acoplamento direto a SDK de provedor no core |
| 6 | **Engenheiro de Dados** | Ingestão, medalhão, contratos de dados, pipelines | Pipelines Lakeflow, data contracts, expectations | Modelagem física e SLAs | Silver nunca é escrita direto da ingestão (orientação Databricks) |
| 7 | **Analytics Engineer** (camada semântica) | Materializar a semântica em ativos consultáveis | Tabelas de dimensão e mapeamento, **UC Metric Views**, metadados para agentes | Definição técnica das métricas | Métrica definida uma vez, reusada em todo lugar |
| 8 | **Data Quality Steward** | Qualidade nas 6 dimensões, quarentena, monitoramento | Catálogo de expectations, monitores, runbook de incidentes | Severidade (warn/drop/fail) | Dado que não passa não alimenta glosa |
| 9 | **Analista de Dados** | Perfilamento, descoberta de padrões, funil (Parte 2) | Relatório de perfilamento, análise do funil | — | Todo achado com evidência reproduzível |
| 10 | **Cientista de Dados** | Avaliação estatística, amostragem e métricas de decisão | Plano de avaliação, ICs, plano amostral do shadow, matriz de custo | Critérios estatísticos de go-live | Métrica sem intervalo de confiança não vai para decisão |
| 11 | **Engenheiro de IA Sênior / LLMOps** | Camada de IA independente de provedor, avaliação, telemetria | Port/adapters, matriz de capacidades, golden set, telemetria por chamada | Modelos, parâmetros, prompts | LLM fora do caminho crítico da decisão de glosa. Toda chamada auditável |
| 12 | **Segurança, Privacidade e Governança (LGPD)** | Dado de saúde é **dado pessoal sensível** | Classificação, mascaramento, política de envio a provedores externos | O que pode sair do perímetro | Sem PHI real em dev e sem PHI em prompt sem base legal ou contrato com o provedor |
| 13 | **MLOps / DevOps** | CI/CD, promoção entre ambientes, observabilidade | Pipelines CI, bundles, alertas | Processo de release | Código promove, dado não promove |

**Rituais do comitê:** ADR para cada decisão estrutural, registro de ambiguidades semânticas (decision log) e gate formal ao fim de cada fase, com o dono assinando.

---

## 2. Princípios de arquitetura (valem para todas as fases)

1. **Semântica antes de código.** Regras referenciam *conceitos* aprovados (`conceito = TAXA_SALA_CIRURGICA`), nunca colunas cruas nem descrições.
2. **Decisão determinística, IA assistiva.** A glosa é decidida por um motor de regras versionado. A IA lê contratos, sugere mapeamentos e redige textos, sempre com validação. Por isso o **resultado de glosa é idêntico com qualquer provedor**, porque o provedor só influencia artefatos que passam por consenso e aprovação humana antes de virar parâmetro.
3. **Independência de provedor em duas camadas.**
   - Na aplicação: Ports & Adapters.
   - Na infraestrutura: AI Gateway, com endpoint OpenAI-compatível, fallbacks e traffic splitting.
   - Se todos os LLMs falharem, existe caminho **determinístico** (parser e transcrição revisada). O sistema degrada, mas não para.
4. **Tudo versionado e rastreável.** Contrato, glossário, regra, prompt, modelo, schema e run. Delta time travel e lineage do Unity Catalog.
5. **Gates com critério numérico.** Nada avança por opinião.
6. **Privacidade por padrão.** Minimização: o LLM recebe o *contrato*, não o *sinistro do paciente*.

---

## 3. Visão geral: fases, donos e gates (ordem obrigatória)

| Fase | Nome | Líder | Participantes | Gate de saída |
|---|---|---|---|---|
| F0 | Enquadramento do problema | PM/CS | Negócio, Auditor, Jurídico | **G0:** perguntas de negócio e KPI tree aprovadas |
| F1 | Descoberta e perfilamento | Analista de Dados | Eng. Dados, DQ | **G1:** relatório de perfilamento e data contract rascunho |
| F2 | **Camada semântica** | Especialista Contas Médicas | Auditor, Jurídico, Analytics Eng | **G2:** glossário, ontologia e ambiguidades decididas (sign-off) |
| F3 | Contrato como dado | Jurídico | Eng. IA, Negócio | **G3:** `contract_params` aprovado, 100% dos campos com evidência |
| F4 | Plataforma e ambientes | Arquiteto | Eng. Dados, Segurança, MLOps | **G4:** dev/stg/prod provisionados, CI verde |
| F5 | Pipelines medalhão e qualidade | Eng. Dados | DQ Steward, Analytics Eng | **G5:** expectations nas 6 dimensões, monitores ativos |
| F6 | Motor de regras | Eng. Dados | Negócio, Jurídico | **G6:** 100% dos testes de regra e borda passando |
| F7 | Camada de IA independente de provedor | Eng. IA | Arquiteto, Segurança | **G7:** golden set aprovado em ≥ 2 provedores, telemetria completa |
| F8 | Avaliação científica | Cientista de Dados | Auditor, Negócio | **G8:** métricas com IC, divergências adjudicadas |
| F9 | Indicadores de sanidade | Analytics Eng + DQ + Eng. IA | Todos | **G9:** painel e alertas com donos e runbooks |
| F10 | Rollout (shadow → canário → automático) | PM + Cientista | Todos | **G10:** critérios de go-live por regra atingidos |
| F11 | Parte 2: funil e otimização | PM/CS + Analista | Negócio, Auditor | Memo e deck aprovados |
| F12 | Entrega e apresentação | PM | Todos | Ensaio e checklist |

F3 e F4 podem correr em paralelo após o G2. F7 pode começar no G2, em paralelo com F5 e F6.

---

## F0. Enquadramento do problema

**Líder: PM/CS.** Antes de tecnologia, escreva o problema.

**Recomendações por especialista:**
- **PM:** escrever o *problem statement*: "A Parthenon paga ao Hospital São Rafael valores em desacordo com o contrato PRT-2025-0417. Queremos identificar, fundamentar e efetivar essas glosas de forma defensável, contribuindo para a meta de ≥ 2% do sinistro (R$ 1,4 mi/mês)."
- **PM + Negócio:** catálogo de **perguntas de negócio** que o sistema deve responder. Ele é o teste de aceite da camada semântica:
  1. Quanto foi cobrado acima do contrato, por cláusula, por mês e por prestador?
  2. Quais itens foram cobrados à parte quando estavam inclusos em pacote? Em quais cirurgias isso é recorrente?
  3. Quanto da glosa identificada vira glosa efetivada? Onde se perde?
  4. Qual regra tem maior taxa de recurso e de reversão?
  5. Qual procedimento tem maior gap entre o cobrado e o pactuado? (É a pergunta que um agente futuro deve responder sozinho.)
  6. O comportamento de cobrança do prestador mudou depois das glosas?
- **CS:** mapa de personas com dor **quantificada**:
  - Paulo: meta de 2%, efetivando 0,48%
  - Alana: perda de ~30% entre o enviado e o registrado
  - Dr. Ary: técnicas enviadas em 45% vs 83% das administrativas
- **Jurídico:** escopo contratual. Cláusulas 2.2, 3.2, 3.3 e 4.2 estão dentro. A 2.3 (itens fora do Anexo I) está **fora** da auditoria automática de preço. A 3.4 lista exclusões do pacote.
- **Anti-escopo explícito:** glosa clínica de pertinência, itens sem preço pactuado, reajustes não formalizados.

**G0:** perguntas, KPI tree e escopo assinados por PM, Negócio e Jurídico.

---

## F1. Descoberta e perfilamento de dados

**Líder: Analista de Dados.** Descrever o que o dado **é**, sem interpretar ainda.

**Achados já observados (precisam ser confirmados formalmente):**

| Achado | Evidência | Implicação para F2 |
|---|---|---|
| 1.696 itens, 320 contas, 178 beneficiários, 1 prestador, 16 códigos TUSS, todas as datas em jun/2025 | Perfilamento | Volume pequeno: o desenho deve escalar, mas o case é amostra |
| `carater_atendimento` tem só 2 valores: `Eletivo`, `Urgência` | Contagem | O contrato fala em "urgência **ou emergência**". Onde está emergência? (F2) |
| **114 itens em Pronto Socorro com caráter Eletivo** | Crosstab caráter × tipo_conta | Conflito semântico: local de atendimento ≠ caráter (F2) |
| 66 itens Ambulatorial + Urgência | Crosstab | Validar se é coerente para o negócio |
| 25 consultas em consultório dentro de contas de Internação | Filtro | "Consulta em consultório" durante internação: termo correto? |
| 20 taxas de sala em contas **sem** procedimento de pacote | Filtro | Pacote não se aplica. Taxa devida? |
| **11 casos de beneficiário com > 1 conta no mesmo dia** | Agrupamento | O escopo do pacote é "a conta". Fragmentação de conta pode escapar da regra (F2) |
| Descrição diverge do contrato (`500mg` vs `500 mg`, `—` vs `-`) | Comparação | Chave = código TUSS, nunca descrição |
| Decimal com vírgula, data por extenso em PT-BR, BOM UTF-8 | Leitura | Parsing explícito na silver |
| `vl_total = qtd × vl_unitario`: 0 inconsistências | Validação | Manter como expectation |
| Gabarito: 263 itens de 179 contas, **amostra enriquecida** em regras-alvo | Distribuição gabarito vs população | Avaliação precisa de reponderação (F8) |
| Planilha Parte 2: "Mes Sinistro = 2025-06-25" | Leitura | O valor é mensal ou de um dia? Agregado de 6 meses? (F2/F11) |

**Recomendações:**
- **Eng. Dados:** rascunho do **data contract** de entrada com schema, tipos, domínios, chaves (`id_item` único; `id_item` → `id_conta` N:1), cardinalidades, frequência e responsável na origem (TI da Parthenon).
- **DQ Steward:** classificar cada achado em uma das 6 dimensões do Databricks DQ (consistência, acurácia, validade, completude, tempestividade, unicidade).
- **Segurança:** classificar colunas. `id_beneficiario` é identificador de pessoa com dado de saúde, portanto sensível.

**G1:** relatório de perfilamento e data contract rascunho revisados pelo Eng. Dados e pelo Negócio.

---

## F2. Camada semântica (a fase mais importante)

**Líder: Especialista em Contas Médicas.** Participam Auditor Médico, Jurídico e Analytics Engineer.

> Por que é crítica: é a camada semântica que vai permitir que um agente, no futuro, descubra sozinho que "a cirurgia X tem um gap recorrente em relação ao contrato". Sem termos definidos, o agente aprende ruído. A documentação Databricks de qualidade de dados é explícita: dado confiável é pré-requisito para IA confiável. E as UC Metric Views existem justamente para "definir a métrica uma vez" e expô-la a dashboards, notebooks e **Genie Agents**.

### 2.1 Glossário de negócio (rascunho para o comitê decidir)

| Termo | Definição proposta | Fonte | Ambiguidade a resolver | Dono |
|---|---|---|---|---|
| **Caráter de atendimento** | Natureza clínica do atendimento: eletivo vs urgência/emergência | Guia TISS (campo informado pelo prestador) | O contrato diz "urgência ou emergência". O dado só tem "Urgência". Confirmar se o domínio da origem agrupa os dois (validar na terminologia TISS vigente) e mapear sinônimos | Especialista + Auditor |
| **Tipo de conta / regime** | Local ou regime: Internação, Ambulatorial, Pronto Socorro | Sistema da operadora | **Não é caráter.** PS + Eletivo existe (114 itens). Decidir se é erro de registro ou atendimento eletivo em PS | Especialista |
| **Taxa de urgência/emergência** | *Item* cobrável, código 99999001 | Anexo I, Cl. 4.1 | Diferente de caráter. Devida só se caráter = urgência/emergência | Jurídico |
| **Conta** | Agrupador de faturamento (`id_conta`) | Sistema | O escopo do pacote é "a conta em que o procedimento for realizado" (3.2). E se o prestador fragmentar contas? (11 casos beneficiário-dia) | Jurídico + Especialista |
| **Pacote cirúrgico** | Procedimento do Anexo II remunerado em regime fechado | Anexo II, Cl. 3.1 | Vale só em Internação? (Hoje 100% das cirurgias são em internação) | Jurídico |
| **Porte** | Porte da **taxa de sala** (2 ou 4) | Anexo II | Não confundir com porte anestésico ou porte CBHPM | Especialista |
| **Material de rotina** | Lista **fechada**: 70520020 e 70402600 | Cl. 3.2(b) | O termo genérico "material de rotina" não amplia a lista | Jurídico |
| **Valor pactuado** | **Teto** unitário (não preço fixo) | Anexo I | Cobrança abaixo do teto é válida | Jurídico |
| **Glosa** | Recusa de pagamento, integral ou parcial, com cláusula | Cl. 5.2 | Integral (3.3, 4.2) vs parcial/excedente (2.2) | Jurídico |
| **Glosa técnica vs administrativa** | Técnica envolve julgamento clínico. Administrativa é regra objetiva | Prática de mercado e planilha | As 3 regras do case são administrativas? A 4.2 em PS pode virar técnica | Auditor |
| **Economia identificada / enviada à operadora / enviada ao prestador / efetivada** | Estágios do funil | Planilha Arvo | **Definições não fornecidas.** Confirmar com a Arvo (F11) | PM/CS |
| **Recurso / reversão** | Contestação do prestador / glosa revertida | Cl. 5.2 | Prazo regulamentar e fonte do dado | Jurídico |

### 2.2 Ontologia (modelo de entidades)

```
Contrato ─1:N─ Cláusula ─1:N─ Regra ─1:N─ Parâmetro (valor, código, lista)
   │                              │
Prestador ─1:N─ Conta ─1:N─ Item ─N:1─ Código TUSS ─N:1─ Conceito de negócio
                  │                                         (PROCEDIMENTO_CIRURGICO_PACOTE,
             Beneficiário, Data,                             TAXA_SALA_CIRURGICA, MATERIAL_ROTINA,
             Caráter, Regime                                 TAXA_URGENCIA, DIARIA, SADT, MEDICAMENTO, ...)
Apontamento (glosa) ─ referencia ─ Item + Regra + Versão do contrato + Evidência
```

### 2.3 Registro de ambiguidades (decision log)
Cada linha registra: ID, pergunta, evidência no dado, opções, decisão, decisor, data e impacto em regra. Exemplos que já precisam de decisão:
- **AMB-01:** taxa de urgência em PS com caráter Eletivo. Glosa automática, glosa com revisão humana ou não glosa?
- **AMB-02:** pacote com contas fragmentadas no mesmo dia e beneficiário. A regra olha "conta" ou "episódio"?
- **AMB-03:** existe outra regra (não contratual) que explique os 15 "Sim" do gabarito sem base no contrato?
- **AMB-04:** taxa de sala sem procedimento de pacote (20 itens) fica fora da regra 3.3? (Proposta: sim, fora.)
- **AMB-05:** definição de cada estágio do funil de economia da Parte 2.

### 2.4 Materialização no Databricks (Analytics Engineer)
1. **Fonte da verdade versionada em Git:** `src/arvo/semantic/glossario.yaml`, `src/arvo/semantic/conceitos.yaml`, `src/arvo/semantic/map_tuss_conceito.yaml`, `src/arvo/semantic/metricas.yaml`.
2. **Tabelas no Unity Catalog** (schema `semantic`): `dim_conceito`, `map_tuss_conceito` (com vigência), `glossario`, `dim_carater` (mapeando valores de origem para valor canônico e sinônimos).
3. **Comentários e tags** em tabelas e colunas (UC), para que o significado viaje com o dado.
4. **UC Metric Views** para as métricas de negócio:
   - `valor_glosado`, `taxa_glosa_sobre_sinistro`, `taxa_recurso`, `taxa_reversao`
   - `conversao_funil_*`, `gap_cobrado_vs_pactuado_por_procedimento`
   - Com **agent metadata** (sinônimos, display names, formatos). Ex.: "emergência", "PS" e "pronto-atendimento" mapeados aos conceitos corretos, para o Genie e agentes não confundirem *local* com *caráter*.
5. **Testes semânticos automáticos** (rodam no CI e no pipeline):
   - 100% dos `cod_tuss` do sinistro mapeados a um conceito. Código novo vai para quarentena e alerta ao Especialista.
   - Toda regra referencia apenas conceitos aprovados.
   - Todo valor de `carater_atendimento` mapeado para o domínio canônico.
   - As perguntas de negócio da F0 respondidas por metric views (teste de aceite).

### 2.5 Por que isso habilita "treinar agentes"
A aderência à semântica produz **dados rotulados em vocabulário comum**: decisões do auditor, resultado de recurso e reversões, todos ligados a conceito e cláusula. Isso alimenta:
- **Datasets de avaliação** (MLflow evaluation datasets)
- Juízes calibrados
- No futuro, ajuste de prompts ou modelos
- Agentes analíticos (Genie sobre metric views) que respondem "qual cirurgia tem gap recorrente vs contrato?" sem alucinar termos

**G2:** glossário e ontologia assinados por Especialista, Auditor e Jurídico. AMB-01 a AMB-04 decididos. Testes semânticos escritos.

---

## F3. Contrato como dado

**Líder: Jurídico.** Execução: Eng. IA e Negócio.

**Objetivo:** transformar o PDF em `contracts.contract_params` versionado, com cada parâmetro ligado a uma **cláusula** e a uma **citação literal**.

**Pipeline (máquina de estados persistida em `ops.contract_extraction_state`):**
```
RECEBIDO → PARSEADO (texto + layout) → EXTRAIDO_A ─┐
                                      EXTRAIDO_B ─┼→ RECONCILIADO → JULGADO → REVISAO_HUMANA → APROVADO | REJEITADO
                     (parser determinístico) EXTRAIDO_D ─┘
```
- **Parse:** o PDF deste contrato é texto puro (0 imagens em 4 páginas). Use `ai_parse_document` (Databricks AI Functions) e um parser aberto (pdfplumber) como redundância. Se vier escaneado, a rota passa por OCR/visão com o mesmo fluxo de revisão.
- **Extração A e B:** dois provedores ou modelos **de famílias diferentes**, via Port (F7), com o mesmo schema. Extração D: parser determinístico por regex/tabela, como baseline e fallback.
- **Grounding obrigatório:** cada campo extraído traz `quote` (trecho literal) e `clausula`. O código verifica que `quote` é **substring exata** do texto parseado. Campo sem citação verificável é rejeitado.
  - Isso segue a orientação da Anthropic para reduzir alucinação: extrair citações literais, permitir "não sei" e remover afirmações sem suporte.
  - No Claude, *citations* e *structured outputs* são incompatíveis na mesma chamada. Um campo `quote` no schema, com verificação em código, resolve isso **para qualquer provedor**.
- **Reconciliação:** valor por valor entre A, B e D. A concorda com B e com D: auto-aceita. Divergência: vai para o juiz e para revisão humana.
- **Juiz (LLM-as-judge):** de **outra família** de provedor, com saída estruturada (`{campo, veredito: CONFIRMA|CONTESTA|INCONCLUSIVO, motivo, quote}`). O juiz **não aprova sozinho**: só prioriza a revisão humana.
- **Revisão humana:** o Jurídico aprova. A aprovação gera `versao_contrato` imutável.

**Testes de sanidade do contrato:**
- Todo pacote do Anexo II referencia taxa de sala existente no Anexo I.
- Preços extraídos > 0, com 2 casas decimais.
- Todos os códigos com 8 dígitos.
- Vigência coerente (01/01/2025 + 24 meses).
- Cobertura: % de códigos do sinistro presentes no Anexo I.

**G3:** 100% dos parâmetros com citação verificada e aprovação jurídica. Concordância A/B/D reportada.

---

## F4. Plataforma e ambientes

**Líder: Arquiteto.** Participam Eng. Dados, Segurança e MLOps.

### 4.1 Topologia de catálogos (Unity Catalog)
Seguindo a orientação Databricks (catálogo como unidade primária de isolamento, frequentemente por ambiente; um metastore por região; workspace binding quando ambiente e dado têm o mesmo requisito de isolamento):

| Catálogo | Schemas | Dados | Quem escreve |
|---|---|---|---|
| `arvo_dev` | `bronze`, `silver`, `gold`, `semantic`, `contracts`, `ops`, `quarantine`, `sandbox_<dev>` | **Sintéticos ou anonimizados** | Desenvolvedores (bundle em modo dev, recursos prefixados por usuário) |
| `arvo_stg` | os mesmos | Cópia mascarada de prod e **golden datasets congelados** | Somente service principal do CI |
| `arvo_prod` | os mesmos e `gold_shadow` | Reais | Somente service principal de produção (MODIFY reservado a service principals) |

- Isso atende o pedido de **silver dev, gold dev etc.**: `arvo_dev.silver`, `arvo_dev.gold`, `arvo_stg.silver`...
- **`gold_shadow`** fica em prod: o agente lê dado real e grava apontamentos **sem enviar ao cliente** (F10).
- `arvo_prod` com **workspace binding** ao workspace de produção. Ownership de produção para **grupos**. Jobs rodam como **service principal**. Tabelas **managed**.
- **LGPD:** column masks ou row filters em `id_beneficiario`. Nada de PHI em `arvo_dev`. Política de que **o sinistro não vai para LLM externo** (só o contrato vai).

### 4.2 Promoção e CI/CD
- **Declarative Automation Bundles** (antigo Databricks Asset Bundles), com `databricks.yml` e `targets: dev | stg | prod` (`mode: development` em dev, `production` em stg/prod, `run_as` service principal).
- Pipeline de CI:
  1. `bundle validate`
  2. Testes unitários (regras, parsing, semântica)
  3. Deploy em stg
  4. Testes de integração, expectations e **regressão no golden set**, comparando apontamentos com a versão anterior
  5. Aprovação manual (PM e Cientista)
  6. Deploy em prod
- **Código promove, dado não promove.** `contract_params` e semântica promovem como artefatos versionados aprovados.

**G4:** três ambientes provisionados, permissões testadas, CI verde num "hello pipeline".

---

## F5. Pipelines medalhão e qualidade de dados

**Líder: Eng. Dados.** Participam DQ Steward e Analytics Engineer.

### 5.1 Camadas (conforme orientação Databricks)
- **Bronze:** ingestão incremental append-only, fiel à origem. Campos como string, com metadados `_ingest_ts`, `_source_file`, `_batch_id`.
- **Silver:** tipagem (decimal PT-BR, data por extenso para `DATE`), deduplicação, enforcement de schema e **enriquecimento semântico** (join com `map_tuss_conceito` e `dim_carater`). Nunca escrita direto da ingestão.
- **Gold:**
  - `fato_item_auditado` (item, conceito, regra avaliada, resultado)
  - `apontamentos` (glosas com cláusula, evidência, valores, versões)
  - `resumo_glosa`
  - `fato_funil_economia` (Parte 2)
  - Base das metric views

### 5.2 Expectations pelas 6 dimensões (Lakeflow Declarative Pipelines)

| Dimensão | Expectation (exemplo) | Ação |
|---|---|---|
| Unicidade | `id_item` único | **fail** |
| Validade | `cod_tuss` com 8 dígitos; `qtd > 0`; `vl_unitario > 0` | drop para **quarentena** |
| Validade semântica | `cod_tuss` mapeado em `map_tuss_conceito`; `carater` no domínio canônico | quarentena e alerta ao Especialista |
| Consistência | `abs(vl_total − qtd × vl_unitario) ≤ 0,01`; caráter, regime e data únicos por conta | warn (vai para o indicador) |
| Completude | colunas obrigatórias não nulas; contas com ≥ 1 item | drop / warn |
| Acurácia | preço dentro de banda plausível (ex.: ≤ 5× o teto) | warn (outlier vai para revisão) |
| Tempestividade | lote do mês chega até D+N | alerta (anomaly detection de freshness) |

- **Padrão de quarentena:** em vez de descartar, isolar registros inválidos em `quarantine.*` com motivo. A métrica de cada expectation vai para o **event log** do pipeline.
- **Data quality monitoring** (antigo Lakehouse Monitoring):
  - **Anomaly detection** de freshness e completude no schema
  - **Data profiling** com drift (ex.: distribuição de `vl_unitario` por conceito vs baseline)
  - **Custom metrics** de negócio (ex.: % de itens acima do teto)

**G5:** expectations implementadas e testadas com dados sujos sintéticos. Monitores ativos em stg.

---

## F6. Motor de regras (determinístico)

**Líder: Eng. Dados.** Participam Negócio e Jurídico.

- **Regras como dados**, referenciando conceitos:

| Regra | Cláusula | Condição (semântica) | Valor |
|---|---|---|---|
| R1 | 2.2 | Item com preço pactuado e `vl_unitario > teto` | `(vl_unit − teto) × qtd` |
| R2 | 3.2(a)/3.3 | Conta contém `PROCEDIMENTO_CIRURGICO_PACOTE` e item é `TAXA_SALA` **do porte do pacote** | integral |
| R3 | 3.2(b)/3.3 | Conta contém pacote e item é `MATERIAL_ROTINA` | integral |
| R4 | 4.1/4.2 | Item é `TAXA_URGENCIA` e caráter canônico = `ELETIVO` | integral. Em regime PS, segue a decisão de AMB-01 |

- **Resolução de conflito:** uma glosa por item, com `vl_glosado ≤ vl_total`. A cláusula **principal** é a integral de texto mais literal. As demais são **subsidiárias**, registradas na justificativa como defesa em camadas.
- **Saída por apontamento:**
  - `id_item`, `id_conta`, `regra_id`, `clausula_principal`, `clausulas_subsidiarias`
  - `vl_cobrado`, `vl_referencia`, `vl_glosado`, `justificativa` (template determinístico)
  - `evidencia` (itens da conta que dispararam a regra)
  - `versao_regra`, `versao_contrato`, `versao_semantica`, `run_id`
- **Testes:** um por regra e um por caso de borda da F1. Exemplos: taxa de sala sem pacote não glosa; fio sem pacote não glosa; PS + Eletivo segue AMB-01; conta sem itens.
- **Reprodutibilidade:** mesma entrada e mesmas versões dão **o mesmo hash de saída**. Isso entra como teste de regressão no CI.

**G6:** testes 100% verdes e revisão do Jurídico sobre o texto das justificativas.

---

## F7. Camada de IA independente de provedor

**Líder: Eng. IA Sênior.**

### 7.1 Onde a IA entra (e onde não entra)

| Tarefa | Usa LLM? | Tier de modelo | Criticidade | Salvaguarda |
|---|---|---|---|---|
| Decidir glosa | **Não** | — | — | Motor determinístico |
| Extrair parâmetros do contrato | Sim | Frontier, 2 famílias | Alta, rara | Quote verificado, consenso, juiz e humano |
| Sugerir mapeamento descrição/código → conceito (códigos novos) | Sim | Pequeno/médio | Média | Sempre revisão do Especialista |
| Redigir justificativa | Opcional | Pequeno | Média | Default = template. LLM só reescreve, mantendo números verificados |
| Juiz (avaliação) | Sim | Família diferente da geradora | Alta | Calibrado contra rótulos humanos |
| Futuro: rascunho de resposta a recurso, agente analítico (Genie) | Sim | Variável | Média | HITL |

### 7.2 Ports & Adapters (o core nunca importa SDK de provedor)
```
core (regras, contrato, semântica)
   │  depende só de interfaces
   ▼
LLMPort.generate_structured(task_id, messages, schema_id, params) -> LLMResult
JudgePort.evaluate(task_id, candidate, evidence, rubric_id) -> JudgeResult
DocumentParserPort.parse(file) -> ParsedDoc
   ▲  injetados por configuração (registry por task_id)
adapters/
   databricks_gateway.py   # endpoint OpenAI-compatível do AI Gateway (OpenAI, Anthropic, Vertex/Gemini, Bedrock, custom, modelos databricks-*)
   anthropic_direct.py     # Messages API, output_config.format
   openai_direct.py        # Responses API, text.format json_schema strict
   gemini_direct.py        # structured output com schema
   open_weights.py         # modelo aberto (ex.: databricks-gpt-oss-* ou vLLM próprio)
   deterministic.py        # parser/regex: fallback sem LLM
```
- **Duas camadas de independência:**
  1. **AI Gateway**: traffic splitting, fallbacks, rate limits, budgets, payload logging em inference tables e usage tracking em system tables.
  2. **Adapters próprios**: se o Gateway ou um provedor cair, o roteador troca de adapter sem tocar no core.
- **Router por `task_id`:** tier primário, fallback ordenado e critério de falha (erro, timeout, schema inválido, recusa, truncamento).

### 7.3 Matriz de capacidades por provedor (da documentação oficial; revalidar a cada release)

| Capacidade | OpenAI | Anthropic | Gemini | Databricks (model serving) |
|---|---|---|---|---|
| Structured output | `text.format` `json_schema`, `strict` | `output_config.format` `json_schema` (o antigo `output_format` está depreciado) | `response_format` com `mime_type: application/json` e schema | `response_format` `json_schema` `strict`. Nos Claude 5.5 via Databricks, usar `output_config` na Messages API |
| Restrições de schema | todos os campos `required`; `additionalProperties: false`; sem `allOf`/`not`/`if` | sem `minimum`/`maximum`/`minLength`; `additionalProperties: false` | `minLength`, `maxLength` etc. são **removidos silenciosamente** | sem `pattern`/`anyOf`/`oneOf`/`$ref`; ≤ 64 chaves |
| Sinal de saída inválida | `status: incomplete` (`max_output_tokens`, `content_filter`); parte `refusal` | `stop_reason`: `max_tokens`, `refusal` | verificar finish reason | `finish_reason` (ex.: `content_filter`) |
| Tokens reportados | input, cached, output, reasoning | input, output e campos de cache | `total_cached_tokens` | `usage` (prompt, total) e system tables |
| Caching | automático (prefixo estável, dinâmico no fim) | `cache_control` em blocos; mudar o schema invalida o cache | implícito (mínimo por modelo) | — |
| Batch | Batch API (24h, 50% de desconto, junção por `custom_id`) | Message Batches | — | `ai_query` em batch (dataset inteiro em uma query) |

**Decisão do Eng. IA:** usar um **schema mínimo comum**: plano, todos os campos `required`, nullables explícitos, `additionalProperties: false`, sem `pattern`, `min`, `max` ou `oneOf`. **Todas as restrições finas são validadas em código** (Pydantic/JSON Schema completo), porque cada provedor ignora ou rejeita partes diferentes. Lição dos próprios docs da OpenAI: *aderência ao schema não é acurácia*.

### 7.4 Determinismo, cache, orçamento, assíncrono e idempotência
- **Determinismo:** nenhum provedor garante saída idêntica. Temperatura baixa ajuda, mas modelos de raciocínio podem **não aceitar** `temperature`/`top_p` (o controle passa a ser `reasoning.effort`). Por isso o determinismo do *sistema* vem de: schema estrito, consenso entre extrações, cache por hash, aprovação humana e motor determinístico. Registrar sempre o **parâmetro pedido vs aplicado**.
- **Cache de respostas:** tabela Delta `ops.llm_cache`, com chave `sha256(provider, model, model_version, prompt_id@versao, params, schema_id@versao, input_hash)`. Em batch não precisa de Redis. Se houver uso online no futuro, usar um KV rápido.
- **Prompt caching do provedor:** prefixo estável (instruções e contrato) primeiro, variáveis no fim.
- **Orçamento de tokens:** budgets e rate limits no AI Gateway, mais um **orçamento por run** em código (estimativa prévia de tokens; aborta se exceder) e circuit breaker para loops.
- **Assíncrono:** tudo roda em **Jobs** (batch). Nada síncrono no caminho do sinistro.
- **Idempotência:** chave = hash da entrada e da versão. Retry não duplica chamada nem apontamento.
- **Versionamento de prompt:** **MLflow Prompt Registry** no UC (versões imutáveis, aliases `staging`/`production`; está em Beta, então fixar versão).
- **Rastreamento:** **MLflow 3 Tracing** (spans, tokens, latência, custo) e inference tables do Gateway.

### 7.5 Critério de aceite "independente de provedor"
- **Golden set de contratos:** este contrato, mais variantes sintéticas (preços alterados, cláusula renumerada, tabela quebrada em 2 páginas, versão escaneada).
- **Cada provedor habilitado** precisa atingir, no golden set:
  - acurácia **campo a campo** ≥ 99%
  - 100% de quotes verificáveis
  - 0 campos inventados
- **Produção exige ≥ 2 provedores aprovados**, além do caminho determinístico.
- **Teste de caos:** desligar o provedor primário em stg. O pipeline precisa concluir via fallback, com o **mesmo `contract_params`** e, portanto, os mesmos apontamentos.

**G7:** golden set aprovado em ≥ 2 provedores, teste de caos passando e telemetria (9.4) completa em 100% das chamadas.

---

## F8. Avaliação científica

**Líder: Cientista de Dados.** Participam Auditor e Negócio.

**Diagnóstico do protótipo da v1 (hipótese):**
- Contagem: TP 135, FP 8, FN 15, TN 105.
- **Precisão 94,4%, IC 95% [89,3% – 97,1%]**.
- **Recall 90,0%, IC 95% [84,2% – 93,8%]** (Wilson).
- Precisão **ponderada por R$**: 92,8% (R$ 45,6 mil corretos vs R$ 3,5 mil em FP). FN somam R$ 15,8 mil cobrados.
- **O gabarito é enriquecido.** As métricas valem para a amostra, não para a população:

| Código | % no gabarito | % na população |
|---|---|---|
| Taxa de urgência | 11,4% | 6,5% |
| Fio de sutura | 6,1% | 2,6% |
| Taxa de sala porte 4 | 6,1% | 1,9% |

**Recomendações:**
1. **Adjudicação das 23 divergências:** dupla revisão **cega** (Auditor e Especialista), com concordância medida por Cohen's κ. Classificar cada caso: erro do gabarito, regra faltante (vira AMB), problema de dado ou erro do agente. **O gabarito é dado rotulado de qualidade desconhecida, não verdade absoluta.**
2. **Métricas por regra e ponderadas por R$**, com IC.
3. **Estimativa populacional:** reponderar por estrato (código/regra) ou desenhar nova amostra **estratificada aleatória** que inclua itens não disparados. É o único jeito honesto de estimar recall.
4. **Matriz de custo de negócio:**
   - Custo de FP = custo do recurso + atrito + probabilidade de reversão × valor + erosão de confiança (retenção pelo Dr. Ary).
   - Custo de FN = valor não recuperado.
   - Resultado: priorizar **precisão no go-live**, com limiar por regra.
5. **Tamanho amostral do shadow:** para estimar precisão ~98% com ±2 p.p. (95%), são necessários ~**190 apontamentos auditados por regra** (n ≈ z²·p(1−p)/e²).
6. Registrar tudo em **MLflow** (experimento de avaliação, dataset versionado, métricas).

**G8:** métricas com IC por regra, divergências adjudicadas e matriz de custo aprovada pelo Negócio.

---

## F9. Indicadores de sanidade (negócio primeiro)

**Líderes:** Analytics Eng (negócio e semântica), DQ Steward (dados) e Eng. IA (IA). Cada indicador tem: definição (metric view), dono, banda esperada, alerta e ação no runbook.

### 9.1 Negócio (os principais)

| Família | Indicador | Definição | Por que importa | Alerta (exemplo) |
|---|---|---|---|---|
| **Valor** | Economia efetivada run-rate vs meta | efetivado/mês ÷ R$ 1,4 mi | É a meta do Paulo | < 80% da trajetória planejada |
| | Taxa de glosa sobre sinistro | valor glosado ÷ valor apresentado, por prestador e por regra | Saúde e plausibilidade | Fora de ±3σ histórico |
| | Gap cobrado vs pactuado por procedimento | Σ(cobrado − teto) por conceito | Responde a pergunta 5 da F0 | Top-N novo surge |
| **Qualidade da decisão** | Precisão auditada | amostra auditada contínua, por regra | Confiança do Dr. Ary | < 98% em regra automática: rebaixa para HITL |
| | **Taxa de recurso** | apontamentos recorridos ÷ enviados | Atrito e defensabilidade | > benchmark da regra |
| | **Taxa de reversão** | recursos procedentes ÷ recorridos | **Precisão real em campo** | > 5% |
| | FN amostral | auditoria de amostra aleatória de itens **não** glosados | Único estimador de recall em produção | Tendência de alta |
| **Funil** | Conversão identificada → enviada → registrada → efetivada | por inteligência e regra | Onde a economia vaza (Parte 2) | Queda em qualquer etapa |
| | Taxa de retenção, com **motivo** | retido ÷ identificado, motivo codificado | Ataca o gargalo da auditoria | Motivo "sem confiança" crescendo |
| | Perda de registro | enviado − registrado | Falha de integração (Alana) | > 5% |
| **Relação com prestador** | % contas glosadas, glosa média por conta, concentração top-10 | — | Evita atrito desproporcional | Concentração anômala |
| **Comportamento** | Hit rate por regra × prestador (tendência) | apontamentos ÷ itens elegíveis | Queda pode ser **sucesso** (o hospital parou de cobrar) ou **bug**. Distinguir pelos indicadores de dados | Queda brusca sem mudança de dado |
| **Cobertura** | % itens com preço pactuado; % contas com pacote; % itens fora do Anexo I (Cl. 2.3) | — | Quanto do sinistro é auditável | Cobertura caindo |
| **Invariantes** (devem ser sempre 0) | glosa > cobrado; item com 2 glosas; glosa sem cláusula ou evidência; Σ glosa da conta > total da conta | — | Violação gera erro jurídico | ≠ 0 bloqueia o envio |

### 9.2 Aderência semântica
- % de códigos TUSS e valores de enum mapeados (meta 100%). Termos novos por semana.
- Taxa de conflitos semânticos (ex.: PS + Eletivo) e tendência.
- % regras e métricas referenciando conceitos aprovados. Versão do glossário em uso por run.
- Perguntas de negócio da F0 respondidas corretamente por metric views e Genie (benchmark de perguntas, re-executado a cada release).

### 9.3 Engenharia de dados
- Pass rate por expectation e por dimensão. Volume em quarentena e motivo.
- Freshness e completude (anomaly detection). Volume vs previsto. Schema drift.
- Drift de distribuição (data profiling) de preço e quantidade por conceito.
- SLA do pipeline, falhas e retries. Custo (DBU, via `system.billing.usage`). Lineage íntegra.

### 9.4 IA: telemetria obrigatória por chamada (`ops.llm_calls`)

| Grupo | Campos |
|---|---|
| Identidade | `call_id`, `run_id`, `task_id`, `idempotency_key`, `timestamp`, `ambiente` |
| Modelo | `provider`, `adapter`, `endpoint`, `model`, `model_version/snapshot`, `fallback_from`, `tier` |
| Prompt | `prompt_id`, `prompt_version`, `prompt_hash`, `system_hash`, `schema_id`, `schema_version` |
| Parâmetros | `temperature`, `top_p`, `max_tokens`, `seed`, `reasoning_effort`/`thinking_budget`, `stop`, com **pedido vs aceito/aplicado** (ex.: temperatura ignorada em modelo de raciocínio) |
| Consumo | `input_tokens`, `output_tokens`, `cached_tokens`, `reasoning_tokens`, `custo_estimado`, `cache_hit` (cache próprio) |
| Latência | `latency_ms` total, TTFT (se streaming), tempo em fila |
| Resultado | `finish/stop_reason` (`max_tokens`/`incomplete`, `refusal`, `content_filter`), `schema_valid`, `retries`, `erro` |
| Qualidade | `quotes_verificados_pct`, `concordancia_entre_provedores`, `judge_score`, `acuracia_campo_golden` (em avaliação) |
| Linhagem | `versao_contrato`, `versao_semantica`, hash do documento de entrada |

**Indicadores agregados de IA:**
- Taxa de schema válido, de recusa e de truncamento
- % de quotes verificados, concordância A×B, score do juiz e acurácia no golden
- Tokens e custo por contrato processado, cache hit rate
- Latência p50/p95
- Taxa de fallback por provedor (degradação de um provedor dispara troca automática), retries
- **Drift de modelo:** mudou o snapshot? Rodar o golden set automaticamente.

**Por que registrar tudo:** auditoria (por que este parâmetro de contrato saiu assim?) e **mapa de evolução** (qual modelo, prompt ou parâmetro melhorou a acurácia e o custo ao longo do tempo, ligado aos indicadores de negócio).

**G9:** painel (AI/BI dashboard sobre metric views) e alertas SQL com dono e runbook para cada indicador crítico.

---

## F10. Rollout

**Líderes: PM e Cientista.**

1. **Backtest:** histórico de 3 a 6 meses vs decisões reais da auditoria.
2. **Regressão em stg:** golden set congelado. Diferença de apontamentos vs a versão anterior precisa ser explicada.
3. **Shadow em prod** (`arvo_prod.gold_shadow`, 4 a 8 semanas): nada é enviado. Auditoria amostral estratificada (todos os itens de alto valor e ~190 por regra).
4. **Canário por regra:** liga R1 e R3 primeiro (mais objetivas). R2 depois. R4 em regime PS só com HITL, conforme AMB-01.
5. **Automático com guarda-corpos:** HITL acima de R$ X ou em casos de conflito semântico. **Kill switch por regra.** Invariantes ≠ 0 bloqueiam o envio.

**Critérios de go-live por regra:**
- Precisão auditada ≥ 98% com limite inferior do IC ≥ 95%
- 0 violações de invariantes
- Reversão projetada ≤ 5%
- Aderência semântica = 100%
- Telemetria completa
- Integração ponta a ponta testada (o apontamento chega registrado no sistema da Parthenon)

---

## F11. Parte 2: funil de economia e otimização com o cliente

**Líderes: PM/CS e Analista.** Antes de analisar, **resolver o AMB-05** (definição de cada estágio) e confirmar a granularidade ("Mes Sinistro = 2025-06-25": é o mês ou um dia?).

**Leitura da planilha (válida se as definições forem as presumidas):**

| Etapa | R$/mês | % do identificado |
|---|---|---|
| Identificado | 1.936.700 (2,77% do sinistro) | 100% |
| (−) Inteligências desligadas | −966.000 | −49,9% |
| (−) Retidas pela operadora | −433.720 | −22,4% |
| (−) Perda de registro | −163.065 | −8,4% |
| (−) Perda em recurso | −38.145 | −2,0% |
| **Efetivado** | **335.770 (0,48%)** | 17,3% |

**Diagnóstico:**
- **Detectar não é o gargalo:** a Arvo já identifica 2,77%, acima da meta de 2%. O problema é converter.
- **Efetivação sobre o que chega ao prestador:** 89,8%, alinhada à média Arvo.
- **Perda de registro uniforme (62–75%) em todas as inteligências:** causa sistêmica de integração ou processo.
- **Retenção técnica:** técnicas são enviadas em 45%, administrativas em 83%. As maiores retenções são Pertinência de Materiais (R$ 187,5 mil) e Sobreposição de procedimentos cirúrgicos (R$ 91 mil).
- **Desligadas com bom benchmark:** Sobreposição de SADT (R$ 175 mil, 72%), Qtd excessiva de taxas (R$ 98 mil, 96%), SADT ambulatorial (R$ 77 mil, 88%).
- **Desligadas com benchmark ruim:** Alto Markup (R$ 350 mil, efetivação média de apenas 12%). Reformular ancorando no Anexo I (regra 2.2), em vez de ligar como está.

**Ponte de valor (cenários):**

| Cenário | Efetivado/mês |
|---|---|
| Hoje | R$ 336 mil |
| Registro corrigido para 95% | ~R$ 458 mil |
| Envio das ligadas em 90% | ~R$ 755 mil |
| Ligar as desligadas com benchmark ≥ 50% | ~R$ 1,17 mi |
| Alto Markup reformulado | ~R$ 1,32 mi (1,9%) |
| Melhoria contínua | ≥ R$ 1,4 mi |

**Proposta:**
1. **Força-tarefa de registro:** reconciliação ponta a ponta com TI da Parthenon.
2. **Programa de confiança técnica com o Dr. Ary:** evidência por inteligência, shadow, limiares definidos pelo time dele e motivo de retenção codificado.
3. **Ondas de ativação:** administrativas de alto benchmark primeiro, cada onda com shadow.
4. **Reformulação contratual das inteligências fracas.**
5. **Ciclo de melhoria contínua:** a camada semântica permite ver *recorrência por conceito × cláusula × prestador*. O que recorre vira regra, renegociação ou argumento para a praça.

**Requisitos (Arvo / Parthenon / ambos):**

| Requisito | Responsável |
|---|---|
| Logs e homologação de integração | TI Parthenon |
| Tempo do time de auditoria para o piloto | Dr. Ary |
| Patrocínio executivo e meta oficial | Paulo |
| Definições do funil e taxonomia de motivos | Ambos |
| Evidência, dashboards e engenharia | Arvo |

**Detalhe a corrigir no discurso:** o contrato é **Curitiba/PR**, não SC.

**Mini-deck (10 slides):**
1. Tese
2. Funil (waterfall)
3. As 3 perdas
4. Matriz valor × benchmark
5. Ponte até 2%
6. Registro (Alana)
7. Confiança técnica (Dr. Ary)
8. Ondas e reformulação
9. Requisitos / RACI
10. Plano 90 dias e KPIs (os de 9.1)

---

## F12. Entrega e apresentação

**Artefatos finais:**
1. **Repositório:** bundle, `src/arvo/semantic/`, `contracts/`, `src/` (core + ports + adapters), `tests/`, `docs/adr/`, README com "um comando roda tudo" (local com adapter determinístico, e Databricks com `bundle deploy -t dev && bundle run`).
2. **Glossário, ontologia e decision log** (F2). Mostrar isso é o que diferencia de "mais um script".
3. `apontamentos.csv`, valor total glosado, métricas com IC e tabela de divergências adjudicadas.
4. Respostas às 8 perguntas do case, cada uma apontando para a fase correspondente (1→F3/F6, 2→F6/F7, 3→F8, 4→F6, 5→F2/F6/defensabilidade, 6→F2/F3, 7→F4/F10, 8→F9).
5. Memo/deck da Parte 2.
6. Dashboard de sanidade (negócio na primeira aba).

**Ensaio:** pitch de 1, 5 e 15 minutos. Perguntas difíceis:
- "Por que não deixar o LLM decidir?"
- "E se o OpenAI ou o Anthropic cair amanhã?"
- "Por que confiar no gabarito?"
- "Como escala para 50 hospitais?" (Resposta: contrato vira parâmetro e semântica vira ativo reusável.)
- "Quanto custa por contrato?"

---

## 13. Defensabilidade em recurso (resposta da pergunta 5, revisada pelo Jurídico e pelo Auditor)

| Regra | Posição | Fundamento |
|---|---|---|
| 2.2 Preço acima do teto | **Mais defensável** | Número vs tabela assinada; glosa só do excedente; zero espaço clínico. Ataque possível: reajuste/aditivo (checar vigência em F3) |
| 3.3 Material de rotina | Muito forte | Lista fechada de códigos e "integralmente glosada" explícito |
| 3.3 Taxa de sala | Forte, com ressalva | Depende de "porte correspondente" e do escopo "conta" (AMB-02) |
| 4.2 Urgência em eletivo | **Mais frágil no subconjunto PS** | Depende do caráter informado. Em PS, o hospital alega urgência clínica e leva a discussão ao campo médico (AMB-01) |

**Item com várias regras:** a principal é a integral de texto mais literal, e as subsidiárias ficam registradas. A justificativa sempre traz cláusula, valor pactuado, valor cobrado, cálculo e evidência na conta.

---

## 14. Referências consultadas (06/11/2026)

**Databricks**
- Data quality management (6 dimensões): https://www.databricks.com/discover/pages/data-quality-management
- Expectations (warn/drop/fail, quarentena, event log): https://docs.databricks.com/aws/en/ldp/expectations
- Medalhão: https://docs.databricks.com/aws/en/lakehouse/medallion
- Unity Catalog best practices (catálogo por ambiente, binding, service principals): https://docs.databricks.com/aws/en/data-governance/unity-catalog/best-practices
- Metric views / UC semantics: https://docs.databricks.com/aws/en/metric-views/
- Data quality monitoring (anomaly detection, data profiling): https://docs.databricks.com/aws/en/data-quality-monitoring/
- Declarative Automation Bundles (targets/modes): https://docs.databricks.com/aws/en/dev-tools/bundles/ e https://docs.databricks.com/aws/en/dev-tools/bundles/settings
- AI Gateway (usage, inference tables, rate limits, budgets, fallbacks, guardrails): https://docs.databricks.com/aws/en/ai-gateway/
- External models: https://docs.databricks.com/aws/en/generative-ai/external-models/
- Structured outputs no Databricks: https://docs.databricks.com/aws/en/machine-learning/model-serving/structured-outputs
- MLflow 3 Tracing: https://docs.databricks.com/aws/en/mlflow3/genai/tracing/
- Avaliação e monitoramento GenAI: https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/
- AI Functions (`ai_query`, `ai_parse_document`, `ai_extract`): https://docs.databricks.com/aws/en/large-language-models/ai-functions
- Prompt Registry (Beta): https://docs.databricks.com/aws/en/mlflow3/genai/prompt-version-mgmt/prompt-registry/

**Provedores de IA**
- OpenAI: structured outputs, reasoning, prompt caching e batch em https://developers.openai.com/api/docs/guides/
- Google Gemini: structured output e caching em https://ai.google.dev/gemini-api/docs/structured-output e https://ai.google.dev/gemini-api/docs/caching
- Anthropic: structured outputs, citations e redução de alucinação em https://platform.claude.com/docs/en/build-with-claude/structured-outputs, https://platform.claude.com/docs/en/build-with-claude/citations e https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations

**Lacunas a verificar antes de implementar:**
- Schema exato das inference tables e das system tables do AI Gateway (se registram parâmetros por requisição)
- Detalhes da configuração de fallback do Gateway
- Suporte a `temperature`/`seed` por modelo em cada provedor (os docs consultados não garantem determinismo)
- Chaves YAML das metric views

---

## 15. Cronograma sugerido (5 a 6 dias de case)

| Dia | Fases | Saída |
|---|---|---|
| 1 | F0, F1 | Problem statement, perguntas de negócio, perfilamento e data contract |
| 2 | **F2** (com F3 começando) | Glossário, ontologia, decision log, metric views rascunho e contrato extraído com quotes |
| 3 | F4, F5, F6 | Ambientes, pipelines com expectations e motor de regras com testes |
| 4 | F7, F8 | Port/adapters com ≥ 2 provedores e o determinístico, golden set, avaliação com IC e adjudicação |
| 5 | F9, F11 | Painel de sanidade (negócio primeiro), memo e deck da Parte 2 |
| 6 | F10 (desenho), F12 | Plano de rollout, README, ensaio |

> Num case com prazo curto, F4 e F10 podem ser **desenho e documentação** (ADRs, bundle de exemplo), com execução real em `arvo_dev` na Databricks Free Edition. Deixe isso explícito na apresentação: "isto está implementado, isto está especificado".
