"""Regras de negócio atendimento VGR — espelho PRODESP (customizar depois).

Fonte: prodesp/prodesp/atendimento_business_rules.py (edição / AG-GP / transição).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Optional

from login.portal_access_config import (
    DEPT_AGENDAMENTO,
    DEPT_GP,
    DEPT_IMPLANTACAO,
    DEPT_SUPERVISORES,
    departamentos_do_usuario,
)
from vgr.vgr.operacao.catalogo_atendimento import (
    STATUS_FINAIS,
    STATUS_OPERACIONAL,
    SUBSTATUS_AGUARDA_CONTRATADA,
    SUBSTATUS_AGUARDA_GESTAO,
    SUBSTATUS_AGUARDA_LICENCA,
    SUBSTATUS_AGUARDANDO_CLIENTE,
    SUBSTATUS_COM_SUPORTE,
    SUBSTATUS_FLUXO,
    SUBSTATUS_INICIAL_FILA,
    SUBSTATUS_LEGACY_TRIAGEM,
    SUBSTATUS_PARALELOS,
    SUBSTATUS_QUEBRA_TBRA,
    is_substatus_gestao,
    is_substatus_quebra_normal,
    normalizar_substatus_fluxo,
    validar_par_status_substatus,
)

SUBSTATUS_AG_GP_PARALELOS = frozenset(
    {
        SUBSTATUS_AGUARDANDO_CLIENTE,
        SUBSTATUS_AGUARDA_CONTRATADA,
        SUBSTATUS_AGUARDA_LICENCA,
    }
)

FILA_AGUARDANDO_GESTAO = frozenset({SUBSTATUS_INICIAL_FILA})

SUBSTATUS_EDICAO_SOMENTE_GESTAO = frozenset(
    {SUBSTATUS_LEGACY_TRIAGEM, SUBSTATUS_AGUARDA_GESTAO}
)

SUBSTATUS_EDICAO_AGENDAMENTO_GP = frozenset(
    {
        *SUBSTATUS_EDICAO_SOMENTE_GESTAO,
        *SUBSTATUS_AG_GP_PARALELOS,
        *FILA_AGUARDANDO_GESTAO,
    }
)

_PERFIS_EDICAO_RESTRITA = frozenset(
    {DEPT_AGENDAMENTO, DEPT_SUPERVISORES, DEPT_GP}
)


def usuario_usa_regras_edicao_gp_agendamento_restritas(user: Any) -> bool:
    """AG/GP/SUPERVISORES sem IMPLANTAÇÃO — mesmas regras restritas PRODESP."""
    if not user:
        return False
    if int(getattr(user, "admin_user", 0) or 0) == 1:
        return False
    depts = departamentos_do_usuario(user)
    if DEPT_IMPLANTACAO in depts:
        return False
    return bool(depts & _PERFIS_EDICAO_RESTRITA)


def destinos_substatus_permitidos_ag_gp(old_substatus: str) -> frozenset[str]:
    old = (old_substatus or "").strip()
    gestao_vals = frozenset({SUBSTATUS_AGUARDA_GESTAO, SUBSTATUS_LEGACY_TRIAGEM})
    if is_substatus_gestao(old):
        return gestao_vals | SUBSTATUS_AG_GP_PARALELOS | FILA_AGUARDANDO_GESTAO
    if old == SUBSTATUS_INICIAL_FILA:
        return gestao_vals | FILA_AGUARDANDO_GESTAO | SUBSTATUS_AG_GP_PARALELOS
    if old in SUBSTATUS_AG_GP_PARALELOS:
        return gestao_vals | SUBSTATUS_AG_GP_PARALELOS | FILA_AGUARDANDO_GESTAO
    return frozenset()


def mensagem_transicao_substatus_ag_gp_negada(
    old_substatus: str, new_substatus: str
) -> str:
    return (
        f"Seu perfil (Agendamento, GP ou SUPERVISORES) não pode mover o substatus "
        f"de «{normalizar_substatus_fluxo(old_substatus)}» para «{new_substatus}». "
        "Envie apenas para filas «Aguardando …» ou pendências paralelas; "
        "etapas «Em …» são assumidas pelo time de Implantação."
    )


def validar_transicao_substatus_ag_gp(
    old_substatus: str, new_substatus: str
) -> Optional[str]:
    old = (old_substatus or "").strip()
    new = (new_substatus or "").strip()
    if not new or new == old:
        return None
    if new in frozenset(SUBSTATUS_QUEBRA_TBRA) or is_substatus_quebra_normal(new):
        if old in SUBSTATUS_EDICAO_AGENDAMENTO_GP:
            return None
    allowed = destinos_substatus_permitidos_ag_gp(old)
    if new in allowed:
        return None
    if is_substatus_gestao(new) and SUBSTATUS_AGUARDA_GESTAO in allowed:
        return None
    return mensagem_transicao_substatus_ag_gp_negada(old, new)


def mensagem_edicao_restrita_ag_gp() -> str:
    return (
        f"Seu perfil (Agendamento, GP ou SUPERVISORES) só pode editar em "
        f"«{SUBSTATUS_AGUARDA_GESTAO}», «{SUBSTATUS_INICIAL_FILA}», ou pendências "
        f"paralelas («{SUBSTATUS_AGUARDA_LICENCA}», «{SUBSTATUS_AGUARDA_CONTRATADA}», "
        f"«{SUBSTATUS_AGUARDANDO_CLIENTE}»)."
    )


def mensagem_edicao_apenas_gestao() -> str:
    return (
        "Este substatus é exclusivo do time de Agendamento/Gestão. "
        "Somente perfis de Agendamento, GP ou SUPERVISORES podem editar ou movimentar."
    )


def _data_registro_atendimento(row: Mapping[str, Any]) -> date | None:
    raw = row.get("criado_em") or row.get("atualizado_em")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "")[:19]).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None


def validar_dono_edicao_vgr(
    nome_user: str,
    atendimento_row: Mapping[str, Any],
    *,
    is_agendamento_gp: bool,
) -> Optional[str]:
    """VGR: único campo analista_atuante nas etapas «Em …» (exceto AG/GP)."""
    if is_agendamento_gp:
        return None
    sub = normalizar_substatus_fluxo(atendimento_row.get("substatus_atendimento"))
    if not sub.startswith("Em "):
        return None
    dono = (atendimento_row.get("analista_atuante") or "").strip()
    if not dono:
        return None
    if (nome_user or "").strip().casefold() == dono.casefold():
        return None
    return (
        f"Etapa «{sub}» está com o analista «{dono}». "
        "Somente o dono (ou Admin) pode editar neste substatus."
    )


def validar_edicao_atendimento(
    user: Any,
    atendimento_row: Mapping[str, Any],
    hoje: date,
) -> tuple[bool, Optional[str], int]:
    """Permissão de edição: perfil, data (criado_em), status e dono — padrão PRODESP."""
    if not atendimento_row:
        return False, "Atendimento não encontrado.", 404

    if int(getattr(user, "admin_user", 0) or 0) == 1:
        return True, None, 200

    is_ag_gp = usuario_usa_regras_edicao_gp_agendamento_restritas(user)
    nome_user = (getattr(user, "nome_user", None) or "").strip()

    status_row = (atendimento_row.get("status_atendimento") or "").strip()
    substatus = (atendimento_row.get("substatus_atendimento") or "").strip()
    cmp_date = _data_registro_atendimento(atendimento_row)

    if is_ag_gp:
        if substatus not in SUBSTATUS_EDICAO_AGENDAMENTO_GP:
            return False, mensagem_edicao_restrita_ag_gp(), 403
        if status_row != STATUS_OPERACIONAL:
            return False, "Edição permitida apenas para atendimentos em andamento.", 403
        if cmp_date is not None and cmp_date != hoje:
            return False, "Edição permitida apenas para atendimentos da data atual.", 403
    else:
        if substatus in SUBSTATUS_EDICAO_SOMENTE_GESTAO:
            return False, mensagem_edicao_apenas_gestao(), 403
        if status_row != STATUS_OPERACIONAL:
            return False, "Edição permitida apenas para atendimentos em andamento.", 403
        if cmp_date is not None and cmp_date != hoje:
            return False, "Edição permitida apenas para atendimentos da data atual.", 403

    msg_dono = validar_dono_edicao_vgr(
        nome_user, atendimento_row, is_agendamento_gp=is_ag_gp
    )
    if msg_dono:
        return False, msg_dono, 403

    return True, None, 200


def validar_edicao_observacao_atendimento(
    user: Any,
    atendimento_row: Mapping[str, Any],
    hoje: date,
) -> tuple[bool, Optional[str], int]:
    if not atendimento_row:
        return False, "Atendimento não encontrado.", 404
    if int(getattr(user, "admin_user", 0) or 0) == 1:
        return True, None, 200
    status_row = (atendimento_row.get("status_atendimento") or "").strip()
    cmp_date = _data_registro_atendimento(atendimento_row)
    if cmp_date is not None and cmp_date != hoje:
        return False, "Edição permitida apenas para atendimentos da data atual.", 403
    if status_row in STATUS_FINAIS:
        return True, None, 200
    return validar_edicao_atendimento(user, atendimento_row, hoje)


def check_transicao_substatus_update(
    old_row: Mapping[str, Any],
    new_status: str,
    new_substatus: str,
    user: Any,
) -> Optional[str]:
    """Valida par + transição AG/GP no update."""
    err = validar_par_status_substatus(new_status, new_substatus)
    if err:
        return err
    if not usuario_usa_regras_edicao_gp_agendamento_restritas(user):
        return None
    old_sub = (old_row.get("substatus_atendimento") or "").strip()
    return validar_transicao_substatus_ag_gp(old_sub, new_substatus)


def catalogo_regras_payload() -> dict:
    """Flags para a UI espelhar destinos AG/GP e edição."""
    return {
        "fluxo": list(SUBSTATUS_FLUXO),
        "paralelos": list(SUBSTATUS_PARALELOS),
        "paralelos_ag_gp": sorted(SUBSTATUS_AG_GP_PARALELOS),
        "edicao_ag_gp": sorted(SUBSTATUS_EDICAO_AGENDAMENTO_GP),
        "edicao_somente_gestao": sorted(SUBSTATUS_EDICAO_SOMENTE_GESTAO),
        "fila_inicial": SUBSTATUS_INICIAL_FILA,
        "com_suporte": SUBSTATUS_COM_SUPORTE,
    }
