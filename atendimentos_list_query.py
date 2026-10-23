"""Consultas da lista PRODESP (scope fila, resumo KPI, paginação server-side).

Usado por ``api/atendimentos_list`` (P3).
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any, Mapping, Optional

from prodesp.prodesp.atendimento_business_rules import (
    FINAL_STATUSES_ATENDIMENTO,
    SUBSTATUS_AGUARDA_CONTRATADA,
    SUBSTATUS_AGUARDA_GESTAO,
    SUBSTATUS_AGUARDA_LICENCA,
    SUBSTATUS_COM_SUPORTE,
    SUBSTATUS_LEGACY_TRIAGEM,
)

FILAS_SUBSTATUSES: tuple[str, ...] = (
    SUBSTATUS_AGUARDA_GESTAO,
    SUBSTATUS_LEGACY_TRIAGEM,
    SUBSTATUS_COM_SUPORTE,
    "Aguardando Cliente",
    SUBSTATUS_AGUARDA_CONTRATADA,
    SUBSTATUS_AGUARDA_LICENCA,
    "Aguardando Config. Remota",
    "Em Configuração Remota",
    "Aguardando Config. MPLS",
    "Em Configuração do MPLS",
    "Aguardando Caderno de Teste",
    "Em Caderno de Teste",
)

_FINAL_STATUS_SQL = tuple(sorted(FINAL_STATUSES_ATENDIMENTO))

_CARD_MODES = frozenset({
    "migrados",
    "aguardando-cliente",
    "aguarda-contratada",
    "aguarda-licenca",
    "agendados",
    "aguarda-gestao",
    "filas-ativas",
})

DT_COL_SQL: dict[int, str] = {
    0: "id_vgr",
    1: "contratada",
    2: "data_agendamento",
    3: "hora_agendamento",
    4: "data_atendimento",
    5: "acronimo",
    6: "endereco",
    7: "municipio",
    8: "status_atendimento",
    9: "substatus_atendimento",
    10: "analista_atuante",
    11: "analista_configuracao",
    12: "analista_mpls_atendimentos",
    13: "analista_caderno_teste",
    14: "ultimo_substatus_log",
    15: "data_atendimento",
    17: "_sort_lista",
}

_DT_SEARCHABLE_COLS = tuple(
    col for idx, col in DT_COL_SQL.items() if idx not in (14, 15)
)

_CARD_FILTER_RE = re.compile(r"^(mode|status|substatus):(.+)$")

_MAX_PAGE_LENGTH = 500


def list_server_side_enabled() -> bool:
    """Padrão desligado: ~1–2k linhas filtram instantâneo no cliente (KPI + ColumnControl)."""
    raw = (os.getenv("PRODESP_ATENDIMENTOS_LIST_SERVER_SIDE") or "0").strip().lower()
    return raw not in ("0", "false", "no", "off")


def default_list_scope() -> str:
    return (os.getenv("PRODESP_ATENDIMENTOS_LIST_SCOPE_DEFAULT") or "fila").strip().lower()


def effective_scope(requested: str | None, *, is_admin: bool) -> str:
    """Admin: ``= completo (todos os status). Demais: fila ativa por padrão."""
    raw = (requested or "").strip().lower()
    if raw in ("fila", "completo"):
        scope = raw
    elif is_admin:
        scope = "completo"
    else:
        scope = default_list_scope() or "fila"
        if scope not in ("fila", "completo"):
            scope = "fila"
    if scope == "completo" and not is_admin:
        scope = "fila"
    return scope


def parse_col_search_values(raw: str) -> list[str]:
    """Normaliza busca de coluna enviada pelo DataTables (regex ^…$, alternância |)."""
    v = (raw or "").strip()
    if not v:
        return []
    if v.startswith("^"):
        v = v[1:]
    if v.endswith("$"):
        v = v[:-1]
    if v.startswith("(") and v.endswith(")"):
        v = v[1:-1]
    parts = re.split(r"(?<!\\)\|", v)
    out: list[str] = []
    for p in parts:
        s = p.replace("\\", "").strip()
        if s:
            out.append(s)
    return out


def sql_cte_ultimo_substatus_log_agg() -> str:
    return """
    ult_sub_log_agg AS (
        SELECT
            id_atendimentos AS id_atend,
            substatus_nome AS sub_nome,
            MAX(ts) AS ultimo_ts
        FROM (
            SELECT
                s.id_atendimentos_log AS id_atendimentos,
                TRIM(s.valor_novo_log) AS substatus_nome,
                s.alterado_em_log AS ts
            FROM atendimentos_status_log s
            WHERE s.tipo_campo_log = 'substatus'
            UNION ALL
            SELECT
                h.id_registro_afetado_historico,
                TRIM(h.valor_novo_historico),
                h.data_alteracao_historico
            FROM historico h
            WHERE h.tabela_afetada_historico = 'atendimentos'
              AND h.campo_alterado_historico = 'substatus_atendimentos'
        ) _ult_sub_union
        GROUP BY id_atendimentos, substatus_nome
    )
    """


def sql_list_base_from(cte_agg: str | None = None) -> str:
    """Subselect ``lst`` com colunas da grade.

    Com ``PRODESP_SUBSTATUS_DESDE_READ=1`` usa coluna materializada (sem CTE).
    Com ``PRODESP_TEMPO_SNAPSHOT_READ=1`` junta snapshot em vez da view de tempos.
    """
    from prodesp.prodesp.substatus_materializado import COLUMN, read_enabled
    from prodesp.prodesp.tempo_snapshot import tempo_source_table

    tempo_src = tempo_source_table()

    if read_enabled():
        ultimo_expr = f"a.`{COLUMN}` AS ultimo_substatus_log"
        with_prefix = "WITH"
        joins_extra = ""
    else:
        cte = cte_agg if cte_agg is not None else sql_cte_ultimo_substatus_log_agg()
        ultimo_expr = "usa.ultimo_ts AS ultimo_substatus_log"
        with_prefix = f"WITH {cte},"
        joins_extra = """
        LEFT JOIN ult_sub_log_agg usa ON usa.id_atend = v.id_atendimentos
            AND usa.sub_nome = TRIM(v.substatus_atendimentos)"""

    return f"""
    {with_prefix}
    lst AS (
        SELECT
            v.id_unidades AS id_unidade,
            v.id_atendimentos AS id_atendimento,
            v.data_atendimentos AS data_atendimento,
            v.status_atendimentos AS status_atendimento,
            v.substatus_atendimentos AS substatus_atendimento,
            v.analista_atuante_atendimentos AS analista_atuante,
            v.analista_configuracao_atendimentos AS analista_configuracao,
            v.analista_mpls_atendimentos AS analista_mpls_atendimentos,
            v.analista_caderno_teste_atendimentos AS analista_caderno_teste,
            v.horario_inicio_atendimentos AS horario_inicio,
            a.horario_finalizacao_atendimentos AS horario_finalizacao,
            v.endereco_unidades AS endereco,
            u_list.municipio_unidades AS municipio,
            u_list.acronimo_unidades AS acronimo,
            v.id_vgr_unidades AS id_vgr,
            COALESCE(
                NULLIF(TRIM(a.contratada_atendimentos), ''),
                NULLIF(TRIM(u_list.contratada_planejada_unidades), '')
            ) AS contratada,
            u_list.contratada_planejada_unidades AS contratada_planejada_unidades,
            v.data_agendamento_unidades AS data_agendamento,
            v.hora_agendamento_unidades AS hora_agendamento,
            vt.tempo_total_geral AS tempo_total_geral,
            {ultimo_expr}
        FROM vw_agendamentos_e_atendimentos_ativos v
        LEFT JOIN atendimentos a ON a.id_atendimentos = v.id_atendimentos
        LEFT JOIN unidades u_list ON u_list.id_unidades = v.id_unidades
        LEFT JOIN {tempo_src} vt ON vt.id_atendimentos = v.id_atendimentos
        {joins_extra}
    )
    """


def sql_scope_where(scope: str) -> str:
    if scope == "completo":
        return "1=1"
    finals_in = ", ".join(f"'{s}'" for s in _FINAL_STATUS_SQL)
    return f"""(
        lst.id_atendimento IS NULL
        OR TRIM(COALESCE(lst.status_atendimento, '')) = ''
        OR TRIM(lst.status_atendimento) NOT IN ({finals_in})
    )"""


def _filas_in_sql() -> str:
    return ", ".join(f"'{s}'" for s in FILAS_SUBSTATUSES)


def parse_card_filter(card_filter: str | None) -> tuple[str, list[Any]]:
    """Retorna (sql_fragment, params) para filtro de card (whitelist)."""
    raw = (card_filter or "").strip()
    if not raw:
        return "1=1", []

    m = _CARD_FILTER_RE.match(raw)
    if m:
        kind, value = m.group(1), m.group(2).strip()
        if kind == "status" and value:
            return "TRIM(lst.status_atendimento) = %s", [value]
        if kind == "substatus" and value:
            return "TRIM(lst.substatus_atendimento) = %s", [value]

    mode_key = raw.split(":", 1)[1] if raw.startswith("mode:") else raw
    if mode_key not in _CARD_MODES:
        return "1=1", []

    if mode_key == "migrados":
        return (
            "TRIM(lst.status_atendimento) = 'Concluído' "
            "AND TRIM(lst.substatus_atendimento) = 'Concluído'",
            [],
        )
    if mode_key == "aguardando-cliente":
        return (
            "TRIM(lst.status_atendimento) = 'Em Atendimento' "
            "AND TRIM(lst.substatus_atendimento) = 'Aguardando Cliente'",
            [],
        )
    if mode_key == "aguarda-contratada":
        return (
            "TRIM(lst.status_atendimento) = 'Em Atendimento' "
            f"AND TRIM(lst.substatus_atendimento) = '{SUBSTATUS_AGUARDA_CONTRATADA}'",
            [],
        )
    if mode_key == "aguarda-licenca":
        return (
            "TRIM(lst.status_atendimento) = 'Em Atendimento' "
            f"AND TRIM(lst.substatus_atendimento) = '{SUBSTATUS_AGUARDA_LICENCA}'",
            [],
        )
    if mode_key == "agendados":
        return """(
            TRIM(lst.status_atendimento) = 'Agendado'
            OR lst.id_atendimento IS NULL
            OR (
                TRIM(COALESCE(lst.status_atendimento, '')) = ''
                AND (
                    TRIM(lst.substatus_atendimento) = 'Sem atendimento iniciado'
                    OR TRIM(COALESCE(lst.substatus_atendimento, '')) = ''
                )
            )
        )""", []
    if mode_key == "aguarda-gestao":
        return (
            f"TRIM(lst.substatus_atendimento) IN ('Triagem', '{SUBSTATUS_AGUARDA_GESTAO}')",
            [],
        )
    if mode_key == "filas-ativas":
        return f"TRIM(lst.substatus_atendimento) IN ({_filas_in_sql()})", []

    return "1=1", []


def parse_dt_request_args(args: Mapping[str, Any]) -> dict[str, Any]:
    """Parâmetros DataTables server-side + scope/card."""
    try:
        draw = int(args.get("draw") or 0)
    except (TypeError, ValueError):
        draw = 0
    try:
        start = max(0, int(args.get("start") or 0))
    except (TypeError, ValueError):
        start = 0
    try:
        length = int(args.get("length") or 10)
    except (TypeError, ValueError):
        length = 10
    if length == -1:
        length = _MAX_PAGE_LENGTH
    length = max(1, min(length, _MAX_PAGE_LENGTH))

    try:
        order_col = int(args.get("order[0][column]", 16))
    except (TypeError, ValueError):
        order_col = 16
    order_dir = (args.get("order[0][dir]") or "asc").strip().lower()
    if order_dir not in ("asc", "desc"):
        order_dir = "asc"

    global_search = (args.get("search[value]") or "").strip()
    col_searches: dict[int, str] = {}
    for idx in DT_COL_SQL:
        val = (args.get(f"columns[{idx}][search][value]") or "").strip()
        if val:
            col_searches[idx] = val

    card_filter = (args.get("card_filter") or "").strip()
    scope = (args.get("scope") or "").strip().lower() or None

    return {
        "draw": draw,
        "start": start,
        "length": length,
        "order_col": order_col,
        "order_dir": order_dir,
        "global_search": global_search,
        "col_searches": col_searches,
        "card_filter": card_filter,
        "scope": scope,
    }


def _build_filter_clauses(
    scope: str,
    card_filter: str | None,
    global_search: str,
    col_searches: dict[int, str],
) -> tuple[str, list[Any]]:
    parts = [sql_scope_where(scope)]
    params: list[Any] = []

    card_sql, card_params = parse_card_filter(card_filter)
    parts.append(f"({card_sql})")
    params.extend(card_params)

    if global_search:
        like = f"%{global_search}%"
        ors = " OR ".join(f"CAST(lst.{col} AS CHAR) LIKE %s" for col in _DT_SEARCHABLE_COLS)
        parts.append(f"({ors})")
        params.extend([like] * len(_DT_SEARCHABLE_COLS))

    for idx, val in col_searches.items():
        col = DT_COL_SQL.get(idx)
        if not col or idx in (13, 14):
            continue
        values = parse_col_search_values(val)
        if not values:
            continue
        if col in ("id_vgr", "status_atendimento", "substatus_atendimento"):
            if len(values) == 1:
                parts.append(f"TRIM(CAST(lst.{col} AS CHAR)) = %s")
                params.append(values[0])
            else:
                placeholders = ", ".join(["%s"] * len(values))
                parts.append(f"TRIM(CAST(lst.{col} AS CHAR)) IN ({placeholders})")
                params.extend(values)
        elif len(values) == 1:
            parts.append(f"CAST(lst.{col} AS CHAR) LIKE %s")
            params.append(f"%{values[0]}%")
        else:
            ors = " OR ".join(f"CAST(lst.{col} AS CHAR) LIKE %s" for _ in values)
            parts.append(f"({ors})")
            params.extend(f"%{x}%" for x in values)

    return " AND ".join(f"({p})" for p in parts), params


def sql_list_default_order() -> str:
    """Em Atendimento (mais recente) → Agendado → demais."""
    return """
    CASE
      WHEN TRIM(lst.status_atendimento) = 'Em Atendimento' THEN 0
      WHEN lst.id_atendimento IS NULL OR TRIM(lst.status_atendimento) = 'Agendado' THEN 1
      ELSE 2
    END ASC,
    lst.data_atendimento DESC,
    lst.horario_inicio DESC
    """


def build_paginated_query(
    scope: str,
    *,
    start: int,
    length: int,
    order_col: int,
    order_dir: str,
    global_search: str = "",
    col_searches: Optional[dict[int, str]] = None,
    card_filter: str | None = None,
) -> tuple[str, list[Any]]:
    col_searches = col_searches or {}
    where_sql, params = _build_filter_clauses(scope, card_filter, global_search, col_searches)
    if order_col == 16:
        order_sql = sql_list_default_order()
    else:
        order_field = DT_COL_SQL.get(order_col, "data_atendimento")
        order_sql = f"lst.{order_field} {order_dir.upper()}"
        if order_col == 4:
            order_sql = f"lst.data_atendimento {order_dir.upper()}, lst.horario_inicio {order_dir.upper()}"

    cte = sql_cte_ultimo_substatus_log_agg()
    base = sql_list_base_from(cte)
    query = f"""
    {base}
    SELECT * FROM lst
    WHERE {where_sql}
    ORDER BY {order_sql}
    LIMIT %s OFFSET %s
    """
    return query, [*params, length, start]


def build_count_query(
    scope: str,
    *,
    global_search: str = "",
    col_searches: Optional[dict[int, str]] = None,
    card_filter: str | None = None,
) -> tuple[str, list[Any]]:
    col_searches = col_searches or {}
    where_sql, params = _build_filter_clauses(scope, card_filter, global_search, col_searches)
    cte = sql_cte_ultimo_substatus_log_agg()
    base = sql_list_base_from(cte)
    scope_only = sql_scope_where(scope)
    query = f"""
    {base}
    SELECT
        (SELECT COUNT(*) FROM lst WHERE ({scope_only})) AS records_total,
        (SELECT COUNT(*) FROM lst WHERE {where_sql}) AS records_filtered
    """
    return query, params


def build_full_list_query(scope: str) -> tuple[str, list[Any]]:
    where_sql = sql_scope_where(scope)
    cte = sql_cte_ultimo_substatus_log_agg()
    base = sql_list_base_from(cte)
    query = f"""
    {base}
    SELECT * FROM lst
    WHERE {where_sql}
    ORDER BY {sql_list_default_order()}
    """
    return query, []


def build_rows_by_ids_query(ids: list[int]) -> tuple[str, list[Any]]:
    """Linhas slim da grade para IDs de atendimento (sem filtro de scope)."""
    clean = []
    seen = set()
    for raw in ids:
        try:
            n = int(raw)
        except (TypeError, ValueError):
            continue
        if n <= 0 or n in seen:
            continue
        seen.add(n)
        clean.append(n)
    if not clean:
        raise ValueError("ids vazio")
    placeholders = ", ".join(["%s"] * len(clean))
    cte = sql_cte_ultimo_substatus_log_agg()
    base = sql_list_base_from(cte)
    query = f"""
    {base}
    SELECT * FROM lst
    WHERE lst.id_atendimento IN ({placeholders})
    """
    return query, clean


def row_in_scope(row: Mapping[str, Any], scope: str) -> bool:
    """Espelha ``sql_scope_where`` em Python (para classificar updated vs removed)."""
    if scope == "completo":
        return True
    st = str(row.get("status_atendimento") or "").strip()
    if not st:
        return True
    return st not in FINAL_STATUSES_ATENDIMENTO


def list_delta_enabled() -> bool:
    """Feature flag — padrão OFF (zero impacto)."""
    raw = (os.getenv("PRODESP_ATENDIMENTOS_LIST_DELTA") or "0").strip().lower()
    return raw not in ("0", "false", "no", "off")


def build_resumo_query() -> str:
    return """
    SELECT
        TRIM(v.substatus_atendimentos) AS substatus,
        COUNT(*) AS cnt
    FROM vw_agendamentos_e_atendimentos_ativos v
    WHERE TRIM(COALESCE(v.substatus_atendimentos, '')) <> ''
    GROUP BY TRIM(v.substatus_atendimentos)
    """


def build_resumo_agendados_query() -> str:
    return """
    SELECT COUNT(*) AS cnt
    FROM vw_agendamentos_e_atendimentos_ativos v
    WHERE TRIM(COALESCE(v.status_atendimentos, '')) = 'Agendado'
    """


def resumo_from_substatus_rows(rows: list[dict[str, Any]], *, agendados: int = 0) -> dict[str, Any]:
    substatus_stats: dict[str, int] = defaultdict(int)
    for row in rows:
        sub = (row.get("substatus") or "").strip()
        if sub:
            substatus_stats[sub] += int(row.get("cnt") or 0)
    total_geral_fila = sum(substatus_stats.get(s, 0) for s in FILAS_SUBSTATUSES)
    return {
        "total_geral": total_geral_fila,
        "agendados": agendados,
        "substatus_counts": dict(substatus_stats),
    }


def slim_list_row(row: dict[str, Any]) -> None:
    """Remove campos internos não usados na grade (P3 payload)."""
    row.pop("horario_finalizacao", None)
    row.pop("tempo_total_geral", None)
    row.pop("id_unidade", None)
