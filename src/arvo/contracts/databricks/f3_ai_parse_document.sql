-- =====================================================================================================
-- F3 · Parser alternativo: Databricks AI Functions `ai_parse_document`
--
-- Papel: segundo DocumentParserPort, independente do pdfplumber, para contratos escaneados ou com layout complexo.
-- A doc Databricks descreve: "Parse structured content (text, tables, figure descriptions) and layout from
-- unstructured documents". Requer DBR 15.4 LTS+ (18.2 recomendado). Não disponível em Classic SQL warehouse.
-- Custo: system.billing.usage com billing_origin_product = 'AI_FUNCTIONS'.
--
-- VALIDAR NO WORKSPACE antes de usar: o formato exato do VARIANT de saída (elementos, páginas, tabelas)
-- não foi verificado neste case. O adapter Python correspondente (DocumentParserPort) só deve ser escrito depois disso.
-- =====================================================================================================
USE CATALOG IDENTIFIER(:catalog);

CREATE OR REPLACE TABLE contracts.contract_parsed_ai AS
SELECT
  path,
  sha2(content, 256) AS documento_sha256,
  ai_parse_document(content) AS parsed
FROM read_files('/Volumes/arvo_dev/contracts/raw/', format => 'binaryFile');  -- caminho literal: ajuste por ambiente

-- Inspeção rápida da estrutura retornada (passo 1 da validação)
-- SELECT path, schema_of_variant(parsed) FROM contracts.contract_parsed_ai;
