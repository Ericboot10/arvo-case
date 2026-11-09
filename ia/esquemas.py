"""Registro de schemas de saída estruturada. Desacopla a camada de IA das tarefas que a usam.

Cada tarefa registra (schema_id, versão) → validador. O adapter valida TODA resposta pelo registro;
sem validador registrado, aplica a validação estrutural genérica do schema enviado.
Restrições finas (formatos, faixas, unicidade) ficam no validador da tarefa, porque o schema enviado ao provedor usa só
o subconjunto comum entre provedores (ver ia/config/capacidades.yaml).
"""
from __future__ import annotations

from typing import Callable

_REGISTRO: dict[tuple[str, str], Callable[[object], list[str]]] = {}


def registrar(schema_id: str, versao: str, validador: Callable[[object], list[str]]) -> None:
    _REGISTRO[(schema_id, versao)] = validador


def registrados() -> list[tuple[str, str]]:
    return sorted(_REGISTRO)


def validar_estrutura(valor, esquema: dict, caminho: str = "$") -> list[str]:
    """Validação estrutural do subconjunto comum: type/properties/required/additionalProperties/items/enum."""
    erros: list[str] = []
    t = esquema.get("type")
    if t == "object":
        if not isinstance(valor, dict):
            return [f"{caminho}: esperado objeto"]
        props = esquema.get("properties", {})
        erros += [f"{caminho}.{k}: ausente" for k in esquema.get("required", []) if k not in valor]
        if esquema.get("additionalProperties") is False:
            erros += [f"{caminho}.{k}: campo não previsto" for k in valor if k not in props]
        for k, sub in props.items():
            if k in valor:
                erros += validar_estrutura(valor[k], sub, f"{caminho}.{k}")
    elif t == "array":
        if not isinstance(valor, list):
            return [f"{caminho}: esperado lista"]
        for i, v in enumerate(valor):
            erros += validar_estrutura(v, esquema.get("items", {}), f"{caminho}[{i}]")
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
    elif t == "boolean":
        if not isinstance(valor, bool):
            erros.append(f"{caminho}: esperado booleano")
    return erros


def validar(schema_id: str, versao: str, schema: dict, dados) -> list[str]:
    v = _REGISTRO.get((schema_id, versao))
    return v(dados) if v else validar_estrutura(dados, schema)
