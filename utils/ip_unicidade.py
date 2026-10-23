"""
Unicidade de IPv4 entre links (loopback, VLAN, WAN Vivo).

A consulta ao banco fica no módulo (DMA, VGR…). Aqui: comparação canônica,
mensagens e políticas reutilizáveis.

Não incluir nome de unidade/cliente de outro CNPJ nas mensagens globais
(evita vazamento de cadastro).
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Optional

from core.utils.link_vivo import is_vivo_operadora
from core.utils.network import canonicalize_ipv4

TIPO_LINK_WAN = "WAN"

FindConflictsFn = Callable[..., list[Mapping[str, Any]]]


def ipv4_iguais(a: Any, b: Any) -> bool:
    ca = canonicalize_ipv4(a)
    cb = canonicalize_ipv4(b)
    if not ca or not cb:
        return False
    return ca == cb


def cliente_aplica_unicidade_vlan(
    cnpj: str | None,
    habilitados: Iterable[str] | None,
) -> bool:
    """True só se o CNPJ do cliente estiver na lista opt-in (novos clientes não herdam)."""
    if not habilitados:
        return False
    alvo = str(cnpj or "").strip()
    if not alvo:
        return False
    enabled = {str(item).strip() for item in habilitados if str(item).strip()}
    return alvo in enabled


def aplica_unicidade_ip_wan_vivo(operadora: Any) -> bool:
    """IP de WAN VIVO é único em todos os clientes (mesmo critério do loopback Vivo)."""
    return is_vivo_operadora(operadora)


def issues_unicidade_wan_vivo(
    wans: Iterable[Mapping[str, Any]] | None,
    *,
    finder: FindConflictsFn | None = None,
) -> list[dict[str, str]]:
    """
    Conflitos de IP de WAN Vivo.

    Cada item: ``field``, ``ip``, ``operadora``, ``id_link`` (opcional).
    ``finder(tipo_link, ip, *, id_cliente=None, exclude_id_unidade=None, exclude_id_link=None)``.
    Mensagem global — sem nome de unidade/cliente.
    """
    items: list[dict[str, Any]] = []
    for raw in wans or []:
        field = str(raw.get("field") or "").strip()
        ip = canonicalize_ipv4(raw.get("ip"))
        if not field or not ip:
            continue
        items.append(
            {
                "field": field,
                "ip": ip,
                "operadora": raw.get("operadora"),
                "id_link": raw.get("id_link"),
            }
        )

    issues: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(field: str, ip: str) -> None:
        key = (field, ip)
        if key in seen:
            return
        seen.add(key)
        issues.append(
            {
                "field": field,
                "message": msg_ip_duplicado_global("WAN IP Vivo", ip),
            }
        )

    vivo_items = [
        item for item in items if aplica_unicidade_ip_wan_vivo(item.get("operadora"))
    ]
    for vivo in vivo_items:
        for other in items:
            if other["field"] == vivo["field"]:
                continue
            if ipv4_iguais(vivo["ip"], other["ip"]):
                add(vivo["field"], vivo["ip"])

    if finder is None:
        return issues

    for vivo in vivo_items:
        raw_id = vivo.get("id_link")
        try:
            exclude_link = int(raw_id) if raw_id not in (None, "") else None
        except (TypeError, ValueError):
            exclude_link = None
        hit = primeiro_conflito(
            finder(
                TIPO_LINK_WAN,
                vivo["ip"],
                id_cliente=None,
                exclude_id_unidade=None,
                exclude_id_link=exclude_link,
            ),
            vivo["ip"],
        )
        if hit:
            add(vivo["field"], vivo["ip"])
    return issues


def msg_vlan_ips_iguais_na_unidade(ip: Any) -> str:
    canon = canonicalize_ipv4(ip) or str(ip or "").strip()
    return (
        f"VLAN 1 e VLAN 2 não podem usar o mesmo IP ({canon}) na mesma unidade."
    )


def msg_ip_duplicado_cliente(
    label: str,
    ip: Any,
    nome_unidade: str | None = None,
) -> str:
    canon = canonicalize_ipv4(ip) or str(ip or "").strip()
    extra = ""
    nome = str(nome_unidade or "").strip()
    if nome:
        extra = f" (já usado em {nome})"
    return f"{label} {canon} já está em uso em outra unidade deste cliente{extra}."


def msg_ip_duplicado_global(label: str, ip: Any) -> str:
    """Sem nome de unidade/cliente — unicidade entre todos os cadastros."""
    canon = canonicalize_ipv4(ip) or str(ip or "").strip()
    return f"{label} {canon} já está em uso e não pode se repetir."


def primeiro_conflito(
    rows: Iterable[Mapping[str, Any]] | None,
    ip: Any,
    *,
    ip_key: str = "ip_address",
) -> Optional[Mapping[str, Any]]:
    """Primeira linha cujo IPv4 canônico coincide com ``ip``."""
    canon = canonicalize_ipv4(ip)
    if not canon:
        return None
    for row in rows or []:
        if canonicalize_ipv4(row.get(ip_key)) == canon:
            return row
    return None
