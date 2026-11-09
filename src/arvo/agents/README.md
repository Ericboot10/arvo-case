# Agentes (`src/arvo/agents/`)

Tudo o que é preciso para reproduzir os agentes do projeto, e para trocar ou acrescentar provedores de IA.

```
agents/
├── analyst/      o agente analista: loop, ferramentas, catálogo semântico, prompt, configuração e benchmark
├── genie/        o espaço Genie como código (espaco.yaml) e o publicador (space.py)
└── providers/    adapters de provedor: o ÚNICO lugar onde SDKs de IA e do Databricks são importados
```

| Agente | Para quê | Onde |
|---|---|---|
| **Analista** | Responde perguntas de negócio a partir da camada semântica, com a fonte e o SQL de cada número | [`analyst/`](analyst/README.md) |
| **Genie** (Databricks) | Descoberta de dados em linguagem natural sobre as metric views. É a primeira ferramenta do analista e também pode ser usado sozinho no workspace | [`genie/`](genie/) |
| **Extração de contrato** | Lê o PDF com 2 modelos de famílias diferentes + juiz, com grounding por trecho | [`../contracts/`](../contracts/) (usa os mesmos providers) |

## Provedores

| Adapter | Arquivo | Provedor | Perímetro | Usado por |
|---|---|---|---|---|
| `AnthropicAgenteAdapter` | [`providers/agente_llm.py`](providers/agente_llm.py) | Claude via API da Anthropic (Messages API, tools) | externo | analista (orquestrador) |
| `ChatToolsAdapter` | [`providers/agente_llm.py`](providers/agente_llm.py) | Modelos servidos no Databricks (`databricks-gpt-oss-120b`), Chat Completions com tools | plataforma | analista (fallback) |
| `GenieConsultaAdapter` | [`providers/databricks_dados.py`](providers/databricks_dados.py) | Genie (Conversation API) | plataforma | analista (`consultar_dados`) |
| `DatabricksSQLExecutor` | [`providers/databricks_dados.py`](providers/databricks_dados.py) | SQL warehouse | plataforma | analista (`consultar_metrica`) |
| `AnthropicAdapter` | [`providers/anthropic_adapter.py`](providers/anthropic_adapter.py) | Claude, saída estruturada | externo | extração de contrato |
| `OpenAIResponsesAdapter`, `OpenAICompatChatAdapter` | [`providers/openai_adapters.py`](providers/openai_adapters.py) | OpenAI e qualquer endpoint compatível (AI Gateway do Databricks) | externo ou plataforma | extração de contrato |
| `ReplayAdapter` | [`providers/replay_adapter.py`](providers/replay_adapter.py) | Respostas gravadas (testes e demo sem chave) | local | testes |

Os contratos que cada adapter cumpre estão em [`../ai/ports.py`](../ai/ports.py): `LLMPort` (saída estruturada), `AgenteLLMPort` (turno com ferramentas), `ConsultaDadosPort` (pergunta → SQL e linhas) e `ExecutorSQLPort`. A política de dados ([`../ai/config/politica_dados.yaml`](../ai/config/politica_dados.yaml)) define o que pode ir para cada perímetro.

## Reproduzir do zero

1. **Instalar:**
   ```bash
   pip install -e ".[dev,agents]"
   ```
2. **Databricks:** siga [`docs/databricks-free-edition.md`](../../../docs/databricks-free-edition.md) até os jobs rodarem (o analista lê as tabelas e metric views do `arvo_dev`).
3. **Publicar o espaço Genie:**
   ```bash
   python -m arvo.agents.genie.space publicar
   ```
4. **Perguntar:**
   ```bash
   python -m arvo.agents.analyst "Quanto foi glosado por cláusula em junho?" --rastro
   ```
5. **Medir:**
   ```bash
   python -m arvo.agents.analyst.benchmark --alvo genie
   ```
6. **Usar o Claude como orquestrador:** defina `ANTHROPIC_API_KEY` (ou `ant auth login`). Sem credencial, o analista usa o modelo do Databricks.

## Acrescentar um provedor
1. Crie o adapter em `providers/`, implementando o port certo (`AgenteLLMPort` para orquestrar, `ConsultaDadosPort` para descobrir dados, `LLMPort` para saída estruturada). Importe o SDK dentro do adapter, de forma tardia.
2. Declare o `perimetro` (`local`, `plataforma` ou `externo`): a política de dados decide o que ele pode receber.
3. Registre na configuração do agente ([`analyst/config.yaml`](analyst/config.yaml)): a ordem da lista é a ordem de fallback.
4. Rode o benchmark com `--orquestrador <nome>` e compare com os outros alvos em `analyst/RELATORIO_BENCHMARK.md`.

## Acrescentar um agente
Crie `src/arvo/agents/<agente>/` com `__init__.py`, `README.md`, `config.yaml` e o prompt versionado em `src/arvo/ai/prompts/<agente>_v1.md` (travado com `python -m arvo.ai.prompts travar`). Reaproveite os providers e os ports; os testes ficam em `tests/agents/`.
