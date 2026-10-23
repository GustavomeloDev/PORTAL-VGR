"""Instrumentação leve de latência server-side (Sprint 1 performance).

Uso: decorar views que retornam ``jsonify(...)``.

- Injeta ``server_ms`` no JSON (float, ms).
- Header ``X-Portal-Server-Ms``.
- Log estruturado opcional via ``PORTAL_TIMING_LOG=1``.
- Desliga payload/header com ``PORTAL_TIMING=0``.
"""

from __future__ import annotations

import logging
import os
import time
from functools import wraps
from typing import Any, Callable

from flask import Response, jsonify, request

_logger = logging.getLogger("portal.timing")


def timing_enabled() -> bool:
    return (os.getenv("PORTAL_TIMING", "true") or "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def timing_log_enabled() -> bool:
    return (os.getenv("PORTAL_TIMING_LOG", "false") or "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def with_server_ms(view: Callable[..., Any]) -> Callable[..., Any]:
    """Mede a view e anexa ``server_ms`` se a resposta for JSON dict."""

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        t0 = time.perf_counter()
        result = view(*args, **kwargs)
        ms = round((time.perf_counter() - t0) * 1000.0, 1)
        if not timing_enabled():
            return result

        response: Any = result
        status: Any = None
        headers: Any = None
        if isinstance(result, tuple):
            if len(result) == 2:
                response, status = result
            elif len(result) >= 3:
                response, status, headers = result[0], result[1], result[2]
            else:
                response = result[0]

        if isinstance(response, Response) and response.is_json:
            data = response.get_json(silent=True)
            if isinstance(data, dict) and "server_ms" not in data:
                data = dict(data)
                data["server_ms"] = ms
                new_resp = jsonify(data)
                new_resp.status_code = response.status_code
                for k, v in response.headers:
                    if k.lower() not in ("content-length", "content-type"):
                        new_resp.headers[k] = v
                new_resp.headers["X-Portal-Server-Ms"] = str(ms)
                response = new_resp
            else:
                response.headers["X-Portal-Server-Ms"] = str(ms)
        elif isinstance(response, Response):
            response.headers["X-Portal-Server-Ms"] = str(ms)

        if timing_log_enabled():
            ep = getattr(request, "endpoint", None) or "?"
            _logger.info(
                "timing endpoint=%s method=%s server_ms=%.1f status=%s",
                ep,
                request.method,
                ms,
                getattr(response, "status_code", status) if response is not None else status,
            )

        if status is None and headers is None:
            return response
        if headers is None:
            return response, status
        return response, status, headers

    return wrapper
