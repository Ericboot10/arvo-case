# Arvo × Parthenon · agente de glosa do Hospital São Rafael

Este é um case de seleção da Arvo. O agente audita a conta hospitalar contra o contrato PRT-2025-0417 (Curitiba/PR) e aponta cada cobrança indevida com a cláusula que fundamenta a glosa. Ele foi desenhado como um comitê de tecnologia faria: semântica antes do código, independência de provedor de IA, sanidade com foco no negócio e rollout com evidência.

**Resultado:**
- **R$ 121.948,93 glosados em 369 itens.**
- **Precisão de 94,4% e recall de 90,0%** contra o gabarito.
- **Nenhuma regra vai a envio automático antes do shadow.**

**Para entender o projeto:** [`docs/how-it-works.md`](docs/how-it-works.md) explica o raciocínio, o agente passo a passo, como rodar com um mês novo e o papel do Databricks. A estrutura e o padrão de nomes (pastas, jobs, recursos do Databricks) estão em [`docs/conventions.md`](docs/conventions.md). Para reproduzir os agentes de IA (Genie, Claude e outros provedores): [`src/arvo/agents/README.md`](src/arvo/agents/README.md). Para mostrar o agente ao vivo: [`docs/demo-ao-vivo.md`](docs/demo-ao-vivo.md).

**Onde estão as respostas:**
- As 8 perguntas da Parte 1: [`deliverables/RESPOSTAS_CASE.md`](deliverables/RESPOSTAS_CASE.md).
- A Parte 2: [memo](https://claude.ai/artifact/Y3i8MpGuPeFnxUxc7BxnCf) e [deck](https://claude.ai/artifact/Duao3bxGMDvN5R9Uq6jTTs).

## Um comando roda tudo
```bash
python -m arvo.deliverables.rodar_tudo
```
Gera os entregáveis em cerca de 4 minutos, localmente, sem chamar provedor de IA externo (a extração do contrato usa o replay determinístico). Com `--testes`, roda também a suíte de 214 testes.

Para rodar o agente sobre outro mês no mesmo layout: `python -m arvo.deliverables.gerar --sinistro caminho/arquivo.csv` (saída em `outputs/results/`).

Requisitos: Python 3.12 e Java 11+. Na raiz do repositório:
```bash
pip install -e ".[dev,agents]"
```
O pacote `arvo` fica em `src/` e as dependências, no `pyproject.toml`. O extra `agents` traz os SDKs da Anthropic e do Databricks, usados só pelos agentes.

No Databricks, o mesmo código roda pelo bundle:
```bash
databricks bundle validate -t dev
```
```bash
databricks bundle deploy -t dev
```
```bash
databricks bundle run medallion_run -t dev
```
Antes do deploy, preencha os placeholders `DEFINIR_*` do `databricks.yml`: workspace, service principals e warehouse.

Para testar sem conta corporativa, use a **Databricks Free Edition** com o alvo `free`: passo a passo em [`docs/databricks-free-edition.md`](docs/databricks-free-edition.md).

## Entregáveis
| Pedido do case | Onde |
|---|---|
| Regras do contrato, com a cláusula de cada glosa | [`src/arvo/rules/regras.yaml`](src/arvo/rules/regras.yaml) e [`src/arvo/semantic/vinculos/PRT-2025-0417.yaml`](src/arvo/semantic/vinculos/PRT-2025-0417.yaml) |
| Lista de apontamentos (id_item, regra, valor) | [`deliverables/apontamentos.csv`](deliverables/apontamentos.csv) |
| Valor de glosa total | [`deliverables/resumo_glosa.json`](deliverables/resumo_glosa.json) |
| Precisão, recall e divergências | [`src/arvo/evaluation/RELATORIO_AVALIACAO.md`](src/arvo/evaluation/RELATORIO_AVALIACAO.md) |
| Defensabilidade, parâmetros por prestador, produção e monitoramento | [`deliverables/RESPOSTAS_CASE.md`](deliverables/RESPOSTAS_CASE.md) |
| Parte 2: funil de economia | Memo e deck (links acima) e [`src/arvo/funnel/`](src/arvo/funnel/) |
| Apresentação | [`deliverables/PITCH.md`](deliverables/PITCH.md) |

## Estrutura
```
src/arvo/<domínio>/      código, um subpacote por domínio (semantic, contracts, medallion, rules, ...)
src/arvo/agents/         agentes: analyst, genie e providers (adapters de IA)
tests/<domínio>/         testes, espelhando src/arvo
resources/<tipo>/        jobs, pipelines, painel e alertas do Databricks, um arquivo por domínio
deliverables/            entregáveis gerados
data/case/               arquivos do case, sem alteração
docs/                    guia, plano, Free Edition, convenções
```

## Mapa do repositório (na ordem do comitê)
| Fase | Pasta | O quê |
|---|---|---|
| F2 · semântica | [`src/arvo/semantic/`](src/arvo/semantic/) | Glossário (51 termos), conceitos, papéis contratuais, 34 métricas, decision log AMB-01..21 |
| F3 · contrato como dado | [`src/arvo/contracts/`](src/arvo/contracts/) | Extrator determinístico + 2 LLMs de famílias diferentes + juiz, grounding por trecho, aprovação humana |
| F4 · plataforma | [`src/arvo/platform/`](src/arvo/platform/), [`databricks.yml`](databricks.yml) | Catálogo por ambiente, grants, máscaras LGPD, bundle, CI com OIDC |
| Arquitetura | [`src/arvo/architecture/`](src/arvo/architecture/) | `modelo.yaml` → Mermaid, draw.io e grafo gerados (doc = código, testado) |
| F5 · medalhão | [`src/arvo/medallion/`](src/arvo/medallion/) | Bronze → silver → gold com expectations; Lakeflow e harness local com o mesmo código |
| F6 · motor | [`src/arvo/rules/`](src/arvo/rules/) | Regras como dado, sobre colunas semânticas; justificativa com cláusula e cálculo |
| F7 · IA | [`src/arvo/ai/`](src/arvo/ai/) | Ports & adapters, roteador com política de dados, golden set por provedor, telemetria |
| Agentes | [`src/arvo/agents/`](src/arvo/agents/) | Perguntas de negócio respondidas pela camada semântica: Genie para os dados, Claude (ou modelo do Databricks) para orquestrar |
| F8 · avaliação | [`src/arvo/evaluation/`](src/arvo/evaluation/) | IC, estimativa populacional, divergências, adjudicação cega, matriz de custo |
| F9 · sanidade | [`src/arvo/monitoring/`](src/arvo/monitoring/) | 39 indicadores (negócio primeiro, Parte I e Parte II separadas), alertas SQL, painel AI/BI, portão de envio |
| F10 · rollout | [`src/arvo/rollout/`](src/arvo/rollout/) | Estágios por regra, teto de valor pela matriz de custo, rebaixamento automático |
| F11 · Parte 2 | [`src/arvo/funnel/`](src/arvo/funnel/) | Números do funil, reproduzíveis |
| F12 · entrega | [`deliverables/`](deliverables/) | Respostas, apontamentos, pitch e o comando único |

O plano do comitê, com papéis, gates G0–G12 e referências, está em [`docs/plan.md`](docs/plan.md).

## O que está implementado e o que está especificado
| Implementado e testado | Especificado, aguardando ambiente ou pessoas |
|---|---|
| Todas as fases acima, com 214 testes locais | Ambientes stg e prod (exigem account console e service principals) |
| Execução no Databricks Free Edition (alvo `free`) com os dados do case: F2, F5, F8, F9 e F10, painel com precisão e recall, mesmos números da entrega ([detalhes](docs/databricks-free-edition.md)) | Extração do contrato por IA no workspace (sem chave de provedor) |
| Extração do contrato em modo replay | Extração com provedores reais (sem chaves de API) |
| Pacote de adjudicação cega | Revisão pelos dois auditores |
| Critérios de go-live e o que falta por regra | Shadow e backtest com histórico da Parthenon |
| Decision log | Decisões e assinaturas de Negócio, Jurídico e Auditoria |

## Dados
Os arquivos do case (contrato, sinistro, gabarito e planilha) ficam em [`data/case/`](data/case/), sem alteração. O `sync.exclude` deixa os quatro fora do código publicado pelo bundle. No workspace, eles entram pelos volumes, com `src/arvo/platform/subir_dados_case.sh`, e ficam marcados como dado do case. O gerador de sinistro sintético existe só para um dev corporativo com PHI real (alvo `dev`) e não é usado em nenhum número da entrega.
