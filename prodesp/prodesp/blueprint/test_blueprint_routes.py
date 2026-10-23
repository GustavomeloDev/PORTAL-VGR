"""Testes das regras de blueprint (serial duplicado, preview de links).

Rodar (na raiz do repo, venv ``.venv_portal_pessoal``):

    .venv_portal_pessoal\\Scripts\\python.exe -m prodesp.prodesp.blueprint.test_blueprint_routes
"""
from __future__ import annotations

from prodesp.prodesp.db_field_limits import (
    limit_for_column,
    message_from_mysql_exception,
    normalize_coordinate_for_db,
    validate_blueprint_form_business_rules,
    validate_blueprint_form_limits,
    validate_coordinate_for_db,
    validate_link_fields,
    validate_link_wan_gateway_distinct,
    validate_no_whitespace,
    validate_static_wan_ip_block,
)
from prodesp.prodesp.blueprint.link_velocity_rules import (
    normalize_velocity_mbps,
    normalize_velocity_mbps_with_meta,
)
from prodesp.prodesp.blueprint.link_vivo_rules import (
    derive_vivo_gateway_from_wan,
    derive_vivo_mask_from_wan,
    normalize_link_api_payload,
    normalize_vivo_link_fields,
)
from prodesp.prodesp.blueprint.prodesp_csv_generator import (
    apply_blueprint_equipamento_overrides,
    validar_dados_blueprint,
)
from prodesp.prodesp.blueprint.prodesp_routes import (
    _blueprint_exception_message,
    _is_mysql_bad_decimal,
    _is_mysql_duplicate_key,
    _links_dict_from_list,
    _preview_equipamento_for_blueprint,
    _preview_links_for_blueprint,
    mensagem_serial_duplicado,
)

FAILURES: list[str] = []
OK: list[str] = []


def check_true(name: str, cond: bool):
    if cond:
        OK.append(name)
    else:
        FAILURES.append(name)


def check_eq(name: str, got, expected):
    if got == expected:
        OK.append(name)
    else:
        FAILURES.append(f"{name}: esperado {expected!r}, obteve {got!r}")


def test_mensagem_serial_duplicado():
    from unittest.mock import MagicMock

    from prodesp.prodesp.blueprint.prodesp_routes import buscar_colisao_serial_equipamento

    msg = mensagem_serial_duplicado("FGT40FTK123", "2177114")
    check_true("mensagem contém serial", "FGT40FTK123" in msg)
    check_true("mensagem contém id vgr", "2177114" in msg)
    check_true("mensagem prefixo Erro", msg.startswith("Erro:"))

    cur = MagicMock()
    cur.fetchone.return_value = {"id_vgr_unidades": "00001"}
    vgr = buscar_colisao_serial_equipamento(
        cur, "FGT40FTK123", None, exclude_unidade_id=99
    )
    check_eq("colisao retorna vgr", vgr, "00001")
    sql = cur.execute.call_args[0][0]
    check_true("sql exclui unidade atual", "id_unidades_equipamentos != %s" in sql)
    check_eq("params serial+exclude+unidade", cur.execute.call_args[0][1], ["FGT40FTK123", -1, 99])


def test_mysql_duplicate_key_errno():
    class FakeDup(Exception):
        errno = 1062

    class FakeOther(Exception):
        errno = 1406

    check_true("detecta errno 1062", _is_mysql_duplicate_key(FakeDup()))
    check_true("ignora outros errno", not _is_mysql_duplicate_key(FakeOther()))


def test_mysql_duplicate_message_serial():
    from prodesp.prodesp.db_field_limits import message_from_mysql_exception

    class FakeDup(Exception):
        errno = 1062

        def __str__(self):
            return (
                "1062 (23000): Duplicate entry 'FGT40FTK25036177' "
                "for key 'equipamentos.idx_serial_equipamentos'"
            )

    msg, is_client = message_from_mysql_exception(FakeDup())
    check_true("dup serial is_client", is_client)
    check_true("dup serial menciona serie", "série" in msg.lower() or "serial" in msg.lower() or "FGT40FTK25036177" in msg)
    check_true("dup serial nao generica", "conflito ou vínculo" not in msg.lower())


def test_mysql_fk_message():
    from prodesp.prodesp.db_field_limits import message_from_mysql_exception

    class FakeFk(Exception):
        errno = 1452

        def __str__(self):
            return "1452 (23000): Cannot add or update a child row: a foreign key constraint fails"

    msg, is_client = message_from_mysql_exception(FakeFk())
    check_true("fk is_client", is_client)
    check_true("fk menciona vinculo", "vínculo" in msg.lower() or "vinculo" in msg.lower() or "estrangeira" in msg.lower())


def test_preview_equipamento():
    old = {"id_equipamentos": 1, "serial_equipamentos": "OLD", "versao_equipamentos": "7.0"}
    preview = _preview_equipamento_for_blueprint(old, "NEW", "7.4", "FortiGate 40F")
    check_eq("preview serial", preview.get("serial_equipamentos"), "NEW")
    check_eq("preview versao", preview.get("versao_equipamentos"), "7.4")
    check_eq("preview mantém id", preview.get("id_equipamentos"), 1)


def test_equipamento_override_serial_formulario():
    """Prévia do modal: serial digitado no form cobre equipamento vazio no banco."""
    eq_db = {}
    eq = apply_blueprint_equipamento_overrides(
        eq_db,
        {"serial_equipamentos": "FGT40FTKTIETE11", "versao_equipamentos": "7.4.11"},
    )
    check_eq("override serial", eq.get("serial_equipamentos"), "FGT40FTKTIETE11")
    check_eq("override versao", eq.get("versao_equipamentos"), "7.4.11")
    check_true("modelo inferido", "40F" in str(eq.get("modelo_equipamentos") or ""))

    unidade = {
        "hostname_unidades": "ppt-spk-c3-c4-id-00337784",
        "acronimo_unidades": "PPT",
        "ip_lan_01_unidades": "10.88.193.1/25",
        "loopback_cliente_unidades": "10.1.1.1",
        "loopback_on_bgp_unidades": "10.1.1.2",
        "loopback_vivo_unidades": "10.1.1.3",
    }
    links = [
        {
            "tipo_links": "MPLS",
            "operadora_links": "VIVO",
            "designador_links": "DES1",
            "ip_wan_links": "10.250.3.18",
            "ip_gateway_links": "10.250.3.17",
            "ip_mascara_links": "255.255.255.248",
            "velocidade_links": "40",
            "id_vgr_links": "337784",
        }
    ]
    ok_sem, errs_sem = validar_dados_blueprint(unidade, {}, links)
    check_true("sem serial no DB falha", not ok_sem)
    check_true(
        "erro serial ausente",
        any("Serial Number" in e for e in errs_sem),
    )
    ok_com, errs_com = validar_dados_blueprint(unidade, eq, links)
    check_true(
        "com serial do form passa serial",
        not any("Serial Number" in e for e in errs_com),
    )


def test_normalize_coordinate_comma():
    check_eq("virgula vira ponto", normalize_coordinate_for_db("-22,4351324"), "-22.4351324")
    check_eq("ponto mantido", normalize_coordinate_for_db("-45.8768593"), "-45.8768593")
    check_eq("vazio none", normalize_coordinate_for_db(""), None)
    check_true("invalido none", normalize_coordinate_for_db("abc") is None)


def test_validate_coordinate_for_db():
    check_true("virgula ok", validate_coordinate_for_db("-22,43", field_label="Latitude") is None)
    check_true("invalido erro", validate_coordinate_for_db("x", field_label="Longitude") is not None)


def test_mysql_bad_decimal_errno():
    class FakeBadDecimal(Exception):
        errno = 1366

    check_true("detecta errno 1366", _is_mysql_bad_decimal(FakeBadDecimal()))


def test_hostname_limit_80():
    check_eq("hostname limite py", limit_for_column("unidades", "hostname_unidades"), 80)


def test_validate_blueprint_hostname_too_long():
    long_host = "x" * 81
    errors = validate_blueprint_form_limits({"hostname_unidades": long_host})
    check_true("hostname longo rejeitado", any("Hostname" in e for e in errors))
    ok_host = "detran-spk-c1-c2-id-00322890"
    check_true("hostname ok", not validate_blueprint_form_limits({"hostname_unidades": ok_host}))


def test_mysql_data_too_long_hostname_message():
    class FakeTooLong(Exception):
        errno = 1406

        def __str__(self):
            return "1406 (22001): Data too long for column 'hostname_unidades' at row 1"

    msg, is_client = message_from_mysql_exception(FakeTooLong())
    check_true("1406 é client error", is_client)
    check_true("mensagem hostname", "Hostname" in msg and "80" in msg)
    check_true("exception helper", "Hostname" in _blueprint_exception_message(FakeTooLong()))


def test_preview_links_mpls_from_form():
    unit_links = [
        {
            "id_link": 10,
            "tipo_links": "MPLS",
            "operadora_links": "VIVO",
            "id_vgr_links": "111",
            "designador_links": "D1",
            "ip_wan_links": "1.1.1.1",
            "ip_gateway_links": "1.1.1.2",
            "ip_mascara_links": "255.255.255.252",
            "velocidade_links": "100",
            "vlan_links": "100",
        }
    ]
    form = {
        "mpls_operadora": "VIVO",
        "mpls_id_vgr": "111",
        "mpls_designador": "D1",
        "mpls_ip_wan": "2.2.2.2",
        "mpls_ip_gateway": "2.2.2.3",
        "mpls_ip_mascara": "255.255.255.252",
        "mpls_velocidade": "200",
        "mpls_vlan": "200",
    }
    preview = _preview_links_for_blueprint(unit_links, form, 99)
    mpls = next(l for l in preview if l.get("tipo_links") == "MPLS")
    check_eq("preview mpls ip wan", mpls.get("ip_wan_links"), "2.2.2.2")
    check_eq("preview mpls velocidade", mpls.get("velocidade_links"), "200")


def test_preview_links_from_form_when_db_empty():
    """Modal Criar Blueprint: link so no form (DB sem links) deve validar."""
    form = {
        "mpls_operadora": "VIVO",
        "mpls_id_vgr": "332924",
        "mpls_designador": "LP_SCM",
        "mpls_ip_wan": "10.250.3.18",
        "mpls_ip_gateway": "10.250.3.17",
        "mpls_ip_mascara": "255.255.255.248",
        "mpls_velocidade": "40",
    }
    links_db = _preview_links_for_blueprint([], {}, 1)
    check_true("sem form e sem DB = sem links", len(links_db) == 0)
    links = _preview_links_for_blueprint([], form, 1)
    check_true("form MPLS cria link na previa", len(links) == 1)
    check_eq("tipo MPLS", links[0].get("tipo_links"), "MPLS")

    unidade = {
        "hostname_unidades": "sap-spk-c3-c4-id-00332924",
        "acronimo_unidades": "SAP",
        "ip_lan_01_unidades": "10.14.98.241/28",
        "loopback_cliente_unidades": "10.1.1.1",
        "loopback_on_bgp_unidades": "10.1.1.2",
        "loopback_vivo_unidades": "10.1.1.3",
    }
    eq = apply_blueprint_equipamento_overrides(
        {}, {"serial_equipamentos": "FGT40FTKTIETE11"}
    )
    ok_db, errs_db = validar_dados_blueprint(unidade, eq, [])
    check_true("DB sem link falha", not ok_db)
    check_true(
        "erro cita link",
        any("link" in e.lower() for e in errs_db),
    )
    ok_form, errs_form = validar_dados_blueprint(unidade, eq, links)
    check_true("form com MPLS valida", ok_form)
    check_eq("sem erros form", errs_form, [])


def test_links_dict_assigns_orphan_tipo_to_static_slot():
    links = _links_dict_from_list(
        [
            {
                "id_link": 1,
                "tipo_links": "MPLS",
                "designador_links": "A",
                "operadora_links": "VIVO",
            },
            {
                "id_link": 2,
                "tipo_links": "",
                "designador_links": "115693279117195",
                "id_vgr_links": "2160994",
                "operadora_links": "VIVO",
            },
        ]
    )
    check_eq("orphan vai para STATIC", links["STATIC"].get("id_link"), 2)
    check_eq("MPLS tipado mantido", links["MPLS"].get("id_link"), 1)


def test_preview_update_orphan_keeps_id_link():
    unit_links = [
        {
            "id_link": 2,
            "tipo_links": "",
            "operadora_links": "VIVO",
            "id_vgr_links": "2160994",
            "designador_links": "115693279117195",
            "ip_wan_links": "186.238.81.67",
            "ip_gateway_links": "186.238.81.66",
            "ip_mascara_links": "255.255.255.254",
            "velocidade_links": "16",
        }
    ]
    form = {
        "static_id_link": "2",
        "static_operadora": "VIVO",
        "static_id_vgr": "2160994",
        "static_designador": "115693279117195",
        "static_ip_wan": "186.238.81.67",
        "static_ip_gateway": "186.238.81.66",
        "static_ip_mascara": "255.255.255.254",
        "static_velocidade": "16",
    }
    preview = _preview_links_for_blueprint(unit_links, form, 99)
    static = next(l for l in preview if l.get("tipo_links") == "STATIC")
    check_eq("preview update preserva id_link", static.get("id_link"), 2)


def test_vivo_wan_par_impar_mask_gateway():
    check_eq("vivo mpls /29", derive_vivo_mask_from_wan("10.250.11.224", "MPLS"), "255.255.255.248")
    check_eq("vivo mpls /29 impar", derive_vivo_mask_from_wan("10.250.11.225", "MPLS"), "255.255.255.248")
    check_eq("vivo static par /30", derive_vivo_mask_from_wan("200.159.30.22", "STATIC"), "255.255.255.252")
    check_eq("vivo static impar /31", derive_vivo_mask_from_wan("200.159.30.23", "STATIC"), "255.255.255.254")
    check_eq("vivo par /30 sem tipo", derive_vivo_mask_from_wan("200.159.30.22"), "255.255.255.252")
    check_eq("vivo impar /31 sem tipo", derive_vivo_mask_from_wan("200.159.30.23"), "255.255.255.254")
    check_eq("vivo gateway wan-1", derive_vivo_gateway_from_wan("200.159.30.22"), "200.159.30.21")
    check_eq("vivo gateway impar", derive_vivo_gateway_from_wan("200.159.30.23"), "200.159.30.22")
    norm_static = normalize_vivo_link_fields(
        {
            "tipo_links": "STATIC",
            "operadora_links": "VIVO",
            "ip_wan_links": "200.159.30.22",
            "ip_gateway_links": "0.0.0.0",
            "ip_mascara_links": "255.255.255.255",
        }
    )
    check_eq("normalize vivo static mask", norm_static["ip_mascara_links"], "255.255.255.252")
    check_eq("normalize vivo static gw", norm_static["ip_gateway_links"], "200.159.30.21")
    norm_mpls = normalize_vivo_link_fields(
        {
            "tipo_links": "MPLS",
            "operadora_links": "VIVO",
            "ip_wan_links": "10.250.11.224",
            "ip_gateway_links": "0.0.0.0",
            "ip_mascara_links": "255.255.255.255",
        }
    )
    check_eq("normalize vivo mpls mask", norm_mpls["ip_mascara_links"], "255.255.255.248")
    check_eq("normalize vivo mpls gw", norm_mpls["ip_gateway_links"], "10.250.11.223")
    norm = normalize_vivo_link_fields(
        {
            "operadora_links": "VIVO",
            "ip_wan_links": "200.159.30.22",
            "ip_gateway_links": "0.0.0.0",
            "ip_mascara_links": "255.255.255.255",
        }
    )
    check_eq("normalize vivo mask", norm["ip_mascara_links"], "255.255.255.252")
    check_eq("normalize vivo gw", norm["ip_gateway_links"], "200.159.30.21")
    claro = normalize_vivo_link_fields(
        {"operadora_links": "CLARO", "ip_wan_links": "200.159.30.22", "ip_mascara_links": "255.255.255.248"}
    )
    check_eq("claro inalterado", claro["ip_mascara_links"], "255.255.255.248")
    api = normalize_link_api_payload(
        {"operadora": "VIVO", "tipo": "STATIC", "ip_wan": "200.159.30.22", "ip_gateway": "0.0.0.0", "ip_mascara": "255.255.255.255"}
    )
    check_eq("api payload vivo static mask", api["ip_mascara"], "255.255.255.252")
    check_eq("api payload vivo static gw", api["ip_gateway"], "200.159.30.21")
    api_mpls = normalize_link_api_payload(
        {"operadora": "VIVO", "tipo": "MPLS", "ip_wan": "10.250.11.224", "ip_gateway": "0.0.0.0", "ip_mascara": "255.255.255.255"}
    )
    check_eq("api payload vivo mpls mask", api_mpls["ip_mascara"], "255.255.255.248")
    check_eq("api payload vivo mpls gw", api_mpls["ip_gateway"], "10.250.11.223")
    err_static = validate_link_fields({
        "tipo": "STATIC",
        "operadora": "CLARO",
        "designador": "LP_SAI",
        "velocidade": "100",
        "ip_wan": "201.60.1.1",
        "ip_gateway": "201.60.1.2",
        "ip_mascara": "255.255.255.252",
    })
    check_true("validate_link_fields bloqueia 201.60", err_static is not None)


def test_normalize_velocity_mbps():
    # Legado numérico (×1000)
    check_eq("8MB legado", normalize_velocity_mbps("8MB"), "8")
    check_eq("8000 kbps erro", normalize_velocity_mbps("8000"), "8")
    check_eq("4000 legado", normalize_velocity_mbps("4000"), "4")
    check_eq("200000 legado", normalize_velocity_mbps("200000"), "200")
    check_eq("50000 legado", normalize_velocity_mbps("50000"), "50")
    check_eq("155000 legado", normalize_velocity_mbps("155000"), "155")
    check_eq("300000 legado", normalize_velocity_mbps("300000"), "300")
    # Colagem planilha (texto)
    check_eq("10G", normalize_velocity_mbps("10G"), "10000")
    check_eq("10 G", normalize_velocity_mbps("10 G"), "10000")
    check_eq("1 Gbps", normalize_velocity_mbps("1 Gbps"), "1000")
    check_eq("2,5 Gbps", normalize_velocity_mbps("2,5 Gbps"), "2500")
    check_eq("300 Mbps", normalize_velocity_mbps("300 Mbps"), "300")
    check_eq("1 Mbps", normalize_velocity_mbps("1 Mbps"), "1")
    check_eq("1 Gbps literal", normalize_velocity_mbps("1000"), "1000")
    check_eq("2000 legado 2M", normalize_velocity_mbps("2000"), "2")
    val, adj, _raw = normalize_velocity_mbps_with_meta("8000")
    check_eq("meta 8000", val, "8")
    check_true("meta 8000 ajustado", adj)
    val_g, adj_g, _ = normalize_velocity_mbps_with_meta("10G")
    check_eq("meta 10G", val_g, "10000")
    check_true("meta 10G ajustado", adj_g)
    api = normalize_link_api_payload({"operadora": "VIVO", "tipo": "MPLS", "velocidade": "8MB"})
    check_eq("api velocidade normalizada", api["velocidade"], "8")
    api2 = normalize_link_api_payload({"operadora": "VIVO", "tipo": "MPLS", "velocidade": "300 Mbps"})
    check_eq("api 300 Mbps", api2["velocidade"], "300")


def test_validate_link_wan_equals_gateway():
    err = validate_link_fields(
        {
            "tipo": "MPLS",
            "operadora": "CLARO",
            "designador": "LP_SCM",
            "velocidade": "100",
            "ip_wan": "10.1.1.1",
            "ip_gateway": "10.1.1.1",
            "ip_mascara": "255.255.255.252",
        }
    )
    check_true("wan igual gateway rejeitado", err is not None)
    check_true("mensagem cita WAN e Gateway", "WAN" in err and "Gateway" in err)


def test_validate_static_wan_bloco_201_60():
    err = validate_static_wan_ip_block("201.60.10.5")
    check_true("201.60 bloqueado", err is not None)
    check_true("mensagem manobra IP", "manobra" in err.lower())


def test_validate_static_wan_bloco_201_61():
    err = validate_static_wan_ip_block("201.61.2.3")
    check_true("201.61 bloqueado", err is not None)


def test_validate_static_wan_ok():
    check_true("outro bloco ok", validate_static_wan_ip_block("10.0.0.1") is None)


def test_validar_dados_blueprint_exige_operadora_designador():
    from prodesp.prodesp.blueprint.prodesp_csv_generator import validar_dados_blueprint

    unidade = {"id_vgr_unidades": "U1", "nome_unidades": "Unidade Teste"}
    equipamento = {
        "serial_equipamentos": "FGT40FTK1234567890",
        "hostname_equipamentos": "HOST1",
        "modelo_equipamentos": "FortiGate 40F",
        "versao_equipamentos": "7.0",
    }
    link_sem = {
        "tipo_links": "MPLS",
        "operadora_links": "",
        "designador_links": "",
        "ip_wan_links": "10.1.1.1",
        "ip_gateway_links": "10.1.1.2",
        "ip_mascara_links": "255.255.255.252",
        "velocidade_links": "100",
    }
    ok, erros = validar_dados_blueprint(unidade, equipamento, [link_sem])
    check_true("rejeita sem operadora/designador", not ok)
    check_true("erro cita Operadora", any("Operadora" in e for e in erros))
    check_true("erro cita Designador", any("Designador" in e for e in erros))

    link_ok = dict(link_sem)
    link_ok["operadora_links"] = "CLARO"
    link_ok["designador_links"] = "LP_SCM"
    ok2, erros2 = validar_dados_blueprint(unidade, equipamento, [link_ok])
    check_true(
        "aceita com operadora e designador",
        ok2 or not any("Operadora" in e or "Designador" in e for e in erros2),
    )


def test_validate_link_required_fields_atendimento():
    from prodesp.prodesp.db_field_limits import validate_link_required_fields, validate_link_fields

    err = validate_link_required_fields({"tipo": "MPLS", "designador": "D1"})
    check_true("faltam operadora/velocidade/ips", err is not None)
    check_true("mensagem lista Operadora", "Operadora" in (err or ""))
    check_true("mensagem lista Velocidade", "Velocidade" in (err or ""))

    err_ok = validate_link_required_fields(
        {
            "tipo": "DHCP",
            "operadora": "CLARO",
            "designador": "LP_DHCP",
            "velocidade": "50",
        }
    )
    check_true("DHCP só comuns ok", err_ok is None)

    err_pppoe = validate_link_required_fields(
        {
            "tipo": "PPPoE",
            "operadora": "VIVO",
            "designador": "LP_PP",
            "velocidade": "100",
        }
    )
    check_true("PPPoE exige user/pass", err_pppoe is not None and "PPPoE" in err_pppoe)

    err_vivo = validate_link_fields(
        {
            "tipo": "MPLS",
            "operadora": "VIVO",
            "designador": "LP_SCM",
            "velocidade": "100",
            "ip_wan": "10.1.1.1",
            "ip_gateway": "10.1.1.2",
            "ip_mascara": "255.255.255.248",
        }
    )
    check_true("VIVO exige id_vgr", err_vivo is not None and "ID VGR" in (err_vivo or ""))


def test_validate_no_whitespace_hostname():
    err = validate_no_whitespace("host name", "Hostname")
    check_true("espaco em hostname rejeitado", err is not None)


def test_validate_blueprint_form_business_rules_static_block():
    errors = validate_blueprint_form_business_rules(
        {
            "static_ip_wan": "201.60.1.1",
            "static_ip_gateway": "201.60.1.2",
        }
    )
    check_true("form static 201.60 bloqueado", any("201.60" in e for e in errors))


def main():
    test_mensagem_serial_duplicado()
    test_mysql_duplicate_key_errno()
    test_mysql_duplicate_message_serial()
    test_mysql_fk_message()
    test_normalize_coordinate_comma()
    test_validate_coordinate_for_db()
    test_mysql_bad_decimal_errno()
    test_hostname_limit_80()
    test_validate_blueprint_hostname_too_long()
    test_mysql_data_too_long_hostname_message()
    test_preview_equipamento()
    test_equipamento_override_serial_formulario()
    test_preview_links_mpls_from_form()
    test_preview_links_from_form_when_db_empty()
    test_links_dict_assigns_orphan_tipo_to_static_slot()
    test_preview_update_orphan_keeps_id_link()
    test_vivo_wan_par_impar_mask_gateway()
    test_validate_link_wan_equals_gateway()
    test_validate_static_wan_bloco_201_60()
    test_validate_static_wan_bloco_201_61()
    test_validate_static_wan_ok()
    test_validar_dados_blueprint_exige_operadora_designador()
    test_validate_link_required_fields_atendimento()
    test_validate_no_whitespace_hostname()
    test_validate_blueprint_form_business_rules_static_block()

    print(f"OK: {len(OK)}")
    for item in OK:
        print(f"  + {item}")
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for item in FAILURES:
            print(f"  - {item}")
        raise SystemExit(1)
    print("Todos os testes blueprint routes passaram.")


if __name__ == "__main__":
    main()
