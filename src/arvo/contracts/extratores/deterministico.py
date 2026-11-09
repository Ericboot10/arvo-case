"""Extrator D: determinístico, sem LLM.

Papel: (1) baseline independente para o consenso; (2) fallback quando nenhum provedor de IA está disponível
(degradação graciosa: o sistema continua entregando, com revisão humana).
Limitação assumida: é dependente de LAYOUT (cabeçalhos de tabela e numeração "N.N."). Contrato com outro layout
leva a campos ausentes, o que gera status INCOMPLETO na reconciliação e manda o caso para revisão. Nunca é aceito em silêncio.
"""
from __future__ import annotations

import re

from arvo.contracts.grounding import normalizar
from arvo.contracts.parsing import limpar_celula
from arvo.ai.ports import ParsedDoc

NOME = "deterministico"
FAMILIA = "regras"

_COD = re.compile(r"\b(\d{8})\b")
_BRL = re.compile(r"R\$\s*([\d\.]+,\d{2})")
_MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
          "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}

# (tipo, tipo_glosa, marcadores no texto normalizado). Heurística explícita e auditável.
_REGRAS = [
    ("PRECO_TETO", "EXCEDENTE", ["naopoderaoexceder", "montanteexcedente"]),
    ("EXCLUSAO_AUDITORIA", "NENHUMA", ["naosendoobjetodaauditoria"]),
    ("PACOTE_ITEM_INCLUSO", "INTEGRAL", ["vedadaacobrancaemseparado"]),
    ("ITEM_EXCLUIDO_PACOTE", "NENHUMA", ["naointegramopacote"]),
    ("TAXA_CONDICIONADA_CARATER", "INTEGRAL", ["integralmenteglosada", "carátereletivo"]),
]


def _brl(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def _primeira_frase(t: str, limite: int = 220) -> str:
    return t[:limite].rsplit(" ", 1)[0] if len(t) > limite else t


def extrair(doc: ParsedDoc) -> dict:
    txt = doc.texto_limpo
    flat = " ".join(txt.split())

    # ---------------- contrato
    m_id = re.search(r"Contrato\s+n\W*\s*([A-Z]{2,5}-\d{4}-\d{3,5})", flat)
    m_partes = re.search(r"De um lado,\s+(.+?),\s+inscrita.+?de outro,\s+(.+?),\s+inscrito", flat)
    m_mod = re.search(r"Modalidade\s+(fee-for-\s?service)", flat, re.I)
    m_vig = re.search(r"vigorar[áa]\s+por\s+(\d+)\s*\(([^)\x00]*)[)\x00]?\s*meses\s+a\s+contar\s+de\s+(\d{1,2})\W*\s*de\s+"
                      r"(\w+)\s+de\s+(\d{4})", flat)
    contrato = {
        "id_contrato": m_id.group(1) if m_id else "",
        "operadora": m_partes.group(1) if m_partes else "",
        "prestador": m_partes.group(2) if m_partes else "",
        "modelo_remuneracao": "fee_for_service" if m_mod else "outro",
        "vigencia_inicio": (f"{m_vig.group(5)}-{_MESES.get(m_vig.group(4).lower(), 0):02d}-{int(m_vig.group(3)):02d}"
                            if m_vig else ""),
        "vigencia_meses": int(m_vig.group(1)) if m_vig else 0,
        "quote_id": m_id.group(0) if m_id else "",
        "quote_partes": m_partes.group(0) if m_partes else "",
        "quote_modelo": m_mod.group(0) if m_mod else "",
        "quote_vigencia": m_vig.group(0) if m_vig else "",
    }
    nao_encontrados = [k for k in ("id_contrato", "operadora", "vigencia_inicio") if not contrato[k]]

    # ---------------- tabelas (classificadas pelo cabeçalho)
    anexo_i, anexo_ii = [], []
    for t in doc.tabelas:
        cab = normalizar(" ".join(t["cabecalho"]))
        tipo_tab = "i" if "valorpactuado" in cab else "ii" if "taxadesala" in cab else None
        # Continuação de tabela SEM cabeçalho repetido (o extrator de PDF devolve a 1ª linha de dados como
        # "cabeçalho"): a linha volta a ser dado e cada linha é classificada pelo FORMATO. Falha achada pelo golden v6.
        linhas = t["linhas"] if tipo_tab else [t["cabecalho"]] + t["linhas"]
        for r in linhas:
            cel = [limpar_celula(c) for c in r]
            quote = " ".join(cel)
            tipo_linha = tipo_tab or _tipo_pela_forma(cel)
            if tipo_linha == "i" and len(cel) >= 4 and _COD.fullmatch(cel[0] or ""):
                mv = _BRL.search(cel[3])
                if mv:
                    anexo_i.append({"codigo": cel[0], "descricao": cel[1], "tipo": cel[2],
                                    "valor_teto": _brl(mv.group(1)), "quote": quote})
            elif tipo_linha == "ii" and len(cel) >= 4 and _COD.fullmatch(cel[0] or ""):
                salas = _COD.findall(cel[2])
                anexo_ii.append({"codigo_procedimento": cel[0], "taxa_sala_codigo": salas[0] if salas else "",
                                 "materiais_rotina": _COD.findall(cel[3]), "quote": quote})
    if not anexo_i:
        nao_encontrados.append("anexo_i")
    if not anexo_ii:
        nao_encontrados.append("anexo_ii")

    # ---------------- regras e taxas condicionadas (pela segmentação de cláusulas)
    regras, taxas = [], []
    for num, texto in doc.clausulas.items():
        n = normalizar(texto)
        for tipo, glosa, marcas in _REGRAS:
            if any(normalizar(mk) in n for mk in marcas):
                if tipo == "TAXA_CONDICIONADA_CARATER" and "eletiv" not in n:
                    continue
                regras.append({"clausula": num, "tipo": tipo, "tipo_glosa": glosa, "quote": _primeira_frase(texto)})
                break
        if "exclusivamente" in n and ("urgencia" in n or "emergencia" in n):
            for cod in _COD.findall(texto):
                taxas.append({"codigo": cod, "carater_permitido": ["URGENCIA_EMERGENCIA"], "clausula": num,
                              "quote": _primeira_frase(texto, 400)})

    out = {"contrato": contrato, "anexo_i": anexo_i, "anexo_ii": anexo_ii, "taxas_condicionadas": taxas,
           "regras": regras, "campos_nao_encontrados": nao_encontrados}
    return _sem_nul(out)


def _tipo_pela_forma(cel: list[str]) -> str | None:
    """Anexo I: código, descrição, tipo e 'R$ valor'. Anexo II: código, procedimento, sala '(porte' e materiais."""
    if len(cel) < 4 or not _COD.fullmatch(cel[0] or ""):
        return None
    if _BRL.search(cel[3]):
        return "i"
    if _COD.search(cel[2]) and "porte" in cel[2].lower():
        return "ii"
    return None


def _sem_nul(o):
    """Remove o artefato \\x00 do PDF das citações (a verificação normalizada continua casando)."""
    if isinstance(o, str):
        return o.replace("\x00", "")
    if isinstance(o, list):
        return [_sem_nul(v) for v in o]
    if isinstance(o, dict):
        return {k: _sem_nul(v) for k, v in o.items()}
    return o
