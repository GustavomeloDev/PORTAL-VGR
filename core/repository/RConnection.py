from core.database.config import DB_CONFIG
from core.database.connection import DB_REQUEST

def openConnection(database):
    db_config = DB_CONFIG(database)
    try:
        atendimento = DB_REQUEST(db_config)
        return atendimento
    except Exception as e:
        return {'msg': 'Erro: {}'.format(e)}