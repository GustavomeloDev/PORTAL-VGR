"""Enriquecimento de endereço padrão do portal (ViaCEP / Nominatim).

Motor: ``core.utils.endereco_enriquecimento_engine``.
Novos módulos devem usar ``enriquecer_endereco_portal`` (aceita cidade/uf).
A Prodesp continua com a cópia própria e não depende deste pacote.
"""

from __future__ import annotations

from typing import Any

from core.utils.endereco_enriquecimento_engine import enriquecer_endereco_unidade

_STR_MAX = 500
_KEYS_IN = (
    "endereco",
    "numero",
    "bairro",
    "municipio",
    "cidade",
    "estado",
    "uf",
    "cep",
    "latitude",
    "longitude",
)


def _clip(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()[:_STR_MAX]


def _normalize_payload(payload: dict[str, Any] | None) -> dict[str, str]:
    raw = payload or {}
    out: dict[str, str] = {}
    for key in _KEYS_IN:
        if key in raw:
            out[key] = _clip(raw.get(key))
    cidade = out.get("cidade") or ""
    uf = out.get("uf") or ""
    if not out.get("municipio") and cidade:
        out["municipio"] = cidade
    if not out.get("estado") and uf:
        out["estado"] = uf
    return out


def enriquecer_endereco_portal(payload: dict[str, Any] | None) -> dict[str, Any]:
    """
    Completa campos vazios e devolve avisos se CEP/endereço/coordenadas divergirem.

    Não grava no banco. Chamador deve estar autenticado + CSRF.
    """
    data = _normalize_payload(payload)
    result = enriquecer_endereco_unidade(data)
    if not isinstance(result, dict):
        return {
            "success": False,
            "message": "Falha ao completar endereço.",
            "updates": {},
        }
    updates = dict(result.get("updates") or {})
    if "municipio" in updates and "cidade" not in updates:
        updates["cidade"] = updates["municipio"]
    if "estado" in updates and "uf" not in updates:
        updates["uf"] = updates["estado"]
    result["updates"] = updates
    return result
