-- =====================================================================================================
-- F8 · Precisão e recall do agente contra o gabarito do case, no Databricks. Rodar com :catalog.
-- Mesma conta da avaliação local (src/arvo/evaluation/metricas.py), que gera RELATORIO_AVALIACAO.md:
--   pred = o motor glosou o item (gold.fato_item_auditado.glosado); real = gabarito diz "indevido = Sim";
--   só os itens rotulados entram; IC 95% de Wilson; R$: TP e FP pelo valor glosado, FN pelo valor cobrado.
-- Pré-requisitos: F5 (gold.fato_item_auditado) e o notebook f8_carregar_gabarito (bronze.gabarito_raw).
-- =====================================================================================================
USE CATALOG IDENTIFIER(:catalog);

-- 1 linha por item do sinistro: decisão do motor e rótulo do gabarito (quando houver)
CREATE OR REPLACE VIEW gold.v_avaliacao_gabarito
COMMENT 'F8 · item do sinistro × gabarito do case: decisão do motor (pred), rótulo (real) e resultado TP/FP/FN/TN'
AS
SELECT i.id_item, i.id_conta, i.cod_tuss, i.conceito, i.regime, i.carater_canonico,
       i.regra_principal, i.clausula_principal,
       coalesce(i.glosado, false)                AS pred,
       g.id_item IS NOT NULL                     AS rotulado,
       coalesce(g.indevido = 'Sim', false)       AS real,
       CAST(coalesce(i.vl_glosado, 0) AS DOUBLE) AS vl_glosado,
       CAST(i.vl_cobrado AS DOUBLE)              AS vl_cobrado,
       CASE WHEN g.id_item IS NULL THEN NULL
            WHEN coalesce(i.glosado, false) AND g.indevido = 'Sim' THEN 'TP'
            WHEN coalesce(i.glosado, false)                        THEN 'FP'
            WHEN g.indevido = 'Sim'                                THEN 'FN'
            ELSE 'TN' END                        AS resultado
FROM gold.fato_item_auditado i
LEFT JOIN bronze.gabarito_raw g ON g.id_item = i.id_item;

-- Precisão e recall com IC 95% de Wilson: total e precisão por regra (recall por regra não existe: o FN não tem regra)
CREATE OR REPLACE VIEW ops.v_precisao_recall
COMMENT 'F8 · precisão e recall do agente contra o gabarito do case (IC 95% de Wilson), total e por regra'
AS
WITH contagem AS (
  SELECT 'total' AS recorte, 0 AS ordem,
         count_if(resultado = 'TP') AS tp, count_if(resultado = 'FP') AS fp,
         count_if(resultado = 'FN') AS fn, count_if(resultado = 'TN') AS tn,
         sum(CASE WHEN resultado = 'TP' THEN vl_glosado ELSE 0 END) AS vl_tp,
         sum(CASE WHEN resultado = 'FP' THEN vl_glosado ELSE 0 END) AS vl_fp,
         sum(CASE WHEN resultado = 'FN' THEN vl_cobrado ELSE 0 END) AS vl_fn_cobrado
  FROM gold.v_avaliacao_gabarito WHERE rotulado
  UNION ALL
  SELECT concat('regra ', regra_principal), 1,
         count_if(resultado = 'TP'), count_if(resultado = 'FP'), CAST(NULL AS BIGINT), CAST(NULL AS BIGINT),
         sum(CASE WHEN resultado = 'TP' THEN vl_glosado ELSE 0 END),
         sum(CASE WHEN resultado = 'FP' THEN vl_glosado ELSE 0 END), CAST(NULL AS DOUBLE)
  FROM gold.v_avaliacao_gabarito WHERE rotulado AND pred
  GROUP BY regra_principal
),
taxas AS (
  SELECT *, 1.959963984540054 AS z,
         CAST(nullif(tp + fp, 0) AS DOUBLE) AS n_p, tp / nullif(tp + fp, 0) AS precisao,
         CAST(nullif(tp + fn, 0) AS DOUBLE) AS n_r, tp / nullif(tp + fn, 0) AS recall
  FROM contagem
)
SELECT recorte, ordem, tp, fp, fn, tn, tp + fp + coalesce(fn, 0) + coalesce(tn, 0) AS itens_rotulados,
       precisao,
       (precisao + z*z/(2*n_p) - z*sqrt(precisao*(1-precisao)/n_p + z*z/(4*n_p*n_p))) / (1 + z*z/n_p) AS precisao_ic_inf,
       (precisao + z*z/(2*n_p) + z*sqrt(precisao*(1-precisao)/n_p + z*z/(4*n_p*n_p))) / (1 + z*z/n_p) AS precisao_ic_sup,
       recall,
       (recall + z*z/(2*n_r) - z*sqrt(recall*(1-recall)/n_r + z*z/(4*n_r*n_r))) / (1 + z*z/n_r) AS recall_ic_inf,
       (recall + z*z/(2*n_r) + z*sqrt(recall*(1-recall)/n_r + z*z/(4*n_r*n_r))) / (1 + z*z/n_r) AS recall_ic_sup,
       vl_tp / nullif(vl_tp + vl_fp, 0)          AS precisao_rs,
       vl_tp / nullif(vl_tp + vl_fn_cobrado, 0)  AS recall_rs_limite_inferior,
       vl_tp, vl_fp, vl_fn_cobrado
FROM taxas;

-- Rodada 0 de auditoria = gabarito do case, com peso pós-estratificado por código TUSS × decisão do motor
-- (mesma regra de src/arvo/monitoring/local.py). Alimenta a metric view mv_qualidade_auditoria e os indicadores S05/S06.
CREATE OR REPLACE TABLE gold.fato_auditoria_amostral
COMMENT 'F8 · itens auditados com peso amostral. Rodada R0_gabarito_case = gabarito do case (não probabilística)'
AS
WITH pop AS (SELECT cod_tuss, pred, count(*) AS n_pop FROM gold.v_avaliacao_gabarito GROUP BY cod_tuss, pred),
     amo AS (SELECT cod_tuss, pred, count(*) AS n_amo FROM gold.v_avaliacao_gabarito WHERE rotulado GROUP BY cod_tuss, pred)
SELECT a.id_item, 'R0_gabarito_case' AS rodada,
       CASE WHEN a.pred THEN 'GLOSADO' ELSE 'NAO_GLOSADO' END AS estrato,
       a.cod_tuss AS subestrato,
       CAST(pop.n_pop AS DOUBLE) / amo.n_amo AS peso_amostral,
       CASE WHEN a.pred THEN a.regra_principal END AS regra_principal,
       a.pred AS agente_indevido, a.real AS auditor_indevido,
       'gabarito_case' AS auditor, CAST(NULL AS STRING) AS motivo
FROM gold.v_avaliacao_gabarito a
JOIN pop ON pop.cod_tuss = a.cod_tuss AND pop.pred = a.pred
JOIN amo ON amo.cod_tuss = a.cod_tuss AND amo.pred = a.pred
WHERE a.rotulado;

ALTER TABLE gold.fato_auditoria_amostral SET TAGS ('origem_dado' = 'case_arvo');
