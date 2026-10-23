"""Snapshot de tempos por atendimento (P0-02 / Sprint 5).

Tabela ``atendimento_tempo_snapshot`` (ver ``prodesp/sql/019_atendimento_tempo_snapshot.sql``).

Flags (default OFF — ligar após DDL + backfill):
  PRODESP_TEMPO_SNAPSHOT_WRITE=1  — refresh após create/update
  PRODESP_TEMPO_SNAPSHOT_READ=1   — lista/dashboard/KPIs leem snapshot em vez da view

Rollback leitura: READ=0 → vw_tempo_atendimento_detalhado.
"""

from __future__ import annotations

import logging
import os
from typing import Any

_logger = logging.getLogger("prodesp.tempo_snapshot")

TABLE = "atendimento_tempo_snapshot"
VIEW = "vw_tempo_atendimento_detalhado"


def write_enabled() -> bool:
    return (os.getenv("PRODESP_TEMPO_SNAPSHOT_WRITE", "false") or "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def read_enabled() -> bool:
    return (os.getenv("PRODESP_TEMPO_SNAPSHOT_READ", "false") or "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def tempo_source_table() -> str:
    """Alias ``v`` esperado pelos SQLs existentes."""
    return TABLE if read_enabled() else VIEW


def refresh_one(cursor, id_atendimento: int) -> bool:
    """UPSERT de uma linha a partir da view. Retorna False se falhar/desligado."""
    if not write_enabled():
        return False
    try:
        aid = int(id_atendimento)
    except (TypeError, ValueError):
        return False
    sql = f"""
        INSERT INTO {TABLE} (
            id_atendimentos, id_unidade,
            tempo_total_geral, tempo_total_atendimento, tempo_aguardando_cliente,
            tempo_triagem, tempo_aguarda_gestao, tempo_com_suporte,
            tempo_aguardando_config_remota, tempo_config_remota,
            tempo_aguardando_mpls, tempo_config_mpls,
            tempo_aguardando_caderno, tempo_caderno_teste,
            analista_atuante_atendimentos, analista_configuracao_atendimentos,
            analista_mpls_atendimentos, analista_caderno_teste_atendimentos,
            refreshed_at
        )
        SELECT
            v.id_atendimentos,
            v.id_unidade,
            v.tempo_total_geral,
            v.tempo_total_atendimento,
            v.tempo_aguardando_cliente,
            v.tempo_triagem,
            v.tempo_aguarda_gestao,
            v.tempo_com_suporte,
            v.tempo_aguardando_config_remota,
            v.tempo_config_remota,
            v.tempo_aguardando_mpls,
            v.tempo_config_mpls,
            v.tempo_aguardando_caderno,
            v.tempo_caderno_teste,
            v.analista_atuante_atendimentos,
            v.analista_configuracao_atendimentos,
            v.analista_mpls_atendimentos,
            v.analista_caderno_teste_atendimentos,
            NOW()
        FROM {VIEW} v
        WHERE v.id_atendimentos = %s
        ON DUPLICATE KEY UPDATE
            id_unidade = VALUES(id_unidade),
            tempo_total_geral = VALUES(tempo_total_geral),
            tempo_total_atendimento = VALUES(tempo_total_atendimento),
            tempo_aguardando_cliente = VALUES(tempo_aguardando_cliente),
            tempo_triagem = VALUES(tempo_triagem),
            tempo_aguarda_gestao = VALUES(tempo_aguarda_gestao),
            tempo_com_suporte = VALUES(tempo_com_suporte),
            tempo_aguardando_config_remota = VALUES(tempo_aguardando_config_remota),
            tempo_config_remota = VALUES(tempo_config_remota),
            tempo_aguardando_mpls = VALUES(tempo_aguardando_mpls),
            tempo_config_mpls = VALUES(tempo_config_mpls),
            tempo_aguardando_caderno = VALUES(tempo_aguardando_caderno),
            tempo_caderno_teste = VALUES(tempo_caderno_teste),
            analista_atuante_atendimentos = VALUES(analista_atuante_atendimentos),
            analista_configuracao_atendimentos = VALUES(analista_configuracao_atendimentos),
            analista_mpls_atendimentos = VALUES(analista_mpls_atendimentos),
            analista_caderno_teste_atendimentos = VALUES(analista_caderno_teste_atendimentos),
            refreshed_at = VALUES(refreshed_at)
    """
    try:
        cursor.execute(sql, (aid,))
        return True
    except Exception as exc:
        _logger.warning(
            "tempo_snapshot refresh_one id=%s falhou (%s)",
            aid,
            type(exc).__name__,
        )
        return False


def tempo_join_alias() -> str:
    """Fragmento SQL ``LEFT JOIN <src> vt ON vt.id_atendimentos = ...`` target id expr."""
    return tempo_source_table()
