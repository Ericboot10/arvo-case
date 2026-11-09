"""F9 · Avalia o painel de sanidade localmente (Spark local) com o MESMO SQL gerado para o Databricks
(dialeto local: fórmula da métrica em vez de MEASURE()). Prova que as definições rodam e mostra o estado atual.

Fontes locais:
  - pipeline F5/F6 sobre o sinistro real (medalhao.local.executar)
  - funil da Parte 2 (planilha de inteligências)
  - ops.v_ia_sanidade: o próprio SQL da F7 (ia/databricks/v_ia_sanidade.sql) sobre o llm_calls.jsonl do run demo da F3
  - gold.fato_auditoria_amostral: rodada 0 = gabarito do case, com peso pós-estratificado por código × decisão
    do motor (F8). NÃO é amostra probabilística: serve para exercitar S05–S07, não para decidir go-live.

  python -m sanidade.local       grava sanidade/saida_local/{status.json, PAINEL_LOCAL.md, painel_local.html}
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sanidade import gerar
from sanidade.portao import avaliar_portao

RAIZ = gerar.RAIZ
SAIDA = gerar.AQUI / "saida_local"
PLANILHA = RAIZ / "arvo.case" / "Inteligencias_apos_6_meses.xlsx"
LLM_CALLS = sorted((RAIZ / "contratos" / "runs").glob("*/*/llm_calls.jsonl"))

SCHEMA_LLM = ("call_id string, run_id string, task_id string, ts_inicio double, ambiente string, provedor string, "
              "adapter string, modelo_pedido string, modelo_servido string, fallback_de string, "
              "params_ignorados map<string,string>, input_tokens bigint, output_tokens bigint, cache_read_tokens bigint, "
              "reasoning_tokens bigint, custo_estimado_usd double, cache_hit_local boolean, latencia_ms double, "
              "stop_normalizado string, schema_valido boolean")


def _select_da_view(arquivo: Path, view: str) -> str:
    """Extrai o SELECT de um CREATE VIEW ... AS <select>; para rodar o mesmo SQL no Spark local."""
    txt = "\n".join(ln for ln in arquivo.read_text("utf-8").splitlines() if not ln.strip().startswith("--"))
    m = re.search(rf"CREATE OR REPLACE VIEW {re.escape(view)}.*?\bAS\b\s*(WITH .*|SELECT .*)", txt, re.S)
    return m.group(1).strip().rstrip(";")


def auditoria_do_gabarito(spark, out: dict):
    """gold.fato_auditoria_amostral local a partir do gabarito (pós-estratificação cod_tuss × pred, como na F8)."""
    from avaliacao_cientifica.dados import base_avaliacao

    base, _ = base_avaliacao(spark, out)
    pop = base.groupby(["cod_tuss", "pred"]).size().rename("N")
    rot = base[base.rotulado].copy()
    n = rot.groupby(["cod_tuss", "pred"]).size().rename("n")
    rot = rot.join(pop, on=["cod_tuss", "pred"]).join(n, on=["cod_tuss", "pred"])
    linhas = [{"id_item": r.id_item, "rodada": "R0_gabarito_case", "estrato": "GLOSADO" if r.pred else "NAO_GLOSADO",
               "subestrato": r.cod_tuss, "peso_amostral": float(r.N / r.n),
               "regra_principal": r.regra_principal if r.pred else None, "agente_indevido": bool(r.pred),
               "auditor_indevido": bool(r.real), "auditor": "gabarito_case", "motivo": None} for r in rot.itertuples()]
    return spark.createDataFrame(linhas, "id_item string, rodada string, estrato string, subestrato string, "
                                         "peso_amostral double, regra_principal string, agente_indevido boolean, "
                                         "auditor_indevido boolean, auditor string, motivo string")


def registrar(spark, out: dict, llm_calls: list[Path] | None = None, com_gabarito: bool = True,
              incluir_simulado: bool = False) -> set[str]:
    """Registra as fontes como views temporárias schema__tabela. Devolve o conjunto de fontes disponíveis.

    Telemetria de IA simulada (provedor 'simulado', respostas gravadas da F3) fica de fora por padrão: o painel só
    mostra chamadas reais. Sem chave de provedor, os indicadores de IA ficam SEM_DADO."""
    disp = set()
    for nome, df in out.items():
        if not nome.startswith("_") and "." in nome:
            df.createOrReplaceTempView(nome.replace(".", "__"))
            disp.add(nome)
    if com_gabarito:
        auditoria_do_gabarito(spark, out).createOrReplaceTempView("gold__fato_auditoria_amostral")
        disp.add("gold.fato_auditoria_amostral")
    arquivos = LLM_CALLS if llm_calls is None else llm_calls
    if arquivos:
        llm = spark.read.schema(SCHEMA_LLM).json([str(a) for a in arquivos])
        if not incluir_simulado:
            llm = llm.where("provedor <> 'simulado'")
        llm.createOrReplaceTempView("ops__llm_calls")
        sql = _select_da_view(RAIZ / "ia" / "databricks" / "v_ia_sanidade.sql", "ops.v_ia_sanidade")
        spark.sql(sql.replace("ops.llm_calls", "ops__llm_calls")).createOrReplaceTempView("ops__v_ia_sanidade")
        disp |= {"ops.llm_calls", "ops.v_ia_sanidade"}
    return disp


def avaliar(spark, disponiveis: set[str], c: dict | None = None) -> list[dict]:
    c = c or gerar.carregar()
    sql = gerar.select_status(c, "local", disponiveis)
    rows = [r.asDict() for r in spark.sql(sql + " ORDER BY ordem, recorte").collect()]
    for r in rows:
        r["avaliado_em"] = r["avaliado_em"].isoformat() if r["avaliado_em"] else None
    return rows


# ===================================================================================================== saída
def _fmt(v, ind: str) -> str:
    if v is None:
        return "—"
    if ind in {"S04"}:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if ind in {"S18", "S19", "S20", "S21", "S24", "S25", "S26", "S37", "S39"}:
        return f"{v:,.0f}".replace(",", ".")
    return f"{100 * v:.2f}%".replace(".", ",")


def _banda(r: dict) -> str:
    lo, hi = r["banda_min"], r["banda_max"]
    if r["historico_min"] is not None and r["status"] == "CALIBRANDO":
        return f"histórico {r['n_historico'] or 0}/{r['historico_min']}"
    if lo is None and hi is None:
        return "—"
    return " · ".join(x for x in [f"≥ {_fmt(lo, r['id_indicador'])}" if lo is not None else "",
                                   f"≤ {_fmt(hi, r['id_indicador'])}" if hi is not None else ""] if x)


def resumo(rows: list[dict]) -> dict:
    por = {}
    for r in rows:
        por.setdefault(r["camada_titulo"], {}).setdefault(r["status"], 0)
        por[r["camada_titulo"]][r["status"]] += 1
    return por


def markdown(rows: list[dict], portao: dict) -> str:
    L = ["# Painel de sanidade · avaliação local", "",
         "> GERADO por `python -m sanidade.local`. Mesmo SQL do Databricks (dialeto local). Dados: sinistro real do case,",
         "> planilha do funil, gabarito como rodada 0 de auditoria (não probabilística).", "",
         f"**Portão de envio: {'LIBERADO' if portao['liberado'] else 'BLOQUEADO'}**"
         + ("" if portao["liberado"] else " · " + "; ".join(f"{b['id_indicador']} {b['recorte']}" for b in portao["bloqueios"])), ""]
    L += ["| Camada | " + " | ".join(gerar.STATUS) + " |", "|---|" + "---|" * len(gerar.STATUS)]
    for cam, st in resumo(rows).items():
        L.append(f"| {cam} | " + " | ".join(str(st.get(s, 0)) for s in gerar.STATUS) + " |")
    atual = None
    for r in rows:
        if r["camada_titulo"] != atual:
            atual = r["camada_titulo"]
            L += ["", f"## {atual}", "", "| Status | Id | Indicador | Recorte | Valor | Banda | Sev. | Dono | Ação |",
                  "|---|---|---|---|---|---|---|---|---|"]
        acao = r["acao"] if r["status"] == "ALERTA" else ""
        L.append(f"| **{r['status']}** | {r['id_indicador']} | {r['nome']} | {r['recorte']} | {_fmt(r['valor'], r['id_indicador'])} | "
                 f"{_banda(r)} | {r['severidade']} | {r['dono']} | {acao} |")
    return "\n".join(L) + "\n"


def pagina_html(rows: list[dict], portao: dict) -> str:
    cor = {"OK": "ok", "ALERTA": "alerta", "CALIBRANDO": "calib", "SEM_DADO": "semdado", "SEM_FONTE": "semfonte"}
    blocos, atual, linhas = [], None, []

    def fechar():
        if atual:
            blocos.append(f"<section><h2>{html.escape(atual)}</h2><div class='tw'><table><thead><tr><th>Status</th><th>Id</th>"
                          "<th>Indicador</th><th>Recorte</th><th class='n'>Valor</th><th>Banda</th><th>Sev.</th><th>Dono</th>"
                          f"<th>Ação (se em alerta)</th></tr></thead><tbody>{''.join(linhas)}</tbody></table></div></section>")
    for r in rows:
        if r["camada_titulo"] != atual:
            fechar()
            atual, linhas = r["camada_titulo"], []
        e = html.escape
        linhas.append(f"<tr><td><span class='st {cor[r['status']]}'>{r['status']}</span></td><td>{r['id_indicador']}</td>"
                      f"<td>{e(r['nome'])}</td><td class='rec'>{e(r['recorte'])}</td><td class='n'>{_fmt(r['valor'], r['id_indicador'])}</td>"
                      f"<td>{e(_banda(r))}</td><td>{r['severidade']}</td><td>{r['dono']}</td>"
                      f"<td>{e(r['acao']) if r['status'] == 'ALERTA' else ''}</td></tr>")
    fechar()
    res = resumo(rows)
    cab = "".join(f"<th>{s}</th>" for s in gerar.STATUS)
    corpo = "".join(f"<tr><td>{html.escape(c)}</td>" + "".join(f"<td class='n'>{st.get(s, 0)}</td>" for s in gerar.STATUS) + "</tr>"
                    for c, st in res.items())
    estado = "LIBERADO" if portao["liberado"] else "BLOQUEADO"
    motivos = "" if portao["liberado"] else "<ul>" + "".join(
        f"<li>{b['id_indicador']} · {html.escape(b['nome'])} · {html.escape(b['recorte'])}</li>" for b in portao["bloqueios"]) + "</ul>"
    quando = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Painel de sanidade</title><style>
:root{{--bg:#f7f7f5;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#e3e2dd;--ok:#2f7d4f;--al:#b3261e;--ca:#8a6d1d;--sd:#5b5b8a;--sf:#77756f}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#161615;--fg:#ecebe6;--mut:#a3a29c;--card:#1f1f1d;--line:#34332f;--ok:#6cc58f;--al:#ff8a80;--ca:#e0c068;--sd:#a9a9e0;--sf:#a3a29c}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:24px 16px 48px}}h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:16px;margin:28px 0 8px}}
.sub{{color:var(--mut);margin:0 0 16px}}.portao{{background:var(--card);border:1px solid var(--line);border-left:4px solid {'var(--ok)' if portao['liberado'] else 'var(--al)'};padding:12px 16px;border-radius:6px}}
.portao b{{color:{'var(--ok)' if portao['liberado'] else 'var(--al)'}}}.tw{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:6px}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{font-weight:600;color:var(--mut);font-size:12px;white-space:nowrap}}td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
td.rec{{color:var(--mut);font-size:12px}}.st{{font-size:11px;font-weight:700;letter-spacing:.02em}}.ok{{color:var(--ok)}}.alerta{{color:var(--al)}}
.calib{{color:var(--ca)}}.semdado{{color:var(--sd)}}.semfonte{{color:var(--sf)}}.resumo{{max-width:640px;margin-top:16px}}
</style></head><body><main>
<h1>Painel de sanidade · avaliação local</h1>
<p class="sub">Negócio primeiro. Mesmo SQL do Databricks (dialeto local) · {quando}. Gabarito usado como rodada 0 de auditoria (não probabilística).</p>
<div class="portao">Portão de envio: <b>{estado}</b>{motivos}</div>
<div class="tw resumo"><table><thead><tr><th>Camada</th>{cab}</tr></thead><tbody>{corpo}</tbody></table></div>
{''.join(blocos)}
</main></body></html>
"""


def main() -> None:
    from medalhao.local import executar, liberar, spark_local

    spark = spark_local()
    spark.sparkContext.setLogLevel("ERROR")
    out = executar(spark, str(RAIZ / "arvo.case" / "sinistro-hospital-saorafael.csv"), planilha=str(PLANILHA), run_id="f9-sanidade")
    try:
        rows = avaliar(spark, registrar(spark, out))
    finally:
        liberar(out)
    portao = avaliar_portao(rows)
    SAIDA.mkdir(exist_ok=True)
    (SAIDA / "status.json").write_text(json.dumps({"portao": portao, "indicadores": rows}, ensure_ascii=False, indent=2,
                                                  default=str), "utf-8")
    (SAIDA / "PAINEL_LOCAL.md").write_text(markdown(rows, portao), "utf-8")
    (SAIDA / "painel_local.html").write_text(pagina_html(rows, portao), "utf-8")
    print(json.dumps({"portao": portao["liberado"], "resumo": resumo(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
