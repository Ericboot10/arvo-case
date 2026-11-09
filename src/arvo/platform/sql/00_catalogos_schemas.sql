-- =====================================================================================================
-- F4 · 00 · Catálogos por ambiente e schemas (executado UMA vez pelo grupo arvo-plataforma-admins)
--
-- Base (Unity Catalog best practices): o catálogo é a unidade primária de isolamento e costuma representar um
-- ambiente. Um metastore por região serve dev, stg e prod. Usar tabelas managed. Ownership de produção fica com grupos.
-- Decisão: ADR-001 (src/arvo/platform/ADRs.md).
--
-- Mesmos schemas nos três ambientes: "silver de dev", "gold de dev" etc. são arvo_dev.silver, arvo_dev.gold.
--   bronze      ingestão bruta, append-only, fiel à origem (F5)
--   silver      tipado, validado e enriquecido com a semântica (F5)
--   gold        fatos e apontamentos de negócio (F5/F6)
--   semantic    glossário, conceitos, mapas e metric views (F2)
--   contracts   contratos como dado: parâmetros aprovados (F3)
--   ops         telemetria de IA, estado de pipelines, checagens de plataforma
--   quarantine  registros reprovados nas expectations, com motivo (F5)
-- Só em dev:  sandbox      experimentos individuais, descartáveis
-- Só em prod: gold_shadow  saída do agente em modo sombra: lê dado real e NÃO envia ao cliente (F10)
-- =====================================================================================================

-- MANAGED LOCATION: defina o storage de cada catálogo conforme a conta. Prod em storage separado.
CREATE CATALOG IF NOT EXISTS arvo_dev  COMMENT 'Desenvolvimento: dados SINTÉTICOS ou anonimizados. Nunca PHI real (ADR-002).';
CREATE CATALOG IF NOT EXISTS arvo_stg  COMMENT 'Homologação: cópia mascarada de prod e golden datasets congelados. Escrita só pelo SP de stg.';
CREATE CATALOG IF NOT EXISTS arvo_prod COMMENT 'Produção: dados reais. Escrita só pelo SP de prod. Catálogo ISOLATED, vinculado ao workspace de prod.';

-- ---------------------------------------------------------------- arvo_dev
CREATE SCHEMA IF NOT EXISTS arvo_dev.bronze     COMMENT 'Ingestão bruta (sintética em dev)';
CREATE SCHEMA IF NOT EXISTS arvo_dev.silver     COMMENT 'Silver de desenvolvimento';
CREATE SCHEMA IF NOT EXISTS arvo_dev.gold       COMMENT 'Gold de desenvolvimento';
CREATE SCHEMA IF NOT EXISTS arvo_dev.semantic   COMMENT 'Camada semântica (F2)';
CREATE SCHEMA IF NOT EXISTS arvo_dev.contracts  COMMENT 'Contratos como dado (F3)';
CREATE SCHEMA IF NOT EXISTS arvo_dev.ops        COMMENT 'Telemetria e operação';
CREATE SCHEMA IF NOT EXISTS arvo_dev.quarantine COMMENT 'Registros reprovados nas expectations';
CREATE SCHEMA IF NOT EXISTS arvo_dev.sandbox    COMMENT 'Experimentos individuais; descartável';

-- ---------------------------------------------------------------- arvo_stg
CREATE SCHEMA IF NOT EXISTS arvo_stg.bronze     COMMENT 'Ingestão bruta (cópia mascarada)';
CREATE SCHEMA IF NOT EXISTS arvo_stg.silver     COMMENT 'Silver de homologação';
CREATE SCHEMA IF NOT EXISTS arvo_stg.gold       COMMENT 'Gold de homologação';
CREATE SCHEMA IF NOT EXISTS arvo_stg.semantic   COMMENT 'Camada semântica (F2)';
CREATE SCHEMA IF NOT EXISTS arvo_stg.contracts  COMMENT 'Contratos como dado (F3)';
CREATE SCHEMA IF NOT EXISTS arvo_stg.ops        COMMENT 'Telemetria e operação';
CREATE SCHEMA IF NOT EXISTS arvo_stg.quarantine COMMENT 'Registros reprovados nas expectations';

-- ---------------------------------------------------------------- arvo_prod
CREATE SCHEMA IF NOT EXISTS arvo_prod.bronze      COMMENT 'Ingestão bruta de produção';
CREATE SCHEMA IF NOT EXISTS arvo_prod.silver      COMMENT 'Silver de produção';
CREATE SCHEMA IF NOT EXISTS arvo_prod.gold        COMMENT 'Gold de produção';
CREATE SCHEMA IF NOT EXISTS arvo_prod.gold_shadow COMMENT 'Modo sombra (F10): apontamentos NÃO enviados ao cliente';
CREATE SCHEMA IF NOT EXISTS arvo_prod.semantic    COMMENT 'Camada semântica aprovada (G2)';
CREATE SCHEMA IF NOT EXISTS arvo_prod.contracts   COMMENT 'Contratos aprovados pelo Jurídico (G3)';
CREATE SCHEMA IF NOT EXISTS arvo_prod.ops         COMMENT 'Telemetria e operação';
CREATE SCHEMA IF NOT EXISTS arvo_prod.quarantine  COMMENT 'Registros reprovados nas expectations';

-- ---------------------------------------------------------------- volumes (arquivos não tabulares)
CREATE VOLUME IF NOT EXISTS arvo_dev.bronze.landing     COMMENT 'Arquivos de sinistro SINTÉTICOS';
CREATE VOLUME IF NOT EXISTS arvo_dev.contracts.raw      COMMENT 'PDFs de contrato';
CREATE VOLUME IF NOT EXISTS arvo_dev.contracts.revisao  COMMENT 'Pacotes de revisão da F3';
CREATE VOLUME IF NOT EXISTS arvo_stg.bronze.landing     COMMENT 'Arquivos de sinistro mascarados';
CREATE VOLUME IF NOT EXISTS arvo_stg.contracts.raw      COMMENT 'PDFs de contrato';
CREATE VOLUME IF NOT EXISTS arvo_stg.contracts.revisao  COMMENT 'Pacotes de revisão da F3';
CREATE VOLUME IF NOT EXISTS arvo_prod.bronze.landing    COMMENT 'Arquivos de sinistro reais (TI da Parthenon)';
CREATE VOLUME IF NOT EXISTS arvo_prod.contracts.raw     COMMENT 'PDFs de contrato';
CREATE VOLUME IF NOT EXISTS arvo_prod.contracts.revisao COMMENT 'Pacotes de revisão e aprovações assinadas';

ALTER CATALOG arvo_dev  SET TAGS ('ambiente' = 'dev',  'dados' = 'sinteticos');
ALTER CATALOG arvo_stg  SET TAGS ('ambiente' = 'stg',  'dados' = 'mascarados');
ALTER CATALOG arvo_prod SET TAGS ('ambiente' = 'prod', 'dados' = 'reais_lgpd_sensivel');
