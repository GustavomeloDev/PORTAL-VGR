"""
Contador global de revisão de dados PRODESP (fila + gestão).

Incrementado em bump() após mutações. Clientes fazem poll em /api/data_revision
a cada PRODESP_DT_SYNC_INTERVAL_SEC; ajax.reload da DataTable só ocorre se o
contador mudou (ou no botão Atualizar / force).

Dirty set por revisão: bump(atendimento_ids=...) grava IDs tocados para o
endpoint de delta. Sem IDs (bump opaco) o cliente faz fallback_full.

Persistido em arquivo local para sobreviver ao reloader do Flask.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import pytz

_LOCK = threading.Lock()
_REV_PATH = Path(
    os.getenv("PRODESP_DATA_REVISION_FILE")
    or (Path(tempfile.gettempdir()) / "portal_prodesp_data_revision.txt")
)
_DIRTY_PATH = Path(
    os.getenv("PRODESP_DATA_REVISION_DIRTY_FILE")
    or (Path(tempfile.gettempdir()) / "portal_prodesp_data_revision_dirty.json")
)

# Quantas revisões guardar no dirty log; gap maior → fallback_full.
_DIRTY_KEEP_REVS = 80
# Mais IDs que isso no delta → fallback_full (evita patch gigante).
_DIRTY_MAX_IDS = 200


def _read_persisted() -> int:
    try:
        raw = _REV_PATH.read_text(encoding="utf-8").strip()
        return max(0, int(raw or "0"))
    except (OSError, TypeError, ValueError):
        return 0


def _write_persisted(value: int) -> None:
    try:
        _REV_PATH.write_text(str(int(value)), encoding="utf-8")
    except OSError:
        pass


_REVISION = _read_persisted()


def _sync_interval_sec() -> int:
    try:
        return max(15, int((os.getenv("PRODESP_DT_SYNC_INTERVAL_SEC") or "90").strip()))
    except (TypeError, ValueError):
        return 90


def current_revision() -> int:
    with _LOCK:
        return _REVISION


def _normalize_ids(atendimento_ids: Optional[Iterable[Any]]) -> Optional[list[int]]:
    if atendimento_ids is None:
        return None
    out: list[int] = []
    seen: set[int] = set()
    for raw in atendimento_ids:
        if raw is None or raw == "":
            continue
        try:
            n = int(raw)
        except (TypeError, ValueError):
            continue
        if n <= 0 or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def bump(atendimento_ids: Optional[Iterable[Any]] = None) -> int:
    """Incrementa revisão (após mutação que altera fila/dashboard).

    ``atendimento_ids`` omitido/None = revisão opaca (delta → fallback_full).
    Iterável (mesmo vazio) = IDs conhecidos gravados no dirty log.
    """
    global _REVISION
    explicit = atendimento_ids is not None
    ids = _normalize_ids(atendimento_ids) if explicit else None
    with _LOCK:
        _REVISION += 1
        _write_persisted(_REVISION)
        if explicit:
            _record_dirty_unlocked(_REVISION, ids if ids is not None else [])
        else:
            _record_dirty_unlocked(_REVISION, None)
        return _REVISION


def _read_dirty() -> dict[str, Any]:
    try:
        raw = _DIRTY_PATH.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        if isinstance(data, dict) and isinstance(data.get("by_rev"), dict):
            return data
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return {"by_rev": {}}


def _write_dirty(data: dict[str, Any]) -> None:
    try:
        _DIRTY_PATH.write_text(
            json.dumps(data, ensure_ascii=True, separators=(",", ":")),
            encoding="utf-8",
        )
    except OSError:
        pass


def _record_dirty_unlocked(rev: int, ids: Optional[list[int]]) -> None:
    """ids=None → revisão opaca (força fallback_full no gap)."""
    data = _read_dirty()
    by_rev: dict[str, Any] = dict(data.get("by_rev") or {})
    if ids is None:
        by_rev[str(rev)] = {"opaque": True, "ids": []}
    else:
        by_rev[str(rev)] = {"opaque": False, "ids": ids}
    # Mantém só as últimas N revisões.
    keys = sorted((int(k) for k in by_rev.keys() if str(k).isdigit()), reverse=True)
    keep = set(str(k) for k in keys[:_DIRTY_KEEP_REVS])
    data["by_rev"] = {k: v for k, v in by_rev.items() if k in keep}
    _write_dirty(data)


def dirty_ids_since(since_revision: int) -> dict[str, Any]:
    """IDs sujos após ``since_revision`` (exclusive) até a revisão atual.

    Retorno:
      unchanged, fallback_full, ids, data_revision
    """
    try:
        since = int(since_revision)
    except (TypeError, ValueError):
        since = -1

    with _LOCK:
        current = _REVISION
        if since < 0:
            return {
                "unchanged": False,
                "fallback_full": True,
                "ids": [],
                "data_revision": current,
            }
        if since >= current:
            return {
                "unchanged": True,
                "fallback_full": False,
                "ids": [],
                "data_revision": current,
            }
        gap = current - since
        if gap > _DIRTY_KEEP_REVS:
            return {
                "unchanged": False,
                "fallback_full": True,
                "ids": [],
                "data_revision": current,
            }
        data = _read_dirty()
        by_rev = data.get("by_rev") or {}
        collected: set[int] = set()
        for rev in range(since + 1, current + 1):
            entry = by_rev.get(str(rev))
            if entry is None:
                return {
                    "unchanged": False,
                    "fallback_full": True,
                    "ids": [],
                    "data_revision": current,
                }
            if entry.get("opaque"):
                return {
                    "unchanged": False,
                    "fallback_full": True,
                    "ids": [],
                    "data_revision": current,
                }
            for raw in entry.get("ids") or []:
                try:
                    collected.add(int(raw))
                except (TypeError, ValueError):
                    continue
        if len(collected) > _DIRTY_MAX_IDS:
            return {
                "unchanged": False,
                "fallback_full": True,
                "ids": [],
                "data_revision": current,
            }
        return {
            "unchanged": False,
            "fallback_full": False,
            "ids": sorted(collected),
            "data_revision": current,
        }


def reset_for_tests(value: int = 0) -> None:
    global _REVISION
    with _LOCK:
        _REVISION = int(value)
        # Sem write no contador: testes não devem zerar o arquivo do servidor local.
        # Limpa só o dirty path atual (nos testes aponta para tempfile).
        try:
            _write_dirty({"by_rev": {}})
        except OSError:
            pass


def _next_sync_epoch_ms(interval_ms: int | None = None) -> int:
    interval_ms = interval_ms or (_sync_interval_sec() * 1000)
    now_ms = int(time.time() * 1000)
    elapsed = now_ms % interval_ms
    if elapsed == 0:
        return now_ms + interval_ms
    return now_ms + (interval_ms - elapsed)


def revision_payload() -> dict[str, Any]:
    tz_sp = pytz.timezone("America/Sao_Paulo")
    interval_sec = _sync_interval_sec()
    return {
        "data_revision": current_revision(),
        "revision": current_revision(),
        "server_time": datetime.now(tz_sp).isoformat(),
        "sync_interval_sec": interval_sec,
        "next_sync_epoch_ms": _next_sync_epoch_ms(interval_sec * 1000),
    }


def attach_to_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Inclui data_revision e server_time em respostas completas da API."""
    rev = revision_payload()
    out = dict(payload)
    out["data_revision"] = rev["data_revision"]
    if "server_time" not in out:
        out["server_time"] = rev["server_time"]
    return out
