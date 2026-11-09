-- =====================================================================================================
-- F3 · Tabelas Delta da extração de contrato e da telemetria de IA
-- Rodar com o parâmetro :catalog = arvo_dev | arvo_stg | arvo_prod
-- Tabelas managed (recomendação do Unity Catalog). Em prod, MODIFY só para o service principal do job.
-- =====================================================================================================
USE CATALOG IDENTIFIER(:catalog);
CREATE SCHEMA IF NOT EXISTS contracts COMMENT 'Contratos como dado (F3): parâmetros versionados e aprovados';
CREATE SCHEMA IF NOT EXISTS ops COMMENT 'Operação: estado de pipelines e telemetria de IA';

-- Telemetria obrigatória por chamada de IA (plano v2, 9.4). Uma linha por chamada, incluindo cache hit e falha.
CREATE TABLE IF NOT EXISTS ops.llm_calls (
  call_id STRING NOT NULL, run_id STRING, task_id STRING, chave_idempotencia STRING, ts_inicio DOUBLE, ambiente STRING,
  provedor STRING, adapter STRING, familia STRING, endpoint STRING, modelo_pedido STRING, modelo_servido STRING,
  fallback_de STRING,
  prompt_id STRING, prompt_versao STRING, prompt_hash STRING, system_hash STRING,
  schema_id STRING, schema_versao STRING, schema_hash STRING,
  params_pedidos MAP<STRING, STRING>, params_aplicados MAP<STRING, STRING>, params_ignorados MAP<STRING, STRING>
    COMMENT 'Parâmetro pedido e não aplicado, com motivo (ex.: temperature em modelo que não aceita)',
  input_tokens BIGINT, output_tokens BIGINT, cache_read_tokens BIGINT, cache_write_tokens BIGINT, reasoning_tokens BIGINT,
  custo_estimado_usd DOUBLE, cache_hit_local BOOLEAN, latencia_ms DOUBLE,
  stop_normalizado STRING COMMENT 'COMPLETO | TRUNCADO | RECUSA | FILTRO_CONTEUDO | ERRO | BLOQUEADO_ORCAMENTO',
  stop_bruto STRING, stop_detalhe STRING, schema_valido BOOLEAN, erros_schema ARRAY<STRING>, erro STRING,
  request_id STRING, documento_sha256 STRING,
  classe_dados STRING COMMENT 'Classe do dado enviado (src/arvo/ai/config/politica_dados.yaml)',
  perimetro STRING COMMENT 'local | plataforma | externo'
) COMMENT 'Telemetria de toda chamada de IA. Complementa as inference tables e as system tables do AI Gateway.';

CREATE TABLE IF NOT EXISTS ops.contract_extraction_state (
  chave_idempotencia STRING NOT NULL, contrato STRING, estado STRING, historico STRING COMMENT 'JSON com as transições',
  atualizado_em TIMESTAMP
) COMMENT 'Máquina de estados da extração: RECEBIDO→...→REVISAO_HUMANA→APROVADO|REJEITADO';

CREATE TABLE IF NOT EXISTS contracts.contract_field_candidates (
  chave_idempotencia STRING, run_id STRING, contrato STRING, campo STRING, status STRING,
  fonte STRING, valor STRING, quote STRING, quote_ok BOOLEAN, valor_ok BOOLEAN,
  juiz_veredito STRING, juiz_quote_ok BOOLEAN
) COMMENT 'Um registro por campo x extrator (D/A/B), com a evidência literal e o resultado da reconciliação';

CREATE TABLE IF NOT EXISTS contracts.contract_params (
  versao_contrato STRING NOT NULL COMMENT 'id@data-hash; imutável',
  id_contrato STRING, documento_sha256 STRING, aprovado_por STRING, papel STRING, data_aprovacao STRING,
  params_json STRING COMMENT 'contract_params.json aprovado (anexo_i, anexo_ii, taxas_condicionadas, regras)',
  vigente BOOLEAN COMMENT 'Só uma versão vigente por contrato; o motor de regras (F6) lê apenas vigente = true'
) COMMENT 'Parâmetros contratuais APROVADOS pelo Jurídico. Única fonte de parâmetros para o motor de regras.';

-- Indicadores de sanidade de IA (exemplos sobre ops.llm_calls)
-- SELECT task_id, adapter, COUNT(*) chamadas, AVG(CAST(schema_valido AS INT)) taxa_schema_valido,
--        AVG(CASE WHEN stop_normalizado='TRUNCADO' THEN 1 ELSE 0 END) taxa_truncamento,
--        AVG(CASE WHEN stop_normalizado='RECUSA' THEN 1 ELSE 0 END) taxa_recusa,
--        AVG(CASE WHEN fallback_de IS NOT NULL THEN 1 ELSE 0 END) taxa_fallback,
--        PERCENTILE(latencia_ms, 0.95) p95_ms, SUM(custo_estimado_usd) custo_usd,
--        SUM(CASE WHEN size(params_ignorados) > 0 THEN 1 ELSE 0 END) chamadas_com_param_ignorado
-- FROM ops.llm_calls GROUP BY ALL;
