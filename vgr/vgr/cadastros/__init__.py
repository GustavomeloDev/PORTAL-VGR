"""Cadastros multi-cliente (clientes / unidades)."""

from vgr.vgr.cadastros import repo_inventario as repo
from vgr.vgr.cadastros.validators import (
    parse_cliente_payload,
    parse_unidade_payload,
)

__all__ = [
    "repo",
    "parse_cliente_payload",
    "parse_unidade_payload",
]
