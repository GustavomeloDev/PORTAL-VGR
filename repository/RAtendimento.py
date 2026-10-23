from core.database.repository import BaseRepository
from core.repository.exceptions import QueryError

def finalizarAtendimento(query: str, database):
    repo = BaseRepository(database)
    return repo.execute(query)

def buscarTodosAtendimentos(query: str, database):
    repo = BaseRepository(database)
    return repo.fetch_all(query)

def buscarAtendimentosPorId(query: str, id, database):
    repo = BaseRepository(database)
    return repo.fetch_one(query, (id,))

def salvarAtendimento(query: str, data: dict, database):
    repo = BaseRepository(database)
    params = tuple(data.values())
    return repo.execute(query, params)

def buscarLinksPorIdAtendimento(query: str, id, database):
    repo = BaseRepository(database)
    return repo.fetch_all(query, (id,))

def buscarCliente(query: str, id, database):
    repo = BaseRepository(database)
    return repo.fetch_one(query, (id,))
