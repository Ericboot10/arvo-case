"""F9 · Gera, a partir de src/arvo/monitoring/indicadores.yaml (fonte única), tudo o que o painel precisa:

  src/arvo/monitoring/databricks/v_sanidade_status.sql   view ops.v_sanidade_status (1 linha por indicador × recorte, com status)
  resources/alerts/monitoring.yml             SQL alerts (v2) do bundle, um por indicador não-INFO
  resources/dashboards/monitoring.yml         dashboard AI/BI do bundle (catálogo por target)
  src/arvo/monitoring/dashboard/painel_sanidade.lvdash.json
  src/arvo/monitoring/RUNBOOKS.md

Dois dialetos para a MESMA definição:
  databricks  métricas via MEASURE() das UC Metric Views (semantic.mv_*), tabelas schema.tabela após USE CATALOG
  local       a mesma fórmula de src/arvo/semantic/metricas.yaml direto na tabela gold (Spark local, views temporárias
              schema__tabela). As metric views também são geradas dessa fórmula, então os dois são equivalentes.

  python -m arvo.monitoring.gerar            gera os artefatos
  python -m arvo.monitoring.gerar --checar   falha se algum artefato gerado estiver desatualizado (CI)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
AQUI = Path(__file__).resolve().parent
SPEC = AQUI / "indicadores.yaml"
DESTINOS = AQUI / "destinos.yaml"
SAIDAS = {
    "view": AQUI / "databricks" / "v_sanidade_status.sql",
    "alertas": RAIZ / "resources" / "alerts" / "monitoring.yml",
    "painel_bundle": RAIZ / "resources" / "dashboards" / "monitoring.yml",
    "painel": AQUI / "dashboard" / "painel_sanidade.lvdash.json",
    "runbooks": AQUI / "RUNBOOKS.md",
}
SEVERIDADES = ["CRITICA", "ALTA", "MEDIA", "INFO"]
STATUS = ["OK", "ALERTA", "CALIBRANDO", "SEM_DADO", "SEM_FONTE"]
# Criadas pelo próprio job da F9 antes da view de status (resources/jobs/monitoring.yml · monitoring_refresh)
CRIADAS_PELO_JOB_F9 = {"ops.v_ia_sanidade"}
CRON = {"CRITICA": "0 0 * * * ?", "ALTA": "0 0 7 * * ?", "MEDIA": "0 0 7 * * ?"}   # quartz
FONTE_REDE = "gold.fato_funil_economia"   # planilha da rede (Parte II); o resto do negócio é o agente no São Rafael (Parte I)
REF = re.compile(r"\{([a-z_]+\.[a-z_]+)\}")


# ===================================================================================================== carga
def carregar() -> dict:
    ler = lambda p: yaml.safe_load(Path(p).read_text("utf-8"))  # noqa: E731
    spec = ler(SPEC)
    met = ler(RAIZ / "src" / "arvo" / "semantic" / "metricas.yaml")
    mod = ler(RAIZ / "src" / "arvo" / "architecture" / "modelo.yaml")
    glo = ler(RAIZ / "src" / "arvo" / "semantic" / "glossario.yaml")
    ia = ler(RAIZ / "src" / "arvo" / "ai" / "config" / "alertas_ia.yaml")
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
            return {"max": 0, "origem": "src/arvo/ai/config/alertas_ia.yaml (drift_modelo)"}
        lim = c["ia"]["limites"][ind["limite_ia"]]
        return {k: lim[k] for k in ("min", "max") if k in lim} | {"origem": "src/arvo/ai/config/alertas_ia.yaml"}
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
        if i["camada"] == "negocio":
            esp = "rede" if FONTE_REDE in fontes(i, c) else "sao_rafael"
            if i.get("escopo") not in spec["escopos"]:
                erros.append(f"{p}: indicador de negócio sem escopo (sao_rafael | rede)")
            elif i["escopo"] != esp:
                erros.append(f"{p}: escopo {i['escopo']} diverge da fonte (esperado {esp})")
        elif "escopo" in i:
            erros.append(f"{p}: escopo só vale para a camada negocio")
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
                erros.append(f"{p}: fonte {f} não está em src/arvo/architecture/modelo.yaml")
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


def secao(i: dict, spec: dict) -> tuple[int, str]:
    """(posição, título) da seção do indicador. O negócio se divide pelo escopo: Parte I antes da Parte II."""
    cam = spec["camadas"][i["camada"]]
    if i["camada"] == "negocio":
        e = spec["escopos"][i["escopo"]]
        return (cam["ordem"] * 10 + e["ordem"], e["titulo"])
    return (cam["ordem"] * 10, cam["titulo"])


def select_status(c: dict, dialeto: str, disponiveis: set[str]) -> str:
    """O SELECT da view ops.v_sanidade_status. Indicadores sem fonte entram com status SEM_FONTE (não somem).
    `ordem` agrupa por seção (Parte I, Parte II, semântica, dados, IA) e, dentro dela, segue o YAML."""
    spec = c["spec"]
    meta = []
    for pos, i in enumerate(spec["indicadores"], 1):
        tem = all(f in disponiveis for f in fontes(i, c))
        b = banda(i, c)
        sec_ordem, sec_titulo = secao(i, spec)
        meta.append("(" + ", ".join([
            _lit(i["id"]), str(sec_ordem * 1000 + pos), _lit(i["camada"]), _lit(spec["camadas"][i["camada"]]["titulo"]),
            _lit(i.get("escopo") or "plataforma"), _lit(sec_titulo), _lit(i["familia"]),
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
  AS t(id_indicador, ordem, camada, camada_titulo, escopo, secao, familia, nome, definicao, severidade, bloqueia_envio, dono,
       runbook, acao, origem_banda, fonte_disponivel)
),
medicoes AS (
  {union}
)
SELECT m.ordem, m.id_indicador, m.camada, m.camada_titulo, m.escopo, m.secao, m.familia, m.nome, m.definicao, m.severidade,
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
-- F9 · ops.v_sanidade_status. GERADO por `python -m arvo.monitoring.gerar`. NÃO EDITE À MÃO.
-- Fonte: src/arvo/monitoring/indicadores.yaml (+ src/arvo/semantic/metricas.yaml, src/arvo/ai/config/alertas_ia.yaml, src/arvo/architecture/modelo.yaml)
-- 1 linha por indicador × recorte, com banda, status, dono e runbook. Alimenta o painel e os alertas SQL.
-- Pré-requisitos no mesmo job: src/arvo/semantic/databricks/02_metric_views.sql e src/arvo/ai/databricks/v_ia_sanidade.sql
-- Sem fonte hoje (status SEM_FONTE até a tabela existir; regerar após mudar o modelo): {', '.join(sem) or 'nenhum'}
-- =====================================================================================================
USE CATALOG IDENTIFIER(:catalog);

CREATE OR REPLACE VIEW ops.v_sanidade_status
COMMENT 'Indicadores de sanidade (F9): negócio primeiro (Parte I · agente no São Rafael, depois Parte II · funil da rede), depois semântica, dados e IA. Fonte: src/arvo/monitoring/indicadores.yaml'
AS
{select_status(c, "databricks", disp)};
"""


# ===================================================================================================== alertas
def _rotulo(i: dict) -> str:
    return {"sao_rafael": "Parte I · ", "rede": "Parte II · "}.get(i.get("escopo"), "")


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
        out[f"monitoring_{i['id'].lower()}"] = {      # padrão: arvo-<domínio> · <id> · <nome> [<severidade>]
            "display_name": f"arvo-monitoring · {i['id']} · {_rotulo(i)}{i['nome']} [{i['severidade']}]",
            "query_text": ("SELECT count_if(status = 'ALERTA') AS n_alerta, "
                           "concat_ws('; ', collect_list(CASE WHEN status = 'ALERTA' THEN recorte END)) AS recortes "
                           f"FROM ${{var.catalog}}.ops.v_sanidade_status WHERE id_indicador = '{i['id']}'"),
            "warehouse_id": "${var.warehouse_id}",
            "custom_summary": f"{i['id']} em ALERTA · dono {i['dono']} · {i['runbook']}",
            "custom_description": f"Ação: {acao(i, c)} | Runbook {i['runbook']} ({rb['titulo']}): src/arvo/monitoring/RUNBOOKS.md"
                                  + (" | BLOQUEIA O ENVIO" if i["severidade"] == "CRITICA" else ""),
            "evaluation": {"comparison_operator": "GREATER_THAN", "source": {"name": "n_alerta"},
                           "threshold": {"value": {"double_value": 0}}, "notification": notif},
            "schedule": {"quartz_cron_schedule": CRON[i["severidade"]], "timezone_id": "America/Sao_Paulo"},
        }
    cab = ("# GERADO por `python -m arvo.monitoring.gerar` a partir de src/arvo/monitoring/indicadores.yaml. NÃO EDITE À MÃO.\n"
           "# SQL alerts (v2) do bundle (CLI ≥ 0.279.0). Em `mode: development` as agendas ficam pausadas.\n"
           "# Destinos de notificação por dono: src/arvo/monitoring/destinos.yaml (IDs de notification destinations, G9).\n")
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


# ===================================================================================================== painel · dados do case
# Parte I: cada item de conta do São Rafael com as colunas originais do CSV e a decisão do agente.
# O identificador do beneficiário aparece só como pseudônimo (ADR-006: o id em claro existe apenas na bronze).
SQL_ITENS_SAO_RAFAEL = """
SELECT s.id_prestador, s.id_item, s.id_conta, s.id_beneficiario_hash AS id_beneficiario_pseudonimo,
       s.dt_atendimento, s.carater_origem AS carater_atendimento, s.regime_origem AS tipo_conta, s.cod_tuss,
       s.desc_item_origem AS desc_item, s.tipo_item_origem AS tipo_item, s.qtd, s.vl_unitario, s.vl_total, s.nome_prestador,
       CASE WHEN i.glosado THEN 'Sim' ELSE 'Não' END AS glosado,
       CAST(coalesce(a.vl_glosado, 0) AS DECIMAL(12, 2)) AS vl_glosado,
       a.regra_principal, a.clausula_principal,
       CASE r.defensabilidade WHEN 'mais_forte' THEN 'Mais defensável' WHEN 'muito_forte' THEN 'Muito forte'
            WHEN 'forte_com_ressalva' THEN 'Forte, com ressalva' WHEN 'forte_fragil_em_ps' THEN 'Forte; frágil em Pronto Socorro'
            WHEN 'fragil' THEN 'Frágil' END AS defensabilidade,
       nullif(array_join(a.clausulas_subsidiarias, ', '), '') AS clausulas_subsidiarias,
       coalesce(a.justificativa, 'Sem glosa: nenhuma regra do contrato PRT-2025-0417 se aplica ao item.') AS justificativa,
       CASE WHEN a.id_item IS NULL THEN NULL
            WHEN a.status_envio = 'REVISAO_HUMANA' THEN concat('Revisão humana: ', a.motivo_revisao)
            WHEN d.destino_envio = 'NAO_ENVIAR' THEN 'Não enviada: regra em shadow (F10)'
            WHEN d.destino_envio = 'ENVIO_AUTOMATICO' THEN 'Envio automático'
            WHEN d.destino_envio IS NOT NULL THEN d.destino_envio
            ELSE 'Pronta; aguarda decisão do rollout' END AS situacao_glosa,
       CASE WHEN g.rotulado THEN CASE WHEN g.real THEN 'Sim' ELSE 'Não' END END AS gabarito_indevido
FROM silver.item_conta s
JOIN gold.fato_item_auditado i ON i.id_item = s.id_item
LEFT JOIN gold.fato_apontamento a ON a.id_item = s.id_item
LEFT JOIN gold.dim_regra r ON r.versao_regra = a.versao_regra
LEFT JOIN (SELECT id_apontamento, max_by(destino_envio, decidido_em) AS destino_envio
           FROM ops.rollout_destino GROUP BY id_apontamento) d ON d.id_apontamento = a.id_apontamento
LEFT JOIN gold.v_avaliacao_gabarito g ON g.id_item = s.id_item
ORDER BY s.id_conta, s.id_item"""
COLS_ITENS = ["id_prestador", "id_item", "id_conta", "id_beneficiario_pseudonimo", "dt_atendimento", "carater_atendimento",
              "tipo_conta", "cod_tuss", "desc_item", "tipo_item", "qtd", "vl_unitario", "vl_total", "nome_prestador",
              "glosado", "vl_glosado", "regra_principal", "clausula_principal", "defensabilidade", "clausulas_subsidiarias",
              "justificativa", "situacao_glosa", "gabarito_indevido"]

# Parte II: tudo sai das colunas da planilha (gold.fato_funil_economia, competência mais recente). Nada estimado,
# exceto `total_possivel` = economia identificada × média de efetivação Arvo (duas colunas da planilha), que supõe a
# inteligência ligada e todo o identificado chegando ao prestador. A meta de 2% do sinistro é a do contrato com a Parthenon.
_FUNIL_ULTIMA = "f AS (SELECT * FROM gold.fato_funil_economia WHERE competencia = (SELECT max(competencia) FROM gold.fato_funil_economia))"
SQL_PLANILHA = f"""
WITH {_FUNIL_ULTIMA},
linhas AS (
  SELECT 0 AS ordem, inteligencia, tipo_inteligencia AS tipo, status_inteligencia AS status, vl_identificado,
         vl_enviado_operadora, vl_enviado_prestador, vl_efetivado, taxa_efetivacao_benchmark,
         vl_identificado * taxa_efetivacao_benchmark AS vl_possivel
  FROM f
  UNION ALL
  SELECT 1, 'Total', '', '', sum(vl_identificado), sum(vl_enviado_operadora), sum(vl_enviado_prestador), sum(vl_efetivado),
         avg(taxa_efetivacao_benchmark), sum(vl_identificado * taxa_efetivacao_benchmark)
  FROM f)
SELECT inteligencia, tipo, status,
       round(vl_identificado, 2) AS economia_identificada, round(vl_enviado_operadora, 2) AS enviada_operadora,
       round(vl_enviado_prestador, 2) AS enviada_prestador, round(vl_efetivado, 2) AS economia_efetivada,
       round(100 * taxa_efetivacao_benchmark, 1) AS media_efetivacao_todos_clientes_pct,
       round(vl_possivel, 2) AS total_possivel, round(vl_possivel - vl_efetivado, 2) AS falta_para_o_possivel
FROM linhas ORDER BY ordem, CASE status WHEN 'Ligada' THEN 0 ELSE 1 END, vl_identificado DESC"""
COLS_PLANILHA = ["inteligencia", "tipo", "status", "economia_identificada", "enviada_operadora", "enviada_prestador",
                 "economia_efetivada", "media_efetivacao_todos_clientes_pct", "total_possivel", "falta_para_o_possivel"]
SQL_META = f"""
WITH {_FUNIL_ULTIMA},
t AS (SELECT sum(vl_identificado) AS ident, sum(vl_efetivado) AS efet,
             sum(vl_identificado * taxa_efetivacao_benchmark) AS poss, max(vl_sinistro_processado) AS sin FROM f)
SELECT round(sin, 2) AS sinistro_operadora, round(0.02 * sin, 2) AS meta_rs,
       round(efet, 2) AS economia_efetivada, round(100 * efet / sin, 2) AS efetivado_pct_sinistro,
       round(100 * efet / (0.02 * sin), 1) AS efetivado_pct_meta,
       round(poss, 2) AS total_possivel, round(100 * poss / sin, 2) AS possivel_pct_sinistro,
       round(100 * poss / (0.02 * sin), 1) AS possivel_pct_meta,
       round(ident, 2) AS economia_identificada, round(100 * ident / sin, 2) AS identificado_pct_sinistro
FROM t"""
# Funil em R$: cada etapa é uma coluna da planilha; a perda é a diferença entre duas colunas (sem interpretar o motivo).
SQL_FUNIL_ETAPAS = f"""
WITH {_FUNIL_ULTIMA},
t AS (SELECT CAST(sum(vl_identificado) AS DOUBLE) AS ident,
             CAST(sum(CASE WHEN status_inteligencia = 'Ligada' THEN vl_identificado END) AS DOUBLE) AS lig,
             CAST(sum(vl_enviado_operadora) AS DOUBLE) AS op, CAST(sum(vl_enviado_prestador) AS DOUBLE) AS pr,
             CAST(sum(vl_efetivado) AS DOUBLE) AS ef, CAST(max(vl_sinistro_processado) AS DOUBLE) AS sin FROM f)
SELECT etapa, round(valor, 2) AS valor_rs, round(100 * valor / sin, 2) AS pct_sinistro,
       round(100 * valor / ident, 1) AS pct_do_identificado, round(perda, 2) AS perda_rs, origem_da_perda
FROM t LATERAL VIEW stack(5,
  '1 · Identificada (26 inteligências)', ident, CAST(NULL AS DOUBLE), '',
  '2 · Identificada nas ligadas', lig, ident - lig, 'Inteligências com status Desligada: identificam, mas a planilha não registra envio',
  '3 · Enviada a operadora', op, lig - op, 'Identificada nas ligadas − Enviada a Operadora',
  '4 · Enviada para prestador', pr, op - pr, 'Enviada a Operadora − Enviada para Prestador',
  '5 · Efetivada', ef, pr - ef, 'Enviada para Prestador − Efetivado') s AS etapa, valor, perda, origem_da_perda
ORDER BY etapa"""



def painel(c: dict) -> dict:
    """Dashboard AI/BI (.lvdash.json). Datasets sem catálogo: o bundle injeta dataset_catalog por target."""
    esc = c["spec"]["escopos"]

    def status(chave: str, titulo: str, filtro: str) -> dict:
        return _ds(f"ds_status_{chave}", f"Status · {titulo}", f"""
SELECT {', '.join(SELECT_STATUS)}, ordem FROM ops.v_sanidade_status WHERE {filtro}
ORDER BY CASE status WHEN 'ALERTA' THEN 0 WHEN 'SEM_DADO' THEN 1 WHEN 'CALIBRANDO' THEN 2 WHEN 'SEM_FONTE' THEN 3 ELSE 4 END,
         ordem, recorte""")

    secoes = [(e, t["titulo"], f"escopo = '{e}'") for e, t in esc.items()] + \
             [(cam, t["titulo"], f"camada = '{cam}'") for cam, t in c["spec"]["camadas"].items() if cam != "negocio"]

    datasets = [
        _ds("ds_resumo", "Resumo por seção × status", """
SELECT secao, status, count(*) AS indicadores FROM ops.v_sanidade_status GROUP BY ALL"""),
        _ds("ds_itens", "Parte I · itens de conta do São Rafael com a decisão do agente", SQL_ITENS_SAO_RAFAEL),
        _ds("ds_planilha", "Parte II · planilha de inteligências (linha a linha)", SQL_PLANILHA),
        _ds("ds_meta", "Parte II · meta e possível", SQL_META),
        _ds("ds_funil_etapas", "Parte II · funil em R$ (colunas da planilha)", SQL_FUNIL_ETAPAS),
        _ds("ds_parte1", "Parte I · glosa do agente no São Rafael", """
SELECT MEASURE(valor_glosado) AS valor_glosado, MEASURE(itens_glosados) AS itens_glosados,
       round(100 * MEASURE(taxa_glosa), 1) AS taxa_glosa_pct, MEASURE(valor_apresentado) AS valor_apresentado
FROM semantic.mv_auditoria_glosa"""),
        _ds("ds_portao", "Portão de envio", """
SELECT count_if(status = 'ALERTA' AND bloqueia_envio) AS bloqueios_de_envio,
       count_if(status = 'ALERTA') AS indicadores_em_alerta FROM ops.v_sanidade_status"""),
        _ds("ds_norte", "Parte II · índice-norte da rede (última competência)", """
SELECT competencia, round(100 * MEASURE(indice_norte), 2) AS indice_norte_pct,
       round(100 * MEASURE(atingimento_meta), 1) AS atingimento_meta_pct,
       MEASURE(economia_efetivada) AS economia_efetivada
FROM semantic.mv_funil_economia GROUP BY competencia ORDER BY competencia DESC LIMIT 1"""),
        _ds("ds_fatores", "Parte II · fatores do norte (M21 × M22 × M23 × M24 × M18)", """
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
    ] + [status(*s) for s in secoes]

    parte1 = [
        _texto("t_p1", [f"## {esc['sao_rafael']['titulo']}",
                        "Cada linha é um item de conta do sinistro do Hospital São Rafael (jun/2025), com as colunas originais "
                        f"de `{esc['sao_rafael']['fonte']}` e a decisão do agente: glosado ou não, valor, regra e cláusula, "
                        "defensabilidade da regra principal e a justificativa.",
                        "Item em mais de uma regra: a principal é a de texto mais literal; as outras ficam como subsidiárias. "
                        "Valor **identificado**, não economia: nenhuma glosa foi enviada ao prestador e nada disso entra no "
                        "índice-norte da rede (Parte II). `gabarito_indevido` = rótulo do gabarito do case (263 itens)."], 0, 0, h=3),
        _contador("c_p1_valor", "ds_parte1", "valor_glosado", "Glosa identificada (R$)", 0, 3),
        _contador("c_p1_itens", "ds_parte1", "itens_glosados", "Itens glosados (de 1.696)", 2, 3),
        _contador("c_p1_taxa", "ds_parte1", "taxa_glosa_pct", "% do sinistro do hospital", 4, 3),
        _tabela("tb_itens", "ds_itens", COLS_ITENS, "Itens de conta · São Rafael · decisão do agente", 0, 6, h=16),
        _barra("b_regra", "ds_glosa_regra", "regra_principal", "valor_glosado", "Glosa por regra (R$)", 0, 22, w=6, h=5),
    ]
    parte2 = [
        _texto("t_p2", [f"## {esc['rede']['titulo']}",
                        f"Funil de economia da operação inteira, como está em `{esc['rede']['fonte']}`. Não depende do agente da Parte I.",
                        "Cada etapa é uma coluna da planilha: Identificada → (só as ligadas) → Enviada a Operadora → Enviada para "
                        "Prestador → Efetivado. A perda de cada etapa é a diferença entre duas colunas. **Índice-norte** = "
                        "efetivado ÷ sinistro da operadora (meta 2%)."], 0, 0, h=3),
        _contador("c_norte", "ds_norte", "indice_norte_pct", "Índice-norte da rede, % (meta 2%)", 0, 3),
        _contador("c_meta", "ds_norte", "atingimento_meta_pct", "Atingimento da meta, %", 2, 3),
        _contador("c_efet", "ds_norte", "economia_efetivada", "Economia efetivada (R$/mês)", 4, 3),
        _barra("b_funil", "ds_funil_etapas", "etapa", "valor_rs", "Funil em R$ (colunas da planilha)", 0, 6, w=6),
        _tabela("tb_funil", "ds_funil_etapas", ["etapa", "valor_rs", "pct_sinistro", "pct_do_identificado", "perda_rs",
                                                "origem_da_perda"], "Etapas e perdas", 0, 12, h=5),
    ]
    planilha = [
        _texto("t_pl", ["## Parte II · Inteligências da Arvo · planilha de 6 meses",
                        "Uma linha por inteligência, com as colunas da planilha. **total_possivel** = economia identificada × "
                        "média de efetivação de todos os clientes Arvo (duas colunas da planilha): quanto a inteligência renderia "
                        "ligada e com todo o identificado chegando ao prestador. Meta = 2% do sinistro processado da operadora."],
               0, 0, h=3),
        _contador("c_pl_efet", "ds_meta", "economia_efetivada", "Efetivado hoje (R$/mês)", 0, 3),
        _contador("c_pl_efet_sin", "ds_meta", "efetivado_pct_sinistro", "Efetivado, % do sinistro", 2, 3),
        _contador("c_pl_efet_meta", "ds_meta", "efetivado_pct_meta", "Quanto da meta de 2% já atingimos, %", 4, 3),
        _contador("c_pl_poss", "ds_meta", "total_possivel", "Possível com todas as inteligências (R$/mês)", 0, 6),
        _contador("c_pl_poss_sin", "ds_meta", "possivel_pct_sinistro", "Possível, % do sinistro", 2, 6),
        _contador("c_pl_poss_meta", "ds_meta", "possivel_pct_meta", "Possível, % da meta", 4, 6),
        _tabela("tb_planilha", "ds_planilha", COLS_PLANILHA, "Inteligências · linha a linha (última linha = total)", 0, 9, h=12),
    ]
    sanidade = [
        _texto("t_san", ["## Sanidade · indicadores de negócio",
                         "Status de cada indicador, separado por parte. Invariante em ALERTA **bloqueia o envio**. "
                         "CALIBRANDO = banda dinâmica ainda sem histórico; SEM_FONTE = tabela ainda não existe."], 0, 0),
        _contador("c_bloq", "ds_portao", "bloqueios_de_envio", "Bloqueios de envio (deve ser 0)", 0, 2),
        _contador("c_alertas", "ds_portao", "indicadores_em_alerta", "Indicadores em alerta", 2, 2),
        _tabela("tb_p1", "ds_status_sao_rafael", COLS_STATUS, "Indicadores · Parte I · São Rafael", 0, 5, h=10),
        _tabela("tb_p2", "ds_status_rede", COLS_STATUS, "Indicadores · Parte II · rede", 0, 15, h=10),
    ]
    pr = [
        _texto("t_pr", ["## Parte I · Precisão e recall · gabarito do case",
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
                        "Limites em `src/arvo/ai/config/alertas_ia.yaml`. Drift de modelo ou troca de provedor exige golden set.",
                        "Neste workspace não há chave de provedor de IA: a extração do contrato não rodou aqui e a página fica "
                        "vazia, em vez de mostrar telemetria simulada. O motor usa o contrato do case revisado na F2."], 0, 0, h=3),
        _barra("b_ia", "ds_ia_serie", "dia", "taxa_schema_valido", "Schema válido por dia", 0, 3, cor="tarefa_adapter", w=6),
        _tabela("tb_ia", "ds_status_ia", COLS_STATUS, "Indicadores de IA", 0, 9),
    ]
    geral = [
        _texto("t_geral", ["## Visão geral", "Quantos indicadores em cada status, por seção."], 0, 0),
        _barra("b_resumo", "ds_resumo", "secao", "indicadores", "Indicadores por status", 0, 2, cor="status", w=6),
    ]
    pg = lambda n, t, l: {"name": n, "displayName": t, "pageType": "PAGE_TYPE_CANVAS", "layout": l}  # noqa: E731
    return {"datasets": datasets,
            "pages": [pg("parte1_itens", "1 · Parte I · Itens de conta São Rafael", parte1),
                      pg("precisao_recall", "2 · Parte I · Precisão e recall", pr),
                      pg("parte2_funil", "3 · Parte II · Funil da rede", parte2),
                      pg("parte2_planilha", "4 · Parte II · Inteligências (planilha 6 meses)", planilha),
                      pg("sanidade", "5 · Sanidade · indicadores", sanidade),
                      pg("semantica_dados", "6 · Semântica e dados", sem_dados),
                      pg("ia", "7 · IA", ia), pg("geral", "8 · Visão geral", geral)]}


def painel_bundle_yaml() -> str:
    return """# GERADO por `python -m arvo.monitoring.gerar`. NÃO EDITE À MÃO.
# Dashboard AI/BI do painel de sanidade. dataset_catalog troca o catálogo por target (arvo_dev | arvo_stg | arvo_prod):
# os datasets do .lvdash.json não qualificam catálogo de propósito.
resources:
  dashboards:
    monitoring_dashboard:
      display_name: "arvo-monitoring-${bundle.target}"
      file_path: ../../src/arvo/monitoring/dashboard/painel_sanidade.lvdash.json
      warehouse_id: ${var.warehouse_id}
      dataset_catalog: ${var.catalog}
      embed_credentials: false
"""


# ===================================================================================================== runbooks
def runbooks_md(c: dict) -> str:
    spec = c["spec"]
    por = {i["id"]: i for i in spec["indicadores"]}
    L = ["# Runbooks do painel de sanidade (F9)", "",
         "> GERADO por `python -m arvo.monitoring.gerar` a partir de [`indicadores.yaml`](indicadores.yaml). Não edite à mão.", "",
         "Severidade: **CRITICA** bloqueia o envio do run e alerta a cada hora · **ALTA** alerta diário, ação no dia ·"
         " **MEDIA** alerta diário, ação na semana · **INFO** só painel.", "",
         "## Indicadores", "", "| Id | Seção | Indicador | Definição | Banda | Origem da banda | Severidade | Dono | Runbook |",
         "|---|---|---|---|---|---|---|---|---|"]
    for i in spec["indicadores"]:
        b = banda(i, c)
        if "sigma" in b:
            bt = f"±{b['sigma']}σ das {b['janela']} competências anteriores (mín. {b['historico_min']})"
        else:
            bt = " · ".join(x for x in [f"≥ {b['min']}" if "min" in b else "", f"≤ {b['max']}" if "max" in b else ""] if x)
        d = i.get("metrica") or (f"limite IA `{i['limite_ia']}`" if "limite_ia" in i else "SQL próprio")
        L.append(f"| {i['id']} | {secao(i, spec)[1]} | {i['nome']} | {d} | {bt} | {b['origem']} | "
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
            sys.exit("desatualizados (rode `python -m arvo.monitoring.gerar`): " + ", ".join(velhos))
        print("artefatos da F9 atualizados")
        return
    for k, v in arts.items():
        SAIDAS[k].parent.mkdir(parents=True, exist_ok=True)
        SAIDAS[k].write_text(v, "utf-8")
        print("gerado", SAIDAS[k].relative_to(RAIZ))


if __name__ == "__main__":
    main()
