# F7: camada de IA independente de provedor (`ia/`)

> **Status:** implementada e testada localmente (19 testes), **sem chamada a provedor real**: não há chave de API nesta máquina.
> **Gate G7: NÃO ATENDIDO.** O critério exige ≥ 2 provedores de IA aprovados no golden set, e nenhum foi avaliado ainda.
> O caminho determinístico passa em todas as variantes. Para fechar o G7, rode `python -m ia.avaliacao.golden --modo real`.

## O que é

A camada de IA compartilhada por todas as tarefas. Hoje são três: extração de contrato (F3), juiz da reconciliação (F3) e sugestão de conceito TUSS (F7). As tarefas conhecem só os **ports**. Provedor, modelo, fallback, política e orçamento ficam em configuração.

```
tarefa ──► LLMRequest(classe_dados, schema@versão, prompt@versão, params pedidos)
              │
              ▼
          Roteador ─► 1 política de dados ─► 2 circuit breaker ─► 3 cache ─► 4 orçamento ─► 5 adapter ─► fallback
              │                                                                                      │
              └────────────────────────── LLMCallRecord (telemetria de TODA chamada) ◄────────────────┘
adapters: anthropic (Messages API) · openai (Responses) · openai_compat (Databricks AI Gateway / vLLM) · replay (simulado)
```

| Arquivo | Papel |
|---|---|
| [`ports.py`](ports.py) | `LLMPort`, `LLMRequest` (com `classe_dados`), `LLMResult`, `DocumentParserPort`. Adapter declara `perimetro` |
| [`roteador.py`](roteador.py) | Política de dados, circuit breaker, cache por hash, orçamento de tokens, fallback e telemetria |
| [`esquemas.py`](esquemas.py) | Registro `schema_id@versão → validador`. Toda resposta é validada em código (o provedor só garante o formato) |
| [`config/politica_dados.yaml`](config/politica_dados.yaml) | **LGPD:** que classe de dado pode ir para que perímetro. Identificável: nunca |
| [`config/capacidades.yaml`](config/capacidades.yaml) + [`capacidades.py`](capacidades.py) | Matriz por provedor (palavras de schema rejeitadas ou **ignoradas em silêncio**, limites, amostragem, cache, batch) e linter |
| [`avaliacao/golden.py`](avaliacao/golden.py) | **Golden set de aceite:** contrato real + 6 variantes. Relatório em [`avaliacao/relatorio_aceite.md`](avaliacao/relatorio_aceite.md) |
| [`indicadores.py`](indicadores.py) + [`config/alertas_ia.yaml`](config/alertas_ia.yaml) + [`databricks/v_ia_sanidade.sql`](databricks/v_ia_sanidade.sql) | Indicadores de sanidade e alertas (mesmas definições em Python e SQL) |
| [`prompts.py`](prompts.py) + [`prompts.lock.json`](prompts.lock.json) | Versão obrigatória e trava de conteúdo por sha256. [`databricks/registrar_prompts.py`](databricks/registrar_prompts.py) publica no MLflow Prompt Registry |
| [`tarefas/sugerir_conceito.py`](tarefas/sugerir_conceito.py) | Tarefa 2: código TUSS novo (quarentena E03) → conceito sugerido, **sempre** pendente do Especialista |

## Garantias (testadas)

**Independência de provedor**
- Nenhum SDK de provedor fora de `ia/adapters` (varredura do repositório inteiro).
- Todos os schemas das tarefas passam no linter para **todos** os provedores das cadeias: Anthropic, OpenAI, Google (via Gateway) e Databricks.
- Um schema com `minLength` ou `pattern` é barrado: rejeitado por uns e ignorado em silêncio por outros.

**Política de dados (LGPD)**
- O roteador bloqueia **antes** de chamar e cai no próximo adapter permitido. Dado identificável não sai para nenhum perímetro.
- A extração de contrato é `contratual` e a sugestão de conceito é `catalogo` (código e descrição, sem pessoa). As duas podem ir para provedor externo.
- Dado pseudonimizado só vai para modelo hospedado no Databricks (`plataforma`).

**Resiliência**
- O circuit breaker abre após 3 falhas consecutivas do mesmo adapter no run e fecha no sucesso.
- Fallback em erro, truncamento, recusa e schema inválido (testes da F3).

**Golden set** (critério: acurácia ≥ 99%, 0 inventados, 100% das citações verificadas)

| Variante | Determinístico |
|---|---|
| v0 contrato original | ✅ |
| v1 preços alterados | ✅ |
| v2 cláusula renumerada | ✅ |
| v3 linha nova no Anexo I | ✅ |
| v4 pacote removido | ✅ |
| v5 código da taxa trocado | ✅ |
| v6 tabela sem cabeçalho repetido | ✅ (após correção) |

Um extrator com os 5 erros da demo da F3 é **reprovado**, com os erros apontados.

**O golden set encontrou 3 problemas reais**, que foram corrigidos:
1. O extrator determinístico perdia 7 linhas quando a continuação do Anexo I não repetia o cabeçalho (v6 a 82%). Agora classifica a linha pelo formato.
2. A verificação de citações ignorava a linha de "cabeçalho" das tabelas.
3. O próprio gerador de variantes alterava preço também no Anexo II.

**Prompts**
- 3 prompts versionados e travados. O prompt do juiz saiu do código e foi para um arquivo versionado.
- Mudar o texto sem subir a versão faz o CI falhar.

**Tarefa 2**
- Resposta com conceito fora do domínio: a resposta **inteira** é descartada (registrada como schema inválido) e entra o fallback determinístico.
- Quando LLM e determinístico discordam, a sugestão vai para o topo da fila. Status sempre `PENDENTE_ESPECIALISTA`.

## Indicadores de sanidade de IA (por tarefa × adapter)

| Grupo | Indicadores |
|---|---|
| Qualidade | schema válido · recusa · truncamento · erro |
| Resiliência | fallback · circuito aberto · cache hit |
| Governança | bloqueio de política (deve ser 0) · parâmetro pedido e ignorado (ex.: temperatura em modelo de raciocínio) |
| Custo | tokens de entrada, saída, cache e raciocínio · custo estimado |
| Latência | p50 · p95 |
| Drift | modelo servido ≠ pedido, ou mais de um modelo servido → rodar o golden set antes de aceitar |

```bash
python -m ia.indicadores contratos/runs/PRT-2025-0417/<chave>/llm_calls.jsonl
```

## Rodar
```bash
pytest ia/tests -v
```
```bash
python -m ia.avaliacao.golden --modo simulado
```
```bash
python -m ia.prompts verificar
```

Depois de editar um prompt, suba a `versao` no frontmatter e trave:
```bash
python -m ia.prompts travar
```

## Para fechar o Gate G7
- [ ] Credenciais de ≥ 2 provedores de **famílias diferentes** (ou endpoints no AI Gateway) e os `DEFINIR_*` em `arvo_contrato/config/extracao.yaml`
- [ ] `python -m ia.avaliacao.golden --modo real`: cada provedor aprovado nas 7 variantes
- [ ] Teste de caos em stg: derrubar o provedor primário e confirmar que o `contract_params` sai idêntico via fallback
- [ ] View `ops.v_ia_sanidade` e alertas SQL ligados, e `registrar_prompts.py` executado (validar a assinatura do MLflow no workspace)
