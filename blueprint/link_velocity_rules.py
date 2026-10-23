"""
Velocidade de link PRODESP — persistência sempre em Mbps (somente dígitos).

Entrada típica dos analistas (colagem da planilha):
- Texto: 10G, 10 G, 1 Gbps, 2,5 Gbps, 300 Mbps, 1 Mbps, 8MB
- Legado numérico (Mbps × 1000): 155000 → 155, 300000 → 300, 8000 → 8
- Já normalizado: 8, 300, 1000
"""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

_G_TEXT = re.compile(
    r"^(\d+(?:\.\d+)?)(?:gbps|gbit/s|g)$",
    re.IGNORECASE,
)
_M_TEXT = re.compile(
    r"^(\d+(?:\.\d+)?)(?:mbps|mb/s|mb|m)$",
    re.IGNORECASE,
)


def _compact_velocity_text(raw: str) -> str:
    s = str(raw or "").strip().replace(",", ".")
    return re.sub(r"\s+", "", s)


def _digits_only(value: Any) -> str:
    return re.sub(r"\D", "", str(value or "").strip())


def _parse_gbps_from_compact(compact: str) -> Optional[int]:
    m = _G_TEXT.match(compact)
    if not m:
        return None
    mbps = round(float(m.group(1)) * 1000)
    return mbps if mbps > 0 else None


def _parse_mbps_from_compact(compact: str) -> Optional[int]:
    m = _M_TEXT.match(compact)
    if not m:
        return None
    mbps = round(float(m.group(1)))
    return mbps if mbps > 0 else None


def _normalize_plain_mbps_integer(n: int) -> int:
    """Número puro sem unidade — legado planilha Mbps × 1000."""
    if n <= 0:
        return 0
    if n >= 100_000 and n % 1000 == 0:
        return n // 1000
    if n >= 2_000 and n % 1000 == 0:
        return n // 1000
    return n


def parse_velocity_to_mbps(value: Any) -> Tuple[str, str]:
    """
    Retorna (valor_mbps, origem).
    origem: 'g' | 'm' | 'plain' | ''
    """
    raw = str(value or "").strip()
    if not raw:
        return "", ""

    compact = _compact_velocity_text(raw)

    gbps = _parse_gbps_from_compact(compact)
    if gbps is not None:
        return str(gbps), "g"

    mbps = _parse_mbps_from_compact(compact)
    if mbps is not None:
        return str(mbps), "m"

    nums = _digits_only(raw)
    if not nums:
        return "", ""

    n = int(nums)
    normalized = _normalize_plain_mbps_integer(n)
    if normalized <= 0:
        return "", ""
    return str(normalized), "plain"


def format_velocity_mbps_message(mbps: str) -> str:
    if not mbps:
        return ""
    n = int(mbps)
    if n == 1000:
        return "1 Gbps (1000 Mbps)."
    if n == 2500:
        return "2,5 Gbps (2500 Mbps)."
    if n == 10000:
        return "10 Gbps (10000 Mbps)."
    return f"{n} Mbps."


def normalize_velocity_mbps(value: Any) -> str:
    """Retorna velocidade em Mbps como string de dígitos (vazio se inválido)."""
    mbps, _src = parse_velocity_to_mbps(value)
    return mbps


def normalize_velocity_mbps_with_meta(value: Any) -> Tuple[str, bool, str]:
    """
    Retorna (valor_mbps, foi_ajustado, texto_original).
    """
    raw = str(value or "").strip()
    if not raw:
        return "", False, ""

    mbps, src = parse_velocity_to_mbps(raw)
    if not mbps:
        return "", False, raw

    plain_digits = _digits_only(raw)
    if src in ("g", "m"):
        adjusted = mbps != plain_digits
    elif plain_digits:
        try:
            plain_n = int(plain_digits)
            adjusted = mbps != str(plain_n)
        except ValueError:
            adjusted = False
    else:
        adjusted = False

    return mbps, adjusted, raw
