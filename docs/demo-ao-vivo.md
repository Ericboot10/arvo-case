# Demonstração ao vivo: o agente na prática

Três formas de mostrar o agente funcionando, da mais robusta para a mais vistosa. Todas usam só os arquivos do case.

| | O que mostra | Precisa de | Quem consegue reproduzir |
|---|---|---|---|
| **A · Agente de glosa (Python, local)** | O agente lê o sinistro e o contrato e gera as 369 glosas com cláusula e justificativa | Python 3.12, Java 11+ e o repositório | Qualquer pessoa com acesso ao repositório |
| **B · Genie no Databricks** | Perguntas em português sobre os resultados, com o SQL de cada resposta | O workspace (Free Edition) já carregado | Você, compartilhando a tela |
| **C · Agente analista (Python + Databricks)** | O mesmo tipo de pergunta pelo terminal, com o rastro de ferramentas | B, mais `databricks auth login` | Você; outra pessoa precisa do próprio workspace |

## A · Agente de glosa (o que eles devem conseguir reproduzir)

```bash
git clone https://github.com/Ericboot10/arvo-case.git
```
```bash
cd arvo-case && python3.12 -m venv .venv && source .venv/bin/activate
```
```bash
pip install -e ".[dev,agents]"
```
```bash
python -m arvo.deliverables.gerar
```

Resultado esperado em `deliverables/resumo_glosa.json`: **369 glosas, R$ 121.948,93, 10,21% do sinistro**, 9 em revisão humana.
`deliverables/apontamentos.csv` tem uma linha por glosa, com regra, cláusula, valor e a justificativa.

**Outro mês, mesmo layout** (o teste mais forte, se eles trouxerem um arquivo novo):

```bash
python -m arvo.deliverables.gerar --sinistro caminho/novo_mes.csv
```

Saída em `outputs/results/novo_mes/`. Linha com dado inválido (código TUSS desconhecido, caráter fora do domínio, total
inconsistente) não vira glosa: vai para `quarentena.csv` com o motivo.

**Determinismo:** rodar duas vezes dá o mesmo arquivo. A IA não decide glosa; o motor aplica as regras do contrato.

Tudo de uma vez (entregáveis, avaliação, painel local), cerca de 4 minutos:

```bash
python -m arvo.deliverables.rodar_tudo
```

## B · Genie no Databricks

Abra o espaço `arvo-analyst-genie-dev` no workspace e pergunte. Perguntas que já foram conferidas contra os entregáveis:

1. "Quanto foi glosado por cláusula no Hospital São Rafael?" → 3.3: R$ 55.484,17 · 2.2: R$ 39.875,41 · 4.2: R$ 26.589,35
2. "Qual a precisão e o recall do motor contra o gabarito?" → 94,4% e 90,0%
3. "Qual o índice-norte da rede no mês mais recente?" → 0,48% (meta 2%)

Sempre abra o SQL da resposta: é ele que prova de onde veio o número. O painel `arvo-monitoring-free` mostra os 1.696
itens com a decisão do agente (página 1) e a planilha de inteligências linha a linha (página 4).

## C · Agente analista pelo terminal

```bash
python -m arvo.agents.analyst "Quanto foi glosado por cláusula em junho no Hospital São Rafael?"
```

Sem `ANTHROPIC_API_KEY`, o orquestrador é o modelo servido no Databricks (`databricks-gpt-oss-120b`). Com `--rastro`,
mostra cada ferramenta chamada e o SQL. Benchmark das 8 perguntas de referência:

```bash
python -m arvo.agents.analyst.benchmark --alvo genie
```

## Antes de apresentar

- O repositório é **privado**: quem for reproduzir precisa ser convidado como colaborador.
- Rode A uma vez na máquina da apresentação (a primeira execução do Spark é mais lenta).
- Abra o workspace e o Genie antes; a Free Edition pode demorar a acordar o warehouse.
