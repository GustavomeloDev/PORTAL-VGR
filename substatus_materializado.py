"""Materialização do instante de entrada no substatus atual (P0-01 / Sprint 4).

Coluna: ``atendimentos.substatus_desde_atendimentos`` (ver ``prodesp/sql/018_substatus_desde_atendimentos.sql``).

Flags (default OFF — ligar após DDL + backfill em homolog):
  PRODESP_SUBSTATUS_DESDE_WRITE=1  — grava a coluna em create/update
  PRODESP_SUBSTATUS_DESDE_READ=1   — lista/dashboard usam a coluna (sem CTE ult_sub_log_agg)

Rollback leitura: READ=0 → CTE antiga.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any


COLUMN = "substatus_desde_atendimentos"


def write_enabled() -> bool:
    return (os.getenv("PRODESP_SUBSTATUS_DESDE_WRITE", "false") or "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def read_enabled() -> bool:
    return (os.getenv("PRODESP_SUBSTATUS_DESDE_READ", "false") or "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def stamp_now(tz_aware: datetime | None = None) -> datetime:
    """Valor a gravar na coluna (naive, sem microssegundos)."""
    if tz_aware is not None:
        dt = tz_aware.replace(tzinfo=None) if tz_aware.tzinfo else tz_aware
    else:
        dt = datetime.now()
    return dt.replace(microsecond=0)


def apply_stamp_on_updates(
    atendimento_updates: dict[str, Any],
    *,
    substatus_mudou: bool,
    restart_timer: bool = False,
    now: datetime | None = None,
) -> None:
    """Dual-write: marca desde=agora quando substatus muda ou cronômetro reinicia."""
    if not write_enabled():
        return
    if not (substatus_mudou or restart_timer):
        return
    atendimento_updates[COLUMN] = stamp_now(now)


def apply_stamp_on_create(insert_data: dict[str, Any], *, now: datetime | None = None) -> None:
    if not write_enabled():
        return
    if insert_data.get("substatus_atendimentos"):
        insert_data[COLUMN] = stamp_now(now)
