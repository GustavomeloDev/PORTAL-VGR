"""Conexão MySQL do módulo VGR — pool opcional via .env."""

from __future__ import annotations

import os
import threading

import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv

from core.database.config import module_db_config

load_dotenv()

_POOL = None
_POOL_LOCK = threading.Lock()


def _pool_enabled() -> bool:
    return (os.getenv("VGR_MYSQL_POOL", "true") or "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _pool_size() -> int:
    raw = os.getenv("VGR_MYSQL_POOL_SIZE") or os.getenv("WAITRESS_THREADS", "16")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 16
    return max(4, min(n, 64))


def vgr_db_base_config() -> dict:
    db_name = os.getenv("VGR_MYSQL_DATABASE", "multi_cliente_db")
    return module_db_config(db_name, use_pool=False)


def _pool_reset_session() -> bool:
    raw = (
        os.getenv("VGR_MYSQL_POOL_RESET_SESSION")
        or os.getenv("MYSQL_POOL_RESET_SESSION")
        or "true"
    )
    return (raw or "true").strip().lower() in ("1", "true", "yes", "on")


def get_vgr_db_connection(*, use_pool: bool | None = None):
    """Retorna conexão MySQL (multi_cliente_db)."""
    if use_pool is None:
        use_pool = _pool_enabled()
    if not use_pool:
        return mysql.connector.connect(**vgr_db_base_config())

    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                cfg = vgr_db_base_config()
                _POOL = pooling.MySQLConnectionPool(
                    pool_name=os.getenv("VGR_MYSQL_POOL_NAME", "vgr_pool"),
                    pool_size=_pool_size(),
                    pool_reset_session=_pool_reset_session(),
                    **cfg,
                )
    return _POOL.get_connection()
