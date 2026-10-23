from core.database.repository import BaseRepository

def BuscarClientePorIdAtendimento(query: str, id, database):
    repo = BaseRepository(database)
    return repo.fetch_one(query, (id,))

def buscarTodosCliente(query: str, id, database):
    repo = BaseRepository(database)
    return repo.fetch_all(query)
