"""
Resolução de links e formatação de campos do CARIMBO NOC (caderno PRODESP).
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Optional

from prodesp.prodesp.blueprint.prodesp_csv_generator import format_velocity

_NA_VALUES = frozenset({"", "N/A", "N/A_", "NA"})


def _strip_ip(val: str) -> str:
    v = (val or "").strip()
    if not v:
        return ""
    return v.split("/")[0].strip()


def _vazio_ou_na(val: Any) -> bool:
    v = (str(val) if val is not None else "").strip().upper()
    if not v:
        return True
    if v in _NA_VALUES:
        return True
    return v.startswith("N/A") and all(c in "N/A_-" for c in v)


def mask_to_prefix(mask: str) -> Optional[int]:
    m = (mask or "").strip()
    if not m:
        return None
    if m.startswith("/"):
        try:
            return int(m.lstrip("/"))
        except ValueError:
            return None
    if re.fullmatch(r"\d{1,2}", m):
        p = int(m)
        return p if 0 <= p <= 32 else None
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{m}", strict=False).prefixlen
    except ValueError:
        return None


def _parse_ip_cidr(cidr: str) -> tuple[str, Optional[int]]:
    raw = (cidr or "").strip()
    if not raw:
        return "", None
    if "/" in raw:
        ip_part, prefix_part = raw.split("/", 1)
        try:
            return ip_part.strip(), int(prefix_part.strip())
        except ValueError:
            return ip_part.strip(), None
    return raw, None


def _mesma_rede(ip_a: str, ip_b: str, prefix: int) -> bool:
    if not ip_a or not ip_b or prefix is None:
        return False
    try:
        rede_a = ipaddress.ip_network(f"{ip_a}/{prefix}", strict=False)
        rede_b = ipaddress.ip_network(f"{ip_b}/{prefix}", strict=False)
        return rede_a == rede_b
    except ValueError:
        return False


def _host_superior_rede(referencia: str, prefix: int) -> str:
    rede = ipaddress.ip_network(f"{referencia}/{prefix}", strict=False)
    hosts = list(rede.hosts())
    if len(hosts) >= 2:
        return str(hosts[-1])
    if len(hosts) == 1:
        return str(hosts[0])
    return referencia


def _arp_vizinhos_rede(wan_host: str, prefix: int, arp_neighbors: list[str] | None) -> list[str]:
    vizinhos: list[str] = []
    for addr in arp_neighbors or []:
        if addr == wan_host:
            continue
        if _mesma_rede(addr, wan_host, prefix):
            vizinhos.append(addr)
    return vizinhos


def _resolver_remoto(
    wan_host: str,
    prefix: int,
    ip_gw_db: str,
    *,
    arp_neighbors: list[str] | None = None,
) -> str:
    """REMOTO: ARP na interface + gateway cadastrado + outro host do enlace."""
    arp_rede = _arp_vizinhos_rede(wan_host, prefix, arp_neighbors)
    if arp_rede:
        if ip_gw_db and ip_gw_db in arp_rede:
            return ip_gw_db
        if len(arp_rede) == 1:
            return arp_rede[0]
        if ip_gw_db and _mesma_rede(ip_gw_db, wan_host, prefix):
            return ip_gw_db
        return sorted(arp_rede, key=lambda x: int(ipaddress.ip_address(x)))[0]

    if ip_gw_db and _mesma_rede(ip_gw_db, wan_host, prefix):
        try:
            rede = ipaddress.ip_network(f"{wan_host}/{prefix}", strict=False)
            gw = ipaddress.ip_address(ip_gw_db)
            wan = ipaddress.ip_address(wan_host)
            if gw in rede and gw != wan:
                return ip_gw_db
        except ValueError:
            pass
    try:
        rede = ipaddress.ip_network(f"{wan_host}/{prefix}", strict=False)
        hosts = [str(h) for h in rede.hosts()]
        if wan_host in hosts:
            for host in hosts:
                if host != wan_host:
                    return host
        if len(hosts) >= 2:
            return hosts[0]
        if len(hosts) == 1:
            return hosts[0]
    except ValueError:
        pass
    return ip_gw_db or wan_host


def _resolver_wan_host(
    *,
    ip_wan_db: str,
    ip_gw_db: str,
    prefix: int,
    ip_log: str,
) -> str:
    """
    IP WAN: validação tripla log (FGT) × cadastro (links) × fallback legado.
    Log na mesma rede prevalece; sem log usa ip_wan_links (não host superior da sub-rede).
    """
    if ip_log and prefix is not None:
        if ip_wan_db and _mesma_rede(ip_log, ip_wan_db, prefix):
            return ip_log
        if ip_gw_db and _mesma_rede(ip_log, ip_gw_db, prefix):
            return ip_log
        if not ip_wan_db:
            return ip_log
        if not _mesma_rede(ip_log, ip_wan_db, prefix):
            return ip_log

    if ip_wan_db:
        return ip_wan_db

    referencia = ip_gw_db
    if referencia and prefix is not None:
        return _host_superior_rede(referencia, prefix)
    return ip_log or ip_gw_db


def format_carimbo_ip_wan_remoto(
    link: dict[str, Any],
    *,
    ip_interface_log: str = "",
    arp_neighbors: list[str] | None = None,
) -> tuple[str, str]:
    """
    IP WAN e REMOTO: cadastro links + IP da interface (show/physical) + ARP na interface.
    ip_interface_log: CIDR da interface (ex.: 10.250.56.66/29).
    arp_neighbors: endereços vistos em get sys arp na mesma interface.
    """
    ip_wan_db = _strip_ip(link.get("ip_wan_links") or link.get("ip_wan") or "")
    ip_gw_db = _strip_ip(link.get("ip_gateway_links") or link.get("ip_gateway") or "")
    prefix_link = mask_to_prefix(link.get("ip_mascara_links") or link.get("ip_mascara") or "")
    ip_log, prefix_log = _parse_ip_cidr(ip_interface_log)
    prefix = prefix_link if prefix_link is not None else prefix_log

    if prefix is None:
        wan = ip_log or ip_wan_db
        remoto = ip_gw_db or ip_wan_db or wan
        return wan, remoto

    wan_host = _resolver_wan_host(
        ip_wan_db=ip_wan_db,
        ip_gw_db=ip_gw_db,
        prefix=prefix,
        ip_log=ip_log,
    )
    if not wan_host:
        return "", ip_gw_db

    ip_wan_out = f"{wan_host}/{prefix}"
    remoto = _resolver_remoto(wan_host, prefix, ip_gw_db, arp_neighbors=arp_neighbors)
    return ip_wan_out, remoto


def format_velocidade_carimbo(velocidade: str) -> str:
    v = format_velocity(velocidade)
    if not v:
        return ""
    if re.search(r"Mb$", v, flags=re.I):
        return re.sub(r"Mb$", "Mb", v, flags=re.I)
    return f"{v}Mb"


def _designador(link: dict[str, Any]) -> str:
    return (link.get("designador_links") or link.get("designador") or "").strip().upper()


def _tipo(link: dict[str, Any]) -> str:
    return (link.get("tipo_links") or link.get("tipo") or "").strip().upper()


def link_sai_bl(links: list[dict[str, Any]]) -> dict[str, Any]:
    for lnk in links:
        d = _designador(lnk)
        if "SAI-BL" in d or "INET1" in d:
            return lnk
    for lnk in links:
        if _tipo(lnk) == "STATIC" and "SAI-BLI" not in _designador(lnk) and "INET2" not in _designador(lnk):
            return lnk
    return next((l for l in links if _tipo(l) == "STATIC"), {})


def link_sai_bli(links: list[dict[str, Any]]) -> dict[str, Any]:
    for lnk in links:
        d = _designador(lnk)
        if "SAI-BLI" in d or "INET2" in d:
            return lnk
    prim = link_sai_bl(links)
    prim_key = prim.get("id_link") or id(prim)
    for lnk in links:
        if _tipo(lnk) != "STATIC":
            continue
        lnk_key = lnk.get("id_link") or id(lnk)
        if prim and lnk_key == prim_key:
            continue
        return lnk
    return {}


def link_scm(links: list[dict[str, Any]]) -> dict[str, Any]:
    for lnk in links:
        if "SCM" in _designador(lnk):
            return lnk
    return next((l for l in links if _tipo(l) == "MPLS"), {})


def deve_inserir_bloco_sai_bli(link: dict[str, Any]) -> bool:
    """Não inserir Conectividade SAI-BLI se dados vazios ou N/A."""
    if not link:
        return False
    id_v = (link.get("id_vgr_links") or link.get("id_vgr") or "").strip()
    ip_wan = _strip_ip(link.get("ip_wan_links") or link.get("ip_wan") or "")
    vel = (link.get("velocidade_links") or link.get("velocidade") or "").strip()
    designador = _designador(link)
    if _vazio_ou_na(id_v) and not ip_wan and _vazio_ou_na(vel):
        return False
    if _vazio_ou_na(id_v) and not ip_wan:
        return False
    if "SAI-BLI" not in designador and "INET2" not in designador:
        if _vazio_ou_na(id_v) or _vazio_ou_na(vel):
            return False
    return True


def deve_exibir_bloco_sai_bli_no_carimbo(campos: dict[str, Any]) -> bool:
    """Ocultar bloco SAI-BLI na planilha/cópia quando circuito ou dados úteis estão vazios/N/A."""
    if not campos:
        return False
    circuito = str(campos.get("circuito") or "").strip()
    id_v = str(campos.get("id_vantive") or campos.get("id_vgr") or "").strip()
    ip = str(campos.get("ip_wan") or "").strip()
    vel = str(campos.get("velocidade") or "").strip()
    desc = str(campos.get("description") or "").strip()
    if _vazio_ou_na(circuito):
        return False
    if _vazio_ou_na(id_v) and not ip:
        return False
    if _vazio_ou_na(id_v) and _vazio_ou_na(vel) and not ip:
        return False
    if not desc or re.fullmatch(r"N/A(_N/A)?_*", desc):
        return False
    return True


def build_description(circuito: str, tecnologia: str, id_vantive: str, velocidade: str) -> str:
    vel = format_velocity(velocidade)
    id_v = (id_vantive or "").strip() or "N/A"
    if not vel:
        return f"{circuito}_{tecnologia}_{id_v}_"
    return f"{circuito}_{tecnologia}_{id_v}_{vel}"


@dataclass
class LinksCarimboResolvidos:
    sai_bl: dict[str, Any]
    sai_bli: dict[str, Any]
    scm: dict[str, Any]

    @property
    def incluir_sai_bli(self) -> bool:
        return deve_inserir_bloco_sai_bli(self.sai_bli)


def resolver_links_carimbo(links: list[dict[str, Any]]) -> LinksCarimboResolvidos:
    return LinksCarimboResolvidos(
        sai_bl=link_sai_bl(links),
        sai_bli=link_sai_bli(links),
        scm=link_scm(links),
    )


def montar_bloco_carimbo(
    link: dict[str, Any],
    *,
    interface: str,
    circuito: str,
    tecnologia: str,
    ip_interface_log: str = "",
    arp_neighbors: list[str] | None = None,
) -> dict[str, str]:
    id_v = str(link.get("id_vgr_links") or link.get("id_vgr") or "").strip()
    vel = link.get("velocidade_links") or link.get("velocidade") or ""
    ip_wan, remoto = format_carimbo_ip_wan_remoto(
        link,
        ip_interface_log=ip_interface_log,
        arp_neighbors=arp_neighbors,
    )
    return {
        "interface": interface,
        "circuito": circuito,
        "tecnologia": tecnologia,
        "id_vantive": id_v or "N/A",
        "velocidade": format_velocidade_carimbo(vel),
        "description": build_description(circuito, tecnologia, id_v, vel),
        "ip_wan": ip_wan,
        "remoto": remoto,
    }


def nome_arquivo_caderno(unidade: dict[str, Any]) -> str:
    acr = (unidade.get("acronimo_unidades") or unidade.get("acronimo") or "").strip()
    id_vgr = str(unidade.get("id_vgr_unidades") or unidade.get("id_vgr") or "").strip()
    id_intra = str(unidade.get("id_intragov_unidades") or unidade.get("id_intragov") or "").strip()
    id_intra = id_intra.replace("/", "-")
    return f"{acr}_ID_VGR_{id_vgr}_ID_INTRAGOV_{id_intra}"
