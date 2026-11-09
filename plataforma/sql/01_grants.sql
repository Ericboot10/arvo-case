-- =====================================================================================================
-- F4 · 01 · Permissões por ambiente (menor privilégio)
--
-- Pré-requisito: grupos e service principals criados NA CONTA (SCIM / identity management), não no workspace.
--   Grupos:  arvo-plataforma-admins, arvo-engenharia, arvo-analytics, arvo-auditoria-medica, arvo-juridico,
--            arvo-negocio-leitura, arvo-lgpd-acesso-pleno
--   SPs:     sp-arvo-stg, sp-arvo-prod   (o nome aqui é o display name; ajuste para o application ID se preferir)
--
-- Regras (UC best practices + comitê):
--   * ownership de stg e prod com grupo, nunca com pessoa;
--   * MODIFY em stg e prod SÓ para service principals: ninguém escreve em produção na mão;
--   * nunca ALL PRIVILEGES;
--   * BROWSE para "account users", para que todos vejam que o ativo existe sem ler o dado.
-- =====================================================================================================

-- ---------------------------------------------------------------- ownership
ALTER CATALOG arvo_dev  OWNER TO `arvo-plataforma-admins`;
ALTER CATALOG arvo_stg  OWNER TO `arvo-plataforma-admins`;
ALTER CATALOG arvo_prod OWNER TO `arvo-plataforma-admins`;

GRANT BROWSE ON CATALOG arvo_dev  TO `account users`;
GRANT BROWSE ON CATALOG arvo_stg  TO `account users`;
GRANT BROWSE ON CATALOG arvo_prod TO `account users`;

-- ---------------------------------------------------------------- arvo_dev: o time constrói (dados sintéticos)
GRANT USE CATALOG, USE SCHEMA, SELECT, MODIFY, CREATE TABLE, CREATE FUNCTION, CREATE VOLUME, CREATE MODEL,
      READ VOLUME, WRITE VOLUME, EXECUTE ON CATALOG arvo_dev TO `arvo-engenharia`;
GRANT USE CATALOG, USE SCHEMA, SELECT, MODIFY, CREATE TABLE, CREATE FUNCTION, EXECUTE
      ON CATALOG arvo_dev TO `arvo-analytics`;
GRANT USE CATALOG, USE SCHEMA, SELECT, READ VOLUME ON CATALOG arvo_dev TO `arvo-auditoria-medica`;
GRANT USE CATALOG, USE SCHEMA, SELECT, READ VOLUME ON CATALOG arvo_dev TO `arvo-juridico`;

-- ---------------------------------------------------------------- arvo_stg: só o SP de stg escreve
GRANT USE CATALOG, USE SCHEMA, SELECT, MODIFY, CREATE TABLE, CREATE FUNCTION, CREATE VOLUME, CREATE MODEL,
      READ VOLUME, WRITE VOLUME, EXECUTE ON CATALOG arvo_stg TO `sp-arvo-stg`;
GRANT USE CATALOG, USE SCHEMA, SELECT, READ VOLUME, EXECUTE ON CATALOG arvo_stg TO `arvo-engenharia`;
GRANT USE CATALOG, USE SCHEMA, SELECT, EXECUTE ON CATALOG arvo_stg TO `arvo-analytics`;
GRANT USE CATALOG, USE SCHEMA, SELECT, READ VOLUME ON CATALOG arvo_stg TO `arvo-auditoria-medica`;
GRANT USE CATALOG, USE SCHEMA, SELECT, READ VOLUME ON CATALOG arvo_stg TO `arvo-juridico`;

-- ---------------------------------------------------------------- arvo_prod: só o SP de prod escreve
GRANT USE CATALOG, USE SCHEMA, SELECT, MODIFY, CREATE TABLE, CREATE FUNCTION, CREATE VOLUME, CREATE MODEL,
      READ VOLUME, WRITE VOLUME, EXECUTE ON CATALOG arvo_prod TO `sp-arvo-prod`;
-- engenharia: diagnóstico de operação, sem acesso a bronze/silver (onde o identificador ainda está em claro)
GRANT USE CATALOG ON CATALOG arvo_prod TO `arvo-engenharia`;
GRANT USE SCHEMA, SELECT ON SCHEMA arvo_prod.ops        TO `arvo-engenharia`;
GRANT USE SCHEMA, SELECT ON SCHEMA arvo_prod.quarantine TO `arvo-engenharia`;
-- auditoria médica e jurídico: decisão de glosa e contrato
GRANT USE CATALOG ON CATALOG arvo_prod TO `arvo-auditoria-medica`;
GRANT USE SCHEMA, SELECT ON SCHEMA arvo_prod.gold        TO `arvo-auditoria-medica`;
GRANT USE SCHEMA, SELECT ON SCHEMA arvo_prod.gold_shadow TO `arvo-auditoria-medica`;
GRANT USE SCHEMA, SELECT ON SCHEMA arvo_prod.semantic    TO `arvo-auditoria-medica`;
GRANT USE CATALOG ON CATALOG arvo_prod TO `arvo-juridico`;
GRANT USE SCHEMA, SELECT ON SCHEMA arvo_prod.contracts TO `arvo-juridico`;
GRANT USE SCHEMA, SELECT ON SCHEMA arvo_prod.gold      TO `arvo-juridico`;
GRANT READ VOLUME, WRITE VOLUME ON VOLUME arvo_prod.contracts.revisao TO `arvo-juridico`;  -- devolve aprovacao.yaml assinado
-- negócio (Paulo, Alana): só a camada semântica (metric views) e gold, sem identificador de pessoa
GRANT USE CATALOG ON CATALOG arvo_prod TO `arvo-negocio-leitura`;
GRANT USE SCHEMA, SELECT ON SCHEMA arvo_prod.semantic TO `arvo-negocio-leitura`;
GRANT USE SCHEMA, SELECT ON SCHEMA arvo_prod.gold     TO `arvo-negocio-leitura`;
