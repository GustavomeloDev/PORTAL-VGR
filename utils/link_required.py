"""
Campos obrigatórios de link — regras genéricas por modo/operadora.

Módulos adaptam enums (ex. VGR usa tipo_link + modo_conexao).
Visibilidade de grupos (STATIC/MPLS × DHCP × PPPoE) para UI reutilizável.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

WAN_MODOS = ("STATIC", "MPLS", "DHCP", "PPPOE")
WAN_MODOS_COM_IP = frozenset({"STATIC", "MPLS"})
WAN_GRUPO_IP = "ip"
WAN_GRUPO_PPPOE = "pppoe"
WAN_GRUPO_DHCP = "dhcp"
WAN_GRUPO_COMUNS = "comuns"
WAN_GRUPO_ID_VGR = "id_vgr_link"
WAN_GRUPO_VLAN = "vlan_wan"


def normalize_wan_modo(modo: Any) -> str:
    return str(modo or "").strip().upper()


def csv_wan_link_type(modo: Any, vlan_id: Any = None) -> str:
    """Tipo no CSV FortiManager: ``vlan`` se VLAN WAN preenchida; senão o modo em minúsculas."""
    vid = str(vlan_id or "").strip()
    if vid and vid not in ("0",):
        return "vlan"
    m = normalize_wan_modo(modo)
    return m.lower() if m else ""


def wan_grupos_visiveis(
    modo: Any,
    *,
    operadora: Any = None,
    id_vgr_so_vivo: bool = False,
) -> frozenset[str]:
    """
    Grupos de campos visíveis no formulário WAN (Prateleira / Grupo Líder / DMA).

    - STATIC/MPLS: IP, máscara, gateway, VLAN WAN, ID VGR (ou só VIVO se
      ``id_vgr_so_vivo``).
    - PPPOE: usuário/senha.
    - DHCP: aviso (sem IP).
    - comuns: velocidade, operadora, designador (sempre que há modo).
    """
    m = normalize_wan_modo(modo)
    if not m:
        return frozenset({WAN_GRUPO_COMUNS})
    vis: set[str] = {WAN_GRUPO_COMUNS}
    if m in WAN_MODOS_COM_IP:
        vis.add(WAN_GRUPO_IP)
        vis.add(WAN_GRUPO_VLAN)
        op = str(operadora or "").strip().upper()
        if not id_vgr_so_vivo or op == "VIVO":
            vis.add(WAN_GRUPO_ID_VGR)
    elif m == "PPPOE":
        vis.add(WAN_GRUPO_PPPOE)
    elif m == "DHCP":
        vis.add(WAN_GRUPO_DHCP)
    return frozenset(vis)


def wan_campo_visivel(
    modo: Any,
    grupo: str,
    *,
    operadora: Any = None,
    id_vgr_so_vivo: bool = False,
) -> bool:
    return grupo in wan_grupos_visiveis(
        modo, operadora=operadora, id_vgr_so_vivo=id_vgr_so_vivo
    )


def _s(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        if key in payload and payload[key] is not None:
            v = str(payload[key]).strip()
            if v:
                return v
    return ""


def validate_link_required_by_modo(
    payload: Mapping[str, Any],
    *,
    modo_keys: Sequence[str] = ("modo_conexao", "modo"),
    tipo_keys: Sequence[str] = ("tipo_link", "tipo"),
    modos_com_ip: Sequence[str] = ("STATIC", "MPLS"),
    exigir_operadora: bool = False,
    exigir_designador: bool = False,
    exigir_velocidade: bool = False,
    exigir_mascara: bool = False,
    id_vgr_obrigatorio_vivo: bool = True,
    porta_obrigatoria_vivo: bool = True,
) -> Optional[str]:
    """
    Retorna mensagem se faltar campo. Defaults conservadores (não forçam
    designador/velocidade) para não quebrar cadastros parciais.

    - tipos ≠ WAN (LAN, loopbacks…): não exigem modo STATIC/DHCP/PPPOE/MPLS.
    - WAN STATIC/MPLS: IP + Gateway; VIVO → id_vgr_link (+ identificador/porta).
    - WAN PPPOE: credenciais se ``_require_pppoe_creds``.
    """
    tipo = _s(payload, *tipo_keys).upper()
    modo = _s(payload, *modo_keys).upper()
    operadora = _s(payload, "operadora")
    missing: list[str] = []

    if not tipo:
        missing.append("Tipo")
        return (
            "Campos obrigatórios do link não preenchidos: "
            + ", ".join(missing)
            + "."
        )

    # LAN / loopbacks / ranges: sem modo de WAN (grupo_lider / inventário VGR).
    if tipo != "WAN":
        return None

    if exigir_operadora and not operadora:
        missing.append("Operadora")
    if exigir_designador and not _s(payload, "designador"):
        missing.append("Designador")
    if exigir_velocidade and not _s(payload, "velocidade"):
        missing.append("Velocidade")

    if modo in {m.upper() for m in modos_com_ip}:
        if not _s(payload, "ip_address", "ip_wan"):
            missing.append("IP")
        if exigir_mascara and not _s(payload, "mascara", "mask"):
            missing.append("Máscara")
        if not _s(payload, "gateway", "ip_gateway"):
            missing.append("Gateway")
        if id_vgr_obrigatorio_vivo and operadora.upper() == "VIVO":
            if not _s(payload, "id_vgr_link", "id_vgr"):
                missing.append("ID VGR do link (obrigatório para VIVO)")
            if porta_obrigatoria_vivo and not _s(payload, "identificador"):
                missing.append("Identificação da porta (obrigatório para VIVO)")

    if modo == "PPPOE":
        # Segredos podem já existir no banco em update; só exige se flags de set
        # ou campos em claro vierem vazios no create — módulo decide.
        if payload.get("_require_pppoe_creds"):
            if not _s(payload, "pppoe_user") and not payload.get("has_pppoe_user"):
                missing.append("PPPoE User")
            if not _s(payload, "pppoe_pass") and not payload.get("has_pppoe_pass"):
                missing.append("PPPoE Password")

    if missing:
        return (
            "Campos obrigatórios do link não preenchidos: "
            + ", ".join(missing)
            + "."
        )
    return None
