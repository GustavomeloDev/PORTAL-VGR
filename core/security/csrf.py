"""CSRF por sessão Flask (token em formulário, JSON ou header X-CSRF-Token).

Usuário autenticado recebe um token estável (HMAC do id + SECRET_KEY). Assim o
valor no HTML e o da requisição seguinte coincidem mesmo quando várias
requisições paralelas criariam tokens aleatórios diferentes, ou quando o
cookie de sessão não guarda a chave aleatória (cookie Secure em HTTP, remember-me).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets

from flask import current_app, jsonify, redirect, request, session, url_for

_log = logging.getLogger("portal.csrf")
_SESSION_KEY = "_portal_csrf_token"


def _authenticated_user_id() -> str | None:
    try:
        from flask_login import current_user

        if getattr(current_user, "is_authenticated", False):
            uid = current_user.get_id()
            if uid:
                return str(uid)
    except Exception:
        pass
    raw = session.get("_user_id")
    return str(raw) if raw else None


def _bound_csrf_token(user_id: str) -> str | None:
    try:
        key = current_app.secret_key
    except Exception:
        return None
    if not key:
        return None
    if isinstance(key, str):
        key = key.encode("utf-8")
    msg = f"portal-csrf-v1:{user_id}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def ensure_csrf_token() -> str:
    uid = _authenticated_user_id()
    if uid:
        bound = _bound_csrf_token(uid)
        if bound:
            return bound
    tok = session.get(_SESSION_KEY)
    if not tok:
        tok = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = tok
    return str(tok)


def validate_csrf_token(token: str | None) -> bool:
    if not token:
        return False
    token = str(token)
    expected = session.get(_SESSION_KEY)
    if expected and secrets.compare_digest(str(expected), token):
        return True
    uid = _authenticated_user_id()
    if not uid:
        return False
    bound = _bound_csrf_token(uid)
    return bool(bound) and secrets.compare_digest(bound, token)


def csrf_token_from_request():
    payload = request.get_json(silent=True) or {}
    return (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token")
        or payload.get("csrf_token")
    )


def wants_json_response() -> bool:
    if request.is_json:
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.headers.get("Accept") or ""
    if "application/json" in accept:
        return True
    ctype = request.content_type or ""
    return ctype.startswith("application/json")


def csrf_reject_response(*, login_endpoint: str = "login.admin_dashboard"):
    if wants_json_response() or not request.form:
        return jsonify(
            {"ok": False, "erro": "Token CSRF inválido ou ausente. Recarregue a página."}
        ), 403
    from flask import flash

    flash("Sessão expirada ou token inválido. Recarregue a página e tente novamente.", "danger")
    return redirect(url_for(login_endpoint))


def validate_admin_csrf_or_response():
    """Valida CSRF em mutações /login/admin/*; retorna Response ou None."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    path = request.path or ""
    if not path.startswith("/login/admin"):
        return None
    provided = csrf_token_from_request()
    if validate_csrf_token(provided):
        return None
    payload = request.get_json(silent=True) or {}
    _log.warning(
        "csrf rejeitado path=%s header=%s json=%s form=%s sessao=%s usuario=%s",
        path,
        bool(request.headers.get("X-CSRF-Token")),
        bool(payload.get("csrf_token")),
        bool(request.form.get("csrf_token")),
        bool(session.get(_SESSION_KEY)),
        bool(_authenticated_user_id()),
    )
    return csrf_reject_response()
