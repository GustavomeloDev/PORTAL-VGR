"""Parse de «get system status» / «get sys status» (FortiOS)."""

from __future__ import annotations

import re
from typing import Any, Optional

CMD_GET_SYS_STATUS = "get system status"
SYS_STATUS_RESUMO_MARKER = "--- sys status — resumo ---"

_RE_VERSION = re.compile(r"(?im)^\s*Version\s*:\s*(.+?)\s*$")
_RE_SERIAL = re.compile(r"(?im)^\s*Serial-Number\s*:\s*(\S+)\s*$")
_RE_HOSTNAME = re.compile(r"(?im)^\s*Hostname\s*:\s*(\S+)\s*$")
_RE_LICENSE_STATUS = re.compile(r"(?im)^\s*License Status\s*:\s*(.+?)\s*$")
_RE_FORTICLOUD = re.compile(r"(?im)^\s*FortiCloud(?: account)?\s*:\s*(.+?)\s*$")
_RE_REGISTRATION = re.compile(r"(?im)^\s*Registration(?: Status)?\s*:\s*(.+?)\s*$")
_RE_FMG = re.compile(
    r"(?im)^\s*(?:FortiManager|Central-Management|central-management)\s*:\s*(.+?)\s*$"
)


def normalize_fortigate_version(raw: str) -> str:
    """«FortiGate-40F v7.4.11,build2878,260126 (GA.M)» → «FortiGate-40F v7.4.11»."""
    text = (raw or "").strip()
    if not text:
        return ""
    return text.split(",", 1)[0].strip()


def parse_get_sys_status(body: str) -> dict[str, str]:
    """Extrai Version, Serial-Number, Hostname e sinais de licença/gestão."""
    text = body or ""

    def _first(rx: re.Pattern[str]) -> str:
        m = rx.search(text)
        return (m.group(1) or "").strip() if m else ""

    version_raw = _first(_RE_VERSION)
    return {
        "version_raw": version_raw,
        "version": normalize_fortigate_version(version_raw),
        "serial": _first(_RE_SERIAL),
        "hostname": _first(_RE_HOSTNAME),
        "license_status": _first(_RE_LICENSE_STATUS),
        "forticloud": _first(_RE_FORTICLOUD),
        "registration": _first(_RE_REGISTRATION),
        "fortimanager": _first(_RE_FMG),
    }


def montar_resumo_sys_status(parsed: Optional[dict[str, Any]]) -> str:
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


def _positivo(valor: str) -> bool:
    low = (valor or "").strip().lower()
    if not low:
        return False
    if any(tok in low for tok in ("not registered", "unregistered", "invalid", "expired", "none")):
        return False
    return any(
        tok in low
        for tok in ("valid", "registered", "connected", "licensed", "ok", "yes", "sim")
    )


def frase_licenca_forticloud(parsed: Optional[dict[str, Any]] = None, logs: str = "") -> str:
    """Só preenche se o status/coleta confirmar. Não inventa."""
    data = parsed or {}
    if _positivo(str(data.get("license_status") or "")):
        return "Licença ativa na FortiCloud"
    if _positivo(str(data.get("forticloud") or "")) or _positivo(str(data.get("registration") or "")):
        return "Licença ativa na FortiCloud"
    blob = (logs or "").lower()
    if "forticloud" in blob and any(x in blob for x in ("registered", "connected", "valid")):
        return "Licença ativa na FortiCloud"
    return ""


def frase_fortimanager(parsed: Optional[dict[str, Any]] = None, logs: str = "") -> str:
    """Só preenche se FortiManager aparecer na coleta. Não inventa."""
    data = parsed or {}
    if _positivo(str(data.get("fortimanager") or "")):
        return "Fortigate cadastrado no FortiManager"
    blob = (logs or "").lower()
    if "fortimanager" in blob and any(
        x in blob for x in ("registered", "connected", "configured", "cadastrado")
    ):
        return "Fortigate cadastrado no FortiManager"
    return ""
