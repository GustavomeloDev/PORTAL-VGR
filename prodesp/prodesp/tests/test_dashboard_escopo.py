"""Testes: total do período e timeline (Agendado vs Fora Escopo)."""
from __future__ import annotations

from prodesp.prodesp.gestao.dashboard_escopo import (
    detalhar_total_periodo,
    format_hint_total_periodo,
    timeline_series,
)


def test_detalhar_total_periodo_exemplo_21():
    start, end = "2026-08-03", "2026-08-03"
    rows = [
        # 5 pendentes (só agenda no dia)
        *[{"id_atendimento": None, "data_agendamento": start, "status_atendimentos": "Agendado"} for _ in range(5)],
        # 12 finalizados com agenda no dia
        *[
            {
                "id_atendimento": i,
                "data_agendamento": start,
                "data_atendimentos": start,
                "status_atendimentos": "Concluído",
                "substatus_atendimentos": "Concluído",
            }
            for i in range(1, 13)
        ],
        # 2 ativos com agenda no dia
        {
            "id_atendimento": 100,
            "data_agendamento": start,
            "data_atendimentos": start,
            "status_atendimentos": "Em Atendimento",
        },
        {
            "id_atendimento": 101,
            "data_agendamento": start,
            "data_atendimentos": start,
            "status_atendimentos": "Em Atendimento",
        },
        # 1 fora escopo finalizado (agenda outro dia)
        {
            "id_atendimento": 200,
            "data_agendamento": "2026-07-30",
            "data_atendimentos": start,
            "status_atendimentos": "Concluído",
            "substatus_atendimentos": "Concluído",
        },
        # 1 fora escopo ativo
        {
            "id_atendimento": 201,
            "data_agendamento": "2026-07-31",
            "data_atendimentos": start,
            "status_atendimentos": "Em Atendimento",
        },
    ]
    det = detalhar_total_periodo(rows, start, end)
    assert det["agendados_pend"] == 5
    assert det["agendados_finalizados"] == 12
    assert det["agendados_ativos"] == 2
    assert det["fora_escopo_finalizados"] == 1
    assert det["fora_escopo_ativos"] == 1
    assert det["total"] == 21
    hint = format_hint_total_periodo(det)
    assert "5 Agendados Pend." in hint
    assert "1 Fora Escopo Ativo" in hint


def test_timeline_fora_escopo_no_dia_realizacao():
    start, end = "2026-08-03", "2026-08-03"
    rows = [
        {
            "id_unidades": 1,
            "id_atendimento": 1,
            "data_agendamento": "2026-07-30",
            "data_atendimentos": "2026-08-03",
            "status_atendimentos": "Concluído",
        },
        {
            "id_unidades": 2,
            "id_atendimento": 2,
            "data_agendamento": "2026-08-03",
            "data_atendimentos": "2026-08-03",
            "status_atendimentos": "Concluído",
        },
        {
            "id_unidades": 3,
            "id_atendimento": None,
            "data_agendamento": "2026-08-03",
            "status_atendimentos": "Agendado",
        },
    ]
    tl = timeline_series(rows, start, end)
    # agendas de 30/07 não entram no eixo (fora do filtro)
    assert "2026-07-30" not in tl["scheduled"]
    assert tl["scheduled"].get("2026-08-03") == 2  # unidades 2 e 3
    assert tl["realized"].get("2026-08-03") == 1  # só id 2 (mesmo dia)
    assert tl["fora_escopo"].get("2026-08-03") == 1  # id 1 no dia da atividade
    assert "2026-07-30" not in tl["fora_escopo"]
