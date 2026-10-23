"""
Formato de Designador / ID VGR do link (padrão VIVO no inventário PRODESP).

Usado pelos KPIs admin («fora do padrão») e por validate_link_fields no cadastro.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, MutableMapping, Optional

# Padrão dominante em prodesp_db.links: ID VGR ~7 dígitos; designador VIVO ~15.
ID_VGR_LINK_MIN_DIGITS = 7
DESIGNADOR_LINK_MIN_DIGITS = 15

# Colagem Excel/planilha: ZWSP, BOM, soft-hyphen, NBSP, aspas tipográficas nas bordas.
_PASTE_INVISIBLE_RE = re.compile(
    r"[\u200B-\u200D\uFEFF\u00AD\u2060\u00A0\u202F\u2007]"
)
_EDGE_QUOTES_RE = re.compile(r"^['\"\u2018\u2019\u201c\u201d]+|['\"\u2018\u2019\u201c\u201d]+$")
_WS_RE = re.compile(r"\s+")

_LINK_ID_KEYS = (
    "designador",
    "designador_links",
    "id_vgr",
    "id_vgr_links",
)


def _first(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def sanitize_link_pasted_text(value: Any) -> str:
    """
    Limpa ruido tipico de colagem (Excel/Word/HTML) em Designador e ID VGR.

    Nao remove hifen/barra (ex.: «00201723/26» continua invalido de proposito).
    """
    s = str(value if value is not None else "")
    if not s:
        return ""
    s = _PASTE_INVISIBLE_RE.sub("", s)
    s = _WS_RE.sub("", s)
    # Aspas nas bordas (repasse se colarem duplo)
    for _ in range(3):
        nxt = _EDGE_QUOTES_RE.sub("", s)
        if nxt == s:
            break
        s = nxt
    return s


def apply_link_identifier_sanitize(payload: MutableMapping[str, Any]) -> None:
    """Normaliza designador/id_vgr in-place (JSON de save / form)."""
    for key in _LINK_ID_KEYS:
        if key in payload and payload[key] is not None:
            payload[key] = sanitize_link_pasted_text(payload[key])


def is_id_vgr_link_fora_padrao(value: Any) -> bool:
    """
    ID VGR do link fora do padrão: só dígitos e comprimento mínimo.
    Ex. fora: «00201723/26», IP no campo, ou menos de 7 dígitos.
    Vazio não conta como fora (ausência ≠ formato inválido).
    """
    s = sanitize_link_pasted_text(value)
    if not s:
        return False
    return (not s.isdigit()) or len(s) < ID_VGR_LINK_MIN_DIGITS


def is_designador_link_fora_padrao(value: Any, operadora: Any = None) -> bool:
    """
    Designador fora do padrão — exclusivo de links VIVO (circuito numérico ~15).
    Outras operadoras não entram no critério (formatos distintos).
    Vazio não conta como fora.
    """
    if str(operadora or "").strip().upper() != "VIVO":
        return False
    s = sanitize_link_pasted_text(value)
    if not s:
        return False
    return (not s.isdigit()) or len(s) < DESIGNADOR_LINK_MIN_DIGITS


def validate_link_format_fields(payload: Mapping[str, Any]) -> Optional[str]:
    """
    Bloqueia cadastro/edição com mensagem objetiva. None se ok.
    Designador: só VIVO. ID VGR: quando preenchido.
    """
    operadora = str(
        _first(payload, "operadora", "operadora_links") or ""
    ).strip()
    designador = sanitize_link_pasted_text(
        _first(payload, "designador", "designador_links")
    )
    id_vgr = sanitize_link_pasted_text(_first(payload, "id_vgr", "id_vgr_links"))

    if is_designador_link_fora_padrao(designador, operadora):
        return (
            f"Designador «{designador}» fora do padrão VIVO: use apenas dígitos "
            f"com no mínimo {DESIGNADOR_LINK_MIN_DIGITS} caracteres "
            "(ex.: circuito de 15 dígitos)."
        )
    if is_id_vgr_link_fora_padrao(id_vgr):
        return (
            f"ID VGR do link «{id_vgr}» fora do padrão: use apenas dígitos "
            f"com no mínimo {ID_VGR_LINK_MIN_DIGITS} caracteres "
            "(ex.: 1737352)."
        )
    return None
