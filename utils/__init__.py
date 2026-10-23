"""
Core Utils Module
"""

from .validators import (
    validate_email,
    validate_cnpj,
    validate_cpf,
    validate_cep,
    validate_phone,
    only_digits
)

from .sanitizers import (
    sanitize_string,
    sanitize_cnpj,
    sanitize_cpf,
    sanitize_cep,
    sanitize_phone,
    normalize_text
)

__all__ = [
    'validate_email',
    'validate_cnpj',
    'validate_cpf',
    'validate_cep',
    'validate_phone',
    'only_digits',
    'sanitize_string',
    'sanitize_cnpj',
    'sanitize_cpf',
    'sanitize_cep',
    'sanitize_phone',
    'normalize_text'
]
