"""Headers HTTP de segurança e configuração de cookies de sessão (SEC-006, SEC-012)."""

from __future__ import annotations

import os
from typing import Mapping
from urllib.parse import urlparse


def portal_use_https() -> bool:
    """True se o portal estiver servido via HTTPS (env PORTAL_HTTPS=1/true)."""
    raw = (os.getenv("PORTAL_HTTPS") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def session_cookie_config(*, use_https: bool | None = None) -> dict[str, object]:
    """Config Flask para cookies de sessão em intranet HTTP ou HTTPS."""
    secure = portal_use_https() if use_https is None else use_https
    return {
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": bool(secure),
    }


def apply_session_cookie_config(app, *, use_https: bool | None = None) -> None:
    for key, value in session_cookie_config(use_https=use_https).items():
        app.config[key] = value


def _agendamentos_dashboard_frame_origin() -> str:
    """Origem do Streamlit embarcado no dashboard de agendamentos (CSP frame-src)."""
    raw = (os.getenv("AGENDAMENTOS_DASHBOARD_URL") or "http://localhost:8510/").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return raw.rstrip("/")


def default_security_headers(*, csp_report_only: bool = True) -> Mapping[str, str]:
    """Headers recomendados; CSP em report-only para não quebrar CDN/scripts legados."""
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }
    frame_origin = _agendamentos_dashboard_frame_origin()
    frame_src = f"frame-src 'self' {frame_origin}; " if frame_origin else "frame-src 'self'; "
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https:; "
        "connect-src 'self' https:; "
        f"{frame_src}"
        "frame-ancestors 'self'"
    )
    if csp_report_only:
        headers["Content-Security-Policy-Report-Only"] = csp
    else:
        headers["Content-Security-Policy"] = csp
    return headers


def register_security_headers(app, *, csp_report_only: bool = True) -> None:
    headers = dict(default_security_headers(csp_report_only=csp_report_only))

    @app.after_request
    def _inject_security_headers(response):
        for name, value in headers.items():
            if name not in response.headers:
                response.headers[name] = value
        return response
