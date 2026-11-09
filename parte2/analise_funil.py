"""F11 · Parte 2: números do memo e do deck do funil de economia, reproduzíveis a partir da planilha.

  python -m parte2.analise_funil

Escopo (AMB-06, resolvido): operação inteira da Parthenon, com toda a rede, num mês (sinistro médio mensal de R$ 70 mi).
Premissas (AMB-05 em aberto): definição de cada etapa;
benchmark = efetivado ÷ enviado ao prestador nos outros clientes; desligada não gera valor após a identificação.
Cenários: efeitos aplicados em sequência; efetivação atual nas ligadas e benchmark nas novas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PLANILHA = RAIZ / "arvo.case" / "Inteligencias_apos_6_meses.xlsx"
META = 0.02
EXCLUIR_DAS_ONDAS = {"Alto Markup", "Quantidade excessiva de terapia internação"}   # benchmark < 20%: reformular
ONDAS = {
    1: ["Quantidade excessiva de taxas", "Conformidade vias de acesso", "Códigos inválidos"],
    2: ["Sobreposição de SADT", "Quantidade excessiva SADT ambulatorial", "Reexecução SADT"],
    3: ["Quantidade Excessiva de Materiais", "Quantidade excessiva de terapia sequencial",
        "Cobrança em excesso de anatomia patológica",
        "Cobrança indevida de procedimentos ambulatoriais durante internação"],
}


@dataclass(frozen=True)
class Cenario:
    nome: str
    registro: float          # piso da taxa de registro nas ligadas
    envio: float             # piso da taxa de envio nas ligadas
    envio_novas: float       # envio nas desligadas que forem ligadas
    registro_novas: float
    efetivacao_markup: float | None   # None = Alto Markup não é ligada


CENARIOS = [
    Cenario("conservador", 0.85, 0.75, 0.60, 0.85, None),
    Cenario("base", 0.90, 0.85, 0.80, 0.90, 0.30),
    Cenario("agressivo", 0.95, 0.90, 0.90, 0.95, 0.50),
]


def carregar(caminho: Path = PLANILHA) -> tuple[pd.DataFrame, float]:
    bruto = pd.read_excel(caminho, header=None)
    assert bruto.iat[0, 0] == "Sinistro Processado", "layout da planilha mudou"
    sinistro = float(bruto.iat[0, 1])
    cab = bruto.index[bruto[0] == "Inteligencias"][0]
    df = bruto.iloc[cab + 1:, [0, 1, 2, 3, 4, 5, 6, 8]].dropna(how="all")
    df.columns = ["inteligencia", "tipo", "status", "ident", "env_op", "env_pr", "efet", "bench"]
    df = df[df.inteligencia.ne("Total")].copy()
    for c in ["ident", "env_op", "env_pr", "efet", "bench"]:
        df[c] = df[c].astype(float)
    df["ligada"] = df.status.str.lower().str.startswith("ligad")
    return df.reset_index(drop=True), sinistro


def funil(df: pd.DataFrame, sinistro: float) -> dict:
    lig = df[df.ligada]
    ident, ident_l = df.ident.sum(), lig.ident.sum()
    eo, ep, ef = lig.env_op.sum(), lig.env_pr.sum(), lig.efet.sum()
    return {
        "identificado": ident, "desligadas": ident - ident_l, "retido_operadora": ident_l - eo,
        "perda_registro": eo - ep, "perda_recurso": ep - ef, "efetivado": ef,
        "M21_identificacao": ident / sinistro, "M22_ativacao": ident_l / ident, "M23_envio": eo / ident_l,
        "M24_registro": ep / eo, "M18_efetivacao": ef / ep, "M20_norte": ef / sinistro,
        "envio_tecnicas": lig[lig.tipo == "Técnica"].env_op.sum() / lig[lig.tipo == "Técnica"].ident.sum(),
        "envio_administrativas": lig[lig.tipo == "Administrativa"].env_op.sum() / lig[lig.tipo == "Administrativa"].ident.sum(),
    }


def efetivado(df: pd.DataFrame, c: Cenario, frentes: tuple[str, ...] = ("registro", "envio", "ativacao", "markup")) -> float:
    lig = df[df.ligada]
    envio = lig.env_op / lig.ident
    reg = lig.env_pr / lig.env_op
    efr = lig.efet / lig.env_pr
    eo = lig.ident * (envio.clip(lower=c.envio) if "envio" in frentes else envio)
    ep = eo * (reg.clip(lower=c.registro) if "registro" in frentes else reg)
    total = float((ep * efr).sum())
    des = df[~df.ligada]
    if "ativacao" in frentes:
        novas = des[des.inteligencia.isin(sum(ONDAS.values(), []))]
        total += float((novas.ident * c.envio_novas * c.registro_novas * novas.bench).sum())
    if "markup" in frentes and c.efetivacao_markup is not None:
        mk = des[des.inteligencia == "Alto Markup"].ident.sum()
        total += mk * c.envio_novas * c.registro_novas * c.efetivacao_markup
    return total


def ponte(df: pd.DataFrame, c: Cenario) -> list[tuple[str, float]]:
    """Ganho de cada frente, aplicadas em sequência (registro → envio → ativação → markup)."""
    passos, ant, feitas = [("hoje", efetivado(df, c, ()))], efetivado(df, c, ()), ()
    for f in ("registro", "envio", "ativacao", "markup"):
        feitas += (f,)
        v = efetivado(df, c, feitas)
        passos.append((f, v - ant))
        ant = v
    return passos


def resumo() -> dict:
    df, sin = carregar()
    return {"sinistro": sin, "meta": META * sin, "funil": funil(df, sin),
            "ondas_identificado": {k: float(df[df.inteligencia.isin(v)].ident.sum()) for k, v in ONDAS.items()},
            "cenarios": {c.nome: efetivado(df, c) for c in CENARIOS},
            "ponte_agressivo": ponte(df, CENARIOS[-1])}


if __name__ == "__main__":
    print(json.dumps(resumo(), ensure_ascii=False, indent=2))
