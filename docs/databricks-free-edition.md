# Rodar o projeto na Databricks Free Edition

O workspace Databricks é sempre **na nuvem**: não existe versão que rode na sua máquina. Na sua máquina ficam o código, a CLI e o deploy. Localmente, o harness com Spark continua rodando tudo (`python -m arvo.deliverables.rodar_tudo`).

A **Free Edition** é gratuita e serverless. Ela comporta o ambiente de **dev**. Aqui ele roda com os **arquivos do case**, sem alteração e marcados como dado do case. Num dev corporativo, com PHI real, o desenho manda usar sintético (ADR-002, alvo `dev`). Stg e prod ficam como especificados, porque exigem account console, service principals e workspaces separados, que a Free Edition não oferece.

Fonte: documentação da Databricks consultada em 07/11/2026 ([Free Edition](https://docs.databricks.com/aws/en/getting-started/free-edition), [limitações](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations), [CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install), [autenticação](https://docs.databricks.com/aws/en/dev-tools/cli/authentication)).

## 1. Criar a conta e o workspace (você, no navegador)
1. Abra https://login.databricks.com/?dbx_source=docs&intent=CE_SIGN_UP
2. Entre com e-mail, Google ou Microsoft. A Databricks cria o workspace sozinha.
3. Copie a URL do workspace que abrir (algo como `https://dbc-xxxxxxxx-xxxx.cloud.databricks.com`).

## 2. Instalar a CLI (Terminal do Mac)
```bash
brew tap databricks/tap
```
```bash
brew trust databricks/tap
```
```bash
brew install databricks
```
```bash
databricks -v
```
A versão precisa ser 0.279.0 ou maior, por causa dos alertas SQL do bundle.

## 3. Autenticar a CLI no seu workspace
```bash
databricks auth login --host https://SEU-WORKSPACE.cloud.databricks.com --profile arvo-free
```
Abre o navegador para você entrar. O perfil `arvo-free` fica em `~/.databrickscfg`, e o token no Keychain. O bundle usa esse perfil no alvo `free`.

## 4. Conferir o SQL warehouse
```bash
databricks warehouses list -p arvo-free
```
O bundle procura um warehouse chamado **"Serverless Starter Warehouse"**. Se o seu tiver outro nome, troque o `lookup` do alvo `free` em `databricks.yml`.

## 5. Validar e publicar o bundle
Na pasta do projeto:
```bash
databricks bundle validate -t free
```
```bash
databricks bundle deploy -t free
```

## 6. Preparar o ambiente
Este passo cria o catálogo `arvo_dev`, os schemas e os volumes. O catálogo fica marcado como **dados do case**: comentário e tag `origem_dado = case_arvo`.
```bash
databricks bundle run platform_setup -t free
```
No primeiro deploy, o pipeline e o job `medallion_run` falham com `CATALOG_DOES_NOT_EXIST`. O pipeline exige que o catálogo já exista, e quem o cria é este job. Depois que ele terminar, rode `databricks bundle deploy -t free` de novo.

## 7. Subir os quatro arquivos do case, sem alteração
Sinistro, gabarito, planilha e contrato vão para os volumes. Nada é gerado ou simulado.
```bash
./plataforma/subir_dados_case.sh
```
O script usa sempre `-p arvo-free`. Sem o perfil, dentro da pasta do projeto, a CLI tenta o alvo `dev`, que ainda tem o endereço `DEFINIR-*`.

## 8. Rodar as fases, nesta ordem
```bash
databricks bundle run semantic_load -t free
```
```bash
databricks bundle run medallion_run -t free
```
```bash
databricks bundle run evaluation_run -t free
```
```bash
databricks bundle run monitoring_refresh -t free
```
```bash
databricks bundle run rollout_decide -t free
```
- **F2:** carrega a semântica e o contrato revisado, que o pipeline usa.
- **F5:** roda o medalhão e o motor de regras sobre o sinistro do case.
- **F8:** carrega o gabarito e calcula precisão e recall, com IC 95% de Wilson. Também grava a auditoria rodada 0.
- **F9:** cria as metric views e a view de status, e roda o portão de envio.
- **F10:** decide o destino de cada apontamento.
- **F3 (extração do contrato por IA):** **não roda aqui**. No alvo `free` ela está em modo `real`, e sem chave de provedor não há o que rodar. O modo simulado (respostas gravadas) fica para os testes locais, para não pôr telemetria inventada no workspace.

Se o sinistro mudar depois de já ter sido ingerido, reprocesse do zero:
```bash
databricks bundle run medallion -t free --full-refresh-all
```
A bronze é append-only.

## 9. Ver o resultado
- **Painel** "arvo-monitoring-free", em Dashboards:
  - Negócio;
  - **Precisão e recall**;
  - Semântica e dados;
  - IA;
  - Visão geral.
- **Tabelas:**
  - `arvo_dev.gold.fato_apontamento`;
  - `arvo_dev.ops.v_precisao_recall`;
  - `arvo_dev.gold.v_avaliacao_gabarito`, com TP, FP, FN e TN por item;
  - `arvo_dev.ops.v_sanidade_status`.
- **Alertas:** os 35 alertas de sanidade, em Alerts. No modo development as agendas ficam **pausadas**.

## Limites da Free Edition que afetam o projeto
| Limite | Efeito aqui |
|---|---|
| Só compute serverless | Ok: o bundle já usa serverless |
| 1 SQL warehouse 2X-Small | Painel e alertas usam esse warehouse |
| 1 pipeline ativo por tipo | Ok: há um pipeline (F5) |
| 5 tarefas de job simultâneas por conta | Rode as fases uma de cada vez, como no passo 8 |
| Cota diária de compute | Se estourar, o compute para até o dia seguinte |
| Sem account console, SSO, SCIM ou rede privada | Grants por grupo, binding ISOLATED e service principals de stg e prod ficam como especificados |
| Saída de internet só para domínios confiáveis | Provedores de IA externos podem não ser alcançáveis: a F3 fica em modo simulado |

## Desfazer
```bash
databricks bundle destroy -t free
```
Remove jobs, pipeline, painel e alertas publicados pelo bundle. O catálogo e os dados continuam até você removê-los.

## O que já foi validado neste workspace (09/11/2026)
Todos os jobs rodaram com sucesso sobre os **dados do case**: preparação, F2, F5 (pipeline e motor), F8, F9 e F10. Os números são os mesmos da execução local ([`deliverables/`](../deliverables/)):

| | Workspace | Entrega local |
|---|---|---|
| Itens do sinistro (bronze → silver, quarentena) | 1.696 → 1.696, 0 | 1.696 |
| Apontamentos e glosa | 369 · R$ 121.948,93 | 369 · R$ 121.948,93 |
| Precisão (IC 95%) | 94,4% [89,3% – 97,1%] | 94,4% [89,3% – 97,1%] |
| Recall (IC 95%) | 90,0% [84,2% – 93,8%] | 90,0% [84,2% – 93,8%] |
| TP · FP · FN · TN | 135 · 8 · 15 · 105 | 135 · 8 · 15 · 105 |
| Índice-norte (planilha) | 0,48% do sinistro | 0,48% |

Os 369 apontamentos ficam em `NAO_ENVIAR`, porque as regras estão em SHADOW. Nenhuma regra atinge o piso de 95% no limite inferior do IC: o indicador S06 está em alerta, como na avaliação local.

Antes desta carga, o workspace tinha rodado com um sinistro sintético e a F3 simulada. Esses arquivos e as linhas que geraram foram apagados, e o pipeline foi reprocessado do zero.

Correções que o workspace real exigiu:
| Erro | Causa | Correção |
|---|---|---|
| Mesmo nome no pipeline e no job da F5 | Chaves de recurso precisam ser únicas no bundle | Pipeline renomeado para `medallion` |
| `expected a file … got a notebook` | O código do pipeline tem cabeçalho de notebook | Biblioteca declarada como `notebook` |
| `Catalog 'arvo_dev' does not exist` | O pipeline exige o catálogo no deploy | Rodar a preparação e publicar de novo |
| `Permission denied: '/local_disk0/tmp'` (F3) | No serverless esse disco não é gravável | Pasta temporária do sistema |
| `tableExists is not whitelisted` (F5) | O Lakeflow serverless bloqueia essa chamada | Leitura protegida com try/except |
| `'NoneType' object is not subscriptable` (F5) | `.first()` dentro do pipeline lê a dimensão antes de ela existir | Join de uma linha no lugar da leitura imediata |
| `Table … is already managed by pipeline <id>` (F5) | Ao renomear a chave do pipeline no bundle, o deploy apaga o pipeline antigo e cria outro, mas as tabelas continuam presas ao id antigo | Apagar as tabelas do pipeline (`DROP MATERIALIZED VIEW`, e `DROP TABLE` na bronze) e rodar `medallion_run` de novo; elas são reconstruídas a partir do volume |
