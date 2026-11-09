# Registro de ambiguidades e decisões (decision log)

> Toda ambiguidade semântica vira uma entrada aqui **antes** de virar regra.
> A "Recomendação do comitê" é uma **proposta**. Só vale depois que o decisor assina e o status passa a `DECIDIDA`.
> Evidências calculadas sobre `sinistro-hospital-saorafael.csv` (1.696 itens, 320 contas, R$ 1.194.396,92) e `gabarito-auditoria.csv` (263 itens).

| ID | Tema | Bloqueia | Decisor | Status |
|---|---|---|---|---|
| AMB-01 | Taxa de urgência em PS ou ambulatório com caráter Eletivo | Regra R4 | Auditor + Jurídico | ABERTA |
| AMB-02 | Escopo do pacote: conta x atendimento (fragmentação) | Regras R2, R3 | Jurídico + Especialista | ABERTA |
| AMB-03 | 15 itens "Sim" no gabarito sem base contratual | Avaliação (F8) | Auditor | ABERTA |
| AMB-04 | Taxa de sala e material de rotina em conta sem pacote | Regras R2, R3 | Jurídico | ABERTA |
| AMB-05 | Definição dos estágios do funil de economia | Parte 2, M14–M19 | PM/CS + Arvo | ABERTA |
| AMB-06 | Granularidade e escopo dos valores (mês, sinistro total x amostra) | M19, Parte 2 | PM/CS | RESOLVIDA (07/11/2026) |
| AMB-07 | Domínio do caráter: "urgência ou emergência" x valor "Urgência" | Domínio canônico | Especialista | ABERTA |
| AMB-08 | Procedimento cirúrgico repetido no mesmo dia em contas distintas | Fora do escopo das 3 regras | Auditor | ABERTA |
| AMB-09 | Diária classificada como "Taxa" na origem | Conceito DIARIA | Especialista | ABERTA |
| AMB-10 | "Consulta em consultório" dentro de conta de internação | Fora do escopo | Auditor | ABERTA |
| AMB-11 | Taxa de sala de porte diferente do pacote na mesma conta | Regra R2 | Jurídico | ABERTA |
| AMB-12 | Pacote fora do regime de internação | Regras R2, R3 | Jurídico | ABERTA |
| AMB-13 | Vigência, reajuste e aditivos do Anexo I | Regra R1 | Jurídico | ABERTA |
| AMB-14 | Hierarquia de fundamento quando o item infringe várias regras | Motor (F6) | Jurídico | ABERTA |
| AMB-15 | Denominador do indicador-norte (sinistro total x auditável) | M20, M19, M21 | PM/CS + Paulo | ABERTA |
| AMB-16 | Linha de base da economia preventiva | M29, fato_excedente_mensal | Cientista + PM/CS | ABERTA |
| AMB-17 | Mapeamento regra ↔ inteligência Arvo | ponte_regra_inteligencia | Arvo + PM/CS | ABERTA |
| AMB-18 | Fonte dos eventos do funil (envio, registro, recurso) | fato_glosa_ciclo, M12, M13, M31–M35 | Parthenon (TI + Alana) | ABERTA |
| AMB-19 | Taxonomia de motivos (RET/REG/REC) | dim_motivo, M33, M35 | Auditor + Contas + Jurídico | ABERTA |
| AMB-20 | Premissas da matriz de custo (FP, revisão, piso de precisão) | Modo de envio por regra (F8/F10) | PM/CS + Jurídico + Auditor | ABERTA |
| AMB-21 | Bandas e limites do painel de sanidade marcados como premissa | Alertas da F9 (S02, S07, S08, S13, S15, S23, S27, S28) | Donos de cada indicador | ABERTA |

---

## AMB-01: Taxa de urgência em atendimento Eletivo fora da internação
- **Pergunta:** a taxa 99999001 cobrada em conta de **Pronto Socorro** (ou Ambulatorial) com caráter **Eletivo** deve ser glosada automaticamente?
- **Evidência:**

  | Caráter × regime | Itens | Valor | Gabarito |
  |---|---|---|---|
  | Eletivo × Internação | 50 | R$ 17.279,48 | 20 Sim / 0 Não |
  | Eletivo × Ambulatorial | 18 | R$ 6.221,89 | 5 Sim / 0 Não |
  | **Eletivo × Pronto Socorro** | **9** | **R$ 3.087,98** | 4 Sim / 0 Não |
  | Urgência × Pronto Socorro | 4 | R$ 1.379,90 | 0 Sim / 1 Não |

  O sinistro tem 114 itens em PS com caráter Eletivo (32 contas).
- **Opções:**
  - (A) Glosa automática pela letra da 4.1 ("caráter **registrado**")
  - (B) Glosa com revisão humana quando o regime é PS
  - (C) Não glosar em PS
- **Leitura jurídica:** o texto ampara (A). O gabarito também glosou os 4 casos de PS Eletivo rotulados.
- **Risco:** em recurso, o hospital alega erro de registro e urgência clínica. A disputa sai do campo administrativo e vai para o técnico.
- **Recomendação do comitê:** (A) para Internação e Ambulatorial. **(B) para PS** até o shadow mostrar a taxa de reversão. Registrar o PS Eletivo como **conflito semântico** (métrica M09), porque é um problema de qualidade de dado na origem.
- **Decisor:** Auditor Médico + Jurídico · **Status:** ABERTA

## AMB-02: Escopo do pacote (conta x atendimento)
- **Pergunta:** o pacote vale só para a conta onde está o procedimento (letra da 3.2) ou para o **atendimento** (mesmo beneficiário e mesmo dia)?
- **Evidência:**
  - 11 pares beneficiário-dia têm mais de uma conta.
  - Em 2 deles há **material de rotina cobrado numa conta paralela sem pacote**, no mesmo dia de uma conta com pacote:
    - B00152, 02/06: G00170 (artroscopia) + G00273, com compressa IT01519, R$ 9,00
    - B00212, 11/06: G00102 (artroscopia) + G00310, com compressa IT01659, R$ 26,76 (o gabarito marca **Não**)
- **Opções:**
  - (A) Escopo = conta (literal). Não glosa.
  - (B) Escopo = atendimento. Glosa.
  - (C) (A) para glosa automática e (B) como **alerta de fragmentação** para revisão.
- **Recomendação do comitê:** **(C).** Glosar por "atendimento" vai além do texto e é frágil em recurso. Mas a fragmentação é um padrão a monitorar e a levar à renegociação (definir "conta" ou "internação" no aditivo).
- **Decisor:** Jurídico + Especialista · **Status:** ABERTA

## AMB-03: Itens "Sim" no gabarito sem base contratual
- **Pergunta:** existe regra **fora do contrato** (norma interna, TISS, auditoria clínica) que explique os 15 itens rotulados "Sim" sem cláusula correspondente?
- **Evidência:**
  - Os 15 têm preço **abaixo** do teto.
  - Não são itens inclusos em pacote nem taxa de urgência.
  - Exemplos: IT00143, uma de 3 diárias da mesma conta, só ela "Sim"; IT01167, dipirona a R$ 3,90 contra teto de R$ 4,00; IT00492, o próprio procedimento de pacote.
  - Também há 8 itens "Não" que contrariam a letra do contrato. Exemplo: IT00228, artroscopia a R$ 5.134,22 contra R$ 3.800.
- **Opções:**
  - (A) Erro de rotulagem: corrigir o gabarito.
  - (B) Regra não escrita: formalizar como nova regra, com fonte.
  - (C) Inconclusivo: excluir da métrica.
- **Recomendação do comitê:** adjudicação **cega** por 2 revisores (Auditor + Especialista), medindo concordância (κ). Nenhuma glosa sem cláusula escrita.
- **Decisor:** Auditor Médico · **Status:** ABERTA

## AMB-04: Taxa de sala e material de rotina em conta sem pacote
- **Pergunta:** a regra 3.3 se aplica quando a conta **não** tem procedimento do Anexo II?
- **Evidência:**
  - 20 taxas de sala sem pacote (8 Ambulatorial, 7 PS, 5 Internação), somando R$ 21.957,14.
  - 31 materiais de rotina sem pacote, somando R$ 1.251,74.
  - O gabarito marca "Não" nos 4 casos rotulados.
- **Recomendação do comitê:** **fora da regra 3.3**, porque a vedação é condicionada ao pacote. A pertinência da taxa de sala sem cirurgia é tema de outra inteligência ("Pertinência de taxas", "Conformidade taxas de sala").
- **Decisor:** Jurídico · **Status:** ABERTA

## AMB-05: Definição dos estágios do funil de economia
- **Pergunta:** o que significam exatamente "Economia Identificada", "Enviada à Operadora", "Enviada para Prestador" e "Efetivado"? Quem executa cada passagem e qual sistema registra?
- **Evidência:** a planilha não traz dicionário. A perda de registro uniforme (62–75% de passagem em todas as inteligências) sugere uma causa sistêmica, mas a leitura depende da definição.
- **Recomendação do comitê:** confirmar com a Arvo antes do memo. Definições presumidas em T37–T42.
- **Decisor:** PM/CS + Arvo · **Status:** ABERTA

## AMB-06: Granularidade e escopo dos valores
- **Pergunta:**
  - "Mes Sinistro = 2025-06-25": é a competência junho/2025 ou um corte diário?
  - Os R$ 70 mi são o sinistro **total** da Parthenon? (O arquivo do case cobre R$ 1,19 mi de um prestador.)
  - A planilha é do mês 6 ou um acumulado?
- **Recomendação do comitê:** tratar como competência mensal (jun/2025), sinistro total da operadora, e declarar a premissa no memo.
- **Decisão (07/11/2026):** o enunciado do case confirma que a planilha é da **operação inteira, com toda a rede**, e que o extrato da Parte 1 é de **um mês de um único prestador**: os dois números não precisam bater. O sinistro processado da planilha (R$ 70 mi) é o sinistro médio mensal do contrato, então os valores são tratados como **mensais**. Mantido como inferência: a planilha não diz "mensal" com todas as letras.
- **Decisor:** PM/CS · **Status:** RESOLVIDA

## AMB-07: Domínio do caráter de atendimento
- **Pergunta:** o contrato fala em "urgência **ou** emergência", mas a origem só tem "Urgência". O sistema de origem agrupa os dois? Existe valor "Emergência" em outros prestadores?
- **Evidência:** há 2 valores distintos em 1.696 itens.
- **Verificação pendente:** o domínio oficial do TISS para "caráter do atendimento" **não foi confirmado**. A tabela de domínio está nos arquivos de terminologia da ANS (pacote ZIP do Padrão TISS), que ainda não foram consultados.
- **Recomendação do comitê:**
  - Valor canônico único `URGENCIA_EMERGENCIA`, preservando `carater_origem`.
  - Valor de origem desconhecido vai para **quarentena**, nunca para "Eletivo" por default.
  - Confirmar na tabela TISS oficial.
- **Decisor:** Especialista · **Status:** ABERTA

## AMB-08: Procedimento cirúrgico repetido no mesmo dia em contas distintas
- **Evidência:**
  - B00080, 22/06: artroscopia em G00042 (IT00262, R$ 5.058,59) **e** em G00149 (IT00942, R$ 3.696,67).
  - B00134, 09/06: colecistectomia em G00053 (IT00335, Eletivo, R$ 4.168,46) **e** em G00110 (IT00697, Urgência, R$ 4.125,87).
- **Leitura:** não há cláusula no PRT-2025-0417 para isso. É candidato às inteligências Arvo "Sobreposição de procedimentos cirúrgicos" e "Guias duplicadas", e mostra o valor do conceito derivado ATENDIMENTO (T11).
- **Recomendação do comitê:** fora do escopo das 3 regras. Gerar **alerta** para o Auditor e levar à Parte 2 como evidência de oportunidade.
- **Decisor:** Auditor · **Status:** ABERTA

## AMB-09: Diária classificada como "Taxa" na origem
- **Evidência:** `tipo_item` = "Taxa" para 60012010 (372 itens). A Cl. 3.4 trata diárias como categoria própria.
- **Recomendação do comitê:** conceito próprio `DIARIA`, mantendo `tipo_item_origem` só como atributo.
- **Decisor:** Especialista · **Status:** ABERTA

## AMB-10: "Consulta em consultório" em conta de internação
- **Evidência:** 25 itens 10101039 em 25 contas de Internação (R$ 6.510,28). O gabarito marca "Não" nos 2 rotulados.
- **Leitura:** pode ser visita hospitalar codificada como consulta de consultório. É um tema de pertinência, fora das 3 regras.
- **Recomendação do comitê:** registrar como conflito semântico. Avaliar a inteligência "Cobrança indevida de procedimentos ambulatoriais durante internação" (hoje Desligada na planilha).
- **Decisor:** Auditor · **Status:** ABERTA

## AMB-11: Porte da taxa de sala divergente do pacote
- **Pergunta:** numa conta com pacote de porte 2 (herniorrafia), a cobrança de taxa de **porte 4** é glosável pela 3.3?
- **Evidência:** 0 casos em jun/2025.
- **Opções:**
  - (A) Glosa integral: a sala está inclusa, qualquer porte.
  - (B) Glosa só se o porte for o correspondente (letra).
  - (C) Revisão humana.
- **Recomendação do comitê:** (C) até decisão jurídica. Implementar o caso no motor para não falhar em silêncio.
- **Decisor:** Jurídico · **Status:** ABERTA

## AMB-12: Pacote fora do regime de internação
- **Evidência:** 100% das 180 contas com procedimento de pacote são de Internação. O contrato não restringe por regime.
- **Recomendação do comitê:** a regra não depende do regime (letra do contrato). Monitorar se surgir pacote em Ambulatorial ou PS.
- **Decisor:** Jurídico · **Status:** ABERTA

## AMB-13: Vigência, reajuste e aditivos do Anexo I
- **Pergunta:** houve reajuste ou aditivo entre 01/01/2025 e jun/2025?
- **Risco:** é o principal argumento do prestador contra a regra 2.2.
- **Recomendação do comitê:** confirmar com a Parthenon e versionar o Anexo I por vigência (`vigencia_inicio` e `vigencia_fim`).
- **Decisor:** Jurídico · **Status:** ABERTA

## AMB-14: Hierarquia de fundamento
- **Proposta:**
  - 1 glosa por item, com valor ≤ valor cobrado.
  - Fundamento principal = regra **integral** de texto mais literal (3.3 ou 4.2). Excedente (2.2) como subsidiário.
  - Em jun/2025 não houve item com regra integral e excedente ao mesmo tempo, mas o motor precisa tratar o caso.
- **Decisor:** Jurídico · **Status:** ABERTA

---

## AMB-15: Denominador do indicador-norte
- **Pergunta:** a economia efetivada é medida sobre o sinistro **total** processado (R$ 70 mi/mês) ou sobre o sinistro **auditável** (itens com regra contratual aplicável)?
- **Evidência:** a meta comercial da Arvo é "2% do sinistro médio mensal", o que aponta para o total. No case, 100% dos itens do São Rafael têm preço pactuado, mas isso não vale para todo prestador.
- **Recomendação do comitê:**
  - **Norte = efetivado ÷ sinistro total processado** (M20), alinhado à meta contratada.
  - Cobertura auditável (M07) como diagnóstico, para explicar quando o teto de ganho é baixo.
- **Decisor:** PM/CS + Paulo Antunes · **Status:** ABERTA

## AMB-16: Linha de base da economia preventiva
- **Pergunta:** como medir o valor que **deixou de ser cobrado** porque o prestador mudou de comportamento? Sem esse número, o sucesso do agente aparece como queda de glosa.
- **Proposta:**
  - A linha de base é a taxa de excedente (excedente ÷ apresentado) por prestador × conceito nos **3 meses anteriores ao go-live**, congelada como versão (`gold.ref_linha_base_excedente`, SCD2).
  - Economia preventiva do mês = `max(0, taxa_base − taxa_atual) × valor apresentado`.
  - Só conta em conceito com volume mínimo, para evitar ruído.
- **Riscos:** sazonalidade, mudança de mix e reajuste de contrato. Rever a linha de base a cada aditivo.
- **Decisor:** Cientista de Dados + PM/CS · **Status:** ABERTA

## AMB-17: Mapeamento regra ↔ inteligência Arvo
- **Pergunta:** a que inteligência da planilha cada regra contratual corresponde? Isso define em que linha do funil a economia da F6 entra.
- **Proposta (semantic/funil.yaml):**
  - R1 ↔ Alto Markup (reformulação contratual)
  - R2 ↔ Conformidade taxas de sala
  - R3 ↔ Pertinencia de Materiais (vínculo parcial)
  - R4 ↔ Pertinência de taxas
- **Decisor:** Arvo + PM/CS · **Status:** ABERTA

## AMB-18: Fonte dos eventos do funil
- **Pergunta:** de onde vêm as datas e valores de cada etapa (envio, registro, recurso, julgamento, efetivação) e o motivo de retenção?
- **Evidência:** a planilha traz só o agregado mensal. Sem eventos por glosa, o funil é uma **fotografia, não uma gestão**.
- **Recomendação do comitê:** é um requisito para a Parthenon (memo da Parte 2): TI expõe eventos por glosa (API ou arquivo), e a auditoria registra o motivo ao reter.
- **Decisor:** Parthenon (TI + Alana) · **Status:** ABERTA

## AMB-19: Taxonomia de motivos de retenção, perda de registro e reversão
- **Pergunta:** os motivos RET-*, REG-* e REC-* de semantic/funil.yaml cobrem a realidade da operação?
- **Recomendação do comitê:** validar com o Dr. Ary (retenção), a Alana (registro) e o Jurídico (reversão) antes de instrumentar a coleta. Lista fechada, com "OUTRO" exigindo texto.
- **Decisor:** Auditor + Contas Médicas + Jurídico · **Status:** ABERTA

## AMB-20: Premissas da matriz de custo de decisão
- **Pergunta:** quanto custa, de fato, uma glosa indevida enviada (recurso, retrabalho, atrito) e quanto custa uma revisão humana? Isso define, por regra, se o envio é AUTOMATICO, com REVISAO_HUMANA ou BLOQUEADO.
- **Premissas atuais** (avaliacao_cientifica/custos.yaml):
  - R$ 60 por FP (operação), mais 20% do valor como atrito;
  - R$ 20 por revisão;
  - piso de 95% no limite inferior do IC para envio automático.
- **Evidência:** com essas premissas, todas as regras têm ganho esperado positivo, mas nenhuma atinge o piso com o gabarito atual (n pequeno). A decisão de envio automático depende do shadow (F10).
- **Decisor:** PM/CS + Jurídico + Auditor · **Status:** ABERTA

## AMB-21: Bandas do painel de sanidade que são premissa
- **Pergunta:** os limites marcados com origem "premissa AMB-21" em `sanidade/indicadores.yaml` estão certos para a Parthenon?
- **Premissas atuais:**
  - S02 atingimento ≥ 80% da trajetória; S07 indevido não detectado ≤ 5%; S08 recurso ≤ 15% (até haver benchmark por regra);
  - S13 efetivação ≥ 80% do benchmark Arvo; S15 concentração top-10 contas ≤ 50%; S23 conflito semântico ≤ 1%;
  - S27 quarentena ≤ 2%; S28 pass rate por dimensão ≥ 99%.
- **Evidência:** na avaliação local, S23 está em 6,72%: o conflito PS × Eletivo é marcado na **conta**, então todos os itens das contas em conflito contam. Decidir se a banda é por item ou por conta antes do go-live.
- **Bandas que não são premissa:** meta de 2% (contrato comercial), invariantes (= 0), piso de precisão (F8/AMB-20), limites de IA (`ia/config/alertas_ia.yaml`) e bandas ±3σ (dinâmicas; ficam em CALIBRANDO até haver histórico).
- **Decisor:** dono de cada indicador, consolidado pelo PM/CS · **Status:** ABERTA
