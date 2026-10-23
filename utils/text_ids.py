"""
Sanitização e validação de identificadores textuais (IDs, designadores, hostnames).

Extraído dos padrões PRODESP (colagem Excel, dígitos mínimos, sem espaços).
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Colagem Excel/Word: ZWSP, BOM, soft-hyphen, NBSP, aspas tipográficas nas bordas.
_PASTE_INVISIBLE_RE = re.compile(
    r"[\u200B-\u200D\uFEFF\u00AD\u2060\u00A0\u202F\u2007]"
)
_EDGE_QUOTES_RE = re.compile(r"^['\"\u2018\u2019\u201c\u201d]+|['\"\u2018\u2019\u201c\u201d]+$")
_WS_RE = re.compile(r"\s+")

# Padrões dominantes no inventário VIVO/PRODESP (configuráveis na chamada).
ID_VGR_LINK_MIN_DIGITS = 7
DESIGNADOR_VIVO_MIN_DIGITS = 15


def sanitize_pasted_text(value: Any) -> str:
    """Remove ruído típico de colagem; não remove hífen/barra de propósito."""
    s = str(value if value is not None else "")
    if not s:
        return ""
    s = _PASTE_INVISIBLE_RE.sub("", s)
    s = _WS_RE.sub("", s)
    for _ in range(3):
        nxt = _EDGE_QUOTES_RE.sub("", s)
        if nxt == s:
            break
        s = nxt
    return s


def has_internal_whitespace(value: Any) -> bool:
    if value is None:
        return False
    s = str(value)
    if not s.strip():
        return False
    return any(ch.isspace() for ch in s)


def validate_no_whitespace(value: Any, label: str = "Campo") -> Optional[str]:
    if has_internal_whitespace(value):
        return (
            f"O campo «{label}» não pode conter espaços. "
            "Remova os espaços e tente novamente."
        )
    return None


def normalizar_hostname(value: Any) -> str:
    return str(value or "").strip().lower()


def validate_hostname(value: Any, *, obrigatorio: bool = False) -> Optional[str]:
    s = str(value or "").strip()
    if not s:
        if obrigatorio:
            return "Hostname é obrigatório."
        return None
    err = validate_no_whitespace(s, "Hostname")
    if err:
        return err
    return None


def is_digits_min_len(value: Any, min_digits: int) -> bool:
    """True se, após sanitize, só dígitos e len >= min_digits."""
    s = sanitize_pasted_text(value)
    if not s:
        return False
    return s.isdigit() and len(s) >= int(min_digits)


def validate_digits_min_len(
    value: Any,
    *,
    label: str,
    min_digits: int,
    obrigatorio: bool = False,
) -> Optional[str]:
    s = sanitize_pasted_text(value)
    if not s:
        if obrigatorio:
            return f"{label} é obrigatório."
        return None
    if not s.isdigit() or len(s) < int(min_digits):
        return (
            f"{label} inválido: informe apenas dígitos com no mínimo "
            f"{min_digits} caracteres (ex.: {'1' * min_digits})."
        )
    return None


def is_id_vgr_link_fora_padrao(
    value: Any, *, min_digits: int = ID_VGR_LINK_MIN_DIGITS
) -> bool:
    """Vazio não conta como fora do padrão."""
    s = sanitize_pasted_text(value)
    if not s:
        return False
    return (not s.isdigit()) or len(s) < int(min_digits)


def is_designador_vivo_fora_padrao(
    value: Any,
    operadora: Any = None,
    *,
    min_digits: int = DESIGNADOR_VIVO_MIN_DIGITS,
) -> bool:
    """Designador rígido só para operadora VIVO; vazio não conta."""
    if str(operadora or "").strip().upper() != "VIVO":
        return False
    s = sanitize_pasted_text(value)
    if not s:
        return False
    return (not s.isdigit()) or len(s) < int(min_digits)


def validate_id_vgr_link_format(
    value: Any, *, min_digits: int = ID_VGR_LINK_MIN_DIGITS
) -> Optional[str]:
    if not sanitize_pasted_text(value):
        return None
    if is_id_vgr_link_fora_padrao(value, min_digits=min_digits):
        return (
            f"ID VGR do link inválido: apenas dígitos e no mínimo {min_digits} "
            f"caracteres (ex.: {'1' * min_digits})."
        )
    return None


def validate_designador_vivo_format(
    value: Any,
    operadora: Any = None,
    *,
    min_digits: int = DESIGNADOR_VIVO_MIN_DIGITS,
) -> Optional[str]:
    if str(operadora or "").strip().upper() != "VIVO":
        return None
    if not sanitize_pasted_text(value):
        return None
    if is_designador_vivo_fora_padrao(value, operadora, min_digits=min_digits):
        return (
            f"Designador VIVO inválido: apenas dígitos e no mínimo {min_digits} "
            "caracteres."
        )
    return None
