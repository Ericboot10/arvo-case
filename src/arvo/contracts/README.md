# F3: contrato como dado (`arvo.contracts`)

> **Status:** implementado e testado localmente (29 testes). Os extratores de IA **reais** ainda não foram executados: não há chave de API nesta máquina, então a demonstração usa extratores **simulados**, marcados como tal em toda saída.
> A F3 roda antes do Gate G2 (semântica) por decisão do usuário. Os parâmetros que ela gerar continuam rascunho até o G2 ser assinado.

## O que faz
Transforma o PDF do contrato em `contract_params.json` versionado. Cada parâmetro tem:
1. **citação literal verificada no documento**, e o valor aparece dentro da citação;
2. **consenso entre extratores independentes**: D (determinístico), A e B (LLMs de famílias diferentes);
3. **aprovação humana** do Jurídico, com assinatura, antes de existir para o motor de regras.

```
RECEBIDO → PARSEADO → EXTRAIDO (D, A, B) → RECONCILIADO → JULGADO → REVISAO_HUMANA → APROVADO | REJEITADO
                                                                     ▲ o pipeline PARA aqui. Só um humano avança
```

## Arquitetura (Ports & Adapters)
| Camada | Arquivos | Regra |
|---|---|---|
| **Ports** | `../ia/ports.py` (camada compartilhada, F7) | `LLMPort`, `DocumentParserPort`, `LLMRequest/LLMResult/LLMParams`. O core só conhece isto |
| **Core** | `pipeline.py`, `reconciliacao.py`, `grounding.py`, `juiz.py`, `revisao.py`, `sanidade.py`, `estado.py`, `schema.py` | **Nenhum** import de SDK de provedor (há teste que garante) |
| **Roteamento** | `../ia/roteador.py` (F7: + política de dados e circuit breaker) | Cadeia de fallback, cache por hash, orçamento de tokens antes da chamada, telemetria |
| **Adapters** | `../ia/adapters/anthropic_adapter.py`, `../ia/adapters/openai_adapters.py` (OpenAI direto e **qualquer endpoint OpenAI-compatível, incluindo o Databricks AI Gateway**), `../ia/adapters/replay_adapter.py` (simulado) | Único lugar com SDK. Import tardio |
| **Configuração** | `config/extracao.yaml` | Provedores, modelos, cadeias, orçamento e preços. **Trocar de provedor = editar o YAML** |
| **Prompt** | `prompts/extracao_contrato_v1.md` e `prompts/juiz_extracao_v1.md` | Versionado. O hash vai para a telemetria. Travado em `../ia/prompts.lock.json` e publicado no MLflow Prompt Registry |

**Independência de provedor em 3 níveis:**
1. A e B precisam ser de famílias diferentes. A config é rejeitada se não forem, e a reconciliação sinaliza `independencia_reduzida` se um fallback cair na mesma família.
2. Cada slot tem uma cadeia de fallback: direto → AI Gateway.
3. O extrator D não usa LLM. Com **todos** os provedores fora do ar, o pipeline ainda chega à revisão humana (teste de caos).

## Decisões guiadas pela documentação dos provedores
- **Schema mínimo comum:** todos os campos `required`, `additionalProperties: false`, sem `pattern`, `min`, `max`, `oneOf` ou `$ref`. Cada provedor rejeita ou ignora partes diferentes. Toda restrição fina é validada em código (`schema.validar`).
- **Anthropic (`claude-opus-5-5`):**
  - `output_config.format` em vez do `output_format`, que está depreciado.
  - `temperature` e `top_p` **não são enviados**, porque retornam 400 nesse modelo. A telemetria registra "pedido e não aplicado".
  - `output_config.effort: high` explícito (o padrão do modelo é `medium`).
  - `cache_control` no prefixo estável (instruções + contrato).
  - Fallback de recusa no servidor ligado (`server-side-fallback-2026-07-01`, `fallbacks: "default"`). Desligue no Batches API, Bedrock, Vertex e Foundry.
  - O modelo que de fato respondeu fica em `modelo_servido`.
- **OpenAI (Responses API):**
  - `text.format` `json_schema` `strict`.
  - Truncamento detectado por `status: incomplete` / `max_output_tokens`. Recusa, por conteúdo `type: refusal`.
  - Tokens de raciocínio são registrados à parte.
- **Databricks AI Gateway (Chat Completions):**
  - `response_format` `json_schema` `strict`.
  - Os modelos `databricks-claude-*-5-5` retornam 400 com `response_format` nessa API. A config avisa, e esses modelos devem ir pelo adapter Anthropic.
- **Citações vs structured outputs:** no Claude não dá para combinar os dois na mesma chamada. Por isso a citação é um **campo do schema** verificado em código, técnica que vale igual para qualquer provedor.

## Achados reais deste PDF (tratados pelo parser e contados em `artefatos`)
- **Rodapé repetido em todas as páginas:** corta a cláusula 2.2 ao meio. O parser remove e reúne a cláusula.
- **21 caracteres nulos (`\x00`) no lugar de `)` e `-`:** ex.: `20103077 (porte 4\x00`, `0001\x0090`.
- **Símbolo `∘` no lugar de `º`:** `n ∘`, `1∘ de janeiro`.
- **Texto corrido intercala as células das tabelas:** a verificação de citação compara contra o texto **e** as linhas de tabela em ordem de leitura.

## Bugs que os próprios controles pegaram durante a construção
1. **Cache contaminando a independência.** A chave de cache não incluía o adapter, então dois extratores com o mesmo nome de modelo receberam a mesma resposta. O "consenso" saiu 100%, falso. A chave foi corrigida e há teste de regressão (`test_cache_nao_mistura_adapters_com_mesmo_modelo`).
2. **Aprovação sem regras.** O número da cláusula ("2.2") tem ponto e quebrava a reconstrução dos parâmetros. A **checagem de sanidade S07 bloqueou a aprovação** em vez de deixar passar parâmetros sem regras.

## Como rodar
A partir da pasta `Arvo_Case`:
```bash
pip install -e ".[dev]"
```
```bash
pytest tests/contracts -v
```
```bash
python -m arvo.contracts extrair --pdf data/case/Contrato-parthenon-x-hospital-sao-rafael.pdf --modo simulado
```
O comando cria `outputs/runs/PRT-2025-0417/<chave>/` com estes arquivos:
- `revisao.md`: o que o Jurídico lê
- `aprovacao.yaml`: o que o Jurídico preenche e assina
- `reconciliacao.json`, `extracao_{D,A,B}.json`, `llm_calls.jsonl` (telemetria), `estado.json` e `parse.json`

Depois que o Jurídico assinar o `aprovacao.yaml`:
```bash
python -m arvo.contracts aprovar --run outputs/runs/PRT-2025-0417/<chave> --aprovacao outputs/runs/PRT-2025-0417/<chave>/aprovacao.yaml
```
Isso gera `contract_params.json` (versão imutável `id@data-hash`), `vinculo.yaml` (substitui a transcrição manual de `src/arvo/semantic/vinculos/`, via PR) e `sanidade.json`.

**Modo real:**
1. Preencha os `DEFINIR_*` em `config/extracao.yaml`.
2. Exporte as credenciais: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DATABRICKS_HOST` e `DATABRICKS_TOKEN`.
3. Use `--modo real`.

**No Databricks:**
1. `databricks/f3_tabelas.sql`: cria `ops.llm_calls`, `ops.contract_extraction_state`, `contracts.contract_field_candidates` e `contracts.contract_params`.
2. `databricks/f3_executar_extracao.py`: a task de Job. Credenciais vêm de secret scope.
3. `databricks/f3_ai_parse_document.sql`: parser alternativo, **a validar** no workspace.

## O que a demo simulada mostra
O extrator B simulado tem 5 erros típicos de LLM, e todos são pegos:

| Erro injetado | Como é pego | Status |
|---|---|---|
| Valor alucinado (4.300) com citação verdadeira ("R$ 4.200,00") | O valor não aparece na citação | DIVERGENTE |
| Citação inventada na regra 4.2 | A citação não existe na cláusula 4.2 | CONSENSO_SEM_EVIDENCIA |
| Pacote 30715016 omitido | Falta numa fonte | INCOMPLETO |
| Cateter listado como material de rotina | Divergência + não está na citação | DIVERGENTE |
| Cláusula 5.1 (genérica) tratada como regra | Só uma fonte traz o campo; o juiz diz NENHUM_CORRETO | INCOMPLETO |

Ficam 34 de 42 campos com consenso verificado (aceite em bloco) e 8 para decisão humana.

## Indicadores de sanidade da IA (`ops.llm_calls`)
- **Por chamada:** provedor, adapter, família, modelo pedido e servido, prompt e schema (id, versão e hash), parâmetros pedidos/aplicados/ignorados, tokens (input, output, cache read e write, reasoning), custo estimado, latência, desfecho normalizado (COMPLETO, TRUNCADO, RECUSA, FILTRO_CONTEUDO, ERRO, BLOQUEADO_ORCAMENTO), schema válido, fallback, cache hit e sha256 do documento.
- **Do run** (`reconciliacao.json`): taxa de consenso verificado, campos por status, independência e falhas por extrator.

## Pendências
- [ ] Rodar em modo **real** com ≥ 2 provedores e medir: concordância A×B, consenso verificado, custo e latência.
- [ ] Golden set de variantes do contrato (preço alterado, cláusula renumerada, PDF escaneado) para aceitar cada provedor (critério do plano: ≥ 99% de acerto campo a campo, 0 campos inventados).
- [ ] Validar `ai_parse_document` no workspace e escrever o adapter correspondente.
- [ ] Assinatura do Jurídico no run de produção. Promover `vinculo.yaml` para `src/arvo/semantic/vinculos/` via PR.
