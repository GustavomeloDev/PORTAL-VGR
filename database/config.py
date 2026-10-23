from dotenv import load_dotenv
import os

load_dotenv()

def DB_CONFIG(database, *, use_pool=False):
    port = os.getenv('PORT') or os.getenv('MYSQL_PORT')
    ssl_ca = os.getenv('MYSQL_SSL_CA')
    timeout = int(os.getenv('MYSQL_CONN_TIMEOUT') or '10')
    host = os.getenv('HOST') or os.getenv('MYSQL_HOST')
    user = os.getenv('USER') or os.getenv('MYSQL_USER')
    password = os.getenv('PASS') or os.getenv('MYSQL_PASSWORD')
    db_config = {
        "host": host,
        "user": user,
        "password": password,
        "port": int(port) if port else 3306,
        "connection_timeout": timeout,
    }
    if use_pool:
        db_config["pool_name"] = os.getenv('MYSQL_POOL_NAME') or 'vita_pool'
        db_config["pool_size"] = int(os.getenv('MYSQL_POOL_SIZE') or '5')
    if database:
        db_config["database"] = database
    if ssl_ca:
        db_config["ssl_ca"] = ssl_ca
    return db_config


def module_db_config(database: str, *, use_pool: bool = False) -> dict:
    """Atalho login/prodesp: credenciais do .env; pool desligado por padrão (open/close por request)."""
    return DB_CONFIG(database, use_pool=use_pool)
