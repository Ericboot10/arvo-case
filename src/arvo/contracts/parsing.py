"""DocumentParserPort: pdfplumber (aberto, local, determinístico).

Alternativa no Databricks: `ai_parse_document` (ver databricks/f3_ai_parse_document.sql), atrás da mesma interface.

Artefatos REAIS observados neste PDF, que o parser trata e conta:
- rodapé repetido em todas as páginas ("contrato-parthenon-x-hospital-sao-rafael N"), que corta cláusulas ao meio
  (a 2.2 começa na pág. 1 e termina na 2);
- parênteses de fechamento extraídos como caractere nulo (\\x00) em algumas fontes, ex.: "20103077 (porte 4\\x00";
- símbolo "∘" no lugar de "º" ("n ∘", "1∘ de janeiro").
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

from arvo.ai.ports import ParsedDoc

_INICIO_CLAUSULA = re.compile(r"(?m)^(\d{1,2}\.\d{1,2})\.\s+")
_FIM_SECAO = re.compile(r"(?m)^(CLÁUSULA|ANEXO|E por estarem|Curitiba/PR)")


def _linha_base(linha: str) -> str:
    return re.sub(r"\s+\d+\s*$", "", linha.strip())


class PdfPlumberParser:
    nome = "pdfplumber"

    def parse(self, caminho: Path) -> ParsedDoc:
        import pdfplumber  # dependência do adapter, não do core

        caminho = Path(caminho)
        dados = caminho.read_bytes()
        paginas, tabelas = [], []
        with pdfplumber.open(caminho) as pdf:
            for n, pg in enumerate(pdf.pages, start=1):
                paginas.append(pg.extract_text() or "")
                for t in pg.extract_tables():
                    if not t:
                        continue
                    tabelas.append({"pagina": n, "cabecalho": [c or "" for c in t[0]],
                                    "linhas": [[c or "" for c in r] for r in t[1:]]})
            versao = getattr(pdfplumber, "__version__", "?")

        nul = sum(p.count("\x00") for p in paginas) + sum(
            c.count("\x00") for t in tabelas for r in t["linhas"] for c in r)

        # cabeçalhos/rodapés: linhas (sem número de página) repetidas em >= metade das páginas
        cont = Counter()
        for p in paginas:
            cont.update({_linha_base(l) for l in p.splitlines() if l.strip()})
        minimo = max(2, (len(paginas) + 1) // 2)
        repetidas = {l for l, c in cont.items() if c >= minimo}
        removidas = 0
        limpas = []
        for p in paginas:
            linhas = []
            for l in p.splitlines():
                if _linha_base(l) in repetidas:
                    removidas += 1
                    continue
                linhas.append(l)
            limpas.append("\n".join(linhas))
        texto = "\n".join(limpas)

        return ParsedDoc(
            parser=self.nome, parser_versao=versao, sha256=hashlib.sha256(dados).hexdigest(),
            paginas=paginas, texto_limpo=texto, tabelas=tabelas, clausulas=segmentar_clausulas(texto),
            artefatos={"nul_chars": nul, "rodapes_removidos": removidas, "paginas": len(paginas),
                       "tabelas": len(tabelas)},
        )


def segmentar_clausulas(texto: str) -> dict[str, str]:
    """'2.2' -> texto da subcláusula, até a próxima subcláusula ou título de seção."""
    marcas = list(_INICIO_CLAUSULA.finditer(texto))
    out = {}
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        trecho = texto[m.start():fim]
        corte = _FIM_SECAO.search(trecho, pos=len(m.group(0)))
        if corte:
            trecho = trecho[:corte.start()]
        out[m.group(1)] = " ".join(trecho.split())
    return out


def limpar_celula(c: str) -> str:
    return " ".join(c.replace("\x00", "").split())
