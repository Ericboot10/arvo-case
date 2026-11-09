# Como o sistema funciona

Guia para entender e explicar o projeto: o raciocínio, o que o agente faz com o sinistro, como rodar (inclusive com um mês novo) e o papel do Databricks.

**Sumário**
1. [O raciocínio em uma página](#1-o-raciocínio-em-uma-página)
2. [O agente, passo a passo](#2-o-agente-passo-a-passo)
3. [Como rodar](#3-como-rodar)
4. [Rodar outro mês](#4-rodar-outro-mês)
5. [Como o repositório está organizado](#5-como-o-repositório-está-organizado)
6. [O Databricks](#6-o-databricks)
7. [O agente analista](#7-o-agente-analista)

---

## 1. O raciocínio em uma página

O case pede um agente que leia a conta do Hospital São Rafael, compare com o contrato PRT-2025-0417 e aponte o que foi cobrado em desacordo. A pergunta que guiou o desenho não foi "como acho erro", e sim **"como uma glosa sobrevive a um recurso do hospital"**. Daí saem as decisões, na ordem em que foram tomadas:

| # | Decisão | Por quê | Onde |
|---|---|---|---|
| 1 | **Entender as palavras antes de escrever código** | "Urgência", "conta", "pacote", "porte" têm mais de um sentido. Ex.: "Pronto Socorro" é o *regime* do atendimento, não o *caráter*. Um atendimento eletivo no PS não prova cobrança indevida de urgência. Cada dúvida virou uma decisão registrada (AMB-01 a AMB-21) | `src/arvo/semantic/` (F2) |
| 2 | **O contrato vira dado, não código** | Preços do Anexo I e pacotes do Anexo II ficam numa tabela versionada. Outro hospital = outro contrato carregado, mesmo código. Cada valor precisa apontar o trecho do PDF de onde saiu | `src/arvo/semantic/vinculos/`, `src/arvo/contracts/` (F3) |
| 3 | **Limpar e conferir os dados antes de glosar** | Uma linha com valor inconsistente ou código desconhecido não pode fundamentar glosa. Ela vai para quarentena, com o motivo | `src/arvo/medallion/` (F5) |
| 4 | **Regras como uma lista legível** | Cada regra é uma condição, um valor e uma cláusula. Um advogado consegue ler `src/arvo/rules/regras.yaml` | `src/arvo/rules/` (F6) |
| 5 | **Toda glosa vem com a frase que a defende** | Cláusula, valores e cálculo, prontos para o recurso | `src/arvo/rules/regras.yaml`, campo `justificativa` |
| 6 | **Medir antes de confiar** | Precisão e recall contra o gabarito, com margem de erro. A prioridade é a precisão: glosa errada custa relacionamento e cai em recurso | `src/arvo/evaluation/` (F8) |
| 7 | **Não enviar nada sem evidência** | As regras começam em modo sombra: calculam, mas não enviam. Uma regra só passa a enviar sozinha quando prova precisão ≥ 95% | `src/arvo/rollout/` (F10), `src/arvo/monitoring/` (F9) |

A Parte 2 segue o mesmo raciocínio aplicado ao funil: a Arvo já **encontra** 2,77% do sinistro, mais que a meta de 2%, mas só 0,48% vira economia. O problema é converter, não detectar (`src/arvo/funnel/`).

---

## 2. O agente, passo a passo

Uma execução do agente lê o CSV do sinistro e devolve a lista de glosas. São seis etapas. As funções são as mesmas no seu computador e no Databricks.

```
sinistro.csv ─► 1. BRONZE ─► 2. SILVER ─► 3. CONTA ─► 4. GOLD ─► 5. MOTOR ─► 6. DESTINO
                 cópia fiel   tipado +     pacote,     preço do    regras do    enviar ou
                              semântica    porte,      contrato    YAML +       não enviar
                              quarentena   caráter     por item    justificativa
```

**1. Bronze: guardar o arquivo como veio** (`src/arvo/medallion/transformacoes.py`, `bronze_sinistro`)
Cada linha do CSV é gravada sem alteração, com o nome do arquivo e a hora da carga. Se alguém contestar um número, dá para voltar ao original.

**2. Silver: tipar e traduzir para a semântica** (`silver_item_conta_candidatos`)
- Converte "132,93" em número e "14 de junho de 2025" em data.
- Traduz o código TUSS para um **conceito** (`src/arvo/semantic/map_tuss_conceito.yaml`). Ex.: 70520020 (fio de sutura) → conceito `MATERIAL_SUTURA`, que o contrato trata como material de rotina do pacote.
- Traduz caráter e regime para valores canônicos (`src/arvo/semantic/dominios.yaml`). Ex.: "Pronto Socorro" → regime PS.
- Confere dez regras de qualidade (`src/arvo/medallion/expectations.yaml`, E01 a E10). A linha que falha em alguma vai para a **quarentena** com o motivo e **não é glosada**. Ex.: código TUSS que a semântica não conhece (E03), total diferente de quantidade × unitário (E08).

**3. Conta: olhar o item no contexto da conta** (`silver_conta`)
Várias regras dependem da conta inteira, não do item sozinho. Aqui se descobre se a conta tem um procedimento de pacote do Anexo II e de qual porte, e qual é o caráter do atendimento.

**4. Gold: cruzar com o contrato** (`fato_item`)
Cada item recebe o que o contrato diz dele: o preço teto do Anexo I, o excedente (cobrado − teto) e a versão do contrato e da semântica usadas. Dois invariantes param a execução se quebrarem, porque só quebram por bug (E31, E32).

**5. Motor: aplicar as regras** (`src/arvo/rules/motor.py` + `src/arvo/rules/regras.yaml`)
O motor é genérico: lê as regras do YAML e as aplica a cada item.

| Regra | Condição (resumida) | Valor glosado |
|---|---|---|
| R1 | item tem preço no Anexo I e foi cobrado acima do teto | só o excedente |
| R2 | taxa de sala do porte do pacote presente na conta | integral |
| R3 | material de rotina (lista fechada) em conta com pacote | integral |
| R4 | taxa de urgência em atendimento eletivo | integral |

- Antes de tudo, a pré-condição global: atendimento **dentro da vigência** do contrato (AMB-13).
- Se um item cai em mais de uma regra, a principal é a mais objetiva. As outras ficam como subsidiárias, para uma segunda defesa.
- Alguns casos vão para **revisão humana** em vez de glosa direta. Ex.: taxa de urgência em conta de PS com caráter eletivo (AMB-01).
- Toda glosa sai com a justificativa. Exemplo real: *"Glosa parcial de R$ 1.129,77 no item IT00001 (cód. 31001012): valor unitário cobrado R$ 5.329,77 acima do pactuado R$ 4.200,00 no Anexo I, multiplicado por 1 unidade(s). Fundamento: Cláusula 2.2."*
- Mais três invariantes param a execução se quebrarem (E40 a E42): glosa maior que o cobrado, glosa sem cláusula, status fora do domínio.

**6. Destino: enviar ou não** (`src/arvo/rollout/envio.py`)
Cada regra está num estágio (`src/arvo/rollout/estado_regras.yaml`). Hoje todas estão em **SHADOW**: a glosa é calculada e guardada, mas o destino é `NAO_ENVIAR`. Isso muda regra a regra, quando a precisão medida justificar.

**Depois da execução: avaliação** (`src/arvo/evaluation/`)
Os 263 itens do gabarito são comparados com a decisão do agente:
- **TP** (glosou e era indevido): 135;
- **FP** (glosou e não era): 8;
- **FN** (não glosou e era): 15;
- **TN** (não glosou e não era): 105.

Precisão = 135 ÷ 143 = 94,4%. Recall = 135 ÷ 150 = 90,0%. Os dois têm intervalo de confiança de 95%.

---

## 3. Como rodar

**Requisitos:** Python 3.12, Java 11 ou superior (o Spark precisa) e as bibliotecas:
```bash
pip install -e ".[dev]"
```

**Tudo de uma vez** (cerca de 4 minutos): agente, avaliação, painel local, rollout e funil da Parte 2.
```bash
python -m arvo.deliverables.rodar_tudo
```

**Só o agente sobre o sinistro do case:** grava `deliverables/apontamentos.csv` e `deliverables/resumo_glosa.json`.
```bash
python -m arvo.deliverables.gerar
```

**Só a avaliação contra o gabarito:** grava `src/arvo/evaluation/RELATORIO_AVALIACAO.md`.
```bash
python -m arvo.evaluation.relatorio
```

**Os testes** (188, cerca de 7 minutos):
```bash
python -m pytest -q
```

Nenhum desses comandos chama um provedor de IA. A extração do contrato usa respostas gravadas (replay), e os parâmetros do contrato usados pelo agente vêm da transcrição revisada em `src/arvo/semantic/vinculos/PRT-2025-0417.yaml`.

---

## 4. Rodar outro mês

O agente aceita qualquer arquivo no **mesmo layout** do sinistro do case:
```bash
python -m arvo.deliverables.gerar --sinistro caminho/sinistro_julho.csv
```
O resultado vai para `outputs/results/sinistro_julho/`, sem tocar nos entregáveis do case:

| Arquivo | Conteúdo |
|---|---|
| `apontamentos.csv` | uma linha por item glosado, com regra, cláusula, valores e justificativa |
| `resumo_glosa.json` | itens lidos, itens em quarentena, total glosado, % do sinistro, total por regra |
| `quarentena.csv` | itens que o agente **não auditou** e o motivo (só aparece se houver algum) |

Para escolher a pasta de saída:
```bash
python -m arvo.deliverables.gerar --sinistro caminho/sinistro_julho.csv --saida outputs/results/julho
```

**O que o arquivo precisa ter**
- **As mesmas 14 colunas, na mesma ordem:** `id_prestador, id_item, id_conta, id_beneficiario, dt_atendimento, carater_atendimento, tipo_conta, cod_tuss, desc_item, tipo_item, qtd, vl_unitario, vl_total, nome_prestador`. A leitura é por posição.
- **Datas por extenso**, como no case: "3 de julho de 2025".
- **Valores com vírgula decimal e sem ponto de milhar**, como no case: "5329,77".
- **Atendimentos dentro da vigência** do contrato (01/01/2025 a 31/12/2026). Fora dela, nada é glosado.

**O que acontece com o que é novo**
O sistema falha para o lado seguro: o que ele não entende não vira glosa, vai para a quarentena.
- Código TUSS que não está em `src/arvo/semantic/map_tuss_conceito.yaml` → quarentena **E03**. Para auditá-lo, o especialista inclui o código no mapa, com o conceito.
- Caráter ou regime fora do domínio (ex.: "Emergência") → quarentena **E04** ou **E05**. Nunca vira "Eletivo" por padrão (AMB-07).
- Valor que não fecha (total ≠ quantidade × unitário) ou data ilegível → quarentena **E08** ou **E09**.

Testei com uma cópia do arquivo do case com um código e um caráter alterados: os dois itens foram para `quarentena.csv` (E03 e E04), e os demais 1.694 itens foram auditados normalmente.

**O que não dá para saber num mês novo**
- **Precisão e recall:** só existem com um gabarito. Sem auditoria do mês, o agente diz *quanto glosaria*, mas não *quanto acertou*. Na operação, isso vem da amostra auditada mensalmente (`src/arvo/evaluation/amostragem.py`).
- **Outro hospital:** exige o contrato dele. As regras não mudam, porque usam papéis contratuais ("item com preço pactuado"), não códigos. Mudam os parâmetros do contrato (F3) e, se houver códigos novos, o mapa semântico.

**No Databricks**
Basta colocar o arquivo novo em `/Volumes/arvo_dev/bronze/landing/sinistro/` e rodar o job `medallion_run`. O pipeline percebe sozinho que chegou um arquivo novo.

Há uma limitação: hoje a regra de unicidade E01 olha o `id_item` em toda a bronze. Se o mês 2 reaproveitar os ids do mês 1 (IT00001...), os itens repetidos dos dois meses vão para a quarentena. Na operação real, a chave do item teria de incluir a competência ou o arquivo. Localmente, cada execução é isolada, e esse problema não existe.

---

## 5. Como o repositório está organizado

Todo o código está em `src/arvo/`, um subpacote por domínio, com os testes em `tests/<domínio>/`; os recursos do Databricks ficam em `resources/<tipo>/<domínio>.yml`. O padrão completo de nomes está em [`conventions.md`](conventions.md). O que o case pede cabe em quatro domínios; os outros mostram como o agente iria para produção numa empresa como a Arvo. Para ler o projeto, siga esta ordem:

**Núcleo: responde à Parte 1**

| Pasta | O que é |
|---|---|
| `data/case/` | os quatro arquivos do case, sem alteração |
| `src/arvo/semantic/` | vocabulário, mapa TUSS → conceito, contrato transcrito, decisões AMB |
| `src/arvo/medallion/` | leitura, limpeza, quarentena e cruzamento com o contrato |
| `src/arvo/rules/` | as regras (`regras.yaml`) e o motor que as aplica |
| `deliverables/` | respostas, apontamentos, total e o comando único |

**Prova: o agente está certo?**

| Pasta | O que é |
|---|---|
| `src/arvo/evaluation/` | precisão, recall, margem de erro, divergências contra o gabarito |
| `src/arvo/funnel/` | os números do funil da Parte 2 |

**Produção: como isso rodaria na Arvo**

| Pasta | O que é |
|---|---|
| `src/arvo/contracts/` | ler o PDF do contrato com IA e conferir cada valor contra o texto |
| `src/arvo/ai/` | núcleo de IA: ports, roteador, política de dados, telemetria e prompts |
| `src/arvo/agents/` | os agentes (analista e Genie) e os adapters de cada provedor |
| `src/arvo/monitoring/` | os indicadores, alertas e painel |
| `src/arvo/rollout/` | quando cada regra pode enviar glosa sozinha |
| `src/arvo/platform/`, `resources/`, `databricks.yml`, `.github/` | ambiente Databricks, jobs e deploy automático |
| `src/arvo/architecture/` | diagramas gerados a partir de um único arquivo |

Para um avaliador sem tempo: `README.md` → `deliverables/RESPOSTAS_CASE.md` → `src/arvo/rules/regras.yaml` → `deliverables/apontamentos.csv`.

---

## 6. O Databricks

### O que é
O Databricks é uma plataforma de dados na nuvem. Num lugar só, ele junta:
- **armazenamento** em tabelas (formato Delta), organizadas e com controle de acesso pelo **Unity Catalog**;
- **processamento** com Spark, sem servidor para administrar (serverless);
- **orquestração**: os jobs, que rodam etapas em ordem;
- **SQL e painéis** para o negócio;
- **alertas**.

### Para que serve neste case
Localmente, o projeto prova que o agente funciona com um arquivo. O Databricks mostra que **o mesmo código** roda como sistema: os dados ficam guardados com histórico, o acesso é controlado (LGPD), o painel fica aberto para o negócio e os alertas vigiam a qualidade. As funções de `src/arvo/medallion/transformacoes.py` e `src/arvo/rules/motor.py` são as mesmas nos dois lugares. Por isso os números batem: 369 glosas, R$ 121.948,93, precisão de 94,4% e recall de 90,0% no workspace e na execução local.

### De onde vêm os dados
Os arquivos não vão junto com o código: o `databricks.yml` exclui `data/case/` do deploy. Eles entram por **volumes**, que são pastas de arquivos com controle de acesso dentro do catálogo. O script `src/arvo/platform/subir_dados_case.sh` copia os quatro arquivos do case:

| Arquivo | Destino no workspace |
|---|---|
| sinistro | `/Volumes/arvo_dev/bronze/landing/sinistro/` |
| gabarito | `/Volumes/arvo_dev/bronze/landing/gabarito/` |
| planilha da Parte 2 | `/Volumes/arvo_dev/bronze/landing/inteligencias/` |
| contrato (PDF) | `/Volumes/arvo_dev/contracts/raw/` |

Tudo fica marcado com a tag `origem_dado = case_arvo`.

### Como fica organizado
O catálogo `arvo_dev` tem um schema por camada:

| Schema | O que guarda |
|---|---|
| `bronze` | o arquivo como veio |
| `silver` | dados tipados e com semântica |
| `gold` | itens cruzados com o contrato e as glosas |
| `quarantine` | o que foi rejeitado, com o motivo |
| `semantic` | o mapa TUSS e os domínios |
| `contracts` | o contrato como dado |
| `ops` | qualidade, métricas e decisões de envio |

Em produção haveria três catálogos, `arvo_dev`, `arvo_stg` e `arvo_prod`. O código promove de um para o outro; o dado não.

### O bundle: a infraestrutura como código
`databricks.yml` e a pasta `resources/` descrevem tudo o que existe no workspace: jobs, pipeline, painel e alertas. Um comando publica:
```bash
databricks bundle deploy -t free
```
O `-t` escolhe o ambiente:
- **free:** o Free Edition usado na demonstração;
- **dev**, **stg** e **prod:** os ambientes de uma operação real, que exigem contas corporativas.

### Os jobs, um por fase
Um job é uma sequência de tarefas que o Databricks executa em ordem.

| Job | O que faz | Lê | Grava |
|---|---|---|---|
| `platform_setup` | cria catálogo, schemas e volumes | — | `arvo_dev.*` |
| `semantic_load` | carrega o vocabulário e o mapa TUSS em tabelas | `src/arvo/semantic/*.yaml` | `semantic.*` |
| `medallion_run` | 1) lê a planilha da Parte 2; 2) roda o **pipeline** (bronze → silver → gold → motor); 3) coleta os resultados de qualidade | volumes de landing | `bronze.*`, `silver.*`, `gold.*`, `quarantine.*`, `ops.dq_resultados` |
| `evaluation_run` | carrega o gabarito e calcula precisão e recall | gabarito, `gold.fato_item_auditado` | `gold.v_avaliacao_gabarito`, `ops.v_precisao_recall` |
| `monitoring_refresh` | cria as métricas do painel, calcula o status de cada indicador e roda o portão de envio | gold e ops | `ops.v_sanidade_status` |
| `rollout_decide` | decide o destino de cada glosa: hoje tudo em `NAO_ENVIAR` | `gold.fato_apontamento` | `ops.rollout_destino` |
| `contracts_extract` | lê o PDF do contrato com IA | PDF | `contracts.*` |

O `contracts_extract` **não roda no Free Edition**: precisa de chave de um provedor de IA, e não vamos pôr resultado simulado no workspace.

**O pipeline** (`src/arvo/medallion/pipeline_lakeflow.py`) é a parte central do `medallion_run`. Ele é declarativo: diz quais tabelas devem existir e de onde cada uma vem, e o Databricks resolve a ordem. A leitura do sinistro usa o **Auto Loader**, que processa só os arquivos novos que aparecem na pasta. As regras de qualidade de `src/arvo/medallion/expectations.yaml` viram expectations do pipeline, com contagem de violações em cada execução.

### Painel e alertas
- **Painel "arvo-monitoring"**, com cinco páginas:
  1. Negócio: índice-norte e funil;
  2. **Precisão e recall**: matriz TP/FP/FN/TN e precisão por regra contra o piso de 95%;
  3. Semântica e dados;
  4. IA;
  5. Visão geral.
- **35 alertas SQL:** um por indicador, como precisão abaixo do piso ou taxa de reversão alta. No ambiente de desenvolvimento as agendas ficam pausadas.

### CI no GitHub
A cada envio ao repositório, o GitHub Actions roda os 214 testes. Os jobs de deploy para stg e prod existem, mas ficam pulados até haver workspaces e credenciais desses ambientes.

### Numa Arvo de verdade
- **Chegada dos dados:** os arquivos das operadoras chegam todo mês, ou continuamente, por integração. Caem no volume de landing, e o pipeline processa só o que é novo.
- **Um contrato por prestador:** o PDF passa pela F3 (IA + conferência contra o texto + aprovação do Jurídico) e vira parâmetros versionados. As regras não mudam.
- **Agendas ligadas:** o pipeline roda quando chega arquivo, o painel atualiza e os alertas avisam o time quando um indicador sai da faixa.
- **Três ambientes separados:** dev (com dado sintético, para quem não pode ver dado de paciente), stg e prod. Cada um tem o próprio catálogo e roda com uma conta de serviço, não com o usuário de uma pessoa.
- **Rollout regra a regra:** shadow por algumas semanas com auditoria por amostra, depois envio com revisão humana e, por fim, envio automático até um teto de valor. Uma regra cuja taxa de reversão em recurso passa de 5% é desligada automaticamente.

---

## 7. O agente analista

Um agente que responde perguntas de negócio ("quanto glosamos por cláusula?", "qual a precisão do motor?", "quanto falta para a meta?") consultando a camada semântica. Detalhes em [`src/arvo/agents/analyst/README.md`](../src/arvo/agents/analyst/README.md).

- **Genie é a prioridade para os dados.** Ele entende as metric views publicadas no Unity Catalog e roda dentro da plataforma. O espaço é configurado por código ([`src/arvo/agents/genie/espaco.yaml`](../src/arvo/agents/genie/espaco.yaml)), com instruções tiradas do glossário e das decisões AMB.
- **O orquestrador é trocável:** a API do Claude, com fallback para um modelo hospedado no Databricks. Ele escolhe as ferramentas e escreve a resposta, citando a fonte de cada número.
- **Se o Genie falhar,** o agente consulta as metric views de forma estruturada: escolhe medida e dimensão do catálogo, e o SQL é montado por código.
- **O agente não glosa.** Ele explica, investiga e responde. Quem glosa continua sendo o motor.
- **O modelo nunca recebe dado de pessoa, conta ou data de atendimento:** o resultado de cada consulta é reduzido antes de chegar a ele.

