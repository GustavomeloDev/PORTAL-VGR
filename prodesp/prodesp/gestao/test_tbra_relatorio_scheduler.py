"""Testes — agendador relatório Time TBRA."""
from __future__ import annotations

from datetime import datetime

import pytz

from prodesp.prodesp.gestao.gestao_relatorio_email import colunas_relatorio
from prodesp.prodesp.gestao.tbra_relatorio_scheduler import (
    dentro_janela_report_final_tbra,
    hora_fim_periodico_tbra,
    horarios_tbra_from_env,
    slot_relatorio_tbra,
)

TZ = pytz.timezone("America/Sao_Paulo")


def _dt(h: int, m: int = 0) -> datetime:
    return TZ.localize(datetime(2026, 7, 3, h, m, 0))


def test_horarios_tbra_default(monkeypatch):
    monkeypatch.delenv("PRODESP_TIME_TBRA_RELATORIO_HORARIOS", raising=False)
    assert horarios_tbra_from_env() == (11, 15, 18, 22)


def test_horarios_tbra_custom(monkeypatch):
    monkeypatch.setenv("PRODESP_TIME_TBRA_RELATORIO_HORARIOS", "11; 15,18,22")
    assert horarios_tbra_from_env() == (11, 15, 18, 22)


def test_slot_relatorio_tbra():
    horarios = (11, 15, 18, 22)
    assert slot_relatorio_tbra(_dt(11, 5), horarios) == "2026-07-03 11"
    assert slot_relatorio_tbra(_dt(15, 59), horarios) == "2026-07-03 15"
    assert slot_relatorio_tbra(_dt(10, 30), horarios) is None
    assert slot_relatorio_tbra(_dt(22, 0), horarios) == "2026-07-03 22"


def test_colunas_relatorio_tbra_sem_noc_e_tempo():
    cols = colunas_relatorio("tbra")
    assert "Tck NOC" not in cols
    assert "Tempo de Vita" not in cols
    assert "Tempo do Atendimento" not in cols
    assert "Início da Atividade" not in cols
    assert "Horário Finalização" not in cols
    assert "ID VGR" in cols
    assert "Contratada" in cols
    assert "Observações" in cols


def test_hora_fim_periodico_tbra():
    assert hora_fim_periodico_tbra((11, 15, 18, 22)) == 22
    assert hora_fim_periodico_tbra((11, 15)) == 15


def test_janela_report_final_tbra(monkeypatch):
    monkeypatch.setenv("PRODESP_TIME_TBRA_RELATORIO_FINAL_ENABLED", "true")
    monkeypatch.setenv("PRODESP_TIME_TBRA_RELATORIO_HORA_LIMITE_FINAL", "23")
    horarios = (11, 15, 18, 22)

    assert dentro_janela_report_final_tbra(_dt(22, 0), horarios) is False
    assert dentro_janela_report_final_tbra(_dt(22, 1), horarios) is True
    assert dentro_janela_report_final_tbra(_dt(23, 30), horarios) is True
    assert dentro_janela_report_final_tbra(_dt(18, 30), horarios) is False


def test_janela_report_final_tbra_desabilitado(monkeypatch):
    monkeypatch.setenv("PRODESP_TIME_TBRA_RELATORIO_FINAL_ENABLED", "false")
    assert dentro_janela_report_final_tbra(_dt(22, 30), (11, 22)) is False


def test_enviar_tbra_aceita_tipo_final():
    import inspect

    from prodesp.prodesp.gestao.tbra_relatorio_email import enviar_relatorio_tbra_periodo

    sig = inspect.signature(enviar_relatorio_tbra_periodo)
    assert "tipo_relatorio" in sig.parameters
