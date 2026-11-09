-- =====================================================================================================
-- F7 · View de sanidade da camada de IA sobre ops.llm_calls (mesmas definições de ia/indicadores.py)
-- Rodar com :catalog. Alertas: comparar com os limites de ia/config/alertas_ia.yaml (SQL alerts do Databricks).
-- Complementa as system tables de uso e as inference tables do AI Gateway (que veem só o tráfego pelo Gateway).
-- =====================================================================================================
USE CATALOG IDENTIFIER(:catalog);

CREATE OR REPLACE VIEW ops.v_ia_sanidade
COMMENT 'Indicadores de sanidade de IA por dia × tarefa × adapter (F7). Fonte: ops.llm_calls'
AS
WITH base AS (
  SELECT *, to_date(from_unixtime(ts_inicio)) AS dia,
         stop_normalizado IN ('BLOQUEADO_POLITICA_DADOS', 'BLOQUEADO_CIRCUITO', 'BLOQUEADO_ORCAMENTO') AS bloqueada,
         coalesce(cache_hit_local, false) AS hit
  FROM ops.llm_calls
)
SELECT
  dia, task_id, adapter, provedor, first(modelo_pedido) AS modelo_pedido,
  count(*) AS chamadas,
  count_if(NOT bloqueada AND NOT hit) AS chamadas_efetivas,
  avg(CASE WHEN NOT bloqueada AND NOT hit THEN CAST(schema_valido AS INT) END) AS taxa_schema_valido,
  avg(CASE WHEN NOT bloqueada AND NOT hit THEN CAST(stop_normalizado = 'RECUSA' AS INT) END) AS taxa_recusa,
  avg(CASE WHEN NOT bloqueada AND NOT hit THEN CAST(stop_normalizado = 'TRUNCADO' AS INT) END) AS taxa_truncamento,
  avg(CASE WHEN NOT bloqueada AND NOT hit THEN CAST(stop_normalizado = 'ERRO' AS INT) END) AS taxa_erro,
  avg(CAST(fallback_de IS NOT NULL AS INT)) AS taxa_fallback,
  avg(CAST(hit AS INT)) AS taxa_cache_hit,
  avg(CAST(stop_normalizado = 'BLOQUEADO_POLITICA_DADOS' AS INT)) AS taxa_bloqueio_politica,
  avg(CAST(stop_normalizado = 'BLOQUEADO_CIRCUITO' AS INT)) AS taxa_bloqueio_circuito,
  avg(CASE WHEN NOT bloqueada AND NOT hit THEN CAST(size(params_ignorados) > 0 AS INT) END) AS pct_param_ignorado,
  percentile(CASE WHEN NOT bloqueada AND NOT hit THEN latencia_ms END, 0.5) AS latencia_p50_ms,
  percentile(CASE WHEN NOT bloqueada AND NOT hit THEN latencia_ms END, 0.95) AS latencia_p95_ms,
  sum(coalesce(input_tokens, 0)) AS input_tokens,
  sum(coalesce(output_tokens, 0)) AS output_tokens,
  sum(coalesce(cache_read_tokens, 0)) AS cache_read_tokens,
  sum(coalesce(reasoning_tokens, 0)) AS reasoning_tokens,
  sum(coalesce(custo_estimado_usd, 0)) AS custo_estimado_usd,
  array_sort(collect_set(modelo_servido)) AS modelos_servidos,
  size(collect_set(modelo_servido)) > 1
    OR max(CASE WHEN modelo_servido IS NOT NULL AND modelo_servido <> modelo_pedido THEN 1 ELSE 0 END) = 1 AS drift_modelo
FROM base
GROUP BY dia, task_id, adapter, provedor;
