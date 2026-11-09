# Arvo × Parthenon · agente de glosa do Hospital São Rafael

Este é um case de seleção da Arvo. O agente audita a conta hospitalar contra o contrato PRT-2025-0417 (Curitiba/PR) e aponta cada cobrança indevida com a cláusula que fundamenta a glosa. Ele foi desenhado como um comitê de tecnologia faria: semântica antes do código, independência de provedor de IA, sanidade com foco no negócio e rollout com evidência.

**Resultado:**
- **R$ 121.948,93 glosados em 369 itens.**
- **Precisão de 94,4% e recall de 90,0%** contra o gabarito.
- **Nenhuma regra vai a envio automático antes do shadow.**

**Para entender o projeto:** [`COMO_FUNCIONA.md`](COMO_FUNCIONA.md) explica o raciocínio, o agente passo a passo, como rodar com um mês novo e o papel do Databricks.

**Onde estão as respostas:**
- As 8 perguntas da Parte 1: [`entrega/RESPOSTAS_CASE.md`](entrega/RESPOSTAS_CASE.md).
- A Parte 2: [memo](https://claude.ai/artifact/Y3i8MpGuPeFnxUxc7BxnCf) e [deck](https://claude.ai/artifact/Duao3bxGMDvN5R9Uq6jTTs).

## Um comando roda tudo
```bash
python -m entrega.rodar_tudo
```
Gera os entregáveis em cerca de 4 minutos, localmente, sem chamar provedor de IA externo (a extração do contrato usa o replay determinístico). Com `--testes`, roda também a suíte de 188 testes.

Para rodar o agente sobre outro mês no mesmo layout: `python -m entrega.gerar --sinistro caminho/arquivo.csv` (saída em `resultados/`).

Requisitos: Python 3.12, Java 11+ e:
```bash
pip install pyyaml pandas pytest pytest-timeout pdfplumber openpyxl "pyspark==3.5.3"
```

No Databricks, o mesmo código roda pelo bundle:
```bash
databricks bundle validate -t dev
```
```bash
databricks bundle deploy -t dev
```
```bash
databricks bundle run f5_medalhao -t dev
```
Antes do deploy, preencha os placeholders `DEFINIR_*` do `databricks.yml`: workspace, service principals e warehouse.

Para testar sem conta corporativa, use a **Databricks Free Edition** com o alvo `free`: passo a passo em [`plataforma/FREE_EDITION.md`](plataforma/FREE_EDITION.md).

## Entregáveis
| Pedido do case | Onde |
|---|---|
| Regras do contrato, com a cláusula de cada glosa | [`motor/regras.yaml`](motor/regras.yaml) e [`semantic/vinculos/PRT-2025-0417.yaml`](semantic/vinculos/PRT-2025-0417.yaml) |
| Lista de apontamentos (id_item, regra, valor) | [`entrega/apontamentos.csv`](entrega/apontamentos.csv) |
| Valor de glosa total | [`entrega/resumo_glosa.json`](entrega/resumo_glosa.json) |
| Precisão, recall e divergências | [`avaliacao_cientifica/RELATORIO_AVALIACAO.md`](avaliacao_cientifica/RELATORIO_AVALIACAO.md) |
| Defensabilidade, parâmetros por prestador, produção e monitoramento | [`entrega/RESPOSTAS_CASE.md`](entrega/RESPOSTAS_CASE.md) |
| Parte 2: funil de economia | Memo e deck (links acima) e [`parte2/`](parte2/) |
| Apresentação | [`entrega/PITCH.md`](entrega/PITCH.md) |

## Mapa do repositório (na ordem do comitê)
| Fase | Pasta | O quê |
|---|---|---|
| F2 · semântica | [`semantic/`](semantic/) | Glossário (51 termos), conceitos, papéis contratuais, 34 métricas, decision log AMB-01..21 |
| F3 · contrato como dado | [`arvo_contrato/`](arvo_contrato/) | Extrator determinístico + 2 LLMs de famílias diferentes + juiz, grounding por trecho, aprovação humana |
| F4 · plataforma | [`plataforma/`](plataforma/), [`databricks.yml`](databricks.yml) | Catálogo por ambiente, grants, máscaras LGPD, bundle, CI com OIDC |
| Arquitetura | [`arquitetura/`](arquitetura/) | `modelo.yaml` → Mermaid, draw.io e grafo gerados (doc = código, testado) |
| F5 · medalhão | [`medalhao/`](medalhao/) | Bronze → silver → gold com expectations; Lakeflow e harness local com o mesmo código |
| F6 · motor | [`motor/`](motor/) | Regras como dado, sobre colunas semânticas; justificativa com cláusula e cálculo |
| F7 · IA | [`ia/`](ia/) | Ports & adapters, roteador com política de dados, golden set por provedor, telemetria |
| Agente analista | [`ia/agente/`](ia/agente/) | Perguntas de negócio respondidas pela camada semântica: Genie para os dados, Claude (ou modelo do Databricks) para orquestrar |
| F8 · avaliação | [`avaliacao_cientifica/`](avaliacao_cientifica/) | IC, estimativa populacional, divergências, adjudicação cega, matriz de custo |
| F9 · sanidade | [`sanidade/`](sanidade/) | 38 indicadores (negócio primeiro), alertas SQL, painel AI/BI, portão de envio |
| F10 · rollout | [`rollout/`](rollout/) | Estágios por regra, teto de valor pela matriz de custo, rebaixamento automático |
| F11 · Parte 2 | [`parte2/`](parte2/) | Números do funil, reproduzíveis |
| F12 · entrega | [`entrega/`](entrega/) | Respostas, apontamentos, pitch e o comando único |

O plano do comitê, com papéis, gates G0–G12 e referências, está em [`PLANO_CASE_ARVO.md`](PLANO_CASE_ARVO.md).

## O que está implementado e o que está especificado
| Implementado e testado | Especificado, aguardando ambiente ou pessoas |
|---|---|
| Todas as fases acima, com 188 testes locais | Ambientes stg e prod (exigem account console e service principals) |
| Execução no Databricks Free Edition (alvo `free`) com os dados do case: F2, F5, F8, F9 e F10, painel com precisão e recall, mesmos números da entrega ([detalhes](plataforma/FREE_EDITION.md)) | Extração do contrato por IA no workspace (sem chave de provedor) |
| Extração do contrato em modo replay | Extração com provedores reais (sem chaves de API) |
| Pacote de adjudicação cega | Revisão pelos dois auditores |
| Critérios de go-live e o que falta por regra | Shadow e backtest com histórico da Parthenon |
| Decision log | Decisões e assinaturas de Negócio, Jurídico e Auditoria |

## Dados
Os arquivos do case (contrato, sinistro, gabarito e planilha) ficam em [`arvo.case/`](arvo.case/), sem alteração. O `sync.exclude` deixa os quatro fora do código publicado pelo bundle. No workspace, eles entram pelos volumes, com `plataforma/subir_dados_case.sh`, e ficam marcados como dado do case. O gerador de sinistro sintético existe só para um dev corporativo com PHI real (alvo `dev`) e não é usado em nenhum número da entrega.
