# Agente analista (`src/arvo/agents/analyst/`)

Responde perguntas de negócio sobre a auditoria do Hospital São Rafael e o funil de economia, a partir da camada semântica publicada no Databricks. Todo número da resposta sai de uma consulta registrada, com o SQL.

```bash
python -m arvo.agents.analyst "Quanto foi glosado por cláusula em junho, e qual cláusula é mais defensável em recurso?" --rastro
```

## A decisão: Genie para os dados, um modelo trocável para orquestrar

| Pergunta | Decisão | Por quê |
|---|---|---|
| Quem descobre os dados? | **Genie, como prioridade** | Lê a camada semântica do Unity Catalog (metric views com `MEASURE`, comentários, tags) e roda dentro da plataforma. Com o espaço configurado por código, acertou 8 de 8 perguntas do benchmark |
| O Genie é o agente inteiro? | **Não** | Ele transforma pergunta em SQL. Não explica uma glosa com a cláusula, não lê o glossário nem as decisões, não entra no controle de prompts, telemetria e fallback da camada de IA, e prenderia o agente a um fornecedor |
| Quem orquestra? | **API do Claude (`claude-opus-5-5`), com fallback para um modelo hospedado no Databricks (`databricks-gpt-oss-120b`)** | O orquestrador decide que ferramenta usar e escreve a resposta. Os dois ficam atrás do mesmo port, e a troca é configuração (`src/arvo/agents/analyst/config.yaml`) |
| E se o Genie falhar? | **Consulta estruturada às metric views** | O modelo escolhe medida e dimensão do catálogo; o SQL é montado por código, nunca escrito pelo modelo |

## Como funciona

```
pergunta ─► ORQUESTRADOR (Claude ▸ fallback gpt-oss no Databricks) ─► resposta com número, fonte e SQL
                 │
                 ├─ consultar_dados ─────► Genie (espaço "arvo-analyst-genie-dev")
                 ├─ consultar_metrica ───► SQL montado pelo catálogo semântico ─► SQL warehouse
                 ├─ consultar_semantica ─► glossário, conceitos, métricas, regras e decisões AMB
                 ├─ consultar_regra ─────► src/arvo/rules/regras.yaml + contrato transcrito
                 └─ explicar_glosa ──────► o apontamento do motor (regra, cláusula, valores, justificativa)
```

| Arquivo | Papel |
|---|---|
| [`agente.py`](agente.py) | Loop: turno do modelo → ferramentas → próximo turno. Conversa em formato neutro; fallback entre modelos com circuit breaker |
| [`ferramentas.py`](ferramentas.py) | As cinco ferramentas e a redução pela política de dados |
| [`semantica.py`](semantica.py) | Catálogo lido de `src/arvo/semantic/databricks/02_metric_views.sql`; montagem e validação do SQL; busca no glossário |
| [`../genie/space.py`](../genie/space.py) + [`../genie/espaco.yaml`](../genie/espaco.yaml) | O espaço Genie como código: tabelas, instruções, exemplos e benchmark |
| [`benchmark.py`](benchmark.py) + [`benchmark.yaml`](benchmark.yaml) | As perguntas de negócio com resposta conhecida, contra três alvos |
| [`../adapters/agente_llm.py`](../providers/agente_llm.py) | Orquestradores: Claude (Messages API) e Chat Completions com ferramentas (modelos do Databricks) |
| [`../adapters/databricks_dados.py`](../providers/databricks_dados.py) | Genie (Conversation API) e o executor de SQL |
| [`../prompts/agente_analista_v1.md`](../../ai/prompts/agente_analista_v1.md) | Instruções do orquestrador, versionadas e travadas |

## Regras que o código garante (testadas em `tests/agents/test_analyst.py`)
- **O agente não decide glosa.** Nenhuma ferramenta escreve. Quem glosa é o motor determinístico.
- **O modelo só recebe dado agregado, de catálogo ou de contrato.** Antes de qualquer resultado chegar ao modelo, saem as colunas de pessoa, conta e data de atendimento. Uma coluna cujo valor tem formato de identificador (B00134, G00027) também sai, qualquer que seja o nome dela. O número de linhas tem teto de 50. Vale para qualquer modelo, inclusive o externo.
- **Número sem fonte não existe.** As instruções exigem que todo número venha de uma ferramenta da conversa; o rastro guarda ferramenta, fonte e SQL de cada consulta.
- **SQL do caminho estruturado é montado por código.** Medida, dimensão e view são conferidas contra o catálogo; valores de filtro entram escapados.
- **Fallback de modelo.** Se o Claude falha, o modelo seguinte continua a mesma conversa. Sem credencial, o Claude sai da rodada na primeira tentativa.
- **Claude conforme a API vigente:** ferramentas com `strict`, `tool_choice` automático, sem `temperature`, esforço em `output_config.effort`, raciocínio reenviado sem alteração, fallback de recusa no servidor (`fallbacks: "default"`), cache do prefixo estável.

## Rodar
Requisitos: `pip install -e ".[dev,agents]"` na raiz do repositório e o perfil da CLI do Databricks (`arvo-free`).

```bash
python -m arvo.agents.genie.space publicar
```
Cria ou atualiza o espaço Genie e grava o id em `genie/estado.json`.

```bash
python -m arvo.agents.analyst "Qual a precisão e o recall do motor contra o gabarito?"
```

```bash
python -m arvo.agents.analyst "Quanto falta para a meta de 2%?" --orquestrador databricks_gpt_oss --sem-genie
```

**Para usar o Claude:** defina `ANTHROPIC_API_KEY` ou faça `ant auth login`. Sem credencial, o agente usa o modelo do Databricks. Cada pergunta ao Claude consome tokens pagos.

## Benchmark
```bash
python -m arvo.agents.analyst.benchmark --alvo metrica
```
```bash
python -m arvo.agents.analyst.benchmark --alvo genie
```
```bash
python -m arvo.agents.analyst.benchmark --alvo agente --orquestrador databricks_gpt_oss
```
A resposta certa de cada pergunta é o resultado do SQL de referência, executado no workspace na hora. Resultados em [`RELATORIO_BENCHMARK.md`](RELATORIO_BENCHMARK.md).
