"""
Testes para BaseRepository
Valida compatibilidade e funcionalidade básica
"""

import pytest
from unittest.mock import Mock, MagicMock
from core.base.repository import BaseRepository


class TestRepository(BaseRepository):
    """Repository de teste para validar BaseRepository"""
    pass


def test_init_with_database_name():
    """Testa inicialização com nome do banco"""
    repo = TestRepository('test_db')
    assert repo.database == 'test_db'
    assert repo.connection is None


def test_init_with_connection_object():
    """Testa inicialização com objeto de conexão"""
    mock_conn = Mock()
    mock_conn.cursor = Mock()
    
    repo = TestRepository(mock_conn)
    assert repo.database == mock_conn
    assert repo.connection == mock_conn


def test_sanitize_none():
    """Testa sanitização de valores None"""
    repo = TestRepository('test_db')
    assert repo._sanitize(None) is None
    assert repo._sanitize('') is None
    assert repo._sanitize('null') is None
    assert repo._sanitize('none') is None
    assert repo._sanitize('NULL') is None


def test_sanitize_string():
    """Testa sanitização de strings"""
    repo = TestRepository('test_db')
    assert repo._sanitize('  test  ') == 'test'
    assert repo._sanitize('Test') == 'Test'


def test_sanitize_non_string():
    """Testa sanitização de valores não-string"""
    repo = TestRepository('test_db')
    assert repo._sanitize(123) == 123
    assert repo._sanitize(True) is True


def test_fetch_all_with_connection():
    """Testa fetch_all com conexão direta"""
    mock_conn = Mock()
    mock_conn.cursor = Mock()
    mock_conn.get_all = Mock(return_value=[{'id': 1}, {'id': 2}])
    
    repo = TestRepository(mock_conn)
    result = repo.fetch_all("SELECT * FROM test")
    
    assert len(result) == 2
    assert result[0]['id'] == 1
    mock_conn.get_all.assert_called_once_with("SELECT * FROM test")


def test_fetch_all_with_params():
    """Testa fetch_all com parâmetros"""
    mock_conn = Mock()
    mock_conn.cursor = Mock()
    mock_conn.get_all = Mock(return_value=[{'id': 1}])
    
    repo = TestRepository(mock_conn)
    result = repo.fetch_all("SELECT * FROM test WHERE id = %s", (1,))
    
    assert len(result) == 1
    mock_conn.get_all.assert_called_once_with("SELECT * FROM test WHERE id = %s", (1,))


def test_fetch_one_with_connection():
    """Testa fetch_one com conexão direta"""
    mock_conn = Mock()
    mock_conn.cursor = Mock()
    mock_conn.get_one = Mock(return_value={'id': 1, 'name': 'Test'})
    
    repo = TestRepository(mock_conn)
    result = repo.fetch_one("SELECT * FROM test WHERE id = %s", (1,))
    
    assert result['id'] == 1
    assert result['name'] == 'Test'


def test_execute_with_connection():
    """Testa execute com conexão direta"""
    mock_conn = Mock()
    mock_conn.cursor = Mock()
    mock_conn.update = Mock(return_value=1)
    
    repo = TestRepository(mock_conn)
    affected = repo.execute("UPDATE test SET name = %s WHERE id = %s", ('New Name', 1))
    
    assert affected == 1
    mock_conn.update.assert_called_once()


def test_insert_with_connection():
    """Testa insert com conexão direta"""
    mock_conn = Mock()
    mock_conn.cursor = Mock()
    mock_conn.insert = Mock(return_value=5)
    
    repo = TestRepository(mock_conn)
    last_id = repo.insert("INSERT INTO test (name) VALUES (%s)", ('Test',))
    
    assert last_id == 5
    mock_conn.insert.assert_called_once()


def test_execute_many():
    """Testa execute_many"""
    mock_conn = Mock()
    mock_conn.cursor = Mock()
    mock_conn.update = Mock(return_value=1)
    
    repo = TestRepository(mock_conn)
    params_list = [('Name1', 1), ('Name2', 2), ('Name3', 3)]
    affected = repo.execute_many("UPDATE test SET name = %s WHERE id = %s", params_list)
    
    assert affected == 3
    assert mock_conn.update.call_count == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
