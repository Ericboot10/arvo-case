# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Carregar a camada semântica no Unity Catalog
# MAGIC
# MAGIC Publica os YAMLs versionados em `semantic/` (a fonte da verdade, no Git) como tabelas Delta em
# MAGIC `<catalog>.semantic.*`, com comentários e tags. Assim o significado viaja junto com o dado e fica
# MAGIC disponível para SQL, dashboards, metric views e agentes (Genie).
# MAGIC
# MAGIC * **Idempotente:** sobrescreve as tabelas a cada execução. O histórico fica no Delta time travel e no Git.
# MAGIC * **Ambiente:** o widget `catalog` recebe `arvo_dev`, `arvo_stg` ou `arvo_prod`, preenchido pela variável do bundle no target.
# MAGIC * **Pré-requisito:** os testes `pytest semantic/tests` precisam passar no CI. Este notebook não carrega semântica inválida.

# COMMAND ----------

# MAGIC %pip install pyyaml==6.0.2

# COMMAND ----------

dbutils.widgets.text("catalog", "arvo_dev")
dbutils.widgets.text("semantic_dir", "..")  # relativo a este notebook dentro do Git folder
CATALOG = dbutils.widgets.get("catalog")
SEM_DIR = dbutils.widgets.get("semantic_dir")
assert CATALOG in {"arvo_dev", "arvo_stg", "arvo_prod"}, f"catálogo inesperado: {CATALOG}"

# COMMAND ----------

import os
import yaml
import pandas as pd


def load(name):
    with open(os.path.join(SEM_DIR, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


glossario = load("glossario.yaml")
dominios = load("dominios.yaml")
conceitos = load("conceitos.yaml")
mapa = load("map_tuss_conceito.yaml")
metricas = load("metricas.yaml")
perguntas = load("perguntas_negocio.yaml")
funil = load("funil.yaml")

VERSAO = glossario["versao"]
for doc in (dominios, conceitos, mapa, metricas, funil):
    assert doc["versao"] == VERSAO, "todos os artefatos semânticos devem compartilhar a mesma versão"

STATUS = glossario["status"]
if CATALOG == "arvo_prod":
    assert STATUS == "aprovado_G2", "prod só aceita semântica aprovada no Gate G2"

# COMMAND ----------

pai_de = {c["id"]: c["pai"] for c in conceitos["conceitos"]}


def raiz(cid):
    while pai_de.get(cid):
        cid = pai_de[cid]
    return cid


tabelas = {
    "dim_conceito": pd.DataFrame(
        [{"id": c["id"], "pai": c["pai"], "raiz": raiz(c["id"]), "definicao": c["definicao"],
          "observacao": c.get("observacao")} for c in conceitos["conceitos"]]),
    "dim_papel_contratual": pd.DataFrame(conceitos["papeis_contratuais"]),
    "map_tuss_conceito": pd.DataFrame(
        [{"cod_tuss": m["codigo"], "descricao_canonica": m["descricao_canonica"], "conceito": m["conceito"],
          "conceito_pai": raiz(m["conceito"]), "tipo_item_origem": m["tipo_item_origem"],
          "porte_sala": (m.get("atributos") or {}).get("porte_sala"),
          "vigencia_inicio": mapa["vigencia_inicio"]} for m in mapa["codigos"]]),
    "dim_dominio_valor": pd.DataFrame(
        [{"dominio": n, "coluna_origem": d["coluna_origem"], "valor_origem": m["valor_origem"],
          "canonico": m["canonico"]} for n, d in dominios["dominios"].items() for m in d["mapeamento_origem"]]),
    "dim_sinonimo": pd.DataFrame(
        [{"dominio": n, "canonico": k, "sinonimo": s} for n, d in dominios["dominios"].items()
         for k, lst in (d.get("sinonimos") or {}).items() for s in lst]),
    "glossario": pd.DataFrame(
        [{"id": t["id"], "termo": t["termo"], "definicao": " ".join(t["definicao"].split()), "fonte": t["fonte"],
          "dono": t["dono"], "status": t["status"], "sinonimos": t.get("sinonimos", []),
          "nao_confundir_com": t.get("nao_confundir_com", []), "pendencias": t.get("pendencias", [])}
         for t in glossario["termos"]]),
    "dim_metrica": pd.DataFrame(
        [{"id": m["id"], "nome": m["nome"], "definicao": " ".join(m["definicao"].split()), "formula": m["formula"],
          "tabela": m["tabela"], "unidade": m["unidade"], "dono": m["dono"],
          "disponibilidade": m["disponibilidade"], "dimensoes": m["dimensoes"]} for m in metricas["metricas"]]),
    "perguntas_negocio": pd.DataFrame(perguntas["perguntas"]),
    "funil_etapas": pd.DataFrame(funil["etapas"]),
    "funil_motivos": pd.DataFrame(funil["motivos"]),
    "regra_inteligencia": pd.DataFrame(funil["regra_inteligencia"]),
}

COMENTARIOS = {
    "dim_conceito": "Taxonomia universal de conceitos de negócio (independe de prestador). Fonte: semantic/conceitos.yaml",
    "dim_papel_contratual": "Papéis que um contrato pode atribuir a códigos (pacote, incluso, teto...). Valores por contrato vêm da F3.",
    "map_tuss_conceito": "Código TUSS -> conceito. Chave de negócio do item é o código, nunca a descrição.",
    "dim_dominio_valor": "Valor de origem -> valor canônico (caráter, regime, tipo_item). Valor desconhecido = quarentena.",
    "dim_sinonimo": "Sinônimos dos valores canônicos para busca/agentes. Não confundir regime PRONTO_SOCORRO com caráter URGENCIA_EMERGENCIA.",
    "glossario": "Glossário de negócio aprovado pelo comitê. Termos com status != aprovado não devem ser usados em regra.",
    "dim_metrica": "Definições de métricas de negócio (fonte das metric views).",
    "perguntas_negocio": "Perguntas de negócio = teste de aceite da semântica e benchmark do agente analítico.",
    "funil_etapas": "Etapas do ciclo de vida da glosa (base de gold.dim_etapa_funil)",
    "funil_motivos": "Motivos RET/REG/REC (base de gold.dim_motivo). Proposta pendente de AMB-19",
    "regra_inteligencia": "Ponte regra contratual × inteligência Arvo. Proposta pendente de AMB-17",
}

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.semantic COMMENT 'Camada semântica do projeto Arvo x Parthenon'")

for nome, pdf in tabelas.items():
    pdf = pdf.assign(versao_semantica=VERSAO, status_semantica=STATUS)
    fqn = f"{CATALOG}.semantic.{nome}"
    (spark.createDataFrame(pdf).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn))
    spark.sql(f"COMMENT ON TABLE {fqn} IS '{COMENTARIOS[nome]}'")
    spark.sql(f"ALTER TABLE {fqn} SET TAGS ('camada' = 'semantic', 'versao_semantica' = '{VERSAO}', 'status' = '{STATUS}')")
    print(f"{fqn}: {len(pdf)} linhas")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Checagem pós-carga
# MAGIC Repete no Databricks o teste de aderência mais importante: todo código da silver precisa ter conceito.
# MAGIC Só roda se a silver já existir (F5).

# COMMAND ----------

if spark.catalog.tableExists(f"{CATALOG}.silver.item_conta"):
    sem_conceito = spark.sql(f"""
        SELECT s.cod_tuss, COUNT(*) AS itens
        FROM {CATALOG}.silver.item_conta s
        LEFT ANTI JOIN {CATALOG}.semantic.map_tuss_conceito m USING (cod_tuss)
        GROUP BY s.cod_tuss
    """)
    assert sem_conceito.count() == 0, f"códigos sem conceito: {sem_conceito.collect()}"
    print("aderência semântica: 100% dos códigos mapeados")
else:
    print("silver.item_conta ainda não existe (F5): checagem pulada")
