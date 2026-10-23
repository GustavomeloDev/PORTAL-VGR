"""
Resolve nome da interface FGT a partir do show sys interface completo (description/alias).
Fallback: IP (physical ou set ip do show) → mapa por modelo (legado).
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Iterable

from prodesp.prodesp.caderno.caderno_carimbo_links import (
    LinksCarimboResolvidos,
    build_description,
    mask_to_prefix,
)
from prodesp.prodesp.caderno.fgt_model_interfaces import (
    interface_wan_backup,
    interface_wan_internet,
    interface_wan_mpls,
)

_PREFIXO_CMD = "show sys interface "
_CMD_SHOW_FULL = "show sys interface"
_CMD_PHYSICAL = "get sys interface physical"
_CMD_ARP = "get sys arp"

_RE_ARP_ENTRY = re.compile(
    r"^(\d{1,3}(?:\.\d{1,3}){3})\s+\d+\s+[0-9a-f:]+\s+(\S+)",
    re.IGNORECASE,
)

_RE_IFACE_PHYSICAL = re.compile(r"==\[([^\]]+)\]", re.IGNORECASE)
_RE_IP_PHYSICAL = re.compile(r"^\s*ip:\s*(\S+)\s+(\S+)", re.IGNORECASE)
_RE_EDIT_IFACE = re.compile(r'^\s*edit\s+"([^"]+)"', re.IGNORECASE)
_RE_SET_IP = re.compile(r"^\s*set\s+ip\s+(\S+)\s+(\S+)", re.IGNORECASE)

_SET_DESCRIPTION = re.compile(r'^\s*set\s+description\s+"([^"]+)"', re.IGNORECASE)
_SET_ALIAS = re.compile(r'^\s*set\s+alias\s+"([^"]+)"', re.IGNORECASE)
_LINE_ALIAS = re.compile(r"^\s*alias:\s*(.+?)\s*$", re.IGNORECASE)
_LINE_DESCRIPTION = re.compile(r"^\s*description:\s*(.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class _SpecInterfaceLink:
    chave: str
    circuito: str
    tecnologia: str
    marcadores: tuple[str, ...]
    fallback_attr: str  # wan_internet | wan_mpls | wan_backup


_SPECS_LINKS: tuple[_SpecInterfaceLink, ...] = (
    _SpecInterfaceLink("sai_bli", "SAI-BLI", "INET2", ("SAI-BLI",), "wan_backup"),
    _SpecInterfaceLink("scm", "SCM", "MPLS1", ("SCM", "MPLS1"), "wan_mpls"),
    _SpecInterfaceLink("sai_bl", "SAI-BL", "INET1", ("SAI-BL", "INET1"), "wan_internet"),
)


def _limpar_texto(valor: str) -> str:
    return (valor or "").strip().strip('"').strip()


def _extrair_textos_interface(body: str) -> str:
    """Junta description + alias do bloco show sys interface (FortiOS)."""
    partes: list[str] = []
    vistos: set[str] = set()
    for linha in (body or "").splitlines():
        s = linha.strip()
        for pat in (_SET_DESCRIPTION, _SET_ALIAS, _LINE_DESCRIPTION, _LINE_ALIAS):
            m = pat.match(s)
            if m:
                txt = _limpar_texto(m.group(1))
                if txt and txt.upper() not in vistos:
                    vistos.add(txt.upper())
                    partes.append(txt)
                break
    return " ".join(partes)


def _iter_blocos_show_sys_interface(body: str):
    """Percorre blocos edit \"iface\" … next do show sys interface completo."""
    iface_atual: str | None = None
    linhas_atual: list[str] = []

    def _flush():
        nonlocal iface_atual, linhas_atual
        if iface_atual and linhas_atual:
            yield iface_atual, linhas_atual
        iface_atual = None
        linhas_atual = []

    for linha in (body or "").splitlines():
        stripped = linha.strip()
        m_edit = _RE_EDIT_IFACE.match(stripped)
        if m_edit:
            yield from _flush()
            iface_atual = m_edit.group(1)
            linhas_atual = [linha]
            continue
        if iface_atual is None:
            continue
        linhas_atual.append(linha)
        if stripped == "next":
            yield from _flush()
    if iface_atual and linhas_atual:
        yield iface_atual, linhas_atual


def parse_show_sys_interface_completo(body: str) -> dict[str, str]:
    """Mapa interface (minúscula) → description + alias a partir do show completo."""
    out: dict[str, str] = {}
    for iface, linhas in _iter_blocos_show_sys_interface(body):
        texto = _extrair_textos_interface("\n".join(linhas))
        if texto:
            out[iface.lower()] = texto
    return out


def extrair_blocos_show_interface_texto(body: str, ifaces: Iterable[str]) -> dict[str, str]:
    """Extrai blocos edit por interface para colar no carimbo."""
    desejadas = {i.lower() for i in ifaces if (i or "").strip()}
    if not desejadas:
        return {}
    out: dict[str, str] = {}
    for iface, linhas in _iter_blocos_show_sys_interface(body):
        if iface.lower() in desejadas:
            out[iface.lower()] = "\n".join(linhas).strip()
    return out


def extrair_ips_show_interface_completo(body: str) -> dict[str, str]:
    """Mapa interface → IP/CIDR a partir de set ip nos blocos do show completo."""
    out: dict[str, str] = {}
    for iface, linhas in _iter_blocos_show_sys_interface(body):
        for linha in linhas:
            m_ip = _RE_SET_IP.match(linha.strip())
            if not m_ip:
                continue
            ip, mask = m_ip.group(1), m_ip.group(2)
            if ip in ("0.0.0.0", "::"):
                continue
            prefix = mask_to_prefix(mask)
            if prefix is not None:
                out[iface.lower()] = f"{ip}/{prefix}"
            break
    return out


def extrair_aliases_show_interface(por_cmd: dict[str, str]) -> dict[str, str]:
    """Mapa interface (minúscula) → textos alias/description do FortiGate."""
    out: dict[str, str] = {}
    body_full = (por_cmd.get(_CMD_SHOW_FULL) or "").strip()
    if body_full:
        out.update(parse_show_sys_interface_completo(body_full))

    for cmd, body in por_cmd.items():
        if cmd == _CMD_SHOW_FULL or not cmd.startswith(_PREFIXO_CMD):
            continue
        iface = cmd[len(_PREFIXO_CMD) :].strip()
        if not iface or iface.lower() in out:
            continue
        texto = _extrair_textos_interface(body)
        if texto:
            out[iface.lower()] = texto
    return out


def extrair_ips_interfaces_logs(por_cmd: dict[str, str] | None) -> dict[str, str]:
    """Combina get sys interface physical com set ip do show sys interface completo."""
    cmds = por_cmd or {}
    ips = extrair_ips_interface_physical(cmds)
    body_full = (cmds.get(_CMD_SHOW_FULL) or "").strip()
    if body_full:
        for iface, cidr in extrair_ips_show_interface_completo(body_full).items():
            ips.setdefault(iface, cidr)
    return ips


def extrair_arp_por_interface(por_cmd: dict[str, str] | None) -> dict[str, list[str]]:
    """Mapa interface → endereços ARP vistos em get sys arp."""
    body = (por_cmd or {}).get(_CMD_ARP, "")
    if not body:
        return {}
    out: dict[str, list[str]] = {}
    for linha in body.splitlines():
        m = _RE_ARP_ENTRY.match(linha.strip())
        if not m:
            continue
        addr, iface = m.group(1), m.group(2).strip().lower()
        out.setdefault(iface, []).append(addr)
    return out


def montar_show_interface_parts_para_carimbo(
    por_cmd: dict[str, str],
    ifaces_resolvidas: Iterable[str],
) -> list[str]:
    """Monta trechos de show sys interface para a coluna E do carimbo."""
    ifaces = [i for i in ifaces_resolvidas if (i or "").strip()]
    if not ifaces:
        return []

    body_full = (por_cmd.get(_CMD_SHOW_FULL) or "").strip()
    if body_full:
        blocos = extrair_blocos_show_interface_texto(body_full, ifaces)
        parts: list[str] = []
        for iface in ifaces:
            blk = blocos.get(iface.lower())
            if blk:
                parts.append(f"=== show sys interface {iface} ===\n{blk}")
        if parts:
            return parts

    ifaces_set = {i.lower() for i in ifaces}
    legacy = [
        f"=== {cmd} ===\n{body}"
        for cmd, body in por_cmd.items()
        if cmd.startswith(_PREFIXO_CMD) and body and cmd.rsplit(" ", 1)[-1].lower() in ifaces_set
    ]
    legacy.sort(
        key=lambda p: next(
            (i for i, iface in enumerate(ifaces) if p.lower().startswith(f"=== show sys interface {iface.lower()}")),
            99,
        )
    )
    return legacy


def extrair_ips_interface_physical(por_cmd: dict[str, str]) -> dict[str, str]:
    """Mapa interface → IP/CIDR a partir de get sys interface physical."""
    body = por_cmd.get(_CMD_PHYSICAL, "")
    if not body:
        return {}
    out: dict[str, str] = {}
    iface_atual: str | None = None
    for linha in body.splitlines():
        m_if = _RE_IFACE_PHYSICAL.search(linha)
        if m_if:
            iface_atual = m_if.group(1).strip().lower()
            continue
        if not iface_atual:
            continue
        m_ip = _RE_IP_PHYSICAL.match(linha)
        if not m_ip:
            continue
        ip, mask = m_ip.group(1), m_ip.group(2)
        if ip in ("0.0.0.0", "::"):
            continue
        prefix = mask_to_prefix(mask)
        if prefix is not None:
            out[iface_atual] = f"{ip}/{prefix}"
    return out


def resolver_interface_por_ip_link(
    link: dict[str, Any],
    iface_ips: dict[str, str],
    *,
    excluir: set[str] | None = None,
) -> str:
    """Associa link ao interface cuja rede contém o IP WAN cadastrado."""
    bloqueadas = {x.lower() for x in (excluir or set())}
    ip_raw = (link.get("ip_wan_links") or link.get("ip_wan") or "").strip().split("/")[0].strip()
    if not ip_raw:
        return ""
    prefix = mask_to_prefix(link.get("ip_mascara_links") or link.get("ip_mascara") or "")
    try:
        if prefix is not None:
            alvo = ipaddress.ip_address(ip_raw)
            rede_link = ipaddress.ip_network(f"{ip_raw}/{prefix}", strict=False)
            for iface, cidr in iface_ips.items():
                if iface.lower() in bloqueadas:
                    continue
                try:
                    rede_if = ipaddress.ip_network(cidr, strict=False)
                except ValueError:
                    continue
                if alvo in rede_if or rede_link.subnet_of(rede_if) or rede_if.subnet_of(rede_link):
                    return iface
        else:
            alvo = ipaddress.ip_address(ip_raw)
            for iface, cidr in iface_ips.items():
                if iface.lower() in bloqueadas:
                    continue
                try:
                    rede_if = ipaddress.ip_network(cidr, strict=False)
                except ValueError:
                    continue
                if alvo in rede_if:
                    return iface
    except ValueError:
        return ""
    return ""


def _marcador_casa_alias(marcador: str, alias: str) -> bool:
    """Evita SAI-BL casar com alias SAI-BLI."""
    mk = (marcador or "").strip().upper()
    al = (alias or "").upper()
    if not mk or not al:
        return False
    if mk == "SAI-BL":
        return bool(re.search(r"SAI-BL(?!I)", al))
    if mk == "SAI-BLI":
        return "SAI-BLI" in al
    if mk in ("INET1", "INET2"):
        return (
            al == mk
            or f"_{mk}_" in al
            or al.startswith(f"{mk}_")
            or al.endswith(f"_{mk}")
            or f"{mk}_" in al
        )
    return mk in al


def resolver_interface_por_alias(
    aliases: dict[str, str],
    *,
    marcadores: Iterable[str] = (),
    descricao: str = "",
    fallback: str = "",
    excluir: set[str] | None = None,
) -> str:
    bloqueadas = {x.lower() for x in (excluir or set())}
    desc_u = (descricao or "").strip().upper()

    def _candidato(iface: str) -> bool:
        return iface.lower() not in bloqueadas

    for marcador in marcadores:
        for iface, alias in aliases.items():
            if not _candidato(iface):
                continue
            if _marcador_casa_alias(marcador, alias):
                return iface

    if desc_u:
        for iface, alias in aliases.items():
            if not _candidato(iface):
                continue
            alias_u = alias.upper()
            if desc_u == alias_u or desc_u in alias_u or alias_u in desc_u:
                return iface

    fb = (fallback or "").strip()
    if fb and _candidato(fb):
        return fb
    return ""


def _fallback_interface(modelo: str, attr: str) -> str:
    if attr == "wan_internet":
        return interface_wan_internet(modelo)
    if attr == "wan_mpls":
        return interface_wan_mpls(modelo)
    if attr == "wan_backup":
        return interface_wan_backup(modelo) or "a"
    return ""


def _link_por_chave(links_res: LinksCarimboResolvidos, chave: str) -> dict[str, Any]:
    if chave == "sai_bl":
        return links_res.sai_bl
    if chave == "scm":
        return links_res.scm
    if chave == "sai_bli":
        return links_res.sai_bli
    return {}


def resolver_interfaces_carimbo(
    aliases: dict[str, str],
    links_res: LinksCarimboResolvidos,
    modelo: str,
    por_cmd: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Resolve interface instalada para SAI-BL, SCM e SAI-BLI (quando aplicável).
    Ordem: alias/description (show sys interface) → IP (physical/show) → modelo.
    """
    iface_ips = extrair_ips_interfaces_logs(por_cmd)
    ifaces_usadas: set[str] = set()
    resultado: dict[str, str] = {}

    for spec in _SPECS_LINKS:
        if spec.chave == "sai_bli" and not links_res.incluir_sai_bli:
            continue
        link = _link_por_chave(links_res, spec.chave)
        id_v = str(link.get("id_vgr_links") or link.get("id_vgr") or "").strip()
        vel = link.get("velocidade_links") or link.get("velocidade") or ""
        desc = build_description(spec.circuito, spec.tecnologia, id_v, vel)
        fallback = _fallback_interface(modelo, spec.fallback_attr)

        iface = resolver_interface_por_alias(
            aliases,
            marcadores=spec.marcadores,
            descricao=desc,
            fallback="",
            excluir=ifaces_usadas,
        )
        if not iface:
            iface = resolver_interface_por_ip_link(link, iface_ips, excluir=ifaces_usadas)
        if not iface and fallback and fallback.lower() not in ifaces_usadas:
            iface = fallback

        if iface:
            ifaces_usadas.add(iface.lower())
            resultado[spec.chave] = iface

    return resultado
