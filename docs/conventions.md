# Convenções do projeto

Padrão de nomes e de estrutura, para que qualquer engenheiro encontre, rode e estenda o projeto sem perguntar. A documentação e o conteúdo de negócio ficam em português; nomes de pastas, pacotes e recursos do Databricks ficam em inglês.

## Estrutura do repositório

```
arvo-case/
├── README.md                 visão geral, resultado e como rodar
├── pyproject.toml            pacote `arvo` (layout src) e dependências: pip install -e ".[dev,agents]"
├── databricks.yml            bundle: alvos dev, free, stg, prod
├── resources/                recursos do bundle, um arquivo por domínio
│   ├── jobs/<domínio>.yml
│   ├── pipelines/<domínio>.yml
│   ├── dashboards/<domínio>.yml      (gerado)
│   └── alerts/<domínio>.yml          (gerado)
├── src/arvo/                 todo o código, um subpacote por domínio
│   ├── semantic/             camada semântica: glossário, conceitos, métricas, decisões AMB
│   ├── contracts/            contrato como dado: extração por IA, grounding, aprovação
│   ├── platform/             catálogos, permissões, LGPD, notebooks e SQL de plataforma
│   ├── medallion/            bronze → silver → gold (Lakeflow e harness local)
│   ├── rules/                motor de regras de glosa (regras.yaml)
│   ├── evaluation/           precisão, recall, amostragem, adjudicação
│   ├── monitoring/           indicadores de sanidade, painel, alertas, portão de envio
│   ├── rollout/              estágios por regra e destino de cada glosa
│   ├── funnel/               Parte 2: funil de economia
│   ├── architecture/         modelo de dados como código e diagramas gerados
│   ├── ai/                   núcleo de IA: ports, roteador, política de dados, telemetria, prompts
│   ├── agents/               agentes: analyst/, genie/, providers/ (ver src/arvo/agents/README.md)
│   └── deliverables/         código que gera os entregáveis do case
├── tests/<domínio>/          testes, espelhando src/arvo/
├── deliverables/             entregáveis gerados: respostas, apontamentos, resumo, pitch
├── data/case/                arquivos do case, sem alteração
├── docs/                     guia, plano, Free Edition, convenções, histórico
└── outputs/                  saídas locais de execução (ignoradas pelo git)
```

**Regras:**
- **Um domínio = uma pasta** em `src/arvo/<domínio>/`, com `README.md`, e os testes em `tests/<domínio>/`.
- **Notebooks e SQL do Databricks** ficam dentro do domínio: `src/arvo/<domínio>/notebooks/` e `src/arvo/<domínio>/databricks/`.
- **Arquivos gerados** dizem no cabeçalho quem os gera e não são editados à mão; o CI confere que estão atualizados.
- **Caminhos no código** partem da raiz do repositório (`RAIZ`) ou da pasta do próprio arquivo. Nada depende do diretório de onde o comando foi chamado.
- **Comandos** rodam como módulo: `python -m arvo.<domínio>.<módulo>`.
- **Nomes de módulos e funções** continuam em português, porque descrevem o domínio do case (glosa, sinistro, apontamento). A estrutura em volta é em inglês.

## Databricks

| Item | Padrão | Exemplo |
|---|---|---|
| Arquivo de recurso | `resources/<tipo>/<domínio>.yml` | `resources/jobs/medallion.yml` |
| Chave do recurso no bundle | `<domínio>_<ação>` | `medallion_run` |
| Nome no workspace | `arvo-<domínio>-<ação>-<alvo>` | `arvo-medallion-run-free` |
| Pipeline | `arvo-<domínio>-<alvo>` | `arvo-medallion-free` |
| Painel | `arvo-<domínio>-<alvo>` | `arvo-monitoring-free` |
| Alerta | `arvo-<domínio> · <id> · <nome> [<severidade>]` | `arvo-monitoring · S06 · … [ALTA]` |
| Espaço Genie | `arvo-<agente>-genie-<ambiente>` | `arvo-analyst-genie-dev` |
| Tarefa (task_key) | verbo + objeto, em inglês | `load_gold_standard` |
| Tags de todo job e pipeline | `project`, `domain`, `phase` | `{project: arvo, domain: evaluation, phase: F8}` |
| Catálogo e schemas | `arvo_<ambiente>.<camada>` | `arvo_dev.gold`, `arvo_dev.semantic` |

A fase do projeto (F2 … F12) não entra no nome: ela muda com o tempo e o domínio não. A fase fica como tag. O teste `tests/platform/test_plataforma.py::test_nomes_e_tags_seguem_a_convencao` falha se um job ou pipeline fugir do padrão.

**Jobs hoje:**

| Chave | Domínio | O que faz |
|---|---|---|
| `platform_setup` | platform | (só alvo `free`) cria catálogo, schemas e volumes |
| `platform_smoke_test` | platform | gate G4: ambiente, permissões, máscaras |
| `platform_synthetic_data` | platform | (só alvo `dev`) sinistro sintético para quem não pode ver dado real |
| `semantic_load` | semantic | carrega a camada semântica em tabelas |
| `contracts_extract` | contracts | extrai o contrato do PDF por IA (exige chave de provedor) |
| `medallion_run` | medallion | planilha → bronze, pipeline `medallion`, coleta de qualidade |
| `evaluation_run` | evaluation | gabarito → precisão e recall |
| `monitoring_refresh` | monitoring | metric views, status dos indicadores, portão de envio |
| `rollout_decide` | rollout | destino de cada glosa |

Ordem no Free Edition: `platform_setup` → `semantic_load` → `medallion_run` → `evaluation_run` → `monitoring_refresh` → `rollout_decide`.

## Como adicionar
- **Um domínio novo:** `src/arvo/<domínio>/` com `__init__.py` e `README.md`, `tests/<domínio>/`, e, se rodar no Databricks, `resources/jobs/<domínio>.yml` seguindo a tabela acima.
- **Um agente novo:** `src/arvo/agents/<agente>/`, ver [`src/arvo/agents/README.md`](../src/arvo/agents/README.md).
- **Um provedor de IA novo:** um adapter em `src/arvo/agents/providers/`, ver o mesmo README. SDK de provedor só pode ser importado ali (teste em `tests/ai/test_f7.py`).
