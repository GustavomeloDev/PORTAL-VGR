"""
Operadoras de link — lista principal + OUTROS (texto livre em maiúsculas).

Uso: select com VIVO/CLARO/TIM/OI e campo extra para VTAL, EMBRATEL, etc.
"""

from __future__ import annotations

import re
from typing import Any, Optional

OPERADORAS_PRINCIPAIS = ("VIVO", "CLARO", "TIM", "OI")
OPERADORA_SENTINEL_OUTROS = "OUTROS"
OPERADORA_MAX_LEN = 50

_WS_RE = re.compile(r"\s+")


def normalize_operadora(value: Any, *, max_len: int = OPERADORA_MAX_LEN) -> str:
    """Trim, colapsa espaços e força maiúsculas. Não grava o sentinel OUTROS."""
    s = _WS_RE.sub(" ", str(value if value is not None else "").strip()).upper()
    if not s:
        return ""
    if s == OPERADORA_SENTINEL_OUTROS:
        return ""
    return s[: int(max_len)]


def is_operadora_principal(value: Any) -> bool:
    return normalize_operadora(value) in OPERADORAS_PRINCIPAIS


def resolve_operadora(
    select_value: Any,
    outros_value: Any = None,
    *,
    fallback: Any = None,
) -> Optional[str]:
    """
    Select principal → esse valor.
    Select OUTROS → texto do campo extra.
    Sem select → fallback (campo oculto legado).
    """
    sel = _WS_RE.sub(" ", str(select_value or "").strip()).upper()
    if sel == OPERADORA_SENTINEL_OUTROS:
        return normalize_operadora(outros_value) or None
    if sel in OPERADORAS_PRINCIPAIS:
        return sel
    return normalize_operadora(fallback or outros_value or select_value) or None


def operadora_select_value(stored: Any) -> str:
    """Valor a marcar no <select>: principal, OUTROS ou vazio."""
    s = normalize_operadora(stored)
    if not s:
        return ""
    if s in OPERADORAS_PRINCIPAIS:
        return s
    return OPERADORA_SENTINEL_OUTROS


def operadora_outros_value(stored: Any) -> str:
    """Texto do campo extra; vazio se a gravada for principal."""
    s = normalize_operadora(stored)
    if not s or s in OPERADORAS_PRINCIPAIS:
        return ""
    return s
