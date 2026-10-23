"""Testes do catálogo de secretarias Blueprint (seed + validators)."""
from __future__ import annotations

from prodesp.prodesp.blueprint.blueprint_catalog import (
    BUILTIN_SEED_RULES,
    PROCON_DEVICE_BLUEPRINT,
    PROSANGUE_DEVICE_BLUEPRINT,
    SAPTELE_DEVICE_BLUEPRINT,
    SPAGUAS_DEVICE_BLUEPRINT,
    StaticCatalog,
    clear_test_catalog,
    install_test_catalog,
    parse_aliases_field,
    resolve_rule,
    validate_acronimo_token,
    validate_template,
)


def check_true(name, cond):
    assert cond, name


def check_eq(name, a, b):
    assert a == b, f"{name}: {a!r} != {b!r}"


def test_seed_has_core_secretarias():
    cat = StaticCatalog(BUILTIN_SEED_RULES)
    for acr in (
        "DETRAN",
        "PROCON",
        "PRO-SANGUE",
        "PROSANGUE",
        "SP-AGUAS",
        "SPAGUAS",
        "SEDS",
        "SAP",
        "SAPTELE",
        "SAP-TELE",
        "POUPATEMPO",
        "DIPOL",
        "JUSTICA",
        "JUSTIÇA",
    ):
        r = cat.resolve(acr)
        check_true(f"resolve_{acr}", r is not None)
    check_eq("procon_tpl", cat.resolve("PROCON").device_blueprint_template, PROCON_DEVICE_BLUEPRINT)
    check_eq(
        "prosangue_alias",
        cat.resolve("PROSANGUE").device_blueprint_template,
        PROSANGUE_DEVICE_BLUEPRINT,
    )
    check_eq(
        "spaguas_alias",
        cat.resolve("SPAGUAS").device_blueprint_template,
        SPAGUAS_DEVICE_BLUEPRINT,
    )
    check_eq("seds_regra", cat.resolve("SEDS").rede_lan_regra, "antiga")
    check_eq("seds_dhcp", (cat.resolve("SEDS").dhcp_lan_start_octeto, cat.resolve("SEDS").dhcp_lan_end_octeto), ("10", "60"))
    check_eq("sap_dhcp_srv", cat.resolve("SAP").emite_dhcp_server_1, True)
    check_eq("saptele_own", cat.resolve("SAPTELE").acronimo, "SAPTELE")
    check_eq("saptele_tpl", cat.resolve("SAPTELE").device_blueprint_template, SAPTELE_DEVICE_BLUEPRINT)
    check_eq("saptele_alias", cat.resolve("SAP-TELE").acronimo, "SAPTELE")
    check_eq("saptele_alias_tpl", cat.resolve("SAP-TELE").device_blueprint_template, SAPTELE_DEVICE_BLUEPRINT)
    check_eq("saptele_dhcp_srv", cat.resolve("SAPTELE").emite_dhcp_server_1, True)
    check_eq("poupa_sufixo", cat.resolve("POUPATEMPO").aplica_sufixo_lan_dinamico, False)
    check_eq("dipol_layout", cat.resolve("DIPOL").layout_csv, "legado")
    check_eq("dipol_omit", cat.resolve("DIPOL").legado_omitir_dhcp_server, True)


def test_install_test_catalog_resolve():
    clear_test_catalog()
    install_test_catalog()
    try:
        r = resolve_rule("pro-sangue")
        check_true("installed", r is not None)
        check_eq("tpl", r.device_blueprint_template, PROSANGUE_DEVICE_BLUEPRINT)
    finally:
        clear_test_catalog()


def test_inactive_not_resolved():
    from dataclasses import replace

    base = [r for r in BUILTIN_SEED_RULES if r.acronimo != "DETRAN"]
    dead = replace(
        next(r for r in BUILTIN_SEED_RULES if r.acronimo == "DETRAN"),
        ativo=False,
    )
    cat = StaticCatalog(list(base) + [dead])
    check_eq("inactive miss", cat.resolve("DETRAN"), None)


def test_validators():
    a, err = validate_acronimo_token("  sp-aguas ")
    check_eq("acr", a, "SP-AGUAS")
    check_eq("err", err, None)
    _, err = validate_acronimo_token("bad space")
    check_true("space fail", err is not None)
    t, err = validate_template("SPAGUAS_HUB-C3-C4_40F_REDE_LAN_1")
    check_true("tpl ok", t and not err)
    _, err = validate_template("bad template!")
    check_true("tpl fail", err is not None)
    aliases, err = parse_aliases_field("A, B\nC")
    check_eq("aliases", aliases, ["A", "B", "C"])
    check_eq("aliases err", err, None)


def test_parse_payload_collision_shape():
    from prodesp.prodesp.blueprint.blueprint_secretaria_repo import parse_payload

    row, err = parse_payload(
        {
            "acronimo": "FOO",
            "device_blueprint_template": "FOO_HUB-C3-C4_40F_REDE_LAN_1",
            "layout_csv": "rede_lan",
            "rede_lan_regra": "nova",
            "aliases": "BAR",
        },
        is_create=True,
    )
    check_eq("parse err", err, None)
    check_eq("acr", row["acronimo"], "FOO")
    check_eq("aliases", row["aliases"], ["BAR"])
    _, err = parse_payload(
        {
            "acronimo": "X",
            "device_blueprint_template": "X_40F",
            "dhcp_lan_start_octeto": "10",
        },
        is_create=True,
    )
    check_true("dhcp pair", err is not None)


if __name__ == "__main__":
    test_seed_has_core_secretarias()
    test_install_test_catalog_resolve()
    test_inactive_not_resolved()
    test_validators()
    test_parse_payload_collision_shape()
    print("ok")
