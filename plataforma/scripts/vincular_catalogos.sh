#!/usr/bin/env bash
# F4 · Vínculo catálogo ↔ workspace (comandos da doc Databricks "catalogs/binding").
# Isolamento: prod só é visível no workspace de produção; dev e stg ficam no workspace de não-produção.
# Requer: metastore admin, dono do catálogo ou MANAGE. Rodado pelo grupo arvo-plataforma-admins, uma vez.
set -euo pipefail

: "${WS_NAO_PROD_ID:?defina o workspace_id de não-produção}"
: "${WS_PROD_ID:?defina o workspace_id de produção}"
PERFIL="${DATABRICKS_PROFILE:-DEFAULT}"

vincular () {  # catalogo workspace_id binding_type
  databricks catalogs update "$1" --isolation-mode ISOLATED --profile "$PERFIL"
  databricks workspace-bindings update-bindings catalog "$1" \
    --json "{\"add\": [{\"workspace_id\": $2, \"binding_type\": \"$3\"}], \"remove\": []}" --profile "$PERFIL"
  databricks workspace-bindings get-bindings catalog "$1" --profile "$PERFIL"
}

vincular arvo_dev  "$WS_NAO_PROD_ID" BINDING_TYPE_READ_WRITE
vincular arvo_stg  "$WS_NAO_PROD_ID" BINDING_TYPE_READ_WRITE
vincular arvo_prod "$WS_PROD_ID"     BINDING_TYPE_READ_WRITE
