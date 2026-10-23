"""
BaseRepository - Classe base para todos os repositories
Implementa operações CRUD padrão e gerenciamento de conexão

NOTA: Esta é a versão NOVA do BaseRepository.
A versão antiga está em core/database/repository.py e será gradualmente substituída.
"""

from typing import List, Dict, Any, Optional, Union
from abc import ABC
from core.repository.RConnection import openConnection
from core.repository.exceptions import ConnectionError, NotFoundError, QueryError


class BaseRepository(ABC):
    """
    Classe base para repositories seguindo SOLID
    
    Responsabilidade única: Acesso a dados (SQL)
    """
    
    def __init__(self, database: Union[str, Any]):
        """
        Args:
            database: Nome do banco de dados ou objeto de conexão
        """
        self.database = database
        # Compatibilidade com código antigo que passa conexão direta
        self.connection = database if hasattr(database, 'cursor') else None
    
    def _sanitize(self, value: Any) -> Any:
        """
        Sanitiza valores para prevenir SQL injection e normalizar dados
        
        Args:
            value: Valor a ser sanitizado
            
        Returns:
            Valor sanitizado ou None
        """
        if value is None or value == '':
            return None
        
        if isinstance(value, str):
            value = value.strip()
            if value.lower() in ('null', 'none', ''):
                return None
        
        return value
    
    def fetch_all(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Executa query e retorna todos os resultados
        
        Args:
            query: SQL query
            params: Parâmetros da query (opcional)
            
        Returns:
            Lista de dicionários com os resultados
        """
        if self.connection:
            try:
                if params is None:
                    return self.connection.get_all(query)
                return self.connection.get_all(query, params)
            except Exception as e:
                raise QueryError(str(e))

        db = openConnection(self.database)
        if isinstance(db, dict):
            raise ConnectionError("connection_error")
        with db as conn:
            try:
                if params is None:
                    return conn.get_all(query)
                return conn.get_all(query, params)
            except Exception as e:
                raise QueryError(str(e))
    
    def fetch_one(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """
        Executa query e retorna um único resultado
        
        Args:
            query: SQL query
            params: Parâmetros da query (opcional)
            
        Returns:
            Dicionário com o resultado ou None
            
        Raises:
            NotFoundError: Se nenhum resultado for encontrado
        """
        def _execute_fetch_one(conn_obj):
            value = params if params is not None else ()
            row = conn_obj.get_one(query, value)
            if not row:
                raise NotFoundError("not_found")
            return row

        if self.connection:
            try:
                return _execute_fetch_one(self.connection)
            except NotFoundError:
                raise
            except Exception as e:
                raise QueryError(str(e))

        db = openConnection(self.database)
        if isinstance(db, dict):
            raise ConnectionError("connection_error")
        with db as conn:
            try:
                return _execute_fetch_one(conn)
            except NotFoundError:
                raise
            except Exception as e:
                raise QueryError(str(e))
    
    def execute(self, query: str, params: Optional[tuple] = None) -> int:
        """
        Executa query de modificação (UPDATE, DELETE)
        
        Args:
            query: SQL query
            params: Parâmetros da query (opcional)
            
        Returns:
            Número de linhas afetadas
        """
        if self.connection:
            try:
                return self.connection.update(query, params or ())
            except Exception as e:
                raise QueryError(str(e))

        db = openConnection(self.database)
        if isinstance(db, dict):
            raise ConnectionError("connection_error")
        with db as conn:
            try:
                return conn.update(query, params or ())
            except Exception as e:
                raise QueryError(str(e))
    
    def insert(self, query: str, params: Optional[tuple] = None) -> int:
        """
        Executa query de inserção (INSERT)
        
        Args:
            query: SQL query
            params: Parâmetros da query (opcional)
            
        Returns:
            ID do último registro inserido
        """
        if self.connection:
            try:
                return self.connection.insert(query, params or ())
            except Exception as e:
                raise QueryError(str(e))

        db = openConnection(self.database)
        if isinstance(db, dict):
            raise ConnectionError("connection_error")
        with db as conn:
            try:
                return conn.insert(query, params or ())
            except Exception as e:
                raise QueryError(str(e))
    
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """
        Executa múltiplas queries em batch
        
        Args:
            query: SQL query
            params_list: Lista de tuplas com parâmetros
            
        Returns:
            Número de linhas afetadas
        """
        if self.connection:
            try:
                affected = 0
                for params in params_list:
                    affected += self.connection.update(query, params)
                return affected
            except Exception as e:
                raise QueryError(str(e))

        db = openConnection(self.database)
        if isinstance(db, dict):
            raise ConnectionError("connection_error")
        with db as conn:
            try:
                affected = 0
                for params in params_list:
                    affected += conn.update(query, params)
                return affected
            except Exception as e:
                raise QueryError(str(e))
    
    def get_by_id(self, table: str, id_value: int, tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Busca registro por ID com suporte a multitenancy
        
        Args:
            table: Nome da tabela
            id_value: Valor do ID
            tenant_id: ID do tenant (opcional, para multitenancy)
            
        Returns:
            Dicionário com o registro ou None
        """
        if tenant_id is not None:
            query = f"SELECT * FROM {table} WHERE id = %s AND tenant_id = %s"
            return self.fetch_one(query, (id_value, tenant_id))
        else:
            query = f"SELECT * FROM {table} WHERE id = %s"
            return self.fetch_one(query, (id_value,))
    
    def get_all_by_tenant(self, table: str, tenant_id: int) -> List[Dict[str, Any]]:
        """
        Busca todos os registros de um tenant
        
        Args:
            table: Nome da tabela
            tenant_id: ID do tenant
            
        Returns:
            Lista de dicionários com os registros
        """
        query = f"SELECT * FROM {table} WHERE tenant_id = %s"
        return self.fetch_all(query, (tenant_id,))
