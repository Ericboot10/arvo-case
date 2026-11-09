"""F3 · Contrato como dado.

Transforma o PDF do contrato em parâmetros versionados, com citação literal verificada para cada campo,
consenso entre extratores independentes e aprovação humana antes de qualquer uso pelo motor de regras.

Princípio: o core (este pacote) só conhece as interfaces em `ports.py`. Provedores de IA entram como
adapters injetados por configuração (`config/extracao.yaml`); nenhum SDK de provedor é importado fora de `adapters/`.
"""

__version__ = "0.1.0"
