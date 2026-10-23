from core.database.repository import BaseRepository

def buscarLinksPorIdAtendimento(query: str, id, database):
    repo = BaseRepository(database)
    return repo.fetch_all(query, (id,))
