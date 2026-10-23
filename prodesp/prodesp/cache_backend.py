"""Backend de cache PRODESP (memória + Redis opcional, P1-02).

``PRODESP_REDIS_URL`` — se definido e pacote ``redis`` instalado, dashboard
compartilha payload entre workers. Sem URL ou sem pacote: dict processo.

Geração ``prodesp:cache:gen`` incrementada no bust → chaves antigas expiram via TTL.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Optional

_logger = logging.getLogger("prodesp.cache_backend")

_mem_lock = threading.Lock()
_mem: dict[str, tuple[float, str]] = {}
_local_gen = 0
_redis = None
_redis_tried = False


def redis_enabled() -> bool:
    url = (os.getenv("PRODESP_REDIS_URL") or "").strip()
    return bool(url)


def redis_active() -> bool:
    """True se cliente Redis conectado (não só URL configurada)."""
    return _get_redis() is not None


def _get_redis():
    global _redis, _redis_tried
    if not redis_enabled():
        return None
    if _redis_tried:
        return _redis
    _redis_tried = True
    try:
        import redis  # type: ignore

        url = (os.getenv("PRODESP_REDIS_URL") or "").strip()
        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1.5)
        client.ping()
        _redis = client
        _logger.info("prodesp cache Redis OK")
    except Exception as exc:
        _logger.warning("prodesp cache Redis indisponível (%s) — usando memória", type(exc).__name__)
        _redis = None
    return _redis


def generation() -> int:
    """Contador de invalidação compartilhado (Redis) ou local."""
    global _local_gen
    r = _get_redis()
    if r is not None:
        try:
            val = r.get("prodesp:cache:gen")
            return int(val or 0)
        except Exception:
            pass
    with _mem_lock:
        return _local_gen


def bump_generation() -> int:
    global _local_gen
    r = _get_redis()
    if r is not None:
        try:
            return int(r.incr("prodesp:cache:gen"))
        except Exception as exc:
            _logger.warning("redis incr falhou (%s)", type(exc).__name__)
    with _mem_lock:
        _local_gen += 1
        _mem.clear()
        return _local_gen


def _key(ns: str, *parts: str) -> str:
    gen = generation()
    safe = ":".join(str(p) for p in parts)
    return f"prodesp:{ns}:{gen}:{safe}"


def cache_get(ns: str, *parts: str) -> Optional[dict[str, Any]]:
    key = _key(ns, *parts)
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(key)
            if raw:
                return json.loads(raw)
        except Exception as exc:
            _logger.warning("redis get falhou (%s)", type(exc).__name__)
    import time

    now = time.monotonic()
    with _mem_lock:
        entry = _mem.get(key)
        if not entry:
            return None
        exp, raw = entry
        if now > exp:
            _mem.pop(key, None)
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            _mem.pop(key, None)
            return None


def cache_set(ns: str, payload: dict[str, Any], ttl_sec: int, *parts: str) -> None:
    if ttl_sec <= 0:
        return
    key = _key(ns, *parts)
    try:
        raw = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return
    r = _get_redis()
    if r is not None:
        try:
            r.setex(key, ttl_sec, raw)
            return
        except Exception as exc:
            _logger.warning("redis setex falhou (%s)", type(exc).__name__)
    import time

    with _mem_lock:
        _mem[key] = (time.monotonic() + ttl_sec, raw)


def cache_bust() -> None:
    bump_generation()
