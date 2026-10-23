"""
Comandos CLI FortiGate para coleta PRODESP — whitelist extensível.

A consulta FortiManager (`diag dvm device list`) não entra nesta whitelist:
ela roda depois, em outro host, e o resultado fica só no log do portal.
"""
from __future__ import annotations

import re
from typing import Iterable

# Comandos base (todos os atendimentos / acrônimos)
FGT_COMMANDS_BASE: tuple[str, ...] = (
    "get sys status",
    "get sys fortiguard-service status",
    "get sys performance status",
    "diagnose fdsm central-mgmt-status",
    "get sys fortianalyzer-connectivity status",
    "get sys ha status",
    "diag sys sdwan health-check status",
    "diagnose sys sdwan service4",
    "get ipsec tunnel list",
    "get sys interface physical",
    "show sys interface",
    "get sys arp",
    "diagnose sys sip-proxy calls",
    "exec dhcp lease-list",
    "show firewall policy",
)

# Extensível: acrônimo → comandos extras (vazio = usa só base)
FGT_COMMANDS_BY_ACRONIMO: dict[str, tuple[str, ...]] = {}


def comandos_para_acronimo(acronimo: str) -> list[str]:
    """Lista ordenada e deduplicada de comandos para a unidade."""
    acr = (acronimo or "").strip().upper()
    extras = FGT_COMMANDS_BY_ACRONIMO.get(acr, ())
    seen: set[str] = set()
    out: list[str] = []
    for cmd in (*FGT_COMMANDS_BASE, *extras):
        c = (cmd or "").strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def id_intragov_para_grep_fmg(id_intragov: str) -> str:
    """
    Normaliza id_intragov_unidades para o grep do FortiManager.

    «0309472/26» e «00309472/26» viram «00309472» (8 dígitos, sem o sufixo /26).
    Valor não numérico (ex.: IG999) retorna vazio — o comando não é montado.
    """
    base = (id_intragov or "").strip().split("/", 1)[0].strip()
    if not base or not re.fullmatch(r"[0-9]+", base) or len(base) > 12:
        return ""
    try:
        numero = int(base, 10)
    except ValueError:
        return ""
    if numero <= 0 or numero > 99_999_999:
        return ""
    return f"{numero:08d}"


def comando_diag_dvm_device_list(id8: str) -> str:
    """Comando FortiManager. O id precisa ser exatamente 8 dígitos (sem metacaracteres)."""
    token = (id8 or "").strip()
    if not re.fullmatch(r"[0-9]{8}", token):
        raise ValueError("ID FortiManager inválido.")
    return f"diag dvm device list | grep -A 2 -if {token}"


def comandos_show_interface(interfaces: Iterable[str]) -> list[str]:
    """Gera show sys interface <iface> para lista fixa por modelo."""
    cmds: list[str] = []
    for iface in interfaces:
        i = (iface or "").strip()
        if i:
            cmds.append(f"show sys interface {i}")
    return cmds
