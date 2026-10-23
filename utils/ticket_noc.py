"""Ticket NOC — formato numérico predominante (7 dígitos iniciando em 1)."""

from __future__ import annotations

import re
from typing import Any, Optional

TICKET_NOC_REGEX = re.compile(r"^1\d{6}$")


def normalizar_ticket_noc(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def ticket_noc_formato_valido(value: Any) -> bool:
    s = normalizar_ticket_noc(value)
    return bool(s and TICKET_NOC_REGEX.match(s))


def validate_ticket_noc_format(
    value: Any,
    *,
    obrigatorio: bool = False,
    label: str = "Ticket NOC",
) -> Optional[str]:
    """Mensagem neutra (sem amarrar a status de atendimento)."""
    s = normalizar_ticket_noc(value)
    if not s:
        if obrigatorio:
            return f"{label} é obrigatório."
        return None
    if not TICKET_NOC_REGEX.match(s):
        return (
            f"{label} inválido: informe 7 dígitos numéricos começando em 1 "
            "(ex.: 1680355), sem espaços, traços ou texto."
        )
    return None
