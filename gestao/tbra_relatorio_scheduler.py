"""
Agendador — relatório executivo Time TBRA (horários fixos + Report Final).

Registrado em ``run.py`` via ``start_tbra_relatorio_scheduler``.

Agenda, destinatários e condicionais: ``core.reports.report_settings`` (report ``TBRA``),
editáveis em Ajustes operacionais → Personalização dos reports. O ``.env`` é o padrão:
  PRODESP_TIME_TBRA_RELATORIO_EMAIL_ENABLED — default false; liga o agendador nesta instância
  PRODESP_TIME_TBRA_RELATORIO_EMAIL_TO — destinatários (; ou ,)
  PRODESP_TIME_TBRA_RELATORIO_POLL_SECONDS — default 60
  PRODESP_TIME_TBRA_RELATORIO_HORARIOS — default 11,15,18,22 (Final após o último)
  PRODESP_TIME_TBRA_RELATORIO_SKIP_VAZIO / FINAL_ENABLED — default true
Guia: core/docs/reports-automaticos.md. As funções de janela abaixo são legadas (testes).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

import pytz

from prodesp.prodesp.gestao.gestao_relatorio_scheduler import (
    _env_bool,
    _env_int,
    _graph_configurado,
    dia_util,
)

logger = logging.getLogger(__name__)
TZ_SP = pytz.timezone("America/Sao_Paulo")
DEFAULT_HORARIOS_TBRA = (11, 15, 18, 22)


def horarios_tbra_from_env() -> tuple[int, ...]:
    raw = (os.getenv("PRODESP_TIME_TBRA_RELATORIO_HORARIOS") or "").strip()
    if not raw:
        return DEFAULT_HORARIOS_TBRA
    out: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            h = int(part)
        except ValueError:
            continue
        if 0 <= h <= 23:
            out.append(h)
    return tuple(sorted(set(out))) if out else DEFAULT_HORARIOS_TBRA


def slot_relatorio_tbra(now_sp: datetime, horarios: tuple[int, ...]) -> str | None:
    """Chave do slot horário do dia (deduplica um envio por hora configurada)."""
    if now_sp.hour not in horarios:
        return None
    return f"{now_sp.strftime('%Y-%m-%d')} {now_sp.hour:02d}"


def hora_fim_periodico_tbra(horarios: tuple[int, ...] | None = None) -> int:
    """Último horário periódico TBRA (= início da janela de Report Final)."""
    hs = horarios if horarios is not None else horarios_tbra_from_env()
    return max(hs) if hs else max(DEFAULT_HORARIOS_TBRA)


def dentro_janela_report_final_tbra(
    now_sp: datetime,
    horarios: tuple[int, ...] | None = None,
) -> bool:
    """Após o último horário periódico até HORA_LIMITE_FINAL (inclusivo)."""
    if not _env_bool("PRODESP_TIME_TBRA_RELATORIO_FINAL_ENABLED", default=True):
        return False
    hora_fim = hora_fim_periodico_tbra(horarios)
    hora_limite = _env_int("PRODESP_TIME_TBRA_RELATORIO_HORA_LIMITE_FINAL", 23)
    h, m = now_sp.hour, now_sp.minute
    if h < hora_fim:
        return False
    if h == hora_fim and m == 0:
        # Ainda é o slot periódico da última hora — Final só depois do :00 do slot
        return False
    if h > hora_limite:
        return False
    return True


def start_tbra_relatorio_scheduler(app) -> None:
    if not _env_bool("PRODESP_TIME_TBRA_RELATORIO_EMAIL_ENABLED", default=False):
        logger.info(
            "prodesp - agendador relatório TBRA desabilitado "
            "(defina PRODESP_TIME_TBRA_RELATORIO_EMAIL_ENABLED=true no .env)"
        )
        return

    poll_sec = max(15, _env_int("PRODESP_TIME_TBRA_RELATORIO_POLL_SECONDS", 60))

    if not _graph_configurado():
        logger.warning(
            "prodesp - agendador relatório TBRA ativo, mas MS_GRAPH_* não configurado — "
            "envios automáticos falharão até preencher credenciais no .env"
        )

    def loop():
        time.sleep(30)
        from core.reports.report_settings import executar_tick

        estado: dict = {}
        while True:
            try:
                with app.app_context():
                    from prodesp.prodesp.gestao.gestao_relatorio_email import executar_report_final
                    from prodesp.prodesp.gestao.tbra_relatorio_email import (
                        enviar_relatorio_tbra_periodo,
                    )

                    executar_tick(
                        "TBRA",
                        datetime.now(TZ_SP),
                        estado,
                        lambda: enviar_relatorio_tbra_periodo().como_resultado(),
                        lambda: executar_report_final(variant="tbra"),
                    )
            except Exception:
                logger.exception("prodesp - erro no agendador relatório TBRA")
            time.sleep(poll_sec)

    t = threading.Thread(target=loop, name="prodesp_tbra_relatorio", daemon=True)
    t.start()
    logger.info(
        "prodesp - agendador relatório TBRA ativo (poll %s s; agenda em "
        "Ajustes Operacionais → Personalização dos reports)",
        poll_sec,
    )
