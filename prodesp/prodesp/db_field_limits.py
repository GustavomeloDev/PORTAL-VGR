"""
Limites de caracteres alinhados ao schema MySQL PRODESP (unidades, atendimentos, equipamentos, links).
Usado para validação antes do INSERT/UPDATE e mensagens amigáveis ao usuário.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from .link_format_rules import (
    apply_link_identifier_sanitize,
    validate_link_format_fields,
)

# Teto MEDIUMTEXT MySQL para atendimentos.logs_atendimentos (16 777 215 bytes UTF-8, não caracteres).
MYSQL_TEXT_MAX_BYTES = 65535
MYSQL_MEDIUMTEXT_MAX_BYTES = 16777215
LOGS_ATENDIMENTOS_MAX = MYSQL_MEDIUMTEXT_MAX_BYTES

# Campos opcionais Blueprint CSV (MV_*) — js_key, coluna DB, cabeçalho CSV, rótulo UI, max_chars (VARCHAR)
# max_chars: fonte única alinhada a prodesp/sql/016_mv_opcionais_unidades.sql e 017_*.
# WiFi Guest: accordion opcional (016+017). LAN SEC/TER/QUA: UNIDADES_LAN_EXTRA_SPEC (fora do accordion).
UNIDADES_MV_OPCIONAIS_SPEC: tuple[tuple[str, str, str, str, int], ...] = (
    ("mv_ip_transito", "mv_ip_transito_unidades", "MV_IP_TRANSITO", "Lan Trânsito", 45),
    ("mv_mask_transito", "mv_mask_transito_unidades", "MV_MASK_TRANSITO", "Mask Trânsito", 45),
    ("mv_ip_swt", "mv_ip_swt_unidades", "MV_IP_SWT", "SWT", 45),
    ("mv_rede_voz", "mv_rede_voz_unidades", "MV_REDE_VOZ", "Rede Voz", 45),
    ("mv_mask_voz", "mv_mask_voz_unidades", "MV_MASK_VOZ", "Mask Voz", 45),
    ("mv_rede_lan_assoc", "mv_rede_lan_assoc_unidades", "MV_REDE_LAN_ASSOC", "Rede LAN Assoc", 45),
    ("mv_mask_lan_assoc", "mv_mask_lan_assoc_unidades", "MV_MASK_LAN_ASSOC", "Mask LAN Assoc", 45),
    ("mv_rede_totem", "mv_rede_totem_unidades", "MV_REDE_TOTEM", "Rede Totem", 45),
    ("mv_mask_totem", "mv_mask_totem_unidades", "MV_MASK_TOTEM", "Mask Totem", 45),
    ("mv_rede_wifi_guest", "mv_rede_wifi_guest_unidades", "MV_REDE_WIFI_GUEST", "Rede WiFi Guest", 45),
    ("mv_ip_wifi_guest", "mv_ip_wifi_guest_unidades", "MV_IP_WIFI_GUEST", "IP WiFi Guest (CIDR)", 45),
    ("mv_dhcp_start_wifi_guest", "mv_dhcp_start_wifi_guest_unidades", "MV_DHCP_START_WIFI_GUEST", "DHCP Start WiFi Guest", 45),
    ("mv_dhcp_end_wifi_guest", "mv_dhcp_end_wifi_guest_unidades", "MV_DHCP_END_WIFI_GUEST", "DHCP End WiFi Guest", 45),
    ("mv_reserva_start_wifi_guest", "mv_reserva_start_wifi_guest_unidades", "MV_RESERVA_START_WIFI_GUEST", "Reserva Start WiFi Guest", 45),
    ("mv_reserva_end_wifi_guest", "mv_reserva_end_wifi_guest_unidades", "MV_RESERVA_END_WIFI_GUEST", "Reserva End WiFi Guest", 45),
)

# js_keys MV opcionais gravados como CIDR (máscara derivada só no CSV).
UNIDADES_MV_CIDR_JS_KEYS: frozenset[str] = frozenset({"mv_ip_wifi_guest"})

# LAN SEC/TER/QUA — UX junto do IP LAN 1 (não accordion).
# js_key, db_col, csv_ip_or_rede, csv_mask_or_None, label, max_chars, kind ("cidr"|"plain")
UNIDADES_LAN_EXTRA_SPEC: tuple[tuple[str, str, str, str | None, str, int, str], ...] = (
    ("mv_ip_lan_sec", "mv_ip_lan_sec_unidades", "MV_IP_LAN_SEC", "MV_MASK_LAN_SEC", "IP LAN SEC (CIDR)", 255, "cidr"),
    ("mv_rede_lan_sec", "mv_rede_lan_sec_unidades", "MV_REDE_LAN_SEC", None, "Rede LAN SEC", 45, "plain"),
    ("mv_ip_lan_ter", "mv_ip_lan_ter_unidades", "MV_IP_LAN_TER", "MV_MASK_LAN_TER", "IP LAN TER (CIDR)", 45, "cidr"),
    ("mv_rede_lan_ter", "mv_rede_lan_ter_unidades", "MV_REDE_LAN_TER", None, "Rede LAN TER", 45, "plain"),
    ("mv_ip_lan_qua", "mv_ip_lan_qua_unidades", "MV_IP_LAN_QUA", "MV_MASK_LAN_QUA", "IP LAN QUA (CIDR)", 45, "cidr"),
    ("mv_rede_lan_qua", "mv_rede_lan_qua_unidades", "MV_REDE_LAN_QUA", None, "Rede LAN QUA", 45, "plain"),
)

UNIDADES_LAN_EXTRA_DB_COLUMNS: frozenset[str] = frozenset(
    db for _, db, _, _, _, _, _ in UNIDADES_LAN_EXTRA_SPEC
)

UNIDADES_LAN_EXTRA_CIDR_JS_KEYS: frozenset[str] = frozenset(
    js for js, _, _, _, _, _, kind in UNIDADES_LAN_EXTRA_SPEC if kind == "cidr"
)

# Colunas DB gravadas/sanitizadas como IP/CIDR (mantém "/nn").
UNIDADES_CIDR_DB_COLUMNS: frozenset[str] = frozenset(
    {
        "ip_lan_01_unidades",
        "ip_lan_transito_unidades",
        "loopback_vivo_unidades",
        "loopback_cliente_unidades",
        "loopback_on_bgp_unidades",
    }
    | {db for js, db, _, _, _, _, kind in UNIDADES_LAN_EXTRA_SPEC if kind == "cidr"}
    | {db for js, db, _, _, _ in UNIDADES_MV_OPCIONAIS_SPEC if js in UNIDADES_MV_CIDR_JS_KEYS}
)


def _mv_opcionais_column_limits() -> dict[tuple[str, str], tuple[int, str]]:
    """Registra limites MV em COLUMN_LIMITS a partir do spec (evita duplicar max_chars)."""
    return {
        ("unidades", db_col): (max_ch, f"{label} (Blueprint)")
        for _js, db_col, _csv, label, max_ch in UNIDADES_MV_OPCIONAIS_SPEC
    }


def _lan_extra_column_limits() -> dict[tuple[str, str], tuple[int, str]]:
    return {
        ("unidades", db_col): (max_ch, label)
        for _js, db_col, _csv, _mask, label, max_ch, _kind in UNIDADES_LAN_EXTRA_SPEC
    }


UNIDADES_MV_OPCIONAIS_DB_COLUMNS: frozenset[str] = frozenset(
    db for _, db, _, _, _ in UNIDADES_MV_OPCIONAIS_SPEC
)


def unidades_mv_opcionais_js_to_db() -> dict[str, str]:
    return {js: db for js, db, _, _, _ in UNIDADES_MV_OPCIONAIS_SPEC}


def unidades_mv_opcionais_update_js_to_db() -> dict[str, tuple[str, str]]:
    """Mapa js → (tabela, coluna) para validação UPDATE_JS_TO_DB / limites."""
    return {js: ("unidades", db) for js, db, _, _, _ in UNIDADES_MV_OPCIONAIS_SPEC}


def unidades_lan_extra_js_to_db() -> dict[str, str]:
    return {js: db for js, db, _, _, _, _, _ in UNIDADES_LAN_EXTRA_SPEC}


def unidades_lan_extra_update_js_to_db() -> dict[str, tuple[str, str]]:
    return {js: ("unidades", db) for js, db, _, _, _, _, _ in UNIDADES_LAN_EXTRA_SPEC}


def unidades_mv_opcionais_sql_select(prefix: str = "u") -> str:
    """Fragmento SQL: u.col AS js_key para cada campo MV opcional."""
    return ",\n".join(
        f"  {prefix}.{db} AS {js}" for js, db, _, _, _ in UNIDADES_MV_OPCIONAIS_SPEC
    )


def unidades_lan_extra_sql_select(prefix: str = "u") -> str:
    return ",\n".join(
        f"  {prefix}.{db} AS {js}" for js, db, _, _, _, _, _ in UNIDADES_LAN_EXTRA_SPEC
    )


def mv_opcionais_template_fields() -> list[dict[str, object]]:
    """Lista para partial Jinja — derivada de UNIDADES_MV_OPCIONAIS_SPEC (fonte única)."""
    return [
        {
            "db_col": db_col,
            "js_key": js_key,
            "id_suffix": pascalize_js_field(js_key),
            "label": label,
            "csv_col": csv_hdr,
            "max_chars": max_ch,
            "cidr": js_key in UNIDADES_MV_CIDR_JS_KEYS,
        }
        for js_key, db_col, csv_hdr, label, max_ch in UNIDADES_MV_OPCIONAIS_SPEC
    ]


def lan_extra_template_fields() -> list[dict[str, object]]:
    return [
        {
            "db_col": db_col,
            "js_key": js_key,
            "id_suffix": pascalize_js_field(js_key),
            "label": label,
            "csv_col": csv_hdr,
            "csv_mask": csv_mask,
            "max_chars": max_ch,
            "cidr": kind == "cidr",
            "placeholder": "Ex.: 10.152.10.6/24" if kind == "cidr" else "Ex.: 10.152.10.0",
        }
        for js_key, db_col, csv_hdr, csv_mask, label, max_ch, kind in UNIDADES_LAN_EXTRA_SPEC
    ]


def blueprint_mv_opcionais_form_field_limits() -> dict[str, int]:
    limits = {db_col: max_ch for _, db_col, _, _, max_ch in UNIDADES_MV_OPCIONAIS_SPEC}
    limits.update({db_col: max_ch for _, db_col, _, _, _, max_ch, _ in UNIDADES_LAN_EXTRA_SPEC})
    return limits


def truncate_mysql_text_field(text: str, max_bytes: int = MYSQL_TEXT_MAX_BYTES) -> str:
    """Trunca texto para caber em coluna TEXT/MEDIUMTEXT MySQL (limite em bytes UTF-8)."""
    if not text:
        return ""
    raw = str(text).encode("utf-8")
    if len(raw) <= max_bytes:
        return str(text)
    cut = raw[:max_bytes]
    while cut:
        try:
            return cut.decode("utf-8")
        except UnicodeDecodeError:
            cut = cut[:-1]
    return ""

# (tabela, coluna) -> (max_chars, rótulo PT para mensagens)
# Alinhado ao INFORMATION_SCHEMA do ambiente PRODESP (varchar/text).
COLUMN_LIMITS: dict[tuple[str, str], tuple[int, str]] = {
    # --- unidades ---
    ("unidades", "id_vgr_unidades"): (15, "ID VGR"),
    ("unidades", "nome_unidades"): (100, "Nome da unidade"),
    ("unidades", "acronimo_unidades"): (20, "Acrônimo"),
    ("unidades", "hostname_unidades"): (80, "Hostname"),
    ("unidades", "endereco_unidades"): (90, "Endereço"),
    ("unidades", "numero_unidades"): (10, "Número"),
    ("unidades", "complemento_unidades"): (30, "Complemento"),
    ("unidades", "bairro_unidades"): (80, "Bairro"),
    ("unidades", "municipio_unidades"): (80, "Município"),
    ("unidades", "estado_unidades"): (2, "Estado (UF)"),
    ("unidades", "cep_unidades"): (9, "CEP"),
    ("unidades", "telefone_contato_unidades"): (255, "Telefone de contato"),
    ("unidades", "ip_lan_01_unidades"): (45, "IP LAN 01"),
    ("unidades", "ip_lan_transito_unidades"): (45, "IP LAN trânsito"),
    ("unidades", "id_intragov_unidades"): (15, "ID Intragov"),
    ("unidades", "loopback_vivo_unidades"): (45, "Loopback Vivo"),
    ("unidades", "loopback_cliente_unidades"): (45, "Loopback Cliente"),
    ("unidades", "loopback_on_bgp_unidades"): (45, "Loopback BGP"),
    # MV opcionais + LAN extra Blueprint: limites via SPEC (COLUMN_LIMITS.update abaixo)
    ("unidades", "ticket_noc_unidades"): (100, "Ticket NOC"),
    ("unidades", "contratada_planejada_unidades"): (50, "Contratada planejada"),
    ("unidades", "field_planejada_unidades"): (60, "Field planejado"),
    ("unidades", "contato_field_planejada_unidades"): (255, "Contato Field planejado"),
    # --- atendimentos ---
    ("atendimentos", "status_atendimentos"): (30, "Status"),
    ("atendimentos", "substatus_atendimentos"): (30, "Substatus"),
    ("atendimentos", "analista_atuante_atendimentos"): (60, "Analista atuante"),
    ("atendimentos", "analista_configuracao_atendimentos"): (60, "Analista configuração"),
    ("atendimentos", "analista_mpls_atendimentos"): (60, "Analista MPLS"),
    ("atendimentos", "analista_caderno_teste_atendimentos"): (60, "Analista caderno de teste"),
    ("atendimentos", "contratada_atendimentos"): (50, "Contratada"),
    ("atendimentos", "field_atendimentos"): (60, "Field"),
    ("atendimentos", "contato_field_atendimentos"): (255, "Contato Field"),
    ("atendimentos", "logs_atendimentos"): (LOGS_ATENDIMENTOS_MAX, "Logs"),
    # --- equipamentos ---
    ("equipamentos", "modelo_equipamentos"): (50, "Modelo do equipamento"),
    ("equipamentos", "serial_equipamentos"): (50, "Serial do equipamento"),
    ("equipamentos", "versao_equipamentos"): (50, "Versão do equipamento"),
    ("equipamentos", "descricao_equipamentos"): (255, "Descrição do equipamento"),
    # --- links ---
    ("links", "id_vgr_links"): (30, "ID VGR do link"),
    ("links", "designador_links"): (30, "Designador"),
    ("links", "tipo_links"): (100, "Tipo do link"),
    ("links", "operadora_links"): (100, "Operadora"),
    ("links", "vlan_links"): (10, "VLAN"),
    ("links", "ip_wan_links"): (45, "IP WAN"),
    ("links", "redundante_critico_links"): (1, "Redundante Crítico"),
    ("links", "ip_gateway_links"): (45, "IP Gateway"),
    ("links", "ip_mascara_links"): (45, "Máscara IP"),
    ("links", "velocidade_links"): (20, "Velocidade"),
    ("links", "pppoe_user_links"): (255, "Usuário PPPoE"),
    ("links", "pppoe_pass_links"): (255, "Senha PPPoE"),
    # --- observações ---
    ("observacoes", "observacoes"): (65535, "Observação"),
}
COLUMN_LIMITS.update(_mv_opcionais_column_limits())
COLUMN_LIMITS.update(_lan_extra_column_limits())

# Flags / tipos não-VARCHAR em COLUMN_LIMITS (audit INFORMATION_SCHEMA ignora).
COLUMN_LIMITS_NON_VARCHAR: frozenset[tuple[str, str]] = frozenset(
    {
        ("links", "redundante_critico_links"),  # TINYINT(1) 0/1
    }
)

# decimal(10,8) — validação por tamanho da representação textual, não varchar
DECIMAL_COORD_MAX_CHARS = 13

# Campo JS do modal de atendimento -> coluna DB (mesmo mapa de allowed em app.py)
UPDATE_JS_TO_DB: dict[str, tuple[str, str]] = {
    "status": ("atendimentos", "status_atendimentos"),
    "substatus": ("atendimentos", "substatus_atendimentos"),
    "analista_atuante": ("atendimentos", "analista_atuante_atendimentos"),
    "analista_configuracao": ("atendimentos", "analista_configuracao_atendimentos"),
    "analista_mpls_atendimentos": ("atendimentos", "analista_mpls_atendimentos"),
    "analista_caderno_teste": ("atendimentos", "analista_caderno_teste_atendimentos"),
    "contratada": ("atendimentos", "contratada_atendimentos"),
    "field": ("atendimentos", "field_atendimentos"),
    "contato_field": ("atendimentos", "contato_field_atendimentos"),
    "logs": ("atendimentos", "logs_atendimentos"),
    "nome": ("unidades", "nome_unidades"),
    "acronimo": ("unidades", "acronimo_unidades"),
    "hostname": ("unidades", "hostname_unidades"),
    "endereco": ("unidades", "endereco_unidades"),
    "numero": ("unidades", "numero_unidades"),
    "bairro": ("unidades", "bairro_unidades"),
    "municipio": ("unidades", "municipio_unidades"),
    "estado": ("unidades", "estado_unidades"),
    "complemento": ("unidades", "complemento_unidades"),
    "cep": ("unidades", "cep_unidades"),
    "latitude": ("unidades", "latitude_unidades"),
    "longitude": ("unidades", "longitude_unidades"),
    "telefone_contato": ("unidades", "telefone_contato_unidades"),
    "ip_lan_01": ("unidades", "ip_lan_01_unidades"),
    "ip_lan_transito": ("unidades", "ip_lan_transito_unidades"),
    "id_intragov": ("unidades", "id_intragov_unidades"),
    "loopback_vivo": ("unidades", "loopback_vivo_unidades"),
    "loopback_cliente": ("unidades", "loopback_cliente_unidades"),
    "loopback_on_bgp": ("unidades", "loopback_on_bgp_unidades"),
    "ticket_noc": ("unidades", "ticket_noc_unidades"),
}
UPDATE_JS_TO_DB.update(unidades_mv_opcionais_update_js_to_db())
UPDATE_JS_TO_DB.update(unidades_lan_extra_update_js_to_db())

EQUIPAMENTO_JSON_TO_DB: dict[str, tuple[str, str]] = {
    "modelo": ("equipamentos", "modelo_equipamentos"),
    "serial": ("equipamentos", "serial_equipamentos"),
    "versao": ("equipamentos", "versao_equipamentos"),
    "descricao": ("equipamentos", "descricao_equipamentos"),
}

LINK_JSON_TO_DB: dict[str, tuple[str, str]] = {
    "id_vgr": ("links", "id_vgr_links"),
    "designador": ("links", "designador_links"),
    "tipo": ("links", "tipo_links"),
    "operadora": ("links", "operadora_links"),
    "vlan": ("links", "vlan_links"),
    "ip_wan": ("links", "ip_wan_links"),
    "redundante_critico": ("links", "redundante_critico_links"),
    "ip_gateway": ("links", "ip_gateway_links"),
    "ip_mascara": ("links", "ip_mascara_links"),
    "velocidade": ("links", "velocidade_links"),
    "pppoe_user": ("links", "pppoe_user_links"),
    "pppoe_pass": ("links", "pppoe_pass_links"),
}

# Limite de UI para motivo Aguardando Cliente (texto livre, não persiste em coluna dedicada)
AGUARDANDO_CLIENTE_MOTIVO_UI_MAX = 1000

# Limite operacional de textarea de observação no modal (<= coluna TEXT no banco)
OBSERVACAO_UI_MAX = 4000

# Limite operacional de log digitado no modal (<= coluna MEDIUMTEXT no banco)
LOG_UI_MAX = LOGS_ATENDIMENTOS_MAX


def _pair_edit_create(suffix: str, max_len: int) -> dict[str, int]:
    return {f"edit{suffix}": max_len, f"create{suffix}": max_len}


def pascalize_js_field(js_key: str) -> str:
    return "".join(part.capitalize() for part in js_key.split("_"))


def _build_form_element_limits() -> dict[str, int]:
    """Gera maxlength dos modais a partir de COLUMN_LIMITS (fonte única com o backend)."""
    m: dict[str, int] = {}
    js_suffix = {
        "numero": "Numero",
        "endereco": "Endereco",
        "bairro": "Bairro",
        "municipio": "Municipio",
        "estado": "Estado",
        "cep": "Cep",
        "nome": "Nome",
        "acronimo": "Acronimo",
        "hostname": "Hostname",
        "complemento": "Complemento",
        "telefone_contato": "TelefoneContato",
        "id_intragov": "Idintragov",
        "ip_lan_01": "IpLan01",
        "ip_lan_transito": "IpLanTransito",
        "loopback_vivo": "LoopbackVivo",
        "loopback_cliente": "LoopbackCliente",
        "loopback_on_bgp": "LoopbackOnBgp",
        "ticket_noc": "TicketNoc",
        "field": "Field",
        "contato_field": "ContatoField",
        "logs": "LogInput",
    }
    for js_key, _, _, _, _ in UNIDADES_MV_OPCIONAIS_SPEC:
        js_suffix[js_key] = pascalize_js_field(js_key)
    for js_key, _, _, _, _, _, _ in UNIDADES_LAN_EXTRA_SPEC:
        js_suffix[js_key] = pascalize_js_field(js_key)
    for js_key, suffix in js_suffix.items():
        loc = UPDATE_JS_TO_DB.get(js_key)
        if not loc:
            continue
        meta = COLUMN_LIMITS.get(loc)
        if not meta:
            continue
        lim = meta[0]
        ui_max = min(lim, LOG_UI_MAX) if js_key == "logs" else lim
        m.update(_pair_edit_create(suffix, ui_max))

    m.update(_pair_edit_create("Latitude", DECIMAL_COORD_MAX_CHARS))
    m.update(_pair_edit_create("Longitude", DECIMAL_COORD_MAX_CHARS))
    m.update(_pair_edit_create("ObservacaoTexto", OBSERVACAO_UI_MAX))
    m.update(_pair_edit_create("AguardandoClienteMotivo", AGUARDANDO_CLIENTE_MOTIVO_UI_MAX))

    for js_key, suffix in {
        "serial": "EquipamentoSerial",
        "versao": "EquipamentoVersao",
        "descricao": "EquipamentoDescricao",
    }.items():
        loc = EQUIPAMENTO_JSON_TO_DB[js_key]
        meta = COLUMN_LIMITS.get(loc)
        if meta:
            m.update(_pair_edit_create(suffix, meta[0]))

    for js_key, suffix in {
        "id_vgr": "LinkIdVgr",
        "designador": "LinkDesignador",
        "operadora": "LinkOperadora",
        "vlan": "LinkVlan",
        "velocidade": "LinkVelocidade",
        "ip_wan": "LinkIpWan",
        "ip_gateway": "LinkIpGateway",
        "ip_mascara": "LinkIpMascara",
        "pppoe_user": "LinkPppoeUser",
        "pppoe_pass": "LinkPppoePass",
    }.items():
        loc = LINK_JSON_TO_DB[js_key]
        meta = COLUMN_LIMITS.get(loc)
        if meta:
            m.update(_pair_edit_create(suffix, meta[0]))

    return m


FORM_ELEMENT_LIMITS: dict[str, int] = _build_form_element_limits()

_DATA_TOO_LONG_RE = re.compile(
    r"Data too long for column '([^']+)'",
    re.IGNORECASE,
)

# MySQL: Duplicate entry 'VAL' for key 'table.idx_name' (ou só 'idx_name')
_DUP_ENTRY_RE = re.compile(
    r"Duplicate entry ['\"](.+?)['\"] for key ['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)

# Chave UNIQUE → mensagem objetiva (sem stack/SQL cru ao cliente).
_DUP_KEY_MESSAGES: dict[str, str] = {
    "serial_equipamentos": (
        "Número de série «{value}» já está cadastrado em outro equipamento. "
        "Não é permitido repetir o serial FortiGate. "
        "Se acabou de gerar o Blueprint, aguarde e evite clicar de novo (duplo envio)."
    ),
    "idx_serial_equipamentos": (
        "Número de série «{value}» já está cadastrado em outro equipamento. "
        "Não é permitido repetir o serial FortiGate. "
        "Se acabou de gerar o Blueprint, aguarde e evite clicar de novo (duplo envio)."
    ),
    "mac_equipamentos": (
        "MAC «{value}» já está cadastrado em outro equipamento. "
        "Corrija o MAC antes de salvar."
    ),
    "idx_mac_equipamentos": (
        "MAC «{value}» já está cadastrado em outro equipamento. "
        "Corrija o MAC antes de salvar."
    ),
    "id_vgr_unidades": (
        "ID VGR «{value}» já existe em outra unidade. "
        "Não é permitido repetir o ID VGR."
    ),
    "idx_id_vgr_unidades": (
        "ID VGR «{value}» já existe em outra unidade. "
        "Não é permitido repetir o ID VGR."
    ),
}


def _dup_key_basename(key_name: str) -> str:
    """'equipamentos.idx_serial_equipamentos' → 'idx_serial_equipamentos'."""
    raw = (key_name or "").strip()
    if "." in raw:
        return raw.rsplit(".", 1)[-1]
    return raw


def message_from_mysql_duplicate(exc: BaseException) -> Optional[str]:
    """Mensagem amigável para Duplicate entry / UNIQUE (errno 1062/1169)."""
    raw = str(exc).strip()
    m = _DUP_ENTRY_RE.search(raw)
    if not m:
        if getattr(exc, "errno", None) in (1062, 1169) or "duplicate entry" in raw.lower():
            return (
                "Registro duplicado no banco (unicidade). "
                "Verifique serial, MAC, ID VGR, IP/designador/loopback e tente de novo — "
                "evite clicar várias vezes no botão."
            )
        return None
    value, key_name = m.group(1), m.group(2)
    base = _dup_key_basename(key_name)
    if base.upper() == "PRIMARY":
        return (
            "Conflito de chave primária ao salvar (possível duplo envio). "
            "Atualize a tela e confira se o registro já foi gravado."
        )
    tmpl = _DUP_KEY_MESSAGES.get(base) or _DUP_KEY_MESSAGES.get(key_name)
    if tmpl:
        return tmpl.format(value=value)
    pretty = base.replace("idx_", "").replace("_", " ")
    return (
        f"Valor «{value}» já existe no banco (índice «{pretty}»). "
        "Corrija o campo duplicado ou aguarde se acabou de salvar (duplo envio)."
    )

STATIC_WAN_BLOCKED_PREFIXES = ("201.60.", "201.61.")


def _value_has_internal_whitespace(value: Any) -> bool:
    if value is None:
        return False
    return any(ch.isspace() for ch in str(value))


def validate_no_whitespace(value: Any, label: str) -> Optional[str]:
    if _value_has_internal_whitespace(value):
        return (
            f"O campo «{label}» não pode conter espaços. "
            "Remova os espaços e tente novamente."
        )
    return None


def _normalize_ip_compare(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def validate_link_wan_gateway_distinct(
    payload: Mapping[str, Any],
    *,
    link_label: Optional[str] = None,
) -> Optional[str]:
    wan = _normalize_ip_compare(payload.get("ip_wan") or payload.get("ip_wan_links"))
    gw = _normalize_ip_compare(
        payload.get("ip_gateway") or payload.get("ip_gateway_links")
    )
    if not wan or not gw or wan != gw:
        return None
    label = link_label
    if not label:
        tipo = (payload.get("tipo") or payload.get("tipo_links") or "Link").strip()
        des = (payload.get("designador") or payload.get("designador_links") or "").strip()
        label = tipo + (f" — Designador: {des}" if des else "")
    return (
        f"{label}: IP WAN e Gateway não podem ser iguais. "
        "Corrija os campos IP WAN e Gateway."
    )


def validate_static_wan_ip_block(
    ip_wan: Any,
    *,
    label: str = "Link STATIC (SAI-BL)",
) -> Optional[str]:
    ip = _normalize_ip_compare(ip_wan)
    if not ip:
        return None
    if ip.startswith(STATIC_WAN_BLOCKED_PREFIXES):
        display = re.sub(r"\s+", "", str(ip_wan or "").strip())
        return (
            f"{label}: o IP WAN ({display}) pertence ao bloco 201.60/201.61, "
            "que não é válido. Solicite a manobra de IP antes de gerar o Blueprint."
        )
    return None


def validate_links_business_rules_for_blueprint(links: list) -> list[str]:
    """Regras de negócio de links para geração de Blueprint."""
    errors: list[str] = []
    for link in links or []:
        if not isinstance(link, dict):
            continue
        tipo = (link.get("tipo_links") or link.get("tipo") or "").strip().upper()
        prefix = f"Link {tipo}" if tipo else "Link"
        fmt_err = validate_link_format_fields(link)
        if fmt_err:
            errors.append(fmt_err)
        err = validate_link_wan_gateway_distinct(link, link_label=prefix)
        if err:
            errors.append(err)
        if tipo == "STATIC":
            err_blk = validate_static_wan_ip_block(
                link.get("ip_wan_links") or link.get("ip_wan"),
                label=f"{prefix} (SAI-BL)",
            )
            if err_blk:
                errors.append(err_blk)
    return errors


def label_for_column(table: str, column: str) -> str:
    meta = COLUMN_LIMITS.get((table, column))
    if meta:
        return meta[1]
    return column.replace("_", " ").strip()


def limit_for_column(table: str, column: str) -> Optional[int]:
    meta = COLUMN_LIMITS.get((table, column))
    return meta[0] if meta else None


def message_value_too_long(table: str, column: str, value_len: int) -> str:
    label = label_for_column(table, column)
    lim = limit_for_column(table, column)
    if lim is None:
        return f"O campo «{label}» excede o tamanho permitido ({value_len} caracteres)."
    return (
        f"O campo «{label}» aceita no máximo {lim} caracteres "
        f"(você informou {value_len}). Reduza o texto e tente novamente."
    )


def _check_mapped_value(
    mapping: Mapping[str, tuple[str, str]],
    key: str,
    value: Any,
) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if value == "":
        return None
    loc = mapping.get(key)
    if not loc:
        return None
    table, column = loc
    lim = limit_for_column(table, column)
    if lim is not None and len(value) > lim:
        return message_value_too_long(table, column, len(value))
    return None


def normalize_coordinate_for_db(value: Any) -> Optional[str]:
    """
    Normaliza latitude/longitude para DECIMAL MySQL (ponto decimal).
    Aceita vírgula (locale PT-BR). Vazio -> None.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = re.sub(r"\s+", "", s).replace(",", ".")
    from decimal import Decimal, InvalidOperation

    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return format(d, "f")


def validate_coordinate_for_db(value: Any, *, field_label: str = "Latitude/Longitude") -> Optional[str]:
    """Retorna mensagem de erro ou None se vazio/válido."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    len_err = validate_coordinate_text(value)
    if len_err:
        return len_err.replace("Latitude/Longitude", field_label)
    if normalize_coordinate_for_db(value) is None:
        return (
            f"O campo «{field_label}» deve ser um número decimal válido "
            "(use ponto ou vírgula como separador decimal)."
        )
    return None


def validate_coordinate_text(value: Any) -> Optional[str]:
    """decimal(10,8) — tamanho máximo da representação em texto."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) > DECIMAL_COORD_MAX_CHARS:
        return (
            f"O campo «Latitude/Longitude» aceita no máximo {DECIMAL_COORD_MAX_CHARS} caracteres "
            f"(você informou {len(s)})."
        )
    return None


def validate_column_text(table: str, column: str, value: Any) -> Optional[str]:
    """Valida tamanho de um valor contra COLUMN_LIMITS."""
    if value is None:
        return None
    s = str(value).strip() if not isinstance(value, str) else value.strip()
    if not s:
        return None
    lim = limit_for_column(table, column)
    if lim is not None and len(s) > lim:
        return message_value_too_long(table, column, len(s))
    return None


# Campos do formulário Gerar Blueprint → (tabela, coluna)
BLUEPRINT_UNIT_FORM_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("acronimo_unidades", "unidades", "acronimo_unidades"),
    ("hostname_unidades", "unidades", "hostname_unidades"),
    ("ip_lan_01_unidades", "unidades", "ip_lan_01_unidades"),
    ("loopback_vivo_unidades", "unidades", "loopback_vivo_unidades"),
    ("loopback_cliente_unidades", "unidades", "loopback_cliente_unidades"),
    ("loopback_on_bgp_unidades", "unidades", "loopback_on_bgp_unidades"),
    ("mpls_ip_gateway", "unidades", "ip_lan_transito_unidades"),
) + tuple(
    (db_col, "unidades", db_col) for _, db_col, _, _, _ in UNIDADES_MV_OPCIONAIS_SPEC
) + tuple(
    (db_col, "unidades", db_col) for _, db_col, _, _, _, _, _ in UNIDADES_LAN_EXTRA_SPEC
)

BLUEPRINT_LINK_FORM_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("operadora", "operadora_links"),
    ("id_vgr", "id_vgr_links"),
    ("designador", "designador_links"),
    ("ip_wan", "ip_wan_links"),
    ("ip_gateway", "ip_gateway_links"),
    ("ip_mascara", "ip_mascara_links"),
    ("vlan", "vlan_links"),
    ("velocidade", "velocidade_links"),
)


def validate_blueprint_form_limits(form) -> list[str]:
    """Valida tamanhos dos campos editáveis na tela Gerar Blueprint."""
    errors: list[str] = []
    errors.extend(validate_blueprint_form_business_rules(form))
    for form_name, table, column in BLUEPRINT_UNIT_FORM_FIELDS:
        err = validate_column_text(table, column, form.get(form_name))
        if err:
            errors.append(err)
    for form_name, table, column in (
        ("serial_equipamentos", "equipamentos", "serial_equipamentos"),
        ("versao_equipamentos", "equipamentos", "versao_equipamentos"),
    ):
        err = validate_column_text(table, column, form.get(form_name))
        if err:
            errors.append(err)
    for prefix in ("mpls", "static"):
        for suffix, column in BLUEPRINT_LINK_FORM_SUFFIXES:
            err = validate_column_text("links", column, form.get(f"{prefix}_{suffix}"))
            if err:
                errors.append(err)
    return errors


def validate_blueprint_form_business_rules(form: Mapping[str, Any]) -> list[str]:
    """Regras de negócio do formulário Gerar Blueprint (espaços, WAN/Gateway, bloco STATIC)."""
    errors: list[str] = []
    for name, label in (
        ("acronimo_unidades", "Sigla Secretaria (Acrônimo)"),
        ("hostname_unidades", "Hostname"),
        ("latitude_unidades", "Latitude"),
        ("longitude_unidades", "Longitude"),
        ("loopback_vivo_unidades", "Loopback Vivo"),
        ("loopback_cliente_unidades", "Loopback Cliente"),
        ("loopback_on_bgp_unidades", "Loopback On BGP"),
        ("serial_equipamentos", "Serial Number"),
        ("versao_equipamentos", "Versão do equipamento (FortiOS)"),
        ("mpls_designador", "Designador (MPLS)"),
        ("static_designador", "Designador (STATIC)"),
    ):
        err = validate_no_whitespace(form.get(name), label)
        if err:
            errors.append(err)

    for prefix, tipo in (("mpls", "MPLS"), ("static", "STATIC")):
        link_payload = {
            "tipo_links": tipo,
            "operadora_links": form.get(f"{prefix}_operadora"),
            "designador_links": form.get(f"{prefix}_designador"),
            "id_vgr_links": form.get(f"{prefix}_id_vgr"),
            "ip_wan_links": form.get(f"{prefix}_ip_wan"),
            "ip_gateway_links": form.get(f"{prefix}_ip_gateway"),
        }
        fmt_err = validate_link_format_fields(link_payload)
        if fmt_err:
            errors.append(fmt_err)
        wan = _normalize_ip_compare(link_payload.get("ip_wan_links"))
        gw = _normalize_ip_compare(link_payload.get("ip_gateway_links"))
        if wan or gw:
            err = validate_link_wan_gateway_distinct(
                link_payload, link_label=f"Link {tipo}"
            )
            if err:
                errors.append(err)
        if tipo == "STATIC" and wan:
            err_blk = validate_static_wan_ip_block(
                form.get(f"{prefix}_ip_wan"),
                label=f"Link {tipo} (SAI-BL)",
            )
            if err_blk:
                errors.append(err_blk)
    return errors


def blueprint_form_field_limits_for_template() -> dict[str, int]:
    """maxlength dos inputs em prodesp_criar_blueprint.html."""
    limits: dict[str, int] = {}
    for form_name, table, column in BLUEPRINT_UNIT_FORM_FIELDS:
        lim = limit_for_column(table, column)
        if lim is not None:
            limits[form_name] = lim
    for form_name, table, column in (
        ("serial_equipamentos", "equipamentos", "serial_equipamentos"),
        ("versao_equipamentos", "equipamentos", "versao_equipamentos"),
    ):
        lim = limit_for_column(table, column)
        if lim is not None:
            limits[form_name] = lim
    for prefix in ("mpls", "static"):
        for suffix, column in BLUEPRINT_LINK_FORM_SUFFIXES:
            lim = limit_for_column("links", column)
            if lim is not None:
                limits[f"{prefix}_{suffix}"] = lim
    return limits


def validate_update_field(js_field: str, value: Any) -> Optional[str]:
    no_ws_labels = {
        "hostname": "Hostname",
        "acronimo": "Sigla Secretaria (Acrônimo)",
        "latitude": "Latitude",
        "longitude": "Longitude",
        "loopback_vivo": "Loopback Vivo",
        "loopback_cliente": "Loopback Cliente",
        "loopback_on_bgp": "Loopback On BGP",
    }
    if js_field in no_ws_labels:
        err = validate_no_whitespace(value, no_ws_labels[js_field])
        if err:
            return err
    if js_field in ("latitude", "longitude"):
        return validate_coordinate_text(value)
    if js_field == "ticket_noc":
        from .ticket_noc_validation import validate_ticket_noc_format

        s = str(value or "").strip()
        if s:
            return validate_ticket_noc_format(value, obrigatorio=False)
        return None
    return _check_mapped_value(UPDATE_JS_TO_DB, js_field, value)


def validate_observacao_text(text: Any) -> Optional[str]:
    if text is None:
        return None
    s = text if isinstance(text, str) else str(text)
    db_lim = limit_for_column("observacoes", "observacoes")
    if db_lim is None:
        return None
    if len(s) > db_lim:
        return message_value_too_long("observacoes", "observacoes", len(s))
    return None


def validate_equipamento_fields(payload: Mapping[str, Any]) -> Optional[str]:
    for key, label in (
        ("serial", "Serial Number"),
        ("versao", "Versão do equipamento (FortiOS)"),
    ):
        err = validate_no_whitespace(payload.get(key), label)
        if err:
            return err
    for key in EQUIPAMENTO_JSON_TO_DB:
        err = _check_mapped_value(EQUIPAMENTO_JSON_TO_DB, key, payload.get(key))
        if err:
            return err
    return None


def _link_field_str(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        raw = payload.get(key)
        if raw is None:
            continue
        s = str(raw).strip()
        if s:
            return s
    return ""


def validate_link_required_fields(payload: Mapping[str, Any]) -> Optional[str]:
    """
    Campos obrigatórios ao cadastrar/editar link (atendimento, admin, create).
    Sempre: Tipo, Operadora, Designador, Velocidade.
    Por tipo: MPLS/STATIC → WAN/Gateway/Máscara (+ ID VGR se VIVO);
    PPPoE → usuário/senha; DHCP → só os comuns.
    """
    tipo = _link_field_str(payload, "tipo", "tipo_links").upper()
    operadora = _link_field_str(payload, "operadora", "operadora_links")
    designador = _link_field_str(payload, "designador", "designador_links")
    velocidade = _link_field_str(payload, "velocidade", "velocidade_links")

    missing: list[str] = []
    if not tipo:
        missing.append("Tipo")
    if not operadora:
        missing.append("Operadora")
    if not designador:
        missing.append("Designador")
    if not velocidade:
        missing.append("Velocidade")

    if tipo in ("MPLS", "STATIC"):
        if not _link_field_str(payload, "ip_wan", "ip_wan_links"):
            missing.append("IP WAN")
        if not _link_field_str(payload, "ip_gateway", "ip_gateway_links"):
            missing.append("IP Gateway")
        if not _link_field_str(payload, "ip_mascara", "ip_mascara_links"):
            missing.append("IP Máscara")
        if operadora.upper() == "VIVO" and not _link_field_str(
            payload, "id_vgr", "id_vgr_links"
        ):
            missing.append("ID VGR do link (obrigatório para VIVO)")
    elif tipo == "PPPOE":
        if not _link_field_str(payload, "pppoe_user", "pppoe_user_links"):
            missing.append("PPPoE User")
        if not _link_field_str(payload, "pppoe_pass", "pppoe_pass_links"):
            missing.append("PPPoE Password")

    if missing:
        return (
            "Campos obrigatórios do link não preenchidos: "
            + ", ".join(missing)
            + "."
        )
    return None


def validate_link_fields(payload: Mapping[str, Any]) -> Optional[str]:
    # Colagem de planilha: ZWSP/aspas/BOM — limpa in-place quando o payload é dict mutável.
    if isinstance(payload, dict):
        apply_link_identifier_sanitize(payload)
    err = validate_no_whitespace(payload.get("designador"), "Designador")
    if err:
        return err
    for key in LINK_JSON_TO_DB:
        # Flag TINYINT 0/1 — não validar como texto (bool True → "True" = 4 chars)
        if key == "redundante_critico":
            continue
        err = _check_mapped_value(LINK_JSON_TO_DB, key, payload.get(key))
        if err:
            return err
    err = validate_link_required_fields(payload)
    if err:
        return err
    err = validate_link_format_fields(payload)
    if err:
        return err
    tipo = (payload.get("tipo") or payload.get("tipo_links") or "").strip().upper()
    des = (payload.get("designador") or payload.get("designador_links") or "").strip()
    link_label = f"Link {tipo}" if tipo else "Link"
    if des:
        link_label += f" — Designador: {des}"
    err = validate_link_wan_gateway_distinct(payload, link_label=link_label)
    if err:
        return err
    if tipo == "STATIC":
        err_blk = validate_static_wan_ip_block(
            payload.get("ip_wan") or payload.get("ip_wan_links"),
            label=f"{link_label} (SAI-BL)",
        )
        if err_blk:
            return err_blk
    return None


def message_from_mysql_exception(exc: BaseException) -> tuple[str, bool]:
    """
    Converte exceção MySQL em mensagem para o usuário.
    Retorna (mensagem, is_client_error).
    """
    raw = str(exc).strip()
    errno = getattr(exc, "errno", None)

    m = _DATA_TOO_LONG_RE.search(raw)
    if m or errno == 1406:
        col = m.group(1) if m else None
        if col:
            for (table, column), (lim, label) in COLUMN_LIMITS.items():
                if column == col:
                    return (
                        f"O campo «{label}» aceita no máximo {lim} caracteres. "
                        "Reduza o texto e tente novamente.",
                        True,
                    )
            pretty = col.replace("_", " ").replace(" unidades", "").replace(" atendimentos", "")
            return (
                f"O campo «{pretty}» excede o tamanho permitido no banco de dados. "
                "Reduza o texto e tente novamente.",
                True,
            )
        return (
            "Um ou mais campos excedem o tamanho máximo permitido. "
            "Revise os textos informados e tente novamente.",
            True,
        )

    if errno in (1062, 1169) or "duplicate entry" in raw.lower():
        dup_msg = message_from_mysql_duplicate(exc)
        return (
            dup_msg
            or (
                "Registro duplicado no banco. "
                "Verifique os dados e evite clicar várias vezes no botão."
            ),
            True,
        )

    if errno in (1216, 1217, 1451, 1452):
        return (
            "Não foi possível salvar: há vínculo com outro registro no banco "
            "(chave estrangeira). Confira se a unidade/equipamento/link ainda existe "
            "e tente novamente.",
            True,
        )

    if errno == 1205 or "lock wait timeout" in raw.lower():
        return (
            "O banco está ocupado com outra operação (timeout de lock). "
            "Aguarde alguns segundos e tente novamente — evite clicar várias vezes em Confirmar.",
            True,
        )

    if raw.lower().startswith("erro interno:"):
        raw = raw.split(":", 1)[1].strip()

    if _DATA_TOO_LONG_RE.search(raw):
        return message_from_mysql_exception(Exception(raw))

    return (
        "Não foi possível salvar os dados. Tente novamente ou contate o suporte se persistir.",
        False,
    )


def validate_estado_unidade(value: Any) -> Optional[str]:
    """UF com 2 letras; rejeita corte silencioso de valores inválidos."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) == 2 and s.isalpha():
        return None
    return "O campo «Estado (UF)» deve ter exatamente 2 letras (ex.: SP)."


def normalize_estado_unidade(value: Any) -> Optional[str]:
    err = validate_estado_unidade(value)
    if err:
        return None
    s = str(value).strip()
    return s.upper() if s else None


def sanitize_ip_cidr_field(value: Any) -> Any:
    """Remove espaços em IP/CIDR sem alterar o prefixo (ex.: /23 permanece /23)."""
    if value is None:
        return value
    if not isinstance(value, str):
        value = str(value)
    stripped = re.sub(r"\s+", "", value, flags=re.UNICODE)
    return stripped if stripped else value


def sanitize_plain_ipv4_field(value: Any) -> Any:
    """IPv4 ou máscara dotted-decimal: remove espaços e caracteres que não sejam dígito ou ponto."""
    if value is None:
        return value
    if not isinstance(value, str):
        value = str(value)
    stripped = re.sub(r"\s+", "", value, flags=re.UNICODE)
    return re.sub(r"[^0-9.]", "", stripped)


def validate_create_payload(data: Mapping[str, Any]) -> Optional[str]:
    """Valida tamanhos no POST /atendimentos/create (unidade + atendimento + filhos)."""
    from .atendimento_business_rules import CREATE_ATENDIMENTO_JSON_KEYS, CREATE_UNIT_JSON_KEYS

    for key in CREATE_UNIT_JSON_KEYS:
        if key in data:
            err = validate_update_field(key, data.get(key))
            if err:
                return err
    for key in CREATE_ATENDIMENTO_JSON_KEYS:
        if key in data:
            err = validate_update_field(key, data.get(key))
            if err:
                return err
    for obs in data.get("new_observacoes") or []:
        if isinstance(obs, dict):
            err = validate_observacao_text(obs.get("observacao_prodesp"))
            if err:
                return err
    for eq in data.get("new_equipamentos") or []:
        if isinstance(eq, dict):
            err = validate_equipamento_fields(eq)
            if err:
                return err
    for lnk in data.get("new_links") or []:
        if isinstance(lnk, dict):
            err = validate_link_fields(lnk)
            if err:
                return err
    return None


def form_field_limits_for_template() -> dict[str, int]:
    return dict(FORM_ELEMENT_LIMITS)


def audit_mv_opcionais_spec(
    schema_limits: Mapping[tuple[str, str], int] | None = None,
) -> list[str]:
    """
    Valida UNIDADES_MV_OPCIONAIS_SPEC vs COLUMN_LIMITS / UPDATE_JS_TO_DB
    (e opcionalmente CHARACTER_MAXIMUM_LENGTH do INFORMATION_SCHEMA).
    """
    failures: list[str] = []
    seen_db: set[str] = set()
    mv_update = unidades_mv_opcionais_update_js_to_db()

    for js, db_col, _csv, _label, max_spec in UNIDADES_MV_OPCIONAIS_SPEC:
        if db_col in seen_db:
            failures.append(f"UNIDADES_MV_OPCIONAIS_SPEC coluna duplicada: {db_col}")
        seen_db.add(db_col)

        if mv_update.get(js) != ("unidades", db_col):
            failures.append(f"UPDATE_JS_TO_DB diverge do spec MV: {js}")

        meta = COLUMN_LIMITS.get(("unidades", db_col))
        if not meta:
            failures.append(f"COLUMN_LIMITS ausente para MV: unidades.{db_col}")
        elif meta[0] != max_spec:
            failures.append(
                f"MV spec vs COLUMN_LIMITS: unidades.{db_col} spec={max_spec} py={meta[0]}"
            )

        if schema_limits is not None:
            db_lim = schema_limits.get(("unidades", db_col))
            if db_lim is None:
                failures.append(f"MV coluna ausente no banco: unidades.{db_col}")
            elif db_lim != max_spec:
                failures.append(
                    f"MV spec vs schema: unidades.{db_col} spec={max_spec} db={db_lim}"
                )

    return failures


def audit_limits_against_schema(
    schema_limits: Mapping[tuple[str, str], int],
    *,
    tables: tuple[str, ...] = ("unidades", "atendimentos", "equipamentos", "links", "observacoes"),
) -> list[str]:
    """
    Compara COLUMN_LIMITS / FORM_ELEMENT_LIMITS com CHARACTER_MAXIMUM_LENGTH do INFORMATION_SCHEMA.
    Retorna lista de divergências (vazia = OK).
    """
    failures: list[str] = []

    for (table, column), (lim_py, _label) in COLUMN_LIMITS.items():
        if (table, column) in COLUMN_LIMITS_NON_VARCHAR:
            continue
        db_lim = schema_limits.get((table, column))
        if db_lim is None:
            if table in tables:
                failures.append(f"COLUMN_LIMITS sem varchar no banco: {table}.{column}")
        elif lim_py != db_lim:
            failures.append(f"COLUMN_LIMITS diverge: {table}.{column} py={lim_py} db={db_lim}")

    def _form_to_db(element_id: str) -> tuple[str, str] | None:
        for prefix in ("edit", "create"):
            if not element_id.startswith(prefix):
                continue
            suffix = element_id[len(prefix) :]
            if suffix in ("ObservacaoTexto",):
                return "observacoes", "observacoes"
            if suffix in ("AguardandoClienteMotivo",):
                return None
            if suffix in ("Latitude", "Longitude"):
                return None
            equip_map = {
                "EquipamentoSerial": "serial",
                "EquipamentoVersao": "versao",
                "EquipamentoDescricao": "descricao",
            }
            if suffix in equip_map:
                return EQUIPAMENTO_JSON_TO_DB[equip_map[suffix]]
            link_map = {
                "LinkIdVgr": "id_vgr",
                "LinkDesignador": "designador",
                "LinkOperadora": "operadora",
                "LinkVlan": "vlan",
                "LinkVelocidade": "velocidade",
                "LinkIpWan": "ip_wan",
                "LinkIpGateway": "ip_gateway",
                "LinkIpMascara": "ip_mascara",
                "LinkPppoeUser": "pppoe_user",
                "LinkPppoePass": "pppoe_pass",
            }
            if suffix in link_map:
                return LINK_JSON_TO_DB[link_map[suffix]]
            rev = {
                "Numero": "numero",
                "Endereco": "endereco",
                "Bairro": "bairro",
                "Municipio": "municipio",
                "Estado": "estado",
                "Cep": "cep",
                "Nome": "nome",
                "Acronimo": "acronimo",
                "Hostname": "hostname",
                "Complemento": "complemento",
                "TelefoneContato": "telefone_contato",
                "Idintragov": "id_intragov",
                "IpLan01": "ip_lan_01",
                "IpLanTransito": "ip_lan_transito",
                "LoopbackVivo": "loopback_vivo",
                "LoopbackCliente": "loopback_cliente",
                "LoopbackOnBgp": "loopback_on_bgp",
                "TicketNoc": "ticket_noc",
                "Field": "field",
                "ContatoField": "contato_field",
                "LogInput": "logs",
            }
            for js_key, _, _, _, _ in UNIDADES_MV_OPCIONAIS_SPEC:
                rev[pascalize_js_field(js_key)] = js_key
            for js_key, _, _, _, _, _, _ in UNIDADES_LAN_EXTRA_SPEC:
                rev[pascalize_js_field(js_key)] = js_key
            js = rev.get(suffix)
            if js and js in UPDATE_JS_TO_DB:
                return UPDATE_JS_TO_DB[js]
        return None

    for el_id, lim_form in FORM_ELEMENT_LIMITS.items():
        loc = _form_to_db(el_id)
        if loc is None:
            continue
        table, column = loc
        db_lim = schema_limits.get((table, column))
        col_meta = COLUMN_LIMITS.get((table, column))
        if db_lim is None:
            failures.append(f"FORM mapeia coluna inexistente: {el_id} -> {table}.{column}")
            continue
        allowed_ui = db_lim
        if (table, column) == ("observacoes", "observacoes"):
            allowed_ui = min(db_lim, OBSERVACAO_UI_MAX)
        if (table, column) == ("atendimentos", "logs_atendimentos"):
            allowed_ui = min(db_lim, LOG_UI_MAX)
        if lim_form > allowed_ui:
            failures.append(
                f"FORM maior que permitido: {el_id} form={lim_form} max_ui={allowed_ui}"
            )
        if col_meta and lim_form > col_meta[0]:
            failures.append(
                f"FORM maior que COLUMN_LIMITS: {el_id} form={lim_form} py={col_meta[0]}"
            )

    failures.extend(audit_mv_opcionais_spec(schema_limits))

    return failures


def fetch_schema_varchar_limits(
    connection: Any,
    tables: tuple[str, ...] = ("unidades", "atendimentos", "equipamentos", "links", "observacoes"),
) -> dict[tuple[str, str], int]:
    cur = connection.cursor(dictionary=True)
    placeholders = ", ".join(["%s"] * len(tables))
    cur.execute(
        f"""
        SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN ({placeholders})
          AND CHARACTER_MAXIMUM_LENGTH IS NOT NULL
        """,
        tables,
    )
    out = {
        (row["TABLE_NAME"], row["COLUMN_NAME"]): int(row["CHARACTER_MAXIMUM_LENGTH"])
        for row in cur.fetchall()
    }
    cur.close()
    return out
