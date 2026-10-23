"""core.database.connection

Wrapper de baixo nível sobre mysql.connector.
Gerencia ciclo de vida da conexão (cursor, auto-commit, rollback e fechamento seguro)
como context manager.

Uso:
    from core.database.connection import DB_REQUEST

    config = {"host": ..., "user": ..., "password": ..., "database": ...}
    with DB_REQUEST(config) as db:
        rows = db.get_all("SELECT * FROM tabela")
"""
from mysql.connector import connect

class DB_REQUEST:
    """Context manager para conexão MySQL via mysql.connector.

    Atributos:
        conn: Objeto de conexão mysql.connector.
        cursor: Cursor dictionary (retorna dicts em vez de tuplas).
        auto_commit (bool): Se True, confirma automaticamente após insert/update.
            Defina False para controle explícito de transação.
    """

    def __init__(self, config):
        """Abre conexão e cursor a partir do dicionário de configuração.

        Args:
            config (dict): Parâmetros aceitos por mysql.connector.connect
                           (host, user, password, database, port, etc.).
        """
        self.conn = connect(**config)
        self.cursor = self.conn.cursor(dictionary=True)
        self.auto_commit = True  # Default to True for backward compatibility

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc:
                try:
                    self.conn.rollback()
                except (AttributeError, Exception):
                    # Ignora erro se a conexão já estiver fechada ou inválida durante rollback de erro
                    pass
            # Note: We do NOT commit here. Explicit commit is required if auto_commit is False.
        finally:
            self.close()

    def get_all(self, query, id=None):
        """Executa SELECT e retorna todos os resultados como lista de dicts.

        Args:
            query (str): Query SQL com placeholders %s.
            id: Valor único ou lista/tupla de parâmetros (opcional).

        Returns:
            list[dict]: Linhas retornadas pelo banco.
        """
        if id is not None:
            params = id if isinstance(id, (list, tuple)) else (id,)
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        return self.cursor.fetchall()

    def get_one(self, query, value=None):
        """Executa SELECT e retorna a primeira linha como dict.

        Args:
            query (str): Query SQL com placeholders %s.
            value: Parâmetro único ou lista/tupla (opcional).

        Returns:
            dict | None: Primeira linha ou None se não encontrado.
        """
        if value is not None:
            params = value if isinstance(value, (list, tuple)) else (value,)
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        return self.cursor.fetchone()

    def insert(self, query, values=None):
        """Executa INSERT e retorna o ID gerado.

        Args:
            query (str): Query INSERT com placeholders %s.
            values: Parâmetros da query (opcional).

        Returns:
            int: `lastrowid` do registro inserido.
        """
        if values is not None:
            params = values if isinstance(values, (list, tuple)) else (values,)
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        if self.auto_commit:
            self.conn.commit()
        return self.cursor.lastrowid

    def post(self, obj):
        """Executa INSERT a partir de um objeto com atributos `query` e `values`.

        Args:
            obj: Objeto com atributos `query` (str) e `values` (iterável).

        Returns:
            int: `lastrowid` do registro inserido.
        """
        self.cursor.execute(obj.query, tuple(obj.values))
        if self.auto_commit:
            self.conn.commit()
        return self.cursor.lastrowid

    def update(self, query, values=None):
        """Executa UPDATE ou DELETE e retorna o número de linhas afetadas.

        Args:
            query (str): Query SQL com placeholders %s.
            values: Parâmetros da query (opcional).

        Returns:
            int: `rowcount` (linhas afetadas).
        """
        if values is not None:
            params = values if isinstance(values, (list, tuple)) else (values,)
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        if self.auto_commit:
            self.conn.commit()
        return self.cursor.rowcount

    def commit(self):
        """Confirma a transação atual explicitamente."""
        self.conn.commit()

    def rollback(self):
        """Desfaz a transação atual. Retorna True mesmo em caso de falha silenciosa."""
        try:
            self.conn.rollback()
        except (AttributeError, Exception):
            pass
        return True

    def close(self):
        """Fecha cursor e conexão de forma segura, ignorando erros de fechamento."""
        
        try:
            if hasattr(self, 'cursor') and self.cursor:
                self.cursor.close()
        except Exception:
            pass
        finally:
            try:
                if hasattr(self, 'conn') and self.conn:
                    self.conn.close()
            except Exception:
                pass
