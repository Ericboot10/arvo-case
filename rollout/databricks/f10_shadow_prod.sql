-- =====================================================================================================
-- F10 · Só em arvo_prod: apontamentos em SHADOW gravados em gold_shadow (lidos pela auditoria, nunca enviados).
-- Mesmo grão e colunas de gold.fato_apontamento + estágio e destino (ADR-003: o schema gold_shadow só existe em prod).
-- =====================================================================================================
CREATE TABLE IF NOT EXISTS arvo_prod.gold_shadow.fato_apontamento AS
SELECT a.*, CAST(NULL AS STRING) AS estagio_regra, CAST(NULL AS STRING) AS destino_envio
FROM arvo_prod.gold.fato_apontamento a WHERE false;
