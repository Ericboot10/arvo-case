-- =====================================================================================================
-- F4 · Databricks Free Edition: só o catálogo de DEV (uma conta, um workspace, sem account console).
-- Mesmo desenho de 00_catalogos_schemas.sql, recortado: stg e prod pedem workspaces e service principals separados.
-- Se a Free Edition recusar CREATE CATALOG, rode o restante com o catálogo padrão do workspace (ver docs/databricks-free-edition.md).
-- =====================================================================================================
CREATE CATALOG IF NOT EXISTS arvo_dev;
-- Na Free Edition este catálogo guarda os DADOS DO CASE (arquivos fornecidos pela Arvo, sem alteração). Nenhum dado gerado.
COMMENT ON CATALOG arvo_dev IS 'DADOS DO CASE Arvo: sinistro do Hospital São Rafael (jun/2025), gabarito de auditoria, contrato PRT-2025-0417 e planilha de inteligências. Nenhum dado gerado ou simulado.';
ALTER CATALOG arvo_dev SET TAGS ('origem_dado' = 'case_arvo');

CREATE SCHEMA IF NOT EXISTS arvo_dev.bronze     COMMENT 'Ingestão bruta, fiel aos arquivos do case';
CREATE SCHEMA IF NOT EXISTS arvo_dev.silver     COMMENT 'Silver de desenvolvimento';
CREATE SCHEMA IF NOT EXISTS arvo_dev.gold       COMMENT 'Gold de desenvolvimento';
CREATE SCHEMA IF NOT EXISTS arvo_dev.semantic   COMMENT 'Camada semântica (F2)';
CREATE SCHEMA IF NOT EXISTS arvo_dev.contracts  COMMENT 'Contratos como dado (F3)';
CREATE SCHEMA IF NOT EXISTS arvo_dev.ops        COMMENT 'Telemetria e operação';
CREATE SCHEMA IF NOT EXISTS arvo_dev.quarantine COMMENT 'Registros reprovados nas expectations';
CREATE SCHEMA IF NOT EXISTS arvo_dev.sandbox    COMMENT 'Experimentos individuais; descartável';

CREATE VOLUME IF NOT EXISTS arvo_dev.bronze.landing     COMMENT 'Arquivos do case: sinistro/, gabarito/ e inteligencias/';
CREATE VOLUME IF NOT EXISTS arvo_dev.contracts.raw      COMMENT 'PDFs de contrato';
CREATE VOLUME IF NOT EXISTS arvo_dev.contracts.revisao  COMMENT 'Pacotes de revisão da F3';
