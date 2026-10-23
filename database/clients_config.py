import os
from core.database.connection import DB_REQUEST
from core.database.repository import BaseRepository
from core.repository.table_repository import TableRepository
from typing import Optional, Iterable, Any, Dict, List

def CLIENTS_DB_CONFIG(database):
    """
    Configuração de conexão exclusiva para os módulos Agendamentos, Aprendizado e Documentação.
    Lê as configurações do ambiente (ou usa defaults seguros) para garantir isolamento.
    Permite fallback para as variáveis padrão (HOST, USER, PASS, PORT) se as variáveis CLIENT_* não estiverem definidas.
    """
    host = os.getenv('HOST')
    user = os.getenv('USER')
    password = os.getenv('PASS')
    port = os.getenv('PORT')

    # Allow overriding the database name via environment variable
    # e.g. CLIENT_DB_NAME or APRENDIZADO_DB_NAME
    # If not found, defaults to the 'database' argument passed to the function
    env_db_name = os.getenv('CLIENT_DB_NAME')
    
    # Check for specific database overrides (e.g., APRENDIZADO_DB_NAME or DATABASE_APRENDIZADO)
    specific_env_var = f"{database.upper()}_DB_NAME"
    alt_env_var = f"DATABASE_{database.upper()}"
    
    if os.getenv(specific_env_var):
        env_db_name = os.getenv(specific_env_var)
    elif os.getenv(alt_env_var):
        env_db_name = os.getenv(alt_env_var)
    
    final_db_name = env_db_name if env_db_name else database

    return {
        "host": host,
        "user": user,
        "password": password,
        "database": final_db_name,
        "port": port,
        "pool_name": f"{final_db_name}_pool",
        "pool_size": 5,
        "connection_timeout": 10
    }

def open_client_connection(database):
    """
    Abre uma conexão usando a configuração exclusiva de clientes.
    Substitui o uso de openConnection do core.repository.RConnection.
    """
    config = CLIENTS_DB_CONFIG(database)
    return DB_REQUEST(config)

class ClientBaseRepository(BaseRepository):
    """
    Repositório base para clientes que necessitam de conexão exclusiva (Agendamentos, etc.).
    Sobrescreve os métodos de acesso ao banco para utilizar open_client_connection.
    """
    
    def fetch_all(self, query: str, params: Optional[Iterable[Any]] = None) -> List[Dict[str, Any]]:
        if self.connection:
             return super().fetch_all(query, params)
        
        db = open_client_connection(self.database)
        with db as conn:
            return conn.get_all(query, params)

    def fetch_one(self, query: str, params: Optional[Iterable[Any]] = None) -> Optional[Dict[str, Any]]:
        if self.connection:
             return super().fetch_one(query, params)
             
        db = open_client_connection(self.database)
        with db as conn:
            return conn.get_one(query, params)
            
    def execute(self, query: str, params: Optional[Iterable[Any]] = None) -> int:
        if self.connection:
             return super().execute(query, params)
             
        db = open_client_connection(self.database)
        with db as conn:
            return conn.update(query, params)

    def insert(self, query: str, params: Optional[Iterable[Any]] = None) -> int:
        if self.connection:
             return super().insert(query, params)
             
        db = open_client_connection(self.database)
        with db as conn:
            return conn.insert(query, params)

class ClientTableRepository(ClientBaseRepository, TableRepository):
    """
    Extensão de TableRepository que utiliza a conexão exclusiva de clientes.
    """
    def __init__(self, database: str, table: str, id_field: str = "id"):
        # Inicializa via TableRepository, mas os métodos sobrescritos em ClientBaseRepository
        # terão precedência devido à ordem de herança (MRO).
        TableRepository.__init__(self, database, table, id_field)
