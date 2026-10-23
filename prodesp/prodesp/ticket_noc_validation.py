"""Validação do Ticket NOC (unidades) com base no padrão predominante no banco."""
from __future__ import annotations

import re
from typing import Any, Optional

# 784/798 registros válidos no banco: 7 dígitos numéricos começando em 1.
TICKET_NOC_REGEX = re.compile(r"^1\d{6}$")


def normalizar_ticket_noc(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def ticket_noc_formato_valido(value: Any) -> bool:
    s = normalizar_ticket_noc(value)
    return bool(s and TICKET_NOC_REGEX.match(s))


def validate_ticket_noc_format(value: Any, *, obrigatorio: bool = False) -> Optional[str]:
    """
    Retorna mensagem de erro ou None se OK.
    Valor vazio é permitido quando obrigatorio=False (campo opcional fora de Concluído).
    """
    s = normalizar_ticket_noc(value)
    if not s:
        if obrigatorio:
            return "Para Status e Substatus «Concluído», o campo Ticket NOC é obrigatório."
        return None
    if not TICKET_NOC_REGEX.match(s):
        return (
            "Ticket NOC inválido: informe 7 dígitos numéricos começando em 1 "
            "(ex.: 1680355), sem espaços, traços ou texto."
        )
    return None
