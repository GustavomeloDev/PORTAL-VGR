"""Flags e destinatários dos relatórios SUPERVISORES (somente env)."""
from __future__ import annotations

import os

# Perfil SUPERVISORES no portal (Felipe + Alexandre) + caixa CAQ.
DEFAULT_SUPERVISORES_MACRO_TO = [
    "felipe.paixao@telefonica.com",
    "alexandre.neves@telefonica.com",
    "caq.vita.br@telefonica.com",
]

# Alerta de atraso (≥30 min sem analista): lista operacional combinada.
DEFAULT_SUPERVISORES_FILA_TO = [
    "felipe.paixao@telefonica.com",
    "alexandre.neves@telefonica.com",
    "jefferson.ccosta@telefonica.com",
    "vitor.silvasantos@telefonica.com",
    "gustavo.serra@telefonica.com",
    "caq.vita.br@telefonica.com",
]


def env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "sim", "on")


def env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def parse_recipients(raw: str | None, fallback: list[str] | None = None) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return list(fallback or [])
    return [e.strip() for e in text.replace(",", ";").split(";") if e.strip()]


def recipients_macro() -> list[str]:
    return parse_recipients(
        os.getenv("SUPERVISORES_MACRO_EMAIL_TO"),
        DEFAULT_SUPERVISORES_MACRO_TO,
    )


def recipients_fila() -> list[str]:
    return parse_recipients(
        os.getenv("SUPERVISORES_FILA_EMAIL_TO"),
        DEFAULT_SUPERVISORES_FILA_TO,
    )


def graph_mail_ok() -> bool:
    return all(
        (os.getenv(k) or "").strip()
        for k in ("MS_GRAPH_CLIENT_ID", "MS_GRAPH_CLIENT_SECRET", "MS_GRAPH_TENANT_ID")
    )


def _webhook_enabled_map() -> dict[str, bool]:
    try:
        from login.models import LoginDynamicSettings

        return LoginDynamicSettings.is_any_webhook_enabled_effective() or {}
    except Exception:
        return {"ALL": True, "MACRO": True, "FUST": True, "FILA": True}


def teams_webhook_url() -> str:
    raw_env = (os.getenv("SUPERVISORES_MACRO_TEAMS_WEBHOOK_URL") or "").strip()
    try:
        from login.models import LoginDynamicSettings

        raw_db = (LoginDynamicSettings.get(LoginDynamicSettings.K_WEBHOOK_MACRO) or "").strip()
        if raw_db:
            raw_env = raw_db
    except Exception:
        pass
    if not _webhook_enabled_map().get("MACRO", True):
        return ""
    return raw_env


def teams_channel_email() -> str:
    return (os.getenv("SUPERVISORES_MACRO_TEAMS_EMAIL") or "").strip()


def teams_fust_webhook_url() -> str:
    """Webhook de relatório FUST (visão dedicada, sem PRODESP).

    Ordem: 1) DB (LoginDynamicSettings, editável painel admin/supervisão);
           2) fallback env var (legado).
    """
    raw_env = (os.getenv("SUPERVISORES_MACRO_TEAMS_WEBHOOK_FUST_URL") or "").strip()
    try:
        from login.models import LoginDynamicSettings

        raw_db = (LoginDynamicSettings.get(LoginDynamicSettings.K_WEBHOOK_FUST) or "").strip()
        if raw_db:
            raw_env = raw_db
    except Exception:
        pass
    if not _webhook_enabled_map().get("FUST", True):
        return ""
    return raw_env


def teams_fila_webhook_url() -> str:
    raw_env = (os.getenv("SUPERVISORES_FILA_TEAMS_WEBHOOK_URL") or "").strip()
    try:
        from login.models import LoginDynamicSettings

        raw_db = (LoginDynamicSettings.get(LoginDynamicSettings.K_WEBHOOK_FILA) or "").strip()
        if raw_db:
            raw_env = raw_db
    except Exception:
        pass
    if not _webhook_enabled_map().get("FILA", True):
        return ""
    return raw_env


def teams_fila_webhook_chat_url() -> str:
    return (os.getenv("SUPERVISORES_FILA_TEAMS_WEBHOOK_CHAT_URL") or "").strip()


def teams_fila_webhook_urls() -> list[str]:
    saida: list[str] = []
    for url in (teams_fila_webhook_url(), teams_fila_webhook_chat_url()):
        raw = (url or "").strip()
        if raw and raw not in saida:
            saida.append(raw)
    return saida


def teams_fila_channel_email() -> str:
    return (os.getenv("SUPERVISORES_FILA_TEAMS_EMAIL") or "").strip()


def blacklist_analistas_fila() -> list[str]:
    """Blacklist de analistas IMPLANTAÇÃO que NÃO aparecem no card "Analistas disponíveis".

    Ordem de carga:
      1) DB (LoginDynamicSettings, editável via painel admin/supervisão — SEM RESTART da app).
      2) Fallback env var SUPERVISORES_FILA_ANALISTAS_BLACKLIST (CSV ; ou ,).
    """
    raw_env = os.getenv("SUPERVISORES_FILA_ANALISTAS_BLACKLIST")
    try:
        from login.models import LoginDynamicSettings

        return LoginDynamicSettings.blacklist_analistas_fila(fallback_env=raw_env)
    except Exception:
        texto = (raw_env or "").strip()
        if not texto:
            return []
        tokens: list[str] = []
        for parte in texto.replace(",", ";").split(";"):
            p = parte.strip()
            if p and p not in tokens:
                tokens.append(p)
        return tokens
