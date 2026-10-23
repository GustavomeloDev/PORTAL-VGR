"""Coleta SSH FortiGate reutilizável (DMA, VGR, …).

Credenciais: FGT_SSH_USER / FGT_SSH_PASSWORD (fallback PRODESP_FGT_*).
Conexão padrão: SSH direto no loopback. Jump opcional (FGT_SSH_MODE=jump).
"""
from __future__ import annotations

from core.fgt_coleta.commands import comandos_perfil
from core.fgt_coleta.credentials import resolve_fgt_ssh_credentials
from core.fgt_coleta.stamp import frase_admin_carimbo, montar_carimbo_noc
from core.fgt_coleta.collector import FgtCollectResult, coletar_logs_fgt
from core.fgt_coleta.historico_texto import historico_coleta_falha, historico_coleta_sucesso

__all__ = (
    "FgtCollectResult",
    "coletar_logs_fgt",
    "comandos_perfil",
    "frase_admin_carimbo",
    "historico_coleta_falha",
    "historico_coleta_sucesso",
    "montar_carimbo_noc",
    "resolve_fgt_ssh_credentials",
)
