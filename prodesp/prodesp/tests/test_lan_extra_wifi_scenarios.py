"""Cenários LAN SEC/TER/QUA + WiFi Guest (create/edit/blueprint) — sem DB.

Cobre regressões tipicas da 1ª leva MV opcionais: mapa JS↔DB, SELECT whitelist,
payload create/update vazio e preenchido, persist blueprint e CSV com stubs vazios.

Rodar (raiz do repo, venv ``.venv_portal_pessoal``):

    .venv_portal_pessoal\\Scripts\\python.exe -m prodesp.prodesp.tests.test_lan_extra_wifi_scenarios
"""
from __future__ import annotations

from pathlib import Path

from prodesp.prodesp.atendimento_business_rules import CREATE_UNIT_JSON_KEYS
from prodesp.prodesp.blueprint.prodesp_csv_generator import (
    _build_blueprint_rede_lan_row_pairs,
    validar_dados_blueprint,
)
from prodesp.prodesp.blueprint.prodesp_routes import _parse_blueprint_unit_updates
from prodesp.prodesp.db_field_limits import (
    BLUEPRINT_UNIT_FORM_FIELDS,
    COLUMN_LIMITS,
    UNIDADES_LAN_EXTRA_SPEC,
    UNIDADES_MV_CIDR_JS_KEYS,
    UNIDADES_MV_OPCIONAIS_SPEC,
    UPDATE_JS_TO_DB,
    sanitize_ip_cidr_field,
    sanitize_plain_ipv4_field,
    unidades_lan_extra_sql_select,
    unidades_mv_opcionais_sql_select,
    validate_create_payload,
    validate_update_field,
)
from prodesp.prodesp.entity_select import UNIDADE_TABLE_COLS

FAILURES: list[str] = []
OK: list[str] = []

_WIFI_JS_KEYS = (
    "mv_rede_wifi_guest",
    "mv_ip_wifi_guest",
    "mv_dhcp_start_wifi_guest",
    "mv_dhcp_end_wifi_guest",
    "mv_reserva_start_wifi_guest",
    "mv_reserva_end_wifi_guest",
)

_LAN_WIFI_FILLED_JS = {
    "mv_ip_lan_sec": "10.152.10.6/24",
    "mv_rede_lan_sec": "10.152.10.0",
    "mv_ip_lan_ter": "10.153.10.6/24",
    "mv_rede_lan_ter": "10.153.10.0",
    "mv_ip_lan_qua": "10.154.10.6/25",
    "mv_rede_lan_qua": "10.154.10.0",
    "mv_rede_wifi_guest": "10.160.10.0",
    "mv_ip_wifi_guest": "10.160.10.10/24",
    "mv_dhcp_start_wifi_guest": "10.160.10.20",
    "mv_dhcp_end_wifi_guest": "10.160.10.50",
    "mv_reserva_start_wifi_guest": "10.160.10.100",
    "mv_reserva_end_wifi_guest": "10.160.10.110",
}

_CSV_EMPTY_HEADERS = (
    "MV_REDE_LAN_SEC",
    "MV_IP_LAN_SEC",
    "MV_MASK_LAN_SEC",
    "MV_REDE_LAN_TER",
    "MV_IP_LAN_TER",
    "MV_MASK_LAN_TER",
    "MV_REDE_LAN_QUA",
    "MV_IP_LAN_QUA",
    "MV_MASK_LAN_QUA",
    "MV_REDE_WIFI_GUEST",
    "MV_IP_WIFI_GUEST",
    "MV_MASK_WIFI_GUEST",
    "MV_DHCP_START_WIFI_GUEST",
    "MV_DHCP_END_WIFI_GUEST",
    "MV_RESERVA_START_WIFI_GUEST",
    "MV_RESERVA_END_WIFI_GUEST",
    "MV_INTF_INET_1",
    "MV_INTF_INET_2",
    "MV_INTF_MPLS_1",
    "MV_INTF_MPLS_2",
    "MV_INTF_LAN",
)


def check_bool(name: str, got: bool, expected: bool = True):
    if got is not expected:
        FAILURES.append(f"{name}: esperava {expected!r}, got {got!r}")
    else:
        OK.append(name)


def check_eq(name: str, got, expected):
    if got != expected:
        FAILURES.append(f"{name}: esperava {expected!r}, got {got!r}")
    else:
        OK.append(name)


def check_none(name: str, got):
    if got is not None:
        FAILURES.append(f"{name}: esperava None, got {got!r}")
    else:
        OK.append(name)


def _all_new_js_keys() -> list[str]:
    return [js for js, *_ in UNIDADES_LAN_EXTRA_SPEC] + list(_WIFI_JS_KEYS)


def _minimal_unidade_obrigatoria(**extra):
    base = {
        "acronimo_unidades": "DETRAN",
        "hostname_unidades": "host-test",
        "ip_lan_01_unidades": "10.14.128.1/24",
        "loopback_cliente_unidades": "10.252.1.1",
        "loopback_on_bgp_unidades": "10.253.1.1",
        "loopback_vivo_unidades": "10.254.1.1",
    }
    base.update(extra)
    return base


def _link_mpls_ok():
    return {
        "tipo_links": "MPLS",
        "operadora_links": "VIVO",
        "id_vgr_links": "123",
        "designador_links": "DES-1",
        "ip_wan_links": "200.1.1.1",
        "ip_gateway_links": "200.1.1.2",
        "ip_mascara_links": "255.255.255.252",
        "velocidade_links": "100",
    }


def test_whitelist_create_update_select_blueprint():
    """CREATE / UPDATE / SELECT / blueprint form — todos os js/db novos na whitelist."""
    for js, db_col, *_rest in UNIDADES_LAN_EXTRA_SPEC:
        check_bool(f"create keys tem {js}", js in CREATE_UNIT_JSON_KEYS)
        check_eq(f"UPDATE_JS_TO_DB {js}", UPDATE_JS_TO_DB.get(js), ("unidades", db_col))
        check_bool(f"entity_select tem {db_col}", db_col in UNIDADE_TABLE_COLS)
        check_bool(
            f"blueprint form tem {db_col}",
            (db_col, "unidades", db_col) in BLUEPRINT_UNIT_FORM_FIELDS,
        )
        check_bool(f"COLUMN_LIMITS {db_col}", ("unidades", db_col) in COLUMN_LIMITS)

    wifi_by_js = {js: db for js, db, *_ in UNIDADES_MV_OPCIONAIS_SPEC}
    for js in _WIFI_JS_KEYS:
        db_col = wifi_by_js[js]
        check_bool(f"create keys wifi {js}", js in CREATE_UNIT_JSON_KEYS)
        check_eq(f"UPDATE wifi {js}", UPDATE_JS_TO_DB.get(js), ("unidades", db_col))
        check_bool(f"entity_select wifi {db_col}", db_col in UNIDADE_TABLE_COLS)
        check_bool(
            f"blueprint form wifi {db_col}",
            (db_col, "unidades", db_col) in BLUEPRINT_UNIT_FORM_FIELDS,
        )

    lan_sql = unidades_lan_extra_sql_select("u")
    mv_sql = unidades_mv_opcionais_sql_select("u")
    for _, db_col, *_ in UNIDADES_LAN_EXTRA_SPEC:
        check_bool(f"sql select lan {db_col}", db_col in lan_sql)
    for js in _WIFI_JS_KEYS:
        check_bool(f"sql select wifi {wifi_by_js[js]}", wifi_by_js[js] in mv_sql)

    check_eq("lan sec limite 255", COLUMN_LIMITS[("unidades", "mv_ip_lan_sec_unidades")][0], 255)


def test_create_edit_payload_vazio_e_preenchido():
    """Create/edit: campos novos ausentes, vazios ou preenchidos não quebram validação."""
    check_none(
        "create sem campos novos",
        validate_create_payload({"status": "Em Atendimento", "hostname": "h1"}),
    )
    empty = {k: "" for k in _all_new_js_keys()}
    empty["status"] = "Em Atendimento"
    check_none("create campos novos vazios", validate_create_payload(empty))

    filled = {"status": "Em Atendimento", **_LAN_WIFI_FILLED_JS}
    check_none("create campos novos preenchidos", validate_create_payload(filled))

    for js, val in _LAN_WIFI_FILLED_JS.items():
        check_none(f"update field ok {js}", validate_update_field(js, val))
        check_none(f"update field vazio {js}", validate_update_field(js, ""))
        check_none(f"update field None {js}", validate_update_field(js, None))

    too_long_sec = "1" * 256
    err_sec = validate_update_field("mv_ip_lan_sec", too_long_sec)
    check_bool("update lan sec >255 rejeita", err_sec is not None and "LAN SEC" in (err_sec or ""))

    too_long_rede = "1" * 46
    err_rede = validate_update_field("mv_rede_lan_sec", too_long_rede)
    check_bool(
        "update rede lan sec >45 rejeita",
        err_rede is not None and "LAN SEC" in (err_rede or ""),
    )


def test_blueprint_parse_persist_vazio_e_preenchido():
    """_parse_blueprint_unit_updates grava todos os db_cols (vazio e CIDR sanitizado)."""
    empty_form = {}
    updates_empty = _parse_blueprint_unit_updates(empty_form, "")
    for _, db_col, *_ in UNIDADES_LAN_EXTRA_SPEC:
        check_bool(f"parse vazio tem {db_col}", db_col in updates_empty)
    for _, db_col, *_ in UNIDADES_MV_OPCIONAIS_SPEC:
        if db_col.startswith("mv_") and "wifi" in db_col:
            check_bool(f"parse vazio wifi {db_col}", db_col in updates_empty)

    form_filled = {
        "mv_ip_lan_sec_unidades": " 10.152.10.6 / 24 ",
        "mv_rede_lan_sec_unidades": "10.152.10.0",
        "mv_ip_wifi_guest_unidades": "10.160.10.10/24",
        "mv_rede_wifi_guest_unidades": "10.160.10.0 abc",
        "mv_reserva_start_wifi_guest_unidades": "10.160.10.100",
    }
    updates = _parse_blueprint_unit_updates(form_filled, "")
    check_eq(
        "parse cidr lan sec remove espacos",
        updates["mv_ip_lan_sec_unidades"],
        sanitize_ip_cidr_field(" 10.152.10.6 / 24 "),
    )
    check_eq(
        "parse plain wifi remove letras",
        updates["mv_rede_wifi_guest_unidades"],
        sanitize_plain_ipv4_field("10.160.10.0 abc"),
    )
    check_eq(
        "parse cidr wifi guest",
        updates["mv_ip_wifi_guest_unidades"],
        "10.160.10.10/24",
    )


def test_csv_stubs_vazios_e_validacao_opcional():
    """CSV sem campos novos: headers existem e valores vazios; CIDR incompleto rejeita."""
    unidade = _minimal_unidade_obrigatoria()
    eq = {"serial_equipamentos": "FGT40FTK25008428", "modelo_equipamentos": "FortiGate 40F"}
    data = dict(_build_blueprint_rede_lan_row_pairs(unidade, eq, []))
    for hdr in _CSV_EMPTY_HEADERS:
        check_bool(f"csv header presente {hdr}", hdr in data)
        if hdr.startswith("MV_INTF_"):
            continue
        check_eq(f"csv stub vazio {hdr}", data.get(hdr), "")

    ok, erros = validar_dados_blueprint(unidade, eq, [_link_mpls_ok()])
    check_bool("validar blueprint sem lan/wifi ok", ok)
    check_eq("validar blueprint sem erros extra", [e for e in erros if "LAN SEC" in e or "WiFi" in e], [])

    unidade_bad = _minimal_unidade_obrigatoria(mv_ip_lan_sec_unidades="10.1.1.1")
    ok_bad, erros_bad = validar_dados_blueprint(unidade_bad, eq, [_link_mpls_ok()])
    check_bool("validar lan sec sem cidr falha", not ok_bad)
    check_bool(
        "validar lan sec msg cidr",
        any("LAN SEC" in e and "CIDR" in e for e in erros_bad),
    )

    unidade_wifi_bad = _minimal_unidade_obrigatoria(mv_ip_wifi_guest_unidades="10.1.1.1")
    ok_w, erros_w = validar_dados_blueprint(unidade_wifi_bad, eq, [_link_mpls_ok()])
    check_bool("validar wifi sem cidr falha", not ok_w)
    check_bool(
        "validar wifi msg cidr",
        any("WiFi Guest" in e and "CIDR" in e for e in erros_w),
    )

    unidade_ok = _minimal_unidade_obrigatoria(
        mv_ip_lan_sec_unidades="10.152.10.6/24",
        mv_ip_wifi_guest_unidades="10.160.10.10/24",
    )
    ok2, _ = validar_dados_blueprint(unidade_ok, eq, [_link_mpls_ok()])
    check_bool("validar com lan/wifi cidr ok", ok2)

    check_bool("wifi cidr key no set", "mv_ip_wifi_guest" in UNIDADES_MV_CIDR_JS_KEYS)


def test_js_create_edit_details_keys():
    """JS create/edit e details gestão referenciam os mesmos js_keys."""
    root = Path(__file__).resolve().parents[2]
    js_at = (root / "static" / "js" / "script_atendimentos_prodesp.js").read_text(encoding="utf-8")
    js_gestao = (root / "static" / "js" / "script_gestao_atendimentos_prodesp.js").read_text(
        encoding="utf-8"
    )
    for js in _all_new_js_keys():
        check_bool(f"js atendimentos tem {js}", f'"{js}"' in js_at)
        check_bool(f"js gestao details tem {js}", f'"{js}"' in js_gestao)
    check_bool("js PRODESP_LAN_EXTRA_JS_KEYS", "PRODESP_LAN_EXTRA_JS_KEYS" in js_at)
    check_bool("js PRODESP_MV_OPCIONAIS inclui wifi", "mv_ip_wifi_guest" in js_at)


def main() -> int:
    test_whitelist_create_update_select_blueprint()
    test_create_edit_payload_vazio_e_preenchido()
    test_blueprint_parse_persist_vazio_e_preenchido()
    test_csv_stubs_vazios_e_validacao_opcional()
    test_js_create_edit_details_keys()

    print("=== OK (%d) ===" % len(OK))
    for x in OK:
        print(" ", x)
    print("=== FALHAS (%d) ===" % len(FAILURES))
    for x in FAILURES:
        print(" ", x)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
