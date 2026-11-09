# F9: indicadores de sanidade (negócio primeiro)

> **Status:** implementada e testada (11 testes), avaliada localmente com os dados reais do case.
> **Gate G9 ainda aberto:** o painel e os alertas precisam ir para o workspace; cada dono precisa aprovar as bandas que são premissa (AMB-21) e cadastrar o seu destino de notificação.

## Uma fonte, cinco artefatos
[`indicadores.yaml`](indicadores.yaml) define **38 indicadores** e **10 runbooks**. Cada indicador tem:
- definição: métrica da camada semântica, SQL próprio ou limite de IA;
- banda, com a **origem** do número;
- severidade, dono, ação e runbook.

`python -m sanidade.gerar` produz, a partir desse arquivo:

| Artefato | Para quê |
|---|---|
| [`databricks/v_sanidade_status.sql`](databricks/v_sanidade_status.sql) | View `ops.v_sanidade_status`: 1 linha por indicador × recorte, com valor, banda, **status**, dono e runbook |
| [`../resources/alertas_sanidade.yml`](../resources/alertas_sanidade.yml) | 35 SQL alerts (v2) do bundle, um por indicador não-INFO, com o catálogo do target |
| [`dashboard/painel_sanidade.lvdash.json`](dashboard/painel_sanidade.lvdash.json) + [`../resources/painel_sanidade.yml`](../resources/painel_sanidade.yml) | Painel AI/BI: 1 · Negócio, 2 · Semântica e dados, 3 · IA, 4 · Visão geral |
| [`RUNBOOKS.md`](RUNBOOKS.md) | Tabela de indicadores e passo a passo por runbook |

No CI, `python -m sanidade.gerar --checar` falha se algum artefato divergir do YAML.

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
- **Local:** a mesma fórmula de `semantic/metricas.yaml` direto na tabela gold.

Um teste prova que os dois SQLs só diferem nessa tradução. Assim, o que roda localmente é o que vai rodar no workspace.

## Avaliação local com os dados do case
[`saida_local/PAINEL_LOCAL.md`](saida_local/PAINEL_LOCAL.md) e `painel_local.html`, gerados por `python -m sanidade.local`, em cerca de 40 s.

**Portão de envio: LIBERADO.** Todos os invariantes estão em 0.

**Alertas de negócio:**
- **S01 · índice-norte em 0,48%**, contra a meta de 2%; **S02 · atingimento em 24%**.
- **S12 · perda de registro de 30,4%**, contra o limite de 5%. É o maior vazamento depois da retenção, e a ação é com a TI da Parthenon (Alana).
- **S05/S06 · nenhuma regra atinge o piso de precisão.** O limite inferior do IC fica entre 72% (R2) e 88% (R4), coerente com a F8: tudo em REVISAO_HUMANA.
- **S07 · indevido não detectado estimado em 14%**, se o gabarito estiver certo.

**Alerta semântico:**
- **S23 · conflito semântico em 6,7% dos itens.** O conflito PS × Eletivo é marcado na conta, então todos os itens dessas contas contam. A banda vai para o AMB-21.

**Sem alerta:**
- Dados estão OK. IA fica SEM_DADO: sem chave de provedor não há chamada real, e a telemetria simulada da F3 fica de fora do painel.
- 38 recortes ficam em CALIBRANDO, porque o case tem uma única competência.

**Ressalva:** S05–S07 usam o gabarito como "rodada 0" de auditoria, com peso pós-estratificado da F8. Não é amostra probabilística: exercita o indicador, mas não decide go-live.

## Checklist do G9 (o que falta, humano ou de workspace)
1. Definir `warehouse_id` em `databricks.yml` e rodar `databricks bundle validate -t dev` (alerts exigem CLI ≥ 0.279.0).
2. `databricks bundle run f9_sanidade -t dev`, que roda metric views → `v_ia_sanidade` → `v_sanidade_status` → portão.
3. Abrir o painel e fazer o **round-trip** do `.lvdash.json`: exportar do workspace e conferir com o gerado. O formato do arquivo não tem schema público; o teste local só garante consistência interna (datasets, campos e posições).
4. Cada dono cadastra o seu notification destination em [`destinos.yaml`](destinos.yaml). Só IDs, nunca e-mail no repositório.
5. Donos aprovam as bandas de premissa (AMB-21).
6. Ativar o data quality monitoring (anomaly detection) do Unity Catalog nos schemas silver e gold, para freshness e completude. O painel não reimplementa isso.

## Rodar
```bash
python -m sanidade.gerar
```
```bash
python -m sanidade.local
```
```bash
pytest sanidade/tests -v
```
