"""
Regra «Redundante Crítico» — MPLS + operadora VIVO (PRODESP).

Persistência: apenas `redundante_critico_links` (0/1) + `ip_wan_links` (valor efetivo).
A base da planilha é inferida: flag=0 → base=wan; flag=1 → base=wan−2.
Toggle idempotente via flag + ip gravado, sem coluna duplicada de IP.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any, Mapping, Optional

REDUNDANTE_CRITICO_OFFSET = 2


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


def is_vivo_operadora(operadora: Any) -> bool:
    return (str(operadora or "").strip().upper()) == "VIVO"


def applies_redundante_critico(tipo: Any, operadora: Any) -> bool:
    return is_mpls_link_tipo(tipo) and is_vivo_operadora(operadora)


def _parse_bool_flag(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in ("1", "true", "yes", "on", "sim")


def _first_value(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _sanitize_ipv4(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = _parse_ipv4_plain(raw)
    return str(parsed) if parsed is not None else raw.split("/")[0].strip()


def offset_ipv4(ip_value: Any, delta: int) -> Optional[str]:
    addr = _parse_ipv4_plain(ip_value)
    if addr is None:
        return None
    new_int = int(addr) + int(delta)
    if new_int < 0 or new_int > 0xFFFFFFFF:
        return None
    return str(ipaddress.IPv4Address(new_int))


def derive_base_from_stored(ip_wan: Any, redundante_critico: bool) -> str:
    """Infere IP base (planilha) a partir do valor gravado e da flag."""
    wan = _sanitize_ipv4(ip_wan)
    if not wan:
        return ""
    if redundante_critico:
        return offset_ipv4(wan, -REDUNDANTE_CRITICO_OFFSET) or wan
    return wan


def resolve_effective_ip_wan(
    incoming_wan: Any,
    new_flag: bool,
    existing: Optional[Mapping[str, Any]] = None,
) -> str:
    """Calcula ip_wan_links efetivo a gravar (idempotente no toggle da flag).

    Contrato da UI (atendimento e Blueprint): o campo IP WAN exibe/edita o valor
    efetivo gravado. O ±2 só ocorre no toggle da flag — não na edição do IP com
    RC já marcado.
    """
    inc = _sanitize_ipv4(incoming_wan)

    if existing is None:
        return inc

    old_wan = _sanitize_ipv4(existing.get("ip_wan_links"))
    old_flag = _parse_bool_flag(existing.get("redundante_critico_links"))

    if not old_wan:
        return inc

    # Toggle da flag: deriva a partir do WAN já gravado (±2).
    if new_flag != old_flag:
        if new_flag:
            return offset_ipv4(old_wan, REDUNDANTE_CRITICO_OFFSET) or old_wan
        return offset_ipv4(old_wan, -REDUNDANTE_CRITICO_OFFSET) or old_wan

    if not inc or inc == old_wan:
        return old_wan

    # RC já ativo e WAN alterado: gravar exatamente o valor digitado (efetivo).
    # Exceção: se o analista colar a base da planilha (= WAN atual − 2),
    # converte para o efetivo (+2) uma única vez.
    if new_flag:
        old_base = derive_base_from_stored(old_wan, True)
        if inc == old_base:
            return offset_ipv4(inc, REDUNDANTE_CRITICO_OFFSET) or inc
        return inc

    return inc


def apply_redundante_critico_to_link(
    payload: Mapping[str, Any],
    existing: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Normaliza redundância crítica: só flag + ip_wan efetivo."""
    data = dict(payload)
    tipo = _link_tipo_from_mapping(data)
    operadora = data.get("operadora_links") or data.get("operadora")

    data.pop("ip_wan_base", None)
    data.pop("ip_wan_base_links", None)

    if not applies_redundante_critico(tipo, operadora):
        data.pop("redundante_critico", None)
        return data

    flag_present = "redundante_critico" in data or "redundante_critico_links" in data
    new_flag = _parse_bool_flag(
        _first_value(data, "redundante_critico", "redundante_critico_links")
    )
    if existing and not flag_present:
        new_flag = _parse_bool_flag(existing.get("redundante_critico_links"))

    incoming = _first_value(data, "ip_wan", "ip_wan_links")
    ip_wan = resolve_effective_ip_wan(incoming, new_flag, existing)

    data["redundante_critico_links"] = 1 if new_flag else 0
    # API alias como 0/1 (nunca bool True → "True" com 4 chars na validação de tamanho)
    data["redundante_critico"] = data["redundante_critico_links"]
    if ip_wan:
        data["ip_wan"] = ip_wan
        data["ip_wan_links"] = ip_wan

    # Com Redundante Crítico o par WAN/GW é ±3; o toggle ±2 no WAN já alinha.
    # Gateway definitivo é aplicado em normalize_vivo_link_fields (WAN − delta).
    return data


def is_redundante_critico_active(link: Mapping[str, Any]) -> bool:
    return _parse_bool_flag(
        _first_value(link, "redundante_critico_links", "redundante_critico")
    )
