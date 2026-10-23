"""
Mapeamento modelo FGT → interfaces WAN/MPLS (lista fixa para show sys interface).
Sem matriz oficial: defaults por família informada pelo projeto.
"""
from __future__ import annotations

import re
from typing import Optional

# Chave normalizada → interfaces para show sys interface
_MODEL_INTERFACE_MAP: dict[str, tuple[str, ...]] = {
    "FGT-40F": ("wan", "a", "lan1", "lan2", "lan3"),
    "FGT-41F": ("wan", "a", "lan1", "lan2", "lan3"),
    "FGT-60F": ("wan1", "a", "internal1"),
    "FGT-61F": ("wan1", "a", "internal1"),
    "FGT-70F": ("wan1", "a", "lan1"),
    "FGT-71F": ("wan1", "a", "lan1"),
    "FGT-80F": ("wan", "a", "lan3"),
    "FGT-81F": ("wan", "a", "lan3"),
    "FGT-100F": ("wan1", "a", "lan1"),
    "FGT-101F": ("wan1", "a", "lan1"),
    "FGT-200F": ("wan1", "a", "lan3"),
    "FGT-201F": ("wan1", "a", "lan3"),
}


def _normalizar_modelo_chave(modelo: str) -> Optional[str]:
    m = (modelo or "").strip().upper()
    if not m:
        return None
    m = re.sub(r"\s+", "", m)
    m = m.replace("FORTIGATE", "FGT")
    if not m.startswith("FGT"):
        m = f"FGT-{m}" if re.match(r"^\d", m) else m
    m = m.replace("FGT", "FGT-").replace("FGT--", "FGT-")
    # FGT-60F, FGT60F → FGT-60F
    m2 = re.sub(r"FGT-?(\d+)([A-Z]?)F?", r"FGT-\1\2F", m)
    if m2.endswith("F") or re.search(r"FGT-\d+[A-Z]?F$", m2):
        return m2 if m2 in _MODEL_INTERFACE_MAP else m
    return m


def normalizar_modelo_exibicao(modelo: str) -> str:
    """Rótulo para célula MODELO DE EQUIPAMENTO (lista do projeto)."""
    raw = (modelo or "").strip()
    if not raw:
        return ""
    key = _normalizar_modelo_chave(raw)
    if key and key in _MODEL_INTERFACE_MAP:
        return key.replace("FGT-", "FGT-").replace("FGT--", "FGT-")
    return raw


def interfaces_show_por_modelo(modelo: str) -> tuple[str, ...]:
    key = _normalizar_modelo_chave(modelo)
    if key and key in _MODEL_INTERFACE_MAP:
        return _MODEL_INTERFACE_MAP[key]
    # fallback conservador (template usa wan / lan3)
    return ("wan", "lan3")


def interface_wan_internet(modelo: str) -> str:
    ifaces = interfaces_show_por_modelo(modelo)
    for cand in ("wan", "wan1"):
        if cand in ifaces:
            return cand
    return ifaces[0] if ifaces else "wan"


def interface_wan_mpls(modelo: str) -> str:
    ifaces = interfaces_show_por_modelo(modelo)
    for cand in ("lan3", "hswitch-mpls", "internal1", "lan1", "lan2", "a"):
        if cand in ifaces:
            return cand
    return ifaces[-1] if len(ifaces) > 1 else "lan3"


def interface_wan_backup(modelo: str) -> str:
    """Interface do link SAI-BLI (backup), quando existir."""
    ifaces = interfaces_show_por_modelo(modelo)
    bl = interface_wan_internet(modelo)
    mpls = interface_wan_mpls(modelo)
    for cand in ifaces:
        if cand not in (bl, mpls):
            return cand
    return ""


def interfaces_coleta_carimbo(modelo: str, *, tem_sai_bli: bool = False) -> tuple[str, ...]:
    """Todas as interfaces do modelo (+ hswitch-mpls quando aplicável à coleta)."""
    del tem_sai_bli  # reservado — coleta lista completa para casar alias no log
    ifaces = list(interfaces_show_por_modelo(modelo))
    if "hswitch-mpls" not in ifaces:
        ifaces.append("hswitch-mpls")
    return tuple(dict.fromkeys(i for i in ifaces if (i or "").strip()))
