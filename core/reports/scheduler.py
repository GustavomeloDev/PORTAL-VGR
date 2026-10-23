"""Agendador dos relatórios SUPERVISORES (FUST + PRODESP).

Registrado em ``run.py`` (America/Sao_Paulo). Agenda, destinatários e condicionais vêm de
``core.reports.report_settings`` (Ajustes Operacionais → Personalização dos reports; padrão = .env).
Snapshot da fila ≥ limiar: dispara na 1ª unidade nova e relembra no intervalo configurado.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

import pytz

from core.reports.env_config import env_int, graph_mail_ok

logger = logging.getLogger(__name__)
TZ_SP = pytz.timezone("America/Sao_Paulo")


def dia_util(now_sp: datetime) -> bool:
    return now_sp.weekday() < 5


def slot_meia_hora(now_sp: datetime) -> str:
    meia = "00" if now_sp.minute < 30 else "30"
    return f"{now_sp.strftime('%Y-%m-%d %H')}:{meia}"


def dentro_janela(now_sp: datetime, env_ini: str, env_fim: str, default_ini: int, default_fim: int) -> bool:
    hora_ini = env_int(env_ini, default_ini)
    hora_fim = env_int(env_fim, default_fim)
    h, m = now_sp.hour, now_sp.minute
    if h < hora_ini:
        return False
    if h > hora_fim:
        return False
    if h == hora_fim and m > 0:
        return False
    return True


def tick_fila(now_sp: datetime, estado: dict) -> None:
    """Snapshot da fila (1ª unidade nova + relembre) e Report Final, conforme a config FILA."""
    from core.reports.data_loaders import carregar_fila_atual
    from core.reports.fila_sem_analista import (
        aplicar_proximo_aviso,
        chave_fila,
        deve_enviar_snapshot_fila,
        podar_contagem_avisos,
        registrar_envio_avisos,
    )
    from core.reports.report_settings import (
        carregar_config,
        dentro_janela as dentro_agenda,
        final_devido,
        slot_periodico,
    )
    from core.reports.send_reports import enviar_fila

    cfg = carregar_config("FILA")
    dia = now_sp.strftime("%Y-%m-%d")
    if estado.get("final_dia") and estado["final_dia"] != dia:
        estado["final_dia"] = None
    if not (cfg.email_ativo or cfg.teams_ativo):
        return
    if dentro_agenda(cfg, now_sp):
        atuais = carregar_fila_atual(minutos_min=cfg.fila_limiar_min)
        contagem = podar_contagem_avisos(estado.setdefault("contagem", {}), atuais)
        estado["contagem"] = contagem
        slot = None
        if cfg.agenda_modo == "horarios":
            # Unidade nova alerta na hora; o relembre da fila inteira só nos horários fixos.
            slot = slot_periodico(cfg, now_sp)
            nova = any(chave_fila(i) not in contagem for i in atuais)
            relembre = slot is not None and slot != estado.get("slot")
            enviar = bool(atuais) and (nova or relembre)
        else:
            enviar = deve_enviar_snapshot_fila(
                atuais,
                contagem,
                now_sp,
                estado.get("ultimo_envio"),
                relembre_min=cfg.intervalo_min,
            )
        if enviar:
            aplicar_proximo_aviso(atuais, contagem)
            res = enviar_fila(tipo="periodico", itens=atuais)
            if res.enviado:
                registrar_envio_avisos(contagem, atuais)
                logger.info(
                    "supervisores - fila snapshot %s unidade(s) ≥%s min",
                    len(atuais),
                    cfg.fila_limiar_min,
                )
            if res.enviado or res.motivo == "igual":
                estado["ultimo_envio"] = now_sp
                if slot is not None:
                    estado["slot"] = slot
    if estado.get("final_dia") != dia and final_devido(cfg, now_sp):
        res = enviar_fila(tipo="final")
        estado["final_dia"] = dia
        logger.info("supervisores - fila Report Final (%s): %s", dia, res.motivo or "enviado")


def start_supervisores_relatorio_scheduler(app) -> None:
    from core.reports.report_settings import executar_tick, report_permitido_no_servidor

    macro_on = report_permitido_no_servidor("MACRO")
    fust_on = report_permitido_no_servidor("FUST")
    fila_on = report_permitido_no_servidor("FILA")
    if not macro_on and not fila_on:
        logger.info(
            "supervisores - agendador desabilitado "
            "(SUPERVISORES_MACRO_EMAIL_ENABLED / SUPERVISORES_FILA_EMAIL_ENABLED / TEAMS)"
        )
        return
    if not graph_mail_ok() and macro_on:
        logger.warning("supervisores - agendador ativo, mas MS_GRAPH_* ausente")

    poll = max(15, env_int("SUPERVISORES_MACRO_POLL_SECONDS", 60))

    def loop():
        time.sleep(35)
        from core.reports.fila_sem_analista import carregar_contagem_avisos

        estado_macro: dict = {}
        estado_fust: dict = {}
        estado_fila: dict = {"contagem": carregar_contagem_avisos()}
        while True:
            try:
                now_sp = datetime.now(TZ_SP)
                with app.app_context():
                    from core.reports.send_reports import enviar_fust, enviar_macro

                    if macro_on:
                        executar_tick(
                            "MACRO",
                            now_sp,
                            estado_macro,
                            lambda: enviar_macro(tipo="periodico"),
                            lambda: enviar_macro(tipo="final"),
                        )
                    if fust_on:
                        executar_tick(
                            "FUST",
                            now_sp,
                            estado_fust,
                            lambda: enviar_fust(tipo="periodico"),
                            lambda: enviar_fust(tipo="final"),
                        )
                    if fila_on:
                        tick_fila(now_sp, estado_fila)
            except Exception:
                logger.exception("supervisores - erro no agendador")
            time.sleep(poll)

    t = threading.Thread(target=loop, name="supervisores_relatorios", daemon=True)
    t.start()
    logger.info(
        "supervisores - agendador ativo (poll %ss, macro=%s, fust=%s, fila=%s)",
        poll,
        macro_on,
        fust_on,
        fila_on,
    )
