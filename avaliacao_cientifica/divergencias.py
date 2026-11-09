"""Classificação das divergências motor × gabarito e teste de "regra escondida" versus "ruído de rotulagem".

Cada divergência recebe uma causa PROVÁVEL (hipótese, não veredito: o veredito é da adjudicação cega):
  FP · REGRA_CONTRATUAL_LITERAL   o motor aplicou uma cláusula com condição objetiva (preço > teto, item incluso em pacote,
                                  taxa em atendimento eletivo). Se o rótulo diz "Não", o mais provável é erro do gabarito
  FN · SEM_BASE_CONTRATUAL        nenhuma cláusula se aplica (preço ≤ teto, item não incluso, sem taxa condicionada).
                                  Ou o rótulo está errado, ou existe regra fora do contrato (AMB-03)
Sinais extras do FN: item repetido na conta, procedimento do próprio pacote, conflito semântico.

Teste de permutação: se os "Sim" sem base contratual vierem de uma regra escondida, eles se CONCENTRAM em algum conceito.
Ruído de rotulagem se espalha na proporção da base. H0 = taxa de "Sim" entre os não glosados independe do conceito.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def classificar(base: pd.DataFrame) -> pd.DataFrame:
    b = base.copy()
    b["n_mesmo_cod_conta"] = b.groupby(["id_conta", "cod_tuss"]).id_item.transform("count")
    b["razao_teto"] = b.vl_unitario / b.vl_teto_unitario
    rot = b[b.rotulado]
    linhas = []
    for _, r in rot[rot.pred & ~rot.real].iterrows():
        linhas.append({"id_item": r.id_item, "tipo": "FP", "regra_motor": r.regra_principal,
                       "causa": "REGRA_CONTRATUAL_LITERAL", "hipotese": "erro de rotulagem do gabarito (condição objetiva)",
                       "evidencia": r.justificativa, "vl_em_jogo": round(r.vl_glosado, 2)})
    for _, r in rot[~rot.pred & rot.real].iterrows():
        sinais = []
        if r.razao_teto <= 1:
            sinais.append(f"preço {r.razao_teto:.1%} do teto")
        if r.n_mesmo_cod_conta > 1:
            sinais.append(f"código repetido {int(r.n_mesmo_cod_conta)}× na conta")
        if r.conceito == "PROCEDIMENTO_CIRURGICO" and r.conta_tem_pacote:
            sinais.append("é o próprio procedimento do pacote")
        if r.regime == "PRONTO_SOCORRO" and r.carater_canonico == "ELETIVO":
            sinais.append("conflito semântico PS × Eletivo")
        linhas.append({"id_item": r.id_item, "tipo": "FN", "regra_motor": None, "causa": "SEM_BASE_CONTRATUAL",
                       "hipotese": "ruído de rotulagem ou regra fora do contrato (AMB-03)",
                       "evidencia": "; ".join(sinais) or "nenhuma cláusula aplicável",
                       "vl_em_jogo": round(r.vl_cobrado, 2)})
    return pd.DataFrame(linhas)


def teste_concentracao(base: pd.DataFrame, por: str = "conceito", n: int = 5000, semente: int = 3) -> dict:
    """Permutação do qui-quadrado entre os rotulados NÃO glosados: p alto = sem concentração (compatível com ruído)."""
    d = base[base.rotulado & ~base.pred][[por, "real"]]

    def chi2(rotulos: np.ndarray) -> float:
        t = pd.crosstab(d[por].values, rotulos)
        esperado = np.outer(t.sum(1), t.sum(0)) / t.values.sum()
        with np.errstate(divide="ignore", invalid="ignore"):
            return float(np.nansum((t.values - esperado) ** 2 / esperado))

    obs = chi2(d.real.values)
    rng = np.random.default_rng(semente)
    perm = [chi2(rng.permutation(d.real.values)) for _ in range(n)]
    taxa = d.groupby(por).real.mean().round(3).to_dict()
    return {"estatistica_chi2": obs, "p_valor_permutacao": float(np.mean([p >= obs for p in perm])),
            "taxa_sim_entre_nao_glosados": float(d.real.mean()), "taxa_por_" + por: taxa, "n": int(len(d))}
