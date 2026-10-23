"""Perfis de comandos CLI FortiGate (whitelist)."""

from __future__ import annotations

FGT_COMMANDS_DMA: tuple[str, ...] = (
    "get system status",
    "execute ping-options use-sdwan yes",
    "execute ping 8.8.8.8",
    "execute ping google.com",
    "execute ping service.fortiguard.net",
    "execute ping update.fortiguard.net",
    "execute ping guard.fortinet.net",
    "get ipsec tunnel list",
    "get router info bgp summary",
    "get router info routing-table all",
    "get system arp",
    "show system interface",
    "diagnose sys sdwan member",
    "diagnose sys sdwan health-check",
    "diagnose sys sdwan service4",
)

_PERFIS: dict[str, tuple[str, ...]] = {
    "dma": FGT_COMMANDS_DMA,
}


def comandos_perfil(perfil: str) -> list[str]:
    """Lista ordenada do perfil; desconhecido → perfil dma (coleta mínima SD-WAN)."""
    key = (perfil or "").strip().lower() or "dma"
    cmds = _PERFIS.get(key) or FGT_COMMANDS_DMA
    seen: set[str] = set()
    out: list[str] = []
    for cmd in cmds:
        c = (cmd or "").strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out
