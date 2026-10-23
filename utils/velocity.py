"""
Velocidade de link — persistência sugerida em Mbps (somente dígitos).

Aceita texto de planilha: 10G, 1 Gbps, 300 Mbps, legado ×1000, etc.
"""

from __future__ import annotations

import re
from typing import Any, Tuple

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


def _parse_gbps_from_compact(compact: str) -> int | None:
    m = _G_TEXT.match(compact)
    if not m:
        return None
    mbps = round(float(m.group(1)) * 1000)
    return mbps if mbps > 0 else None


def _parse_mbps_from_compact(compact: str) -> int | None:
    m = _M_TEXT.match(compact)
    if not m:
        return None
    mbps = round(float(m.group(1)))
    return mbps if mbps > 0 else None


def _normalize_plain_mbps_integer(n: int) -> int:
    if n <= 0:
        return 0
    if n >= 100_000 and n % 1000 == 0:
        return n // 1000
    if n >= 2_000 and n % 1000 == 0:
        return n // 1000
    return n


def parse_velocity_to_mbps(value: Any) -> Tuple[str, str]:
    """Retorna (valor_mbps, origem) com origem em 'g' | 'm' | 'plain' | ''."""
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
    """Mbps como string de dígitos (vazio se inválido/ausente)."""
    mbps, _src = parse_velocity_to_mbps(value)
    return mbps


def validate_velocity_mbps(value: Any, *, label: str = "Velocidade") -> str | None:
    """None se vazio ou válido; mensagem se texto não interpretável."""
    raw = str(value or "").strip()
    if not raw:
        return None
    mbps = normalize_velocity_mbps(raw)
    if not mbps:
        return (
            f"{label} inválida. Use Mbps/Gbps (ex.: 300, 300 Mbps, 1G, 10 Gbps)."
        )
    return None
