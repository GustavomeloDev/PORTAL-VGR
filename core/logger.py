# core/logger.py
# -*- coding: utf-8 -*-

import logging as _logging
import os
from logging.handlers import RotatingFileHandler

from flask import has_request_context
from flask_login import current_user

# ============================================================
# External libraries to silence (WARNING or above only)
# ============================================================
_LIBS_SILENCIAR = [
    "paramiko",
    "paramiko.transport",
    "paramiko.transport.sftp",
    "urllib3",
    "requests",
    "waitress",
    "mysql.connector",
    "werkzeug",
]


class UsuarioFilter(_logging.Filter):
    def filter(self, record):
        try:
            if not has_request_context():
                record.usuario = "sistema"
                return True

            usuario = getattr(current_user, "nome_user", None)
            record.usuario = usuario or "sistema"
        except Exception:
            record.usuario = "erro_user"
        return True


def _add_filter_once(handler, log_filter):
    if not any(isinstance(existing, UsuarioFilter) for existing in handler.filters):
        handler.addFilter(log_filter)


def _resolve_level(default_level=_logging.INFO):
    env_level = os.getenv("LOG_LEVEL")
    if not env_level:
        return default_level
    env_level = str(env_level).strip().upper()
    mapping = {
        "DEBUG": _logging.DEBUG,
        "INFO": _logging.INFO,
        "WARNING": _logging.WARNING,
        "ERROR": _logging.ERROR,
        "CRITICAL": _logging.CRITICAL,
    }
    return mapping.get(env_level, default_level)


def setup_logger(name=None, log_file="logs/system.log", level=None, silenciar_libs=True):
    """
    Configura a infraestrutura global de logging (handlers, formatter, rotação).
    Deve ser chamado UMA vez no run.py, ANTES dos imports dos blueprints.

    Parâmetros:
        name           : nome do logger retornado (ex: "app")
        log_file       : caminho do arquivo de log rotativo
        level          : nível de log (padrão: INFO ou via env LOG_LEVEL)
        silenciar_libs : se True, silencia libs barulhentas (paramiko, urllib3, etc.)

    Uso no run.py:
        from core.logger import setup_logger
        setup_logger(name="app", log_file="logs/app.log")
    """
    if level is None:
        level = _resolve_level(_logging.INFO)

    # Garante diretório de logs
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Formatter com projeto, arquivo e linha
    usuario_filter = UsuarioFilter()

    formatter = _logging.Formatter(
        "%(asctime)s - %(levelname)s - %(usuario)s - %(name)s - %(module)s:%(lineno)d - %(message)s"
    )

    # Handler de arquivo rotativo (5MB, 5 backups)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    _add_filter_once(file_handler, usuario_filter)

    # Handler de console (só WARNING e acima em produção)
    console_handler = _logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(_logging.INFO)
    _add_filter_once(console_handler, usuario_filter)

    # Configura root logger UMA vez
    root_logger = _logging.getLogger()
    root_logger.setLevel(level)

    # Evita duplicidade de handlers
    has_file = any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers)
    has_console = any(
        isinstance(h, _logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root_logger.handlers
    )

    if not has_file:
        root_logger.addHandler(file_handler)
    else:
        for handler in root_logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                _add_filter_once(handler, usuario_filter)

    if not has_console:
        root_logger.addHandler(console_handler)
    else:
        for handler in root_logger.handlers:
            if isinstance(handler, _logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
                _add_filter_once(handler, usuario_filter)

    # Silencia bibliotecas externas barulhentas
    if silenciar_libs:
        for lib in _LIBS_SILENCIAR:
            _logging.getLogger(lib).setLevel(_logging.WARNING)

    # Retorna logger nomeado
    if name:
        logger = _logging.getLogger(name)
        logger.propagate = True
        return logger

    return root_logger


def get_logger(name: str) -> _logging.Logger:
    """
    Retorna um logger nomeado para uso nos blueprints/módulos.
    Não reconfigura handlers — apenas aponta para o logger correto.

    A variável pode se chamar 'logging' no arquivo destino sem conflito,
    pois aqui o módulo real está protegido pelo alias '_logging'.

    Uso nos blueprints:
        from core.logger import get_logger
        logging = get_logger("FUST")   # substitui o import padrão
        logging = get_logger("RD")
        logging = get_logger("ITAÚ")

    Resultado no log:
        2026-03-17 - INFO - FUST - app:87 - mensagem
        2026-03-17 - ERROR - RD  - validador:42 - erro
    """
    return _logging.getLogger(name)
