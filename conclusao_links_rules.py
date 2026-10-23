"""
Cruzamento de links cadastrados × coleta FGT na conclusão (Status+Substatus Concluído).

Fontes (quando presentes em logs_atendimentos):
- get sys interface physical → IP WAN + máscara; gateway inferido em /30–/31 (peer)
- show sys interface → description (circuito / ID VGR / velocidade) + set ip + bandwidth
- get sys arp → gateway quando a sub-rede tem >2 hosts (ex. /29 MPLS)

Sem coleta de interface: não bloqueia (só regras de cadastro).
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any, Mapping, Optional, Sequence

from prodesp.prodesp.blueprint.link_velocity_rules import normalize_velocity_mbps
from prodesp.prodesp.caderno.caderno_carimbo_links import mask_to_prefix
from prodesp.prodesp.caderno.caderno_interface_resolver import (
    extrair_arp_por_interface,
    extrair_ips_interfaces_logs,
    extrair_ips_show_interface_completo,
    resolver_interface_por_ip_link,
)
from prodesp.prodesp.caderno.fgt_ssh_collector import extrair_bloco_coleta_fgt
from prodesp.prodesp.caderno.gerador_caderno_prodesp import _parse_logs_por_comando

_CMD_SHOW = "show sys interface"
_CMD_PHYSICAL = "get sys interface physical"

_RE_EDIT = re.compile(r'^\s*edit\s+"([^"]+)"', re.IGNORECASE)
_RE_SET_IP = re.compile(r"^\s*set\s+ip\s+(\S+)\s+(\S+)", re.IGNORECASE)
_RE_SET_DESC = re.compile(r'^\s*set\s+description\s+"([^"]+)"', re.IGNORECASE)
_RE_SET_ALIAS = re.compile(r'^\s*set\s+alias\s+"([^"]+)"', re.IGNORECASE)
_RE_SET_BW = re.compile(
    r"^\s*set\s+estimated-(?:up|down)stream-bandwidth\s+(\d+)",
    re.IGNORECASE,
)
# SAI-BL_INET1_2187678_100Mb | SCM_MPLS1_1693458_10Mb
_RE_DESC_META = re.compile(
    r"^(?P<circuito>SAI-BLI|SAI-BL|SCM)_(?P<tec>INET2|INET1|MPLS1)_"
    r"(?P<id_vgr>\d+)_(?P<vel>\d+)\s*M?b?$",
    re.IGNORECASE,
)

_TIPOS_CRUZAR = frozenset({"MPLS", "STATIC"})


def _strip_ip(val: Any) -> str:
    return str(val or "").strip().split("/")[0].strip()


def _norm_ip(val: Any) -> str:
    raw = _strip_ip(val)
    if not raw:
        return ""
    try:
        return str(ipaddress.IPv4Address(raw))
    except ValueError:
        return raw


def _norm_mask(val: Any) -> str:
    raw = str(val or "").strip()
    if not raw:
        return ""
    prefix = mask_to_prefix(raw)
    if prefix is None:
        return raw
    try:
        return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)
    except ValueError:
        return raw


def _link_get(link: Mapping[str, Any], *keys: str) -> str:
    for k in keys:
        v = link.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _label_link(link: Mapping[str, Any]) -> str:
    tipo = _link_get(link, "tipo_links", "tipo").upper() or "?"
    des = _link_get(link, "designador_links", "designador")
    return f"Link {tipo}" + (f" — {des}" if des else "")


def parse_description_link_meta(texto: str) -> dict[str, str]:
    """Extrai circuito/tecnologia/id_vgr/velocidade de description/alias FGT."""
    for token in re.split(r"[\s,;]+", str(texto or "").strip()):
        t = token.strip().strip('"')
        if not t:
            continue
        m = _RE_DESC_META.match(t)
        if m:
            return {
                "circuito": m.group("circuito").upper(),
                "tecnologia": m.group("tec").upper(),
                "id_vgr": m.group("id_vgr"),
                "velocidade_mbps": m.group("vel"),
            }
        # fallback: …_2187678_100Mb sem circuito rígido
        m2 = re.search(r"_(\d+)_(\d+)\s*M?b?$", t, re.IGNORECASE)
        if m2:
            return {
                "circuito": "",
                "tecnologia": "",
                "id_vgr": m2.group(1),
                "velocidade_mbps": m2.group(2),
            }
    return {}


def infer_peer_gateway(ip: str, mask_or_prefix: Any) -> str:
    """
    Em /30 e /31 há exatamente 2 hosts: o peer é o gateway típico do link.
    Retorna string vazia se a rede tiver mais hosts.
    """
    ip_n = _norm_ip(ip)
    if not ip_n:
        return ""
    prefix = mask_to_prefix(mask_or_prefix)
    if prefix is None or prefix < 30:
        return ""
    try:
        net = ipaddress.ip_network(f"{ip_n}/{prefix}", strict=False)
        hosts = [str(h) for h in net.hosts()]
        if len(hosts) == 2:
            return hosts[0] if hosts[1] == ip_n else hosts[1] if hosts[0] == ip_n else ""
        # /31 em Python pode listar os 2 endereços da rede
        addrs = [str(a) for a in net]
        if len(addrs) == 2 and ip_n in addrs:
            return addrs[0] if addrs[1] == ip_n else addrs[1]
    except ValueError:
        return ""
    return ""


def _bandwidth_kbps_to_mbps(kbps: Any) -> str:
    try:
        n = int(str(kbps).strip())
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n % 1000 == 0:
        return str(n // 1000)
    # já em Mbps?
    if n < 10000:
        return str(n)
    return str(max(1, round(n / 1000)))


def extrair_detalhes_show_interface(body: str) -> dict[str, dict[str, str]]:
    """
    Por interface: ip, mask, description, alias, velocidade_mbps (bandwidth).
    """
    out: dict[str, dict[str, str]] = {}
    iface: str | None = None
    cur: dict[str, str] = {}

    def _flush():
        nonlocal iface, cur
        if iface and cur:
            out[iface.lower()] = cur
        iface = None
        cur = {}

    for linha in (body or "").splitlines():
        s = linha.strip()
        m_edit = _RE_EDIT.match(s)
        if m_edit:
            _flush()
            iface = m_edit.group(1)
            cur = {}
            continue
        if s.lower() == "next":
            _flush()
            continue
        if not iface:
            continue
        m_ip = _RE_SET_IP.match(s)
        if m_ip and m_ip.group(1) not in ("0.0.0.0", "::"):
            cur["ip"] = m_ip.group(1)
            cur["mask"] = m_ip.group(2)
            continue
        m_d = _RE_SET_DESC.match(s)
        if m_d:
            cur["description"] = m_d.group(1).strip()
            meta = parse_description_link_meta(m_d.group(1))
            if meta.get("id_vgr"):
                cur.setdefault("id_vgr", meta["id_vgr"])
            if meta.get("velocidade_mbps"):
                cur.setdefault("velocidade_mbps", meta["velocidade_mbps"])
            if meta.get("circuito"):
                cur.setdefault("circuito", meta["circuito"])
            continue
        m_a = _RE_SET_ALIAS.match(s)
        if m_a:
            cur["alias"] = m_a.group(1).strip()
            continue
        m_bw = _RE_SET_BW.match(s)
        if m_bw and "velocidade_mbps" not in cur:
            mbps = _bandwidth_kbps_to_mbps(m_bw.group(1))
            if mbps:
                cur["velocidade_mbps"] = mbps
    _flush()
    return out


def _por_cmd_from_logs(logs_atendimentos: Any) -> dict[str, str]:
    raw = str(logs_atendimentos or "")
    bloco = extrair_bloco_coleta_fgt(raw) or raw
    return _parse_logs_por_comando(bloco)


def tem_coleta_interfaces(por_cmd: Mapping[str, str]) -> bool:
    phys = (por_cmd.get(_CMD_PHYSICAL) or "").strip()
    show = (por_cmd.get(_CMD_SHOW) or "").strip()
    return bool(phys or show)


def _cidr_parts(cidr: str) -> tuple[str, str]:
    raw = (cidr or "").strip()
    if "/" in raw:
        ip, pref = raw.split("/", 1)
        mask = _norm_mask(f"/{pref.strip()}")
        return _norm_ip(ip), mask
    return _norm_ip(raw), ""


def _merge_iface_snapshot(por_cmd: dict[str, str]) -> dict[str, dict[str, str]]:
    """Une physical (IP/máscara) + show (description/meta) + ARP peers."""
    snap: dict[str, dict[str, str]] = {}
    ips = extrair_ips_interfaces_logs(por_cmd)
    for iface, cidr in ips.items():
        ip, mask = _cidr_parts(cidr)
        snap[iface.lower()] = {"ip": ip, "mask": mask, "cidr": cidr}

    show_body = (por_cmd.get(_CMD_SHOW) or "").strip()
    if show_body:
        for iface, det in extrair_detalhes_show_interface(show_body).items():
            slot = snap.setdefault(iface, {})
            if det.get("ip"):
                slot.setdefault("ip", _norm_ip(det["ip"]))
            if det.get("mask"):
                slot.setdefault("mask", _norm_mask(det["mask"]))
            for k in ("description", "alias", "id_vgr", "velocidade_mbps", "circuito"):
                if det.get(k):
                    slot[k] = det[k]

    arp = extrair_arp_por_interface(por_cmd)
    for iface, addrs in arp.items():
        slot = snap.setdefault(iface.lower(), {})
        peers = [a for a in addrs if _norm_ip(a) and _norm_ip(a) != slot.get("ip")]
        if peers:
            slot["arp_peers"] = ",".join(peers)

    return snap


def _resolver_iface_para_link(
    link: Mapping[str, Any],
    snap: dict[str, dict[str, str]],
    usados: set[str],
) -> str:
    iface_ips = {
        k: (v.get("cidr") or f"{v.get('ip')}/{mask_to_prefix(v.get('mask')) or 32}")
        for k, v in snap.items()
        if v.get("ip")
    }
    # normaliza cidr inválido
    clean: dict[str, str] = {}
    for k, cidr in iface_ips.items():
        try:
            ipaddress.ip_network(cidr, strict=False)
            clean[k] = cidr
        except ValueError:
            ip = snap[k].get("ip")
            if ip:
                clean[k] = f"{ip}/32"
    found = resolver_interface_por_ip_link(dict(link), clean, excluir=usados)
    if found:
        return found.lower()

    # fallback: description id_vgr
    id_vgr = _link_get(link, "id_vgr_links", "id_vgr")
    if id_vgr:
        for iface, det in snap.items():
            if iface in usados:
                continue
            if det.get("id_vgr") == id_vgr:
                return iface
    return ""


def _gateway_coletado(det: Mapping[str, str]) -> str:
    peer = infer_peer_gateway(det.get("ip") or "", det.get("mask") or "")
    if peer:
        return peer
    peers = [p.strip() for p in (det.get("arp_peers") or "").split(",") if p.strip()]
    if len(peers) == 1:
        return _norm_ip(peers[0])
    return ""


def _tipo_esperado_do_circuito(circuito: str) -> str:
    c = (circuito or "").upper()
    if c in ("SAI-BL", "SAI-BLI"):
        return "STATIC"
    if c == "SCM":
        return "MPLS"
    return ""


def validar_link_contra_coleta(
    link: Mapping[str, Any],
    det: Mapping[str, str],
    *,
    iface: str,
) -> list[str]:
    """Compara um link cadastrado com o snapshot da interface coletada."""
    errors: list[str] = []
    label = _label_link(link)
    where = f"interface «{iface}»"

    wan_cad = _norm_ip(_link_get(link, "ip_wan_links", "ip_wan"))
    wan_log = _norm_ip(det.get("ip"))
    if wan_log and wan_cad and wan_cad != wan_log:
        errors.append(
            f"{label}: IP WAN divergente da coleta ({where}): "
            f"cadastrado «{wan_cad}» × coletado «{wan_log}»."
        )
    elif wan_log and not wan_cad:
        errors.append(
            f"{label}: IP WAN não cadastrado; coleta ({where}) retornou «{wan_log}»."
        )

    mask_cad = _norm_mask(_link_get(link, "ip_mascara_links", "ip_mascara"))
    mask_log = _norm_mask(det.get("mask"))
    if mask_log and mask_cad and mask_cad != mask_log:
        errors.append(
            f"{label}: Máscara divergente da coleta ({where}): "
            f"cadastrado «{mask_cad}» × coletado «{mask_log}»."
        )

    gw_cad = _norm_ip(_link_get(link, "ip_gateway_links", "ip_gateway"))
    gw_log = _gateway_coletado(det)
    if gw_log and gw_cad and gw_cad != gw_log:
        errors.append(
            f"{label}: Gateway divergente da coleta ({where}): "
            f"cadastrado «{gw_cad}» × coletado «{gw_log}» "
            f"(peer /30–/31 ou ARP)."
        )
    elif gw_log and not gw_cad:
        errors.append(
            f"{label}: Gateway não cadastrado; coleta ({where}) indica «{gw_log}»."
        )

    id_cad = _link_get(link, "id_vgr_links", "id_vgr")
    id_log = (det.get("id_vgr") or "").strip()
    if id_log and id_cad and id_cad != id_log:
        errors.append(
            f"{label}: ID VGR do link divergente da description FGT ({where}): "
            f"cadastrado «{id_cad}» × coletado «{id_log}»."
        )

    vel_cad = normalize_velocity_mbps(_link_get(link, "velocidade_links", "velocidade"))
    vel_log = normalize_velocity_mbps(det.get("velocidade_mbps") or "")
    if vel_log and vel_cad and vel_cad != vel_log:
        errors.append(
            f"{label}: Velocidade divergente da coleta ({where}): "
            f"cadastrado «{vel_cad}» Mbps × coletado «{vel_log}» Mbps."
        )

    tipo_cad = _link_get(link, "tipo_links", "tipo").upper()
    tipo_esp = _tipo_esperado_do_circuito(det.get("circuito") or "")
    if tipo_esp and tipo_cad and tipo_cad != tipo_esp:
        errors.append(
            f"{label}: Tipo cadastrado «{tipo_cad}» não confere com description "
            f"«{det.get('description') or det.get('circuito')}» ({where})."
        )

    return errors


def validate_conclusao_links(
    *,
    links: Sequence[Mapping[str, Any]],
    logs_atendimentos: Any = "",
    exigir_cruzamento_log: bool = True,
) -> list[str]:
    """
    Valida MPLS/STATIC contra coleta FGT.
    Sem physical/show nos logs → lista vazia (não bloqueia).
    """
    if not exigir_cruzamento_log:
        return []

    por_cmd = _por_cmd_from_logs(logs_atendimentos)
    if not tem_coleta_interfaces(por_cmd):
        return []

    snap = _merge_iface_snapshot(por_cmd)
    if not snap:
        return []

    errors: list[str] = []
    usados: set[str] = set()
    cruzaveis = [
        lnk
        for lnk in links
        if _link_get(lnk, "tipo_links", "tipo").upper() in _TIPOS_CRUZAR
    ]

    for lnk in cruzaveis:
        iface = _resolver_iface_para_link(lnk, snap, usados)
        if not iface or iface not in snap:
            # Sem interface associada: não bloqueia (evita falso positivo em DHCP/parcial)
            continue
        usados.add(iface)
        errors.extend(validar_link_contra_coleta(lnk, snap[iface], iface=iface))

    return errors
