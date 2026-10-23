"""Classificação Agendado vs Fora de Escopo (dashboard gestão — total e timeline).

Regras (período [start, end] inclusivo em YYYY-MM-DD):

- **Agendado (no período)**: data de agendamento no intervalo do filtro.
- **Fora de escopo**: atendimento com atividade no período, mas sem agenda no intervalo
  (agenda vazia ou em outro dia fora do filtro).
- **Pendente**: só agendamento, sem id de atendimento.
- **Ativo**: status «Em Atendimento»; demais status com atividade = finalizado.
- Timeline diária:
  - **Agendado** no dia D: unidades distintas com agenda em D.
  - **Realizado** no dia D: atividade com data de realização D e agenda em D
    (mesmo dia — dentro do escopo da agenda do dia).
  - **Fora escopo** no dia D: atividade com realização em D e agenda ≠ D (ou vazia).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping


def day_str(val: Any) -> str:
    if val is None or val == "":
        return ""
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    s = str(val).strip()
    if not s:
        return ""
    if "T" in s:
        s = s.split("T", 1)[0]
    elif " " in s:
        s = s.split(" ", 1)[0]
    return s[:10] if len(s) >= 10 else s


def row_somente_agendado(row: Mapping[str, Any]) -> bool:
    from prodesp.prodesp.gestao.gestao_relatorio_email import row_somente_agendado as _fn

    return _fn(row)


def row_agenda_day(row: Mapping[str, Any]) -> str:
    return day_str(row.get("data_agendamento_timeline") or row.get("data_agendamento"))


def row_real_day(row: Mapping[str, Any]) -> str:
    return day_str(
        row.get("data_atendimentos")
        or row.get("data_atendimento")
        or row.get("data_evento")
    )


def _in_range(day: str, start: str, end: str) -> bool:
    return bool(day and start <= day <= end)


def _is_ativo(row: Mapping[str, Any]) -> bool:
    return (row.get("status_atendimentos") or "").strip() == "Em Atendimento"


def detalhar_total_periodo(
    rows: list[Mapping[str, Any]],
    start: str,
    end: str,
) -> dict[str, int]:
    """Contagens do card «Total no período» (soma = total)."""
    start_s = day_str(start)
    end_s = day_str(end)
    out = {
        "agendados_pend": 0,
        "agendados_finalizados": 0,
        "agendados_ativos": 0,
        "fora_escopo_finalizados": 0,
        "fora_escopo_ativos": 0,
    }
    for row in rows:
        if row_somente_agendado(row):
            out["agendados_pend"] += 1
            continue
        agenda_ok = _in_range(row_agenda_day(row), start_s, end_s)
        ativo = _is_ativo(row)
        if agenda_ok:
            if ativo:
                out["agendados_ativos"] += 1
            else:
                out["agendados_finalizados"] += 1
        else:
            if ativo:
                out["fora_escopo_ativos"] += 1
            else:
                out["fora_escopo_finalizados"] += 1
    out["total"] = (
        out["agendados_pend"]
        + out["agendados_finalizados"]
        + out["agendados_ativos"]
        + out["fora_escopo_finalizados"]
        + out["fora_escopo_ativos"]
    )
    return out


def format_hint_total_periodo(det: Mapping[str, int]) -> str:
    return (
        f"{det.get('agendados_pend', 0)} Agendados Pend. + "
        f"{det.get('agendados_finalizados', 0)} Agendados Finalizados + "
        f"{det.get('agendados_ativos', 0)} Agendados Ativos + "
        f"{det.get('fora_escopo_finalizados', 0)} Fora Escopo Finalizado + "
        f"{det.get('fora_escopo_ativos', 0)} Fora Escopo Ativo"
    )


def timeline_series(
    rows: list[Mapping[str, Any]],
    start: str,
    end: str,
) -> dict[str, dict[str, int]]:
    """Séries diárias (somente dias no filtro)."""
    start_s = day_str(start)
    end_s = day_str(end)
    scheduled_units: dict[str, set[str]] = {}
    realizado: dict[str, int] = {}
    fora: dict[str, int] = {}

    for row in rows:
        agenda = row_agenda_day(row)
        if _in_range(agenda, start_s, end_s):
            uid = row.get("id_unidades")
            if uid is None:
                uid = row.get("id_unidade")
            key = str(uid) if uid is not None and uid != "" else f"_row_{id(row)}"
            scheduled_units.setdefault(agenda, set()).add(key)

        if row_somente_agendado(row):
            continue
        real = row_real_day(row)
        if not _in_range(real, start_s, end_s):
            continue
        if agenda and agenda == real:
            realizado[real] = realizado.get(real, 0) + 1
        else:
            fora[real] = fora.get(real, 0) + 1

    scheduled = {d: len(ids) for d, ids in scheduled_units.items()}
    return {
        "scheduled": scheduled,
        "realized": realizado,
        "fora_escopo": fora,
    }
