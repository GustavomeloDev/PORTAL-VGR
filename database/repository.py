from abc import ABC
from typing import Any, Dict, Iterable, List, Optional, Union
from core.repository.exceptions import ConnectionError, NotFoundError, QueryError
from core.repository.RConnection import openConnection


class BaseRepository(ABC):
    def __init__(self, database: Union[str, Any]):
        # database param can be a string (db name) or a DB_REQUEST object (connection)
        self.database = database
        # If the passed object has a cursor, we assume it's an open connection (DB_REQUEST)
        self.connection = database if hasattr(database, 'cursor') else None


    def fetch_all(self, query: str, params: Optional[Iterable[Any]] = None) -> List[Dict[str, Any]]:
        """
        Executa uma query SELECT e retorna todas as linhas encontradas.
        
        Args:
            query (str): A string SQL a ser executada.
            params (tuple/list, optional): Parâmetros para binding na query.

        Returns:
            List[Dict[str, Any]]: Lista de dicionários representando as linhas.
        """
        if self.connection:
            try:
                if params is None:
                    return self.connection.get_all(query)
                return self.connection.get_all(query, params)
            except Exception as e:
                raise QueryError(str(e))

        from core.repository.RConnection import openConnection
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

    def fetch_one(self, query: str, params: Optional[Iterable[Any]] = None) -> Dict[str, Any]:
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

    def execute(self, query: str, params: Optional[Iterable[Any]] = None) -> int:
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

    def insert(self, query: str, params: Optional[Iterable[Any]] = None) -> int:
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
