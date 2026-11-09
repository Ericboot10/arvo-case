-- =====================================================================================================
-- F4 · 02 · Proteção de dado pessoal sensível (LGPD: dado de saúde vinculado a pessoa)
--
-- Estratégia em camadas (ADR-002):
--   1. dev NÃO recebe dado real: só sintético (src/arvo/platform/sinteticos);
--   2. em stg/prod, identificador de pessoa é PSEUDONIMIZADO por máscara de coluna. O hash é estável,
--      então os joins entre tabelas continuam funcionando sem expor o id real;
--   3. em claro, só para quem precisa (grupo arvo-lgpd-acesso-pleno, ex.: auditoria médica em caso de recurso);
--   4. o sinistro NUNCA vai para LLM externo (só o contrato vai, na F3).
--
-- A doc Databricks recomenda ABAC (políticas por tag) para mascarar de forma consistente entre muitas tabelas.
-- Aqui fica a versão explícita por coluna, que é mais simples de auditar no case. A migração para ABAC está registrada no ADR-002.
-- Ordem de remoção (doc): DROP MASK antes de DROP FUNCTION, senão a tabela fica inacessível.
-- =====================================================================================================

-- Uma função por catálogo (rodar com :catalog = arvo_stg e depois arvo_prod)
USE CATALOG IDENTIFIER(:catalog);

CREATE OR REPLACE FUNCTION ops.mask_id_pessoa(id STRING)
RETURN CASE
  WHEN is_account_group_member('arvo-lgpd-acesso-pleno') THEN id
  ELSE concat('pseud_', substr(sha2(concat('arvo:', id), 256), 1, 16))
END
COMMENT 'Pseudonimiza identificador de pessoa (hash estável). Em claro só para arvo-lgpd-acesso-pleno.';

GRANT EXECUTE ON FUNCTION ops.mask_id_pessoa TO `account users`;

-- Aplicação (ADR-006, minimização): o identificador em claro só existe em bronze.sinistro_raw.
-- A F5 declara a máscara no próprio schema da streaming table do Lakeflow ("id_beneficiario STRING MASK ...").
-- A silver em diante guarda apenas id_beneficiario_hash (mesma fórmula acima), então não há o que mascarar lá.
-- O teste de plataforma (G4/G5) verifica, via information_schema, que toda coluna da lista tem máscara.
