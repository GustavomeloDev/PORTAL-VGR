"""Testes — Report Final e janelas do agendador de relatório gestão."""
from __future__ import annotations

from datetime import datetime

import pytz

from prodesp.prodesp.gestao.gestao_relatorio_email import (
    calcular_kpis_gestao,
    count_atendimentos_ativos,
    elegivel_report_final,
)
from prodesp.prodesp.gestao.gestao_relatorio_scheduler import (
    dia_util,
    dentro_janela_envio,
    dentro_janela_report_final,
    slot_relatorio_gestao,
)

TZ = pytz.timezone("America/Sao_Paulo")


def _dt(h: int, m: int = 0, day: int = 10) -> datetime:
    return TZ.localize(datetime(2026, 6, day, h, m, 0))


def test_count_atendimentos_ativos():
    rows = [
        {"id_atendimento": None, "status_atendimentos": "Agendado"},
        {"id_atendimento": 1, "status_atendimentos": "Em Atendimento"},
        {"id_atendimento": 2, "status_atendimentos": "Concluído Parcial"},
        {"id_atendimento": 3, "status_atendimentos": "Concluído", "substatus_atendimentos": "Concluído"},
    ]
    assert count_atendimentos_ativos(rows) == 1


def test_elegivel_report_final():
    aberto = [
        {"id_atendimento": 1, "status_atendimentos": "Em Atendimento"},
        {"id_atendimento": 2, "status_atendimentos": "Concluído", "substatus_atendimentos": "Concluído"},
    ]
    assert elegivel_report_final(aberto) is False

    encerrado = [
        {"id_atendimento": 1, "status_atendimentos": "Concluído", "substatus_atendimentos": "Concluído"},
        {"id_atendimento": 2, "status_atendimentos": "Quebra"},
    ]
    assert elegivel_report_final(encerrado) is True

    so_agendado = [{"id_atendimento": None, "status_atendimentos": "Agendado"}]
    assert elegivel_report_final(so_agendado) is False


def test_elegivel_report_final_parcial_e_finalizado():
    """Concluído Parcial não bloqueia Report Final (é atendimento finalizado)."""
    rows = [
        {"id_atendimento": 1, "status_atendimentos": "Concluído Parcial"},
        {"id_atendimento": 2, "status_atendimentos": "Concluído", "substatus_atendimentos": "Concluído"},
    ]
    assert elegivel_report_final(rows) is True
    assert count_atendimentos_ativos(rows) == 0


def test_janela_periodica_com_hora_fim_16(monkeypatch):
    monkeypatch.setenv("PRODESP_GESTAO_RELATORIO_HORA_INICIO", "10")
    monkeypatch.setenv("PRODESP_GESTAO_RELATORIO_HORA_FIM", "16")

    assert dentro_janela_envio(_dt(10, 0)) is True
    assert dentro_janela_envio(_dt(15, 30)) is True
    assert dentro_janela_envio(_dt(16, 0)) is True
    assert dentro_janela_envio(_dt(16, 15)) is False
    assert dentro_janela_envio(_dt(17, 30)) is False


def test_janela_report_final_apos_hora_fim(monkeypatch):
    monkeypatch.setenv("PRODESP_GESTAO_RELATORIO_HORA_FIM", "16")
    monkeypatch.setenv("PRODESP_GESTAO_RELATORIO_HORA_LIMITE_FINAL", "23")
    monkeypatch.setenv("PRODESP_GESTAO_RELATORIO_FINAL_ENABLED", "true")

    assert dentro_janela_report_final(_dt(16, 0)) is False
    assert dentro_janela_report_final(_dt(16, 1)) is True
    assert dentro_janela_report_final(_dt(22, 0)) is True
    assert dentro_janela_report_final(_dt(23, 30)) is True
    assert dentro_janela_report_final(_dt(15, 59)) is False


def test_report_final_desabilitado(monkeypatch):
    monkeypatch.setenv("PRODESP_GESTAO_RELATORIO_HORA_FIM", "16")
    monkeypatch.setenv("PRODESP_GESTAO_RELATORIO_FINAL_ENABLED", "false")

    assert dentro_janela_report_final(_dt(22, 0)) is False


def test_relatorio_sem_conteudo():
    from prodesp.prodesp.gestao.gestao_relatorio_email import (
        GestaoKpiResumo,
        deve_omitir_relatorio_periodico_vazio,
        relatorio_gestao_sem_conteudo,
    )

    vazio = GestaoKpiResumo()
    assert relatorio_gestao_sem_conteudo(vazio) is True

    so_agendado = GestaoKpiResumo(agendados=3, total=3)
    assert relatorio_gestao_sem_conteudo(so_agendado) is False

    com_atividade = GestaoKpiResumo(com_atividade=1, total=1)
    assert relatorio_gestao_sem_conteudo(com_atividade) is False


def test_omitir_periodico_vazio(monkeypatch):
    from prodesp.prodesp.gestao.gestao_relatorio_email import (
        GestaoKpiResumo,
        deve_omitir_relatorio_periodico_vazio,
    )

    vazio = GestaoKpiResumo()
    monkeypatch.setenv("PRODESP_GESTAO_RELATORIO_SKIP_VAZIO", "true")
    assert deve_omitir_relatorio_periodico_vazio(vazio, tipo_relatorio="periodico") is True
    assert deve_omitir_relatorio_periodico_vazio(vazio, tipo_relatorio="final") is False

    monkeypatch.setenv("PRODESP_GESTAO_RELATORIO_SKIP_VAZIO", "false")
    assert deve_omitir_relatorio_periodico_vazio(vazio, tipo_relatorio="periodico") is False


def test_omitir_periodico_dia_encerrado():
    from prodesp.prodesp.gestao.gestao_relatorio_email import (
        deve_omitir_periodico_dia_encerrado,
    )

    encerrado = [
        {"id_atendimento": 1, "status_atendimentos": "Concluído", "substatus_atendimentos": "Concluído"},
        {"id_atendimento": 2, "status_atendimentos": "Quebra"},
    ]
    assert deve_omitir_periodico_dia_encerrado(encerrado, tipo_relatorio="periodico") is True
    assert deve_omitir_periodico_dia_encerrado(encerrado, tipo_relatorio="final") is False

    aberto = [
        {"id_atendimento": 1, "status_atendimentos": "Em Atendimento"},
        {"id_atendimento": 2, "status_atendimentos": "Concluído", "substatus_atendimentos": "Concluído"},
    ]
    assert deve_omitir_periodico_dia_encerrado(aberto, tipo_relatorio="periodico") is False


def test_resultado_omitido_dia_encerrado():
    from prodesp.prodesp.gestao.gestao_relatorio_email import ResultadoEnvioRelatorioGestao

    r = ResultadoEnvioRelatorioGestao.omitido_encerrado()
    assert r.omitido_dia_encerrado is True
    assert r.enviado is False
    assert r.slot_concluido is True
    assert r.omitido_sem_conteudo is False


def test_dia_util_e_slot():
    assert dia_util(_dt(10, 0, day=8)) is True
    assert dia_util(_dt(10, 0, day=13)) is False
    assert slot_relatorio_gestao(_dt(10, 15)) == "2026-06-10 10:00"
    assert slot_relatorio_gestao(_dt(10, 45)) == "2026-06-10 10:30"


def test_kpi_em_atendimento_alinhado_a_ativos():
    rows = [
        {"id_atendimento": 1, "status_atendimentos": "Em Atendimento", "substatus_atendimentos": "Triagem"},
        {"id_atendimento": 2, "status_atendimentos": "Concluído Parcial"},
    ]
    kpi = calcular_kpis_gestao(rows)
    assert kpi.em_atendimento == 1
    assert kpi.parcial == 1
    assert count_atendimentos_ativos(rows) == 1
