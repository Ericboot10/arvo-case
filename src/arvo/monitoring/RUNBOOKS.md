# Runbooks do painel de sanidade (F9)

> GERADO por `python -m arvo.monitoring.gerar` a partir de [`indicadores.yaml`](indicadores.yaml). Não edite à mão.

Severidade: **CRITICA** bloqueia o envio do run e alerta a cada hora · **ALTA** alerta diário, ação no dia · **MEDIA** alerta diário, ação na semana · **INFO** só painel.

## Indicadores

| Id | Seção | Indicador | Definição | Banda | Origem da banda | Severidade | Dono | Runbook |
|---|---|---|---|---|---|---|---|---|
| S01 | Parte II · Funil da rede Parthenon (6 meses) | Índice-norte da rede (efetivado ÷ sinistro da rede) | M20 | ≥ 0.02 | meta contratada da Parthenon (2% do sinistro) | ALTA | pm_cs | [RB-VALOR](#rb-valor) |
| S02 | Parte II · Funil da rede Parthenon (6 meses) | Atingimento da meta da rede (run-rate) | M19 | ≥ 0.8 | premissa AMB-21: 80% da trajetória planejada | ALTA | pm_cs | [RB-VALOR](#rb-valor) |
| S03 | Parte I · Agente · Hospital São Rafael (jun/2025) | Taxa de glosa sobre o apresentado, por regra | M03 | ±3σ das 6 competências anteriores (mín. 6) | banda histórica ±3σ (plano 9.1) | MEDIA | analytics_engineer | [RB-COMPORTAMENTO](#rb-comportamento) |
| S04 | Parte I · Agente · Hospital São Rafael (jun/2025) | Gap cobrado vs pactuado (R$) | M06 | ±3σ das 6 competências anteriores (mín. 6) | banda histórica ±3σ | INFO | especialista_contas_medicas | [RB-COBERTURA](#rb-cobertura) |
| S40 | Parte I · Agente · Hospital São Rafael (jun/2025) | Taxa de glosa identificada (glosado ÷ apresentado) | M03 | ±3σ das 6 competências anteriores (mín. 6) | banda histórica ±3σ do hospital; a taxa deve cair depois dos primeiros ciclos de glosa (RESPOSTAS_CASE, seção 4) | MEDIA | pm_cs | [RB-PRESTADOR](#rb-prestador) |
| S05 | Parte I · Agente · Hospital São Rafael (jun/2025) | Precisão auditada (ponderada), por regra | M10 | ≥ 0.98 | critério de go-live por regra (plano F10) | ALTA | cientista_dados | [RB-QUALIDADE](#rb-qualidade) |
| S06 | Parte I · Agente · Hospital São Rafael (jun/2025) | Limite inferior do IC 95% da precisão, por regra | SQL próprio | ≥ 0.95 | piso de envio automático (custos.yaml, AMB-20) | ALTA | cientista_dados | [RB-QUALIDADE](#rb-qualidade) |
| S07 | Parte I · Agente · Hospital São Rafael (jun/2025) | Indevido não detectado (ponderado) | M25 | ≤ 0.05 | premissa AMB-21 | MEDIA | cientista_dados | [RB-QUALIDADE](#rb-qualidade) |
| S08 | Parte I · Agente · Hospital São Rafael (jun/2025) | Taxa de recurso | M12 | ≤ 0.15 | premissa AMB-21 até existir benchmark por regra | ALTA | juridico | [RB-QUALIDADE](#rb-qualidade) |
| S09 | Parte I · Agente · Hospital São Rafael (jun/2025) | Taxa de reversão (precisão em campo) | M13 | ≤ 0.05 | critério de go-live (plano F10) | CRITICA | juridico | [RB-QUALIDADE](#rb-qualidade) |
| S10 | Parte II · Funil da rede Parthenon (6 meses) | Ativação (identificado em ligadas ÷ total) | M22 | ±3σ das 6 competências anteriores (mín. 3) | banda histórica ±3σ | MEDIA | pm_cs | [RB-FUNIL](#rb-funil) |
| S11 | Parte II · Funil da rede Parthenon (6 meses) | Envio à operadora (1 − retenção) | M23 | ±3σ das 6 competências anteriores (mín. 3) | banda histórica ±3σ | ALTA | pm_cs | [RB-FUNIL](#rb-funil) |
| S12 | Parte II · Funil da rede Parthenon (6 meses) | Perda de registro no prestador | M17 | ≤ 0.05 | plano 9.1 (falha de integração) | ALTA | pm_cs | [RB-FUNIL](#rb-funil) |
| S13 | Parte II · Funil da rede Parthenon (6 meses) | Efetivação ÷ benchmark Arvo, por inteligência | SQL próprio | ≥ 0.8 | premissa AMB-21: 80% do benchmark de efetivação da Arvo | MEDIA | juridico | [RB-FUNIL](#rb-funil) |
| S14 | Parte I · Agente · Hospital São Rafael (jun/2025) | Contas com glosa, por prestador | M05 | ±3σ das 6 competências anteriores (mín. 6) | banda histórica ±3σ do prestador | MEDIA | pm_cs | [RB-PRESTADOR](#rb-prestador) |
| S15 | Parte I · Agente · Hospital São Rafael (jun/2025) | Concentração da glosa nas 10 maiores contas | SQL próprio | ≤ 0.5 | premissa AMB-21 | INFO | pm_cs | [RB-PRESTADOR](#rb-prestador) |
| S16 | Parte I · Agente · Hospital São Rafael (jun/2025) | Itens glosados, por regra (hit rate) | M04 | ±3σ das 6 competências anteriores (mín. 6) | banda histórica ±3σ | MEDIA | analytics_engineer | [RB-COMPORTAMENTO](#rb-comportamento) |
| S17 | Parte I · Agente · Hospital São Rafael (jun/2025) | Cobertura de preço pactuado | M07 | ±3σ das 6 competências anteriores (mín. 6) | banda histórica ±3σ | MEDIA | especialista_contas_medicas | [RB-COBERTURA](#rb-cobertura) |
| S18 | Parte I · Agente · Hospital São Rafael (jun/2025) | Apontamentos que violam invariantes | M26 | ≤ 0 | invariante jurídico | CRITICA | juridico | [RB-INVARIANTE](#rb-invariante) |
| S19 | Parte I · Agente · Hospital São Rafael (jun/2025) | Itens com mais de uma glosa | SQL próprio | ≤ 0 | invariante: no máximo 1 glosa por item (grão do fato) | CRITICA | engenheiro_dados | [RB-INVARIANTE](#rb-invariante) |
| S20 | Parte I · Agente · Hospital São Rafael (jun/2025) | Contas com glosa maior que o cobrado | SQL próprio | ≤ 0 | invariante: Σ glosa da conta ≤ total da conta | CRITICA | juridico | [RB-INVARIANTE](#rb-invariante) |
| S21 | Parte I · Agente · Hospital São Rafael (jun/2025) | Apontamentos sem item auditado (órfãos) | SQL próprio | ≤ 0 | invariante: integridade referencial | CRITICA | engenheiro_dados | [RB-INVARIANTE](#rb-invariante) |
| S22 | Aderência semântica | Aderência semântica (itens com conceito) | M08 | ≥ 1.0 | meta da camada semântica (100%) | ALTA | analytics_engineer | [RB-SEMANTICA](#rb-semantica) |
| S23 | Aderência semântica | Conflito semântico (ex.: PS × Eletivo) | M09 | ≤ 0.01 | premissa AMB-21 | MEDIA | especialista_contas_medicas | [RB-SEMANTICA](#rb-semantica) |
| S24 | Aderência semântica | Versões da semântica num mesmo run | SQL próprio | ≤ 1 | invariante: um run, uma versão | CRITICA | analytics_engineer | [RB-SEMANTICA](#rb-semantica) |
| S25 | Aderência semântica | Versões do contrato num mesmo run | SQL próprio | ≤ 1 | invariante: um run, um contrato vigente | CRITICA | engenheiro_dados | [RB-SEMANTICA](#rb-semantica) |
| S26 | Engenharia de dados | Expectations de falha reprovadas (último run) | SQL próprio | ≤ 0 | expectations E* com ação fail (src/arvo/medallion/expectations.yaml) | CRITICA | engenheiro_dados | [RB-DADOS](#rb-dados) |
| S27 | Engenharia de dados | Taxa de quarentena (último run) | SQL próprio | ≤ 0.02 | premissa AMB-21 | ALTA | engenheiro_dados | [RB-DADOS](#rb-dados) |
| S28 | Engenharia de dados | Pass rate por dimensão de qualidade (último run) | SQL próprio | ≥ 0.99 | premissa AMB-21 | MEDIA | engenheiro_dados | [RB-DADOS](#rb-dados) |
| S30 | IA | Schema válido | limite IA `taxa_schema_valido` | ≥ 0.98 | src/arvo/ai/config/alertas_ia.yaml | ALTA | cientista_dados | [RB-IA](#rb-ia) |
| S31 | IA | Recusa | limite IA `taxa_recusa` | ≤ 0.01 | src/arvo/ai/config/alertas_ia.yaml | MEDIA | cientista_dados | [RB-IA](#rb-ia) |
| S32 | IA | Truncamento | limite IA `taxa_truncamento` | ≤ 0.01 | src/arvo/ai/config/alertas_ia.yaml | MEDIA | cientista_dados | [RB-IA](#rb-ia) |
| S33 | IA | Erro | limite IA `taxa_erro` | ≤ 0.05 | src/arvo/ai/config/alertas_ia.yaml | ALTA | engenheiro_dados | [RB-IA](#rb-ia) |
| S34 | IA | Fallback de provedor | limite IA `taxa_fallback` | ≤ 0.1 | src/arvo/ai/config/alertas_ia.yaml | MEDIA | engenheiro_dados | [RB-IA](#rb-ia) |
| S35 | IA | Bloqueio por política de dados | limite IA `taxa_bloqueio_politica` | ≤ 0.0 | src/arvo/ai/config/alertas_ia.yaml | CRITICA | engenheiro_dados | [RB-IA](#rb-ia) |
| S36 | IA | Bloqueio por circuito | limite IA `taxa_bloqueio_circuito` | ≤ 0.0 | src/arvo/ai/config/alertas_ia.yaml | ALTA | engenheiro_dados | [RB-IA](#rb-ia) |
| S37 | IA | Latência p95 (ms) | limite IA `latencia_p95_ms` | ≤ 120000 | src/arvo/ai/config/alertas_ia.yaml | MEDIA | engenheiro_dados | [RB-IA](#rb-ia) |
| S38 | IA | Parâmetro pedido e não aplicado | limite IA `pct_param_ignorado` | ≤ 1.0 | src/arvo/ai/config/alertas_ia.yaml | INFO | cientista_dados | [RB-IA](#rb-ia) |
| S39 | IA | Drift de modelo | limite IA `drift_modelo` | ≤ 0 | src/arvo/ai/config/alertas_ia.yaml (drift_modelo) | ALTA | cientista_dados | [RB-IA](#rb-ia) |

## RB-VALOR

**Valor abaixo da meta**. Disparado por: S01, S02.

1. Abrir a página Negócio do painel e a árvore do norte (M21 × M22 × M23 × M24 × M18)
2. Identificar o fator com maior queda contra a competência anterior
3. Encaminhar ao dono do fator: identificação (Arvo), ativação (cliente), envio (Dr. Ary), registro (Alana), efetivação (Jurídico)
4. Registrar a hipótese e o plano no decision log da conta

Ação específica por indicador:

- **S01** (Índice-norte da rede (efetivado ÷ sinistro da rede)): Abrir a árvore do norte (M21 × M22 × M23 × M24 × M18) e atacar o fator que mais caiu
- **S02** (Atingimento da meta da rede (run-rate)): Reprojetar a trajetória com o Paulo; priorizar inteligências desligadas de maior valor

Escalonamento: PM/CS → Paulo (Parthenon) na reunião mensal.

## RB-QUALIDADE

**Qualidade da decisão abaixo do piso**. Disparado por: S05, S06, S07, S08, S09.

1. Rebaixar a regra para REVISAO_HUMANA (kill switch em src/arvo/rules/regras.yaml, nova versão)
2. Separar FP por causa (avaliacao_cientifica.divergencias.classificar)
3. Se a causa é regra: abrir AMB e revisar com Jurídico e Auditor. Se é rótulo: adjudicação cega (κ ≥ 0,8)
4. Reavaliar com o plano amostral da F8 antes de religar o envio automático

Ação específica por indicador:

- **S05** (Precisão auditada (ponderada), por regra): Regra em envio automático cai para REVISAO_HUMANA (kill switch da regra)
- **S06** (Limite inferior do IC 95% da precisão, por regra): Manter a regra em REVISAO_HUMANA e ampliar a amostra auditada (plano amostral F8)
- **S07** (Indevido não detectado (ponderado)): Abrir os FN da rodada: regra nova (vira AMB) ou ruído de rotulagem (teste de concentração F8)
- **S08** (Taxa de recurso): Ler os recursos da regra; se o argumento se repete, revisar a cláusula com o Jurídico
- **S09** (Taxa de reversão (precisão em campo)): Kill switch da regra com reversão > 5% até adjudicação

Escalonamento: Cientista → Dr. Ary (auditoria) e Jurídico.

## RB-FUNIL

**Vazamento no funil de economia**. Disparado por: S10, S11, S12, S13.

1. Localizar a etapa e a inteligência que vazaram (página Negócio)
2. Retenção: motivos RET-* com a auditoria. Registro: conciliação com a TI. Efetivação: evidências e recursos
3. Quantificar o valor perdido e propor a ação ao cliente

Ação específica por indicador:

- **S10** (Ativação (identificado em ligadas ÷ total)): Inteligência desligada nova? Levar ao cliente com o valor identificado
- **S11** (Envio à operadora (1 − retenção)): Retenção subiu: abrir motivos RET-* com o Dr. Ary (AMB-19)
- **S12** (Perda de registro no prestador): Conciliar enviados × registrados com a TI da Parthenon (Alana): integração, rejeição ou prazo
- **S13** (Efetivação ÷ benchmark Arvo, por inteligência): Defensabilidade fraca: revisar justificativas e evidências da inteligência

Escalonamento: PM/CS → cliente (Dr. Ary, Alana ou Paulo, conforme a etapa).

## RB-PRESTADOR

**Atrito com o prestador**. Disparado por: S14, S15, S40.

1. Abrir as contas do prestador no run e conferir se uma regra concentra a glosa
2. Validar com o Especialista se a cobrança mudou ou se a regra está agressiva
3. Combinar comunicação prévia com o prestador antes do envio

Ação específica por indicador:

- **S14** (Contas com glosa, por prestador): Atrito desproporcional: conversar com o prestador antes do próximo envio
- **S15** (Concentração da glosa nas 10 maiores contas): Concentração anômala: conferir se uma conta isolada distorce o run
- **S40** (Taxa de glosa identificada (glosado ÷ apresentado)): A taxa não caiu depois das primeiras glosas: deixa de ser erro de implantação e vira assunto de relacionamento com o prestador

Escalonamento: PM/CS → relacionamento com prestadores da Parthenon.

## RB-COMPORTAMENTO

**Mudança brusca de hit rate**. Disparado por: S03, S16.

1. Checar S26–S28 (dados) e S22–S25 (semântica) do mesmo run
2. Dados e semântica OK: é comportamento do prestador (sucesso preventivo, M28/M29)
3. Algo fora: tratar como bug e reprocessar

Ação específica por indicador:

- **S03** (Taxa de glosa sobre o apresentado, por regra): Separar sucesso (prestador parou de cobrar) de bug (mudou o dado): conferir S27/S28 do mesmo run
- **S16** (Itens glosados, por regra (hit rate)): Queda brusca: sucesso ou bug? Se os indicadores de dados estão OK, é comportamento do prestador

Escalonamento: Analytics Engineer → Engenharia de Dados.

## RB-COBERTURA

**Cobertura do contrato caindo**. Disparado por: S04, S17.

1. Listar códigos sem preço pactuado com maior valor apresentado
2. Classificar: fora do Anexo I (Cl. 2.3), código novo ou erro de mapeamento
3. Levar à renegociação ou à fila semântica

Ação específica por indicador:

- **S04** (Gap cobrado vs pactuado (R$)): Levar os maiores gaps por conceito à pauta de renegociação
- **S17** (Cobertura de preço pactuado): Códigos fora do Anexo I crescendo (Cl. 2.3): pedir aditivo ou tabela de referência

Escalonamento: Especialista em Contas → Jurídico.

## RB-INVARIANTE

**Invariante violado (envio bloqueado)**. Disparado por: S18, S19, S20, S21.

1. O portão de envio já bloqueou o run (sanidade.portao). Não liberar manualmente
2. Reproduzir localmente com o mesmo run_id e versões (contrato, semântica, regras)
3. Corrigir, adicionar teste de regressão e reprocessar
4. Liberar o envio só com o indicador de volta a 0

Ação específica por indicador:

- **S18** (Apontamentos que violam invariantes): Envio bloqueado. Corrigir o motor ou a regra; reprocessar o run
- **S19** (Itens com mais de uma glosa): Envio bloqueado. Duplicidade no motor ou no merge do fato
- **S20** (Contas com glosa maior que o cobrado): Envio bloqueado. Revisar a regra de pacote/escopo de conta
- **S21** (Apontamentos sem item auditado (órfãos)): Envio bloqueado. Lineage quebrada entre motor e fato

Escalonamento: Engenharia de Dados → Jurídico (se algum apontamento já tiver saído).

## RB-SEMANTICA

**Aderência semântica degradada**. Disparado por: S22, S23, S24, S25.

1. Códigos sem conceito: rodar a sugestão de conceito (ia.tarefas.sugerir_conceito) e enviar à fila do Especialista
2. Conflitos: conferir o domínio canônico (src/arvo/semantic/dominios.yaml) e o AMB-01
3. Versões misturadas: bloquear e reprocessar com a versão única

Ação específica por indicador:

- **S22** (Aderência semântica (itens com conceito)): Código sem conceito: fila do Especialista (ops.ia_sugestoes_conceito); nunca mapear sem aprovação
- **S23** (Conflito semântico (ex.: PS × Eletivo)): Conflitos vão para REVISAO_HUMANA (AMB-01); se crescem, o prestador mudou a codificação
- **S24** (Versões da semântica num mesmo run): Envio bloqueado. Run misturou versões do glossário: reprocessar
- **S25** (Versões do contrato num mesmo run): Envio bloqueado. Conferir dim_contrato (SCD2) e vigência

Escalonamento: Analytics Engineer → Especialista em Contas.

## RB-DADOS

**Qualidade de dados reprovada**. Disparado por: S26, S27, S28.

1. Abrir ops.dq_resultados do run e as linhas em quarentena
2. Classificar: arquivo malformado (devolver ao cliente), código novo (fila semântica) ou bug (corrigir)
3. Freshness, completude e drift de volume: usar o data quality monitoring (anomaly detection) do Unity Catalog nos schemas silver e gold

Ação específica por indicador:

- **S26** (Expectations de falha reprovadas (último run)): Envio bloqueado. Abrir ops.dq_resultados do run e a expectation reprovada
- **S27** (Taxa de quarentena (último run)): Ler os motivos da quarentena; código novo vai para a fila semântica (S22)
- **S28** (Pass rate por dimensão de qualidade (último run)): Dimensão degradada: abrir as expectations dela e comparar com o run anterior

Escalonamento: Engenharia de Dados → TI do cliente (arquivo).

## RB-IA

**Sanidade da camada de IA**. Disparado por: S30, S31, S32, S33, S34, S35, S36, S37, S38, S39.

1. Abrir ops.v_ia_sanidade e ops.llm_calls da tarefa × adapter
2. Seguir a ação do limite em src/arvo/ai/config/alertas_ia.yaml
3. Drift de modelo ou troca de provedor: rodar o golden set (python -m arvo.ai.avaliacao.golden) antes de aceitar
4. Bloqueio por política: é bug de configuração. Nenhum dado de sinistro pode sair para provedor externo

Ação específica por indicador:

- **S30** (Schema válido): revisar prompt/schema; rodar golden set do provedor
- **S31** (Recusa): ver stop_detalhe; avaliar fallback de provedor
- **S32** (Truncamento): aumentar max_output_tokens ou dividir a tarefa
- **S33** (Erro): provedor degradado: checar circuito e fallback
- **S34** (Fallback de provedor): primário instável: abrir incidente com o provedor
- **S35** (Bloqueio por política de dados): BUG de configuração: tarefa tentou enviar classe de dado proibida
- **S36** (Bloqueio por circuito): adapter com falhas consecutivas: investigar antes de reabrir
- **S37** (Latência p95 (ms)): considerar tier menor ou batch
- **S38** (Parâmetro pedido e não aplicado): informativo: parâmetro pedido e não aceito pelo modelo
- **S39** (Drift de modelo): modelo servido diferente do pedido ou mais de um modelo servido → rodar golden set antes de aceitar

Escalonamento: Cientista de Dados → Engenharia de Dados.
