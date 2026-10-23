"""
Cache do payload do dashboard de gestão PRODESP (P1-02).

- Chave: (start_date, end_date) + geração (bust)
- TTL: PRODESP_DASHBOARD_CACHE_TTL_SEC / PRODESP_DATA_CACHE_TTL_SEC
- Backend: memória processo; Redis se PRODESP_REDIS_URL
- Blob inclui tempos_etapa (servido só a quem tem permissão de KPI)

TTL=0 desliga o cache.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from prodesp.prodesp import cache_backend


def _ttl_sec() -> int:
    unified = (os.getenv("PRODESP_DATA_CACHE_TTL_SEC") or "").strip()
    if unified:
        try:
            return max(0, int(unified))
        except (TypeError, ValueError):
            pass
    try:
        return max(0, int((os.getenv("PRODESP_DASHBOARD_CACHE_TTL_SEC") or "25").strip()))
    except (TypeError, ValueError):
        return 25


def get(start_date: str, end_date: str) -> Optional[dict[str, Any]]:
    ttl = _ttl_sec()
    if ttl <= 0:
        return None
    start_s, end_s = str(start_date)[:10], str(end_date)[:10]
    payload = cache_backend.cache_get("dash", start_s, end_s)
    if not payload:
        return None
    out = dict(payload)
    out["cache_meta"] = {
        "from_cache": True,
        "ttl_sec": ttl,
        "age_sec": None,
        "backend": "redis" if cache_backend.redis_active() else "memory",
    }
    return out


def set(start_date: str, end_date: str, payload: dict[str, Any]) -> None:
    ttl = _ttl_sec()
    if ttl <= 0:
        return
    start_s, end_s = str(start_date)[:10], str(end_date)[:10]
    stored = {k: v for k, v in payload.items() if k != "cache_meta"}
    cache_backend.cache_set("dash", stored, ttl, start_s, end_s)


def bust() -> None:
    """Invalida cache dashboard (e geração compartilhada Redis/memória)."""
    cache_backend.cache_bust()
