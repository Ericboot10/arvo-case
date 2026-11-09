"""Testes de sanidade do contrato extraído (antes de virar parâmetro do motor de regras)."""
from __future__ import annotations

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
OBRIGATORIAS = {"PRECO_TETO", "PACOTE_ITEM_INCLUSO", "TAXA_CONDICIONADA_CARATER"}


def checar(params: dict, mapa_tuss: Path | None = None, sinistro_codigos: set[str] | None = None) -> list[dict]:
    """Cada checagem: {id, ok, detalhe, severidade: BLOQUEIA|ALERTA}."""
    r = []

    def add(i, ok, detalhe, sev="BLOQUEIA"):
        r.append({"id": i, "ok": bool(ok), "detalhe": detalhe, "severidade": sev})

    ai = {it["codigo"]: it["valor_teto"] for it in params["anexo_i"]}
    add("S01_anexo_i_nao_vazio", len(ai) > 0, f"{len(ai)} itens")
    add("S02_teto_positivo_2_casas", all(v > 0 and round(v, 2) == v for v in ai.values()), "valores > 0, 2 casas")
    for p in params["anexo_ii"]:
        add(f"S03_pacote_{p['codigo_procedimento']}_procedimento_no_anexo_i", p["codigo_procedimento"] in ai,
            "procedimento em pacote precisa ter preço pactuado (Cl. 3.1)")
        add(f"S04_pacote_{p['codigo_procedimento']}_sala_no_anexo_i", p["taxa_sala_codigo"] in ai,
            f"taxa de sala {p['taxa_sala_codigo']}")
        add(f"S05_pacote_{p['codigo_procedimento']}_materiais_no_anexo_i",
            all(m in ai for m in p["materiais_rotina"]), f"materiais {p['materiais_rotina']}")
    for t in params["taxas_condicionadas"]:
        add(f"S06_taxa_{t['codigo']}_no_anexo_i", t["codigo"] in ai, "taxa condicionada com preço pactuado")
    tipos = {x["tipo"] for x in params["regras"]}
    add("S07_regras_obrigatorias", OBRIGATORIAS <= tipos, f"faltando: {sorted(OBRIGATORIAS - tipos)}")
    c = params["contrato"]
    add("S08_vigencia", c["vigencia_meses"] > 0 and len(c["vigencia_inicio"]) == 10,
        f"{c['vigencia_inicio']} + {c['vigencia_meses']} meses")

    mapa_tuss = mapa_tuss or RAIZ / "semantic" / "map_tuss_conceito.yaml"
    if mapa_tuss.exists():
        mapeados = {m["codigo"] for m in yaml.safe_load(mapa_tuss.read_text("utf-8"))["codigos"]}
        falt = sorted(set(ai) - mapeados)
        add("S09_codigos_com_conceito_semantico", not falt, f"sem conceito (F2): {falt}")
    if sinistro_codigos is not None:
        fora = sorted(sinistro_codigos - set(ai))
        add("S10_cobertura_sinistro", True, f"códigos do sinistro fora do Anexo I (Cl. 2.3): {fora or 'nenhum'}",
            sev="ALERTA")
    return r
