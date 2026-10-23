"""Validação de payload de agendamento VGR."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from vgr.vgr.cadastros.validators import _as_bool01, _trim
from vgr.vgr.operacao.catalogo_agendamento import (
    CHECKLIST_FIELDS,
    STATUS_AGENDAMENTO_SET,
    STATUS_DEFAULT,
    TIPO_AGENDAMENTO_OK,
)


def _parse_date(value: Any) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    s = str(value).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise ValueError("Data de agendamento inválida.") from exc


def _parse_time(value: Any) -> time | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, time):
        return value
    s = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    raise ValueError("Horário inválido.")


def parse_field_ids(raw: Any) -> list[int]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValueError("Lista de Fields inválida.")
    out: list[int] = []
    seen: set[int] = set()
    for item in raw:
        try:
            fid = int(item)
        except (TypeError, ValueError):
            raise ValueError("Field inválido.") from None
        if fid <= 0 or fid in seen:
            continue
        seen.add(fid)
        out.append(fid)
    if len(out) > 30:
        raise ValueError("Máximo de 30 Fields por agendamento.")
    return out


def parse_agendamento_payload(
    raw: dict[str, Any] | None, *, partial: bool = False
) -> dict[str, Any]:
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

    if "status_agendamento" in raw or not partial:
        st = _trim(raw.get("status_agendamento"), 64) or STATUS_DEFAULT
        if st not in STATUS_AGENDAMENTO_SET:
            raise ValueError("Status de agendamento inválido.")
        out["status_agendamento"] = st

    if "substatus_agendamento" in raw or not partial:
        out["substatus_agendamento"] = _trim(raw.get("substatus_agendamento"), 64)

    if "data_agendamento" in raw or not partial:
        out["data_agendamento"] = _parse_date(raw.get("data_agendamento"))

    for key in ("hora_agendamento", "hora_inicio", "hora_fim"):
        if key in raw or not partial:
            out[key] = _parse_time(raw.get(key))

    if "tipo" in raw or not partial:
        tipo = _trim(raw.get("tipo"), 32)
        if tipo and tipo not in TIPO_AGENDAMENTO_OK:
            raise ValueError("Tipo de agendamento inválido.")
        out["tipo"] = tipo

    if "analista_destino" in raw or not partial:
        out["analista_destino"] = _trim(raw.get("analista_destino"), 120)

    if "analista_livre" in raw or not partial:
        out["analista_livre"] = _as_bool01(raw.get("analista_livre"), 0)

    if out.get("analista_livre") and out.get("analista_destino"):
        # livre = sem dono fixo
        out["analista_destino"] = None

    if "observacoes" in raw or not partial:
        obs = raw.get("observacoes")
        if obs is None or str(obs).strip() == "":
            out["observacoes"] = None
        else:
            out["observacoes"] = str(obs).strip()[:5000]

    for q in CHECKLIST_FIELDS:
        if q in raw or not partial:
            out[q] = _as_bool01(raw.get(q), 0)

    if "id_fields" in raw:
        out["id_fields"] = parse_field_ids(raw.get("id_fields"))
        out["_set_fields"] = True

    if "ativo" in raw:
        out["ativo"] = _as_bool01(raw.get("ativo"), 1)
    return out
