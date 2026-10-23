"""
Mensagens flash com escopo por módulo.

Categorias com escopo usam o formato ``{scope}:{category}`` (ex.: ``prodesp:warning``).
Páginas de módulo consomem apenas o escopo local; demais mensagens permanecem na sessão
até a view correta exibi-las.
"""

from __future__ import annotations

from flask import flash, session

LOGIN_ENDPOINTS = frozenset({
    "login.view_login",
    "login.submit_login",
    "login.pos_login",
})

LOGIN_SCOPED_CATEGORIES = frozenset({"login", "warning", "danger", "success", "info"})
ADMIN_SCOPED_CATEGORIES = frozenset({"admin_success", "success", "warning", "danger", "info"})

def portal_flash(message: str, category: str = "info", *, scope: str | None = None) -> None:
    if scope:
        flash(message, f"{scope}:{category}")
    else:
        flash(message, category)


def _is_login_context(endpoint: str | None) -> bool:
    if not endpoint:
        return True
    if endpoint in LOGIN_ENDPOINTS:
        return True
    return endpoint.startswith("login.admin") or endpoint == "login.admin_dashboard"


def _unscoped_visible_on_endpoint(category: str, endpoint: str | None) -> bool:
    if not endpoint:
        return category in LOGIN_SCOPED_CATEGORIES
    if endpoint in LOGIN_ENDPOINTS:
        return category in LOGIN_SCOPED_CATEGORIES or category == "login"
    if endpoint.startswith("login.admin") or endpoint == "login.admin_dashboard":
        return category in ADMIN_SCOPED_CATEGORIES
    return category in LOGIN_SCOPED_CATEGORIES


def portal_flashed_messages(view_scope: str | None = None, endpoint: str | None = None) -> list[tuple[str, str]]:
    raw = session.pop("_flashes", []) or []
    show: list[tuple[str, str]] = []
    keep: list[tuple[str, str]] = []

    login_context = _is_login_context(endpoint)

    for category, message in raw:
        if ":" in category:
            msg_scope, inner_category = category.split(":", 1)
            if view_scope and msg_scope == view_scope:
                show.append((inner_category, message))
            elif not view_scope and login_context and msg_scope == "login":
                show.append((inner_category, message))
            else:
                keep.append((category, message))
            continue

        if view_scope:
            # Em paginas de modulo, apenas mensagens com escopo explicito (ex.: fust:warning).
            keep.append((category, message))
        elif _unscoped_visible_on_endpoint(category, endpoint):
            show.append((category, message))
        else:
            keep.append((category, message))

    if keep:
        session["_flashes"] = keep
        session.modified = True

    return show


def portal_flash_alert_class(category: str) -> str:
    if category == "admin_success":
        return "success"
    if category == "login":
        return "warning"
    return category
