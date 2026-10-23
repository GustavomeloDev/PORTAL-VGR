"""ACL D6 / P5 do módulo VGR — checagens server-side (não confiar só na UI).

Perfis (strings MySQL): IMPLANTAÇÃO, GP, SUPERVISORES, AGENDAMENTO + admin_user.
Acesso ao módulo (card VGR) continua em ``before_request`` do blueprint.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import jsonify, redirect, request, url_for
from flask_login import current_user

from core.portal_flash import portal_flash
from login.portal_access_config import (
    DEPT_AGENDAMENTO,
    DEPT_GP,
    DEPT_IMPLANTACAO,
    DEPT_SUPERVISORES,
    departamentos_do_usuario,
)

# Ações alinhadas a docs/vgr/04-decisoes-abertas.md (D6) + P5
ACAO_CADASTROS = "cadastros"
ACAO_ATENDIMENTO = "atendimento"
ACAO_AGENDAR = "agendar"
ACAO_BLUEPRINT = "blueprint"
ACAO_SUPERVISAO = "supervisao"
ACAO_ADMIN_MODULO = "admin_modulo"

_PERFIS_AGENDA_GESTAO = frozenset(
    {DEPT_GP, DEPT_SUPERVISORES, DEPT_AGENDAMENTO}
)


def eh_admin(user: Any) -> bool:
    return bool(user) and int(getattr(user, "admin_user", 0) or 0) == 1


def _authed(user: Any) -> bool:
    return bool(user) and bool(getattr(user, "is_authenticated", False))


def pode_mutar_cadastros(user: Any) -> bool:
    """Cliente/unidade/eq/link/Field — todos os perfis D6 (com acesso ao módulo)."""
    return _authed(user)


def pode_atendimento(user: Any) -> bool:
    return _authed(user)


def pode_agendar(user: Any) -> bool:
    """IMPLANTAÇÃO sozinho não agenda; Admin sim (P5)."""
    if not _authed(user):
        return False
    if eh_admin(user):
        return True
    return bool(departamentos_do_usuario(user) & _PERFIS_AGENDA_GESTAO)


def pode_blueprint(user: Any) -> bool:
    """Blueprint Fortinet: IMPLANTAÇÃO ou Admin (P5)."""
    if not _authed(user):
        return False
    if eh_admin(user):
        return True
    return DEPT_IMPLANTACAO in departamentos_do_usuario(user)


def pode_supervisao_completa(user: Any) -> bool:
    """Gestão/supervisão/agenda completa — não IMPLANTAÇÃO puro."""
    if not _authed(user):
        return False
    if eh_admin(user):
        return True
    return bool(departamentos_do_usuario(user) & _PERFIS_AGENDA_GESTAO)


def pode_admin_modulo(user: Any) -> bool:
    return eh_admin(user)


def pode(user: Any, acao: str) -> bool:
    acao = (acao or "").strip().lower()
    if acao == ACAO_CADASTROS:
        return pode_mutar_cadastros(user)
    if acao == ACAO_ATENDIMENTO:
        return pode_atendimento(user)
    if acao == ACAO_AGENDAR:
        return pode_agendar(user)
    if acao == ACAO_BLUEPRINT:
        return pode_blueprint(user)
    if acao == ACAO_SUPERVISAO:
        return pode_supervisao_completa(user)
    if acao == ACAO_ADMIN_MODULO:
        return pode_admin_modulo(user)
    return False


def flags_acl(user: Any) -> dict[str, bool]:
    return {
        "pode_cadastros": pode_mutar_cadastros(user),
        "pode_atendimento": pode_atendimento(user),
        "pode_agendar": pode_agendar(user),
        "pode_blueprint": pode_blueprint(user),
        "pode_supervisao": pode_supervisao_completa(user),
        "pode_admin_modulo": pode_admin_modulo(user),
        "eh_admin": eh_admin(user),
    }


def _resposta_negada(message: str = "Sem permissão para esta ação no VGR."):
    wants_json = request.is_json or (
        request.accept_mimetypes.best_match(["application/json", "text/html"])
        == "application/json"
    ) or request.path.startswith("/vgr/api/")
    if wants_json or request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.path.startswith("/vgr/api/") or request.is_json or (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ):
            return jsonify(success=False, message=message), 403
    portal_flash(message, "warning", scope="vgr")
    return redirect(url_for("vgr.clientes_page"))


def exige_acao(acao: str) -> Callable:
    """Decorator: exige ação D6; 403 JSON nas APIs / redirect nas páginas."""

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            if not _authed(current_user):
                return _resposta_negada("Autenticação necessária.")
            if not pode(current_user, acao):
                return _resposta_negada()
            return view(*args, **kwargs)

        return wrapped

    return decorator
