"""Projeção SQL do dashboard PRODESP (P1-03) — sem ``a.*``.

Whitelist das colunas de ``atendimentos`` e ``unidades`` consumidas pela
grade de gestão, KPIs e relatório periódico. Evita puxar ``logs_atendimentos``
e demais campos pesados/irrelevantes para o hot path.

P3-01: helpers de linha única (perm / update) com opção de omitir ``logs`` (MEDIUMTEXT).
"""

from __future__ import annotations

# Colunas físicas de atendimentos usadas no dashboard / KPIs / e-mail.
ATENDIMENTO_DASHBOARD_COLS: tuple[str, ...] = (
    "id_atendimentos",
    "id_unidades_atendimentos",
    "data_atendimentos",
    "status_atendimentos",
    "substatus_atendimentos",
    "analista_atuante_atendimentos",
    "analista_configuracao_atendimentos",
    "analista_mpls_atendimentos",
    "analista_caderno_teste_atendimentos",
    "contratada_atendimentos",
    "field_atendimentos",
    "contato_field_atendimentos",
    "horario_inicio_atendimentos",
    "horario_finalizacao_atendimentos",
)

# Schema HOST `prodesp_db.atendimentos` (inclui snapshot P0 + logs).
ATENDIMENTO_TABLE_COLS: tuple[str, ...] = (
    "id_atendimentos",
    "id_unidades_atendimentos",
    "data_atendimentos",
    "status_atendimentos",
    "substatus_atendimentos",
    "substatus_desde_atendimentos",
    "analista_atuante_atendimentos",
    "analista_configuracao_atendimentos",
    "analista_mpls_atendimentos",
    "analista_caderno_teste_atendimentos",
    "contratada_atendimentos",
    "field_atendimentos",
    "contato_field_atendimentos",
    "logs_atendimentos",
    "horario_inicio_atendimentos",
    "horario_finalizacao_atendimentos",
)

ATENDIMENTO_COLS_SEM_LOGS: tuple[str, ...] = tuple(
    c for c in ATENDIMENTO_TABLE_COLS if c != "logs_atendimentos"
)

# Fragmentos ``u.col AS alias`` (identidade + endereço + agenda + planejado).
UNIDADE_DASHBOARD_SELECT: str = """
        u.id_unidades AS id_unidades,
        u.acronimo_unidades AS acronimo,
        u.id_vgr_unidades AS id_vgr,
        u.nome_unidades AS nome,
        u.ticket_noc_unidades AS ticket_noc,
        u.endereco_unidades AS endereco,
        u.numero_unidades AS numero,
        u.bairro_unidades AS bairro,
        u.cep_unidades AS cep,
        u.municipio_unidades AS municipio,
        u.estado_unidades AS estado,
        u.complemento_unidades AS complemento,
        u.data_agendamento_unidades AS data_agendamento,
        u.hora_agendamento_unidades AS hora_agendamento,
        u.contratada_planejada_unidades AS contratada_planejada_unidades,
        u.field_planejada_unidades AS field_planejada_unidades,
        u.contato_field_planejada_unidades AS contato_field_planejada_unidades
""".strip()


def sql_atendimento_cols(alias: str = "a") -> str:
    """Lista ``a.col1, a.col2, ...`` para o SELECT do período."""
    a = alias.strip() or "a"
    return ",\n        ".join(f"{a}.`{c}`" for c in ATENDIMENTO_DASHBOARD_COLS)


def sql_select_atendimento_by_id(*, include_logs: bool = True, for_update: bool = False) -> str:
    """SELECT 1 linha por ``id_atendimentos``. Perm checks: ``include_logs=False``."""
    cols = ATENDIMENTO_TABLE_COLS if include_logs else ATENDIMENTO_COLS_SEM_LOGS
    sel = ", ".join(f"`{c}`" for c in cols)
    sql = f"SELECT {sel} FROM `atendimentos` WHERE `id_atendimentos` = %s"
    if for_update:
        sql += " FOR UPDATE"
    return sql


def atendimento_null_base() -> dict:
    """Template das chaves de atendimento para linhas só-agenda."""
    return {c: None for c in ATENDIMENTO_DASHBOARD_COLS}
