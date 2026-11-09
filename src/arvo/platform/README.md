# F4: plataforma e ambientes

> **Status:** especificado e testado de forma estática (16 testes locais). **Ainda não provisionado:** não há workspace nem CLI do Databricks nesta máquina. O Gate G4 só fecha depois que o job `platform_smoke_test` passar em dev, stg e prod.

## Topologia

```
                metastore (1 por região)
     ┌──────────────────┼──────────────────────────┐
  arvo_dev            arvo_stg                   arvo_prod          ← catálogo = ambiente (UC best practice)
  sintéticos          mascarados + golden        reais (LGPD)
  └─ workspace NÃO-PROD (dev + stg) ─┘           └─ workspace PROD (catálogo ISOLATED, binding exclusivo)

  schemas em todos: bronze · silver · gold · semantic · contracts · ops · quarantine
  + dev: sandbox          + prod: gold_shadow (modo sombra da F10)
```

| | dev | stg | prod |
|---|---|---|---|
| Bundle `mode` | development (recursos prefixados por usuário, agendas pausadas) | production | production |
| Quem executa | o próprio dev | `sp-arvo-stg` | `sp-arvo-prod` |
| Quem escreve no catálogo | engenharia, analytics | **só o SP** | **só o SP** |
| Dados | **sintéticos rotulados** | cópia mascarada + golden sets | reais, com `id_beneficiario` mascarado |
| IA (F3) | `simulado` | `real` | `real` |
| Deploy | manual (`bundle deploy -t dev`) | automático no merge em `main` | manual, com **aprovação** no environment `prod` |

## Arquivos

| Arquivo | O que faz |
|---|---|
| [`../databricks.yml`](../../../databricks.yml) | Bundle: targets dev/stg/prod, `run_as` service principal, permissões, branch `main`, `sync.exclude` que impede o dado real do case de subir |
| [`../resources/jobs/`](../../../resources/jobs/) | Jobs `platform_smoke_test` (G4), `semantic_load` e `contracts_extract`. O `platform_synthetic_data` só existe no alvo `dev` (`databricks.yml`) |
| [`sql/00_catalogos_schemas.sql`](sql/00_catalogos_schemas.sql) | Catálogos, schemas do medalhão, volumes e tags de ambiente |
| [`sql/01_grants.sql`](sql/01_grants.sql) | Menor privilégio: ownership por grupo, MODIFY em stg/prod só para SP, sem ALL PRIVILEGES, BROWSE para todos |
| [`sql/02_mascaras_lgpd.sql`](sql/02_mascaras_lgpd.sql) + [`lgpd/colunas_sensiveis.yaml`](lgpd/colunas_sensiveis.yaml) | Pseudonimização estável de `id_beneficiario` e o registro das colunas sensíveis que a F5 precisa mascarar |
| [`scripts/vincular_catalogos.sh`](scripts/vincular_catalogos.sh) | Catálogos ISOLATED e workspace bindings (CLI, conforme a doc) |
| [`notebooks/00_hello_ambiente.py`](notebooks/00_hello_ambiente.py) | **G4:** verifica catálogo, schemas, execução por SP, máscara, tags e escrita em `ops`, e grava a evidência em `ops.plataforma_checks` |
| [`notebooks/executar_sql.py`](notebooks/executar_sql.py) + [`sqlutil.py`](sqlutil.py) | Roda os `.sql` do repositório com `:catalog` via `spark.sql(args=…)`, respeitando os blocos `$$` |
| [`sinteticos/gerar_sinistro_sintetico.py`](sinteticos/gerar_sinistro_sintetico.py) | Sinistro sintético **rotulado por construção**, no formato idêntico ao real |
| [`../.github/workflows/ci.yml`](../../../.github/workflows/ci.yml) | Testes → `bundle validate` → deploy stg + hello → prod com aprovação. Autenticação **OIDC**, sem token guardado |

## Dados sintéticos (dev)
`python -m arvo.platform.sinteticos.gerar_sinistro_sintetico` gera em `outputs/synthetic_data/` (semente 42): 410 contas e 2.405 itens.

**Violações injetadas (verdade conhecida):**

| Rótulo | Itens |
|---|---|
| R1 preço acima do teto | 217 |
| R2 sala em pacote | 78 |
| R3 material de rotina em pacote | 141 |
| R4 urgência em eletivo | 40 |

Glosa esperada: **R$ 134.480,97**.

**Casos de borda semântica:**

| Caso | Itens |
|---|---|
| AMB-01: PS com caráter Eletivo e taxa de urgência | 6 |
| AMB-02: fragmentação de conta | 10 |
| AMB-04: taxa de sala sem pacote | 15 |

**Erros de qualidade para as expectations da F5:** código inválido, caráter novo ("Emergência", AMB-07), total inconsistente, id duplicado e quantidade zero.

**Garantias testadas:**
- mesmas colunas e formatos do arquivo real (decimal mínimo com vírgula, data por extenso, BOM);
- IDs que nunca colidem com os reais;
- reprodutível byte a byte;
- os rótulos conferem com uma aplicação independente e literal das cláusulas.

## ADRs

**ADR-001: catálogo por ambiente, prod isolado.**
- **Contexto:** dado de saúde e times diferentes por ambiente.
- **Decisão:** um catálogo por ambiente no mesmo metastore. `arvo_prod` ISOLATED e vinculado só ao workspace de prod. Ownership com o grupo `arvo-plataforma-admins`.
- **Consequência:** "silver de dev" é `arvo_dev.silver`. O código é igual nos três ambientes e só muda `${var.catalog}`.

**ADR-002: dev só com dado sintético. Identificador pseudonimizado em stg e prod.**
- **Contexto:** LGPD (dado de saúde vinculado a pessoa é sensível) e o gabarito real é ruidoso.
- **Decisão:**
  - gerador sintético rotulado para dev;
  - `sync.exclude` impede que os arquivos do case subam para o workspace;
  - máscara de coluna com hash estável em stg e prod;
  - o sinistro nunca vai para LLM externo.
- **Evolução:** migrar as máscaras para ABAC (políticas por tag), que é a recomendação da doc para consistência entre muitas tabelas.

**ADR-003: código promove, dado não promove.**
- **Decisão:** a promoção acontece por bundle (`-t dev|stg|prod`) via CI. Parâmetros de contrato e semântica promovem como artefatos **aprovados** (G2/G3), nunca por cópia de tabela entre catálogos.
- **Consequência:** prod só recebe o que passou por testes, `validate`, stg e aprovação humana.

**ADR-004: SQL do repositório executado por notebook.**
- **Decisão:** um executor único com `spark.sql(cmd, args={"catalog": ...})`.
- **Motivo:** o mesmo `.sql` roda no SQL editor (`:catalog`) e em Job serverless. Isso evita depender de warehouse e de uma sintaxe de parâmetro diferente na task de SQL, que não foi confirmada na doc.

## Gate G4: checklist
- [ ] Grupos e SPs criados na conta (SCIM): `arvo-plataforma-admins`, `arvo-engenharia`, `arvo-analytics`, `arvo-auditoria-medica`, `arvo-juridico`, `arvo-negocio-leitura`, `arvo-lgpd-acesso-pleno`, `sp-arvo-stg`, `sp-arvo-prod`
- [ ] `00_catalogos_schemas.sql` e `01_grants.sql` executados por um admin. Depois `02_mascaras_lgpd.sql` com `:catalog` = `arvo_stg` e `arvo_prod`
- [ ] `vincular_catalogos.sh` executado: prod ISOLATED
- [ ] `DEFINIR_*` preenchidos em `databricks.yml` (hosts e application IDs)
- [ ] Federation policies OIDC por SP e environments `stg`/`prod` no GitHub (prod com required reviewers)
- [ ] `databricks bundle validate -t dev|stg|prod` verde
- [ ] Job `platform_smoke_test` verde nos três alvos, com evidência em `<catalog>.ops.plataforma_checks`
- [ ] Teste negativo: um usuário humano tenta `INSERT` em `arvo_prod.gold` e **falha**

## Rodar os testes locais
```bash
pytest tests/platform -v
```
