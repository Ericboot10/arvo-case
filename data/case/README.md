# Dados do case

Os quatro arquivos que a Arvo enviou no case, **sem nenhuma alteração**. Todo número da entrega e do workspace Databricks sai deles. Nada foi gerado ou simulado.

| Arquivo | O que é | Onde é usado |
|---|---|---|
| `sinistro-hospital-saorafael.csv` | Itens de conta do Hospital São Rafael, jun/2025: 1.696 itens, 320 contas | Medalhão (F5), motor de regras (F6), apontamentos |
| `gabarito-auditoria.csv` | 263 itens rotulados pela auditoria (`indevido` Sim/Não) | Precisão e recall (F8) e auditoria rodada 0 (F9) |
| `Contrato-parthenon-x-hospital-sao-rafael.pdf` | Contrato PRT-2025-0417, Curitiba/PR | Regras e preços pactuados (F2/F3) |
| `Inteligencias_apos_6_meses.xlsx` | Funil de economia da rede inteira, 6 meses | Parte 2 e índice-norte |

A planilha é da operação inteira, com toda a rede. A Parte 1 é um mês de um único prestador. Por isso os números das duas partes não precisam bater.

No Databricks, os arquivos entram pelos volumes com [`src/arvo/platform/subir_dados_case.sh`](../../src/arvo/platform/subir_dados_case.sh). O catálogo fica marcado com a tag `origem_dado = case_arvo`.
