# F9: indicadores de sanidade (negócio primeiro)

> **Status:** implementada e testada (11 testes), avaliada localmente com os dados reais do case.
> **Gate G9 ainda aberto:** o painel e os alertas precisam ir para o workspace; cada dono precisa aprovar as bandas que são premissa (AMB-21) e cadastrar o seu destino de notificação.

## Uma fonte, cinco artefatos
[`indicadores.yaml`](indicadores.yaml) define **39 indicadores** e **10 runbooks**. Cada indicador de negócio tem um **escopo**: `sao_rafael` (Parte I · o agente sobre um hospital, um mês) ou `rede` (Parte II · planilha do funil da rede inteira). O painel e os alertas mostram as duas partes separadas, e o validador recusa um indicador cujo escopo não bate com a fonte. Cada indicador tem:
- definição: métrica da camada semântica, SQL próprio ou limite de IA;
- banda, com a **origem** do número;
- severidade, dono, ação e runbook.

`python -m arvo.monitoring.gerar` produz, a partir desse arquivo:

| Artefato | Para quê |
|---|---|
| [`databricks/v_sanidade_status.sql`](databricks/v_sanidade_status.sql) | View `ops.v_sanidade_status`: 1 linha por indicador × recorte, com valor, banda, **status**, dono e runbook |
| [`../resources/alerts/monitoring.yml`](../../../resources/alerts/monitoring.yml) | 35 SQL alerts (v2) do bundle, um por indicador não-INFO, com o catálogo do target |
| [`dashboard/painel_sanidade.lvdash.json`](dashboard/painel_sanidade.lvdash.json) + [`../resources/dashboards/monitoring.yml`](../../../resources/dashboards/monitoring.yml) | Painel AI/BI: 1 · Parte I · Itens de conta São Rafael (1.696 itens com a decisão do agente), 2 · Parte I · Precisão e recall, 3 · Parte II · Funil da rede (em R$, coluna a coluna da planilha), 4 · Parte II · Inteligências (planilha linha a linha, meta e possível), 5 · Sanidade · indicadores, 6 · Semântica e dados, 7 · IA, 8 · Visão geral |
| [`RUNBOOKS.md`](RUNBOOKS.md) | Tabela de indicadores e passo a passo por runbook |

No CI, `python -m arvo.monitoring.gerar --checar` falha se algum artefato divergir do YAML.

## Como o status é decidido
| Status | Quando |
|---|---|
| **ALERTA** | valor fora da banda |
| **OK** | valor dentro da banda |
| **CALIBRANDO** | banda dinâmica (±3σ das competências anteriores) sem histórico suficiente. Nunca alerta com banda inventada |
| **SEM_DADO** | a fonte existe, mas não tem linhas |
| **SEM_FONTE** | a tabela ainda não existe (ex.: `fato_glosa_ciclo`, AMB-18). O indicador **continua no painel** |

Severidade **CRITICA** bloqueia o envio. [`portao.py`](portao.py) é a função única usada no teste local e no notebook [`portao_envio.py`](notebooks/portao_envio.py), que derruba a task de envio. Os críticos são os invariantes, as versões por run, as expectations de falha, a reversão e o bloqueio por política de dados.

## Mesma definição, dois dialetos
- **Databricks:** `MEASURE()` das UC Metric Views.
- **Local:** a mesma fórmula de `src/arvo/semantic/metricas.yaml` direto na tabela gold.

Um teste prova que os dois SQLs só diferem nessa tradução. Assim, o que roda localmente é o que vai rodar no workspace.

## Avaliação local com os dados do case
[`saida_local/PAINEL_LOCAL.md`](saida_local/PAINEL_LOCAL.md) e `painel_local.html`, gerados por `python -m arvo.monitoring.local`, em cerca de 40 s.

**Portão de envio: LIBERADO.** Todos os invariantes estão em 0.

**Alertas de negócio:**
- **Parte II · S01 · índice-norte da rede em 0,48%**, contra a meta de 2%; **S02 · atingimento em 24%**. Vem da planilha da rede, não do agente.
- **Parte I · S40 · taxa de glosa identificada no São Rafael em 10,2%** (CALIBRANDO: uma competência só). É valor identificado, em revisão, e não entra no índice-norte.
- **S12 · perda de registro de 30,4%**, contra o limite de 5%. É o maior vazamento depois da retenção, e a ação é com a TI da Parthenon (Alana).
- **S05/S06 · nenhuma regra atinge o piso de precisão.** O limite inferior do IC fica entre 72% (R2) e 88% (R4), coerente com a F8: tudo em REVISAO_HUMANA.
- **S07 · indevido não detectado estimado em 14%**, se o gabarito estiver certo.

**Alerta semântico:**
- **S23 · conflito semântico em 6,7% dos itens.** O conflito PS × Eletivo é marcado na conta, então todos os itens dessas contas contam. A banda vai para o AMB-21.

**Sem alerta:**
- Dados estão OK. IA fica SEM_DADO: sem chave de provedor não há chamada real, e a telemetria simulada da F3 fica de fora do painel.
- 39 recortes ficam em CALIBRANDO, porque o case tem uma única competência.

**Ressalva:** S05–S07 usam o gabarito como "rodada 0" de auditoria, com peso pós-estratificado da F8. Não é amostra probabilística: exercita o indicador, mas não decide go-live.

## Checklist do G9 (o que falta, humano ou de workspace)
1. Definir `warehouse_id` em `databricks.yml` e rodar `databricks bundle validate -t dev` (alerts exigem CLI ≥ 0.279.0).
2. `databricks bundle run monitoring_refresh -t dev`, que roda metric views → `v_ia_sanidade` → `v_sanidade_status` → portão.
3. Abrir o painel e fazer o **round-trip** do `.lvdash.json`: exportar do workspace e conferir com o gerado. O formato do arquivo não tem schema público; o teste local só garante consistência interna (datasets, campos e posições).
4. Cada dono cadastra o seu notification destination em [`destinos.yaml`](destinos.yaml). Só IDs, nunca e-mail no repositório.
5. Donos aprovam as bandas de premissa (AMB-21).
6. Ativar o data quality monitoring (anomaly detection) do Unity Catalog nos schemas silver e gold, para freshness e completude. O painel não reimplementa isso.

## Rodar
```bash
python -m arvo.monitoring.gerar
```
```bash
python -m arvo.monitoring.local
```
```bash
pytest tests/monitoring -v
```
