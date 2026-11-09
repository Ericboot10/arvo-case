# F6: motor de regras (determinístico)

> **Status:** implementado e testado com Spark local (13 testes) sobre o sinistro real, o sintético rotulado e casos de borda construídos. Integrado ao harness local e ao pipeline Lakeflow, que ainda **não foi executado num workspace**.
> As regras seguem as **recomendações** do decision log, mas as decisões AMB-01/02/04/11/13/14 continuam abertas. Mudou a decisão, muda o [`regras.yaml`](regras.yaml), não o código.

## Como funciona

```
gold.fato_item + silver.conta + gold.dim_item_contratado + gold.dim_contrato
   → enriquecer()  colunas semânticas e PAPÉIS CONTRATUAIS (a única visão que as regras enxergam)
   → avaliar()     regras.yaml → hits por item → fundamento principal + subsidiárias → valor → revisão → justificativa
   → gold.fato_apontamento (1 por item glosado)  ·  gold.fato_item_auditado (todos os itens)  ·  gold.dim_regra
```

| Regra | Cláusula | Condição (só papéis e conceitos) | Glosa | Revisão humana | Defensabilidade |
|---|---|---|---|---|---|
| R2 | 3.2(a), 3.3 | conta com pacote e item = sala do porte do pacote | integral | — | forte, com ressalva |
| R2B | 3.2(a), 3.3 | conta com pacote e sala de **outro** porte | integral | **sempre** (AMB-11) | frágil |
| R3 | 3.2(b), 3.3 | conta com pacote e material incluso | integral | — | muito forte |
| R4 | 4.1, 4.2 | taxa condicionada e caráter não permitido | integral | se regime = Pronto Socorro (AMB-01) | forte, frágil em PS |
| R1 | 2.1, 2.2 | preço pactuado e excedente > 0 | só o excedente | se > 5× o teto (E30) | mais forte |

**Pré-condição global:** atendimento dentro da vigência do contrato (AMB-13).

**Hierarquia (AMB-14):**
- Uma glosa por item. A regra integral (prioridade 1) é a principal, e as outras cláusulas ficam como **subsidiárias** (defesa em camadas).
- O valor glosado é sempre ≤ valor cobrado. Nunca se soma excedente com integral.

**Justificativa e evidência:**
- Templates determinísticos, com valores em R$ pt-BR.
- Exemplo real: *"Glosa integral de R$ 1.226,03 no item IT00136: taxa de sala (cód. 20103077) inclusa no pacote do procedimento 30715016 (Anexo II), cobrado na mesma conta G00021. Fundamento: Cláusulas 3.2(a) e 3.3."*

## Resultados

**Dado real (jun/2025):**

| Regra | Itens | Valor glosado |
|---|---|---|
| R1 preço acima do teto | 175 | R$ 39.875,41 |
| R2 sala em pacote | 50 | R$ 51.081,77 |
| R3 material de rotina em pacote | 67 | R$ 4.402,40 |
| R4 urgência em eletivo | 77 | R$ 26.589,35 |
| **Total** | **369** | **R$ 121.948,93** |

- É idêntico ao protótipo da v1, mas agora vem com governança.
- **9 em revisão humana:** as taxas de urgência em Pronto Socorro com caráter Eletivo.
- **Invariante M26 = 0**, calculada pela fórmula do contrato semântico.

**Dado sintético (verdade por construção):**
- **Precisão e recall de 100%.**
- Glosa total = manifesto do gerador.
- Fragmentação (AMB-02) e sala sem pacote (AMB-04) não são glosadas. PS Eletivo (AMB-01) vai para revisão.

**Bordas construídas:**

| Caso | Resultado |
|---|---|
| Sala de outro porte | R2B, com revisão |
| Fio em pacote e acima do teto | R3 integral, com 2.2 subsidiária e valor = cobrado |
| Sala ou compressa sem pacote | Não glosa |
| Urgência em PS com caráter Urgência | Não glosa |
| Diária a 6× o teto | R1, só o excedente, com revisão |
| Atendimento fora da vigência | Nada glosado e contabilizado |

## Garantias testadas
- **Regras como dados:** as expressões só usam `colunas_permitidas` (semântica e papéis contratuais). Nenhuma coluna crua da origem.
- **Contrato muda, glosa muda, código não muda:** um teto alterado num "aditivo" de teste muda os resultados da R1 e a versão do contrato gravada.
- **Reprodutível:** reprocessar dá os mesmos apontamentos, com o mesmo `id_apontamento` (hash de item + versão das regras + versão do contrato).
- **Invariantes `fail`** no pipeline (E40–E42): glosa > 0 e ≤ cobrado, com cláusula, evidência e justificativa. Status no domínio. A fração em revisão humana é medida (E43, `warn`).
- **Documentação = código:** o schema real de `fato_apontamento`, `fato_item_auditado`, `dim_regra` e `ponte_regra_inteligencia` é igual ao de `src/arvo/architecture/modelo.yaml`.

## Gate G6
- [x] 100% dos testes de regra e de borda passando
- [ ] Revisão do **Jurídico** sobre o texto das justificativas (os templates estão em `regras.yaml`)
- [ ] Decisões AMB-01, 02, 04, 11, 13 e 14 assinadas. Hoje o motor segue a recomendação do comitê
- [ ] Execução no workspace (pipeline Lakeflow) com contrato **aprovado** (F3). Hoje usa a versão `rascunho-F2`

## Rodar
```bash
pytest tests/rules -v
```
```bash
python -m arvo.medallion.local --sinistro data/case/sinistro-hospital-saorafael.csv --planilha data/case/Inteligencias_apos_6_meses.xlsx
```
