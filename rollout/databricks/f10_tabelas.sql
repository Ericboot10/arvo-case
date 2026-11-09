-- =====================================================================================================
-- F10 · Estado do rollout e destino de cada apontamento. Rodar com :catalog (arvo_dev | arvo_stg | arvo_prod).
-- O estado VIGENTE nasce de rollout/estado_regras.yaml (versionado e aprovado); esta tabela é a cópia SCD2 dele.
-- =====================================================================================================
USE CATALOG IDENTIFIER(:catalog);

CREATE TABLE IF NOT EXISTS ops.rollout_estado_regra (
  regra_principal STRING NOT NULL,
  estagio         STRING NOT NULL COMMENT 'DESLIGADA | SHADOW | CANARIO | AUTOMATICO',
  precisao_inf    DOUBLE COMMENT 'Limite inferior do IC 95% da precisão auditada que sustenta o estágio',
  teto_valor      DECIMAL(14,2) COMMENT 'Teto do envio automático (matriz de custo, AMB-20)',
  motivo          STRING,
  aprovado_por    ARRAY<STRING> COMMENT 'Aprovadores humanos, ou automatico:<indicador> num rebaixamento',
  vigente_desde   DATE NOT NULL,
  vigente_ate     DATE,
  vigente         BOOLEAN NOT NULL
) COMMENT 'F10 · estágio de cada regra ao longo do tempo (SCD2). Fonte: rollout/estado_regras.yaml';

CREATE TABLE IF NOT EXISTS ops.rollout_destino (
  id_apontamento  STRING NOT NULL,
  id_item         STRING NOT NULL,
  id_conta        STRING,
  run_id          STRING NOT NULL,
  regra_principal STRING,
  vl_glosado      DECIMAL(14,2),
  estagio_regra   STRING NOT NULL,
  teto_valor      DOUBLE,
  destino_envio   STRING NOT NULL COMMENT 'BLOQUEADO | NAO_ENVIAR | REVISAO_HUMANA | ENVIO_AUTOMATICO',
  motivo_destino  STRING,
  decidido_em     TIMESTAMP NOT NULL
) COMMENT 'F10 · para onde cada apontamento foi e por quê (rollout/envio.py)';
