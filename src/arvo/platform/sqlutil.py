"""Divide um arquivo SQL em comandos, respeitando blocos $$...$$ (metric views), strings e comentários."""
from __future__ import annotations


def dividir_sql(texto: str) -> list[str]:
    comandos, atual, i, n = [], [], 0, len(texto)
    em_dolar = em_aspas = False
    while i < n:
        c = texto[i]
        if not em_dolar and not em_aspas and texto.startswith("--", i):
            fim = texto.find("\n", i)
            i = n if fim == -1 else fim + 1
            atual.append("\n")
            continue
        if not em_aspas and texto.startswith("$$", i):
            em_dolar = not em_dolar
            atual.append("$$")
            i += 2
            continue
        if not em_dolar and c == "'":
            em_aspas = not em_aspas
        if c == ";" and not em_dolar and not em_aspas:
            cmd = "".join(atual).strip()
            if cmd:
                comandos.append(cmd)
            atual = []
        else:
            atual.append(c)
        i += 1
    cmd = "".join(atual).strip()
    if cmd:
        comandos.append(cmd)
    return comandos
