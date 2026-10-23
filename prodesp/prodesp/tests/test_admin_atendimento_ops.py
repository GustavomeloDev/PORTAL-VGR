"""Testes — exclusão admin de atendimento e remoção de agendamento."""
from __future__ import annotations

from datetime import date, time
from unittest.mock import MagicMock, patch

from prodesp.prodesp.admin_atendimento_ops import (
    AdminAtendimentoOpsError,
    MSG_AGENDAMENTO_REMOVIDO,
    MSG_ATENDIMENTO_REMOVIDO,
    _format_agendamento_label,
    _format_atendimento_label,
    admin_excluir_atendimento,
    admin_remover_agendamento,
)


def test_format_agendamento_label():
    assert _format_agendamento_label(date(2026, 7, 3), time(10, 30)) == "2026-07-03 10:30:00"
    assert _format_agendamento_label(None, None) == "—"


def test_admin_excluir_atendimento_nao_encontrado():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn = MagicMock()
    try:
        admin_excluir_atendimento(conn, cursor, 999)
        assert False, "expected error"
    except AdminAtendimentoOpsError as e:
        assert e.status == 404


@patch("prodesp.prodesp.historico.registrar_log")
def test_admin_excluir_atendimento_ordem_delete(mock_log):
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "id_atendimentos": 2316,
        "id_unidades_atendimentos": 100,
        "data_atendimentos": date(2026, 7, 3),
        "status_atendimentos": "Em Atendimento",
        "substatus_atendimentos": "Aguardando Config. Remota",
    }
    conn = MagicMock()
    cur2 = MagicMock()
    conn.cursor.return_value = cur2

    result = admin_excluir_atendimento(conn, cursor, 2316)

    assert result == {"id_atendimento": 2316, "id_unidade": 100}
    mock_log.assert_called_once_with(
        conn,
        "unidades",
        100,
        "Atendimento",
        _format_atendimento_label(cursor.fetchone.return_value),
        MSG_ATENDIMENTO_REMOVIDO,
        "DELETE",
    )
    sqls = [call.args[0] for call in cur2.execute.call_args_list]
    assert "DELETE FROM atendimentos_status_log" in sqls[0]
    assert "DELETE FROM observacoes" in sqls[1]
    assert "DELETE FROM atendimentos_fora_padrao" in sqls[2]
    assert "DELETE FROM historico" in sqls[3]
    assert "DELETE FROM atendimentos" in sqls[4]


@patch("prodesp.prodesp.historico.registrar_log")
def test_admin_remover_agendamento_sem_agenda(mock_log):
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "id_unidades": 50,
        "id_vgr_unidades": "123",
        "data_agendamento_unidades": None,
        "hora_agendamento_unidades": None,
    }
    conn = MagicMock()
    try:
        admin_remover_agendamento(conn, cursor, id_vgr="123")
        assert False, "expected error"
    except AdminAtendimentoOpsError as e:
        assert e.status == 400
    mock_log.assert_not_called()


@patch("prodesp.prodesp.historico.registrar_log")
def test_admin_remover_agendamento_com_atendimento_na_data(mock_log):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {
            "id_unidades": 50,
            "id_vgr_unidades": "123",
            "data_agendamento_unidades": date(2026, 7, 3),
            "hora_agendamento_unidades": time(9, 0),
        },
        {"id_atendimentos": 10},
    ]
    conn = MagicMock()
    try:
        admin_remover_agendamento(conn, cursor, id_vgr="123")
        assert False, "expected error"
    except AdminAtendimentoOpsError as e:
        assert e.status == 409
    mock_log.assert_not_called()


@patch("prodesp.prodesp.historico.registrar_log")
def test_admin_remover_agendamento_ok(mock_log):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {
            "id_unidades": 50,
            "id_vgr_unidades": "123",
            "data_agendamento_unidades": date(2026, 7, 3),
            "hora_agendamento_unidades": time(9, 0),
        },
        None,
    ]
    conn = MagicMock()
    cur2 = MagicMock()
    conn.cursor.return_value = cur2

    result = admin_remover_agendamento(conn, cursor, id_vgr="123")

    assert result == {"id_unidade": 50, "id_vgr": "123"}
    assert mock_log.call_count == 3
    cur2.execute.assert_called_once()
    assert "UPDATE unidades" in cur2.execute.call_args.args[0]
