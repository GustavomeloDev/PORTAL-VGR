"""SQL da Gestão de Atendimentos VGR (somente leitura).

Duas fontes, unidas em ``gestao_kpis.mesclar_linhas``:
  1. Agenda no período  — agendamentos ativos com data_agendamento no filtro
     (com ou sem atendimento vinculado 1→1).
  2. Atividade no período — atendimentos ativos cuja abertura (ou criação,
     quando ainda não aberto, ex.: «Aguarda Gestão») caiu no filtro.

Datas usam intervalo semiaberto [início 00:00, fim+1 00:00) para aproveitar
índices de DATETIME/TIMESTAMP.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from vgr.credentials.db_connection import get_vgr_db_connection
from vgr.vgr.gestao.gestao_kpis import mesclar_linhas

log = logging.getLogger("VGR.repo_gestao")

# ID VGR do equipamento ativo por tipo de serviço (mesma regra da fila).
_SQL_ID_VGR_POR_SERVICO_U = """
(SELECT e.id_vgr FROM equipamentos e
   WHERE e.id_unidade = u.id_unidade AND e.ativo = 1 AND e.tipo_servico = 'SDWAN'
   ORDER BY e.id_equipamento LIMIT 1) AS id_vgr_sdwan,
(SELECT e.id_vgr FROM equipamentos e
   WHERE e.id_unidade = u.id_unidade AND e.ativo = 1 AND e.tipo_servico = 'SDWIFI'
   ORDER BY e.id_equipamento LIMIT 1) AS id_vgr_sdwifi,
(SELECT e.id_vgr FROM equipamentos e
   WHERE e.id_unidade = u.id_unidade AND e.ativo = 1 AND e.tipo_servico = 'SDLAN'
   ORDER BY e.id_equipamento LIMIT 1) AS id_vgr_sdlan
"""

# Snapshot do Field: do atendimento (efetivo) e da agenda (planejado).
_SQL_FIELDS = """
(SELECT af.snap_contratada_nome FROM atendimento_fields af
   WHERE af.id_atendimento = t.id_atendimento
   ORDER BY af.ordem, af.id_atendimento_field LIMIT 1) AS contratada_atendimento,
(SELECT af.snap_nome FROM atendimento_fields af
   WHERE af.id_atendimento = t.id_atendimento
   ORDER BY af.ordem, af.id_atendimento_field LIMIT 1) AS field_atendimento,
(SELECT gf.snap_nome FROM agendamento_fields gf
   WHERE gf.id_agendamento = a.id_agendamento
   ORDER BY gf.ordem, gf.id_agendamento_field LIMIT 1) AS field_agendamento
"""

_SELECT_LINHA = f"""
  a.id_agendamento, a.data_agendamento, a.hora_agendamento, a.status_agendamento,
  cp.nome_contratada AS contratada_planejada,
  t.id_atendimento, t.status_atendimento, t.substatus_atendimento,
  t.analista_atuante, t.atendimento_iniciado, t.abertura, t.fechamento,
  t.criado_em AS atendimento_criado_em, t.ativo,
  t.abertura AS data_atendimento,
  COALESCE(t.abertura, t.criado_em) AS data_atividade,
  u.id_unidade, u.nome_unidade, u.cidade, u.uf,
  c.id_cliente, c.razao_social,
  {_SQL_ID_VGR_POR_SERVICO_U},
  {_SQL_FIELDS}
"""


def _rows(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        return list(cur.fetchall() or [])
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _limites(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min),
        datetime.combine(end + timedelta(days=1), time.min),
    )


def list_linhas_agenda_periodo(start: date, end: date) -> list[dict[str, Any]]:
    """Agendas ativas com data no período (+ atendimento ativo vinculado, se houver)."""
    return _rows(
        f"""
        SELECT {_SELECT_LINHA}
        FROM agendamentos a
        INNER JOIN unidades u ON u.id_unidade = a.id_unidade
        INNER JOIN clientes c ON c.id_cliente = u.id_cliente
        LEFT JOIN contratadas cp ON cp.id_contratada = a.id_contratada_planejada
        LEFT JOIN atendimentos t
          ON t.id_agendamento = a.id_agendamento AND t.ativo = 1
        WHERE a.ativo = 1
          AND a.data_agendamento BETWEEN %s AND %s
        ORDER BY a.data_agendamento, a.hora_agendamento, a.id_agendamento
        """,
        (start, end),
    )


def list_linhas_atividade_periodo(start: date, end: date) -> list[dict[str, Any]]:
    """Atendimentos ativos com atividade (abertura ou criação) no período."""
    ini, fim = _limites(start, end)
    return _rows(
        f"""
        SELECT {_SELECT_LINHA}
        FROM atendimentos t
        INNER JOIN unidades u ON u.id_unidade = t.id_unidade
        INNER JOIN clientes c ON c.id_cliente = u.id_cliente
        LEFT JOIN agendamentos a ON a.id_agendamento = t.id_agendamento
        LEFT JOIN contratadas cp ON cp.id_contratada = a.id_contratada_planejada
        WHERE t.ativo = 1
          AND (
            (t.abertura >= %s AND t.abertura < %s)
            OR (t.abertura IS NULL AND t.criado_em >= %s AND t.criado_em < %s)
          )
        ORDER BY COALESCE(t.abertura, t.criado_em), t.id_atendimento
        """,
        (ini, fim, ini, fim),
    )


def list_linhas_periodo(start: date, end: date) -> list[dict[str, Any]]:
    """Linhas únicas do período (agenda ∪ atividade): base de KPIs, tabela e relatório."""
    return mesclar_linhas(
        list_linhas_agenda_periodo(start, end),
        list_linhas_atividade_periodo(start, end),
    )


def list_transicoes_periodo(start: date, end: date) -> list[dict[str, Any]]:
    """Log de status/substatus gravado no período (aba «Transições» do XLSX)."""
    ini, fim = _limites(start, end)
    return _rows(
        """
        SELECT
          l.criado_em, l.id_atendimento,
          c.razao_social, u.nome_unidade,
          l.status_anterior, l.substatus_anterior,
          l.status_novo, l.substatus_novo,
          l.usuario_re, l.usuario_nome, l.observacao
        FROM atendimento_status_log l
        INNER JOIN atendimentos t ON t.id_atendimento = l.id_atendimento
        INNER JOIN unidades u ON u.id_unidade = t.id_unidade
        INNER JOIN clientes c ON c.id_cliente = u.id_cliente
        WHERE l.criado_em >= %s AND l.criado_em < %s
        ORDER BY l.criado_em, l.id_log
        """,
        (ini, fim),
    )
