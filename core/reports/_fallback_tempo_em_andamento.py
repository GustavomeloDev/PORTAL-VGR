"""Helper: fallback tempo_em_segundos para atendimentos sem valor preenchido.

Dois casos principais:

1. Atendimento **CONCLUÍDO/QUEBRA/PARCIAL** mas com `tempo_em_segundos == None`
   (porque `horario_finalizacao` está NULL no banco / sem dados de parada).
   Existem esses casos no PRODESP/FUST — ex: 17/09 PRODESP ID 4355 Em Caderno concluído
   no final do dia não tem horario final; dashboard considera agora como final virtual
   e o KPI média do painel bate com isso.

2. Atendimento **EM ANDAMENTO** (modo_duracao='em_andamento' ou status != final):
   dashboard de tela usa cronômetro em tempo real com a hora atual; o tempo médio KPI
   do painel então inclui o tempo parcial de atendimentos ainda abertos.

Fallback:
  - Se tiver `tempo_total_geral` não nulo (VIEW/tabela tempo_snapshot PRODESP) usa como fallback
    (valor da view materializada da soma de etapas).
  - Caso contrário: data_atendimento + horario_inicio + horario_final (se tiver) OU data_atendimento +
    horario_inicio + agora (em_andamento). Aplica parada se existir.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Mapping

import pytz

TZ_SP = pytz.timezone("America/Sao_Paulo")

STATUSES_FINAIS_OR_FECHADOS = frozenset([
    "Concluido", "Concluído", "Concluida - entrega parcial",
    "Concluido parcial", "Concluído Parcial",
    "Quebra", "Quebra TBRA",
    "Fora de Escopo", "Finalizado",
])


def _parse_timedelta_or_timestr(val: Any) -> timedelta | None:
    if val is None:
        return None
    if isinstance(val, timedelta):
        return val
    if isinstance(val, datetime):
        return timedelta(hours=val.hour, minutes=val.minute, seconds=val.second)
    s = str(val).strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        parts_i = [int(p) for p in parts]
    except ValueError:
        return None
    while len(parts_i) < 3:
        parts_i.append(0)
    h, m, sec = parts_i[:3]
    return timedelta(hours=h, minutes=m, seconds=sec)


def _as_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _valor_em_segundos(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip()
    if not s:
        return None
    if ":" in s:
        td = _parse_timedelta_or_timestr(s)
        return int(td.total_seconds()) if td is not None else None
    try:
        return int(float(s))
    except ValueError:
        return None


def fallback_preencher_tempo_em_andamento(row: Mapping[str, Any], *, agora: datetime | None = None) -> int | None:
    """Se tempo_em_segundos == None, calcula fallback.

    Ordem:
      1) tempo_total_geral (PRODESP snapshot view)
      2) tempo_total_atendimento (se existir)
      3) data_base + horario_inicio + (horario_final OU agora se em andamento) - parada

    Retorna None se não houver base para calcular.
    """
    if row.get("tempo_em_segundos") is not None:
        return None
    # 1) snapshot do PRODESP: valor exato da view
    ttg = _valor_em_segundos(row.get("tempo_total_geral"))
    if ttg is not None:
        return ttg
    tta = _valor_em_segundos(row.get("tempo_total_atendimento"))
    if tta is not None:
        return tta

    modo = str(row.get("modo_duracao") or "").strip().lower()
    status = str(row.get("status_atendimentos") or row.get("status_atendimento") or "").strip()
    final_existe = (
        row.get("horario_finalizacao") is not None
        or row.get("horario_finalizacao_atendimentos") is not None
    )
    status_fechado = status in STATUSES_FINAIS_OR_FECHADOS
    em_andamento = (modo == "em_andamento") or (not final_existe and not status_fechado)

    # Se status fechado mas sem horario_final -> usamos inicio + parada se tiver, else 0
    data_base = _as_date(row.get("data_atendimento") or row.get("data_atendimentos"))
    if data_base is None:
        return None
    hi = _parse_timedelta_or_timestr(row.get("horario_inicio") or row.get("horario_inicio_atendimentos"))
    if hi is None:
        return None
    dt_inicio = datetime.combine(data_base, (datetime.min + hi).time())

    hf = _parse_timedelta_or_timestr(row.get("horario_finalizacao") or row.get("horario_finalizacao_atendimentos"))
    dt_final: datetime | None = None
    if hf is not None:
        dt_final = datetime.combine(data_base, (datetime.min + hf).time())
        if dt_final < dt_inicio:
            dt_final += timedelta(days=1)
    elif em_andamento or status_fechado:
        # virtual final = agora
        if agora is None:
            agora = datetime.now(TZ_SP).replace(tzinfo=None)
        dt_final = max(dt_inicio, agora)

    if dt_final is None:
        return None
    segundos_brutos = int((dt_final - dt_inicio).total_seconds())
    if segundos_brutos < 0:
        segundos_brutos = 0
    parada = row.get("parada") or row.get("parada_atendimentos")
    if isinstance(parada, timedelta):
        segundos_brutos = max(0, segundos_brutos - int(parada.total_seconds()))
    elif isinstance(parada, (int, float)):
        segundos_brutos = max(0, segundos_brutos - int(parada))
    elif isinstance(parada, str) and parada.strip():
        pt = _parse_timedelta_or_timestr(parada)
        if pt is not None:
            segundos_brutos = max(0, segundos_brutos - int(pt.total_seconds()))
    return segundos_brutos
