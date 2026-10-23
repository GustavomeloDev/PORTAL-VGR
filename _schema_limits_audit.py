"""Audita COLUMN_LIMITS / FORM_ELEMENT_LIMITS vs INFORMATION_SCHEMA (uso interno).

Inclui colunas TEXT/MEDIUMTEXT via CHARACTER_MAXIMUM_LENGTH (ex.: logs_atendimentos = 16777215).
"""
from __future__ import annotations

import sys

import mysql.connector

from prodesp.credentials.db_config import db_config
from prodesp.prodesp.db_field_limits import (
    COLUMN_LIMITS,
    audit_limits_against_schema,
    fetch_schema_varchar_limits,
)

# Tabelas cobertas por COLUMN_LIMITS (filtro do dump de schema)
TABLES = {table for table, _column in COLUMN_LIMITS}


def fetch_schema_limits() -> dict[tuple[str, str], int]:
    conn = mysql.connector.connect(**db_config)
    schema = fetch_schema_varchar_limits(conn)
    conn.close()
    return schema


def dump_all_limits() -> None:
    schema = fetch_schema_limits()
    for k in sorted(schema):
        if k[0] in TABLES:
            print(f"{k[0]}.{k[1]}={schema[k]}")


def main() -> int:
    try:
        schema = fetch_schema_limits()
    except Exception as e:
        print("ERRO: nao foi possivel conectar ao banco:", e, file=sys.stderr)
        return 2

    failures = audit_limits_against_schema(schema)

    print("=== DIVERGENCIAS (%d) ===" % len(failures))
    for f in failures:
        print(" ", f)
    if not failures:
        print("COLUMN_LIMITS e FORM_ELEMENT_LIMITS alinhados ao schema.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
