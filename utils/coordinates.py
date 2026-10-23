"""Validação/normalização de latitude e longitude (decimal)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

# Compatível com DECIMAL(10,8) típico — margem para sinal/ponto.
COORD_MAX_CHARS = 20


def normalize_coordinate(value: Any) -> Optional[str]:
    """Aceita vírgula PT-BR; retorna string com ponto ou None se vazio/inválido."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = re.sub(r"\s+", "", s).replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return format(d, "f")


def validate_coordinate(
    value: Any,
    *,
    field_label: str = "Latitude/Longitude",
    obrigatorio: bool = False,
) -> Optional[str]:
    """Mensagem de erro ou None se vazio/válido. Vazio só falha se obrigatorio=True."""
    if value is None:
        if obrigatorio:
            return f"{field_label} é obrigatória."
        return None
    s = str(value).strip()
    if not s:
        if obrigatorio:
            return f"{field_label} é obrigatória."
        return None
    if len(s) > COORD_MAX_CHARS:
        return (
            f"O campo «{field_label}» aceita no máximo {COORD_MAX_CHARS} caracteres "
            f"(você informou {len(s)})."
        )
    if normalize_coordinate(value) is None:
        return (
            f"O campo «{field_label}» deve ser um número decimal válido "
            "(use ponto ou vírgula como separador decimal)."
        )
    return None
