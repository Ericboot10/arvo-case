"""Golden set de ACEITE de extratores de contrato (critério do Gate G7).

Casos: o contrato real (v0) e variantes construídas sobre o documento parseado (v1–v6). O ESPERADO vem da transcrição
HUMANA da F2 (semantic/vinculos) e das regras listadas pelo Jurídico, nunca de um extrator. A mesma transformação
aplicada ao documento é aplicada ao esperado.

Critério de aceite por extrator e variante (plano v2, 7.5):
  acurácia campo a campo ≥ 99%  ·  0 campos inventados  ·  100% das citações verificadas no documento
Um provedor de IA só entra em produção se passar em TODAS as variantes. Produção exige ≥ 2 provedores aprovados.

  python -m ia.avaliacao.golden --modo simulado     (determinístico + replay; não precisa de chave)
  python -m ia.avaliacao.golden --modo real         (inclui cada adapter configurado nos slots A/B da F3)
"""
from __future__ import annotations

import argparse
import copy
import json
import time
from pathlib import Path

import yaml

from arvo_contrato.extratores import deterministico
from arvo_contrato.extratores.llm import carregar_prompt, montar_requisicao
from arvo_contrato.grounding import Corpus, verificar
from arvo_contrato.parsing import PdfPlumberParser, segmentar_clausulas
from arvo_contrato.pipeline import carregar_config, construir_adapter
from arvo_contrato.reconciliacao import achatar
from arvo_contrato.schema import validar
from ia.ports import LLMParams
from ia.roteador import Orcamento, Roteador

RAIZ = Path(__file__).resolve().parents[2]
PDF = RAIZ / "arvo.case" / "Contrato-parthenon-x-hospital-sao-rafael.pdf"
AQUI = Path(__file__).resolve().parent
LIMIAR_ACURACIA = 0.99

# Regras que o Jurídico lista como "cláusulas que determinam glosa ou exclusão" (critério do prompt da F3)
REGRAS_ESPERADAS = [("2.2", "PRECO_TETO", "EXCEDENTE"), ("2.3", "EXCLUSAO_AUDITORIA", "NENHUMA"),
                    ("3.3", "PACOTE_ITEM_INCLUSO", "INTEGRAL"), ("3.4", "ITEM_EXCLUIDO_PACOTE", "NENHUMA"),
                    ("4.2", "TAXA_CONDICIONADA_CARATER", "INTEGRAL")]


def esperado_base() -> dict:
    v = yaml.safe_load((RAIZ / "semantic" / "vinculos" / "PRT-2025-0417.yaml").read_text("utf-8"))
    mats = v["pacotes"]["itens_inclusos_comuns"]
    return {
        "contrato": {"id_contrato": "PRT-2025-0417", "operadora": "PARTHENON SAÚDE OPERADORA DE PLANOS DE SAÚDE S.A.",
                     "prestador": "HOSPITAL SÃO RAFAEL LTDA", "modelo_remuneracao": v["modelo_remuneracao"],
                     "vigencia_inicio": v["vigencia"]["inicio"], "vigencia_meses": v["vigencia"]["meses"],
                     "quote_id": "", "quote_partes": "", "quote_modelo": "", "quote_vigencia": ""},
        "anexo_i": [{"codigo": i["codigo"], "descricao": "", "tipo": "", "valor_teto": float(i["teto"]), "quote": ""}
                    for i in v["itens_com_preco_pactuado"]],
        "anexo_ii": [{"codigo_procedimento": p["codigo"], "taxa_sala_codigo": p["taxa_sala_inclusa"],
                      "materiais_rotina": list(mats), "quote": ""} for p in v["pacotes"]["procedimentos"]],
        "taxas_condicionadas": [{"codigo": t["codigo"], "carater_permitido": t["carater_permitido"], "clausula": "4.1",
                                 "quote": ""} for t in v["taxas_condicionadas_ao_carater"]],
        "regras": [{"clausula": c, "tipo": t, "tipo_glosa": g, "quote": ""} for c, t, g in REGRAS_ESPERADAS],
        "campos_nao_encontrados": [],
    }


# ---------------------------------------------------------------------------------------------- variantes
def _tabela_anexo_i(doc, pagina):
    return next(t for t in doc.tabelas if t["pagina"] == pagina and "Valor pactuado" in " ".join(t["cabecalho"]))


def _trocar_preco(doc, esp, codigo, novo_txt, novo_valor):
    for t in doc.tabelas:
        if "Valor pactuado" not in " ".join(t["cabecalho"]):
            continue  # só o Anexo I: no Anexo II a 4ª coluna são os materiais (bug achado pelo próprio golden)
        for r in t["linhas"]:
            if r and r[0] == codigo:
                r[3] = novo_txt
    for i in esp["anexo_i"]:
        if i["codigo"] == codigo:
            i["valor_teto"] = novo_valor


def v1_precos(doc, esp):
    _trocar_preco(doc, esp, "31001012", "R$ 4.350,00", 4350.0)
    _trocar_preco(doc, esp, "40304361", "R$ 19,50", 19.5)
    _trocar_preco(doc, esp, "60012010", "R$ 495,00", 495.0)


def v2_clausula_renumerada(doc, esp):
    doc.texto_limpo = doc.texto_limpo.replace("2.2. Os valores cobrados", "2.5. Os valores cobrados")
    for r in esp["regras"]:
        if r["clausula"] == "2.2":
            r["clausula"] = "2.5"


def v3_linha_nova(doc, esp):
    _tabela_anexo_i(doc, 3)["linhas"].append(["60023012", "Diária de UTI pediátrica", "Taxa", "R$ 2.100,00"])
    esp["anexo_i"].append({"codigo": "60023012", "descricao": "", "tipo": "", "valor_teto": 2100.0, "quote": ""})


def v4_pacote_removido(doc, esp):
    for t in doc.tabelas:
        t["linhas"] = [r for r in t["linhas"] if not ("Taxa de sala" in " ".join(t["cabecalho"]) and r[0] == "30715016")]
    esp["anexo_ii"] = [p for p in esp["anexo_ii"] if p["codigo_procedimento"] != "30715016"]


def v5_codigo_trocado(doc, esp):
    doc.texto_limpo = doc.texto_limpo.replace("99999001", "99999002")
    for t in doc.tabelas:
        t["linhas"] = [[c.replace("99999001", "99999002") for c in r] for r in t["linhas"]]
    for i in esp["anexo_i"]:
        i["codigo"] = i["codigo"].replace("99999001", "99999002")
    for x in esp["taxas_condicionadas"]:
        x["codigo"] = "99999002"


def v6_tabela_sem_cabecalho_repetido(doc, esp):
    """Continuação do Anexo I na página 4 SEM repetir o cabeçalho: a 1ª linha de dados vira o 'cabeçalho'."""
    t = _tabela_anexo_i(doc, 4)
    t["cabecalho"], t["linhas"] = t["linhas"][0], t["linhas"][1:]


VARIANTES = {"v0_original": None, "v1_precos_alterados": v1_precos, "v2_clausula_renumerada": v2_clausula_renumerada,
             "v3_linha_nova_anexo_i": v3_linha_nova, "v4_pacote_removido": v4_pacote_removido,
             "v5_codigo_taxa_trocado": v5_codigo_trocado, "v6_tabela_sem_cabecalho": v6_tabela_sem_cabecalho_repetido}


def casos() -> dict:
    base = PdfPlumberParser().parse(PDF)
    out = {}
    for nome, f in VARIANTES.items():
        doc, esp = copy.deepcopy(base), esperado_base()
        if f:
            f(doc, esp)
            doc.clausulas = segmentar_clausulas(doc.texto_limpo)
            doc.sha256 = f"{base.sha256}:{nome}"
        out[nome] = (doc, esp)
    return out


# ---------------------------------------------------------------------------------------------- pontuação
def pontuar(extraido: dict | None, esperado: dict, doc) -> dict:
    if extraido is None:
        return {"acuracia": 0.0, "corretos": 0, "esperados": len(achatar(esperado)), "faltantes": ["(sem saída)"],
                "errados": [], "inventados": [], "quotes_ok": 0.0, "schema_ok": False, "aprovado": False}
    e = {k: v[0] for k, v in achatar(esperado).items()}
    x = {k: v[0] for k, v in achatar(extraido).items()}
    corretos = [k for k in e if k in x and x[k] == e[k]]
    errados = [k for k in e if k in x and x[k] != e[k]]
    faltantes = [k for k in e if k not in x]
    inventados = [k for k in x if k not in e]
    ev = verificar(extraido, Corpus(doc))
    quotes = sum(1 for v in ev.values() if v["quote_ok"] and v["valor_ok"]) / len(ev) if ev else 0.0
    acc = len(corretos) / len(e)
    schema_ok = not validar(extraido)
    return {"acuracia": round(acc, 4), "corretos": len(corretos), "esperados": len(e), "faltantes": faltantes,
            "errados": errados, "inventados": inventados, "quotes_ok": round(quotes, 4), "schema_ok": schema_ok,
            "aprovado": schema_ok and acc >= LIMIAR_ACURACIA and not inventados and quotes == 1.0}


def avaliar(modo: str = "simulado") -> dict:
    cfg = carregar_config()
    candidatos = {"deterministico": None}
    if modo == "real":
        for slot in ("A", "B"):
            for nome in cfg["modos"]["real"][slot]:
                candidatos[nome] = construir_adapter(nome, cfg["adapters"][nome])
    else:
        candidatos["replay_fiel"] = construir_adapter("replay_fiel", cfg["adapters"]["replay_fiel"])
    prompt = carregar_prompt(cfg["prompt_arquivo"])

    class _Sink:
        def __init__(self):
            self.r = []

        def gravar(self, rec):
            self.r.append(rec)

    sink = _Sink()
    rot = Roteador(sink, Orcamento(cfg["orcamento"]["max_tokens_run"] * 10, 200), precos=cfg.get("precos_usd_por_mtok", {}))
    resultado = {"modo": modo, "executado_em": time.strftime("%Y-%m-%dT%H:%M:%S"), "limiar_acuracia": LIMIAR_ACURACIA,
                 "candidatos": {}}
    for nome_caso, (doc, esp) in casos().items():
        for nome, ad in candidatos.items():
            if nome == "replay_fiel" and nome_caso != "v0_original":
                continue  # fixture estática: só serve para validar o harness no caso original
            if ad is None:
                extr = deterministico.extrair(doc)
            else:
                req = montar_requisicao(doc, prompt, LLMParams(**cfg["params"]), f"golden-{nome_caso}", "golden_extracao")
                res, _ = rot.gerar(req, [ad])
                extr = res.data if res and res.ok else None
            resultado["candidatos"].setdefault(nome, {})[nome_caso] = pontuar(extr, esp, doc)
    for nome, por_caso in resultado["candidatos"].items():
        por_caso["_aprovado_em_todas"] = all(v["aprovado"] for k, v in por_caso.items() if not k.startswith("_"))
    resultado["telemetria"] = [r.to_dict() for r in sink.r]
    llm_aprovados = [n for n, v in resultado["candidatos"].items()
                     if n not in ("deterministico", "replay_fiel") and v["_aprovado_em_todas"]]
    resultado["gate_G7_independencia"] = {"provedores_aprovados": llm_aprovados, "atende": len(llm_aprovados) >= 2}
    return resultado


def relatorio_md(r: dict) -> str:
    casos_ = list(VARIANTES)
    L = ["# Golden set de aceite: extração de contrato", "",
         f"Modo **{r['modo']}** · {r['executado_em']} · critério: acurácia ≥ {r['limiar_acuracia']:.0%}, 0 inventados, "
         "100% das citações verificadas.", "",
         "| Extrator | " + " | ".join(casos_) + " | Todas |", "|---|" + "---|" * (len(casos_) + 1)]
    for nome, por in r["candidatos"].items():
        cel = []
        for c in casos_:
            v = por.get(c)
            cel.append("—" if v is None else f"{'✅' if v['aprovado'] else '❌'} {v['acuracia']:.0%}")
        L.append(f"| `{nome}` | " + " | ".join(cel) + f" | {'✅' if por['_aprovado_em_todas'] else '❌'} |")
    L += ["", "## Falhas", ""]
    for nome, por in r["candidatos"].items():
        for c, v in por.items():
            if c.startswith("_") or v["aprovado"]:
                continue
            L.append(f"- `{nome}` × `{c}`: faltantes {v['faltantes'][:6]} · errados {v['errados'][:6]} · "
                     f"inventados {v['inventados'][:6]} · citações {v['quotes_ok']:.0%}")
    g = r["gate_G7_independencia"]
    L += ["", f"**Gate G7 (≥ 2 provedores de IA aprovados):** {'ATENDE' if g['atende'] else 'NÃO ATENDE'} · "
          f"aprovados: {g['provedores_aprovados'] or 'nenhum'}"]
    if r["modo"] == "simulado":
        L.append("> Modo simulado: nenhum provedor real avaliado (sem chave de API). Rode `--modo real` para o G7.")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", default="simulado", choices=["simulado", "real"])
    a = ap.parse_args()
    r = avaliar(a.modo)
    (AQUI / "relatorio_aceite.json").write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str), "utf-8")
    (AQUI / "relatorio_aceite.md").write_text(relatorio_md(r), "utf-8")
    print(relatorio_md(r))


if __name__ == "__main__":
    main()
