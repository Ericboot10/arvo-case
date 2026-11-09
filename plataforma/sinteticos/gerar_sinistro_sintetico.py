"""Gerador de sinistro SINTÉTICO e ROTULADO para o ambiente de desenvolvimento (ADR-002 / LGPD).

Por que existe:
1. dev nunca recebe dado real de beneficiário;
2. o gabarito real tem rótulos inconsistentes (AMB-03). Aqui, a verdade é conhecida POR CONSTRUÇÃO:
   cada violação é injetada de propósito e registrada no momento da geração, sem reaplicar as regras do motor,
   o que evitaria a circularidade;
3. ele exercita o que as F5/F6 precisam provar: casos de borda semânticos (AMB-01/02/04/07) e erros de
   qualidade de dado para as expectations (código inválido, enum novo, total inconsistente, id duplicado...).

Formato IDÊNTICO ao arquivo real: mesmas colunas e ordem, decimal com vírgula, data por extenso, UTF-8 com BOM.
IDs com prefixo próprio (P9xx, SX, SG, SB), que nunca colidem com os reais.
Reprodutível: mesma semente gera os mesmos bytes (sha256 no manifesto).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
COLUNAS = ["id_prestador", "id_item", "id_conta", "id_beneficiario", "dt_atendimento", "carater_atendimento",
           "tipo_conta", "cod_tuss", "desc_item", "tipo_item", "qtd", "vl_unitario", "vl_total", "nome_prestador"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]

# Descrição e tipo como chegam da ORIGEM (grafias do arquivo real, não do contrato)
ITENS = {
    "31001012": ("Colecistectomia videolaparoscópica", "Procedimento"),
    "31309062": ("Herniorrafia inguinal unilateral", "Procedimento"),
    "30715016": ("Artroscopia cirúrgica de joelho", "Procedimento"),
    "10101039": ("Consulta médica em consultório", "Procedimento"),
    "20103077": ("Taxa de sala cirúrgica — porte 4", "Taxa"),
    "20103050": ("Taxa de sala cirúrgica — porte 2", "Taxa"),
    "60012010": ("Diária de enfermaria", "Taxa"),
    "99999001": ("Taxa de urgência/emergência", "Taxa"),
    "40304361": ("Hemograma completo", "SADT"),
    "40901416": ("Tomografia computadorizada de crânio", "SADT"),
    "40808157": ("Ultrassonografia de abdome total", "SADT"),
    "70520020": ("Fio de sutura agulhado", "Material"),
    "70402600": ("Compressa cirúrgica estéril", "Material"),
    "70451938": ("Cateter venoso central duplo lúmen", "Material"),
    "90070020": ("Cefazolina 1g — frasco-ampola", "Medicamento"),
    "90050010": ("Dipirona 500mg — ampola", "Medicamento"),
}
SADT = ["40304361", "40901416", "40808157"]
MEDS = ["90070020", "90050010"]

TAXAS_PADRAO = {  # probabilidade de injeção por oportunidade
    "R1_preco_acima_teto": 0.10,
    "R2_sala_em_pacote": 0.30,
    "R3_material_em_pacote": 0.35,
    "R4_urgencia_em_eletivo": 0.25,
    "borda_AMB01_ps_eletivo_com_taxa": 0.15,
    "borda_AMB02_fragmentacao": 0.05,
    "borda_AMB04_sala_sem_pacote": 0.15,
    "dq": 0.004,
}


def _brl(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")  # forma mínima, como no arquivo real: "45", "604,4", "4128,27"


class Gerador:
    def __init__(self, semente: int, n_contas: int, ano: int, mes: int, taxas: dict | None = None):
        self.r = random.Random(semente)
        self.semente, self.n_contas, self.ano, self.mes = semente, n_contas, ano, mes
        self.taxas = {**TAXAS_PADRAO, **(taxas or {})}
        v = yaml.safe_load((RAIZ / "semantic" / "vinculos" / "PRT-2025-0417.yaml").read_text("utf-8"))
        self.teto = {i["codigo"]: float(i["teto"]) for i in v["itens_com_preco_pactuado"]}
        self.pacotes = {p["codigo"]: p["taxa_sala_inclusa"] for p in v["pacotes"]["procedimentos"]}
        self.materiais_rotina = v["pacotes"]["itens_inclusos_comuns"]
        self.linhas, self.rotulos = [], []
        self.n_item = self.n_conta = 0
        self.n_benef = 0

    # ------------------------------------------------------------------ helpers
    def _p(self, chave):
        return self.r.random() < self.taxas[chave]

    def _novo_benef(self):
        self.n_benef += 1
        return f"SB{self.n_benef:05d}"

    def _item(self, conta, cod, qtd=None, rotulo=None, preco_forcado=None):
        self.n_item += 1
        desc, tipo = ITENS[cod]
        qtd = qtd or self.r.choice([1, 1, 1, 2, 2, 3, 4])
        teto = self.teto[cod]
        regra, glosa = rotulo, 0.0
        if preco_forcado is not None:
            vu = preco_forcado
        elif rotulo is None and self._p("R1_preco_acima_teto"):
            vu = round(teto * self.r.uniform(1.06, 1.45), 2)
            regra, glosa = "R1_preco_acima_teto", round((vu - teto) * qtd, 2)
        else:
            vu = round(teto * self.r.uniform(0.97, 1.0), 2)
        vt = round(vu * qtd, 2)
        if rotulo in ("R2_sala_em_pacote", "R3_material_em_pacote", "R4_urgencia_em_eletivo",
                      "borda_AMB01_ps_eletivo_com_taxa"):
            glosa = vt                                      # glosa integral
        lin = {"id_prestador": "P900", "id_item": f"SX{self.n_item:06d}", "id_conta": conta["id"],
               "id_beneficiario": conta["benef"], "dt_atendimento": f"{conta['dia']} de {MESES[self.mes - 1]} de {self.ano}",
               "carater_atendimento": conta["carater"], "tipo_conta": conta["regime"], "cod_tuss": cod,
               "desc_item": desc, "tipo_item": tipo, "qtd": qtd, "vl_unitario": vu, "vl_total": vt,
               "nome_prestador": "Hospital Sintetico 900"}
        self.linhas.append(lin)
        self.rotulos.append({"id_item": lin["id_item"], "id_conta": conta["id"], "cod_tuss": cod,
                             "rotulo": regra or "nenhum", "indevido_por_contrato": regra is not None and not regra.startswith("borda_AMB02")
                             and regra != "borda_AMB04_sala_sem_pacote",
                             "vl_glosa_esperado": glosa})
        return lin

    def _conta(self, regime, carater, benef=None, dia=None):
        self.n_conta += 1
        return {"id": f"SG{self.n_conta:05d}", "benef": benef or self._novo_benef(), "regime": regime,
                "carater": carater, "dia": dia or self.r.randint(1, 28)}

    # ------------------------------------------------------------------ tipos de conta
    def conta_cirurgica(self):
        carater = "Eletivo" if self.r.random() < 0.8 else "Urgência"
        c = self._conta("Internação", carater)
        proc = self.r.choice(list(self.pacotes))
        self._item(c, proc, qtd=1)
        for _ in range(self.r.randint(1, 3)):
            self._item(c, "60012010", qtd=1)
        for cod in self.r.sample(SADT, self.r.randint(0, 2)) + self.r.sample(MEDS, self.r.randint(1, 2)):
            self._item(c, cod)
        if self.r.random() < 0.3:
            self._item(c, "70451938", qtd=1)               # material especial: NÃO integra o pacote (Cl. 3.4)
        if self._p("R2_sala_em_pacote"):
            self._item(c, self.pacotes[proc], qtd=1, rotulo="R2_sala_em_pacote")
        for m in self.materiais_rotina:
            if self._p("R3_material_em_pacote"):
                self._item(c, m, rotulo="R3_material_em_pacote")
        if carater == "Eletivo" and self._p("R4_urgencia_em_eletivo"):
            self._item(c, "99999001", qtd=1, rotulo="R4_urgencia_em_eletivo")
        elif carater == "Urgência" and self.r.random() < 0.5:
            self._item(c, "99999001", qtd=1)               # devida
        if self._p("borda_AMB02_fragmentacao"):           # conta paralela no mesmo dia, com material de rotina
            c2 = self._conta("Internação", "Eletivo", benef=c["benef"], dia=c["dia"])
            self._item(c2, "40304361")
            self._item(c2, self.r.choice(self.materiais_rotina), rotulo="borda_AMB02_fragmentacao")

    def conta_clinica(self):
        c = self._conta("Internação", "Eletivo" if self.r.random() < 0.75 else "Urgência")
        for _ in range(self.r.randint(1, 4)):
            self._item(c, "60012010", qtd=1)
        for cod in self.r.sample(SADT, self.r.randint(1, 3)) + self.r.sample(MEDS, self.r.randint(1, 2)):
            self._item(c, cod)

    def conta_ambulatorial(self):
        c = self._conta("Ambulatorial", "Eletivo" if self.r.random() < 0.7 else "Urgência")
        self._item(c, "10101039", qtd=1)
        for cod in self.r.sample(SADT, self.r.randint(0, 2)) + self.r.sample(MEDS, self.r.randint(0, 1)):
            self._item(c, cod)
        if self._p("borda_AMB04_sala_sem_pacote"):
            self._item(c, self.r.choice(["20103050", "20103077"]), qtd=1, rotulo="borda_AMB04_sala_sem_pacote")

    def conta_ps(self):
        carater = "Urgência" if self.r.random() < 0.35 else "Eletivo"   # no real, PS × Eletivo existe (AMB-01)
        c = self._conta("Pronto Socorro", carater)
        self._item(c, "10101039", qtd=1)
        for cod in self.r.sample(SADT, self.r.randint(1, 2)) + self.r.sample(MEDS, 1):
            self._item(c, cod)
        if carater == "Urgência":
            self._item(c, "99999001", qtd=1)
        elif self._p("borda_AMB01_ps_eletivo_com_taxa"):
            self._item(c, "99999001", qtd=1, rotulo="borda_AMB01_ps_eletivo_com_taxa")

    # ------------------------------------------------------------------ erros de qualidade de dado (F5)
    def injetar_dq(self):
        tipos = ["dq_codigo_invalido", "dq_carater_desconhecido", "dq_total_inconsistente", "dq_id_duplicado",
                 "dq_qtd_zero"]
        # Só itens NEUTROS: sem rótulo e que não sejam procedimento de pacote. Corromper o procedimento de pacote
        # mudaria o rótulo de OUTROS itens da conta (a regra 3.3 é no nível da conta). Achado pelo teste de consistência.
        neutros = [i for i, (l, r) in enumerate(zip(self.linhas, self.rotulos))
                   if r["rotulo"] == "nenhum" and l["cod_tuss"] not in self.pacotes]
        alvos = [i for i in neutros if self._p("dq")]
        for k, idx in enumerate(alvos):
            t = tipos[k % len(tipos)]
            lin, rot = self.linhas[idx], self.rotulos[idx]
            if t == "dq_codigo_invalido":
                lin["cod_tuss"] = "1234"
            elif t == "dq_carater_desconhecido":
                lin["carater_atendimento"] = "Emergência"   # valor novo na origem: deve ir para quarentena (AMB-07)
            elif t == "dq_total_inconsistente":
                lin["vl_total"] = round(lin["vl_total"] + 10, 2)
            elif t == "dq_id_duplicado" and idx > 0:
                lin["id_item"] = self.linhas[idx - 1]["id_item"]
            elif t == "dq_qtd_zero":
                lin["qtd"], lin["vl_total"] = 0, 0.0
            rot["erro_dq"] = t

    def gerar(self) -> None:
        tipos = [self.conta_cirurgica] * 56 + [self.conta_clinica] * 20 + [self.conta_ambulatorial] * 12 + [self.conta_ps] * 12
        for _ in range(self.n_contas):
            self.r.choice(tipos)()
        self.injetar_dq()

    def gravar(self, pasta: Path) -> dict:
        pasta.mkdir(parents=True, exist_ok=True)
        import csv
        import io

        def escrever(nome, linhas, cols, fmt):
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            for l in linhas:
                w.writerow(fmt(l))
            dados = ("﻿" + buf.getvalue()).encode("utf-8")
            (pasta / nome).write_bytes(dados)
            return hashlib.sha256(dados).hexdigest()

        sha_sin = escrever("sinistro_sintetico.csv", self.linhas, COLUNAS,
                           lambda l: {**l, "vl_unitario": _brl(l["vl_unitario"]), "vl_total": _brl(l["vl_total"])})
        sha_gab = escrever("gabarito_sintetico.csv", self.rotulos,
                           ["id_item", "id_conta", "cod_tuss", "rotulo", "indevido_por_contrato", "vl_glosa_esperado",
                            "erro_dq"], lambda l: {**l, "erro_dq": l.get("erro_dq", "")})
        cont = {}
        for r in self.rotulos:
            cont[r["rotulo"]] = cont.get(r["rotulo"], 0) + 1
            if r.get("erro_dq"):
                cont[r["erro_dq"]] = cont.get(r["erro_dq"], 0) + 1
        manifesto = {"semente": self.semente, "n_contas": self.n_conta, "n_itens": len(self.linhas),
                     "competencia": f"{self.ano}-{self.mes:02d}", "taxas_injecao": self.taxas, "contagens": cont,
                     "vl_glosa_esperado_total": round(sum(r["vl_glosa_esperado"] for r in self.rotulos
                                                          if r["indevido_por_contrato"]), 2),
                     "sha256": {"sinistro_sintetico.csv": sha_sin, "gabarito_sintetico.csv": sha_gab},
                     "aviso": "DADOS SINTÉTICOS. Não representam pessoas reais."}
        (pasta / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), "utf-8")
        return manifesto


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--semente", type=int, default=42)
    ap.add_argument("--contas", type=int, default=400)
    ap.add_argument("--ano", type=int, default=2025)
    ap.add_argument("--mes", type=int, default=6)
    ap.add_argument("--saida", type=Path, default=RAIZ / "dados_sinteticos")
    a = ap.parse_args()
    g = Gerador(a.semente, a.contas, a.ano, a.mes)
    g.gerar()
    print(json.dumps(g.gravar(a.saida), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
