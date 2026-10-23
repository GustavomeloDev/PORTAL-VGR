"""Projeção explícita de unidades / equipamentos / links (P3-01) — sem ``SELECT *``.

Colunas alinhadas ao schema HOST ``prodesp_db`` (2026-07-14). Forms/blueprint
continuam com a linha completa; o ganho é contrato estável se novas colunas pesadas
forem adicionadas (não entram até entrarem na whitelist).
"""

from __future__ import annotations

UNIDADE_TABLE_COLS: tuple[str, ...] = (
    "id_unidades",
    "id_vgr_unidades",
    "id_intragov_unidades",
    "acronimo_unidades",
    "nome_unidades",
    "hostname_unidades",
    "endereco_unidades",
    "numero_unidades",
    "bairro_unidades",
    "municipio_unidades",
    "estado_unidades",
    "complemento_unidades",
    "cep_unidades",
    "latitude_unidades",
    "longitude_unidades",
    "telefone_contato_unidades",
    "email_contato_unidades",
    "data_agendamento_unidades",
    "hora_agendamento_unidades",
    "ip_lan_01_unidades",
    "ip_lan_transito_unidades",
    "loopback_vivo_unidades",
    "loopback_cliente_unidades",
    "ticket_noc_unidades",
    "loopback_on_bgp_unidades",
    "contratada_planejada_unidades",
    "field_planejada_unidades",
    "contato_field_planejada_unidades",
    "mv_ip_transito_unidades",
    "mv_mask_transito_unidades",
    "mv_ip_swt_unidades",
    "mv_rede_voz_unidades",
    "mv_mask_voz_unidades",
    "mv_rede_lan_assoc_unidades",
    "mv_mask_lan_assoc_unidades",
    "mv_rede_totem_unidades",
    "mv_mask_totem_unidades",
    "mv_ip_lan_sec_unidades",
    "mv_rede_lan_sec_unidades",
    "mv_ip_lan_ter_unidades",
    "mv_rede_lan_ter_unidades",
    "mv_ip_lan_qua_unidades",
    "mv_rede_lan_qua_unidades",
    "mv_rede_wifi_guest_unidades",
    "mv_ip_wifi_guest_unidades",
    "mv_dhcp_start_wifi_guest_unidades",
    "mv_dhcp_end_wifi_guest_unidades",
    "mv_reserva_start_wifi_guest_unidades",
    "mv_reserva_end_wifi_guest_unidades",
)

EQUIPAMENTO_TABLE_COLS: tuple[str, ...] = (
    "id_equipamentos",
    "id_unidades_equipamentos",
    "id_vgr_equipamentos",
    "modelo_equipamentos",
    "serial_equipamentos",
    "mac_equipamentos",
    "licenca_equipamentos",
    "versao_equipamentos",
    "descricao_equipamentos",
    "data_cadastro_equipamentos",
    "deleted_equipamentos",
)

LINK_TABLE_COLS: tuple[str, ...] = (
    "id_link",
    "id_unidades_links",
    "id_vgr_links",
    "status_links",
    "designador_links",
    "tipo_links",
    "operadora_links",
    "ip_wan_links",
    "redundante_critico_links",
    "ip_gateway_links",
    "ip_mascara_links",
    "vlan_links",
    "velocidade_links",
    "pppoe_user_links",
    "pppoe_pass_links",
    "data_ativacao_links",
)


def _sql_cols(cols: tuple[str, ...]) -> str:
    return ", ".join(f"`{c}`" for c in cols)


def sql_select_unidades_by_id_vgr() -> str:
    return f"SELECT {_sql_cols(UNIDADE_TABLE_COLS)} FROM `unidades` WHERE `id_vgr_unidades` = %s"


def sql_select_unidades_by_id() -> str:
    return f"SELECT {_sql_cols(UNIDADE_TABLE_COLS)} FROM `unidades` WHERE `id_unidades` = %s"


def sql_select_equipamentos_by_unidade(*, ativos_only: bool = True, limit_one: bool = False) -> str:
    sql = (
        f"SELECT {_sql_cols(EQUIPAMENTO_TABLE_COLS)} FROM `equipamentos` "
        "WHERE `id_unidades_equipamentos` = %s"
    )
    if ativos_only:
        sql += " AND `deleted_equipamentos` = 0"
    if limit_one:
        sql += " LIMIT 1"
    return sql


def sql_select_links_by_unidade(*, order: bool = False) -> str:
    sql = f"SELECT {_sql_cols(LINK_TABLE_COLS)} FROM `links` WHERE `id_unidades_links` = %s"
    if order:
        sql += " ORDER BY `id_link` ASC"
    return sql


def sql_select_link_by_id_and_unidade() -> str:
    return (
        f"SELECT {_sql_cols(LINK_TABLE_COLS)} FROM `links` "
        "WHERE `id_link` = %s AND `id_unidades_links` = %s"
    )
