"""Cache curto da lista atendimentos PRODESP (api/atendimentos_list).

Camada 1: linhas brutas do MySQL (compartilhado entre usuários).
Camada 2: JSON já processado (_prodesp_atendimentos_list_from_rows) por chave de usuário/perfil.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

_CACHE: Optional[tuple[float, dict[str, Any]]] = None
_RESUMO: Optional[tuple[float, dict[str, Any]]] = None
_PROCESSED: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _ttl_sec() -> int:
    unified = (os.getenv("PRODESP_DATA_CACHE_TTL_SEC") or "").strip()
    if unified:
        try:
            return max(0, int(unified))
        except (TypeError, ValueError):
            pass
    try:
        return max(0, int((os.getenv("PRODESP_ATENDIMENTOS_LIST_CACHE_TTL_SEC") or "60").strip()))
    except (TypeError, ValueError):
        return 60


def get() -> Optional[dict[str, Any]]:
    ttl = _ttl_sec()
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _LOCK:
        global _CACHE
        if not _CACHE:
            return None
        ts, payload = _CACHE
        if now - ts > ttl:
            _CACHE = None
            return None
        return dict(payload)


def set(payload: dict[str, Any]) -> None:
    ttl = _ttl_sec()
    if ttl <= 0:
        return
    with _LOCK:
        global _CACHE, _PROCESSED
        _CACHE = (time.monotonic(), dict(payload))
        _PROCESSED.clear()


def get_resumo() -> Optional[dict[str, Any]]:
    ttl = _ttl_sec()
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _LOCK:
        global _RESUMO
        if not _RESUMO:
            return None
        ts, payload = _RESUMO
        if now - ts > ttl:
            _RESUMO = None
            return None
        return dict(payload)


def set_resumo(payload: dict[str, Any]) -> None:
    ttl = _ttl_sec()
    if ttl <= 0:
        return
    with _LOCK:
        global _RESUMO
        _RESUMO = (time.monotonic(), dict(payload))


def get_processed(user_key: str) -> Optional[dict[str, Any]]:
    """Resposta JSON pronta; só válida enquanto o cache bruto (todos) estiver quente."""
    if not user_key or _ttl_sec() <= 0:
        return None
    if get() is None:
        return None
    with _LOCK:
        cached = _PROCESSED.get(user_key)
        return dict(cached) if cached else None


def set_processed(user_key: str, payload: dict[str, Any]) -> None:
    if not user_key or _ttl_sec() <= 0 or get() is None:
        return
    with _LOCK:
        _PROCESSED[user_key] = dict(payload)


def bust() -> None:
    with _LOCK:
        global _CACHE, _RESUMO, _PROCESSED
        _CACHE = None
        _RESUMO = None
        _PROCESSED.clear()
