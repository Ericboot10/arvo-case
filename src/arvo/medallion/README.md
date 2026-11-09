# F5: pipelines medalhão e qualidade de dados

> **Status:** implementado e testado com **Spark local** (PySpark 3.5) sobre o sinistro real e o sintético (32 testes).
> O pipeline Lakeflow e os notebooks também rodaram no **Databricks Free Edition** em 09/11/2026, sobre o sinistro do case, com o mesmo resultado do local ([passo a passo](../../../docs/databricks-free-edition.md)). O que isso validou está no fim.
> Desenho completo (linhagem, estrela, colunas): [`../arquitetura/ARQUITETURA.md`](../architecture/ARQUITETURA.md).

## Como está organizado

| Arquivo | Papel |
|---|---|
| [`transformacoes.py`](transformacoes.py) | **Funções puras** de DataFrame: bronze, silver, dimensões, fatos e funil. As mesmas rodam no Lakeflow e no teste local |
| [`expectations.yaml`](expectations.yaml) | 15 expectations nas 6 dimensões de qualidade, com ação `warn`, `quarentena` ou `fail` |
| [`pipeline_lakeflow.py`](pipeline_lakeflow.py) | Pipeline Lakeflow Declarative: streaming table na bronze (Auto Loader), materialized views na silver e gold, padrão de quarentena da doc Databricks |
| [`local.py`](local.py) | Harness local com a mesma semântica de expectations. `python -m arvo.medallion.local --sinistro ... --planilha ...` |
| [`notebooks/ingerir_planilha.py`](notebooks/ingerir_planilha.py) | xlsx → `bronze.inteligencias_raw` (idempotente por arquivo) |
| [`notebooks/coletar_dq.py`](notebooks/coletar_dq.py) | Event log do pipeline → `ops.dq_resultados` (mesmo schema do harness local) |
| [`../resources/pipelines/medallion.yml`](../../../resources/pipelines/medallion.yml) | Pipeline serverless e job `medallion_run`: planilha → pipeline → coleta de DQ |

## Resultados no dado real (Hospital São Rafael, jun/2025)

| Verificação | Resultado |
|---|---|
| Bronze → silver | 1.696 → 1.696 itens, **0 em quarentena**, soma exata **R$ 1.194.396,92** (decimal, sem float) |
| Aderência semântica | 100% dos códigos com conceito |
| Contas / atendimentos | 320 contas / 309 atendimentos (beneficiário × dia) |
| Conflito PS × Eletivo (AMB-01) | 32 contas e 114 itens. Medido (E21, `warn`), não bloqueia |
| Fragmentação de conta (AMB-02) | Exatamente os 2 casos do decision log (B00152, B00212) |
| Cirurgia repetida no mesmo dia (AMB-08) | Exatamente os 2 casos do decision log (B00080, B00134) |
| Gap cobrado × pactuado (M06) | 175 itens acima do teto, **R$ 39.875,41**, igual à regra 2.2 do protótipo |
| Funil (Parte 2) | 26 inteligências, identificado R$ 1.936.700, efetivado R$ 335.769,94 |

## Resultados no dado sintético rotulado (semente 42)
- **Quarentena:** recebe **exatamente** os erros injetados, cada um com o motivo certo:
  - código inválido → E02 + E03
  - caráter "Emergência" → E04
  - total inconsistente → E08
  - quantidade zero → E06
  - id duplicado → E01, nas duas linhas
- **Nada além disso vai para a quarentena.**
- **Gap de preço calculado pelo pipeline = glosa de preço rotulada pelo gerador:** duas implementações independentes chegam ao mesmo número.
- **Fragmentação detectada = fragmentações injetadas.**

## Decisões de engenharia

**ADR-005: documentação gerada a partir de uma especificação.**
- [`src/arvo/architecture/modelo.yaml`](../architecture/modelo.yaml) é a fonte única. Mermaid, draw.io e o grafo são gerados a partir dele.
- O teste `test_schema_igual_ao_modelo_documentado` compara o schema **real** de cada tabela gerada pelo código com o modelo, coluna a coluna e tipo a tipo. Documentação desatualizada quebra o CI.

**ADR-006: minimização do identificador.**
- O `id_beneficiario` em claro existe **só na bronze**, mascarado em stg e prod. Da silver em diante (inclusive na quarentena), só fica o pseudônimo `id_beneficiario_hash`, calculado com a mesma fórmula da máscara SQL. Por isso casa entre camadas.
- Isso elimina a dependência de máscara em materialized views.

**ADR-007: fato largo na gold.**
- A `gold.fato_item` mantém as chaves das dimensões (estrela) **e** atributos conformados desnormalizados (conceito, caráter, regime).
- Motivo: as metric views e o Genie respondem com menos joins.
- As dimensões continuam sendo a fonte desses atributos, e o fato os copia no build, então não diverge.

**Quarentena em vez de descarte.**
- Valor inconsistente (E08) vai para quarentena, não para `warn`: um total inconsistente não pode fundamentar glosa (precisão > recall).
- Com id duplicado, as **duas** linhas vão para quarentena, porque não dá para saber qual vale.

**Contrato não aprovado:**
- Fora de prod, a F5 usa a transcrição da F2, marcada como `PRT-2025-0417@rascunho-F2` na `dim_contrato`.
- Em **prod**, sem `contract_params` aprovado, o pipeline **falha** (testado).

**Invariantes `fail`:** excedente entre 0 e o valor cobrado, e versões de contrato e semântica sempre preenchidas. O teste força um teto negativo e confirma que o pipeline para.

## Rodar
A partir da pasta `Arvo_Case`, com Java 11 ou 17:
```bash
pip install -e ".[dev]"
```

> **Memória do Spark local.** O heap é explícito (`ARVO_SPARK_MEM`, padrão `3g`), e cada `executar()` registra o que coloca em cache para `liberar(out)`.
> Sem isso, várias execuções no mesmo processo esgotavam o heap padrão (~1 GB), e o JVM entrava em GC contínuo (incidente de 06/11/2026: 46 min sem terminar, 5.852 full GCs).
> Com a correção, a suíte completa roda em cerca de 1 min 40 s. O `pytest.ini` limita cada teste a 300 s, e o CI roda cada suíte Spark em processo próprio, com teto de 30 min no job.
```bash
pytest tests/medallion -v
```
```bash
python -m arvo.medallion.local --sinistro data/case/sinistro-hospital-saorafael.csv --planilha data/case/Inteligencias_apos_6_meses.xlsx
```

No Databricks:
1. Rode os jobs `semantic_load` e `medallion_run`. O pipeline lê `semantic.*`, `contracts.contract_params` e o Volume `bronze/landing/sinistro/`.
2. Em dev, gere antes os dados sintéticos com o job `platform_synthetic_data`.

## Validação no workspace (Free Edition, 09/11/2026)
- [x] Import do módulo de pipelines no runtime serverless.
- [x] Publicação em vários schemas (bronze, silver, gold) com nomes totalmente qualificados.
- [ ] `MASK` declarado no `schema` da streaming table da bronze: em dev a máscara fica desligada de propósito (só há sintético); valida em stg.
- [x] `pyyaml` e `openpyxl` disponíveis: `ingerir_planilha` leu o xlsx real.
- [x] Caminho JSON das métricas no `event_log()`: `coletar_dq` gravou 29 linhas de 19 expectations em `ops.dq_resultados`.
- [x] Restrições do serverless corrigidas: sem `tableExists` e sem leitura imediata (`.first()`) dentro do pipeline.
- [ ] Monitores de qualidade (anomaly detection de freshness e completude) ligados no schema `bronze`: é a tempestividade, que não é expectation linha a linha.
