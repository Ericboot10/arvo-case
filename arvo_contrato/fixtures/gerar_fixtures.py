"""Gera as fixtures SIMULADAS dos extratores A, B e do juiz (respostas gravadas no formato do schema).

Não são saídas de modelos reais. Elas imitam dois comportamentos para testar o pipeline:
- `replay_fiel.json`: extrator correto, com citações em ordem de leitura e grafia própria (º, espaços, hífen),
  para provar que a verificação normalizada aceita citações legítimas;
- `replay_com_erro.json`: extrator com 5 falhas típicas de LLM, que o pipeline precisa pegar:
    1. valor alucinado com citação verdadeira (31001012: 4300 x "R$ 4.200,00")
    2. citação inventada (regra 4.2)
    3. item omitido (pacote 30715016)
    4. item a mais (cateter 70451938 como material de rotina da herniorrafia)
    5. regra a mais, fora do critério (cláusula 5.1, genérica)
- `replay_juiz.json`: vereditos para os campos divergentes.

Rodar a partir de Arvo_Case:  python -m arvo_contrato.fixtures.gerar_fixtures
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from ..extratores import deterministico
from ..parsing import PdfPlumberParser

AQUI = Path(__file__).resolve().parent
PDF = AQUI.parents[1] / "arvo.case" / "Contrato-parthenon-x-hospital-sao-rafael.pdf"


def brl(v: float) -> str:
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def main() -> None:
    doc = PdfPlumberParser().parse(PDF)
    base = deterministico.extrair(doc)

    fiel = copy.deepcopy(base)
    c = fiel["contrato"]
    c["quote_id"] = "Contrato nº PRT-2025-0417"
    c["quote_modelo"] = "Modalidade fee-for-service"
    c["quote_vigencia"] = "vigorará por 24 (vinte e quatro) meses a contar de 1º de janeiro de 2025"
    c["quote_partes"] = ("De um lado, PARTHENON SAÚDE OPERADORA DE PLANOS DE SAÚDE S.A., inscrita no CNPJ sob o nº "
                         "12.345.678/0001-90, com sede em Curitiba/PR, doravante denominada OPERADORA; e de outro, "
                         "HOSPITAL SÃO RAFAEL LTDA, inscrito")
    for it in fiel["anexo_i"]:
        it["quote"] = f"{it['codigo']} | {it['descricao']} | {it['tipo']} | {brl(it['valor_teto'])}"
    for p in fiel["anexo_ii"]:
        p["quote"] = p["quote"].replace("⋅", " ·")
    for r in fiel["regras"]:
        r["quote"] = r["quote"][: r["quote"].rfind(".") + 1] or r["quote"]
    for t in fiel["taxas_condicionadas"]:
        t["quote"] = t["quote"].split(" é devida")[0] + " é devida exclusivamente em atendimentos cujo caráter registrado seja de urgência ou emergência."

    erro = copy.deepcopy(fiel)
    erro["anexo_i"][0]["valor_teto"] = 4300.00                                   # 1. alucinação de valor
    for r in erro["regras"]:
        if r["clausula"] == "4.2":
            r["quote"] = "É indevida a taxa de urgência em qualquer atendimento eletivo ou ambulatorial."  # 2.
    erro["anexo_ii"] = [p for p in erro["anexo_ii"] if p["codigo_procedimento"] != "30715016"]     # 3.
    for p in erro["anexo_ii"]:
        if p["codigo_procedimento"] == "31309062":
            p["materiais_rotina"] = p["materiais_rotina"] + ["70451938"]                         # 4.
    erro["regras"].append({"clausula": "5.1", "tipo": "PRECO_TETO", "tipo_glosa": "INTEGRAL",       # 5.
                           "quote": "5.1. A OPERADORA poderá auditar, por meios automatizados, as contas apresentadas pelo PRESTADOR"})

    juiz = {"vereditos": [
        {"campo": "anexo_i.31001012.valor_teto", "veredito": "CONFIRMA_D",
         "justificativa": "A tabela do Anexo I fixa R$ 4.200,00 para o código 31001012.",
         "quote": "31001012 Colecistectomia videolaparoscópica Procedimento R$ 4.200,00"},
        {"campo": "anexo_ii.31309062.materiais_rotina", "veredito": "CONFIRMA_D",
         "justificativa": "O Anexo II lista apenas 70520020 e 70402600 como materiais inclusos.",
         "quote": "31309062 Herniorrafia inguinal unilateral 20103050 (porte 2 70520020⋅ 70402600"},
        {"campo": "regra.5.1.tipo", "veredito": "NENHUM_CORRETO",
         "justificativa": "A 5.1 trata do direito de auditar; não é uma regra de glosa específica.",
         "quote": "A OPERADORA poderá auditar, por meios automatizados, as contas apresentadas pelo PRESTADOR"},
    ]}

    for nome, dados in [("replay_fiel", fiel), ("replay_com_erro", erro), ("replay_juiz", juiz)]:
        (AQUI / f"{nome}.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), "utf-8")
        print("gravado", nome)


if __name__ == "__main__":
    main()
