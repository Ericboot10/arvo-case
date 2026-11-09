#!/bin/zsh
# Sobe os quatro arquivos do case para o workspace Free Edition (perfil arvo-free), sem alteração.
# Rodar da raiz do projeto, depois de `databricks bundle run platform_setup -t free`.
set -euo pipefail
P=(-p arvo-free)
V=dbfs:/Volumes/arvo_dev
for pasta in bronze/landing/sinistro bronze/landing/gabarito bronze/landing/inteligencias; do
  databricks fs mkdir "$V/$pasta" "${P[@]}"
done
databricks fs cp --overwrite data/case/sinistro-hospital-saorafael.csv              "$V/bronze/landing/sinistro/sinistro-hospital-saorafael.csv" "${P[@]}"
databricks fs cp --overwrite data/case/gabarito-auditoria.csv                       "$V/bronze/landing/gabarito/gabarito-auditoria.csv" "${P[@]}"
databricks fs cp --overwrite data/case/Inteligencias_apos_6_meses.xlsx              "$V/bronze/landing/inteligencias/Inteligencias_apos_6_meses.xlsx" "${P[@]}"
databricks fs cp --overwrite data/case/Contrato-parthenon-x-hospital-sao-rafael.pdf "$V/contracts/raw/Contrato-parthenon-x-hospital-sao-rafael.pdf" "${P[@]}"
echo "Arquivos do case no workspace:"
databricks fs ls "$V/bronze/landing/sinistro" "${P[@]}"
databricks fs ls "$V/bronze/landing/gabarito" "${P[@]}"
