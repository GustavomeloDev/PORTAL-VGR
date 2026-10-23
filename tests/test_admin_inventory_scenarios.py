"""Cenários admin inventário (equipamentos/links) — sem DB live.

Rodar:

    .venv_portal_pessoal\\Scripts\\python.exe -m prodesp.prodesp.tests.test_admin_inventory_scenarios
"""
from __future__ import annotations

from unittest.mock import MagicMock

from prodesp.prodesp import admin_inventory as inv

FAILURES: list[str] = []
OK: list[str] = []


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


def test_whitelist_order_cols():
    check_bool("eq order whitelist nao vazia", len(inv.EQ_ORDER_WHITELIST) >= 4)
    check_bool("link order whitelist nao vazia", len(inv.LINK_ORDER_WHITELIST) >= 4)
    for col in inv.EQ_ORDER_WHITELIST:
        check_bool(
            f"eq col tem alias {col}",
            col.startswith("e.") or col.startswith("u.") or col.startswith("_att."),
        )
    for col in inv.LINK_ORDER_WHITELIST:
        check_bool(
            f"link col tem alias {col}",
            col.startswith("l.") or col.startswith("u.") or col.startswith("_att."),
        )


def test_dt_args_sanitiza():
    dt = inv._dt_args(
        {
            "draw": "2",
            "start": "-5",
            "length": "9999",
            "search[value]": "  foo ",
            "order[0][column]": "1",
            "order[0][dir]": "DROP",
        }
    )
    check_eq("draw", dt["draw"], 2)
    check_eq("start min 0", dt["start"], 0)
    check_eq("length capped", dt["length"], 200)
    check_eq("search strip", dt["search"], "foo")
    check_eq("order_dir safe", dt["order_dir"], "asc")


def test_client_mode_flag():
    check_bool("mode client", inv._is_client_mode({"mode": "client"}))
    check_bool("mode all", inv._is_client_mode({"mode": "all"}))
    check_bool("mode server default", inv._is_client_mode({}), False)
    check_bool("mode lixo", inv._is_client_mode({"mode": "xyz"}), False)


def test_list_equip_client_mode_mock():
    inv.reset_client_list_cache_for_tests()
    cur = MagicMock()
    list_rows = [
        {
            "id": 1,
            "id_unidade": 10,
            "modelo": "FG",
            "serial": "FGT40FTK2409D6QK",
            "versao": "7",
            "id_vgr": "1",
            "hostname": "h1",
            "acronimo": "A",
            "nome_unidade": "U1",
            "status_ultimo_atendimento": "",
            "analista_caderno_ultimo": "",
        },
        {
            "id": 2,
            "id_unidade": 11,
            "modelo": "FG",
            "serial": "123",
            "versao": "7",
            "id_vgr": "2",
            "hostname": "h2",
            "acronimo": "B",
            "nome_unidade": "U2",
            "status_ultimo_atendimento": "",
            "analista_caderno_ultimo": "",
        },
    ]
    cur.fetchall.return_value = list_rows
    out = inv.list_equipamentos_datatable(cur, {"mode": "client"})
    check_eq("client mode flag", out.get("mode"), "client")
    check_eq("client rows", len(out.get("data") or []), 2)
    check_bool("client slim sem mac", "mac" not in (out["data"][0] or {}))
    check_bool("client slim sem licenca", "licenca" not in (out["data"][0] or {}))
    check_bool("client slim sem descricao", "descricao" not in (out["data"][0] or {}))
    check_eq("fgt padrao ok", out["data"][0].get("fgt_padrao"), 1)
    check_eq("fgt fora", out["data"][1].get("fgt_padrao"), 0)
    check_eq("att list deferred empty", out["data"][0].get("status_ultimo_atendimento"), "")
    check_bool("data_revision presente", "data_revision" in out)
    sql = cur.execute.call_args_list[0][0][0]
    check_bool("client LIMIT unico", "LIMIT %s, %s" not in sql and "LIMIT %s" in sql)
    check_bool("client sem join GROUP_CONCAT", "GROUP_CONCAT" not in sql)
    check_bool("client sql sem mac", "mac_equipamentos" not in sql)
    check_bool("client sql sem licenca", "licenca_equipamentos" not in sql)
    check_bool("client sql sem descricao", "descricao_equipamentos" not in sql)
    check_eq("client execute once", cur.execute.call_count, 1)
    # 2ª chamada com mesma revisão → cache de processo
    out2 = inv.list_equipamentos_datatable(MagicMock(), {"mode": "client"})
    check_bool("client from_cache", out2.get("from_cache") is True)
    # force=1 ignora cache de processo (Atualizar após UPDATE SQL sem bump de revision)
    cur_force = MagicMock()
    cur_force.fetchall.return_value = [
        {
            "id": 99,
            "serial": "FGT60ETK20000001",
            "id_unidade": 1,
            "modelo": "FortiGate 60E",
            "versao": "v7.4.11",
            "id_vgr": "1",
            "hostname": "h99",
            "acronimo": "A",
            "nome_unidade": "U99",
            "status_ultimo_atendimento": "",
            "analista_caderno_ultimo": "",
        }
    ]
    out_force = inv.list_equipamentos_datatable(cur_force, {"mode": "client", "force": "1"})
    check_bool("force bypass cache", out_force.get("from_cache") is not True)
    check_eq("force reconsultou sql", cur_force.execute.call_count, 1)
    check_eq("versao normaliza v prefix", out_force["data"][0].get("versao"), "7.4.11")
    inv.reset_client_list_cache_for_tests()


def test_normalize_versao_equipamento():
    check_eq("versao strip v", inv.normalize_versao_equipamento("v7.4.11"), "7.4.11")
    check_eq("versao strip V", inv.normalize_versao_equipamento("V7.4.11"), "7.4.11")
    check_eq("versao sem prefixo", inv.normalize_versao_equipamento("7.4.11"), "7.4.11")
    check_eq("versao vazia", inv.normalize_versao_equipamento(""), "")


def test_client_unchanged():
    from prodesp.prodesp import data_revision as dr

    dr.reset_for_tests(42)
    out = inv.list_equipamentos_datatable(MagicMock(), {"mode": "client", "since_revision": "42"})
    check_bool("unchanged true", out.get("unchanged") is True)
    check_eq("unchanged rev", out.get("data_revision"), 42)


def test_search_unidades_mock():
    cur = MagicMock()
    cur.fetchall.return_value = [
        {
            "id_unidade": 1,
            "id_vgr": "00321490",
            "acronimo": "CEETEPS",
            "hostname": "host-a",
            "nome": "Paula Souza",
        }
    ]
    rows = inv.search_unidades(cur, "cee", limit=10)
    check_eq("search 1 row", len(rows), 1)
    check_bool("search label", "00321490" in rows[0]["label"] and "CEETEPS" in rows[0]["label"])
    check_eq("search curto vazio", inv.search_unidades(cur, "x"), [])


def test_format_atendimento_timedelta():
    from datetime import date, timedelta, time

    row = inv._format_atendimento_ctx_row(
        {
            "id": 1,
            "data": date(2026, 7, 24),
            "horario_inicio": timedelta(hours=9, minutes=30, seconds=15),
            "status": "Em Andamento",
            "substatus": "Triagem",
            "analista_gestao": "Fulano",
            "analista_config": "Beltrano",
            "analista_caderno": "Sicrano",
            "hora2": time(8, 5, 0),
        }
    )
    check_eq("timedelta→str", row["horario_inicio"], "09:30:15")
    check_eq("date→iso", row["data"], "2026-07-24")
    check_eq("time→str", row["hora2"], "08:05:00")


def test_validate_link_format_fields_vivo():
    from prodesp.prodesp.link_format_rules import (
        sanitize_link_pasted_text,
        validate_link_format_fields,
    )

    ok = validate_link_format_fields(
        {
            "tipo": "MPLS",
            "operadora": "VIVO",
            "designador": "112443547010298",
            "id_vgr": "1737352",
            "velocidade": "100",
            "ip_wan": "10.1.1.1",
            "ip_gateway": "10.1.1.2",
            "ip_mascara": "255.255.255.252",
        }
    )
    check_eq("formato vivo ok", ok, None)
    # Colagem Excel com aspas/BOM/ZWSP — deve aceitar apos sanitize
    ok_paste = validate_link_format_fields(
        {
            "operadora": "VIVO",
            "designador": "\ufeff\"112443547010298\"\u200b",
            "id_vgr": "\u00a0'1737352'",
        }
    )
    check_eq("formato vivo apos paste noise", ok_paste, None)
    check_eq(
        "sanitize remove aspas e zwsp",
        sanitize_link_pasted_text('\u200b"112443547010298"'),
        "112443547010298",
    )
    bad_des = validate_link_format_fields(
        {
            "operadora": "VIVO",
            "designador": "00201723/26",
            "id_vgr": "1737352",
        }
    )
    check_bool("formato des slash", bad_des is not None and "Designador" in bad_des)
    bad_vgr = validate_link_format_fields(
        {
            "operadora": "VIVO",
            "designador": "112443547010298",
            "id_vgr": "00201723/26",
        }
    )
    check_bool("formato vgr slash", bad_vgr is not None and "ID VGR" in bad_vgr)
    other_op = validate_link_format_fields(
        {
            "operadora": "CLARO",
            "designador": "LP_SCM",
            "id_vgr": "",
        }
    )
    check_eq("outra op designador livre", other_op, None)


def test_id_vgr_link_fora_padrao():
    check_bool("vgr ok num", not inv.is_id_vgr_link_fora_padrao("1737352"))
    check_bool("vgr ok zeros", not inv.is_id_vgr_link_fora_padrao("00201723"))
    check_bool("vgr fora slash", inv.is_id_vgr_link_fora_padrao("00201723/26"))
    check_bool("vgr fora curto", inv.is_id_vgr_link_fora_padrao("123456"))
    check_bool("vgr vazio nao fora", not inv.is_id_vgr_link_fora_padrao(""))
    check_bool(
        "flag row",
        inv._link_row_item({"id_vgr_link": "00201863/26", "id_unidade": 1}).get(
            "id_vgr_fora_padrao"
        )
        == 1,
    )


def test_designador_link_fora_padrao():
    check_bool(
        "des ok 15 vivo",
        not inv.is_designador_link_fora_padrao("112443547010298", "VIVO"),
    )
    check_bool(
        "des fora slash vivo",
        inv.is_designador_link_fora_padrao("00201723/26", "VIVO"),
    )
    check_bool(
        "des fora curto vivo",
        inv.is_designador_link_fora_padrao("1234567890", "VIVO"),
    )
    check_bool(
        "des fora letra vivo",
        inv.is_designador_link_fora_padrao("L110633116106690", "VIVO"),
    )
    check_bool(
        "des vazio nao fora",
        not inv.is_designador_link_fora_padrao("", "VIVO"),
    )
    check_bool(
        "des outra op nao aplica",
        not inv.is_designador_link_fora_padrao("00201723/26", "CLARO"),
    )
    check_bool(
        "des sem op nao aplica",
        not inv.is_designador_link_fora_padrao("00201723/26", ""),
    )
    row = inv._link_list_row_item(
        {
            "id": 1,
            "operadora": "VIVO",
            "designador": "00202617/26",
            "id_vgr_link": "1737352",
            "id_unidade": 1,
        }
    )
    check_eq("des flag row vivo", row.get("designador_fora_padrao"), 1)
    check_eq("vgr ok same row", row.get("id_vgr_fora_padrao"), 0)
    row_other = inv._link_list_row_item(
        {
            "id": 2,
            "operadora": "CLARO",
            "designador": "00202617/26",
            "id_vgr_link": "1737352",
            "id_unidade": 1,
        }
    )
    check_eq("des flag outra op", row_other.get("designador_fora_padrao"), 0)

def test_resolve_modelo_from_serial():
    m, err = inv.resolve_modelo_equipamento("FGT40FTK2409D6QK", "FortiGate 900G")
    check_eq("modelo forçado pelo serial", m, "FortiGate 40F")
    check_eq("modelo err none", err, None)
    m2, err2 = inv.resolve_modelo_equipamento("XYZ", "FortiGate 60F")
    check_eq("modelo whitelist ok", m2, "FortiGate 60F")
    check_eq("modelo whitelist err", err2, None)
    m3, err3 = inv.resolve_modelo_equipamento("XYZ", "Qualquer Coisa")
    check_eq("modelo livre bloqueado", m3, "")
    check_bool("modelo livre msg", err3 is not None)
    check_eq(
        "desc firewall",
        inv.resolve_descricao_equipamento("FortiGate 40F", "lixo"),
        "Firewall - Stand Alone",
    )

def test_resolve_unidade_mock():
    cur = MagicMock()
    cur.fetchone.return_value = {"id_unidades": 42}
    uid, err = inv.resolve_unidade_id(cur, id_vgr="00322890")
    check_eq("resolve vgr id", uid, 42)
    check_eq("resolve vgr err", err, None)
    cur.execute.assert_called()

    cur2 = MagicMock()
    cur2.fetchone.return_value = None
    uid2, err2 = inv.resolve_unidade_id(cur2, id_vgr="x")
    check_eq("resolve missing", uid2, None)
    check_bool("resolve missing msg", err2 is not None and "não encontrada" in err2)


def test_create_equip_serial_obrigatorio():
    cur = MagicMock()
    cur.fetchone.return_value = {"id_unidades": 1}
    new_id, changes, err = inv.create_equipamento(cur, {"id_unidade": 1, "serial": ""})
    check_eq("create sem serial id", new_id, None)
    check_eq("create sem serial changes", changes, [])
    check_bool("create sem serial msg", err is not None)


def test_admin_inventory_field_history_diff():
    """Diff 1 linha/campo + máscara de senha PPPoE (sem claro)."""
    changes = inv.collect_field_changes(
        {
            "designador_links": "123456789012345",
            "serial_equipamentos": "OLD",
            "pppoe_pass_links": "segredo1",
            "ip_wan_links": "10.0.0.1",
        },
        {
            "designador_links": "999999999999999",
            "serial_equipamentos": "OLD",
            "pppoe_pass_links": "segredo2",
            "ip_wan_links": "10.0.0.1",
        },
    )
    by_col = {c: (a, n) for c, a, n in changes}
    check_bool("hist tem designador", "designador_links" in by_col)
    check_eq("hist designador antigo", by_col["designador_links"][0], "123456789012345")
    check_eq("hist designador novo", by_col["designador_links"][1], "999999999999999")
    check_bool("hist sem serial igual", "serial_equipamentos" not in by_col)
    check_bool("hist senha mascarada", "pppoe_pass_links" in by_col)
    check_eq("hist pass old mask", by_col["pppoe_pass_links"][0], "(definida)")
    check_eq("hist pass new mask", by_col["pppoe_pass_links"][1], "(redefinida)")
    check_bool(
        "hist senha nao vaza",
        "segredo1" not in str(changes) and "segredo2" not in str(changes),
    )

    xfer = inv.collect_field_changes(
        {"id_unidades_links": 10},
        {"id_unidades_links": 20},
    )
    check_eq("xfer um campo", len(xfer), 1)
    check_eq("xfer col", xfer[0][0], "id_unidades_links")
    check_eq("xfer old", xfer[0][1], 10)
    check_eq("xfer new", xfer[0][2], 20)

    snap = inv.snapshot_field_changes_delete(
        {
            "serial_equipamentos": "FGT40FTK2409D6QK",
            "pppoe_pass_links": "xyz",
            "mac_equipamentos": "",
        },
        ("serial_equipamentos", "pppoe_pass_links", "mac_equipamentos"),
    )
    by_del = {c: a for c, a, n in snap}
    check_eq("delete serial", by_del.get("serial_equipamentos"), "FGT40FTK2409D6QK")
    check_eq("delete pass mask", by_del.get("pppoe_pass_links"), "(definida)")
    check_bool("delete sem mac vazio", "mac_equipamentos" not in by_del)

    cur = MagicMock()
    noop = inv.apply_partial_update(
        cur,
        table="links",
        pk_column="id_link",
        pk_value=10,
        old_map={"designador_links": "A", "ip_wan_links": "1.1.1.1"},
        new_map={"designador_links": "A", "ip_wan_links": "1.1.1.1"},
    )
    check_eq("partial noop vazio", noop, [])
    check_bool("partial noop sem SQL", not cur.execute.called)

    partial = inv.apply_partial_update(
        cur,
        table="links",
        pk_column="id_link",
        pk_value=10,
        old_map={"designador_links": "A", "ip_wan_links": "1.1.1.1"},
        new_map={"designador_links": "B", "ip_wan_links": "1.1.1.1"},
    )
    check_eq("partial um campo", len(partial), 1)
    check_eq("partial col designador", partial[0][0], "designador_links")
    sql = cur.execute.call_args[0][0]
    params = cur.execute.call_args[0][1]
    check_bool("SQL so designador", "designador_links" in sql and "ip_wan_links" not in sql)
    check_eq("params designador e pk", params, ("B", 10))


def test_routes_registered():
    from prodesp import app as app_mod

    check_bool("page equip", hasattr(app_mod, "admin_equipamentos_page"))
    check_bool("page links", hasattr(app_mod, "admin_links_page"))
    check_bool("page bp sec", hasattr(app_mod, "admin_blueprint_secretarias_page"))
    check_bool("api equip", hasattr(app_mod, "api_admin_equipamentos"))
    check_bool("api links", hasattr(app_mod, "api_admin_links"))
    check_bool("api bp sec", hasattr(app_mod, "api_admin_blueprint_secretarias"))
    check_bool("api bp sec item", hasattr(app_mod, "api_admin_blueprint_secretaria_item"))
    check_bool(
        "api bp sec historico",
        hasattr(app_mod, "api_admin_blueprint_secretaria_historico"),
    )
    check_bool("api ultimo map", hasattr(app_mod, "api_admin_ultimo_atendimento_map"))
    check_bool("xfer equip", hasattr(app_mod, "api_admin_equipamento_transferir"))
    check_bool("xfer links", hasattr(app_mod, "api_admin_link_transferir"))
    check_bool("search unidades", hasattr(app_mod, "api_admin_unidades_search"))
    check_bool("ctx unidade vgr", hasattr(app_mod, "api_admin_unidades_contexto"))
    check_bool("ctx equip", hasattr(app_mod, "api_admin_equipamento_contexto"))
    check_bool("ctx links", hasattr(app_mod, "api_admin_link_contexto"))


def test_admin_guard_helper():
    from flask import Flask

    from prodesp.app import _prodesp_require_admin_api, prodesp_bp
    from unittest.mock import patch

    app = Flask("prodesp_test_admin")
    app.register_blueprint(prodesp_bp)

    class U:
        admin_user = 0

    class A:
        admin_user = 1

    with app.app_context():
        with patch("prodesp.app.current_user", U()):
            resp = _prodesp_require_admin_api()
            check_bool("non admin blocked", resp is not None and resp[1] == 403)
        with patch("prodesp.app.current_user", A()):
            check_eq("admin ok", _prodesp_require_admin_api(), None)


def test_templates_exist():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for name in (
        "templates/admin_equipamentos_prodesp.html",
        "templates/admin_links_prodesp.html",
        "templates/admin_blueprint_secretarias_prodesp.html",
        "static/js/script_admin_equipamentos_prodesp.js",
        "static/js/script_admin_links_prodesp.js",
        "static/js/script_admin_blueprint_secretarias_prodesp.js",
    ):
        p = root / name
        check_bool(f"arquivo {name}", p.is_file())
    base = (root / "templates" / "base_prodesp.html").read_text(encoding="utf-8")
    check_bool("sidebar ADMIN", "adminSubmenu" in base and "admin_equipamentos_page" in base)
    check_bool("sidebar bp sec", "admin_blueprint_secretarias_page" in base)
    eq_html = (root / "templates" / "admin_equipamentos_prodesp.html").read_text(encoding="utf-8")
    check_bool("portal dt css equip", "portal_datatable.css" in eq_html)
    check_bool("portal dt toolbar equip", "portal_dt_toolbar.js" in eq_html)
    eq_js = (root / "static" / "js" / "script_admin_equipamentos_prodesp.js").read_text(
        encoding="utf-8"
    )
    check_bool(
        "equip CC helpers",
        "ccSearchList()" in eq_js,
    )
    check_bool("equip td portal-dt-acoes", "portal-dt-acoes" in eq_js)
    check_bool("equip mode client", 'mode: "client"' in eq_js or "mode=client" in eq_js or "clientAjax" in eq_js)
    check_bool("equip common js", "script_admin_inventory_common.js" in eq_html)
    check_bool("equip kpis", "adminEqKpis" in eq_html)
    check_bool("equip ID VGR Unidade", "ID VGR Unidade" in eq_html)
    check_bool("equip status ultimo th", "Status (último atend.)" in eq_html)
    check_bool("equip analista caderno th", "Analista caderno (último)" in eq_html)
    check_bool("equip tabs", "adminEqTabContexto" in eq_html and "adminEqAtivos" in eq_html)
    check_bool("equip summary", "adminEqSummary" in eq_html)
    check_bool("equip footer xfer", "btnAdminEqFooterXfer" in eq_html)
    check_bool("equip sections", "admin-inv-section-title" in eq_html)
    lk_html = (root / "templates" / "admin_links_prodesp.html").read_text(encoding="utf-8")
    check_bool("links summary", "adminLkSummary" in lk_html)
    check_bool("links status ultimo th", "Status (último atend.)" in lk_html)
    check_bool("links analista caderno th", "Analista caderno (último)" in lk_html)
    check_bool("links tabs", "adminLkTabAtivos" in lk_html)
    check_bool("links footer unlink", "btnAdminLkFooterUnlink" in lk_html)
    common_js = (root / "static" / "js" / "script_admin_inventory_common.js").read_text(
        encoding="utf-8"
    )
    check_bool("common summary strip", "renderSummaryStrip" in common_js)
    check_bool("common fillContextTabs", "fillContextTabs" in common_js)
    check_bool("common unidade preview", "loadUnidadeContextoByVgr" in common_js)
    check_bool("common dt language inline", "dtLanguagePtBr" in common_js)
    check_bool("common sync toast", "Inventário atualizado por outro admin" in common_js)
    check_bool(
        "common sync ancora revision null",
        "state.revision == null" in common_js and "reloadInFlight" in common_js,
    )
    check_bool("common toast soft", "adminInvSoftToast" in common_js)
    lk_js = (root / "static" / "js" / "script_admin_links_prodesp.js").read_text(encoding="utf-8")
    check_bool("links data-link-type js", "bindLinkTypeFields" in lk_js)
    check_bool("links deferRender", "deferRender: true" in lk_js)
    check_bool("links expected_id_unidade", "expected_id_unidade" in lk_js)
    eq_js = (root / "static" / "js" / "script_admin_equipamentos_prodesp.js").read_text(
        encoding="utf-8"
    )
    check_bool("eq deferRender", "deferRender: true" in eq_js)
    check_bool("eq expected_id_unidade", "expected_id_unidade" in eq_js)
    check_bool("eq sync 20s", "intervalMs: 20000" in eq_html or "PRODESP_DT_SYNC" in eq_html)
    check_bool("links sync 20s", "PRODESP_DT_SYNC" in lk_html)


def test_expected_unidade_conflito():
    check_bool(
        "sem expected ok",
        inv.check_expected_unidade(10, {"id_vgr": "1"}) is None,
    )
    check_bool(
        "expected igual ok",
        inv.check_expected_unidade(10, {"expected_id_unidade": 10}) is None,
    )
    check_bool(
        "expected null e atual null",
        inv.check_expected_unidade(None, {"expected_id_unidade": None}) is None,
    )
    msg = inv.check_expected_unidade(10, {"expected_id_unidade": 99})
    check_bool("expected diverge", msg == inv.MSG_UNIDADE_CONFLITO)
    check_bool("is conflito helper", inv.is_unidade_conflito_msg(msg))
    check_bool(
        "atual null expected set",
        inv.check_expected_unidade(None, {"expected_id_unidade": 5}) == inv.MSG_UNIDADE_CONFLITO,
    )


def test_ultimo_atendimento_helpers():
    ids = inv._unit_ids_from_rows(
        [
            {"id_unidade": 1},
            {"id_unidade": "1"},
            {"id_unidade": None},
            {"id_unidade": 2},
            {"id_unidade": ""},
        ]
    )
    check_eq("unit ids unique", ids, [1, 2])
    rows = [
        {"id_unidade": 1, "x": 1},
        {"id_unidade": 99, "x": 2},
        {"id_unidade": None, "x": 3},
    ]
    inv._apply_ultimo_atendimento(rows, {1: ("Em Atendimento", "Ana")})
    check_eq("att status row1", rows[0]["status_ultimo_atendimento"], "Em Atendimento")
    check_eq("att analista row1", rows[0]["analista_caderno_ultimo"], "Ana")
    check_eq("att status missing", rows[1]["status_ultimo_atendimento"], "")
    check_eq("att status null uid", rows[2]["status_ultimo_atendimento"], "")
    cc = inv._build_column_control(
        [
            {"tipo": "STATIC", "status_ultimo_atendimento": "Concluído"},
            {"tipo": "STATIC", "status_ultimo_atendimento": ""},
            {"tipo": "PPPoE", "status_ultimo_atendimento": "Concluído"},
        ],
        ("tipo", "status_ultimo_atendimento"),
    )
    check_eq("cc tipo count", len(cc["tipo"]), 2)
    check_bool(
        "cc status value sem acento (DT normalize)",
        any(o.get("value") == "Concluido" and o.get("label") == "Concluído" for o in cc["status_ultimo_atendimento"]),
    )
    check_bool(
        "cc status usa dash vazio",
        any(o.get("value") == "—" for o in cc["status_ultimo_atendimento"]),
    )
    join_sql = inv._sql_join_ultimo_atendimento("l.id_unidades_links")
    check_bool(
        "join sql usa MAX nao GROUP_CONCAT full",
        "MAX(a2.id_atendimentos)" in join_sql and "GROUP_CONCAT" not in join_sql,
    )
    inv.reset_client_list_cache_for_tests()
    check_bool("client list cache clear", inv._client_list_cache_get("links") is None)
    check_eq(
        "parse ids whitelist",
        inv.parse_unidade_ids_param("1,2,x,2,0,-1,3", max_ids=2),
        [1, 2],
    )
    slim = inv._link_list_row_item(
        {
            "id": 9,
            "id_unidade": 1,
            "tipo": "PPPOE",
            "operadora": "VIVO",
            "designador": "d",
            "id_vgr_link": "123",
            "ip_wan": "1.1.1.1",
            "id_vgr": "v",
            "hostname": "h",
            "acronimo": "a",
            "redundante_critico": 1,
        }
    )
    check_bool("list row sem pppoe", "pppoe_user" not in slim)
    check_eq("list row rc", slim.get("redundante_critico"), 1)
    eq_slim = inv._equipamento_list_row_item(
        {
            "id": 3,
            "id_unidade": 10,
            "serial": "FGT40FTK2409D6QK",
            "modelo": "FortiGate 40F",
            "versao": "7.4",
            "id_vgr": "1",
            "hostname": "h",
            "acronimo": "a",
            "nome_unidade": "U",
        }
    )
    check_bool("eq list sem mac", "mac" not in eq_slim)
    check_bool("eq list sem licenca", "licenca" not in eq_slim)
    check_eq("eq list fgt", eq_slim.get("fgt_padrao"), 1)
    from pathlib import Path

    root_static = Path(__file__).resolve().parents[2] / "static" / "js"
    common_js = (root_static / "script_admin_inventory_common.js").read_text(encoding="utf-8")
    lk_js = (root_static / "script_admin_links_prodesp.js").read_text(encoding="utf-8")
    check_bool("common page enrich", "bindUltimoAtendimentoPageEnrich" in common_js)
    check_bool("common colctrl bind", "bindPortalDtColumnControl" in common_js)
    check_bool("common ccSearchList helper", "ccSearchList" in common_js)
    check_bool("common cc heavy lazy", "ADMIN_INV_CC_HEAVY" in common_js)
    check_bool(
        "common cache max links",
        "4500000" in common_js or "ADMIN_INV_CACHE_MAX_CHARS = 4500000" in common_js,
    )
    check_bool("links usa ccSearchList", "ccSearchList()" in lk_js)
    check_bool("links bind CC com kind", 'bindPortalDtColumnControl(this.api(), "links")' in lk_js)
    check_bool("links usa bindPortalDtColumnControl", "bindPortalDtColumnControl" in lk_js)
    check_bool("links openEdit early show", "modalLk.show()" in lk_js and "openEditSeq" in lk_js)
    eq_js_chk = (root_static / "script_admin_equipamentos_prodesp.js").read_text(encoding="utf-8")
    check_bool("eq openEdit early show", "modalEq.show()" in eq_js_chk and "openEditSeq" in eq_js_chk)
    check_bool("eq usa ccSearchList", "ccSearchList()" in eq_js_chk)
    check_bool(
        "eq bind CC com kind",
        'bindPortalDtColumnControl(this.api(), "equipamentos")' in eq_js_chk,
    )


def main() -> int:
    test_whitelist_order_cols()
    test_dt_args_sanitiza()
    test_client_mode_flag()
    test_list_equip_client_mode_mock()
    test_client_unchanged()
    test_search_unidades_mock()
    test_format_atendimento_timedelta()
    test_resolve_modelo_from_serial()
    test_resolve_unidade_mock()
    test_create_equip_serial_obrigatorio()
    test_admin_inventory_field_history_diff()
    test_routes_registered()
    test_admin_guard_helper()
    test_templates_exist()
    test_expected_unidade_conflito()
    test_ultimo_atendimento_helpers()
    print("=== OK (%d) ===" % len(OK))
    for x in OK:
        print(" ", x)
    print("=== FALHAS (%d) ===" % len(FAILURES))
    for x in FAILURES:
        print(" ", x)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
