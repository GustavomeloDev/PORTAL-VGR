class RepositoryError(Exception):
    pass


class ConnectionError(RepositoryError):
    pass


class QueryError(RepositoryError):
    pass


class NotFoundError(RepositoryError):
    pass


class ValidationError(RepositoryError):
    pass
