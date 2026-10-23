"""
BaseService - Classe base para todos os services
Implementa lógica de negócio e orquestração
"""

from abc import ABC
from typing import Any, Dict, Optional
from core.exceptions.base_exceptions import ValidationError, BusinessRuleError


class BaseService(ABC):
    """
    Classe base para services seguindo SOLID
    
    Responsabilidade única: Lógica de negócio e orquestração
    """
    
    def __init__(self):
        """Inicializa o service"""
        pass
    
    def validate_required_fields(self, data: Dict[str, Any], required_fields: list) -> None:
        """
        Valida se campos obrigatórios estão presentes
        
        Args:
            data: Dicionário com os dados
            required_fields: Lista de campos obrigatórios
            
        Raises:
            ValidationError: Se algum campo obrigatório estiver ausente
        """
        missing_fields = []
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == '':
                missing_fields.append(field)
        
        if missing_fields:
            raise ValidationError(f"Campos obrigatórios ausentes: {', '.join(missing_fields)}")
    
    def validate_tenant_access(self, resource_tenant_id: int, user_tenant_id: int) -> None:
        """
        Valida se o usuário tem acesso ao recurso (multitenancy)
        
        Args:
            resource_tenant_id: ID do tenant do recurso
            user_tenant_id: ID do tenant do usuário
            
        Raises:
            BusinessRuleError: Se o usuário não tiver acesso
        """
        if resource_tenant_id != user_tenant_id:
            raise BusinessRuleError("Acesso negado: recurso pertence a outro tenant")
    
    def sanitize_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitiza dados de entrada removendo espaços e valores vazios
        
        Args:
            data: Dicionário com os dados
            
        Returns:
            Dicionário com dados sanitizados
        """
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                value = value.strip()
                if value == '':
                    value = None
            sanitized[key] = value
        return sanitized
    
    def build_response(self, success: bool, message: str, data: Any = None) -> Dict[str, Any]:
        """
        Constrói resposta padronizada
        
        Args:
            success: Se a operação foi bem-sucedida
            message: Mensagem de retorno
            data: Dados adicionais (opcional)
            
        Returns:
            Dicionário com resposta padronizada
        """
        response = {
            'success': success,
            'message': message
        }
        if data is not None:
            response['data'] = data
        return response
