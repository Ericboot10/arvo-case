"""Ferramentas do agente analista e a política de dados aplicada ao que elas devolvem.

| ferramenta           | fonte                                          | classe do dado devolvido |
|----------------------|------------------------------------------------|--------------------------|
| consultar_dados      | Genie (prioridade), pergunta em linguagem natural | agregado ou catalogo  |
| consultar_metrica    | SQL montado por código sobre as metric views   | agregado                 |
| consultar_semantica  | glossário, conceitos, métricas, decisões AMB   | publico                  |
| consultar_regra      | motor/regras.yaml + contrato transcrito (F2)   | contratual               |
| explicar_glosa       | o apontamento do motor, sem conta nem data     | catalogo                 |

O agente NÃO decide glosa: nenhuma ferramenta escreve. Quem glosa é o motor determinístico (F6).
Todo resultado de dado passa por `reduzir()`: colunas de pessoa, conta e data saem, valores com formato de
identificador derrubam a coluna inteira, e o número de linhas tem teto. Isso vale para qualquer modelo orquestrador.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import yaml

from ..ports import ConsultaDadosPort, ExecutorSQLPort, ResultadoConsulta
from ..roteador import carregar_politica
from . import semantica

RAIZ = Path(__file__).resolve().parents[2]
APONTAMENTOS_LOCAL = RAIZ / "entrega" / "apontamentos.csv"
# Formatos de identificador do case (beneficiário B00134, conta G00027): coluna com esse valor não sai, qualquer nome
PADROES_IDENTIFICADOR = {"beneficiario": re.compile(r"^B\d{5}$"), "conta": re.compile(r"^G\d{5}$"),
                         "pseudonimo": re.compile(r"^[0-9a-f]{16}$")}


def _schema(propriedades: dict) -> dict:
    """Schema aceito por todos os provedores da cadeia: tudo obrigatório, sem campo extra, sem minLength/minimum."""
    return {"type": "object", "properties": propriedades, "required": sorted(propriedades),
            "additionalProperties": False}


def definicoes(catalogo: dict[str, semantica.MetricView], com_genie: bool) -> list[dict]:
    views = sorted(catalogo)
    defs = []
    if com_genie:
        defs.append({"nome": "consultar_dados", "descricao": (
            "Pergunta de DADOS em linguagem natural ao Genie, que conhece a camada semântica publicada no Databricks "
            "(metric views, gold, precisão e recall). É a primeira escolha para qualquer número. Devolve o SQL gerado "
            "e as linhas. Faça perguntas agregadas e específicas (uma métrica por vez, com o recorte desejado)."),
            "schema": _schema({"pergunta": {"type": "string", "description": "Pergunta em português, autocontida."}})})
    defs.append({"nome": "consultar_metrica", "descricao": (
        "Consulta ESTRUTURADA a uma metric view da camada semântica: o SQL é montado por código a partir das medidas "
        "e dimensões do catálogo (lista no system prompt). Use quando o Genie falhar, não estiver disponível, ou para "
        "conferir um número. Filtros são igualdade simples; use lista vazia quando não houver."),
        "schema": _schema({
            "view": {"type": "string", "enum": views},
            "medidas": {"type": "array", "items": {"type": "string"}},
            "dimensoes": {"type": "array", "items": {"type": "string"}},
            "filtros": {"type": "array", "items": _schema({"dimensao": {"type": "string"}, "valor": {"type": "string"}})},
            "ordenar_por": {"type": "string", "description": "Medida ou dimensão pedida; texto vazio para não ordenar."},
            "limite": {"type": "integer", "description": "Máximo de linhas (até 50)."}})})
    defs.append({"nome": "consultar_semantica", "descricao": (
        "Busca no glossário de negócio, na taxonomia de conceitos, nas definições de métricas e nas decisões "
        "registradas (AMB-01 a AMB-21). Use para o SIGNIFICADO de um termo ou o porquê de uma regra."),
        "schema": _schema({"termo": {"type": "string"}})})
    defs.append({"nome": "consultar_regra", "descricao": (
        "Definição de uma regra de glosa (R1, R2, R2B, R3, R4): cláusula, condição, cálculo, defensabilidade em "
        "recurso (mais_forte, forte, ...), revisão humana e os parâmetros do contrato PRT-2025-0417 que ela usa."),
        "schema": _schema({"regra": {"type": "string", "enum": ["R1", "R2", "R2B", "R3", "R4"]}})})
    defs.append({"nome": "explicar_glosa", "descricao": (
        "O apontamento do motor para um item (ex.: IT00001): regra, cláusula, valores e a justificativa pronta para "
        "recurso. Se o item não foi glosado, diz isso."),
        "schema": _schema({"id_item": {"type": "string"}})})
    return defs


class Ferramentas:
    def __init__(self, catalogo: dict[str, semantica.MetricView] | None = None,
                 consulta_dados: ConsultaDadosPort | None = None, executor_sql: ExecutorSQLPort | None = None,
                 catalogo_uc: str | None = "arvo_dev", politica: dict | None = None):
        self.catalogo = catalogo if catalogo is not None else semantica.carregar_catalogo()
        self.consulta_dados, self.executor_sql, self.catalogo_uc = consulta_dados, executor_sql, catalogo_uc
        cfg = (politica or carregar_politica()).get("agente", {})
        self.colunas_removidas = set(cfg.get("colunas_removidas", []))
        self.max_linhas = int(cfg.get("max_linhas_por_resultado", 50))
        self._entradas = None

    def definicoes(self) -> list[dict]:
        return definicoes(self.catalogo, self.consulta_dados is not None)

    # ------------------------------------------------------------------------------------------- política de dados
    def reduzir(self, colunas: list[str], linhas: list[list]) -> dict:
        tiradas = [c for c in colunas if c in self.colunas_removidas or c.lower().startswith("id_benef")]
        for i, c in enumerate(colunas):
            if c in tiradas:
                continue
            valores = [str(r[i]) for r in linhas if i < len(r) and r[i] is not None]
            if any(p.match(v) for v in valores for p in PADROES_IDENTIFICADOR.values()):
                tiradas.append(c)
        manter = [i for i, c in enumerate(colunas) if c not in tiradas]
        linhas_red = [[r[i] for i in manter] for r in linhas[: self.max_linhas]]
        cols = [colunas[i] for i in manter]
        return {"colunas": cols, "linhas": linhas_red, "linhas_omitidas": max(0, len(linhas) - self.max_linhas),
                "colunas_removidas_pela_politica": tiradas,
                "classe_dados": "catalogo" if "id_item" in cols else "agregado"}

    # ------------------------------------------------------------------------------------------------- execução
    def executar(self, nome: str, argumentos: dict) -> dict:
        """Nunca levanta exceção: o erro volta para o modelo como resultado, e ele decide o próximo passo."""
        try:
            metodo = getattr(self, f"_{nome}", None)
            if metodo is None or nome not in {d["nome"] for d in self.definicoes()}:
                return {"ok": False, "erro": f"ferramenta '{nome}' não existe"}
            return metodo(**argumentos)
        except TypeError as e:
            return {"ok": False, "erro": f"argumentos inválidos para {nome}: {e}"}
        except semantica.ConsultaInvalida as e:
            return {"ok": False, "erro": str(e)}
        except Exception as e:
            return {"ok": False, "erro": f"{type(e).__name__}: {e}"}

    def _consultar_dados(self, pergunta: str) -> dict:
        r: ResultadoConsulta = self.consulta_dados.consultar(pergunta)
        base = {"ok": r.ok, "fonte": r.fonte, "sql": r.sql, "resumo_da_fonte": r.texto, "referencia": r.referencia}
        if not r.ok:
            return {**base, "erro": r.erro, "proximo_passo": "use consultar_metrica com o catálogo semântico"}
        return {**base, **self.reduzir(r.colunas, r.linhas)}

    def _consultar_metrica(self, view: str, medidas: list, dimensoes: list, filtros: list, ordenar_por: str,
                           limite: int) -> dict:
        sql = semantica.montar_sql(self.catalogo, view, medidas, dimensoes, filtros, ordenar_por, True, limite,
                                   self.catalogo_uc)
        if self.executor_sql is None:
            return {"ok": False, "sql": sql, "erro": "sem SQL warehouse configurado: a consulta não foi executada"}
        colunas, linhas = self.executor_sql.executar(sql)
        return {"ok": True, "fonte": "camada_semantica", "sql": sql, **self.reduzir(colunas, linhas)}

    def _consultar_semantica(self, termo: str) -> dict:
        if self._entradas is None:
            self._entradas = semantica.entradas_semanticas()
        achados = semantica.buscar(termo, self._entradas)
        return {"ok": True, "fonte": "semantic/", "classe_dados": "publico", "resultados": achados,
                **({} if achados else {"aviso": "nenhum termo encontrado; tente sinônimos"})}

    def _consultar_regra(self, regra: str) -> dict:
        cfg = yaml.safe_load((RAIZ / "motor" / "regras.yaml").read_text("utf-8"))
        r = next((x for x in cfg["regras"] if x["id"] == regra), None)
        if r is None:
            return {"ok": False, "erro": f"regra {regra} não existe"}
        v = yaml.safe_load((RAIZ / "semantic" / "vinculos" / "PRT-2025-0417.yaml").read_text("utf-8"))
        parametros = {
            "R1": {"itens_com_preco_pactuado": v.get("itens_com_preco_pactuado")},
            "R2": {"pacotes": v.get("pacotes", {}).get("procedimentos")},
            "R2B": {"pacotes": v.get("pacotes", {}).get("procedimentos")},
            "R3": {"materiais_rotina_inclusos": v.get("pacotes", {}).get("itens_inclusos_comuns")},
            "R4": {"taxas_condicionadas_ao_carater": v.get("taxas_condicionadas_ao_carater")},
        }.get(regra, {})
        return {"ok": True, "fonte": "motor/regras.yaml + semantic/vinculos/PRT-2025-0417.yaml",
                "classe_dados": "contratual", "versao_regras": cfg.get("versao_regras"),
                "pre_condicao_global": cfg.get("pre_condicao_global"),
                "regra": {k: r[k] for k in ("id", "nome", "clausula", "clausulas_base", "tipo", "tipo_glosa", "prioridade",
                                            "defensabilidade", "condicao", "valor", "referencia", "revisao_humana",
                                            "justificativa") if k in r},
                "parametros_do_contrato": parametros}

    def _explicar_glosa(self, id_item: str) -> dict:
        id_item = id_item.strip().upper()
        if not re.fullmatch(r"IT\d{5}", id_item):
            return {"ok": False, "erro": "id_item no formato ITnnnnn"}
        campos = ["id_item", "regra_principal", "clausula_principal", "clausulas_subsidiarias", "vl_cobrado",
                  "vl_referencia", "vl_glosado", "justificativa", "status_envio", "motivo_revisao", "versao_regra",
                  "versao_contrato"]
        if self.executor_sql is not None:
            cols, linhas = self.executor_sql.executar(
                f"SELECT {', '.join(campos)} FROM {self.catalogo_uc}.gold.fato_apontamento "
                f"WHERE id_item = '{id_item}'")
            fonte = f"{self.catalogo_uc}.gold.fato_apontamento"
            achado = [dict(zip(cols, ln)) for ln in linhas]
        else:
            with APONTAMENTOS_LOCAL.open(encoding="utf-8-sig") as f:
                achado = [{k: ln[k] for k in campos if k in ln} for ln in csv.DictReader(f) if ln["id_item"] == id_item]
            fonte = "entrega/apontamentos.csv"
        if not achado:
            return {"ok": True, "fonte": fonte, "classe_dados": "catalogo", "glosado": False,
                    "mensagem": f"{id_item} não tem apontamento: o motor não glosou este item"}
        return {"ok": True, "fonte": fonte, "classe_dados": "catalogo", "glosado": True, "apontamento": achado[0]}


def serializar(resultado: dict) -> str:
    return json.dumps(resultado, ensure_ascii=False, default=str)
