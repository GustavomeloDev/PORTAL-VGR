"""
Regras de máscara/gateway para operadora VIVO (reuso Prodesp / DMA / VGR).

- MPLS → 255.255.255.248 (/29), salvo ``mpls_usa_29=False`` (aí vale paridade).
- STATIC e demais: último octeto par → /30 (…252); ímpar → /31 (…254).
- Gateway esperado = IP WAN − 1.

Não inclui offset de redundante crítico (específico Prodesp).
"""

from __future__ import annotations

import ipaddress
from typing import Any, Optional

from core.utils.network import is_valid_ipv4, normalize_ip_text

VIVO_MASK_MPLS = "255.255.255.248"
VIVO_MASK_EVEN = "255.255.255.252"
VIVO_MASK_ODD = "255.255.255.254"


def is_vivo_operadora(operadora: Any) -> bool:
    return str(operadora or "").strip().upper() == "VIVO"


def _parse_ipv4(value: Any) -> Optional[ipaddress.IPv4Address]:
    raw = normalize_ip_text(value).split("/")[0]
    if not raw or not is_valid_ipv4(raw):
        return None
    try:
        return ipaddress.IPv4Address(raw)
    except ValueError:
        return None


def derive_vivo_mask_from_wan(
    ip_wan: Any,
    modo: Any = None,
    *,
    mpls_usa_29: bool = True,
) -> Optional[str]:
    addr = _parse_ipv4(ip_wan)
    if addr is None:
        return None
    modo_u = str(modo or "").strip().upper()
    if mpls_usa_29 and modo_u == "MPLS":
        return VIVO_MASK_MPLS
    last = int(str(addr).split(".")[-1])
    return VIVO_MASK_EVEN if last % 2 == 0 else VIVO_MASK_ODD


def derive_vivo_gateway_from_wan(ip_wan: Any, *, delta: int = 1) -> Optional[str]:
    addr = _parse_ipv4(ip_wan)
    if addr is None:
        return None
    as_int = int(addr)
    if as_int < int(delta):
        return None
    return str(ipaddress.IPv4Address(as_int - int(delta)))


def vivo_mask_message(modo: Any, expected: str) -> str:
    if str(modo or "").strip().upper() == "MPLS" and expected == VIVO_MASK_MPLS:
        return f"VIVO + MPLS: máscara esperada {VIVO_MASK_MPLS} (/29)."
    if expected == VIVO_MASK_EVEN:
        return f"VIVO: último octeto par → máscara {VIVO_MASK_EVEN} (/30)."
    return f"VIVO: último octeto ímpar → máscara {VIVO_MASK_ODD} (/31)."


def collect_vivo_link_pendencias(
    *,
    modo: Any = None,
    operadora: Any = None,
    ip: Any = None,
    mascara: Any = None,
    gateway: Any = None,
    designador: Any = None,
    mpls_usa_29: bool = True,
) -> list[str]:
    """
    Avisos (não bloqueiam). Só se operadora VIVO e IP WAN válido.
    Designador vazio entra como pendência de LP.
    """
    if not is_vivo_operadora(operadora):
        return []
    out: list[str] = []
    expected_mask = derive_vivo_mask_from_wan(ip, modo, mpls_usa_29=mpls_usa_29)
    expected_gw = derive_vivo_gateway_from_wan(ip)
    mask = normalize_ip_text(mascara)
    gw = normalize_ip_text(gateway).split("/")[0]
    if expected_mask:
        if not mask:
            out.append(vivo_mask_message(modo, expected_mask))
        elif mask != expected_mask:
            out.append(
                vivo_mask_message(modo, expected_mask) + f" Valor informado: {mask}."
            )
    if expected_gw:
        if not gw:
            out.append(f"VIVO: gateway esperado {expected_gw} (IP WAN − 1).")
        elif gw != expected_gw:
            out.append(
                f"VIVO: gateway esperado {expected_gw} (IP WAN − 1). "
                f"Valor informado: {gw}."
            )
    des = str(designador or "").strip()
    if not des:
        out.append("Designador (LP) VIVO pendente: 15 dígitos.")
    return out
