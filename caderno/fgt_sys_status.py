"""
Parse de «get sys status» (FortiOS) para resumo no log da coleta PRODESP.

Por ora só alimenta logs_atendimentos; a conclusão do atendimento
cruza esses dados via ``conclusao_equipamento_rules``.
"""
from __future__ import annotations

import re
from typing import Any, Optional

CMD_GET_SYS_STATUS = "get sys status"
SYS_STATUS_RESUMO_MARKER = "--- sys status — resumo ---"

_RE_VERSION = re.compile(r"(?im)^\s*Version\s*:\s*(.+?)\s*$")
_RE_SERIAL = re.compile(r"(?im)^\s*Serial-Number\s*:\s*(\S+)\s*$")
_RE_HOSTNAME = re.compile(r"(?im)^\s*Hostname\s*:\s*(\S+)\s*$")


def normalize_fortigate_version(raw: str) -> str:
    """
    «FortiGate-40F v7.4.11,build2878,260126 (GA.M)» → «FortiGate-40F v7.4.11»
    """
    text = (raw or "").strip()
    if not text:
        return ""
    return text.split(",", 1)[0].strip()


def parse_get_sys_status(body: str) -> dict[str, str]:
    """Extrai Version (normalizada), Serial-Number e Hostname da saída bruta."""
    text = body or ""
    version_raw = ""
    m_ver = _RE_VERSION.search(text)
    if m_ver:
        version_raw = (m_ver.group(1) or "").strip()
    serial = ""
    m_ser = _RE_SERIAL.search(text)
    if m_ser:
        serial = (m_ser.group(1) or "").strip()
    hostname = ""
    m_host = _RE_HOSTNAME.search(text)
    if m_host:
        hostname = (m_host.group(1) or "").strip()
    return {
        "version_raw": version_raw,
        "version": normalize_fortigate_version(version_raw),
        "serial": serial,
        "hostname": hostname,
    }


def montar_resumo_sys_status(parsed: Optional[dict[str, Any]]) -> str:
    """Bloco legível para gravar no log da coleta."""
    data = parsed or {}
    version = (data.get("version") or "").strip()
    serial = (data.get("serial") or "").strip()
    hostname = (data.get("hostname") or "").strip()
    if not (version or serial or hostname):
        return ""
    lines = [
        SYS_STATUS_RESUMO_MARKER,
        f"Version do equipamento: {version or '—'}",
        f"Número de Serie: {serial or '—'}",
        f"Hostname: {hostname or '—'}",
    ]
    return "\n".join(lines)


def extrair_resumo_sys_status_coleta(text: str) -> str:
    """Recorta o bloco de resumo já gravado no log (se existir)."""
    raw = text or ""
    idx = raw.find(SYS_STATUS_RESUMO_MARKER)
    if idx < 0:
        return ""
    rest = raw[idx:]
    nxt = rest.find("\n--- ", len(SYS_STATUS_RESUMO_MARKER))
    if nxt > 0:
        return rest[:nxt].strip()
    return rest.strip()
