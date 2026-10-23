"""
Inferência de modelo FortiGate a partir do serial (ex.: FGT40FTK25008428 → FortiGate 40F).
Alinhado à família de modelos usada em PRODAM (40F, 60F, 70F, 200F, 400F), com ordem
do mais específico para o mais curto para evitar falsos positivos em seriais numéricos.
"""
from __future__ import annotations

from typing import Optional

# (substring no serial em maiúsculas, rótulo gravado em modelo_equipamentos)
SERIAL_MODEL_FRAGMENTS_ORDERED = [
    ("900G", "FortiGate 900G"),
    ("400F", "FortiGate 400F"),
    ("200F", "FortiGate 200F"),
    ("120G", "FortiGate 120G"),
    ("100F", "FortiGate 100F"),
    ("90G", "FortiGate 90G"),
    ("80F", "FortiGate 80F"),
    ("70F", "FortiGate 70F"),
    ("60F", "FortiGate 60F"),
    ("40F", "FortiGate 40F"),
]

DEFAULT_MODELO_EQUIPAMENTO = "FortiGate 40F"
DEFAULT_MODELO_FRAGMENT = "40F"

# Ordem do mais específico → mais curto (igual SERIAL_MODEL_FRAGMENTS_ORDERED)
_MODELO_FRAGMENTS_ORDERED = tuple(frag for frag, _ in SERIAL_MODEL_FRAGMENTS_ORDERED)

# Interfaces Blueprint CSV (MV_INTF_*) por fragmento de modelo — só geração, sem persistência.
_BLUEPRINT_INTF_BY_FRAGMENT: dict[str, dict[str, str]] = {
    "40F": {
        "MV_INTF_INET_1": "wan",
        "MV_INTF_INET_2": "a",
        "MV_INTF_MPLS_1": "lan3",
        "MV_INTF_MPLS_2": "lan2",
        "MV_INTF_LAN": "lan1",
    },
    "60F": {
        "MV_INTF_INET_1": "wan1",
        "MV_INTF_INET_2": "wan2",
        "MV_INTF_MPLS_1": "a",
        "MV_INTF_MPLS_2": "b",
        "MV_INTF_LAN": "internal1",
    },
    "120G": {
        "MV_INTF_INET_1": "port1",
        "MV_INTF_INET_2": "port2",
        "MV_INTF_MPLS_1": "port3",
        "MV_INTF_MPLS_2": "port4",
        "MV_INTF_LAN": "port16",
    },
    "900G": {
        "MV_INTF_INET_1": "port1",
        "MV_INTF_INET_2": "port2",
        "MV_INTF_MPLS_1": "port3",
        "MV_INTF_MPLS_2": "port4",
        "MV_INTF_LAN": "port16",
    },
}

_BLUEPRINT_INTF_KEYS = (
    "MV_INTF_INET_1",
    "MV_INTF_INET_2",
    "MV_INTF_MPLS_1",
    "MV_INTF_MPLS_2",
    "MV_INTF_LAN",
)


def infer_modelo_equipamento_from_serial(serial):
    """
    Deriva modelo_equipamentos a partir do número de série Fortinet.
    Exemplo: FGT40FTK25008428 → FortiGate 40F
    """
    s = (serial or "").upper().replace(" ", "")
    if not s:
        return ""
    for fragment, label in SERIAL_MODEL_FRAGMENTS_ORDERED:
        if fragment in s:
            return label
    return DEFAULT_MODELO_EQUIPAMENTO


def resolve_fortigate_model_fragment(
    modelo: Optional[str] = None,
    serial: Optional[str] = None,
) -> str:
    """
    Fragmento usado no Device Blueprint (ex.: 40F, 60F).
    Prioridade: modelo_equipamentos → serial → 40F.
    """
    texto = f"{modelo or ''} {serial or ''}".upper().replace(" ", "")
    if texto.strip():
        for fragment in _MODELO_FRAGMENTS_ORDERED:
            if fragment in texto:
                return fragment
    return DEFAULT_MODELO_FRAGMENT


def blueprint_intf_fields_for_equipment(
    modelo: Optional[str] = None,
    serial: Optional[str] = None,
) -> dict[str, str]:
    """
    MV_INTF_* para o CSV. Sem modelo/serial reconhecido em 40F/60F/120G/900G → vazios.
    Não aplica DEFAULT_MODELO_FRAGMENT (diferente de resolve_fortigate_model_fragment).
    """
    texto = f"{modelo or ''} {serial or ''}".upper().replace(" ", "")
    fragment = ""
    if texto.strip():
        for frag in _MODELO_FRAGMENTS_ORDERED:
            if frag in texto:
                fragment = frag
                break
    mapped = _BLUEPRINT_INTF_BY_FRAGMENT.get(fragment) or {}
    return {k: mapped.get(k, "") for k in _BLUEPRINT_INTF_KEYS}
