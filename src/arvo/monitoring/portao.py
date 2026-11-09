"""F9 · Portão de envio: nenhum apontamento sai se algum indicador CRÍTICO estiver em ALERTA.

Mesma regra no Databricks (src/arvo/monitoring/notebooks/portao_envio.py, sobre ops.v_sanidade_status)
e localmente (lista de linhas da view). SEM_FONTE, SEM_DADO e CALIBRANDO não bloqueiam: o painel mostra, e o
critério de go-live da F10 exige que os indicadores críticos tenham fonte antes do envio automático.
"""
from __future__ import annotations


def avaliar_portao(linhas: list[dict]) -> dict:
    bloqueios = [{k: r[k] for k in ("id_indicador", "nome", "recorte", "valor", "dono", "runbook", "acao")}
                 for r in linhas if r["bloqueia_envio"] and r["status"] == "ALERTA"]
    criticos_sem_medicao = sorted({r["id_indicador"] for r in linhas
                                   if r["bloqueia_envio"] and r["status"] in ("SEM_FONTE", "SEM_DADO")})
    return {"liberado": not bloqueios, "bloqueios": bloqueios, "criticos_sem_medicao": criticos_sem_medicao}


SQL_PORTAO = """SELECT id_indicador, nome, recorte, valor, dono, runbook, acao
FROM ops.v_sanidade_status WHERE bloqueia_envio AND status = 'ALERTA'"""
