"""
Sanitizadores reutilizáveis
Funções de sanitização comuns a todos os módulos
"""

import re
from typing import Any, Optional


def sanitize_string(value: Any) -> Optional[str]:
    """
    Sanitiza string removendo espaços e normalizando valores vazios
    
    Args:
        value: Valor a ser sanitizado
        
    Returns:
        String sanitizada ou None
    """
    if value is None:
        return None
    
    if not isinstance(value, str):
        value = str(value)
    
    value = value.strip()
    
    if value == '' or value.lower() in ('null', 'none', 'nan'):
        return None
    
    return value


def sanitize_cnpj(cnpj: str) -> Optional[str]:
    """
    Sanitiza CNPJ removendo caracteres especiais
    
    Args:
        cnpj: CNPJ a ser sanitizado
        
    Returns:
        CNPJ apenas com dígitos ou None
    """
    if not cnpj:
        return None
    
    cnpj = re.sub(r'\D', '', cnpj)
    
    if len(cnpj) != 14:
        return None
    
    return cnpj


def sanitize_cpf(cpf: str) -> Optional[str]:
    """
    Sanitiza CPF removendo caracteres especiais
    
    Args:
        cpf: CPF a ser sanitizado
        
    Returns:
        CPF apenas com dígitos ou None
    """
    if not cpf:
        return None
    
    cpf = re.sub(r'\D', '', cpf)
    
    if len(cpf) != 11:
        return None
    
    return cpf


def sanitize_cep(cep: str) -> Optional[str]:
    """
    Sanitiza CEP removendo caracteres especiais
    
    Args:
        cep: CEP a ser sanitizado
        
    Returns:
        CEP apenas com dígitos ou None
    """
    if not cep:
        return None
    
    cep = re.sub(r'\D', '', cep)
    
    if len(cep) != 8:
        return None
    
    return cep


def sanitize_phone(phone: str) -> Optional[str]:
    """
    Sanitiza telefone removendo caracteres especiais
    
    Args:
        phone: Telefone a ser sanitizado
        
    Returns:
        Telefone apenas com dígitos ou None
    """
    if not phone:
        return None
    
    phone = re.sub(r'\D', '', phone)
    
    if len(phone) not in [10, 11]:
        return None
    
    return phone


def normalize_text(text: str) -> str:
    """
    Normaliza texto removendo acentos e caracteres especiais
    
    Args:
        text: Texto a ser normalizado
        
    Returns:
        Texto normalizado
    """
    if not text:
        return ''
    
    import unicodedata
    
    # Remove acentos
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ASCII', 'ignore').decode('ASCII')
    
    return text.strip()
