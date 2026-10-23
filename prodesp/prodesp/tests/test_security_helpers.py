"""Testes SEC-005 (concluídos) e helpers de segurança PRODESP."""

from unittest.mock import MagicMock, patch

import pytest

from prodesp.app import (
    _prodesp_is_admin,
    _prodesp_json_error,
    _prodesp_resposta_leitura_concluido,
    _prodesp_status_concluido,
)


def test_status_concluido_variacoes():
    assert _prodesp_status_concluido("Concluído") is True
    assert _prodesp_status_concluido("concluido") is True
    assert _prodesp_status_concluido(" CONCLUÍDO ") is True
    assert _prodesp_status_concluido("Em Atendimento") is False
    assert _prodesp_status_concluido("") is False
    assert _prodesp_status_concluido(None) is False


def test_is_admin():
    assert _prodesp_is_admin(MagicMock(admin_user=1)) is True
    assert _prodesp_is_admin(MagicMock(admin_user=0)) is False
    assert _prodesp_is_admin(MagicMock(admin_user="1")) is True


@patch("prodesp.app.get_db_connection")
def test_concluido_bloqueia_nao_admin(mock_conn, app_ctx):
    cursor = MagicMock()
    cursor.fetchone.return_value = ("Concluído",)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_conn.return_value = conn

    user = MagicMock(admin_user=0)
    result = _prodesp_resposta_leitura_concluido(42, user)
    assert result is not None
    resp, status = result
    data = resp.get_json()
    assert status == 404
    assert data["success"] is False
    assert "disponível" in data["message"].lower()


@patch("prodesp.app.get_db_connection")
def test_concluido_admin_liberado(mock_conn):
    user = MagicMock(admin_user=1)
    assert _prodesp_resposta_leitura_concluido(42, user) is None
    mock_conn.assert_not_called()


@patch("prodesp.app.get_db_connection")
def test_concluido_em_atendimento_liberado(mock_conn):
    cursor = MagicMock()
    cursor.fetchone.return_value = ("Em Atendimento",)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_conn.return_value = conn

    user = MagicMock(admin_user=0)
    assert _prodesp_resposta_leitura_concluido(7, user) is None


@patch("prodesp.app.get_db_connection")
def test_concluido_inexistente_404(mock_conn, app_ctx):
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_conn.return_value = conn

    user = MagicMock(admin_user=0)
    result = _prodesp_resposta_leitura_concluido(999, user)
    resp, status = result
    assert status == 404
    assert "não encontrado" in resp.get_json()["message"].lower()


class _FakeLog:
    def warning(self, *_a, **_k):
        pass

    def exception(self, *_a, **_k):
        pass


def test_prodesp_json_error_nao_vaza_mysql(app_ctx):
    class FakeMysqlError(Exception):
        pass

    exc = FakeMysqlError("1146 Table 'secret_db.users' doesn't exist")
    resp, status = _prodesp_json_error(exc, log=_FakeLog(), action="test")
    data = resp.get_json()
    assert status == 500
    assert data["success"] is False
    assert "secret_db" not in data.get("message", "")
    assert "1146" not in data.get("message", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
