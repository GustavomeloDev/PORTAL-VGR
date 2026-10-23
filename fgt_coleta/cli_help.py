"""Ajuda CLI FortiOS («comando ?») — espaço obrigatório antes do «?»."""

from __future__ import annotations

import re

_CLI_HELP_SUFFIX_RE = re.compile(r"\s*\?\s*$")


def format_fgt_cli_help_command(partial_command: str) -> str:
    """
    Monta comando de ajuda FortiOS com espaço obrigatório antes de «?».

    «show sys admin ?» funciona; «show sys admin?» não.
    O mesmo vale para «execute disconnect-admin-session ?».
    """
    base = _CLI_HELP_SUFFIX_RE.sub("", (partial_command or "").strip()).strip()
    if not base:
        raise ValueError("comando parcial vazio para ajuda CLI FortiOS")
    return f"{base} ?"
