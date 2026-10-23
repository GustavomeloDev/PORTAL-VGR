"""Validação de payload de atendimento VGR."""
from __future__ import annotations

from typing import Any

from vgr.vgr.cadastros.validators import _as_bool01, _trim
from vgr.vgr.operacao.catalogo_atendimento import (
    STATUS_ATENDIMENTO_OK,
    STATUS_OPERACIONAL,
    is_substatus_gestao,
    resolver_par_status_substatus,
    substatus_padrao,
)


def parse_atendimento_payload(
    raw: dict[str, Any] | None, *, partial: bool = False
) -> dict[str, Any]:
    """Payload atendimento (P4/P6/P13). `id_agendamento` opcional (walk-in)."""
    raw = raw or {}
    out: dict[str, Any] = {}

    if "id_unidade" in raw or not partial:
        try:
            id_unidade = int(raw.get("id_unidade"))
        except (TypeError, ValueError):
            raise ValueError("Unidade é obrigatória.") from None
        if id_unidade <= 0:
            raise ValueError("Unidade é obrigatória.")
        out["id_unidade"] = id_unidade

    if "id_agendamento" in raw:
        ag = raw.get("id_agendamento")
        if ag is None or str(ag).strip() == "":
            out["id_agendamento"] = None
        else:
            try:
                id_ag = int(ag)
            except (TypeError, ValueError):
                raise ValueError("Agendamento inválido.") from None
            if id_ag <= 0:
                raise ValueError("Agendamento inválido.")
            out["id_agendamento"] = id_ag

    # ---------------- status + substatus (validação do PAR) ----------------
    status_in = (
        "status_atendimento" in raw or not partial
    )
    sub_in = "substatus_atendimento" in raw or not partial

    st: str | None = None
    if status_in:
        st = _trim(raw.get("status_atendimento"), 64) or STATUS_OPERACIONAL
        if st not in STATUS_ATENDIMENTO_OK:
            # tolerante a acento/caixa antes de rejeitar
            st_canon, _, _ = resolver_par_status_substatus(st, None)
            st = st_canon

    if sub_in:
        sub = _trim(raw.get("substatus_atendimento"), 64)
        if not sub and not partial:
            sub = substatus_padrao(st) or "Aguarda Gestão"

        st_canon, sub_canon, erro = resolver_par_status_substatus(st, sub)
        if erro:
            raise ValueError(erro)

        if st is not None:
            st = st_canon
        if sub_canon:
            out["substatus_atendimento"] = sub_canon
        elif not partial:
            out["substatus_atendimento"] = None

    if st is not None:
        out["status_atendimento"] = st
    # ----------------------------------------------------------------------

    if "analista_atuante" in raw or not partial:
        out["analista_atuante"] = _trim(raw.get("analista_atuante"), 120)

    if "observacoes" in raw:
        obs = raw.get("observacoes")
        if obs is None or str(obs).strip() == "":
            out["observacoes"] = None
        else:
            out["observacoes"] = str(obs).strip()[:5000]

    if "atendimento_iniciado" in raw:
        out["atendimento_iniciado"] = _as_bool01(raw.get("atendimento_iniciado"), 0)

    if "ativo" in raw:
        out["ativo"] = _as_bool01(raw.get("ativo"), 1)
    return out

# ---------------------------------------------------------------------------
# Bloqueios de transição (espelho PRODESP) — usados pelo gate server-side
# ---------------------------------------------------------------------------
VGR_FILAS_AGUARDANDO_CONFIG: frozenset[str] = frozenset(
    {
        "Aguardando Config. Remota",
        "Aguardando Config. MPLS",
        "Aguardando Caderno de Teste",
    }
)
VGR_AGUARDA_EXTERNO: frozenset[str] = frozenset(
    {"Aguarda Cliente", "Aguarda Contratada"}
)


def is_transicao_gestao_para_fila_config(old_sub: str | None, new_sub: str | None) -> bool:
    """Aguarda Gestão (ou Triagem legada) → fila «Aguardando …» de configuração."""
    return is_substatus_gestao(old_sub) and (new_sub or "").strip() in VGR_FILAS_AGUARDANDO_CONFIG