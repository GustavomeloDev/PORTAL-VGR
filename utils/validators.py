"""
Validadores reutilizáveis
Funções de validação comuns a todos os módulos
"""

import re
from typing import Optional


def validate_email(email: str) -> bool:
    """
    Valida formato de email
    
    Args:
        email: Email a ser validado
        
    Returns:
        True se válido, False caso contrário
    """
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_cnpj(cnpj: str) -> bool:
    """
    Valida CNPJ brasileiro
    
    Args:
        cnpj: CNPJ a ser validado (apenas dígitos)
        
    Returns:
        True se válido, False caso contrário
    """
    if not cnpj or len(cnpj) != 14:
        return False
    
    if not cnpj.isdigit():
        return False
    
    # Verifica se todos os dígitos são iguais
    if len(set(cnpj)) == 1:
        return False
    
    # Validação dos dígitos verificadores
    def calculate_digit(cnpj_partial: str, weights: list) -> int:
        total = sum(int(digit) * weight for digit, weight in zip(cnpj_partial, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder
    
    weights_first = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights_second = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    
    first_digit = calculate_digit(cnpj[:12], weights_first)
    second_digit = calculate_digit(cnpj[:13], weights_second)
    
    return cnpj[-2:] == f"{first_digit}{second_digit}"


def validate_cpf(cpf: str) -> bool:
    """
    Valida CPF brasileiro
    
    Args:
        cpf: CPF a ser validado (apenas dígitos)
        
    Returns:
        True se válido, False caso contrário
    """
    if not cpf or len(cpf) != 11:
        return False
    
    if not cpf.isdigit():
        return False
    
    # Verifica se todos os dígitos são iguais
    if len(set(cpf)) == 1:
        return False
    
    # Validação dos dígitos verificadores
    def calculate_digit(cpf_partial: str) -> int:
        total = sum(int(digit) * weight for digit, weight in zip(cpf_partial, range(len(cpf_partial) + 1, 1, -1)))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder
    
    first_digit = calculate_digit(cpf[:9])
    second_digit = calculate_digit(cpf[:10])
    
    return cpf[-2:] == f"{first_digit}{second_digit}"


def validate_cep(cep: str) -> bool:
    """
    Valida formato de CEP brasileiro
    
    Args:
        cep: CEP a ser validado
        
    Returns:
        True se válido, False caso contrário
    """
    if not cep:
        return False
    
    # Remove caracteres não numéricos
    cep_digits = re.sub(r'\D', '', cep)
    
    return len(cep_digits) == 8


def validate_phone(phone: str) -> bool:
    """
    Valida formato de telefone brasileiro
    
    Args:
        phone: Telefone a ser validado
        
    Returns:
        True se válido, False caso contrário
    """
    if not phone:
        return False
    
    # Remove caracteres não numéricos
    phone_digits = re.sub(r'\D', '', phone)
    
    # Aceita 10 dígitos (fixo) ou 11 dígitos (celular)
    return len(phone_digits) in [10, 11]


def only_digits(text: str) -> str:
    """
    Remove todos os caracteres não numéricos
    
    Args:
        text: Texto a ser processado
        
    Returns:
        String contendo apenas dígitos
    """
    if not text:
        return ''
    return re.sub(r'\D', '', text)


def validate_schedule(fields: dict)  -> bool:
    try:
       if fields['inicio'] and fields['fim']:
           return True
    except Exception as e:
        return False
        
    
