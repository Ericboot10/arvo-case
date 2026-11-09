# Camada semântica (Fase F2)

> **Status: rascunho v0.1.0, pendente do Gate G2.**
> Os artefatos foram propostos pelo comitê. Só passam a valer quando os donos assinam a tabela da seção 4 e as ambiguidades que bloqueiam regras estão `DECIDIDA`.

## 1. Por que esta camada vem antes do código
O agente de glosa só é confiável se "urgência", "pacote", "conta", "porte" e "glosa efetivada" significarem **a mesma coisa** para o contrato, para o dado, para o motor de regras, para o dashboard e para qualquer agente futuro.

Sem isso, o número pode até bater e ainda assim não responder à pergunta de negócio. Exemplos do próprio dado:
- **Caráter não é regime.** 114 itens estão em Pronto Socorro com caráter Eletivo.
- **Conta não é atendimento.** Em 11 casos o mesmo beneficiário tem mais de uma conta no mesmo dia, e 2 deles têm material de rotina cobrado na conta paralela.
- **O gabarito tem rótulos sem base contratual** (AMB-03).

## 2. Conteúdo

| Arquivo | O que é | Dono |
|---|---|---|
| [`glossario.yaml`](glossario.yaml) | 51 termos com definição, fonte, sinônimos, "não confundir com", dono e pendências | Especialista em Contas Médicas |
| [`dominios.yaml`](dominios.yaml) | Valores canônicos e mapeamento da origem (caráter, regime, tipo_item) e formatos de origem | Especialista / Eng. Dados |
| [`conceitos.yaml`](conceitos.yaml) | Taxonomia **universal** de conceitos (19) e **papéis contratuais** (6) | Especialista |
| [`map_tuss_conceito.yaml`](map_tuss_conceito.yaml) | 17 códigos TUSS → conceito, com as descrições observadas | Especialista |
| [`vinculos/PRT-2025-0417.yaml`](vinculos/PRT-2025-0417.yaml) | O que **este** contrato diz sobre cada código (rascunho por transcrição; a versão oficial sai da F3) | Jurídico |
| [`metricas.yaml`](metricas.yaml) | 34 métricas em 7 níveis (norte, meta, fator, guardrail, diagnóstico, sanidade, base), a **árvore do indicador-norte** e o **contrato de colunas das tabelas gold** | Analytics Engineer |
| [`funil.yaml`](funil.yaml) | Etapas do ciclo de vida da glosa, motivos RET/REG/REC e a ponte regra ↔ inteligência Arvo (propostas) | PM/CS + Auditor |
| [`perguntas_negocio.yaml`](perguntas_negocio.yaml) | 17 perguntas de negócio por persona, que são o **teste de aceite** da semântica e o benchmark do agente analítico | PM/CS |
| [`ontologia.md`](ontologia.md) | Modelo de entidades, hierarquia de conceitos e os 3 eixos que não podem ser confundidos | Arquiteto + Especialista |
| [`decision_log.md`](decision_log.md) | 19 ambiguidades (AMB-01 a AMB-19), cada uma com evidência, opções, recomendação e decisor | Comitê |
| [`tests/test_semantica.py`](tests/test_semantica.py) | Integridade, aderência do dado, aceite de negócio e árvore do norte | Analytics Engineer |
| [`databricks/01_carregar_semantica.py`](databricks/01_carregar_semantica.py) | Notebook que publica os YAMLs como tabelas em `<catalog>.semantic.*`, com comentários e tags | Eng. Dados |
| [`databricks/02_metric_views.sql`](databricks/02_metric_views.sql) | 6 UC Metric Views **geradas** de `metricas.yaml` por [`gerar_metric_views.py`](databricks/gerar_metric_views.py) (a fórmula existe em um lugar só), com sinônimos para agentes | Analytics Engineer |

**Decisão de design central:** a semântica separa o **conceito**, que é universal ("70520020 é fio de sutura"), do **papel contratual**, que vale por contrato ("no PRT-2025-0417 o fio é material de rotina incluso no pacote").

As regras são escritas sobre papéis. Para auditar outro hospital, muda só o arquivo em `vinculos/`.

## 3. Como validar
A partir da pasta `Arvo_Case`:
```bash
pip install pyyaml pandas pytest
```
```bash
pytest semantic/tests -v
```

Os testes verificam três coisas:
1. **Integridade:** toda referência entre glossário, conceitos, domínios, métricas, perguntas e vínculo existe, e toda pendência tem entrada no decision log.
2. **Aderência do dado:** todo código, descrição, caráter, regime e tipo_item do sinistro está coberto. Valor novo faz o teste falhar e a decisão vai para o Especialista.
3. **Aceite de negócio:** cada pergunta "hoje" é respondível só com métricas e dimensões definidas.

Na primeira execução, esse teste pegou dois erros semânticos de verdade nas próprias perguntas:
- "Taxa de glosa por cláusula" não tem sentido de negócio.
- "Atingimento da meta por inteligência" também não, porque a meta é do total.

As duas foram corrigidas e comentadas no YAML.

**No Databricks:**
1. Rode `databricks/01_carregar_semantica.py` com `catalog=arvo_dev`. Em `arvo_prod`, o notebook exige `status: aprovado_G2`.
2. Rode `databricks/02_metric_views.sql` com `:catalog`. Isso depende das tabelas gold da F5.

## 4. Gate G2: checklist e assinaturas

**Conteúdo**
- [ ] Glossário revisado termo a termo pelos donos. Status `proposto` → `aprovado`.
- [ ] Definições clínicas de urgência e emergência (T15, T16) validadas pelo Auditor.
- [ ] Domínio oficial TISS de "caráter do atendimento" confirmado (AMB-07). **Ainda não verificado:** a tabela está nos arquivos de terminologia da ANS.
- [ ] Mapa TUSS → conceito revisado (17 códigos), incluindo a origem do código 99999001.
- [ ] Definições do funil confirmadas com a Arvo (AMB-05) e premissas de granularidade (AMB-06).

**Decisões que bloqueiam regras (precisam estar DECIDIDA)**
- [ ] AMB-01 (urgência em PS Eletivo), que bloqueia R4
- [ ] AMB-02 (conta x atendimento), AMB-04 (sala ou material sem pacote), AMB-11 (porte), AMB-12 (regime), que bloqueiam R2 e R3
- [ ] AMB-13 (vigência e reajuste), que bloqueia R1
- [ ] AMB-14 (hierarquia de fundamento), que bloqueia o motor
- [ ] AMB-03 (gabarito), que bloqueia a avaliação F8. Não bloqueia regra.

**Técnico**
- [ ] `pytest semantic/tests` verde no CI
- [ ] Semântica carregada em `arvo_dev.semantic` e metric views criadas sobre a gold de dev
- [ ] Perguntas Q01 a Q10 respondidas por metric views e conferidas pelo dono de cada pergunta
- [ ] `versao` passa de `0.1.0` para `1.0.0` e `status` passa para `aprovado_G2` em todos os YAMLs

| Papel | Nome | Aprova | Data |
|---|---|---|---|
| Especialista em Contas Médicas | | glossário, domínios, conceitos, mapa | |
| Auditor Médico | | T15, T16, T30, AMB-01, AMB-03, AMB-08, AMB-10 | |
| Jurídico | | papéis contratuais, vínculo, AMB-02, AMB-04, AMB-11 a AMB-14 | |
| Analytics Engineer | | métricas, metric views, testes | |
| PM/CS | | perguntas de negócio, AMB-05, AMB-06 | |

## 5. Próximo passo depois do G2
- **F3 (contrato como dado):** substitui o `vinculos/PRT-2025-0417.yaml` transcrito pela versão extraída com citação literal verificada, consenso entre provedores e aprovação do Jurídico.
- **F5 (pipelines):** entrega `gold.fato_item_auditado` e `gold.fato_funil_economia` com as colunas de `metricas.yaml > tabelas_base`.
