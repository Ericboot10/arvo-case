# F8: avaliação científica

> **Status:** implementada e testada (12 testes). O relatório completo, que responde à **pergunta 3 do case**, está em [`RELATORIO_AVALIACAO.md`](RELATORIO_AVALIACAO.md).
> **Gate G8 ainda aberto:**
> - a adjudicação **real** das divergências depende de dois revisores humanos (o pacote está pronto em [`adjudicacao/`](adjudicacao/));
> - a matriz de custo é uma premissa a aprovar (AMB-20).

## Achados principais

1. **Precisão 94,4% [89,3% – 97,1%] · Recall 90,0% [84,2% – 93,8%]** na amostra (IC de Wilson). Em R$, a precisão é 92,8%.
2. **O gabarito é uma amostra enriquecida, e enriquecida em função do próprio resultado:**
   - Reponderar só por código TUSS falha no teste de validade: prevê **791 glosas onde o motor faz 369**.
   - Pós-estratificar por **código × decisão do motor** passa no teste.
   - Por esse método, a precisão populacional é **94,5%** (estável) e o recall populacional é **65,5% [57,5% – 74,2%]**, **se** o gabarito estiver certo.
3. **As 23 divergências têm causa provável:**
   - os **8 FP** são regras contratuais de condição objetiva marcadas "Não";
   - os **15 FN** não têm base contratual (preço ≤ teto em todos).
   - O teste de permutação (p ≈ 0,85) **não** mostra concentração em nenhum conceito: o padrão é de **ruído de rotulagem**, não de regra escondida.
4. **Priorizar precisão**, com critério verificável: a matriz de custo compara o custo esperado do FP no envio automático com o custo da revisão humana, e há um piso de 95% no limite inferior do IC.
5. **Nenhuma regra vai para envio automático com o gabarito atual.** Nem no melhor cenário (R1 67/67 → limite inferior 94,6%; R4 29/29 → 88,3%). Quem decide é o **shadow**, com a amostra auditada por regra calculada aqui: 91 / 40 / 50 / 55, mais 360 não glosados.

## Módulos

| Arquivo | O que faz |
|---|---|
| [`metricas.py`](metricas.py) | Wilson, bootstrap **por conta** (cluster), métricas em R$, precisão por regra, estimativa populacional Horvitz–Thompson com **teste de validade embutido**, κ de Cohen |
| [`divergencias.py`](divergencias.py) | Causa provável de cada FP/FN e teste de permutação "regra escondida × ruído" |
| [`adjudicacao.py`](adjudicacao.py) | Pacote **cego**: divergências + igual número de controles, embaralhados, sem decisão do motor nem rótulo. Adjudicação com κ e terceiro revisor |
| [`custos.yaml`](custos.yaml) + [`decisao.py`](decisao.py) | Matriz de custo (premissas AMB-20) → modo por regra: AUTOMATICO / REVISAO_HUMANA / BLOQUEADO |
| [`amostragem.py`](amostragem.py) | Plano amostral do shadow e da auditoria contínua, com **peso amostral** (M10 e M25 agora são ponderadas) |
| [`relatorio.py`](relatorio.py) | Gera `RELATORIO_AVALIACAO.md`, `resultados.json` e o pacote de adjudicação |

## Adjudicação real (próximo passo humano)
1. Envie `adjudicacao/planilha_cega_revisor_A.csv` ao **Auditor Médico** e `..._B.csv` ao **Especialista em Contas Médicas**, sem a chave.
2. Cada revisor preenche `decisao` (INDEVIDO / DEVIDO / INCONCLUSIVO), `clausula_fundamento` e `comentario`.
3. O Cientista de Dados roda `adjudicacao.adjudicar(a, b, chave)`: meta de **κ ≥ 0,8**. Discordâncias vão para o Jurídico.
4. Rode `aplicar_rotulos` e reemita o relatório com o rótulo adjudicado. As métricas passam a valer para decisão.

## Rodar
```bash
pytest avaliacao_cientifica/tests -v
```
```bash
python -m avaliacao_cientifica.relatorio
```
O relatório leva cerca de 30 s, porque roda o motor da F6 com Spark local.
