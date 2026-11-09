"""Testes da camada semântica (Gate G2).

Rodar a partir da pasta Arvo_Case:
    pip install pyyaml pandas pytest
    pytest tests/semantic -v

Dois tipos de teste:
  1. Integridade interna: referências entre glossário, domínios, conceitos, mapa, vínculos, métricas e perguntas.
  2. Aderência do dado: todo valor que aparece no sinistro está coberto pela semântica
     (código TUSS, descrição, caráter, regime, tipo_item). Valor novo → teste falha → Especialista decide.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest
import yaml

SEM = Path(__file__).resolve().parents[2] / "src" / "arvo" / "semantic"
ROOT = Path(__file__).resolve().parents[2]
SINISTRO = ROOT / "data" / "case" / "sinistro-hospital-saorafael.csv"


def _load(name: str) -> dict:
    with open(SEM / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def glossario():
    return _load("glossario.yaml")


@pytest.fixture(scope="module")
def dominios():
    return _load("dominios.yaml")["dominios"]


@pytest.fixture(scope="module")
def conceitos():
    return _load("conceitos.yaml")


@pytest.fixture(scope="module")
def mapa():
    return _load("map_tuss_conceito.yaml")["codigos"]


@pytest.fixture(scope="module")
def metricas():
    return _load("metricas.yaml")


@pytest.fixture(scope="module")
def perguntas():
    return _load("perguntas_negocio.yaml")["perguntas"]


@pytest.fixture(scope="module")
def vinculo():
    return _load("vinculos/PRT-2025-0417.yaml")


@pytest.fixture(scope="module")
def ambiguidades() -> set[str]:
    txt = (SEM / "decision_log.md").read_text(encoding="utf-8")
    return set(re.findall(r"^## (AMB-\d{2})", txt, flags=re.M))


@pytest.fixture(scope="module")
def sinistro() -> pd.DataFrame:
    return pd.read_csv(SINISTRO, dtype=str, encoding="utf-8-sig")


def _ids_conceito(conceitos) -> set[str]:
    return {c["id"] for c in conceitos["conceitos"]}


def _ids_papel(conceitos) -> set[str]:
    return {p["id"] for p in conceitos["papeis_contratuais"]}


def _pendencias(obj) -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "pendencias":
                out.extend(v)
            else:
                out.extend(_pendencias(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_pendencias(v))
    return out


# ----------------------------------------------------------------- integridade interna
def test_conceitos_ids_unicos_e_hierarquia_valida(conceitos):
    ids = [c["id"] for c in conceitos["conceitos"]]
    assert len(ids) == len(set(ids)), "conceito duplicado"
    for c in conceitos["conceitos"]:
        assert c["pai"] is None or c["pai"] in ids, f"pai inexistente: {c}"
        assert c.get("definicao"), f"conceito sem definição: {c['id']}"


def test_mapa_codigos_unicos_validos_e_conceito_existente(mapa, conceitos):
    ids = _ids_conceito(conceitos)
    cods = [m["codigo"] for m in mapa]
    assert len(cods) == len(set(cods)), "código TUSS duplicado no mapa"
    for m in mapa:
        assert isinstance(m["codigo"], str) and re.fullmatch(r"\d{8}", m["codigo"]), m
        assert m["conceito"] in ids, f"conceito inexistente: {m}"


def test_mapa_tipo_item_origem_no_dominio(mapa, dominios):
    validos = {v["id"] for v in dominios["tipo_item_origem"]["valores_canonicos"]}
    for m in mapa:
        assert m["tipo_item_origem"] in validos, m


def test_dominios_mapeamento_aponta_para_canonico(dominios):
    for nome, d in dominios.items():
        canon = {v["id"] for v in d["valores_canonicos"]}
        for m in d["mapeamento_origem"]:
            assert m["canonico"] in canon, f"{nome}: {m}"
        for k in d.get("sinonimos", {}):
            assert k in canon, f"{nome}: sinônimo para valor inexistente {k}"


def test_glossario_ids_unicos_donos_e_refs(glossario, conceitos, dominios, metricas):
    termos = glossario["termos"]
    ids = [t["id"] for t in termos]
    assert len(ids) == len(set(ids)), "termo duplicado"
    donos = set(glossario["donos_validos"])
    conc, papeis = _ids_conceito(conceitos), _ids_papel(conceitos)
    mets = {m["id"] for m in metricas["metricas"]}
    for t in termos:
        assert t.get("definicao") and t.get("fonte"), f"termo incompleto: {t['id']}"
        assert t["dono"] in donos, f"dono inválido em {t['id']}"
        ref = t.get("ref") or {}
        if "conceito" in ref:
            assert ref["conceito"] in conc, t["id"]
        if "papel_contratual" in ref:
            assert ref["papel_contratual"] in papeis, t["id"]
        if "dominio" in ref:
            assert ref["dominio"] in dominios, t["id"]
            if "valor" in ref:
                assert ref["valor"] in {v["id"] for v in dominios[ref["dominio"]]["valores_canonicos"]}, t["id"]
        if "metrica" in ref:
            assert ref["metrica"] in mets, t["id"]


def test_toda_pendencia_existe_no_decision_log(glossario, dominios, conceitos, mapa, metricas, ambiguidades):
    todas = _pendencias([glossario, dominios, conceitos, mapa, metricas])
    faltando = sorted(set(todas) - ambiguidades)
    assert not faltando, f"pendências sem entrada no decision_log: {faltando}"


def test_metricas_dimensoes_e_tabelas_declaradas(metricas):
    dims = {d["id"] for d in metricas["dimensoes"]}
    tabelas = set(metricas["tabelas_base"]) | {"fato_auditoria_amostral"}
    ids = [m["id"] for m in metricas["metricas"]]
    assert len(ids) == len(set(ids))
    for m in metricas["metricas"]:
        assert m["tabela"] in tabelas, m["id"]
        assert set(m["dimensoes"]) <= dims, f"{m['id']}: dimensão não declarada {set(m['dimensoes']) - dims}"
        assert m["disponibilidade"] in {"hoje", "futura"}


def test_perguntas_de_negocio_respondiveis(perguntas, metricas):
    """Teste de aceite: cada pergunta 'hoje' usa só métricas 'hoje' que aceitam as dimensões pedidas."""
    mets = {m["id"]: m for m in metricas["metricas"]}
    for q in perguntas:
        for mid in q["metricas"]:
            assert mid in mets, f"{q['id']}: métrica inexistente {mid}"
            m = mets[mid]
            if q["disponibilidade"] == "hoje":
                assert m["disponibilidade"] == "hoje", f"{q['id']} depende de métrica futura {mid}"
                ok = set(q["dimensoes"]) <= set(m["dimensoes"])
                assert ok, f"{q['id']}: {mid} não aceita {set(q['dimensoes']) - set(m['dimensoes'])}"


def test_vinculo_contratual_referencia_semantica(vinculo, mapa, conceitos):
    cods = {m["codigo"] for m in mapa}
    conc = _ids_conceito(conceitos)
    for it in vinculo["itens_com_preco_pactuado"]:
        assert it["codigo"] in cods and it["teto"] > 0, it
    pk = vinculo["pacotes"]
    for c in pk["itens_inclusos_comuns"]:
        assert c in cods
    por_cod = {m["codigo"]: m for m in mapa}
    for p in pk["procedimentos"]:
        assert por_cod[p["codigo"]]["conceito"] == "PROCEDIMENTO_CIRURGICO", p
        assert por_cod[p["taxa_sala_inclusa"]]["conceito"] == "TAXA_SALA_CIRURGICA", p
    for c in pk["conceitos_excluidos"]:
        assert c in conc
    for t in vinculo["taxas_condicionadas_ao_carater"]:
        assert por_cod[t["codigo"]]["conceito"] == "TAXA_URGENCIA_EMERGENCIA"


# ----------------------------------------------------------------- aderência do dado
def test_todo_codigo_do_sinistro_esta_mapeado(sinistro, mapa):
    faltando = set(sinistro["cod_tuss"]) - {m["codigo"] for m in mapa}
    assert not faltando, f"códigos sem conceito (→ quarentena + Especialista): {sorted(faltando)}"


def test_toda_descricao_observada_e_conhecida(sinistro, mapa):
    conhecidas = {(m["codigo"], d) for m in mapa for d in m["descricoes_observadas"]}
    obs = set(zip(sinistro["cod_tuss"], sinistro["desc_item"]))
    novas = sorted(obs - conhecidas)
    assert not novas, f"descrições novas para revisar: {novas}"


@pytest.mark.parametrize("dominio", ["carater_atendimento", "regime_atendimento", "tipo_item_origem"])
def test_todo_valor_de_dominio_do_sinistro_esta_mapeado(sinistro, dominios, dominio):
    d = dominios[dominio]
    conhecidos = {m["valor_origem"] for m in d["mapeamento_origem"]}
    faltando = set(sinistro[d["coluna_origem"]]) - conhecidos
    assert not faltando, f"{dominio}: valores sem mapeamento {faltando}"


def test_tipo_item_origem_coerente_com_mapa(sinistro, mapa, dominios):
    """Detecta se a origem mudar a classificação de um código (ex.: diária deixar de vir como 'Taxa')."""
    canon = {m["valor_origem"]: m["canonico"] for m in dominios["tipo_item_origem"]["mapeamento_origem"]}
    esperado = {m["codigo"]: m["tipo_item_origem"] for m in mapa}
    obs = sinistro.groupby("cod_tuss")["tipo_item"].unique()
    for cod, vals in obs.items():
        assert {canon[v] for v in vals} == {esperado[cod]}, (cod, vals)


def test_invariantes_de_grao_da_conta(sinistro):
    """Premissas do glossário T09: 1 beneficiário/data/caráter/regime por conta; id_item único."""
    assert sinistro["id_item"].is_unique
    g = sinistro.groupby("id_conta")
    for col in ["id_beneficiario", "dt_atendimento", "carater_atendimento", "tipo_conta"]:
        assert (g[col].nunique() == 1).all(), f"conta com mais de um {col}"


def test_relatorio_conflitos_semanticos(sinistro):
    """Não falha: registra o tamanho dos conflitos conhecidos (AMB-01) para acompanhar a tendência (métrica M09)."""
    ps_eletivo = ((sinistro["tipo_conta"] == "Pronto Socorro") & (sinistro["carater_atendimento"] == "Eletivo")).sum()
    print(f"\n[M09] itens PS x Eletivo: {ps_eletivo} de {len(sinistro)} ({ps_eletivo / len(sinistro):.1%})")
    assert ps_eletivo >= 0


# ----------------------------------------------------------------- indicadores gold (árvore do norte)
NIVEIS = {"norte", "meta", "fator", "guardrail", "diagnostico", "sanidade", "base"}


def test_niveis_e_arvore_do_indicador_norte(metricas):
    ms = {m["id"]: m for m in metricas["metricas"]}
    assert all(m["nivel"] in NIVEIS for m in ms.values()), [m["id"] for m in ms.values() if m["nivel"] not in NIVEIS]
    assert [i for i, m in ms.items() if m["nivel"] == "norte"] == [metricas["arvore_norte"]["norte"]]
    arv = metricas["arvore_norte"]
    assert ms[arv["meta"]]["nivel"] == "meta"
    assert all(ms[f]["nivel"] == "fator" for f in arv["fatores"])
    assert {i for i, m in ms.items() if m["nivel"] == "fator"} == set(arv["fatores"])
    assert all(ms[g]["nivel"] == "guardrail" for g in arv["guardrails"])
    for i, m in ms.items():
        if m["nivel"] in ("norte", "meta"):
            assert m.get("meta"), f"{i} precisa de meta"
        if m["nivel"] == "guardrail":
            assert m.get("alerta"), f"{i} precisa de alerta"
        if m.get("complemento_de"):
            assert ms[m["complemento_de"]]["nivel"] == "fator", i


def test_versoes_semanticas_alinhadas():
    versoes = {f: _load(f)["versao"] for f in ("glossario.yaml", "dominios.yaml", "conceitos.yaml",
                                               "map_tuss_conceito.yaml", "metricas.yaml", "funil.yaml")}
    assert len(set(versoes.values())) == 1, versoes   # o notebook de carga exige a mesma versão


def test_taxonomia_do_funil():
    import openpyxl

    f = _load("funil.yaml")
    etapas = {e["etapa"]: e for e in f["etapas"]}
    assert len({e["ordem"] for e in f["etapas"]}) == len(etapas)
    prefixo = {"RET": "RETIDA_OPERADORA", "REG": "REGISTRADA_PRESTADOR", "REC": "REVERTIDA"}
    for m in f["motivos"]:
        assert m["etapa"] in etapas and prefixo[m["id_motivo"].split("-")[0]] == m["etapa"], m
    ws = openpyxl.load_workbook(ROOT / "data" / "case" / "Inteligencias_apos_6_meses.xlsx", data_only=True).worksheets[0]
    nomes = {str(r[0]).strip() for r in ws.iter_rows(min_row=5, values_only=True) if r[0]}
    for v in f["regra_inteligencia"]:
        assert v["inteligencia"] in nomes, f"inteligência inexistente na planilha: {v['inteligencia']}"
