"""Grounding: todo valor extraído precisa de citação LITERAL verificável no documento.

Duas checagens, nesta ordem:
1. quote ⊂ documento: a citação existe no texto parseado (comparação normalizada, robusta a quebra de linha,
   espaçamento, acento, travessão e aos artefatos do PDF, mas nunca a paráfrase).
2. valor ⊂ quote: o valor extraído aparece DENTRO da própria citação. Isso pega o modelo que copia um trecho
   verdadeiro e devolve um número diferente (ex.: quote com "R$ 4.200,00" e valor_teto = 4300).

Referência: guia da Anthropic para reduzir alucinação (extrair citações literais e remover afirmações sem suporte).
A técnica é aplicada igual para qualquer provedor, porque a verificação é feita em código.
"""
from __future__ import annotations

import re
import unicodedata

from ia.ports import ParsedDoc
from .parsing import limpar_celula

MIN_QUOTE = 12  # caracteres normalizados; quotes curtas demais casam por acaso


def normalizar(s: str) -> str:
    s = s.replace("\x00", "")
    s = re.sub(r"[º°∘ª]", "", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^0-9a-z]", "", s)


class Corpus:
    """Representações do documento contra as quais uma citação é verificada."""

    def __init__(self, doc: ParsedDoc):
        self.texto = normalizar(doc.texto_limpo)
        # linhas de tabela em ordem de leitura (o texto corrido intercala as células de uma mesma linha)
        # inclui a linha de "cabeçalho": numa continuação sem cabeçalho repetido ela é dado (golden v6)
        self.linhas_tabela = [normalizar(" ".join(limpar_celula(c) for c in r))
                              for t in doc.tabelas for r in [t["cabecalho"]] + t["linhas"]]
        self.clausulas = {k: normalizar(v) for k, v in doc.clausulas.items()}

    def contem(self, quote: str) -> bool:
        q = normalizar(quote or "")
        if len(q) < MIN_QUOTE:
            return False
        return q in self.texto or any(q in l for l in self.linhas_tabela)

    def contem_na_clausula(self, quote: str, clausula: str) -> bool:
        q = normalizar(quote or "")
        return len(q) >= MIN_QUOTE and q in self.clausulas.get(clausula, "")


def centavos(v: float) -> str:
    return str(int(round(v * 100)))


_MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
          "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
_NUM_EXTENSO = {"dois": 2, "tres": 3, "doze": 12, "dezoito": 18, "vinte e quatro": 24, "trinta e seis": 36}


def verificar(dados: dict, corpus: Corpus) -> dict[str, dict]:
    """Para cada campo canônico (mesma chave da reconciliação): {"quote_ok": bool, "valor_ok": bool}."""
    out: dict[str, dict] = {}

    def marca(chave, quote, valor_ok, clausula=None):
        q_ok = corpus.contem_na_clausula(quote, clausula) if clausula else corpus.contem(quote)
        out[chave] = {"quote_ok": q_ok, "valor_ok": bool(valor_ok) and q_ok}

    c = dados["contrato"]
    nq = {k: normalizar(c[k]) for k in ("quote_id", "quote_partes", "quote_modelo", "quote_vigencia")}
    marca("contrato.id_contrato", c["quote_id"], normalizar(c["id_contrato"]) in nq["quote_id"])
    marca("contrato.operadora", c["quote_partes"], normalizar(c["operadora"])[:20] in nq["quote_partes"])
    marca("contrato.prestador", c["quote_partes"], normalizar(c["prestador"])[:15] in nq["quote_partes"])
    marca("contrato.modelo_remuneracao", c["quote_modelo"],
          normalizar(c["modelo_remuneracao"].replace("_", "-")) in nq["quote_modelo"])
    ano, mes, dia = (int(x) for x in c["vigencia_inicio"].split("-")) if re.match(
        r"^\d{4}-\d{2}-\d{2}$", c["vigencia_inicio"]) else (0, 0, 0)
    qv = nq["quote_vigencia"]
    mes_ok = any(n == mes and nome in qv for nome, n in _MESES.items())
    meses_ok = str(c["vigencia_meses"]) in qv or any(
        n == c["vigencia_meses"] and normalizar(t) in qv for t, n in _NUM_EXTENSO.items())
    marca("contrato.vigencia_inicio", c["quote_vigencia"], str(ano) in qv and mes_ok and str(dia) in qv)
    marca("contrato.vigencia_meses", c["quote_vigencia"], meses_ok)

    for it in dados["anexo_i"]:
        q = normalizar(it["quote"])
        marca(f"anexo_i.{it['codigo']}.valor_teto", it["quote"], it["codigo"] in q and centavos(it["valor_teto"]) in q)

    for p in dados["anexo_ii"]:
        q = normalizar(p["quote"])
        base = p["codigo_procedimento"] in q
        marca(f"anexo_ii.{p['codigo_procedimento']}.taxa_sala_codigo", p["quote"], base and p["taxa_sala_codigo"] in q)
        marca(f"anexo_ii.{p['codigo_procedimento']}.materiais_rotina", p["quote"],
              base and all(m in q for m in p["materiais_rotina"]))

    for t in dados["taxas_condicionadas"]:
        q = normalizar(t["quote"])
        carater_ok = all(("urgencia" in q or "emergencia" in q) if x == "URGENCIA_EMERGENCIA" else "eletiv" in q
                         for x in t["carater_permitido"])
        marca(f"taxa_condicionada.{t['codigo']}.carater_permitido", t["quote"], t["codigo"] in q and carater_ok,
              clausula=t["clausula"])

    for r in dados["regras"]:
        # o enquadramento (tipo/tipo_glosa) é interpretação; aqui se exige que a citação venha DA cláusula citada
        marca(f"regra.{r['clausula']}.tipo", r["quote"], True, clausula=r["clausula"])
        marca(f"regra.{r['clausula']}.tipo_glosa", r["quote"], True, clausula=r["clausula"])
    return out
