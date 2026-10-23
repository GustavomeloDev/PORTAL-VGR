"""
BaseController - Classe base para todos os controllers
Implementa roteamento HTTP e validações básicas
"""

from abc import ABC
from flask import jsonify, request, session
from typing import Any, Dict, Optional
from core.exceptions.base_exceptions import ValidationError, BusinessRuleError, RepositoryError


class BaseController(ABC):
    """
    Classe base para controllers seguindo SOLID
    
    Responsabilidade única: Roteamento HTTP e resposta
    """
    
    def __init__(self):
        """Inicializa o controller"""
        pass
    
    def get_tenant_id(self) -> int:
        """
        Obtém o tenant_id da sessão atual
        
        Returns:
            ID do tenant
            
        Raises:
            ValidationError: Se tenant_id não estiver na sessão
        """
        tenant_id = session.get('tenant_id')
        if tenant_id is None:
            raise ValidationError("Tenant ID não encontrado na sessão")
        return tenant_id
    
    def get_user_id(self) -> int:
        """
        Obtém o user_id da sessão atual
        
        Returns:
            ID do usuário
            
        Raises:
            ValidationError: Se user_id não estiver na sessão
        """
        user_id = session.get('user_id')
        if user_id is None:
            raise ValidationError("User ID não encontrado na sessão")
        return user_id
    
    def get_request_data(self) -> Dict[str, Any]:
        """
        Obtém dados da requisição (JSON ou Form)
        
        Returns:
            Dicionário com os dados da requisição
        """
        if request.is_json:
            return request.get_json() or {}
        return request.form.to_dict()
    
    def json_response(self, data: Any, status_code: int = 200):
        """
        Retorna resposta JSON padronizada
        
        Args:
            data: Dados a serem retornados
            status_code: Código HTTP de status
            
        Returns:
            Response JSON do Flask
        """
        return jsonify(data), status_code
    
    def success_response(self, message: str, data: Any = None, status_code: int = 200):
        """
        Retorna resposta de sucesso padronizada
        
        Args:
            message: Mensagem de sucesso
            data: Dados adicionais (opcional)
            status_code: Código HTTP de status
            
        Returns:
            Response JSON do Flask
        """
        response = {
            'success': True,
            'message': message
        }
        if data is not None:
            response['data'] = data
        return self.json_response(response, status_code)
    
    def error_response(self, message: str, status_code: int = 400, error_type: str = None):
        """
        Retorna resposta de erro padronizada
        
        Args:
            message: Mensagem de erro
            status_code: Código HTTP de status
            error_type: Tipo do erro (opcional)
            
        Returns:
            Response JSON do Flask
        """
        response = {
            'success': False,
            'message': message
        }
        if error_type:
            response['error_type'] = error_type
        return self.json_response(response, status_code)
    
    def handle_exception(self, e: Exception):
        """
        Trata exceções de forma padronizada
        
        Args:
            e: Exceção capturada
            
        Returns:
            Response JSON do Flask com erro apropriado
        """
        if isinstance(e, ValidationError):
            return self.error_response(str(e), 400, 'validation_error')
        elif isinstance(e, BusinessRuleError):
            return self.error_response(str(e), 422, 'business_rule_error')
        elif isinstance(e, RepositoryError):
            return self.error_response(str(e), 500, 'repository_error')
        else:
            # Log do erro não tratado
            import logging
            logging.error(f"Erro não tratado: {str(e)}", exc_info=True)
            return self.error_response("Erro interno do servidor", 500, 'internal_error')
