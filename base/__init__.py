"""
Core Base Classes - Factory Pattern
Fornece classes base para todos os módulos do sistema
"""

from .repository import BaseRepository
from .service import BaseService
from .controller import BaseController

__all__ = ['BaseRepository', 'BaseService', 'BaseController']
