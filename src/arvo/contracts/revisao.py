"""Pacote de revisão humana e aprovação (gate da F3).

`gerar_pacote` cria `revisao.md` (para ler) e `aprovacao.yaml` (para o Jurídico preencher e assinar).
`aprovar` só aceita o YAML completo: assinatura e papel, decisão para cada campo sem consenso verificado,
e confirmação explícita do bloco com consenso. Depois roda a sanidade e emite `contract_params.json` versionado.
Nada disso é feito pelo agente em nome de uma pessoa.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from arvo.contracts.reconciliacao import CONSENSO_VERIFICADO
from arvo.contracts.sanidade import checar
from arvo.ai.telemetria import sha256_json

ORDEM_FONTES = ["D", "A", "B"]


def _fmt(v):
    if isinstance(v, tuple):
        return ", ".join(v)
    return v


def gerar_pacote(pasta: Path, rec: dict, estado: dict, meta: dict) -> None:
    pend = [l for l in rec["campos"] if l["status"] != CONSENSO_VERIFICADO]
    L = [f"# Revisão humana: extração do contrato {meta['contrato']}", "",
         f"- Documento: `{meta['documento']}` · sha256 `{meta['documento_sha256'][:16]}…`",
         f"- Run: `{meta['run_id']}` · chave de idempotência `{estado['chave_idempotencia'][:16]}…` · modo **{meta['modo']}**",
         f"- Extratores: " + ", ".join(f"{f} ({rec['familias'][f]})" for f in rec["fontes"]),
         f"- Independência reduzida (A e B da mesma família): **{'SIM' if rec['independencia_reduzida'] else 'não'}**",
         f"- Campos: {rec['n_campos']} · " + " · ".join(f"{k}: {v}" for k, v in rec["resumo"].items()),
         f"- Artefatos do parser: {meta['artefatos']}", ""]
    if meta["modo"] == "simulado":
        L += ["> **Atenção: os extratores A e B deste run são SIMULADOS** (fixtures). Servem para demonstrar e testar o",
              "> fluxo. Para produção, rode em modo `real` com ≥ 2 provedores configurados.", ""]
    L += ["## 1. Campos que exigem decisão", "",
          "| Campo | Status | " + " | ".join(rec["fontes"]) + " | Citação verificada | Juiz |",
          "|---|---|" + "---|" * len(rec["fontes"]) + "---|---|"]
    for l in pend:
        vals = [str(_fmt(l["fontes"][f]["valor"])) if f in l["fontes"] else "—" for f in rec["fontes"]]
        ver = ", ".join(f"{f}:{'✔' if v['quote_ok'] and v['valor_ok'] else '✘'}" for f, v in l["fontes"].items())
        j = l.get("juiz")
        jtxt = f"{j['veredito']}{'' if j['quote_ok'] else ' (citação não verificada)'}" if j else "—"
        L.append(f"| `{l['campo']}` | {l['status']} | " + " | ".join(vals) + f" | {ver} | {jtxt} |")
    if not pend:
        L.append("| — | nenhum | | | |")
    L += ["", "### Citações dos campos pendentes", ""]
    for l in pend:
        L.append(f"**`{l['campo']}`**")
        for f, v in l["fontes"].items():
            L.append(f"- {f} ({'verificada' if v['quote_ok'] else 'NÃO encontrada no documento'}"
                     f"{'' if v['valor_ok'] else '; valor não aparece na citação'}): “{v['quote']}”")
        if l.get("juiz"):
            L.append(f"- Juiz: {l['juiz']['veredito']}: {l['juiz']['justificativa']}")
        L.append("")
    L += ["## 2. Campos com consenso verificado (aceite em bloco)", "",
          "| Campo | Valor |", "|---|---|"]
    for l in rec["campos"]:
        if l["status"] == CONSENSO_VERIFICADO:
            L.append(f"| `{l['campo']}` | {_fmt(l['valor_proposto'])} |")
    (pasta / "revisao.md").write_text("\n".join(L) + "\n", "utf-8")

    modelo = {
        "contrato": meta["contrato"], "chave_idempotencia": estado["chave_idempotencia"],
        "aprovado_por": "", "papel": "juridico", "data": "", "decisao_geral": "",
        "confirmo_consenso_verificado": False,
        "campos": [{"campo": l["campo"], "status": l["status"],
                    "candidatos": {f: (list(v["valor"]) if isinstance(v["valor"], tuple) else v["valor"])
                                   for f, v in l["fontes"].items()},
                    "decisao": ""} for l in pend],
    }
    cab = ("# Preencha e assine. decisao_geral: APROVAR | REJEITAR.\n"
           "# Em cada campo: 'decisao' = valor final (use a mesma forma dos candidatos) ou EXCLUIR.\n")
    (pasta / "aprovacao.yaml").write_text(cab + yaml.safe_dump(modelo, allow_unicode=True, sort_keys=False), "utf-8")


def _converter(campo: str, valor):
    if campo.endswith(".valor_teto"):
        return round(float(valor), 2)
    if campo.endswith(".vigencia_meses"):
        return int(valor)
    if campo.endswith((".materiais_rotina", ".carater_permitido")):
        return sorted(valor if isinstance(valor, (list, tuple)) else [x.strip() for x in str(valor).split(",")])
    return valor


def reconstruir(extracoes: dict, rec: dict, decisoes: dict) -> dict:
    """Monta os parâmetros finais: consenso verificado + decisões humanas. EXCLUIR remove o item."""
    fontes = [f for f in ORDEM_FONTES if f in extracoes]
    final = {l["campo"]: (l["valor_proposto"] if l["status"] == CONSENSO_VERIFICADO else decisoes[l["campo"]])
             for l in rec["campos"]}

    def primeiro(lista_por_fonte, chave, k):
        for f in fontes:
            for it in extracoes[f][lista_por_fonte]:
                if it[chave] == k:
                    return dict(it)
        return None

    out = {"contrato": {}, "anexo_i": [], "anexo_ii": [], "taxas_condicionadas": [], "regras": []}
    base_c = extracoes[fontes[0]]["contrato"]
    for campo in ("id_contrato", "operadora", "prestador", "modelo_remuneracao", "vigencia_inicio", "vigencia_meses"):
        v = final.get(f"contrato.{campo}")
        out["contrato"][campo] = base_c[campo] if campo in ("operadora", "prestador") and v != "EXCLUIR" else (
            _converter(campo, v) if v not in (None, "EXCLUIR") else None)
    for campo, v in final.items():
        if v == "EXCLUIR" or campo.startswith("contrato."):
            continue
        # "regra.2.2.tipo": a chave do item pode conter ponto (número de cláusula), então separe pelas pontas
        tipo_item, resto = campo.split(".", 1)
        chave_item, atributo = resto.rsplit(".", 1)
        partes = [tipo_item, chave_item, atributo]
        if partes[0] == "anexo_i":
            it = primeiro("anexo_i", "codigo", partes[1])
            it["valor_teto"] = _converter(campo, v)
            out["anexo_i"].append(it)
        elif partes[0] == "anexo_ii" and partes[2] == "taxa_sala_codigo":
            it = primeiro("anexo_ii", "codigo_procedimento", partes[1])
            it["taxa_sala_codigo"] = v
            mat = final.get(f"anexo_ii.{partes[1]}.materiais_rotina")
            it["materiais_rotina"] = _converter(".materiais_rotina", mat) if mat not in (None, "EXCLUIR") else []
            out["anexo_ii"].append(it)
        elif partes[0] == "taxa_condicionada":
            it = primeiro("taxas_condicionadas", "codigo", partes[1])
            it["carater_permitido"] = _converter(campo, v)
            out["taxas_condicionadas"].append(it)
        elif partes[0] == "regra" and partes[2] == "tipo":
            it = primeiro("regras", "clausula", partes[1])
            it["tipo"] = v
            g = final.get(f"regra.{partes[1]}.tipo_glosa")
            it["tipo_glosa"] = g if g not in (None, "EXCLUIR") else "NENHUMA"
            out["regras"].append(it)
    return out


def aprovar(pasta: Path, extracoes: dict, rec: dict, aprovacao: dict, estado, doc_sha: str,
            sinistro_codigos: set[str] | None = None) -> dict:
    problemas = []
    for k in ("aprovado_por", "data"):
        if not str(aprovacao.get(k) or "").strip():
            problemas.append(f"'{k}' em branco")
    if aprovacao.get("papel") != "juridico":
        problemas.append("papel deve ser 'juridico'")
    if aprovacao.get("chave_idempotencia") != estado.dados["chave_idempotencia"]:
        problemas.append("aprovação pertence a outro run")
    if aprovacao.get("decisao_geral") not in ("APROVAR", "REJEITAR"):
        problemas.append("decisao_geral deve ser APROVAR ou REJEITAR")
    if problemas:
        raise ValueError("aprovação incompleta: " + "; ".join(problemas))
    if aprovacao["decisao_geral"] == "REJEITAR":
        estado.avancar("REJEITADO", f"rejeitado por {aprovacao['aprovado_por']}")
        return {"estado": "REJEITADO"}

    decisoes = {c["campo"]: c["decisao"] for c in aprovacao.get("campos", [])}
    pend = [l["campo"] for l in rec["campos"] if l["status"] != CONSENSO_VERIFICADO]
    faltando = [c for c in pend if decisoes.get(c) in (None, "")]
    if faltando:
        raise ValueError(f"campos sem decisão: {faltando}")
    if not aprovacao.get("confirmo_consenso_verificado"):
        raise ValueError("confirme o bloco de campos com consenso verificado (confirmo_consenso_verificado: true)")

    params = reconstruir(extracoes, rec, decisoes)
    checks = checar(params, sinistro_codigos=sinistro_codigos)
    bloqueios = [c for c in checks if not c["ok"] and c["severidade"] == "BLOQUEIA"]
    (pasta / "sanidade.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), "utf-8")
    if bloqueios:
        estado.avancar("REJEITADO", f"sanidade bloqueou: {[c['id'] for c in bloqueios]}")
        return {"estado": "REJEITADO", "bloqueios": bloqueios}

    corpo = {k: params[k] for k in ("contrato", "anexo_i", "anexo_ii", "taxas_condicionadas", "regras")}
    h = sha256_json(corpo)[:8]
    versao = f"{params['contrato']['id_contrato']}@{aprovacao['data']}-{h}"
    saida = {"versao_contrato": versao, "documento_sha256": doc_sha, "aprovado_por": aprovacao["aprovado_por"],
             "papel": aprovacao["papel"], "data_aprovacao": aprovacao["data"],
             "origem_campos": {l["campo"]: (l["status"] if l["status"] == CONSENSO_VERIFICADO else "DECISAO_HUMANA")
                               for l in rec["campos"]}, **corpo}
    (pasta / "contract_params.json").write_text(json.dumps(saida, ensure_ascii=False, indent=2), "utf-8")
    (pasta / "vinculo.yaml").write_text(yaml.safe_dump(para_vinculo(saida), allow_unicode=True, sort_keys=False), "utf-8")
    estado.avancar("APROVADO", versao)
    return {"estado": "APROVADO", "versao_contrato": versao}


def para_vinculo(p: dict) -> dict:
    """Converte para o formato de src/arvo/semantic/vinculos/<contrato>.yaml (F2), substituindo a transcrição manual."""
    c = p["contrato"]
    mats = sorted({m for x in p["anexo_ii"] for m in x["materiais_rotina"]})
    return {
        "id_contrato": c["id_contrato"], "modelo_remuneracao": c["modelo_remuneracao"],
        "vigencia": {"inicio": c["vigencia_inicio"], "meses": c["vigencia_meses"]},
        "status": "aprovado_F3", "versao": p["versao_contrato"],
        "itens_com_preco_pactuado": [{"codigo": i["codigo"], "teto": i["valor_teto"]} for i in p["anexo_i"]],
        "pacotes": {"escopo": "conta", "itens_inclusos_comuns": mats,
                    "procedimentos": [{"codigo": x["codigo_procedimento"], "taxa_sala_inclusa": x["taxa_sala_codigo"]}
                                      for x in p["anexo_ii"]]},
        "taxas_condicionadas_ao_carater": [{"codigo": t["codigo"], "carater_permitido": t["carater_permitido"]}
                                           for t in p["taxas_condicionadas"]],
        "regras": [{"clausula": r["clausula"], "tipo": r["tipo"], "tipo_glosa": r["tipo_glosa"]} for r in p["regras"]],
    }
