"""Credenciais SSH FortiGate — env genérico com fallback PRODESP (sem secretos no código)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(*names: str, default: str = "") -> str:
    for name in names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return (default or "").strip()


@dataclass(frozen=True)
class FgtSshCredentials:
    user: str
    password: str
    mode: str  # direct | jump
    jump_host: str
    jump_port: int
    jump_user: str
    jump_password: str


def resolve_fgt_ssh_credentials() -> FgtSshCredentials:
    """
    Preferência: FGT_SSH_* (reutilizável). Fallback: PRODESP_FGT_* / PRODESP_JUMP_*.
    mode=direct SSH no loopback; mode=jump abre túnel no jump e autentica no FGT.
    """
    user = _env("FGT_SSH_USER", "PRODESP_FGT_USER", default="vvita")
    password = _env("FGT_SSH_PASSWORD", "PRODESP_FGT_PASSWORD")
    mode = _env("FGT_SSH_MODE", default="direct").lower()
    if mode not in ("direct", "jump"):
        mode = "direct"
    jump_host = _env("FGT_JUMP_HOST", "PRODESP_JUMP_HOST_1", "PRODESP_JUMP_HOST")
    try:
        jump_port = int(_env("FGT_JUMP_PORT", "PRODESP_JUMP_PORT_1", "PRODESP_JUMP_PORT", default="22") or "22")
    except ValueError:
        jump_port = 22
    jump_user = _env("FGT_JUMP_USER", "PRODESP_JUMP_USER")
    jump_password = _env("FGT_JUMP_PASSWORD", "PRODESP_JUMP_PASSWORD")
    return FgtSshCredentials(
        user=user,
        password=password,
        mode=mode,
        jump_host=jump_host,
        jump_port=jump_port,
        jump_user=jump_user,
        jump_password=jump_password,
    )
