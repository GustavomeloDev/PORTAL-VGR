"""
Agendador em background — relatório executivo PRODESP por e-mail.

Registrado em ``run.py`` via
``prodesp.prodesp.gestao.gestao_relatorio_scheduler.start_gestao_relatorio_scheduler``.

Agenda, destinatários e condicionais: ``core.reports.report_settings`` (report ``GESTAO``),
editáveis em Ajustes operacionais → Personalização dos reports. O ``.env`` é o padrão:
  PRODESP_GESTAO_RELATORIO_EMAIL_ENABLED — default false; liga o agendador nesta instância
  PRODESP_GESTAO_RELATORIO_POLL_SECONDS — default 60
  PRODESP_GESTAO_RELATORIO_HORA_INICIO / HORA_FIM — default 10 / 18 (Final = HORA_FIM)
  PRODESP_GESTAO_RELATORIO_SKIP_VAZIO / FINAL_ENABLED — default true
Guia: core/docs/reports-automaticos.md. As funções de janela abaixo são legadas (testes).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

import pytz

logger = logging.getLogger(__name__)
TZ_SP = pytz.timezone("America/Sao_Paulo")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "sim", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def dia_util(now_sp: datetime) -> bool:
    """Segunda a sexta (America/Sao_Paulo)."""
    return now_sp.weekday() < 5


def hora_fim_periodico() -> int:
    return _env_int("PRODESP_GESTAO_RELATORIO_HORA_FIM", 18)


def dentro_janela_envio(now_sp: datetime) -> bool:
    """True entre hora_inicio e hora_fim (padrão 10h–18h, até :00). Relatórios periódicos."""
    hora_ini = _env_int("PRODESP_GESTAO_RELATORIO_HORA_INICIO", 10)
    hora_fim = hora_fim_periodico()
    h, m = now_sp.hour, now_sp.minute
    if h < hora_ini:
        return False
    if h > hora_fim:
        return False
    if h == hora_fim and m > 0:
        return False
    return True


def dentro_janela_report_final(now_sp: datetime) -> bool:
    """Após HORA_FIM até HORA_LIMITE_FINAL (inclusivo), para envio único de Report Final."""
    if not _env_bool("PRODESP_GESTAO_RELATORIO_FINAL_ENABLED", default=True):
        return False
    hora_fim = hora_fim_periodico()
    hora_limite = _env_int("PRODESP_GESTAO_RELATORIO_HORA_LIMITE_FINAL", 23)
    h, m = now_sp.hour, now_sp.minute
    if h < hora_fim:
        return False
    if h == hora_fim and m == 0:
        return False
    if h > hora_limite:
        return False
    return True


def slot_relatorio_gestao(now_sp: datetime) -> str:
    """Chave do slot :00 ou :30 da hora atual (deduplica envios na mesma meia hora)."""
    meia = "00" if now_sp.minute < 30 else "30"
    return f"{now_sp.strftime('%Y-%m-%d %H')}:{meia}"


def _graph_configurado() -> bool:
    return all(
        (os.getenv(k) or "").strip()
        for k in ("MS_GRAPH_CLIENT_ID", "MS_GRAPH_CLIENT_SECRET", "MS_GRAPH_TENANT_ID")
    )


def start_gestao_relatorio_scheduler(app) -> None:
    if not _env_bool("PRODESP_GESTAO_RELATORIO_EMAIL_ENABLED", default=False):
        logger.info(
            "prodesp - agendador relatório gestão desabilitado "
            "(defina PRODESP_GESTAO_RELATORIO_EMAIL_ENABLED=true no .env)"
        )
        return

    poll_sec = max(15, _env_int("PRODESP_GESTAO_RELATORIO_POLL_SECONDS", 60))

    if not _graph_configurado():
        logger.warning(
            "prodesp - agendador relatório gestão ativo, mas MS_GRAPH_* não configurado — "
            "envios automáticos falharão até preencher credenciais no .env"
        )

    def loop():
        time.sleep(30)
        from core.reports.report_settings import executar_tick

        estado: dict = {}
        while True:
            try:
                with app.app_context():
                    from prodesp.prodesp.gestao.gestao_relatorio_email import (
                        enviar_relatorio_gestao_periodo,
                        executar_report_final,
                    )

                    executar_tick(
                        "GESTAO",
                        datetime.now(TZ_SP),
                        estado,
                        lambda: enviar_relatorio_gestao_periodo().como_resultado(),
                        lambda: executar_report_final(variant="gestao"),
                    )
            except Exception:
                logger.exception("prodesp - erro no agendador relatório gestão")
            time.sleep(poll_sec)

    t = threading.Thread(target=loop, name="prodesp_gestao_relatorio", daemon=True)
    t.start()
    logger.info(
        "prodesp - agendador relatório gestão ativo (poll %s s; agenda em "
        "Ajustes Operacionais → Personalização dos reports)",
        poll_sec,
    )
