"""Schema de extração: o mesmo para TODOS os provedores.

Decisão de design (plano v2, 7.3): usar o MENOR DENOMINADOR COMUM entre provedores.
- objeto plano o suficiente, todos os campos `required`, `additionalProperties: false`
- apenas type, properties, items, required, enum, description
- SEM pattern, minimum/maximum, minLength, oneOf/anyOf, $ref, que cada provedor rejeita ou ignora de um jeito diferente

Toda restrição fina (8 dígitos, data ISO, teto > 0, unicidade...) é validada AQUI, em código.
Aderência ao schema não é acurácia: o grounding e o consenso (grounding.py, reconciliacao.py) cuidam disso.
"""
from __future__ import annotations

import re

from arvo.ai.telemetria import sha256_json

SCHEMA_ID = "extracao_contrato"
SCHEMA_VERSAO = "1.0.0"

TIPOS_REGRA = ["PRECO_TETO", "EXCLUSAO_AUDITORIA", "PACOTE_ITEM_INCLUSO", "ITEM_EXCLUIDO_PACOTE",
               "TAXA_CONDICIONADA_CARATER"]
TIPOS_GLOSA = ["INTEGRAL", "EXCEDENTE", "NENHUMA"]
CARATERES = ["ELETIVO", "URGENCIA_EMERGENCIA"]          # domínio canônico da camada semântica (F2)
MODELOS_REMUNERACAO = ["fee_for_service", "pacote", "capitation", "drg", "outro"]


def _s(desc: str) -> dict:
    return {"type": "string", "description": desc}


def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


QUOTE = "Trecho LITERAL copiado do documento que comprova os valores deste item. Não parafraseie."

SCHEMA: dict = _obj({
    "contrato": _obj({
        "id_contrato": _s("Número do contrato, exatamente como no documento."),
        "operadora": _s("Razão social da operadora."),
        "prestador": _s("Razão social do prestador."),
        "modelo_remuneracao": {"type": "string", "enum": MODELOS_REMUNERACAO},
        "vigencia_inicio": _s("Data de início da vigência no formato AAAA-MM-DD."),
        "vigencia_meses": {"type": "integer", "description": "Duração da vigência em meses."},
        "quote_id": _s(QUOTE),
        "quote_partes": _s(QUOTE),
        "quote_modelo": _s(QUOTE),
        "quote_vigencia": _s(QUOTE),
    }),
    "anexo_i": {"type": "array", "description": "Uma entrada por linha da tabela de preços pactuados.",
                "items": _obj({
                    "codigo": _s("Código TUSS com 8 dígitos, como texto."),
                    "descricao": _s("Descrição do item como no documento."),
                    "tipo": _s("Tipo do item como no documento (Procedimento, Taxa, SADT, Material, Medicamento)."),
                    "valor_teto": {"type": "number", "description": "Valor unitário pactuado em reais (ex.: 4200.00)."},
                    "quote": _s(QUOTE),
                })},
    "anexo_ii": {"type": "array", "description": "Uma entrada por procedimento em regime de pacote.",
                 "items": _obj({
                     "codigo_procedimento": _s("Código TUSS do procedimento em pacote."),
                     "taxa_sala_codigo": _s("Código TUSS da taxa de sala inclusa no pacote."),
                     "materiais_rotina": {"type": "array", "items": {"type": "string"},
                                          "description": "Códigos TUSS dos materiais inclusos no pacote."},
                     "quote": _s(QUOTE),
                 })},
    "taxas_condicionadas": {"type": "array",
                            "description": "Taxas cuja cobrança depende do caráter do atendimento.",
                            "items": _obj({
                                "codigo": _s("Código TUSS da taxa."),
                                "carater_permitido": {"type": "array", "items": {"type": "string", "enum": CARATERES}},
                                "clausula": _s("Número da cláusula (ex.: 4.1)."),
                                "quote": _s(QUOTE),
                            })},
    "regras": {"type": "array",
               "description": "Somente cláusulas que determinam glosa ou excluem algo da auditoria/pacote.",
               "items": _obj({
                   "clausula": _s("Número da cláusula (ex.: 2.2)."),
                   "tipo": {"type": "string", "enum": TIPOS_REGRA},
                   "tipo_glosa": {"type": "string", "enum": TIPOS_GLOSA},
                   "quote": _s(QUOTE),
               })},
    "campos_nao_encontrados": {"type": "array", "items": {"type": "string"},
                               "description": "Campos que você NÃO encontrou no documento. Nunca invente."},
})


def schema_hash(schema: dict | None = None) -> str:
    return sha256_json(schema or SCHEMA)


# ----------------------------------------------------------------------------- validação em código
_COD = re.compile(r"^\d{8}$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLAUSULA = re.compile(r"^\d{1,2}\.\d{1,2}$")


def _estrutura(valor, esquema: dict, caminho: str, erros: list[str]) -> None:
    t = esquema.get("type")
    if t == "object":
        if not isinstance(valor, dict):
            erros.append(f"{caminho}: esperado objeto")
            return
        props = esquema["properties"]
        for k in esquema["required"]:
            if k not in valor:
                erros.append(f"{caminho}.{k}: ausente")
        for k in valor:
            if k not in props:
                erros.append(f"{caminho}.{k}: campo não previsto")
        for k, sub in props.items():
            if k in valor:
                _estrutura(valor[k], sub, f"{caminho}.{k}", erros)
    elif t == "array":
        if not isinstance(valor, list):
            erros.append(f"{caminho}: esperado lista")
            return
        for i, v in enumerate(valor):
            _estrutura(v, esquema["items"], f"{caminho}[{i}]", erros)
    elif t == "string":
        if not isinstance(valor, str):
            erros.append(f"{caminho}: esperado texto")
        elif "enum" in esquema and valor not in esquema["enum"]:
            erros.append(f"{caminho}: valor fora do domínio ({valor})")
    elif t == "integer":
        if not (isinstance(valor, int) and not isinstance(valor, bool)):
            erros.append(f"{caminho}: esperado inteiro")
    elif t == "number":
        if not (isinstance(valor, (int, float)) and not isinstance(valor, bool)):
            erros.append(f"{caminho}: esperado número")


def validar(dados) -> list[str]:
    """Retorna a lista de erros (vazia = válido). Estrutura + restrições finas que o schema comum não expressa."""
    erros: list[str] = []
    _estrutura(dados, SCHEMA, "$", erros)
    if erros:
        return erros
    c = dados["contrato"]
    if not _DATA.match(c["vigencia_inicio"]):
        erros.append("$.contrato.vigencia_inicio: formato AAAA-MM-DD")
    if c["vigencia_meses"] <= 0:
        erros.append("$.contrato.vigencia_meses: deve ser > 0")
    vistos = set()
    for i, it in enumerate(dados["anexo_i"]):
        if not _COD.match(it["codigo"]):
            erros.append(f"$.anexo_i[{i}].codigo: 8 dígitos")
        if it["codigo"] in vistos:
            erros.append(f"$.anexo_i[{i}].codigo: duplicado ({it['codigo']})")
        vistos.add(it["codigo"])
        if it["valor_teto"] <= 0 or round(it["valor_teto"], 2) != it["valor_teto"]:
            erros.append(f"$.anexo_i[{i}].valor_teto: > 0 e no máximo 2 casas decimais")
    for i, p in enumerate(dados["anexo_ii"]):
        for campo in ("codigo_procedimento", "taxa_sala_codigo"):
            if not _COD.match(p[campo]):
                erros.append(f"$.anexo_ii[{i}].{campo}: 8 dígitos")
        for m in p["materiais_rotina"]:
            if not _COD.match(m):
                erros.append(f"$.anexo_ii[{i}].materiais_rotina: código inválido {m}")
    for i, t in enumerate(dados["taxas_condicionadas"]):
        if not _COD.match(t["codigo"]):
            erros.append(f"$.taxas_condicionadas[{i}].codigo: 8 dígitos")
        if not t["carater_permitido"]:
            erros.append(f"$.taxas_condicionadas[{i}].carater_permitido: vazio")
        if not _CLAUSULA.match(t["clausula"]):
            erros.append(f"$.taxas_condicionadas[{i}].clausula: formato N.N")
    for i, r in enumerate(dados["regras"]):
        if not _CLAUSULA.match(r["clausula"]):
            erros.append(f"$.regras[{i}].clausula: formato N.N")
    return erros


# Registro na camada de IA: todo adapter valida a resposta desta tarefa com `validar` (estrutura + restrições finas).
from arvo.ai import esquemas  # noqa: E402

esquemas.registrar(SCHEMA_ID, SCHEMA_VERSAO, validar)
