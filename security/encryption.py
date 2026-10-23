from werkzeug.security import generate_password_hash, check_password_hash
import os
from typing import Optional

def encrypt_pwd(plain_password: str) -> str:
    return generate_password_hash(plain_password)

def check_pwd(plain_password: str, hashed_password: str) -> bool:
    return check_password_hash(hashed_password, plain_password)

_FERNET_CACHE = None

def _get_fernet():
    global _FERNET_CACHE
    if _FERNET_CACHE is not None:
        return _FERNET_CACHE
    try:
        from cryptography.fernet import Fernet
    except Exception:
        return None
    key = os.getenv("FERNET_TECH_KEY")
    if not key:
        return None
    try:
        _FERNET_CACHE = Fernet(key)
        return _FERNET_CACHE
    except Exception:
        return None

def encrypt_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    f = _get_fernet()
    if not f:
        return value
    try:
        token = f.encrypt(value.encode("utf-8"))
        return token.decode("utf-8")
    except Exception:
        return value

def decrypt_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    f = _get_fernet()
    if not f:
        return value
    try:
        plain = f.decrypt(value.encode("utf-8"))
        return plain.decode("utf-8")
    except Exception:
        return value


def encrypt_fields(data: dict, fields: list[str]) -> dict:
    """
    Retorna uma cópia do dicionário com os campos especificados criptografados.

    Uso:
        from core.security.encryption import encrypt_fields

        safe = encrypt_fields(data, fields=["cpf", "rg", "telefone"])

    Args:
        data:   Dicionário de entrada (não é modificado).
        fields: Lista de chaves cujos valores devem ser criptografados.

    Returns:
        Novo dicionário com os campos indicados criptografados.
        Campos ausentes ou None são mantidos como None.
    """
    result = dict(data)
    for field in fields:
        if field in result:
            result[field] = encrypt_text(result[field])
    return result


def decrypt_fields(data: dict, fields: list[str]) -> dict:
    """
    Retorna uma cópia do dicionário com os campos especificados descriptografados.

    Uso:
        from core.security.encryption import decrypt_fields

        plain = decrypt_fields(row, fields=["cpf", "rg", "telefone"])

    Args:
        data:   Dicionário de entrada (não é modificado).
        fields: Lista de chaves cujos valores devem ser descriptografados.

    Returns:
        Novo dicionário com os campos indicados descriptografados.
        Campos ausentes, None ou com token inválido são retornados sem alteração.
    """
    result = dict(data)
    for field in fields:
        if field in result:
            result[field] = decrypt_text(result[field])
    return result


def encrypt_list_fields(items: list[dict], fields: list[str]) -> list[dict]:
    """
    Aplica encrypt_fields em cada item de uma lista de dicionários.

    Uso:
        tecnicos_enc = encrypt_list_fields(tecnicos, fields=["tecnico_nome", "tecnico_cpf"])
    """
    return [encrypt_fields(item, fields) for item in (items or [])]


def decrypt_list_fields(items: list[dict], fields: list[str]) -> list[dict]:
    """
    Aplica decrypt_fields em cada item de uma lista de dicionários.

    Uso:
        tecnicos_dec = decrypt_list_fields(tecnicos, fields=["tecnico_nome", "tecnico_cpf"])
    """
    return [decrypt_fields(item, fields) for item in (items or [])]
