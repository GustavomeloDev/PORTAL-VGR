"""
Regras de IP WAN / máscara / gateway para links da operadora VIVO (Blueprint PRODESP).

- MPLS → máscara 255.255.255.248 (/29)
- STATIC (demais tipos): último octeto PAR → /30; ÍMPAR → /31
- Gateway = IP WAN − 1
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any, Mapping, Optional

from prodesp.prodesp.blueprint.link_velocity_rules import normalize_velocity_mbps
from prodesp.prodesp.blueprint.redundante_critico_rules import (
    apply_redundante_critico_to_link,
    is_redundante_critico_active,
)

VIVO_MASK_MPLS = "255.255.255.248"
VIVO_MASK_EVEN = "255.255.255.252"
VIVO_MASK_ODD = "255.255.255.254"


def is_vivo_operadora(operadora: Any) -> bool:
    return (str(operadora or "").strip().upper()) == "VIVO"


def _parse_ipv4_plain(value: Any) -> Optional[ipaddress.IPv4Address]:
    raw = re.sub(r"\s+", "", str(value or "").strip()).split("/")[0]
    if not raw:
        return None
    try:
        return ipaddress.IPv4Address(raw)
    except ValueError:
        return None


def _link_tipo_from_mapping(data: Mapping[str, Any]) -> str:
    return str(data.get("tipo_links") or data.get("tipo") or "").strip().upper()


def is_mpls_link_tipo(link_tipo: Any) -> bool:
    return str(link_tipo or "").strip().upper() == "MPLS"


def derive_vivo_mask_from_wan(ip_wan: Any, link_tipo: Any = None) -> Optional[str]:
    addr = _parse_ipv4_plain(ip_wan)
    if addr is None:
        return None
    if is_mpls_link_tipo(link_tipo):
        return VIVO_MASK_MPLS
    last_octet = int(str(addr).split(".")[-1])
    return VIVO_MASK_EVEN if last_octet % 2 == 0 else VIVO_MASK_ODD


def derive_vivo_gateway_from_wan(ip_wan: Any, redundante_critico: bool = False, link_tipo: Any = None) -> Optional[str]:
    addr = _parse_ipv4_plain(ip_wan)
    if addr is None:
        return None
    as_int = int(addr)
    delta = 3 if (redundante_critico and is_mpls_link_tipo(link_tipo)) else 1
    if as_int < delta:
        return None
    return str(ipaddress.IPv4Address(as_int - delta))


def derive_vivo_wan_from_gateway(ip_gateway: Any, redundante_critico: bool = False) -> Optional[str]:
    addr = _parse_ipv4_plain(ip_gateway)
    if addr is None:
        return None
    delta = 3 if redundante_critico else 1
    new_int = int(addr) + delta
    if new_int > 0xFFFFFFFF:
        return None
    return str(ipaddress.IPv4Address(new_int))


def normalize_link_api_payload(
    payload: Mapping[str, Any],
    existing: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Normaliza payload JSON de link (atendimentos) antes de validar/persistir."""
    data = apply_redundante_critico_to_link(payload, existing)
    normalized = normalize_vivo_link_fields(
        {
            "tipo": data.get("tipo") or data.get("tipo_links"),
            "tipo_links": data.get("tipo") or data.get("tipo_links"),
            "operadora_links": data.get("operadora") or data.get("operadora_links"),
            "ip_wan_links": data.get("ip_wan") or data.get("ip_wan_links"),
            "ip_gateway_links": data.get("ip_gateway") or data.get("ip_gateway_links"),
            "ip_mascara_links": data.get("ip_mascara") or data.get("ip_mascara_links"),
            "redundante_critico_links": data.get("redundante_critico_links"),
            "redundante_critico": data.get("redundante_critico"),
        }
    )
    if normalized.get("ip_mascara_links") is not None:
        data["ip_mascara"] = normalized["ip_mascara_links"]
    if normalized.get("ip_gateway_links") is not None:
        data["ip_gateway"] = normalized["ip_gateway_links"]
    if normalized.get("ip_wan_links") is not None:
        data["ip_wan"] = normalized["ip_wan_links"]
    data["velocidade"] = normalize_velocity_mbps(data.get("velocidade"))
    return data


def normalize_vivo_link_fields(link: Mapping[str, Any]) -> dict[str, Any]:
    """Aplica máscara e gateway VIVO quando operadora é VIVO e IP WAN é válido."""
    data = dict(link)
    operadora = data.get("operadora_links") or data.get("operadora")
    if not is_vivo_operadora(operadora):
        return data
    link_tipo = _link_tipo_from_mapping(data)
    rc = is_redundante_critico_active(data) and is_mpls_link_tipo(link_tipo)
    ip_wan = data.get("ip_wan_links") or data.get("ip_wan")
    ip_gw = data.get("ip_gateway_links") or data.get("ip_gateway")

    # Gateway preenchido sem WAN: deriva WAN (GW+1 / GW+3)
    if not _parse_ipv4_plain(ip_wan) and _parse_ipv4_plain(ip_gw) and is_mpls_link_tipo(link_tipo):
        derived_wan = derive_vivo_wan_from_gateway(ip_gw, rc)
        if derived_wan:
            data["ip_wan_links"] = derived_wan
            ip_wan = derived_wan

    mask = derive_vivo_mask_from_wan(ip_wan, link_tipo)
    if mask:
        data["ip_mascara_links"] = mask

    gateway = derive_vivo_gateway_from_wan(ip_wan, rc, link_tipo)
    if gateway:
        data["ip_gateway_links"] = gateway
    return data
