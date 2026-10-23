"""
Helpers de rede reutilizáveis (IPv4 / CIDR).

Sem regras de operadora (VIVO, blocos 201.60, MPLS) — essas ficam nos módulos.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Optional

_IPV4_OCTET = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
_IPV4_RE = re.compile(rf"^{_IPV4_OCTET}(?:\.{_IPV4_OCTET}){{3}}$")
_CIDR_RE = re.compile(
    rf"^{_IPV4_OCTET}(?:\.{_IPV4_OCTET}){{3}}/(?:3[0-2]|[12]?\d)$"
)


def normalize_ip_text(value: Any) -> str:
    """Remove espaços; não altera a semântica do valor."""
    return re.sub(r"\s+", "", str(value or "").strip())


def is_valid_ipv4(value: Any) -> bool:
    s = normalize_ip_text(value)
    return bool(s) and bool(_IPV4_RE.match(s))


def is_valid_ipv4_cidr(value: Any) -> bool:
    """IPv4 com prefixo /0–32 (ex.: 10.0.0.1/24)."""
    s = normalize_ip_text(value)
    return bool(s) and bool(_CIDR_RE.match(s))


def wan_equals_gateway(wan: Any, gateway: Any) -> bool:
    w = normalize_ip_text(wan)
    g = normalize_ip_text(gateway)
    if not w or not g:
        return False
    # Compara host sem sufixo CIDR (10.0.0.1/24 ≡ 10.0.0.1).
    w = w.split("/", 1)[0]
    g = g.split("/", 1)[0]
    return w == g


def validate_wan_gateway_distinct(
    wan: Any,
    gateway: Any,
    *,
    label: str = "Link",
) -> Optional[str]:
    if not wan_equals_gateway(wan, gateway):
        return None
    return (
        f"{label}: IP e Gateway não podem ser iguais. "
        "Corrija os campos de endereço."
    )


def normalize_ipv4_excel_artifact(value: Any) -> Optional[str]:
    """
    Corrige IPv4/máscara quando o Excel gravou 12 dígitos sem pontos
    (ex.: 187115201143 → 187.115.201.143).
    """
    if value is None:
        return None
    if isinstance(value, float) and value == int(value):
        value = int(value)
    if isinstance(value, int):
        s = str(value)
    else:
        s = str(value).strip()
    if not s:
        return None
    dotted = normalize_ip_text(s)
    if is_valid_ipv4(dotted):
        return dotted
    digits = re.sub(r"\D", "", s)
    if len(digits) == 12 and digits.isdigit():
        parts = [int(digits[i : i + 3]) for i in (0, 3, 6, 9)]
        if all(0 <= p <= 255 for p in parts):
            return ".".join(str(p) for p in parts)
    return s


def canonicalize_ipv4(value: Any) -> str:
    """
    Host IPv4 para LAN/loopback: espaços, vírgula decimal, CIDR, zeros à esquerda
    e artefato Excel de 12 dígitos. Devolve o texto canônico ou o original limpo.
    """
    if value is None:
        return ""
    s = re.sub(r"\s+", "", str(value).strip()).replace(",", ".")
    if not s:
        return ""
    if "/" in s:
        s = s.split("/", 1)[0]
    excel = normalize_ipv4_excel_artifact(s)
    if excel and is_valid_ipv4(excel):
        return excel
    parts = s.split(".")
    if len(parts) != 4 or any(p == "" for p in parts):
        return s
    nums: list[int] = []
    for part in parts:
        if not part.isdigit():
            return s
        n = int(part, 10)
        if n > 255:
            return s
        nums.append(n)
    return ".".join(str(n) for n in nums)


def validate_ipv4_field(
    value: Any,
    *,
    label: str = "IP",
    obrigatorio: bool = False,
    allow_cidr: bool = False,
) -> Optional[str]:
    """
    Retorna mensagem de erro ou None.
    allow_cidr=False → só IPv4 puro; True → aceita IPv4 ou IPv4/CIDR.
    """
    s = normalize_ip_text(value)
    if not s:
        if obrigatorio:
            return f"{label} é obrigatório."
        return None
    if allow_cidr:
        if is_valid_ipv4(s) or is_valid_ipv4_cidr(s):
            return None
        return f"{label} inválido. Use IPv4 (ex.: 10.0.0.1) ou CIDR (ex.: 10.0.0.1/24)."
    if is_valid_ipv4(s):
        return None
    if "/" in s:
        return f"{label} deve ser IPv4 sem máscara CIDR (ex.: 10.0.0.1)."
    return f"{label} inválido. Use IPv4 (ex.: 10.0.0.1)."


def validate_netmask_field(
    value: Any,
    *,
    label: str = "Máscara",
    obrigatorio: bool = False,
) -> Optional[str]:
    """Máscara pontilhada IPv4 (ex.: 255.255.255.252). Sem CIDR."""
    err = validate_ipv4_field(value, label=label, obrigatorio=obrigatorio, allow_cidr=False)
    if err:
        return err
    s = canonicalize_ipv4(value)
    if not s:
        return None
    if not is_valid_dotted_netmask(s):
        return (
            f"{label} inválida: não é uma máscara de rede (bits devem ser "
            "contíguos, ex.: 255.255.255.0)."
        )
    return None


def is_valid_dotted_netmask(value: Any) -> bool:
    """True se o valor é máscara IPv4 com bits 1 contíguos à esquerda."""
    s = canonicalize_ipv4(value)
    if not is_valid_ipv4(s):
        return False
    try:
        ipaddress.IPv4Network(f"0.0.0.0/{s}")
        return True
    except ValueError:
        return False


def ipv4_interface(ip: Any, mascara: Any) -> Optional[ipaddress.IPv4Interface]:
    """IP + máscara pontilhada → interface (rede derivada com strict=False)."""
    ip_c = canonicalize_ipv4(ip)
    mask_c = canonicalize_ipv4(mascara)
    if not is_valid_ipv4(ip_c) or not is_valid_ipv4(mask_c):
        return None
    try:
        return ipaddress.IPv4Interface(f"{ip_c}/{mask_c}")
    except ValueError:
        return None


def ipv4_network_address(ip: Any, mascara: Any) -> Optional[str]:
    """Endereço de rede (ex.: 10.1.2.0) a partir de IP + máscara."""
    iface = ipv4_interface(ip, mascara)
    if iface is None:
        return None
    return str(iface.network.network_address)


def canonicalize_network_address(value: Any) -> str:
    """Host ou CIDR → endereço de rede pontilhado; senão IPv4 canônico."""
    s = normalize_ip_text(value).replace(",", ".")
    if not s:
        return ""
    if "/" in s:
        try:
            net = ipaddress.IPv4Network(s, strict=False)
            return str(net.network_address)
        except ValueError:
            return canonicalize_ipv4(s.split("/", 1)[0])
    return canonicalize_ipv4(s)


def validate_ip_mask_group(
    *,
    ip: Any,
    mascara: Any,
    gateway: Any = None,
    subrede: Any = None,
    label: str = "Link",
) -> Optional[str]:
    """
    Calculadora IPv4: IP + máscara definem a rede; gateway e subrede devem
    pertencer a ela. Campos vazios ou inválidos isoladamente não bloqueiam
    (a validação individual trata isso).
    """
    ip_c = canonicalize_ipv4(ip)
    mask_c = canonicalize_ipv4(mascara)
    if not ip_c or not mask_c:
        return None
    if not is_valid_ipv4(ip_c) or not is_valid_ipv4(mask_c):
        return None
    iface = ipv4_interface(ip_c, mask_c)
    if iface is None:
        return (
            f"{label}: máscara inválida (não é uma máscara de rede). "
            "Use, por exemplo, 255.255.255.0."
        )
    net = iface.network
    expected_subnet = str(net.network_address)
    prefix = net.prefixlen
    if prefix < 31:
        if iface.ip == net.network_address:
            return (
                f"{label}: IP {ip_c} é o endereço de rede "
                f"{expected_subnet}/{prefix}. Use um IP de host."
            )
        if iface.ip == net.broadcast_address:
            return (
                f"{label}: IP {ip_c} é o endereço de broadcast. Use um IP de host."
            )

    gw_c = canonicalize_ipv4(gateway) if gateway else ""
    if gw_c and is_valid_ipv4(gw_c):
        gw_addr = ipaddress.IPv4Address(gw_c)
        if gw_addr not in net:
            return (
                f"{label}: Gateway {gw_c} não pertence à rede "
                f"{expected_subnet}/{prefix} (máscara {mask_c})."
            )
        if prefix < 31:
            if gw_addr == net.network_address:
                return (
                    f"{label}: Gateway não pode ser o endereço de rede "
                    f"{expected_subnet}."
                )
            if gw_addr == net.broadcast_address:
                return f"{label}: Gateway não pode ser o endereço de broadcast."

    sub_raw = str(subrede).strip() if subrede is not None else ""
    if sub_raw:
        sub_c = canonicalize_network_address(sub_raw)
        if is_valid_ipv4(sub_c) and sub_c != expected_subnet:
            return (
                f"{label}: subrede {sub_c} não corresponde à rede de "
                f"{ip_c}/{mask_c} (esperado {expected_subnet})."
            )
    return None
