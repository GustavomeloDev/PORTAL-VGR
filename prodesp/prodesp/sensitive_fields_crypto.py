"""
Criptografia Fernet (FERNET_TECH_KEY) para campos sensíveis PRODESP.
Mesmo padrão do módulo agendamentos (core.security.encryption).
"""
from __future__ import annotations

import re
from typing import Any, Mapping, MutableMapping, Optional

from core.security.encryption import decrypt_text, encrypt_text

# Colunas MySQL
SENSITIVE_DB_COLUMNS = frozenset({
    "contato_field_atendimentos",
    "contato_field_planejada_unidades",
    "telefone_contato_unidades",
    "pppoe_user_links",
    "pppoe_pass_links",
})

# Chaves JSON/API → coluna DB
_API_KEY_TO_DB: dict[str, str] = {
    "contato_field": "contato_field_atendimentos",
    "contato_field_planejada": "contato_field_planejada_unidades",
    "telefone_contato": "telefone_contato_unidades",
    "pppoe_user": "pppoe_user_links",
    "pppoe_pass": "pppoe_pass_links",
    "pppoe_user_links": "pppoe_user_links",
    "pppoe_pass_links": "pppoe_pass_links",
}

_DB_TO_API_KEYS: dict[str, tuple[str, ...]] = {
    "contato_field_atendimentos": ("contato_field", "contato_field_atendimentos"),
    "contato_field_planejada_unidades": ("contato_field_planejada", "contato_field_planejada_unidades"),
    "telefone_contato_unidades": ("telefone_contato", "telefone_contato_unidades"),
    "pppoe_user_links": ("pppoe_user", "pppoe_user_links"),
    "pppoe_pass_links": ("pppoe_pass", "pppoe_pass_links"),
}

_PHONE_DB_COLUMNS = frozenset({
    "contato_field_atendimentos",
    "contato_field_planejada_unidades",
    "telefone_contato_unidades",
})


def is_sensitive_db_column(db_col: str) -> bool:
    return db_col in SENSITIVE_DB_COLUMNS


def _normalize_phone_plain(value: Any) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())


def encrypt_sensitive_db_column(db_col: str, value: Any) -> Any:
    if db_col not in SENSITIVE_DB_COLUMNS:
        return value
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return ""
    enc = encrypt_text(s)
    return enc if enc is not None else s


def decrypt_sensitive_db_column(db_col: str, value: Any) -> Any:
    if db_col not in SENSITIVE_DB_COLUMNS:
        return value
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return ""
    dec = decrypt_text(s)
    return dec if dec is not None else ""


def ensure_encrypted_db_column(db_col: str, value: Any) -> Any:
    """Migração: criptografa só se ainda estiver em texto claro."""
    if db_col not in SENSITIVE_DB_COLUMNS or value is None:
        return value
    s = str(value).strip()
    if not s:
        return value
    trial = decrypt_text(s)
    if trial is not None and trial != s:
        return s
    return encrypt_sensitive_db_column(db_col, s)


def sensitive_values_equal_for_db(db_col: str, novo_plain: Any, old_stored: Any) -> bool:
    old_plain = decrypt_sensitive_db_column(db_col, old_stored)
    if db_col in _PHONE_DB_COLUMNS:
        return _normalize_phone_plain(novo_plain) == _normalize_phone_plain(old_plain)
    return str(novo_plain or "").strip() == str(old_plain or "").strip()


def decrypt_sensitive_row_inplace(row: Optional[MutableMapping[str, Any]]) -> None:
    if not row:
        return
    for db_col, keys in _DB_TO_API_KEYS.items():
        plain = None
        if db_col in row and row[db_col] not in (None, ""):
            plain = decrypt_sensitive_db_column(db_col, row[db_col])
            row[db_col] = plain
        for key in keys:
            if key in row and row.get(key) not in (None, ""):
                if plain is None:
                    plain = decrypt_sensitive_db_column(db_col, row[key])
                row[key] = plain


def decrypt_sensitive_rows_inplace(rows: Optional[list]) -> list:
    if not rows:
        return []
    for row in rows:
        if isinstance(row, dict):
            decrypt_sensitive_row_inplace(row)
    return rows


def encrypt_link_pppoe_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    for api_key, db_col in (
        ("pppoe_user", "pppoe_user_links"),
        ("pppoe_pass", "pppoe_pass_links"),
    ):
        if api_key in out and out[api_key] is not None:
            out[api_key] = encrypt_sensitive_db_column(db_col, out[api_key])
    return out


def encrypt_link_pppoe_db_dict(data: MutableMapping[str, Any]) -> None:
    for key in ("pppoe_user_links", "pppoe_pass_links"):
        if key in data and data[key] not in (None, ""):
            data[key] = encrypt_sensitive_db_column(key, data[key])


def decrypt_export_telefone_cell(value: Any) -> str:
    return str(decrypt_sensitive_db_column("telefone_contato_unidades", value) or "")


def decrypt_export_links_cell(links_text: Any) -> str:
    """Descriptografa trechos User/Pass na coluna Links do export Excel."""
    if links_text is None or (isinstance(links_text, float) and str(links_text) == "nan"):
        return ""
    text = str(links_text)

    def _repl_user(m: re.Match) -> str:
        token = m.group(1).strip()
        plain = decrypt_sensitive_db_column("pppoe_user_links", token)
        return f"User: {plain or token}"

    def _repl_pass(m: re.Match) -> str:
        token = m.group(1).strip()
        plain = decrypt_sensitive_db_column("pppoe_pass_links", token)
        return f"Pass: {plain or token}"

    text = re.sub(r"User:\s*([^|]+)", _repl_user, text)
    text = re.sub(r"Pass:\s*([^|]+)", _repl_pass, text)
    return text
