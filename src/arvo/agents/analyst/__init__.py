"""Agente analista: perguntas de negócio sobre a auditoria e o funil, respondidas a partir da camada semântica.

  python -m arvo.agents.analyst "quanto glosamos por cláusula em junho?"
  python -m arvo.agents.analyst "..." --orquestrador databricks_gpt_oss --sem-genie

Montagem a partir de config.yaml (nesta pasta). Ver src/arvo/agents/analyst/README.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[4]
CONFIG = Path(__file__).resolve().parent / "config.yaml"


def carregar_config(caminho: Path = CONFIG) -> dict:
    return yaml.safe_load(Path(caminho).read_text("utf-8"))


def space_id(cfg: dict) -> str | None:
    p = RAIZ / cfg["genie"]["estado"]
    if not p.exists():
        return None
    return json.loads(p.read_text("utf-8")).get(cfg["databricks"]["perfil"] or "workspace", {}).get("space_id")


def construir_orquestrador(o: dict, perfil: str | None):
    from arvo.agents.providers.agente_llm import AnthropicAgenteAdapter, ChatToolsAdapter
    if o["tipo"] == "anthropic":
        return AnthropicAgenteAdapter(o["nome"], o["modelo"], o.get("familia", "anthropic"), o.get("effort", "high"),
                                      o.get("server_fallbacks", True), o.get("perimetro", "externo"))
    if o["tipo"] == "chat_tools":
        return ChatToolsAdapter(o["nome"], o["modelo"], o["familia"], o.get("provedor", "databricks_gateway"),
                                o.get("perimetro", "plataforma"), perfil)
    raise ValueError(f"tipo de orquestrador desconhecido: {o['tipo']}")


def construir(cfg: dict | None = None, orquestrador: str | None = None, com_genie: bool = True,
              com_warehouse: bool = True):
    """Agente montado pela configuração. `orquestrador` restringe a cadeia a um adapter."""
    from arvo.agents.providers.databricks_dados import DatabricksSQLExecutor, GenieConsultaAdapter, warehouse_por_nome
    from arvo.ai.telemetria import TelemetriaJSONL
    from arvo.agents.analyst.agente import Agente
    from arvo.agents.analyst.ferramentas import Ferramentas

    cfg = cfg or carregar_config()
    db = cfg["databricks"]
    perfil = db.get("perfil") or None
    executor = None
    if com_warehouse:
        executor = DatabricksSQLExecutor(warehouse_por_nome(db["warehouse"], perfil), db["catalogo"], perfil)
    sid = space_id(cfg) if com_genie else None
    genie = GenieConsultaAdapter(sid, perfil) if sid else None
    cadeia = [construir_orquestrador(o, perfil) for o in cfg["orquestradores"]
              if orquestrador is None or o["nome"] == orquestrador]
    if not cadeia:
        raise ValueError(f"orquestrador '{orquestrador}' não está em {CONFIG.name}")
    return Agente(cadeia, Ferramentas(consulta_dados=genie, executor_sql=executor, catalogo_uc=db["catalogo"]),
                  sink=TelemetriaJSONL(RAIZ / cfg["telemetria"]), max_turnos=cfg.get("max_turnos", 8))
