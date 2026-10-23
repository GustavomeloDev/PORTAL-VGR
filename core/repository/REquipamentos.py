from core.database.repository import BaseRepository

def buscarEquipamentosPorIdAtendimento(query, id, database):
    repo = BaseRepository(database)
    return repo.fetch_all(query, (id,))
        
