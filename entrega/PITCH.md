# Pitch: 1, 5 e 15 minutos

## 1 minuto
O agente encontrou **R$ 121.948,93 em 369 cobranças indevidas** no sinistro do São Rafael. Cada uma tem a cláusula, o valor pactuado e o cálculo, e a **precisão é de 94%** contra o gabarito. Mesmo assim, eu **não ligaria o envio automático hoje**: nenhuma regra tem evidência suficiente para isso, e uma glosa errada custa a confiança do Dr. Ary. O plano é shadow por regra, com critérios medidos e aprovação humana para promover.

Na Parte 2, a Arvo já identifica 2,77% do sinistro, mas só 0,48% vira economia. O gargalo é converter, não detectar. Três frentes, cada uma com um dono na Parthenon, levam a 1,90%.

## 5 minutos
| Tempo | Mensagem | Evidência |
|---|---|---|
| 0:00 | **Antes do código, o significado.** "Urgência", "conta" e "porte" foram definidos com o negócio. Pronto Socorro é regime, não caráter | Glossário e decision log (AMB-01) |
| 0:45 | **Contrato como dado.** Três leitores independentes e um juiz; cada valor precisa de um trecho literal do PDF; o Jurídico aprova. Dado do sinistro nunca vai a um modelo externo | F3 e F7 |
| 1:30 | **Resultado:** R$ 121,9 mil, R1 a R4, com justificativa por item | `apontamentos.csv` |
| 2:15 | **Precisão antes de recall**, por custo e não por opinião. As divergências parecem erro de rótulo, e o gabarito não é amostra aleatória | F8 |
| 3:00 | **Produção:** shadow, canário, automático, com teto de valor calculado e rebaixamento automático | F10 |
| 3:45 | **Saúde do agente:** 38 indicadores, negócio primeiro; invariante quebrado bloqueia o envio | F9 |
| 4:20 | **Parte 2:** três perdas, três donos, 1,90% no cenário agressivo; o resto vem de identificar mais | Deck |

## 15 minutos
1. **O problema e as pessoas** (2 min): Paulo quer 2%; o Dr. Ary é cético; Alana precisa de integração. Cada número da apresentação responde a um deles.
2. **Semântica e comitê** (2 min): por que refazer depois de um protótipo que já "acertava".
3. **Contrato como dado e IA independente de provedor** (2 min): consenso, grounding, golden set por provedor, política de dados.
4. **Motor e resultado** (2 min): as cinco regras, o total e um apontamento lido em voz alta.
5. **Avaliação** (2 min): matriz de confusão, IC, viés do gabarito, divergências.
6. **Produção e monitoramento** (2 min): ambientes, shadow, critérios, painel e portão.
7. **Parte 2** (2 min): o deck.
8. **Próximos 90 dias e o que preciso da Arvo** (1 min).

## Perguntas difíceis
| Pergunta | Resposta curta |
|---|---|
| **Por que não deixar o LLM decidir a glosa?** | Glosa precisa ser reproduzível e defensável em recurso. O LLM lê o contrato uma vez, com consenso e trecho literal; a decisão por item é determinística e sai igual em toda execução |
| **E se o OpenAI ou o Anthropic cair amanhã?** | O agente continua glosando: o motor não chama IA. A extração tem adapters de famílias diferentes, fallback, circuit breaker e um extrator determinístico. Trocar de provedor exige passar no golden set antes |
| **Por que confiar no gabarito?** | Não confio cegamente. Ele foi escolhido de forma ligada à decisão do motor; corrigido, a precisão se mantém (94,5%) e o recall cai (65,5%). As 23 divergências parecem erro de rótulo, e há um pacote de adjudicação cega para provar |
| **Por que precisão e não recall?** | Uma glosa errada custa recurso, atrito e a confiança do Dr. Ary, o que trava o funil inteiro (Parte 2). Uma glosa não feita é recuperável. A matriz de custo transforma isso num critério |
| **Como escala para 50 hospitais?** | As regras valem para papéis contratuais, não para códigos. Hospital novo = contrato extraído + arquivo de vínculos + mapa semântico. Nenhuma linha de código muda, e a semântica vira ativo reusável na praça |
| **Quanto custa por contrato?** | A IA roda por contrato (e por aditivo), não por item de conta: poucas chamadas por documento. A telemetria registra tokens e custo por chamada; o número real sai na primeira extração com chaves reais |
| **Por que não ligar e corrigir depois?** | Porque a primeira impressão do Dr. Ary define a retenção técnica, que hoje já custa R$ 434 mil por mês. O shadow custa cerca de 150 h de auditoria e protege essa confiança |
| **Por que os números da Parte 1 e da Parte 2 não batem?** | Não precisam: a Parte 1 é um mês de um único prestador (R$ 1,19 mi de sinistro); a planilha da Parte 2 é a operação inteira, com toda a rede (R$ 70 mi por mês). O que conecta as duas é o método: o R1 da Parte 1 é a forma defensável de religar o Alto Markup |

## Perguntas para a Arvo
- **Modelo comercial:** fee for service ou participação na economia? Isso muda qual etapa do funil a Arvo prioriza.
- **Benchmark:** a efetivação média dos outros clientes é efetivado ÷ enviado ao prestador?
- **Histórico:** a Parthenon tem 3 a 6 meses de decisões da auditoria para o backtest?
- **Inteligências desligadas:** por que estão desligadas? Decisão do cliente, capacidade da auditoria ou limitação técnica?
- **Praça:** quantos hospitais da região de Curitiba já são clientes, e o que os outros têm em comum?

## Lembretes
- O contrato é de **Curitiba/PR**, não de SC.
- Separe o que está **implementado** (e testado) do que está **especificado**: tabela no fim de `RESPOSTAS_CASE.md`.
- Compartilhe o memo e o deck pelo menu Share antes da reunião.
