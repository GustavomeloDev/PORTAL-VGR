from typing import Any, Dict, Iterable, List, Tuple
from core.database.repository import BaseRepository
from core.repository.exceptions import NotFoundError


class TableRepository(BaseRepository):
    def __init__(self, database: str, table: str, id_field: str = "id"):
        super().__init__(database)
        self.table = table
        self.id_field = id_field

    def get_by_id(self, id_value: Any) -> Dict[str, Any]:
        q = f"SELECT * FROM {self.table} WHERE {self.id_field} = %s AND is_active = 1"
        return self.fetch_one(q, (id_value,))

    def get_all(self) -> List[Dict[str, Any]]:
        q = f"SELECT * FROM {self.table} WHERE is_active = 1"
        return self.fetch_all(q)

    def create(self, data: Dict[str, Any]) -> int:
        keys = list(data.keys())
        placeholders = ", ".join(["%s"] * len(keys))
        columns = ", ".join(keys)
        q = f"INSERT INTO {self.table} ({columns}) VALUES ({placeholders})"
        params = tuple(data[k] for k in keys)
        return self.execute(q, params)

    def update_by_id(self, id_value: Any, data: Dict[str, Any]) -> int:
        keys = list(data.keys())
        set_clause = ", ".join([f"{k}=%s" for k in keys])
        q = f"UPDATE {self.table} SET {set_clause} WHERE {self.id_field}=%s"
        params = tuple(data[k] for k in keys) + (id_value,)
        return self.execute(q, params)

    def delete_by_id(self, id_value: Any) -> int:
        q = f"UPDATE {self.table} SET is_active = -1 WHERE {self.id_field} = %s"
        return self.execute(q, (id_value,))
