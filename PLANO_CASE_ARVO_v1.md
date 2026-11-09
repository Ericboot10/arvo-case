# Case Arvo × Parthenon × Hospital São Rafael — Plano completo para se destacar

> Feito a partir do contrato, do sinistro, do gabarito, da planilha de 6 meses e do seu rascunho.
> Os números marcados com **[protótipo]** vêm de um primeiro teste rápido (`prototipo_regras.py`). Reproduza e valide antes de apresentar.

---

## 0. A tese central (o que vai fazer você se destacar)

Se a banca lembrar de uma coisa só da sua apresentação, que seja esta:

1. **Parte 1: "Glosa sem cláusula não existe."** O agente é **determinístico e auditável**. O LLM só entra para *ler o contrato* e *redigir a justificativa*, nunca para *decidir* a glosa. Isso responde direto ao ceticismo do Dr. Ary.
2. **Parte 1: o gabarito também erra.** As 23 divergências do protótipo parecem ser, em grande parte, **inconsistências do próprio gabarito**. Você mostra que o agente segue o contrato ao pé da letra e trata cada divergência como uma *pergunta para o auditor*, não como um erro a esconder.
3. **Parte 2: o problema não é detectar, é converter.** A Arvo já **identifica 2,77% do sinistro** (R$ 1,94 mi/mês), acima da meta de 2%. Mas só **efetiva 0,48%** (R$ 336 mil). A meta de R$ 1,4 mi está no **funil**, não em mais inteligência.
4. **As duas partes se conectam.** A inteligência "Alto Markup" (R$ 350 mil identificados, mas só 12% de efetivação na média Arvo) é fraca porque não se apoia em contrato. O agente da Parte 1 (regra 2.2, preço acima do Anexo I) é justamente a versão **defensável** do markup.

---

## 1. Entendimento do contexto

### 1.1 Atenção a um detalhe
O contrato diz **Curitiba/PR** (as duas sedes), e não SC como está no seu rascunho. Confira antes de falar de "praça". Errar isso na frente da banca pega mal.

### 1.2 Personas: dor, o que querem ouvir e como ganhar cada uma

| Persona | Papel | Dor real (com dado) | O que ele/ela precisa ver | Como ganhar |
|---|---|---|---|---|
| **Paulo Antunes** | Diretor de Contas Médicas | Prometeu ≥2% (R$ 1,4 mi/mês) e está entregando 0,48%. O gap é de **R$ 1,06 mi/mês** | Número, caminho até a meta e prazo | Ponte de valor (waterfall) de R$ 336 mil para R$ 1,3 mi, com dono e data em cada degrau |
| **Alana Ambrosio** | Gerente de Contas Médicas | Opera o fluxo. **~30% do que é enviado à operadora não chega ao prestador** (perda de registro uniforme entre 62% e 75%) | Menos retrabalho e um fluxo que não vaza | Diagnóstico técnico da perda de registro mais um plano de integração. É o quick win dela |
| **Dr. Ary Aguiar** | Gerente de Auditoria Médica | Cético. O time dele retém **55% das inteligências técnicas** (envia 45%, contra 83% das administrativas). O risco dele é glosa errada, recurso e perda de credibilidade com o hospital | Evidência, controle e o time dele decidindo | Pacote de evidência por inteligência, piloto amostral, limiares definidos por ele e ranking de defensabilidade |

> Resposta ao "por que o Dr. Ary ligaria?": porque você mostra que **o time dele vira o gargalo de R$ 434 mil/mês** (retenção das inteligências ligadas) e oferece uma forma de liberar isso **sem que ele perca o controle**.

### 1.3 Perguntas para levar à Arvo (antes ou durante o case)
- Modelo de remuneração da Arvo: success fee sobre a economia **efetivada**, sobre a **identificada** ou fee fixo? (Isso muda o que você otimiza: efetivação.)
- O gabarito foi feito por auditor humano? Existe alguma regra fora do contrato (norma interna, TISS, rol ANS)?
- A chave de pacote é a **conta** (`id_conta`) ou a **internação/guia**? O hospital pode dividir contas?
- Houve reajuste ou aditivo do Anexo I entre jan/2025 e jun/2025?
- Formato real de entrada no cliente: TISS XML, API ou CSV?
- O que é "economia enviada para prestador" e por que ela difere da "enviada à operadora"? (Isso valida a hipótese da perda de registro.)

---

## 2. Regras extraídas do contrato

O PDF tem 4 páginas e **é só texto, sem imagens** (verificado: 0 imagens por página). Isso define a estratégia de extração.

| ID | Cláusula | Regra | Valor glosado | Tipo |
|---|---|---|---|---|
| R1 | **2.2** | `vl_unitario > valor Anexo I` | `(vl_unit − vl_tabela) × qtd` | Parcial (excedente) |
| R2 | **3.2 a / 3.3** | Conta com procedimento do Anexo II (31001012, 31309062, 30715016) e **taxa de sala do porte correspondente** cobrada à parte | `vl_total` | Integral |
| R3 | **3.2 b / 3.3** | Conta com pacote e cobrança de **fio 70520020** ou **compressa 70402600** | `vl_total` | Integral |
| R4 | **4.1 / 4.2** | Taxa **99999001** com `carater_atendimento = Eletivo` | `vl_total` | Integral |
| (fora) | **2.3** | Itens fora do Anexo I **não** entram na auditoria automática de preço | — | Exclusão explícita |
| (fora) | **3.4** | Diárias, UTI, cateter, medicamentos e SADT **não** integram o pacote | — | Proteção contra FP |

**Regra de conflito** (um item pode bater em mais de uma regra):
- Uma glosa por item, com valor ≤ `vl_total`. Nunca somar o excedente de preço com a glosa integral.
- A **cláusula principal** é a regra integral (3.3 ou 4.2), porque fundamenta 100% do valor. O excedente de preço (2.2) entra como **fundamento subsidiário**: "ainda que fosse devido, o valor excederia o Anexo I". É uma defesa em camadas: se o hospital derrubar a principal, ainda resta a subsidiária.
- No protótipo não houve sobreposição entre preço e regra integral, mas o agente precisa tratar o caso.

**Armadilhas de dados que já encontrei:**
- Números com vírgula decimal (`"132,93"`), datas por extenso (`"14 de junho de 2025"`) e BOM no CSV.
- Descrições diferentes entre sinistro e contrato (`Dipirona 500mg` vs `500 mg`, travessão `—` vs `-`). **Case sempre por código TUSS, nunca por descrição.**
- `vl_total = qtd × vl_unitario` foi validado: 0 inconsistências. Ainda assim, mantenha isso como checagem de qualidade.
- Taxa de sala aparece em contas **Ambulatorial/PS sem pacote** (20 itens). **Não glosar**, porque não há pacote.
- Fio/compressa aparecem **sem pacote** (31 itens). **Não glosar.**
- 9 taxas de urgência em **Pronto Socorro com caráter Eletivo**. Pela letra do contrato, são glosáveis ("caráter registrado"). São as mais frágeis em recurso (ver seção 5).
- A extração do PDF quebra linhas da tabela (ex.: "porte\n4", "R$18,00" sem espaço, "70520020⋅ 70402600"). Por isso é preciso ter um revisor.

---

## 3. Resultado do protótipo [protótipo]

| Métrica | Valor |
|---|---|
| Itens no sinistro | 1.696 itens · 320 contas · R$ 1.194.396,92 |
| Itens glosados | **369** |
| **Valor total glosado** | **R$ 121.948,93** (10,2% do sinistro) |
| Por regra: taxa de sala em pacote (3.3) | 50 itens · R$ 51.081,77 |
| Por regra: preço acima do Anexo I (2.2) | 175 itens · R$ 39.875,41 |
| Por regra: urgência em eletivo (4.2) | 77 itens · R$ 26.589,35 |
| Por regra: material de rotina em pacote (3.3) | 67 itens · R$ 4.402,40 |
| Gabarito | 263 itens (150 "Sim") |
| Matriz de confusão | TP 135 · FP 8 · FN 15 · TN 105 |
| **Precisão / Recall** | **94,4% / 90,0%** |

**Análise das divergências (o diferencial):**
- **8 FPs, que parecem ser erro do gabarito.** Todos contrariam a letra do contrato. Exemplos: IT00228, artroscopia cobrada a R$ 5.134 contra R$ 3.800 do Anexo I, marcada "Não"; IT00136, taxa de sala porte 4 numa conta com artroscopia (pacote porte 4), marcada "Não"; IT00522, fio de sutura numa conta com herniorrafia, marcado "Não"; e 4 diárias/consultas acima da tabela marcadas "Não".
- **15 FNs sem nenhuma base contratual.** Todos têm preço **abaixo** da tabela, não são itens de pacote nem taxa de urgência. Exemplos: IT00143, uma de 3 diárias idênticas, só uma marcada "Sim"; IT01167, dipirona ambulatorial a R$ 3,90 contra R$ 4,00; IT00492, colecistectomia (o próprio pacote!) abaixo da tabela.
- **Como apresentar:** monte uma tabela de divergências com a causa classificada (`erro provável do gabarito` · `regra não escrita?` · `problema de dado`). Mostre que, se o gabarito seguisse o contrato, a precisão iria para ~100%. A recomendação é **não glosar os FNs**. Glosa sem cláusula é indefensável em recurso, viola a cláusula 5.2 e desgasta o hospital. Leve os 15 casos ao Dr. Ary como "existe alguma regra que não está no contrato?". Se existir, vira parâmetro novo.
- Seja humilde no tom: "o agente diverge do gabarito em 23 itens; em todos que analisei, a decisão do agente é a sustentada pelo texto do contrato".

**Precisão vs recall: qual priorizar?**
- **FP** (glosa indevida) gera recurso, custo operacional dos dois lados, reversão, desgaste da relação com o prestador e, principalmente, **perda de confiança do Dr. Ary**, o que faz a retenção subir. No fim, um FP destrói valor futuro.
- **FN** (deixar de glosar) é dinheiro deixado na mesa, mas é recuperável: pode ser pego depois e não gera conflito.
- **Prioridade: precisão** no go-live (meta ≥ 98% para ligar o envio automático). O recall cresce depois, regra a regra. Use a planilha como argumento: a efetivação média da Arvo cai muito em inteligências pouco defensáveis (Alto Markup 12%, Terapia internação 13%). **Baixa precisão mata a efetivação.**
- Extra: calcule também a precisão e o recall **ponderados por R$**. Um FP de R$ 1.226 pesa mais do que um de R$ 9.

---

## 4. Arquitetura do agente no Databricks

### 4.1 Visão geral (arquitetura medalhão)

```
            ┌───────────────────────────── CONTRATO ─────────────────────────────┐
 PDF ──▶ Extrator A (pdfplumber, texto) ─┐                                      │
         Extrator B (LLM, JSON schema) ──┼─▶ Diff/Revisor ─▶ Aprovação humana ─▶ contract_params (Delta, versionado)
         [se houver imagem: OCR/visão]  ─┘                                      │
            └──────────────────────────────────────────────────────────────────┘
 SINISTRO
 CSV/API/TISS ─▶ BRONZE (raw, imutável, _ingest_ts, _source_file)
              ─▶ SILVER (tipado: decimal, data, enums normalizados, validações DQ / expectations)
              ─▶ GOLD   apontamentos (id_item, id_conta, regra, cláusula, justificativa, vl_glosado, versão_regra, versão_contrato)
                        resumo_glosa (por regra, por conta, total)
                        metricas_eval (precisão/recall vs gabarito)
                        monitoramento (saúde do agente)
```

### 4.2 Decisões de design (e por quê)
1. **Regras como dados, não como código.** Ficam em `config/prestadores/P001_hospital_sao_rafael.yaml` (tabela, pacotes, códigos, caráter). O motor é genérico. Trocar de hospital é trocar de YAML. Isso responde à pergunta 6.
2. **Motor determinístico em PySpark/pandas.** É reprodutível (mesma entrada, mesma saída), auditável e barato. Sem LLM no caminho da decisão.
3. **LLM só onde agrega:**
   - Extração estruturada do contrato com dupla extração independente e diff. Com o texto limpo, a transcrição manual mais um teste automático também é aceitável. Diga que **escolheu a confiabilidade**: para 17 linhas, a extração passa por checagem cruzada.
   - Redação da justificativa da glosa (pode ser template; o LLM é opcional).
   - Futuro: rascunho de resposta a recurso.
4. **Testes de sanidade do contrato** (o revisor automático):
   - Todo `cod_tuss` do sinistro está no Anexo I ou é tratado pela 2.3.
   - Cada pacote do Anexo II tem taxa de sala existente no Anexo I.
   - Os preços extraídos batem nas duas extrações.
   - Teste de cobertura: quantos itens ficaram "sem regra aplicável".
5. **Rastreabilidade:** cada apontamento grava `versao_contrato`, `versao_regra`, `run_id` e o hash da entrada. Use Delta time travel e a lineage do Unity Catalog.
6. **"Vamos rodar":** um comando roda tudo, local e no Databricks.
   - Local: `python -m arvo_agent run --prestador P001` (para a banca rodar sem Databricks)
   - Databricks: **Databricks Asset Bundle** com Job/Workflow `ingest → silver → rules → eval → report`
   - Opcional: Databricks Free Edition, para mandar link

### 4.3 Estrutura sugerida do repositório
```
arvo-case/
├── README.md                     # como rodar em 1 comando + resultados + decisões
├── databricks.yml                # Asset Bundle (job com as tasks)
├── config/prestadores/P001_hospital_sao_rafael.yaml
├── data/raw/                     # csvs + pdf do case
├── src/arvo_agent/
│   ├── contract/extract_text.py  # pdfplumber
│   ├── contract/extract_llm.py   # extração estruturada (opcional)
│   ├── contract/review.py        # diff + checagens
│   ├── ingest.py                 # bronze → silver (parsing pt-BR, DQ)
│   ├── rules/engine.py           # motor genérico
│   ├── rules/catalog.py          # R1..R4 parametrizadas
│   ├── resolve.py                # 1 glosa por item, cláusula principal + subsidiária
│   ├── evaluate.py               # matriz, P/R (contagem e R$), divergências
│   └── report.py                 # apontamentos.csv + resumo
├── notebooks/00..05_*.py         # mesma lógica, para demo no Databricks
├── tests/                        # 1 teste por regra + casos de borda listados na seção 2
└── outputs/apontamentos.csv, resumo.md, divergencias.csv
```

---

## 5. Defensabilidade em recurso (pergunta 5)

Critérios de decisão para pontuar cada regra (mostre como matriz):
- **Objetividade da evidência:** compara número com número ou depende de interpretação?
- **Dependência de dado informado pelo próprio prestador** (é a favor, quando o dado vem do hospital).
- **Espaço para argumento clínico** (é contra, porque abre discussão médica).
- **Clareza do texto** ("integralmente glosada" explícito? lista fechada de códigos?).
- **Sensibilidade a fatos externos** (reajuste, aditivo, agrupamento de contas).

| Regra | Defensabilidade | Por quê |
|---|---|---|
| **2.2 Preço acima do Anexo I** | **Mais defensável** | Número contra número numa tabela assinada pelo próprio hospital. Glosa só o excedente (proporcional, difícil chamar de abusiva). Zero espaço clínico. O único ataque é "houve reajuste ou aditivo", que se fecha checando a vigência |
| **3.3 Materiais de rotina** | Muito forte | Lista fechada com códigos no texto (3.2 b) e "integralmente glosada" explícito |
| **3.3 Taxa de sala** | Forte, com ressalva | Código explícito no Anexo II. Ponto de ataque: "porte correspondente" e o agrupamento por conta (se houver outra cirurgia não-pacote na mesma conta, a sala pode ser legítima) |
| **4.2 Urgência em eletivo** | **Mais frágil nos casos de PS** | Em internação eletiva é sólida. Mas depende 100% do campo `carater_atendimento`. Em **Pronto Socorro com caráter Eletivo** (9 itens), o hospital vai alegar erro de registro e urgência clínica, o que leva a discussão para o campo médico (território do Dr. Ary) |

Pode haver quem defenda que a 4.2 é a mais forte ("caráter registrado" é binário). Mostre os dois lados e posicione-se: **forte no geral, frágil no subconjunto PS/eletivo**. Sugestão de produto: marcar esses casos como "glosa com revisão humana".

**Item com várias regras:** cite como principal a regra **integral e de texto mais literal** e use as demais como subsidiárias. A justificativa enviada ao prestador deve conter a cláusula, o valor do contrato, o valor cobrado e o cálculo.
> Exemplo: "Glosa integral de R$ 1.226,03, item IT00136, Cláusulas 3.2(a) e 3.3: taxa de sala porte 4 (cód. 20103077) inclusa no pacote do procedimento 30715016 (Anexo II), cobrado na mesma conta G00021."

---

## 6. Parâmetros que mudam de prestador para prestador (pergunta 6)

**Vêm do contrato (YAML por prestador):**
- Tabela de preços (código, valor, unidade, vigência, índice de reajuste)
- Lista de pacotes: procedimento → taxa de sala/porte → materiais inclusos → itens explicitamente excluídos (3.4)
- Códigos de taxas especiais (urgência), caráter que autoriza a cobrança
- Tipo de glosa (integral vs excedente) e regra de conflito
- Exclusões da auditoria automática (2.3)
- Modelo de remuneração (fee-for-service, pacote, DRG/bundle, capitation), que muda o catálogo de regras aplicáveis
- Prazo de recurso, data de vigência

**Vêm da camada semântica/integração (mudam por cliente mesmo com o mesmo contrato):**
- Mapeamento de colunas, valores de enum (`Urgência` / `U` / código TISS 2), formatos de data e decimal
- Chave de agrupamento do pacote (conta, guia, internação, período)
- Tolerâncias (arredondamento, centavos)
- Thresholds de envio automático vs revisão humana, por regra

**Priorização por recorrência (seu ponto de melhoria contínua):** registre cada glosa com `categoria_regra × tipo_procedimento × prestador`. Se a mesma categoria se repete (ex.: material de rotina em cirurgia X), isso vira (a) um indicador para negociação com o prestador, (b) uma prioridade para template de regra entre hospitais e (c) um argumento comercial para a praça. No protótipo, **diária de enfermaria responde por 65 dos 175 casos de preço acima da tabela**: é um padrão do hospital, não um acaso.

---

## 7. Go-live: sombra antes, sempre (pergunta 7)

**Fases:**
1. **Backtest:** rodar em 3 a 6 meses de histórico e comparar com o que os auditores glosaram.
2. **Shadow mode (4 a 8 semanas):** o agente roda em produção, grava em `gold.apontamentos_shadow` e **não envia nada**. O time do Dr. Ary audita uma amostra estratificada por regra (todos os casos de alto valor e uma amostra aleatória dos demais).
3. **Liga por regra, não tudo de uma vez:** começar pela 2.2 e pela 3.3 materiais (mais objetivas). A 4.2 em PS entra com revisão humana.
4. **Envio automático com guarda-corpos:** human-in-the-loop para glosa > R$ X ou baixa confiança. Kill switch por regra.

**Critérios de "pronto" (definidos junto com o Dr. Ary):**
- Precisão ≥ 98% na amostra auditada por N semanas seguidas, por regra
- Nenhum erro crítico (glosa de item realmente devido de alto valor)
- Taxa de recurso projetada ≤ benchmark e reversão em recurso ≤ X%
- Estabilidade: variação semanal do hit rate dentro da banda esperada
- Qualidade do dado de entrada ≥ limiar (nulos, enums desconhecidos)
- Teste de integração ponta a ponta: o apontamento chega ao sistema do cliente com cláusula e valor (o que evita a "perda de registro")

---

## 8. Monitoramento pós go-live (pergunta 8)

Organize em camadas, como no seu rascunho:

| Camada | Indicadores |
|---|---|
| **Entrada (dados)** | Volume de itens/contas vs média · schema drift · % códigos fora do Anexo I · nulos/enums novos em `carater_atendimento` · atraso de ingestão |
| **Contrato** | Contrato vigente? Aditivo novo? Divergência entre as duas extrações |
| **Processo (agente)** | Hit rate por regra (itens e R$) vs banda histórica · % itens sem regra aplicável · tempo de execução · falhas de job |
| **Saída (qualidade)** | Precisão via auditoria amostral contínua · **FN via amostra aleatória de itens não glosados** (único jeito de medir recall em produção) · taxa de glosa do prestador (% do sinistro) |
| **Integração** | % apontamentos enviados que foram registrados no sistema do cliente (é a "perda de registro" da Parte 2) |
| **Negócio** | **Taxa de recurso do prestador** · **taxa de reversão em recurso** (a métrica-rainha da precisão real) · economia identificada → enviada → registrada → efetivada · tempo até efetivação |
| **LLM** (se usado) | Tokens, custo, latência, taxa de falha de schema, diff entre extrações |
| **Comportamento do prestador** | Queda de hit rate de uma regra pode ser **sucesso** (o hospital parou de cobrar) e não bug. Sinalize com uma tendência separada |

Alertas: hit rate fora de ±3σ, reversão em recurso > limiar, queda de registro e ingestão vazia.
Ferramentas no Databricks: Lakehouse Monitoring / Lakeview dashboard, alertas SQL e MLflow tracing para a parte LLM.

---

## 9. Parte 2: memo/deck da reunião de 6 meses

### 9.1 Funil de economia (dados da planilha, mês de jun/25)

| Etapa | R$/mês | % do identificado |
|---|---|---|
| Identificado (todas as inteligências) | **1.936.700** (2,77% do sinistro) | 100% |
| (−) Inteligências **desligadas** | −966.000 | **−49,9%** |
| (−) **Retidas pela operadora** (ligadas, não enviadas) | −433.720 | **−22,4%** |
| = Enviado à operadora | 536.980 | 27,7% |
| (−) **Perda de registro** (operadora → prestador) | −163.065 | −8,4% |
| = Enviado ao prestador | 373.915 | 19,3% |
| (−) Perda em recurso | −38.145 | −2,0% |
| **= Efetivado** | **335.770** (0,48% do sinistro) | 17,3% |

**Leituras-chave:**
- **Recurso não é o problema:** a efetivação sobre o enviado ao prestador é de 89,8%, em linha com a média Arvo. As inteligências funcionam quando chegam lá.
- **Perda de registro é sistêmica:** os ~30% de perda aparecem em **todas** as inteligências (entre 62% e 75% registrado). Quando é uniforme, a causa não é a inteligência, é **integração ou processo** (API, fila, rejeição no sistema da operadora). É o quick win mais barato.
- **A retenção é técnica:** técnicas são enviadas em 45%, administrativas em 83%. O gargalo é a **auditoria médica**, o time do Dr. Ary. As maiores retenções:
  - Pertinência de Materiais: R$ 187,5 mil retidos (só 25% enviado)
  - Sobreposição de procedimentos cirúrgicos: R$ 91 mil
  - Pertinência em PS: R$ 52,5 mil
  - Sobreposição de consultas: R$ 35 mil
- **Desligadas com alto potencial:**
  - Sobreposição de SADT: R$ 175 mil, bench 72%
  - Qtd excessiva de taxas: R$ 98 mil, **bench 96%**
  - SADT ambulatorial: R$ 77 mil, 88%
  - Reexecução SADT: R$ 63 mil, 84%
  - Qtd excessiva de materiais: R$ 56 mil, 78%
  - Códigos inválidos: R$ 49 mil, 77%
- **Não ligar às cegas:** Alto Markup (R$ 350 mil, bench **12%**) e Terapia internação (bench 13%) têm efetivação ruim em todos os clientes. Ligá-las gera recurso e queima credibilidade. **Reformular Alto Markup ancorado no Anexo I** (o agente da Parte 1).

### 9.2 Ponte de valor até a meta (estimativas, apresente como cenário)

| Alavanca | Premissa | Efetivado/mês |
|---|---|---|
| Hoje | — | R$ 336 mil |
| A. Corrigir perda de registro | registro 70% → 95% | ~R$ 458 mil (+R$ 122 mil) |
| B. Destravar retenção das ligadas | envio 55% → 90%, registro 95% | ~R$ 755 mil |
| C. Ligar desligadas com bench ≥ 50% | envio 90%, registro 95%, efetivação = bench | +~R$ 419 mil → **~R$ 1,17 mi** |
| D. Alto Markup reformulado (contrato) | efetivação 50% | +~R$ 150 mil → **~R$ 1,32 mi (1,9%)** |
| E. Melhoria contínua / novas regras contratuais | recorrência, outros anexos | fecha o gap até **≥ R$ 1,4 mi (2%)** |

Mensagem para o Paulo: **"a meta de 2% é atingível sem inventar nada novo: 85% do caminho está em destravar o que já identificamos."**

### 9.3 Proposta de melhoria
1. **Força-tarefa de registro (semanas 1 a 4).** Reconciliação ponta a ponta entre enviado e registrado, log de rejeições, retry/idempotência na API, alerta de fila.
2. **Programa "confiança técnica" com o Dr. Ary (semanas 2 a 8).**
   - Pacote de evidência por inteligência: precisão histórica, efetivação na base Arvo e exemplos reais
   - Piloto com amostra auditada
   - Limiares por inteligência definidos pelo time dele
   - Envio automático acima do limiar e fila priorizada por R$ × probabilidade de efetivação abaixo dele
   - Começar por Pertinência de Materiais (maior retenção, bench 85%)
3. **Ligar desligadas em ondas, por facilidade.**
   - Onda 1: administrativas de alto bench (Qtd excessiva de taxas 96%, Vias de acesso 89%, Códigos inválidos 77%)
   - Onda 2: técnicas de SADT (Sobreposição, Ambulatorial, Reexecução)
   - Cada onda passa por shadow
4. **Reformular inteligências de baixa efetivação** (Alto Markup, Terapia internação), ancorando no contrato.
5. **Ciclo de melhoria contínua:** registrar causa de retenção, de recurso e de reversão. Revisão mensal: o que se repete vira regra, cláusula de renegociação ou argumento para a praça.
6. **Upsell e expansão (o plus):** padrão de consumo do hospital (ex.: diária de enfermaria é o item mais cobrado acima da tabela), benchmarking entre prestadores da praça e insumo para renegociar contratos.

### 9.4 Requisitos: quem faz o quê

| Requisito | Arvo | Parthenon | Ambos |
|---|---|---|---|
| Reconciliação enviado vs registrado, correção da API | Engenharia, logs, retry | TI: logs do sistema de contas, ambiente de homologação | Reunião técnica semanal |
| Limiares e evidência por inteligência técnica | Pacote de evidência, dashboards | Dr. Ary: tempo do time para piloto e decisão | Comitê quinzenal de inteligências |
| Ligar desligadas | Ajuste de camada semântica, shadow | Aprovação de governança/jurídico | Critérios de go-live |
| Registrar motivos de retenção e recurso | Campo e taxonomia no produto | Time preenche o motivo | Revisão mensal |
| Contratos digitalizados de outros prestadores | Pipeline de extração | Envio dos contratos e aditivos | — |
| Patrocínio e meta | Customer success | Paulo: patrocínio executivo, meta oficial | QBR mensal com waterfall |

### 9.5 Roteiro do mini-deck (8 a 10 slides)
1. **Resumo executivo:** "Identificamos 2,77%, efetivamos 0,48%. A meta está no funil."
2. Funil de economia (waterfall)
3. Onde vaza: as 3 perdas (desligadas, retenção técnica, registro)
4. Por inteligência: matriz *valor identificado × efetivação benchmark*, para decidir onde atacar
5. Ponte de valor até 2% (cenários A a E)
6. Proposta 1: registro (Alana)
7. Proposta 2: confiança técnica (Dr. Ary)
8. Proposta 3: ondas de ativação mais reformulação
9. Requisitos e RACI
10. Plano 90 dias, KPIs e próximos passos (mais o plus: padrão de consumo e praça)

---

## 10. Passo a passo de execução

**Fase 1: Fundação (dia 1)**
- [ ] Rodar `prototipo_regras.py` e validar os números deste plano
- [ ] Criar o repo com a estrutura da seção 4.3 e o workspace Databricks (Free Edition serve)
- [ ] Subir os arquivos em um Volume do Unity Catalog (`/Volumes/arvo/case/raw`)

**Fase 2: Contrato → parâmetros (dia 1 e 2)**
- [ ] Extração A com pdfplumber, extração B (LLM com JSON schema ou transcrição manual)
- [ ] Diff automático e testes de sanidade, YAML final versionado
- [ ] Documentar por que esse método é confiável para este PDF (texto puro) e o que muda se vier escaneado (OCR/visão com revisor)

**Fase 3: Pipeline medalhão (dia 2)**
- [ ] Bronze: ingestão raw com metadados
- [ ] Silver: parsing pt-BR, tipagem, expectations (DQ), normalização de enums
- [ ] Gold: motor de regras, resolução de conflito, apontamentos com justificativa

**Fase 4: Avaliação (dia 3)**
- [ ] Matriz de confusão, P/R por regra e ponderado por R$
- [ ] `divergencias.csv` com causa classificada para cada um dos 23 casos
- [ ] Valor total glosado e quebra por regra
- [ ] Testes unitários (um por regra e por caso de borda)

**Fase 5: Respostas escritas (dia 3)**
- [ ] README/relatório respondendo às perguntas 1 a 8, uma seção cada (use as seções 3, 5, 6, 7 e 8 deste plano)

**Fase 6: Parte 2 (dia 4)**
- [ ] Notebook de análise do funil com os gráficos: waterfall, matriz valor × bench e envio técnico vs administrativo
- [ ] Mini-deck de 10 slides (roteiro 9.5)
- [ ] Dashboard Lakeview com funil e saúde do agente (diferencial visual)

**Fase 7: Polimento e ensaio (dia 5)**
- [ ] Rodar do zero numa máquina limpa: "um comando, mesmo resultado"
- [ ] Ensaiar o pitch em 3 versões: 1 minuto (tese), 5 minutos (case) e 15 minutos (completo)
- [ ] Preparar respostas para perguntas difíceis:
  - "Por que não usar LLM para decidir?"
  - "E se o gabarito estiver certo?"
  - "Como escala para 50 hospitais?"
  - "Por que o Dr. Ary confiaria?"
  - "Quanto custa rodar?"

---

## 11. Checklist "se destacar"
- [ ] Abrir com a tese (seção 0), não com a tecnologia
- [ ] Toda glosa com cláusula, valor de contrato, valor cobrado e cálculo
- [ ] Divergências do gabarito analisadas uma a uma, sem esconder
- [ ] Defender precisão com argumento de negócio (efetivação e confiança), não só técnico
- [ ] Mostrar que trocar de hospital é trocar de YAML
- [ ] Conectar Parte 1 e Parte 2 (Alto Markup ↔ regra 2.2; monitoramento ↔ funil)
- [ ] Falar com cada persona pela dor dela, com número
- [ ] Reprodutível em um comando, com testes
- [ ] Um visual forte: o waterfall do funil
