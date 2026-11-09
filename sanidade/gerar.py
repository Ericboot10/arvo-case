"""F9 · Gera, a partir de sanidade/indicadores.yaml (fonte única), tudo o que o painel precisa:

  sanidade/databricks/v_sanidade_status.sql   view ops.v_sanidade_status (1 linha por indicador × recorte, com status)
  resources/alertas_sanidade.yml              SQL alerts (v2) do bundle, um por indicador não-INFO
  resources/painel_sanidade.yml               dashboard AI/BI do bundle (catálogo por target)
  sanidade/dashboard/painel_sanidade.lvdash.json
  sanidade/RUNBOOKS.md

Dois dialetos para a MESMA definição:
  databricks  métricas via MEASURE() das UC Metric Views (semantic.mv_*), tabelas schema.tabela após USE CATALOG
  local       a mesma fórmula de semantic/metricas.yaml direto na tabela gold (Spark local, views temporárias
              schema__tabela). As metric views também são geradas dessa fórmula, então os dois são equivalentes.

  python -m sanidade.gerar            gera os artefatos
  python -m sanidade.gerar --checar   falha se algum artefato gerado estiver desatualizado (CI)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
AQUI = Path(__file__).resolve().parent
SPEC = AQUI / "indicadores.yaml"
DESTINOS = AQUI / "destinos.yaml"
SAIDAS = {
    "view": AQUI / "databricks" / "v_sanidade_status.sql",
    "alertas": RAIZ / "resources" / "alertas_sanidade.yml",
    "painel_bundle": RAIZ / "resources" / "painel_sanidade.yml",
    "painel": AQUI / "dashboard" / "painel_sanidade.lvdash.json",
    "runbooks": AQUI / "RUNBOOKS.md",
}
SEVERIDADES = ["CRITICA", "ALTA", "MEDIA", "INFO"]
STATUS = ["OK", "ALERTA", "CALIBRANDO", "SEM_DADO", "SEM_FONTE"]
# Criadas pelo próprio job da F9 antes da view de status (resources/jobs.yml · f9_sanidade)
CRIADAS_PELO_JOB_F9 = {"ops.v_ia_sanidade"}
CRON = {"CRITICA": "0 0 * * * ?", "ALTA": "0 0 7 * * ?", "MEDIA": "0 0 7 * * ?"}   # quartz
REF = re.compile(r"\{([a-z_]+\.[a-z_]+)\}")


# ===================================================================================================== carga
def carregar() -> dict:
    ler = lambda p: yaml.safe_load(Path(p).read_text("utf-8"))  # noqa: E731
    spec = ler(SPEC)
    met = ler(RAIZ / "semantic" / "metricas.yaml")
    mod = ler(RAIZ / "arquitetura" / "modelo.yaml")
    glo = ler(RAIZ / "semantic" / "glossario.yaml")
    ia = ler(RAIZ / "ia" / "config" / "alertas_ia.yaml")
    views = {}
    for tid, t in mod["tabelas"].items():
        if t["tipo"] == "metric_view":
            views[t["origem"][0].split(".", 1)[1]] = tid          # fato_x → semantic.mv_x
    return {"spec": spec, "metricas": {m["id"]: m for m in met["metricas"]}, "modelo": mod["tabelas"],
            "donos": set(glo["donos_validos"]), "ia": ia, "views": views,
            "destinos": (ler(DESTINOS) or {}) if DESTINOS.exists() else {}}


def fontes(ind: dict, c: dict) -> list[str]:
    if "metrica" in ind:
        return ["gold." + c["metricas"][ind["metrica"]]["tabela"]]
    if "limite_ia" in ind:
        return ["ops.v_ia_sanidade"]
    return sorted(set(REF.findall(ind["sql"])))


def banda(ind: dict, c: dict) -> dict:
    if "limite_ia" in ind:
        if ind["limite_ia"] == "drift_modelo":
            return {"max": 0, "origem": "ia/config/alertas_ia.yaml (drift_modelo)"}
        lim = c["ia"]["limites"][ind["limite_ia"]]
        return {k: lim[k] for k in ("min", "max") if k in lim} | {"origem": "ia/config/alertas_ia.yaml"}
    return ind["banda"]


def acao(ind: dict, c: dict) -> str:
    if "limite_ia" in ind:
        return c["ia"]["drift_modelo"] if ind["limite_ia"] == "drift_modelo" else c["ia"]["limites"][ind["limite_ia"]]["acao"]
    return ind["acao"]


def validar(c: dict) -> list[str]:
    """Erros de especificação. G9 exige: dono válido, runbook existente, banda com origem, fonte no modelo."""
    erros, spec = [], c["spec"]
    ids = [i["id"] for i in spec["indicadores"]]
    if len(ids) != len(set(ids)):
        erros.append("ids duplicados")
    rbs = spec["runbooks"]
    for i in spec["indicadores"]:
        p = i["id"]
        if sum(k in i for k in ("metrica", "sql", "limite_ia")) != 1:
            erros.append(f"{p}: defina exatamente um de metrica | sql | limite_ia")
            continue
        if i["dono"] not in c["donos"]:
            erros.append(f"{p}: dono {i['dono']} fora de glossario.donos_validos")
        if i["severidade"] not in SEVERIDADES:
            erros.append(f"{p}: severidade inválida")
        if i["camada"] not in spec["camadas"]:
            erros.append(f"{p}: camada inválida")
        if i["runbook"] not in rbs or p not in rbs[i["runbook"]]["gatilho"]:
            erros.append(f"{p}: runbook {i['runbook']} inexistente ou sem o indicador no gatilho")
        if "metrica" in i:
            m = c["metricas"].get(i["metrica"])
            if not m:
                erros.append(f"{p}: métrica {i['metrica']} não existe")
                continue
            if m["tabela"] not in c["views"]:
                erros.append(f"{p}: tabela {m['tabela']} sem metric view")
            dims = set(i.get("recorte", [])) | ({"competencia"} if i.get("competencia") else set())
            if not dims <= set(m["dimensoes"]):
                erros.append(f"{p}: recorte {sorted(dims - set(m['dimensoes']))} não permitido em {m['id']}")
            if i.get("competencia") not in (None, "ultima", "sigma"):
                erros.append(f"{p}: competencia deve ser ultima | sigma")
        if "limite_ia" in i and i["limite_ia"] not in c["ia"]["limites"] and i["limite_ia"] != "drift_modelo":
            erros.append(f"{p}: limite_ia {i['limite_ia']} não existe em alertas_ia.yaml")
        if "sql" in i and set(i.get("fontes", [])) != set(REF.findall(i["sql"])):
            erros.append(f"{p}: `fontes` diverge das tabelas usadas no SQL")
        for f in fontes(i, c):
            if f not in c["modelo"]:
                erros.append(f"{p}: fonte {f} não está em arquitetura/modelo.yaml")
        b = banda(i, c)
        sig = "sigma" in b
        if sig != (i.get("competencia") == "sigma"):
            erros.append(f"{p}: banda sigma exige competencia: sigma (e vice-versa)")
        if not sig and not ({"min", "max"} & set(b)):
            erros.append(f"{p}: banda sem min/max")
        if not b.get("origem"):
            erros.append(f"{p}: banda sem origem")
    for rid, rb in rbs.items():
        if len(rb.get("passos", [])) < 2 or not rb.get("escalonamento"):
            erros.append(f"{rid}: runbook precisa de ≥ 2 passos e escalonamento")
        for g in rb["gatilho"]:
            if g not in ids:
                erros.append(f"{rid}: gatilho {g} não existe")
    cobertos = {i["limite_ia"] for i in spec["indicadores"] if "limite_ia" in i}
    faltam = (set(c["ia"]["limites"]) | {"drift_modelo"}) - cobertos
    if faltam:
        erros.append(f"limites de IA sem indicador no painel: {sorted(faltam)}")
    return erros


# ===================================================================================================== SQL
def _tab(ref: str, dialeto: str) -> str:
    return ref.replace(".", "__") if dialeto == "local" else ref


def _num(x) -> str:
    return "CAST(NULL AS DOUBLE)" if x is None else f"CAST({x} AS DOUBLE)"


def _recorte_expr(dims: list[str]) -> str:
    if not dims:
        return "'total'"
    partes = [f"concat('{d}=', CAST({d} AS STRING))" for d in dims]
    return partes[0] if len(partes) == 1 else f"concat_ws(' · ', {', '.join(partes)})"


def _base_metrica(ind: dict, c: dict, dialeto: str) -> str:
    """SELECT <dims>, valor FROM <fonte> GROUP BY <dims>. Única diferença entre dialetos: MEASURE() × fórmula."""
    m = c["metricas"][ind["metrica"]]
    dims = (["competencia"] if ind.get("competencia") else []) + list(ind.get("recorte", []))
    if dialeto == "databricks":
        expr, origem = f"MEASURE({m['nome']})", c["views"][m["tabela"]]
    else:
        expr, origem = m["formula"], _tab("gold." + m["tabela"], "local")
    sel = ", ".join(dims + [f"{expr} AS valor"])
    where = " AND ".join(f"{d} IS NOT NULL" for d in ind.get("recorte", []))
    q = f"SELECT {sel} FROM {origem}" + (f" WHERE {where}" if where else "")
    return q + (f" GROUP BY {', '.join(dims)}" if dims else "")


def medicao(ind: dict, c: dict, dialeto: str) -> str:
    """Uma consulta → (id_indicador, recorte, valor, banda_min, banda_max, n_historico, historico_min)."""
    b = banda(ind, c)
    pid = f"'{ind['id']}' AS id_indicador"
    fixa = f"{_num(b.get('min'))} AS banda_min, {_num(b.get('max'))} AS banda_max, " \
           "CAST(NULL AS INT) AS n_historico, CAST(NULL AS INT) AS historico_min"
    if "limite_ia" in ind:
        col = "CAST(drift_modelo AS INT)" if ind["limite_ia"] == "drift_modelo" else ind["limite_ia"]
        t = _tab("ops.v_ia_sanidade", dialeto)
        return (f"SELECT {pid}, concat('tarefa=', task_id, ' · adapter=', adapter) AS recorte, "
                f"CAST({col} AS DOUBLE) AS valor, {fixa} FROM {t} WHERE dia = (SELECT max(dia) FROM {t})")
    if "sql" in ind:
        q = REF.sub(lambda mt: _tab(mt.group(1), dialeto), " ".join(ind["sql"].split()))
        return f"SELECT {pid}, recorte, CAST(valor AS DOUBLE) AS valor, {fixa} FROM ({q}) q"
    base = _base_metrica(ind, c, dialeto)
    rec = _recorte_expr(list(ind.get("recorte", [])))
    if not ind.get("competencia"):
        return f"SELECT {pid}, {rec} AS recorte, CAST(valor AS DOUBLE) AS valor, {fixa} FROM ({base}) q"
    part = f"PARTITION BY {rec}"
    if ind["competencia"] == "ultima":
        return (f"SELECT {pid}, recorte, valor, {fixa} FROM (SELECT {rec} AS recorte, CAST(valor AS DOUBLE) AS valor, "
                f"row_number() OVER ({part} ORDER BY competencia DESC) AS rn FROM ({base}) q) s WHERE rn = 1")
    k, jan, hmin = b["sigma"], b["janela"], b["historico_min"]
    w = f"OVER ({part} ORDER BY competencia ROWS BETWEEN {jan} PRECEDING AND 1 PRECEDING)"
    return (f"SELECT {pid}, recorte, valor, mu - {k} * sd AS banda_min, mu + {k} * sd AS banda_max, "
            f"n_historico, CAST({hmin} AS INT) AS historico_min FROM ("
            f"SELECT {rec} AS recorte, CAST(valor AS DOUBLE) AS valor, avg(valor) {w} AS mu, stddev_samp(valor) {w} AS sd, "
            f"CAST(count(valor) {w} AS INT) AS n_historico, row_number() OVER ({part} ORDER BY competencia DESC) AS rn "
            f"FROM ({base}) q) s WHERE rn = 1")


def _lit(x) -> str:
    if isinstance(x, bool):
        return "true" if x else "false"
    return "'" + str(x).replace("'", "''") + "'"


def disponiveis_databricks(c: dict) -> set[str]:
    return {t for t, v in c["modelo"].items() if v.get("status") == "implementado"} | CRIADAS_PELO_JOB_F9


def select_status(c: dict, dialeto: str, disponiveis: set[str]) -> str:
    """O SELECT da view ops.v_sanidade_status. Indicadores sem fonte entram com status SEM_FONTE (não somem)."""
    spec = c["spec"]
    meta = []
    for ordem, i in enumerate(spec["indicadores"], 1):
        tem = all(f in disponiveis for f in fontes(i, c))
        b = banda(i, c)
        meta.append("(" + ", ".join([
            _lit(i["id"]), str(ordem), _lit(i["camada"]), _lit(spec["camadas"][i["camada"]]["titulo"]), _lit(i["familia"]),
            _lit(i["nome"]), _lit(i.get("metrica") or i.get("limite_ia") or "sql"), _lit(i["severidade"]),
            _lit(i["severidade"] == "CRITICA"), _lit(i["dono"]), _lit(i["runbook"]), _lit(acao(i, c)),
            _lit(b["origem"]), _lit(tem)]) + ")")
    meds = [medicao(i, c, dialeto) for i in spec["indicadores"] if all(f in disponiveis for f in fontes(i, c))]
    if not meds:
        meds = ["SELECT CAST(NULL AS STRING) AS id_indicador, CAST(NULL AS STRING) AS recorte, CAST(NULL AS DOUBLE) AS valor, "
                "CAST(NULL AS DOUBLE) AS banda_min, CAST(NULL AS DOUBLE) AS banda_max, CAST(NULL AS INT) AS n_historico, "
                "CAST(NULL AS INT) AS historico_min WHERE false"]
    union = "\n  UNION ALL\n  ".join(meds)
    return f"""WITH meta AS (
  SELECT * FROM VALUES
    {(','+chr(10)+'    ').join(meta)}
  AS t(id_indicador, ordem, camada, camada_titulo, familia, nome, definicao, severidade, bloqueia_envio, dono,
       runbook, acao, origem_banda, fonte_disponivel)
),
medicoes AS (
  {union}
)
SELECT m.ordem, m.id_indicador, m.camada, m.camada_titulo, m.familia, m.nome, m.definicao, m.severidade,
       m.bloqueia_envio, m.dono, m.runbook, m.acao, m.origem_banda,
       coalesce(d.recorte, 'total') AS recorte, d.valor, d.banda_min, d.banda_max, d.n_historico, d.historico_min,
       CASE WHEN NOT m.fonte_disponivel THEN 'SEM_FONTE'
            WHEN d.historico_min IS NOT NULL AND coalesce(d.n_historico, 0) < d.historico_min THEN 'CALIBRANDO'
            WHEN d.valor IS NULL THEN 'SEM_DADO'
            WHEN d.valor < d.banda_min OR d.valor > d.banda_max THEN 'ALERTA'
            ELSE 'OK' END AS status,
       current_timestamp() AS avaliado_em
FROM meta m LEFT JOIN medicoes d ON m.id_indicador = d.id_indicador"""


def sql_view(c: dict) -> str:
    disp = disponiveis_databricks(c)
    sem = [i["id"] for i in c["spec"]["indicadores"] if not all(f in disp for f in fontes(i, c))]
    return f"""-- =====================================================================================================
-- F9 · ops.v_sanidade_status. GERADO por `python -m sanidade.gerar`. NÃO EDITE À MÃO.
-- Fonte: sanidade/indicadores.yaml (+ semantic/metricas.yaml, ia/config/alertas_ia.yaml, arquitetura/modelo.yaml)
-- 1 linha por indicador × recorte, com banda, status, dono e runbook. Alimenta o painel e os alertas SQL.
-- Pré-requisitos no mesmo job: semantic/databricks/02_metric_views.sql e ia/databricks/v_ia_sanidade.sql
-- Sem fonte hoje (status SEM_FONTE até a tabela existir; regerar após mudar o modelo): {', '.join(sem) or 'nenhum'}
-- =====================================================================================================
USE CATALOG IDENTIFIER(:catalog);

CREATE OR REPLACE VIEW ops.v_sanidade_status
COMMENT 'Indicadores de sanidade (F9): negócio primeiro, depois semântica, dados e IA. Fonte: sanidade/indicadores.yaml'
AS
{select_status(c, "databricks", disp)};
"""


# ===================================================================================================== alertas
def alertas_yaml(c: dict) -> str:
    out, dest = {}, c["destinos"]
    for i in c["spec"]["indicadores"]:
        if i["severidade"] == "INFO":
            continue
        rb = c["spec"]["runbooks"][i["runbook"]]
        subs = [{"destination_id": d} for d in (dest.get(i["dono"]) or []) if not str(d).startswith("DEFINIR")]
        notif = {"notify_on_ok": True, "retrigger_seconds": 3600 if i["severidade"] == "CRITICA" else 86400}
        if subs:
            notif["subscriptions"] = subs
        out[f"sanidade_{i['id'].lower()}"] = {
            "display_name": f"[sanidade][{i['severidade']}] {i['id']} · {i['nome']}",
            "query_text": ("SELECT count_if(status = 'ALERTA') AS n_alerta, "
                           "concat_ws('; ', collect_list(CASE WHEN status = 'ALERTA' THEN recorte END)) AS recortes "
                           f"FROM ${{var.catalog}}.ops.v_sanidade_status WHERE id_indicador = '{i['id']}'"),
            "warehouse_id": "${var.warehouse_id}",
            "custom_summary": f"{i['id']} em ALERTA · dono {i['dono']} · {i['runbook']}",
            "custom_description": f"Ação: {acao(i, c)} | Runbook {i['runbook']} ({rb['titulo']}): sanidade/RUNBOOKS.md"
                                  + (" | BLOQUEIA O ENVIO" if i["severidade"] == "CRITICA" else ""),
            "evaluation": {"comparison_operator": "GREATER_THAN", "source": {"name": "n_alerta"},
                           "threshold": {"value": {"double_value": 0}}, "notification": notif},
            "schedule": {"quartz_cron_schedule": CRON[i["severidade"]], "timezone_id": "America/Sao_Paulo"},
        }
    cab = ("# GERADO por `python -m sanidade.gerar` a partir de sanidade/indicadores.yaml. NÃO EDITE À MÃO.\n"
           "# SQL alerts (v2) do bundle (CLI ≥ 0.279.0). Em `mode: development` as agendas ficam pausadas.\n"
           "# Destinos de notificação por dono: sanidade/destinos.yaml (IDs de notification destinations, G9).\n")
    return cab + yaml.safe_dump({"resources": {"alerts": out}}, allow_unicode=True, sort_keys=False, width=200)


# ===================================================================================================== painel
def _ds(nome: str, titulo: str, sql: str) -> dict:
    return {"name": nome, "displayName": titulo, "queryLines": [ln + "\n" for ln in sql.strip().splitlines()]}


def _q(ds: str, campos: list[str]) -> list[dict]:
    return [{"name": "main_query", "query": {"datasetName": ds, "disaggregated": True,
                                             "fields": [{"name": f, "expression": f"`{f}`"} for f in campos]}}]


def _texto(nome: str, linhas: list[str], x: int, y: int, w: int = 6, h: int = 2) -> dict:
    # Cada linha precisa de quebra própria; sem ela o painel cola o título no parágrafo seguinte.
    corpo = [ln + "\n" for par in linhas for ln in (par, "")][:-1]
    return {"widget": {"name": nome, "multilineTextboxSpec": {"lines": corpo}}, "position": {"x": x, "y": y, "width": w, "height": h}}


def _contador(nome, ds, campo, titulo, x, y, w=2, h=3) -> dict:
    return {"widget": {"name": nome, "queries": _q(ds, [campo]),
                       "spec": {"version": 2, "widgetType": "counter",
                                "encodings": {"value": {"fieldName": campo, "displayName": titulo}},
                                "frame": {"showTitle": True, "title": titulo}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def _barra(nome, ds, xcampo, ycampo, titulo, x, y, cor=None, w=3, h=6) -> dict:
    enc = {"x": {"fieldName": xcampo, "scale": {"type": "categorical"}, "displayName": xcampo},
           "y": {"fieldName": ycampo, "scale": {"type": "quantitative"}, "displayName": ycampo}}
    campos = [xcampo, ycampo]
    if cor:
        enc["color"] = {"fieldName": cor, "scale": {"type": "categorical"}, "displayName": cor}
        campos.append(cor)
    return {"widget": {"name": nome, "queries": _q(ds, campos),
                       "spec": {"version": 3, "widgetType": "bar", "encodings": enc,
                                "frame": {"showTitle": True, "title": titulo}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


COLS_STATUS = ["status", "id_indicador", "nome", "recorte", "valor", "banda_min", "banda_max", "severidade", "dono", "runbook", "acao"]
# Taxas pequenas (0,0048) somem com 2 casas decimais: o painel mostra o número com até 4 casas, como texto.
_NUM = {"valor", "banda_min", "banda_max"}
SELECT_STATUS = [f"CAST(round({c}, 4) AS STRING) AS {c}" if c in _NUM else c for c in COLS_STATUS]


def _tabela(nome, ds, campos, titulo, x, y, w=6, h=8) -> dict:
    return {"widget": {"name": nome, "queries": _q(ds, campos),
                       "spec": {"version": 2, "widgetType": "table",
                                "encodings": {"columns": [{"fieldName": f, "displayName": f} for f in campos]},
                                "frame": {"showTitle": True, "title": titulo}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def painel(c: dict) -> dict:
    """Dashboard AI/BI (.lvdash.json). Datasets sem catálogo: o bundle injeta dataset_catalog por target."""
    def status(cam: str) -> dict:
        return _ds(f"ds_status_{cam}", f"Status · {c['spec']['camadas'][cam]['titulo']}", f"""
SELECT {', '.join(SELECT_STATUS)}, ordem FROM ops.v_sanidade_status WHERE camada = '{cam}'
ORDER BY CASE status WHEN 'ALERTA' THEN 0 WHEN 'SEM_DADO' THEN 1 WHEN 'CALIBRANDO' THEN 2 WHEN 'SEM_FONTE' THEN 3 ELSE 4 END,
         ordem, recorte""")

    datasets = [
        _ds("ds_resumo", "Resumo por camada × status", """
SELECT camada_titulo AS camada, status, count(*) AS indicadores FROM ops.v_sanidade_status GROUP BY ALL"""),
        _ds("ds_portao", "Portão de envio", """
SELECT count_if(status = 'ALERTA' AND bloqueia_envio) AS bloqueios_de_envio,
       count_if(status = 'ALERTA') AS indicadores_em_alerta FROM ops.v_sanidade_status"""),
        _ds("ds_norte", "Índice-norte e fatores (última competência)", """
SELECT competencia, round(100 * MEASURE(indice_norte), 2) AS indice_norte_pct,
       round(100 * MEASURE(atingimento_meta), 1) AS atingimento_meta_pct,
       MEASURE(economia_efetivada) AS economia_efetivada
FROM semantic.mv_funil_economia GROUP BY competencia ORDER BY competencia DESC LIMIT 1"""),
        _ds("ds_fatores", "Fatores do norte (M21 × M22 × M23 × M24 × M18)", """
SELECT etapa, round(100 * taxa, 2) AS taxa_pct FROM (
  SELECT competencia, MEASURE(taxa_identificacao) AS identificacao, MEASURE(taxa_ativacao) AS ativacao,
         MEASURE(taxa_envio) AS envio, MEASURE(taxa_registro) AS registro, MEASURE(taxa_efetivacao) AS efetivacao
  FROM semantic.mv_funil_economia GROUP BY competencia ORDER BY competencia DESC LIMIT 1) f
LATERAL VIEW stack(5, '1 identificação', identificacao, '2 ativação', ativacao, '3 envio', envio,
                      '4 registro', registro, '5 efetivação', efetivacao) s AS etapa, taxa"""),
        _ds("ds_glosa_regra", "Glosa por regra", """
SELECT regra_principal, MEASURE(valor_glosado) AS valor_glosado, MEASURE(itens_glosados) AS itens_glosados
FROM semantic.mv_auditoria_glosa WHERE regra_principal IS NOT NULL GROUP BY regra_principal"""),
        _ds("ds_pr_total", "Precisão e recall (gabarito do case)", """
SELECT round(100 * precisao, 1) AS precisao_pct, round(100 * recall, 1) AS recall_pct,
       concat(format_number(100 * precisao_ic_inf, 1), '% – ', format_number(100 * precisao_ic_sup, 1), '%') AS precisao_ic95,
       concat(format_number(100 * recall_ic_inf, 1), '% – ', format_number(100 * recall_ic_sup, 1), '%') AS recall_ic95,
       round(100 * precisao_rs, 1) AS precisao_rs_pct, round(100 * recall_rs_limite_inferior, 1) AS recall_rs_li_pct,
       tp, fp, fn, tn, itens_rotulados
FROM ops.v_precisao_recall WHERE recorte = 'total'"""),
        _ds("ds_pr_matriz", "Matriz de confusão", """
SELECT resultado, CASE resultado WHEN 'TP' THEN 'Glosou e era indevido' WHEN 'FP' THEN 'Glosou, mas era devido'
                                 WHEN 'FN' THEN 'Não glosou, mas era indevido' ELSE 'Não glosou e era devido' END AS significado,
       count(*) AS itens, round(sum(CASE WHEN resultado IN ('TP', 'FP') THEN vl_glosado ELSE vl_cobrado END), 2) AS valor_rs
FROM gold.v_avaliacao_gabarito WHERE rotulado GROUP BY resultado
ORDER BY CASE resultado WHEN 'TP' THEN 1 WHEN 'FP' THEN 2 WHEN 'FN' THEN 3 ELSE 4 END"""),
        _ds("ds_pr_regra", "Precisão por regra", """
SELECT recorte AS regra, tp, fp, round(100 * precisao, 1) AS precisao_pct,
       concat(format_number(100 * precisao_ic_inf, 1), '% – ', format_number(100 * precisao_ic_sup, 1), '%') AS ic95,
       CASE WHEN precisao_ic_inf >= 0.95 THEN 'atinge o piso de 95%' ELSE 'abaixo do piso de 95% (amostra pequena)' END AS piso_envio
FROM ops.v_precisao_recall WHERE ordem = 1 ORDER BY recorte"""),
        _ds("ds_ia_serie", "IA por dia", """
SELECT dia, concat(task_id, ' · ', adapter) AS tarefa_adapter, taxa_schema_valido, custo_estimado_usd, latencia_p95_ms
FROM ops.v_ia_sanidade"""),
    ] + [status(cam) for cam in c["spec"]["camadas"]]

    neg = [
        _texto("t_neg", ["## Sanidade · Negócio primeiro",
                         "Dados do case Arvo: sinistro e gabarito do Hospital São Rafael (jun/2025), contrato PRT-2025-0417 e "
                         "planilha de inteligências (rede inteira, 6 meses). Nenhum dado gerado.",
                         "Valor, qualidade da decisão, funil, prestador e **invariantes**. Invariante em ALERTA **bloqueia o envio**. "
                         "CALIBRANDO = banda dinâmica ainda sem histórico suficiente; SEM_FONTE = tabela ainda não existe."], 0, 0, h=3),
        _contador("c_bloq", "ds_portao", "bloqueios_de_envio", "Bloqueios de envio (deve ser 0)", 0, 3),
        _contador("c_norte", "ds_norte", "indice_norte_pct", "Índice-norte, % do sinistro (meta 2%)", 2, 3),
        _contador("c_meta", "ds_norte", "atingimento_meta_pct", "Atingimento da meta, %", 4, 3),
        _barra("b_fatores", "ds_fatores", "etapa", "taxa_pct", "Fatores do norte (% em cada etapa)", 0, 6),
        _barra("b_regra", "ds_glosa_regra", "regra_principal", "valor_glosado", "Glosa por regra (R$)", 3, 6),
        _tabela("tb_neg", "ds_status_negocio", COLS_STATUS, "Indicadores de negócio", 0, 12, h=10),
    ]
    pr = [
        _texto("t_pr", ["## Precisão e recall · gabarito do case",
                        "Motor de regras sobre o sinistro do Hospital São Rafael (jun/2025), comparado item a item com os "
                        "263 itens do gabarito de auditoria. Dados do case, sem alteração. IC 95% de Wilson.",
                        "**Precisão** = das glosas feitas, quantas eram indevidas. **Recall** = dos itens indevidos, quantos o agente glosou."],
               0, 0, h=3),
        _contador("c_prec", "ds_pr_total", "precisao_pct", "Precisão, %", 0, 3),
        _contador("c_rec", "ds_pr_total", "recall_pct", "Recall, %", 2, 3),
        _contador("c_prec_rs", "ds_pr_total", "precisao_rs_pct", "Precisão em R$, %", 4, 3),
        _tabela("tb_pr_ic", "ds_pr_total", ["precisao_ic95", "recall_ic95", "recall_rs_li_pct", "tp", "fp", "fn", "tn",
                                            "itens_rotulados"], "Intervalos de confiança e contagens", 0, 6, h=3),
        _tabela("tb_pr_matriz", "ds_pr_matriz", ["resultado", "significado", "itens", "valor_rs"], "Matriz de confusão",
                0, 9, w=3, h=5),
        _tabela("tb_pr_regra", "ds_pr_regra", ["regra", "tp", "fp", "precisao_pct", "ic95", "piso_envio"],
                "Precisão por regra (recall por regra não existe: o item não glosado não tem regra)", 3, 9, w=3, h=5),
    ]
    sem_dados = [
        _texto("t_sd", ["## Aderência semântica e engenharia de dados",
                        "A capacidade de treinar agentes vem da aderência à camada semântica: meta 100%."], 0, 0),
        _tabela("tb_sem", "ds_status_semantica", COLS_STATUS, "Aderência semântica", 0, 2),
        _tabela("tb_dados", "ds_status_dados", COLS_STATUS, "Engenharia de dados", 0, 10),
    ]
    ia = [
        _texto("t_ia", ["## IA (independente de provedor)",
                        "Limites em `ia/config/alertas_ia.yaml`. Drift de modelo ou troca de provedor exige golden set.",
                        "Neste workspace não há chave de provedor de IA: a extração do contrato não rodou aqui e a página fica "
                        "vazia, em vez de mostrar telemetria simulada. O motor usa o contrato do case revisado na F2."], 0, 0, h=3),
        _barra("b_ia", "ds_ia_serie", "dia", "taxa_schema_valido", "Schema válido por dia", 0, 3, cor="tarefa_adapter", w=6),
        _tabela("tb_ia", "ds_status_ia", COLS_STATUS, "Indicadores de IA", 0, 9),
    ]
    geral = [
        _texto("t_geral", ["## Visão geral", "Quantos indicadores em cada status, por camada."], 0, 0),
        _barra("b_resumo", "ds_resumo", "camada", "indicadores", "Indicadores por status", 0, 2, cor="status", w=6),
    ]
    pg = lambda n, t, l: {"name": n, "displayName": t, "pageType": "PAGE_TYPE_CANVAS", "layout": l}  # noqa: E731
    return {"datasets": datasets,
            "pages": [pg("negocio", "1 · Negócio", neg), pg("precisao_recall", "2 · Precisão e recall", pr),
                      pg("semantica_dados", "3 · Semântica e dados", sem_dados),
                      pg("ia", "4 · IA", ia), pg("geral", "5 · Visão geral", geral)]}


def painel_bundle_yaml() -> str:
    return """# GERADO por `python -m sanidade.gerar`. NÃO EDITE À MÃO.
# Dashboard AI/BI do painel de sanidade. dataset_catalog troca o catálogo por target (arvo_dev | arvo_stg | arvo_prod):
# os datasets do .lvdash.json não qualificam catálogo de propósito.
resources:
  dashboards:
    painel_sanidade:
      display_name: "Arvo · Painel de sanidade (${bundle.target})"
      file_path: ../sanidade/dashboard/painel_sanidade.lvdash.json
      warehouse_id: ${var.warehouse_id}
      dataset_catalog: ${var.catalog}
      embed_credentials: false
"""


# ===================================================================================================== runbooks
def runbooks_md(c: dict) -> str:
    spec = c["spec"]
    por = {i["id"]: i for i in spec["indicadores"]}
    L = ["# Runbooks do painel de sanidade (F9)", "",
         "> GERADO por `python -m sanidade.gerar` a partir de [`indicadores.yaml`](indicadores.yaml). Não edite à mão.", "",
         "Severidade: **CRITICA** bloqueia o envio do run e alerta a cada hora · **ALTA** alerta diário, ação no dia ·"
         " **MEDIA** alerta diário, ação na semana · **INFO** só painel.", "",
         "## Indicadores", "", "| Id | Camada | Indicador | Definição | Banda | Origem da banda | Severidade | Dono | Runbook |",
         "|---|---|---|---|---|---|---|---|---|"]
    for i in spec["indicadores"]:
        b = banda(i, c)
        if "sigma" in b:
            bt = f"±{b['sigma']}σ das {b['janela']} competências anteriores (mín. {b['historico_min']})"
        else:
            bt = " · ".join(x for x in [f"≥ {b['min']}" if "min" in b else "", f"≤ {b['max']}" if "max" in b else ""] if x)
        d = i.get("metrica") or (f"limite IA `{i['limite_ia']}`" if "limite_ia" in i else "SQL próprio")
        L.append(f"| {i['id']} | {spec['camadas'][i['camada']]['titulo']} | {i['nome']} | {d} | {bt} | {b['origem']} | "
                 f"{i['severidade']} | {i['dono']} | [{i['runbook']}](#{i['runbook'].lower()}) |")
    for rid, rb in spec["runbooks"].items():
        L += ["", f"## {rid}", "", f"**{rb['titulo']}**. Disparado por: " + ", ".join(rb["gatilho"]) + ".", ""]
        L += [f"{n}. {p}" for n, p in enumerate(rb["passos"], 1)]
        L += ["", "Ação específica por indicador:", ""]
        L += [f"- **{g}** ({por[g]['nome']}): {acao(por[g], c)}" for g in rb["gatilho"]]
        L += ["", f"Escalonamento: {rb['escalonamento']}."]
    return "\n".join(L) + "\n"


# ===================================================================================================== main
def artefatos(c: dict | None = None) -> dict[str, str]:
    c = c or carregar()
    erros = validar(c)
    if erros:
        raise ValueError("indicadores.yaml inválido:\n  " + "\n  ".join(erros))
    return {"view": sql_view(c), "alertas": alertas_yaml(c), "painel_bundle": painel_bundle_yaml(),
            "painel": json.dumps(painel(c), ensure_ascii=False, indent=2) + "\n", "runbooks": runbooks_md(c)}


def main() -> None:
    arts = artefatos()
    if "--checar" in sys.argv:
        velhos = [str(SAIDAS[k].relative_to(RAIZ)) for k, v in arts.items()
                  if not SAIDAS[k].exists() or SAIDAS[k].read_text("utf-8") != v]
        if velhos:
            sys.exit("desatualizados (rode `python -m sanidade.gerar`): " + ", ".join(velhos))
        print("artefatos da F9 atualizados")
        return
    for k, v in arts.items():
        SAIDAS[k].parent.mkdir(parents=True, exist_ok=True)
        SAIDAS[k].write_text(v, "utf-8")
        print("gerado", SAIDAS[k].relative_to(RAIZ))


if __name__ == "__main__":
    main()
