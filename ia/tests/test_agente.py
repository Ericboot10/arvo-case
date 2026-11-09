"""Agente analista (ia/agente): catálogo semântico, política de dados, ferramentas, loop com fallback de modelo,
tradução por provedor e o espaço Genie como código. Sem rede: provedores e Databricks são simulados."""
from __future__ import annotations

import json
import re
from types import SimpleNamespace as NS

import pytest
import yaml

from ia import capacidades, prompts
from ia.adapters.agente_llm import AnthropicAgenteAdapter, ChatToolsAdapter
from ia.adapters.databricks_dados import GenieConsultaAdapter
from ia.agente import benchmark, genie_espaco, semantica
from ia.agente.agente import Agente
from ia.agente.ferramentas import Ferramentas, definicoes
from ia.ports import ChamadaFerramenta, ResultadoConsulta, TurnoAgente
from ia.telemetria import LLMCallRecord

CAT = semantica.carregar_catalogo()


# ============================================================================== catálogo e SQL estruturado
def test_catalogo_le_as_metric_views_publicadas():
    assert {"mv_auditoria_glosa", "mv_funil_economia", "mv_qualidade_auditoria"} <= set(CAT)
    assert {"valor_glosado", "taxa_glosa", "gap_cobrado_vs_pactuado"} <= set(CAT["mv_auditoria_glosa"].medidas)
    assert "clausula_principal" in CAT["mv_auditoria_glosa"].dimensoes
    assert "mv_glosa_ciclo" not in CAT                       # view futura (comentada) não entra


def test_sql_montado_por_codigo_so_aceita_o_catalogo():
    sql = semantica.montar_sql(CAT, "mv_auditoria_glosa", ["valor_glosado"], ["clausula_principal"],
                               [{"dimensao": "regime", "valor": "x' OR '1'='1"}], "valor_glosado", True, 999, "arvo_dev")
    assert "MEASURE(`valor_glosado`)" in sql and "FROM arvo_dev.semantic.mv_auditoria_glosa" in sql
    assert "'x'' OR ''1''=''1'" in sql and sql.endswith("LIMIT 50")      # aspas escapadas, teto de linhas
    for ruim in ([["nao_existe"], []], [["valor_glosado"], ["nao_existe"]]):
        with pytest.raises(semantica.ConsultaInvalida):
            semantica.montar_sql(CAT, "mv_auditoria_glosa", ruim[0], ruim[1], [])
    with pytest.raises(semantica.ConsultaInvalida):
        semantica.montar_sql(CAT, "mv_inventada", ["x"], [], [])


def test_busca_semantica_acha_termo_decisao_e_regra():
    tipos = {(e["tipo"], e["id"]) for e in semantica.buscar("urgência eletivo pronto socorro", limite=10)}
    assert ("decisao", "AMB-01") in tipos
    assert any(e["tipo"] == "regra" and e["id"] == "R1" for e in semantica.buscar("defensável em recurso"))


# ============================================================================== política de dados
def test_reducao_tira_pessoa_conta_data_e_valor_com_formato_de_identificador():
    f = Ferramentas(CAT)
    r = f.reduzir(["paciente", "id_conta", "dt_atendimento", "regra_principal", "valor"],
                  [["B00134", "G00027", "2025-06-14", "R1", "10.0"]] * 80)
    assert r["colunas"] == ["regra_principal", "valor"]
    assert set(r["colunas_removidas_pela_politica"]) == {"paciente", "id_conta", "dt_atendimento"}
    assert len(r["linhas"]) == 50 and r["linhas_omitidas"] == 30 and r["classe_dados"] == "agregado"
    assert f.reduzir(["id_item", "vl"], [["IT00001", 1]])["classe_dados"] == "catalogo"


# ============================================================================== ferramentas
class GenieFalso:
    nome, perimetro = "genie", "plataforma"

    def __init__(self, ok=True):
        self.ok, self.perguntas = ok, []

    def consultar(self, pergunta):
        self.perguntas.append(pergunta)
        if not self.ok:
            return ResultadoConsulta(False, "genie", pergunta, erro="FAILED")
        return ResultadoConsulta(True, "genie", pergunta, sql="SELECT 1", colunas=["clausula_principal", "valor_glosado",
                                 "id_conta"], linhas=[["2.2", "39875.41", "G00027"]], texto="ok")


class ExecutorFalso:
    nome, perimetro = "falso", "plataforma"

    def __init__(self):
        self.sqls = []

    def executar(self, sql):
        self.sqls.append(sql)
        return ["clausula_principal", "valor_glosado"], [["3.3", "55484.17"]]


def test_consultar_dados_so_existe_com_genie_e_falha_aponta_a_alternativa():
    assert "consultar_dados" not in {d["nome"] for d in Ferramentas(CAT).definicoes()}
    f = Ferramentas(CAT, consulta_dados=GenieFalso())
    r = f.executar("consultar_dados", {"pergunta": "glosa por cláusula"})
    assert r["ok"] and r["sql"] == "SELECT 1" and "id_conta" not in r["colunas"]
    r = Ferramentas(CAT, consulta_dados=GenieFalso(ok=False)).executar("consultar_dados", {"pergunta": "x"})
    assert not r["ok"] and "consultar_metrica" in r["proximo_passo"]


def test_consultar_metrica_executa_o_sql_do_catalogo_e_erros_voltam_como_resultado():
    ex = ExecutorFalso()
    f = Ferramentas(CAT, executor_sql=ex)
    args = {"view": "mv_auditoria_glosa", "medidas": ["valor_glosado"], "dimensoes": ["clausula_principal"],
            "filtros": [], "ordenar_por": "valor_glosado", "limite": 10}
    r = f.executar("consultar_metrica", args)
    assert r["ok"] and r["linhas"] == [["3.3", "55484.17"]] and ex.sqls[0] == r["sql"]
    assert not f.executar("consultar_metrica", {**args, "medidas": ["inventada"]})["ok"]
    assert not f.executar("ferramenta_inexistente", {})["ok"]
    assert not f.executar("consultar_metrica", {"view": "mv_auditoria_glosa"})["ok"]        # argumento faltando


def test_explicar_glosa_e_consultar_regra_sem_conta_nem_data():
    f = Ferramentas(CAT)
    r = f.executar("explicar_glosa", {"id_item": "it00001"})
    assert r["glosado"] and r["apontamento"]["regra_principal"] == "R1" and "id_conta" not in r["apontamento"]
    assert "Cláusula 2.2" in r["apontamento"]["justificativa"]
    assert not f.executar("explicar_glosa", {"id_item": "IT1; DROP"})["ok"]
    regra = f.executar("consultar_regra", {"regra": "R1"})
    assert regra["regra"]["defensabilidade"] == "mais_forte" and regra["parametros_do_contrato"]["itens_com_preco_pactuado"]


def test_schemas_das_ferramentas_passam_em_todos_os_provedores_da_cadeia():
    for d in definicoes(CAT, com_genie=True):
        s = d["schema"]
        assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"]), d["nome"]
        assert capacidades.lint(s, ["anthropic", "openai", "databricks_gateway"]) == [], d["nome"]


# ============================================================================== loop do agente
def _rec():
    return LLMCallRecord(task_id="agente_analista")


class ModeloRoteirizado:
    """Devolve turnos prontos, em ordem. Guarda o que recebeu."""
    provedor, familia, modelo = "simulado", "simulado", "roteiro"

    def __init__(self, nome, turnos, perimetro="externo"):
        self.nome, self.turnos, self.perimetro, self.recebido = nome, list(turnos), perimetro, []

    def turno(self, system, conversa, ferramentas, run_id):
        self.recebido.append(json.loads(json.dumps(conversa, default=str)))
        t = self.turnos.pop(0)
        return t if isinstance(t, TurnoAgente) else TurnoAgente(**t, record=_rec())


def test_loop_usa_ferramenta_e_cai_para_o_proximo_modelo_sem_credencial():
    sem_chave = ModeloRoteirizado("claude", [TurnoAgente(False, "", [], _rec(), erro="TypeError: Could not resolve "
                                                                                     "authentication method")] * 3)
    chamada = ChamadaFerramenta("c1", "consultar_dados", {"pergunta": "glosa por cláusula"})
    oss = ModeloRoteirizado("gpt_oss", [{"ok": True, "texto": "", "chamadas": [chamada]},
                                        {"ok": True, "texto": "A cláusula 2.2 somou R$ 39.875,41.", "chamadas": []}],
                            perimetro="plataforma")
    genie = GenieFalso()
    r = Agente([sem_chave, oss], Ferramentas(CAT, consulta_dados=genie)).perguntar("Quanto por cláusula?")
    assert r.ok and "39.875,41" in r.texto and r.modelos == ["gpt_oss", "gpt_oss"]
    assert len(sem_chave.recebido) == 1                       # sem credencial: não tenta de novo na mesma rodada
    assert r.rastro[0]["ferramenta"] == "consultar_dados" and r.rastro[0]["fonte"] == "genie"
    resultado = oss.recebido[1][-1]
    assert resultado["papel"] == "ferramenta" and "G00027" not in resultado["conteudo"]     # conta não chega ao modelo
    assert genie.perguntas == ["glosa por cláusula"]


def test_limite_de_turnos():
    loop = ModeloRoteirizado("m", [{"ok": True, "texto": "", "chamadas": [
        ChamadaFerramenta(f"c{i}", "consultar_semantica", {"termo": "glosa"})]} for i in range(3)])
    r = Agente([loop], Ferramentas(CAT), max_turnos=3).perguntar("?")
    assert not r.ok and r.erro == "limite de turnos" and r.turnos == 3


# ============================================================================== tradução por provedor
CONVERSA = [
    {"papel": "usuario", "texto": "quanto?"},
    {"papel": "assistente", "texto": "vou consultar", "chamadas": [
        {"id": "t1", "nome": "consultar_metrica", "argumentos": {"view": "v"}},
        {"id": "t2", "nome": "consultar_semantica", "argumentos": {"termo": "x"}}],
     "nativo": {"adapter": "claude_opus", "conteudo": [{"type": "thinking", "thinking": "", "signature": "s"},
                                                       {"type": "tool_use", "id": "t1", "name": "consultar_metrica",
                                                        "input": {"view": "v"}}]}},
    {"papel": "ferramenta", "id": "t1", "nome": "consultar_metrica", "conteudo": "{}", "erro": False},
    {"papel": "ferramenta", "id": "t2", "nome": "consultar_semantica", "conteudo": "{}", "erro": True},
]


def test_anthropic_reenvia_o_conteudo_nativo_e_agrupa_os_resultados():
    a = AnthropicAgenteAdapter("claude_opus")
    msgs = a.mensagens(CONVERSA)
    assert msgs[1]["content"] == CONVERSA[1]["nativo"]["conteudo"]           # sem alteração, inclusive o raciocínio
    assert len(msgs) == 3 and [b["tool_use_id"] for b in msgs[2]["content"]] == ["t1", "t2"]
    assert msgs[2]["content"][1]["is_error"] is True
    outro = AnthropicAgenteAdapter("outro_claude").mensagens(CONVERSA)       # nativo de outro adapter não é usado
    assert [b["type"] for b in outro[1]["content"]] == ["text", "tool_use", "tool_use"]


def test_anthropic_requisicao_conforme_o_modelo():
    kw = AnthropicAgenteAdapter("claude_opus").montar_requisicao("sys", CONVERSA[:1], definicoes(CAT, True))
    assert kw["model"] == "claude-opus-5-5" and kw["tool_choice"] == {"type": "auto"}
    assert all(t["strict"] for t in kw["tools"]) and kw["output_config"] == {"effort": "high"}
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert not {"temperature", "top_p", "thinking"} & set(kw)


def test_anthropic_le_ferramentas_e_recusa():
    bloco = NS(type="tool_use", id="t9", name="consultar_semantica", input={"termo": "glosa"},
               to_dict=lambda: {"type": "tool_use"})
    resp = NS(model="claude-opus-5-5", _request_id="r", stop_reason="tool_use", content=[bloco],
              usage=NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0))
    t = AnthropicAgenteAdapter.ler_resposta(resp, _rec(), 0.0)
    assert t.ok and t.chamadas[0].argumentos == {"termo": "glosa"} and t.nativo == [{"type": "tool_use"}]
    recusa = NS(**{**resp.__dict__, "stop_reason": "refusal", "stop_details": NS(category="cyber")})
    assert not AnthropicAgenteAdapter.ler_resposta(recusa, _rec(), 0.0).ok


def test_chat_tools_traduz_chamadas_e_resultados():
    msgs = ChatToolsAdapter.mensagens("sys", CONVERSA)
    assert msgs[0] == {"role": "system", "content": "sys"}
    assert json.loads(msgs[2]["tool_calls"][0]["function"]["arguments"]) == {"view": "v"}
    assert [m["role"] for m in msgs[3:]] == ["tool", "tool"] and msgs[3]["tool_call_id"] == "t1"


# ============================================================================== Genie
def test_genie_le_sql_e_linhas_e_falha_vira_resultado():
    anexo = NS(attachment_id="a1", query=NS(query="SELECT 2", description="d"), text=None)
    msg = NS(status=NS(name="COMPLETED"), conversation_id="c", message_id="m", attachments=[anexo], error=None)
    stmt = NS(manifest=NS(schema=NS(columns=[NS(name="v")])), result=NS(data_array=[["1"]]))
    genie = NS(start_conversation_and_wait=lambda *a, **k: msg,
               get_message_attachment_query_result=lambda *a: NS(statement_response=stmt))
    r = GenieConsultaAdapter("s", client=NS(genie=genie)).consultar("p")
    assert r.ok and r.sql == "SELECT 2" and r.linhas == [["1"]] and r.referencia["conversation_id"] == "c"
    msg.status, msg.attachments = NS(name="FAILED"), []
    assert not GenieConsultaAdapter("s", client=NS(genie=genie)).consultar("p").ok

    def explode(*a, **k):
        raise TimeoutError("demorou")
    assert "TimeoutError" in GenieConsultaAdapter("s", client=NS(genie=NS(start_conversation_and_wait=explode))) \
        .consultar("p").erro


def test_espaco_genie_no_formato_da_api():
    s = genie_espaco.montar("arvo_dev")
    ids = [x["id"] for x in s["config"]["sample_questions"] + s["instructions"]["example_question_sqls"]
           + s["benchmarks"]["questions"] + s["instructions"]["text_instructions"]]
    assert all(re.fullmatch(r"[0-9a-f]{32}", i) for i in ids) and len(set(ids)) == len(ids)
    tabelas = [t["identifier"] for t in s["data_sources"]["tables"]]
    assert tabelas == sorted(tabelas) and all(t.startswith("arvo_dev.") and t.count(".") == 2 for t in tabelas)
    assert len(s["instructions"]["text_instructions"]) == 1                  # a API aceita uma instrução de texto
    bench = yaml.safe_load((benchmark.AQUI / "benchmark.yaml").read_text("utf-8"))["perguntas"]
    assert len(s["benchmarks"]["questions"]) == len(bench)
    assert "<catalogo>" not in json.dumps(s) and genie_espaco.montar("arvo_dev") == s     # determinístico


# ============================================================================== benchmark e governança
@pytest.mark.parametrize("texto,valor", [("R$ 121.948,93", 121948.93), ("94,4%", 0.944), ("0,48%", 0.0048),
                                         ("R$ 1,94 mi", 1.94e6), ("1,234.56", 1234.56), ("R$ 39.875", 39875.0), ("R$ 39 875,41", 39875.41),
                                         ("R$\u00a039\u202f875,41", 39875.41)])
def test_leitura_de_numeros_da_resposta(texto, valor):
    assert benchmark.confere(valor, benchmark.numeros_do_texto(texto))


def test_prompt_do_agente_travado():
    assert prompts.verificar() == []
    assert "agente_analista@1.1.0" in json.loads(prompts.LOCK.read_text("utf-8"))
