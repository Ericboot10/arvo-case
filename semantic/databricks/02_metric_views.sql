-- =====================================================================================================
-- 02 · UC Metric Views. GERADO por `python -m semantic.databricks.gerar_metric_views`. NÃO EDITE À MÃO.
-- Fonte: semantic/metricas.yaml (fórmulas, dimensões, níveis) + arquitetura/modelo.yaml (view ↔ tabela).
-- Consulta: SELECT <campo>, MEASURE(<medida>) FROM <view> GROUP BY ALL
-- Ref.: https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference
-- Cada view depende da sua tabela gold. Views com status futuro/especificado só criam depois da fase indicada.
-- AMBIENTE: parâmetro :catalog = arvo_dev | arvo_stg | arvo_prod
-- =====================================================================================================

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA semantic;


-- -----------------------------------------------------------------------------------------------------
-- mv_auditoria_glosa · fonte gold.fato_item_auditado · status especificado (F2)
-- -----------------------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW mv_auditoria_glosa
COMMENT 'auditoria contratual (M01–M09, M27)'
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: gold.fato_item_auditado
fields:
  - name: competencia
    expr: competencia
    comment: "Mês de referência"
  - name: id_prestador
    expr: id_prestador
    comment: "Prestador"
  - name: carater_canonico
    expr: carater_canonico
    comment: "Caráter de atendimento canônico (ELETIVO | URGENCIA_EMERGENCIA). NÃO é o local: Pronto Socorro é regime"
    synonyms: [caráter, natureza do atendimento, eletivo ou urgência, urgência ou emergência]
  - name: regime
    expr: regime
    comment: "Regime de atendimento (INTERNACAO | AMBULATORIAL | PRONTO_SOCORRO). Pronto Socorro não implica urgência"
    synonyms: [tipo de conta, local de atendimento, setor]
  - name: conceito
    expr: conceito
    comment: "Conceito de negócio do item"
    synonyms: [categoria do item, classe do item]
  - name: conceito_pai
    expr: conceito_pai
    comment: "Família do conceito"
    synonyms: [grupo do item, tipo de item]
  - name: cod_tuss
    expr: cod_tuss
    comment: "Código TUSS"
    synonyms: [código do procedimento, código do item, TUSS]
  - name: regra_principal
    expr: regra_principal
    comment: "Regra que fundamenta a glosa"
  - name: clausula_principal
    expr: clausula_principal
    comment: "Cláusula principal"
  - name: conta_tem_pacote
    expr: conta_tem_pacote
    comment: "Conta contém procedimento em pacote"
measures:
  - name: valor_apresentado
    expr: SUM(vl_cobrado)
    comment: "M01 · base · Soma do valor cobrado pelo prestador."
  - name: valor_glosado
    expr: SUM(vl_glosado)
    comment: "M02 · base · Soma do valor glosado pelo agente (identificado, ainda não efetivado)."
  - name: itens_glosados
    expr: COUNT_IF(glosado)
    comment: "M04 · base · Quantidade de itens com glosa."
  - name: pct_contas_com_glosa
    expr: COUNT(DISTINCT CASE WHEN glosado THEN id_conta END) / NULLIF(COUNT(DISTINCT id_conta), 0)
    comment: "M05 · guardrail · Contas com ao menos um item glosado ÷ contas auditadas. Atrito com o prestador."
  - name: taxa_glosa
    expr: SUM(vl_glosado) / NULLIF(SUM(vl_cobrado), 0)
    comment: "M03 · diagnostico · Valor glosado ÷ valor apresentado. Plausibilidade (banda esperada por prestador/regra). NÃO fatiar por cláusula."
  - name: gap_cobrado_vs_pactuado
    expr: SUM(vl_excedente_potencial)
    comment: "M06 · diagnostico · Soma do excedente sobre o teto em TODOS os itens com preço pactuado, glosados ou não. Responde 'qual procedimento tem maior gap em relação ao contrato'."
  - name: cobertura_preco_pactuado
    expr: COUNT_IF(tem_preco_pactuado) / NULLIF(COUNT(1), 0)
    comment: "M07 · diagnostico · Itens com preço pactuado ÷ itens apresentados. Quanto do sinistro é auditável por preço (Cl. 2.3)."
  - name: recorrencia_meses
    expr: COUNT(DISTINCT CASE WHEN glosado THEN competencia END)
    comment: "M27 · diagnostico · Em quantos meses o mesmo padrão (prestador × conceito × cláusula) gerou glosa. Recorrente vira pauta de renegociação."
  - name: aderencia_semantica
    expr: COUNT_IF(conceito IS NOT NULL) / NULLIF(COUNT(1), 0)
    comment: "M08 · sanidade · Itens com código mapeado a conceito aprovado ÷ itens apresentados. Meta 100%."
  - name: taxa_conflito_semantico
    expr: COUNT_IF(conflito_semantico) / NULLIF(COUNT(1), 0)
    comment: "M09 · sanidade · Itens com conflito semântico (p. ex. regime PRONTO_SOCORRO com caráter ELETIVO) ÷ todos os itens. A condição já está no numerador; filtrar por regime ou caráter muda o denominador (o filtro pela própria condição dá 100%)."
$$;

-- -----------------------------------------------------------------------------------------------------
-- mv_funil_economia · fonte gold.fato_funil_economia · status especificado (F2)
-- -----------------------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW mv_funil_economia
COMMENT 'norte, meta e fatores (M14–M24) sobre o funil agregado'
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: gold.fato_funil_economia
fields:
  - name: competencia
    expr: competencia
    comment: "Mês de referência"
  - name: inteligencia
    expr: inteligencia
    comment: "Inteligência Arvo"
  - name: tipo_inteligencia
    expr: tipo_inteligencia
    comment: "Administrativa x Técnica"
  - name: status_inteligencia
    expr: status_inteligencia
    comment: "Ligada x Desligada"
measures:
  - name: indice_norte
    expr: SUM(vl_efetivado) / NULLIF(MAX(vl_sinistro_processado), 0)
    comment: "M20 · norte · Economia efetivada ÷ sinistro processado. É o que define sucesso para a Parthenon."
  - name: atingimento_meta
    expr: SUM(vl_efetivado) / NULLIF(0.02 * MAX(vl_sinistro_processado), 0)
    comment: "M19 · meta · Economia efetivada ÷ meta (2% do sinistro processado do mês)."
  - name: taxa_identificacao
    expr: SUM(vl_identificado) / NULLIF(MAX(vl_sinistro_processado), 0)
    comment: "M21 · fator · Economia identificada ÷ sinistro processado. Alavanca da Arvo (novas regras, cobertura)."
  - name: taxa_ativacao
    expr: SUM(CASE WHEN status_inteligencia = 'Ligada' THEN vl_identificado END) / NULLIF(SUM(vl_identificado), 0)
    comment: "M22 · fator · Identificado em inteligências LIGADAS ÷ identificado total. Alavanca conjunta (ligar desligadas)."
  - name: taxa_envio
    expr: SUM(CASE WHEN status_inteligencia = 'Ligada' THEN vl_enviado_operadora END) / NULLIF(SUM(CASE WHEN status_inteligencia = 'Ligada' THEN vl_identificado END), 0)
    comment: "M23 · fator · Enviado à operadora ÷ identificado, só ligadas. Alavanca da auditoria médica (Dr. Ary)."
  - name: taxa_registro
    expr: SUM(vl_enviado_prestador) / NULLIF(SUM(vl_enviado_operadora), 0)
    comment: "M24 · fator · Registrado no prestador ÷ enviado à operadora. Alavanca de integração (Alana, TI)."
  - name: taxa_efetivacao
    expr: SUM(vl_efetivado) / NULLIF(SUM(vl_enviado_prestador), 0)
    comment: "M18 · fator · Efetivado ÷ registrado no prestador (comparar com taxa_efetivacao_benchmark). Alavanca de defensabilidade."
  - name: economia_efetivada
    expr: SUM(vl_efetivado)
    comment: "M14 · base · Soma da economia efetivada (numerador do norte)."
  - name: economia_identificada
    expr: SUM(vl_identificado)
    comment: "M15 · base · Soma da economia identificada. É insumo, não meta (já passa de 2% e não paga nada sozinha)."
  - name: taxa_retencao_operadora
    expr: SUM(CASE WHEN status_inteligencia = 'Ligada' THEN vl_identificado - vl_enviado_operadora END) / NULLIF(SUM(CASE WHEN status_inteligencia = 'Ligada' THEN vl_identificado END), 0)
    comment: "M16 · diagnostico · (Identificado − enviado à operadora) ÷ identificado, só ligadas. É 1 − M23."
  - name: taxa_perda_registro
    expr: SUM(vl_enviado_operadora - vl_enviado_prestador) / NULLIF(SUM(vl_enviado_operadora), 0)
    comment: "M17 · diagnostico · (Enviado à operadora − registrado no prestador) ÷ enviado. É 1 − M24."
$$;

-- -----------------------------------------------------------------------------------------------------
-- mv_apontamento · fonte gold.fato_apontamento · status especificado (F6)
-- -----------------------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW mv_apontamento
COMMENT 'invariantes dos apontamentos (M26)'
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: gold.fato_apontamento
fields:
  - name: regra_principal
    expr: regra_principal
    comment: "Regra que fundamenta a glosa"
measures:
  - name: violacoes_invariantes
    expr: COUNT_IF(clausula_principal IS NULL OR size(evidencia) = 0 OR vl_glosado <= 0 OR vl_glosado > vl_cobrado)
    comment: "M26 · guardrail · Apontamentos sem cláusula, sem evidência, com glosa ≤ 0 ou maior que o cobrado. Deve ser 0 (bloqueia o envio)."
$$;

-- -----------------------------------------------------------------------------------------------------
-- mv_glosa_ciclo · fonte gold.fato_glosa_ciclo · status futuro (F10)
-- -----------------------------------------------------------------------------------------------------
-- PENDENTE: a fonte gold.fato_glosa_ciclo está com status 'futuro'. Descomente quando ela existir.
-- CREATE OR REPLACE VIEW mv_glosa_ciclo
-- COMMENT 'funil glosa a glosa, recurso, reversão, motivos e tempo de ciclo (M12, M13, M31–M35)'
-- WITH METRICS LANGUAGE YAML AS $$
-- version: 1.1
-- source: gold.fato_glosa_ciclo
-- fields:
--   - name: competencia
--     expr: competencia
--     comment: "Mês de referência"
--   - name: id_prestador
--     expr: id_prestador
--     comment: "Prestador"
--   - name: regra_principal
--     expr: regra_principal
--     comment: "Regra que fundamenta a glosa"
--   - name: inteligencia
--     expr: inteligencia
--     comment: "Inteligência Arvo"
--   - name: motivo_retencao
--     expr: motivo_retencao
--     comment: "Motivo da retenção pela operadora (RET-*)"
--   - name: motivo_registro
--     expr: motivo_registro
--     comment: "Motivo da perda de registro (REG-*)"
--   - name: motivo_reversao
--     expr: motivo_reversao
--     comment: "Motivo da reversão em recurso (REC-*)"
-- measures:
--   - name: taxa_recurso
--     expr: COUNT_IF(dt_recurso IS NOT NULL) / NULLIF(COUNT_IF(dt_registro_prestador IS NOT NULL), 0)
--     comment: "M12 · guardrail · Glosas recorridas ÷ glosas registradas no prestador."
--   - name: taxa_reversao
--     expr: COUNT_IF(vl_revertido > 0) / NULLIF(COUNT_IF(dt_julgamento IS NOT NULL), 0)
--     comment: "M13 · guardrail · Recursos procedentes ÷ recursos julgados. É a precisão real em campo."
--   - name: conversao_glosa_a_glosa
--     expr: SUM(vl_efetivado) / NULLIF(SUM(vl_identificado), 0)
--     comment: "M34 · diagnostico · Efetivado ÷ identificado calculado glosa a glosa (o funil aberto por regra e prestador)."
--   - name: retencao_por_motivo
--     expr: SUM(CASE WHEN etapa_atual = 'RETIDA_OPERADORA' THEN vl_identificado END)
--     comment: "M33 · diagnostico · Valor retido pela operadora, por motivo. Ataca o gargalo da auditoria médica com dado."
--   - name: perda_registro_por_motivo
--     expr: SUM(vl_enviado_operadora - vl_registrado_prestador)
--     comment: "M35 · diagnostico · Valor enviado e não registrado no prestador, por motivo (integração, rejeição, prazo)."
--   - name: tempo_ate_efetivacao
--     expr: AVG(dias_ate_efetivacao)
--     comment: "M31 · diagnostico · Dias médios entre a identificação e a efetivação (onde a glosa fica parada)."
--   - name: valor_em_risco
--     expr: SUM(CASE WHEN etapa_atual = 'EM_RECURSO' THEN vl_recorrido END)
--     comment: "M32 · diagnostico · Valor glosado atualmente em recurso (pode ser revertido)."
-- $$;

-- -----------------------------------------------------------------------------------------------------
-- mv_excedente_mensal · fonte gold.fato_excedente_mensal · status especificado (F9)
-- -----------------------------------------------------------------------------------------------------
-- PENDENTE: a fonte gold.fato_excedente_mensal está com status 'especificado'. Descomente quando ela existir.
-- CREATE OR REPLACE VIEW mv_excedente_mensal
-- COMMENT 'taxa de excedente, reincidência e economia preventiva (M28–M30)'
-- WITH METRICS LANGUAGE YAML AS $$
-- version: 1.1
-- source: gold.fato_excedente_mensal
-- fields:
--   - name: competencia
--     expr: competencia
--     comment: "Mês de referência"
--   - name: id_prestador
--     expr: id_prestador
--     comment: "Prestador"
--   - name: conceito
--     expr: conceito
--     comment: "Conceito de negócio do item"
--     synonyms: [categoria do item, classe do item]
-- measures:
--   - name: taxa_excedente
--     expr: SUM(vl_excedente) / NULLIF(SUM(vl_apresentado), 0)
--     comment: "M30 · diagnostico · Excedente sobre o teto ÷ valor apresentado, por prestador × conceito × mês (base da economia preventiva)."
--   - name: reincidencia_pos_glosa
--     expr: AVG(CASE WHEN teve_glosa_mes_anterior THEN CAST(vl_excedente > 0 AS INT) END)
--     comment: "M28 · diagnostico · Entre os pares prestador × conceito glosados no mês anterior, a fração que voltou a cobrar acima do teto."
--   - name: economia_preventiva
--     expr: SUM(economia_preventiva_estimada)
--     comment: "M29 · diagnostico · Valor que deixou de ser cobrado indevidamente pela mudança de comportamento do prestador, contra a linha de base."
-- $$;

-- -----------------------------------------------------------------------------------------------------
-- mv_qualidade_auditoria · fonte gold.fato_auditoria_amostral · status implementado (F8)
-- -----------------------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW mv_qualidade_auditoria
COMMENT 'precisão auditada e indevido não detectado (M10, M25)'
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: gold.fato_auditoria_amostral
fields:
  - name: regra_principal
    expr: regra_principal
    comment: "Regra que fundamenta a glosa"
  - name: rodada
    expr: rodada
    comment: "Rodada de auditoria amostral"
measures:
  - name: precisao_auditada
    expr: SUM(CASE WHEN estrato = 'GLOSADO' AND auditor_indevido THEN peso_amostral END) / NULLIF(SUM(CASE WHEN estrato = 'GLOSADO' THEN peso_amostral END), 0)
    comment: "M10 · guardrail · Glosas confirmadas pelo auditor ÷ glosas auditadas, PONDERADO pelo peso amostral (Horvitz–Thompson, F8). Sempre com IC. Difere da precisão da amostra do gabarito (ops.v_precisao_recall), que não é ponderada."
  - name: taxa_indevido_nao_detectado
    expr: SUM(CASE WHEN estrato = 'NAO_GLOSADO' AND auditor_indevido THEN peso_amostral END) / NULLIF(SUM(CASE WHEN estrato = 'NAO_GLOSADO' THEN peso_amostral END), 0)
    comment: "M25 · guardrail · Itens NÃO glosados que o auditor considera indevidos ÷ não glosados, PONDERADO pelo peso amostral (F8). Entra na estimativa do recall populacional, mas NÃO é 1 − recall (recall = indevidos glosados ÷ todos os indevidos, em ops.v_precisao_recall)."
$$;
