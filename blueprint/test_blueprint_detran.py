"""Testes do blueprint CSV DETRAN (planilha DETRAN_BP_MODELO_v1).

Rodar (na raiz do repo, venv ``.venv_portal_pessoal``):

    .venv_portal_pessoal\\Scripts\\python.exe -m pytest prodesp/prodesp/blueprint/test_blueprint_detran.py -q
"""
from __future__ import annotations

import csv
import os
import tempfile

from prodesp.prodesp.blueprint.blueprint_catalog import (
    CDHU_DEVICE_BLUEPRINT,
    CEETEPS_DEVICE_BLUEPRINT,
    DER_DEVICE_BLUEPRINT,
    DETRAN_DEVICE_BLUEPRINT,
    DIPOL_DEVICE_BLUEPRINT,
    DPESP_DEVICE_BLUEPRINT,
    FLORESTAL_DEVICE_BLUEPRINT,
    JUSTICA_DEVICE_BLUEPRINT,
    PGE_DEVICE_BLUEPRINT,
    POUPATEMPO_DEVICE_BLUEPRINT,
    PROCON_DEVICE_BLUEPRINT,
    PROSANGUE_DEVICE_BLUEPRINT,
    SAP_DEVICE_BLUEPRINT,
    SAPTELE_DEVICE_BLUEPRINT,
    SDE_DEVICE_BLUEPRINT,
    SEDS_DEVICE_BLUEPRINT,
    SELJ_DEVICE_BLUEPRINT,
    SPAGUAS_DEVICE_BLUEPRINT,
    install_test_catalog,
)
from prodesp.prodesp.blueprint.prodesp_csv_generator import (
    _apply_modelo_to_device_blueprint,
    _build_blueprint_rede_lan_row_pairs,
    _normalize_rede_lan_regra,
    _rede_lan_regra_for_unidade,
    _resolve_dhcp_lan_range,
    _resolve_rede_lan,
    _should_emit_dhcp_server_1,
    _uses_blueprint_rede_lan_modelo,
    _resolve_device_blueprint,
    build_blueprint_row_pairs,
    gerar_csv_blueprint_prodesp,
    get_ip_lan_minus_one,
)

# Catálogo estático (seed) — isolamento dos testes sem MySQL.
install_test_catalog()

FAILURES: list[str] = []
OK: list[str] = []


def check_eq(name: str, got, expected):
    if got != expected:
        FAILURES.append(f"{name}: esperava {expected!r}, got {got!r}")
    else:
        OK.append(name)


def check_true(name: str, cond: bool):
    if not cond:
        FAILURES.append(name)
    else:
        OK.append(name)


def _planilha_exemplo_unidade():
    return {
        "acronimo_unidades": "DETRAN",
        "hostname_unidades": "detran-spk-c1-c2-id-00322890",
        "ip_lan_01_unidades": "10.138.42.129/29",
        "loopback_cliente_unidades": "10.252.3.131",
        "loopback_on_bgp_unidades": "10.253.3.131",
        "loopback_vivo_unidades": "10.254.3.131",
        "latitude_unidades": "-23.185166",
        "longitude_unidades": "-45.8768593",
        "endereco_unidades": "RUA HENRIQUE DIAS 363 S/C 363",
        "numero_unidades": "",
        "bairro_unidades": "Monte Castelo",
        "cep_unidades": "12215260",
        "municipio_unidades": "S JOSE DOS CAMPOS",
        "estado_unidades": "SP",
    }


def _planilha_exemplo_equipamento():
    return {"serial_equipamentos": "FGT40FTK25034989"}


def _planilha_exemplo_links():
    return [
        {
            "tipo_links": "STATIC",
            "ip_wan_links": "189.20.114.165",
            "ip_gateway_links": "189.20.114.164",
            "ip_mascara_links": "255.255.255.252",
            "velocidade_links": "300",
            "id_vgr_links": "2187527",
        },
        {
            "tipo_links": "MPLS",
            "ip_wan_links": "10.250.26.66",
            "ip_gateway_links": "10.250.26.65",
            "ip_mascara_links": "255.255.255.252",
            "velocidade_links": "34",
            "id_vgr_links": "2155440",
        },
    ]


def test_identificacao_detran():
    check_true("uses_rede_lan_modelo", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "detran"}))
    check_true("uses_rede_lan_modelo_dpesp", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "dpesp"}))
    check_true("uses_rede_lan_modelo_selj", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "SELJ"}))
    check_true("uses_rede_lan_modelo_sap", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "SAP"}))
    check_true("uses_rede_lan_modelo_saptele", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "SAPTELE"}))
    check_true("uses_rede_lan_modelo_der", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "DER"}))
    check_true("uses_rede_lan_modelo_sde", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "sde"}))
    check_true("uses_rede_lan_modelo_ceeteps", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "CEETEPS"}))
    check_true("uses_rede_lan_modelo_poupatempo", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "POUPATEMPO"}))
    check_true("uses_rede_lan_modelo_pge", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "PGE"}))
    check_true("uses_rede_lan_modelo_seds", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "SEDS"}))
    check_true("uses_rede_lan_modelo_procon", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "procon"}))
    check_true(
        "uses_rede_lan_modelo_pro_sangue",
        _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "PRO-SANGUE"}),
    )
    check_true(
        "uses_rede_lan_modelo_prosangue",
        _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "PROSANGUE"}),
    )
    check_true(
        "uses_rede_lan_modelo_sp_aguas",
        _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "SP-AGUAS"}),
    )
    check_true(
        "uses_rede_lan_modelo_spaguas",
        _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "SPAGUAS"}),
    )
    check_true("uses_rede_lan_modelo_tjsp", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "TJSP"}))
    check_true("uses_rede_lan_modelo_cdhu", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "CDHU"}))
    check_true("uses_rede_lan_modelo_justica", _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "JUSTICA"}))
    check_true(
        "uses_rede_lan_modelo_justica_acento",
        _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "JUSTIÇA"}),
    )
    check_true(
        "uses_rede_lan_modelo_florestal",
        _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "FLORESTAL"}),
    )
    check_true(
        "uses_rede_lan_fallback_pcesp",
        _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "PCESP"}),
    )
    check_true(
        "uses_rede_lan_fallback_unknown",
        _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "QUALQUER"}),
    )
    check_true(
        "dipol_continua_legado",
        not _uses_blueprint_rede_lan_modelo({"acronimo_unidades": "DIPOL"}),
    )
    eq40 = {"modelo_equipamentos": "FortiGate 40F"}
    check_eq(
        "device_blueprint_detran",
        _resolve_device_blueprint({"acronimo_unidades": "DETRAN"}, eq40),
        DETRAN_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_dpesp",
        _resolve_device_blueprint({"acronimo_unidades": "DPESP"}, eq40),
        DPESP_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_selj",
        _resolve_device_blueprint({"acronimo_unidades": "selj"}, eq40),
        SELJ_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_sap",
        _resolve_device_blueprint({"acronimo_unidades": "SAP"}, eq40),
        SAP_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_saptele",
        _resolve_device_blueprint({"acronimo_unidades": "SAPTELE"}, eq40),
        SAPTELE_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_sap_tele_alias",
        _resolve_device_blueprint({"acronimo_unidades": "SAP-TELE"}, eq40),
        SAPTELE_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_dipol",
        _resolve_device_blueprint({"acronimo_unidades": "DIPOL"}, eq40),
        DIPOL_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_der",
        _resolve_device_blueprint({"acronimo_unidades": "DER"}, eq40),
        DER_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_der_case_insensitive",
        _resolve_device_blueprint({"acronimo_unidades": " der "}, eq40),
        DER_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_sde",
        _resolve_device_blueprint({"acronimo_unidades": "SDE"}, eq40),
        SDE_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_seds",
        _resolve_device_blueprint({"acronimo_unidades": "SEDS"}, eq40),
        SEDS_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_procon",
        _resolve_device_blueprint({"acronimo_unidades": "PROCON"}, eq40),
        PROCON_DEVICE_BLUEPRINT,
    )
    check_true("procon_template_procom", PROCON_DEVICE_BLUEPRINT.startswith("PROCOM_"))
    check_eq(
        "device_blueprint_pro_sangue",
        _resolve_device_blueprint({"acronimo_unidades": "PRO-SANGUE"}, eq40),
        PROSANGUE_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_prosangue_alias",
        _resolve_device_blueprint({"acronimo_unidades": "PROSANGUE"}, eq40),
        PROSANGUE_DEVICE_BLUEPRINT,
    )
    check_true("prosangue_template_prosangue", PROSANGUE_DEVICE_BLUEPRINT.startswith("PROSANGUE_"))
    check_eq(
        "device_blueprint_sp_aguas",
        _resolve_device_blueprint({"acronimo_unidades": "SP-AGUAS"}, eq40),
        SPAGUAS_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_spaguas_alias",
        _resolve_device_blueprint({"acronimo_unidades": "SPAGUAS"}, eq40),
        SPAGUAS_DEVICE_BLUEPRINT,
    )
    check_true("spaguas_template_spaguas", SPAGUAS_DEVICE_BLUEPRINT.startswith("SPAGUAS_"))
    check_eq(
        "device_blueprint_ceeteps",
        _resolve_device_blueprint({"acronimo_unidades": "CEETEPS"}, eq40),
        CEETEPS_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_poupatempo",
        _resolve_device_blueprint({"acronimo_unidades": "POUPATEMPO"}, eq40),
        POUPATEMPO_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_poupatempo_com_lan",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "POUPATEMPO",
                "ip_lan_01_unidades": "10.1.1.1/24",
                "mv_ip_lan_sec_unidades": "10.1.2.1/24",
            },
            eq40,
        ),
        POUPATEMPO_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_pge",
        _resolve_device_blueprint({"acronimo_unidades": "PGE"}, eq40),
        PGE_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_cdhu",
        _resolve_device_blueprint({"acronimo_unidades": "CDHU"}, eq40),
        CDHU_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_justica",
        _resolve_device_blueprint({"acronimo_unidades": "JUSTICA"}, eq40),
        JUSTICA_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_justica_acento",
        _resolve_device_blueprint({"acronimo_unidades": "JUSTIÇA"}, eq40),
        JUSTICA_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_florestal",
        _resolve_device_blueprint({"acronimo_unidades": "FLORESTAL"}, eq40),
        FLORESTAL_DEVICE_BLUEPRINT,
    )
    check_eq(
        "device_blueprint_justica_lan2_preserva_vlan",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "JUSTIÇA",
                "ip_lan_01_unidades": "10.1.1.1/24",
                "mv_ip_lan_sec_unidades": "10.1.2.1/24",
            },
            eq40,
        ),
        "SJC_HUB-C3-C4_40F_REDE_LAN_1_2_VLAN_VOZ_ASSOC",
    )
    check_eq(
        "device_blueprint_florestal_lan2",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "FLORESTAL",
                "ip_lan_01_unidades": "10.1.1.1/24",
                "mv_ip_lan_sec_unidades": "10.1.2.1/24",
            },
            eq40,
        ),
        "FLORESTAL_HUB-C1-C2_40F_REDE_LAN_1_2",
    )
    check_eq(
        "device_blueprint_tjsp_lan1",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "TJSP",
                "ip_lan_01_unidades": "10.1.1.1/24",
            },
            {"modelo_equipamentos": "FortiGate 60F"},
        ),
        "TJ_HUB-C1-C2_60F_REDE_LAN_1_VOZ_WIFI",
    )
    check_eq(
        "device_blueprint_tjsp_lan2",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "TJSP",
                "ip_lan_01_unidades": "10.1.1.1/24",
                "mv_ip_lan_sec_unidades": "10.1.2.1/24",
            },
            {"modelo_equipamentos": "FortiGate 60F"},
        ),
        "TJ_HUB-C1-C2_60F_REDE_LAN_1_2_VOZ_WIFI",
    )
    check_eq(
        "device_blueprint_tjsp_lan3",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "TJSP",
                "ip_lan_01_unidades": "10.1.1.1/24",
                "mv_ip_lan_sec_unidades": "10.1.2.1/24",
                "mv_ip_lan_ter_unidades": "10.1.3.1/24",
            },
            {"modelo_equipamentos": "FortiGate 60F"},
        ),
        "TJ_HUB-C1-C2_60F_REDE_LAN_1_2_3_VOZ_WIFI",
    )
    check_eq(
        "device_blueprint_tjsp_lan4",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "TJSP",
                "ip_lan_01_unidades": "10.1.1.1/24",
                "mv_ip_lan_sec_unidades": "10.1.2.1/24",
                "mv_ip_lan_ter_unidades": "10.1.3.1/24",
                "mv_ip_lan_qua_unidades": "10.1.4.1/24",
            },
            {"modelo_equipamentos": "FortiGate 60F"},
        ),
        "TJ_HUB-C1-C2_60F_REDE_LAN_1_2_3_4_VOZ_WIFI",
    )
    check_eq(
        "device_blueprint_procon_lan4",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "PROCON",
                "ip_lan_01_unidades": "10.1.1.1/24",
                "mv_ip_lan_sec_unidades": "10.1.2.1/24",
                "mv_ip_lan_ter_unidades": "10.1.3.1/24",
                "mv_ip_lan_qua_unidades": "10.1.4.1/24",
            },
            eq40,
        ),
        "PROCOM_HUB-C3-C4_40F_REDE_LAN_1_2_3_4",
    )
    check_eq(
        "device_blueprint_rede_sec_sem_ip",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "DIPOL",
                "ip_lan_01_unidades": "10.77.176.161/27",
                "mv_rede_lan_sec_unidades": "10.77.176.160",
            },
            eq40,
        ),
        "PCSPO_HUB-C3-C4_40F_REDE_LAN_1_2",
    )
    check_eq(
        "device_blueprint_rede_ter_sem_ip",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "DIPOL",
                "ip_lan_01_unidades": "10.77.176.161/27",
                "mv_ip_lan_sec_unidades": "10.77.176.161/27",
                "mv_rede_lan_ter_unidades": "10.77.176.161",
            },
            eq40,
        ),
        "PCSPO_HUB-C3-C4_40F_REDE_LAN_1_2_3",
    )
    check_eq(
        "device_blueprint_rede_ter_sem_sec_nao_avanca",
        _resolve_device_blueprint(
            {
                "acronimo_unidades": "DIPOL",
                "ip_lan_01_unidades": "10.77.176.161/27",
                "mv_rede_lan_ter_unidades": "10.77.176.161",
            },
            eq40,
        ),
        "PCSPO_HUB-C3-C4_40F_REDE_LAN_1",
    )
    from prodesp.prodesp.blueprint.prodesp_csv_generator import BLUEPRINT_MASK_OPTIONS, cidr_to_mask

    check_eq("mask_options_count", len(BLUEPRINT_MASK_OPTIONS), 33)
    check_eq("mask_options_slash0", BLUEPRINT_MASK_OPTIONS[0], ("0.0.0.0", "/0"))
    check_eq("mask_options_slash24", BLUEPRINT_MASK_OPTIONS[24], ("255.255.255.0", "/24"))
    check_eq("mask_options_slash31", BLUEPRINT_MASK_OPTIONS[31], ("255.255.255.254", "/31"))
    check_eq("mask_options_slash32", BLUEPRINT_MASK_OPTIONS[32], ("255.255.255.255", "/32"))
    check_eq("cidr_to_mask_23", cidr_to_mask("/23"), "255.255.254.0")
    check_true("hub_c3_c4_dpesp", "C3-C4" in DPESP_DEVICE_BLUEPRINT and "C1-C2" not in DPESP_DEVICE_BLUEPRINT)
    check_true("hub_c3_c4_sap", "C3-C4" in SAP_DEVICE_BLUEPRINT)


def test_lan_extra_cascade_validation():
    from prodesp.prodesp.blueprint.prodesp_csv_generator import validar_dados_blueprint

    base_u = {
        "hostname_unidades": "H",
        "acronimo_unidades": "PROCON",
        "ip_lan_01_unidades": "10.1.1.1/24",
        "loopback_cliente_unidades": "1.1.1.1",
        "loopback_on_bgp_unidades": "1.1.1.2",
        "loopback_vivo_unidades": "1.1.1.3",
        "mv_ip_lan_ter_unidades": "10.1.3.1/24",
    }
    eq = {"serial_equipamentos": "FGT60FTK"}
    links = [
        {
            "tipo_links": "MPLS",
            "operadora_links": "VIVO",
            "designador_links": "D1",
            "ip_wan_links": "1.1.1.1",
            "ip_gateway_links": "1.1.1.2",
            "ip_mascara_links": "255.255.255.252",
            "velocidade_links": "100",
            "id_vgr_links": "V1",
        }
    ]
    ok, errs = validar_dados_blueprint(base_u, eq, links)
    check_true("ter_sem_sec_invalido", not ok)
    check_true(
        "ter_sem_sec_msg",
        any("TER exige" in e for e in errs),
    )
    base_u["mv_ip_lan_sec_unidades"] = "10.1.2.1/24"
    base_u["mv_ip_lan_qua_unidades"] = "10.1.4.1/24"
    del base_u["mv_ip_lan_ter_unidades"]
    ok2, errs2 = validar_dados_blueprint(base_u, eq, links)
    check_true("qua_sem_ter_invalido", not ok2)
    check_true("qua_sem_ter_msg", any("QUA exige IP LAN TER" in e for e in errs2))


def test_device_blueprint_modelo_equipamento():
    check_eq(
        "sde_60f",
        _resolve_device_blueprint(
            {"acronimo_unidades": "SDE"},
            {"modelo_equipamentos": "FortiGate 60F"},
        ),
        "SDE_HUB-C3-C4_60F_REDE_LAN_1",
    )
    check_eq(
        "saptele_60f_mantem_hub_c5_c6",
        _resolve_device_blueprint(
            {"acronimo_unidades": "SAPTELE"},
            {"modelo_equipamentos": "FortiGate 60F"},
        ),
        "SAP-TELE_HUB-C5-C6_60F_REDE_LAN_1",
    )
    check_eq(
        "pge_60f",
        _resolve_device_blueprint(
            {"acronimo_unidades": "PGE"},
            {"modelo_equipamentos": "FortiGate 60F", "serial_equipamentos": "FGT60FTK123"},
        ),
        "PGE_HUB-C3-C4_HSW_60F_REDE_LAN_1",
    )
    check_eq(
        "default_oes_40f",
        _resolve_device_blueprint({"acronimo_unidades": "PCESP"}, {}),
        "BP_OES_40F",
    )
    check_eq(
        "default_oes_60f_serial",
        _resolve_device_blueprint(
            {"acronimo_unidades": "PCESP"},
            {"serial_equipamentos": "FGT60FTK999"},
        ),
        "BP_OES_60F",
    )
    check_eq(
        "apply_modelo_helper",
        _apply_modelo_to_device_blueprint(SDE_DEVICE_BLUEPRINT, "60F"),
        "SDE_HUB-C3-C4_60F_REDE_LAN_1",
    )


def test_dpesp_selj_der_sde_csv_modelo_rede_lan():
    """DPESP, SELJ, DER e SDE usam layout MV_REDE_LAN (mesma regra DETRAN), não MV_10_ legado."""
    base = {
        "hostname_unidades": "test-hub",
        "ip_lan_01_unidades": "10.138.42.129/29",
        "loopback_cliente_unidades": "10.252.1.1",
        "loopback_on_bgp_unidades": "10.253.1.1",
        "loopback_vivo_unidades": "10.254.1.1",
    }
    equipamento = {"serial_equipamentos": "SN-DPESP"}
    links = [{
        "tipo_links": "MPLS", "ip_wan_links": "10.1.1.1", "ip_gateway_links": "10.1.1.2",
        "ip_mascara_links": "255.255.255.252", "velocidade_links": "100", "id_vgr_links": "1",
    }]
    for acr, expected_bp in (
        ("DPESP", DPESP_DEVICE_BLUEPRINT),
        ("SELJ", SELJ_DEVICE_BLUEPRINT),
        ("DER", DER_DEVICE_BLUEPRINT),
        ("SDE", SDE_DEVICE_BLUEPRINT),
        ("CEETEPS", CEETEPS_DEVICE_BLUEPRINT),
        # POUPATEMPO: template fixo …_REDE_LAN_VOZ (sem sufixo dinâmico por qtd de LAN)
        ("POUPATEMPO", "PPT_HUB-C3-C4_40F_REDE_LAN_VOZ"),
        ("CDHU", CDHU_DEVICE_BLUEPRINT),
        ("JUSTIÇA", JUSTICA_DEVICE_BLUEPRINT),
        ("FLORESTAL", FLORESTAL_DEVICE_BLUEPRINT),
    ):
        unidade = {**base, "acronimo_unidades": acr}
        with tempfile.TemporaryDirectory() as tmp:
            from prodesp.prodesp.blueprint import prodesp_csv_generator
            old_dir = prodesp_csv_generator.CSV_DIR
            try:
                prodesp_csv_generator.CSV_DIR = tmp
                path = gerar_csv_blueprint_prodesp(unidade, equipamento, links)
                with open(path, encoding="utf-8-sig", newline="") as f:
                    reader = csv.reader(f, delimiter=";")
                    headers = next(reader)
                    values = next(reader)
                row = dict(zip(headers, values))
            finally:
                prodesp_csv_generator.CSV_DIR = old_dir
        check_eq(f"{acr.lower()}_device_blueprint", row.get("Device Blueprint"), expected_bp)
        check_true(f"{acr.lower()}_tem_mv_rede_lan", "MV_REDE_LAN" in headers)
        check_true(f"{acr.lower()}_sem_mv_10", "MV_10_" not in headers)
        check_eq(f"{acr.lower()}_rede_lan_minus_one", row.get("MV_REDE_LAN"), "10.138.42.128")


def test_rede_lan_regras():
    ip = "10.138.42.129/29"
    check_eq(
        "rede_lan_regra_nova",
        _resolve_rede_lan(ip, "nova"),
        "10.138.42.128",
    )
    check_eq(
        "rede_lan_regra_antiga",
        _resolve_rede_lan(ip, "antiga"),
        "10.138.42.0",
    )
    check_eq("ip_lan_minus_one_dipol", get_ip_lan_minus_one("10.75.13.193/26"), "10.75.13.192")
    check_eq("normalize_regra_default", _normalize_rede_lan_regra(None), "nova")
    check_eq("normalize_regra_antiga", _normalize_rede_lan_regra("antiga"), "antiga")
    check_eq("regra_sap", _rede_lan_regra_for_unidade({"acronimo_unidades": "SAP"}), "nova")
    check_eq("regra_seds", _rede_lan_regra_for_unidade({"acronimo_unidades": "SEDS"}), "antiga")
    check_eq("regra_procon", _rede_lan_regra_for_unidade({"acronimo_unidades": "PROCON"}), "nova")
    check_eq(
        "regra_pro_sangue",
        _rede_lan_regra_for_unidade({"acronimo_unidades": "PRO-SANGUE"}),
        "nova",
    )
    check_eq(
        "regra_sp_aguas",
        _rede_lan_regra_for_unidade({"acronimo_unidades": "SP-AGUAS"}),
        "nova",
    )
    check_eq("regra_detran", _rede_lan_regra_for_unidade({"acronimo_unidades": "DETRAN"}), "nova")
    check_eq("regra_poupatempo", _rede_lan_regra_for_unidade({"acronimo_unidades": "POUPATEMPO"}), "nova")
    check_eq("regra_pcesp", _rede_lan_regra_for_unidade({"acronimo_unidades": "PCESP"}), "nova")
    check_eq("regra_dipol", _rede_lan_regra_for_unidade({"acronimo_unidades": "DIPOL"}), "nova")
    check_true("detran_sem_dhcp_server_1_flag", not _should_emit_dhcp_server_1({"acronimo_unidades": "DETRAN"}))
    check_true("sap_com_dhcp_server_1_flag", _should_emit_dhcp_server_1({"acronimo_unidades": "SAP"}))
    check_true("saptele_com_dhcp_server_1_flag", _should_emit_dhcp_server_1({"acronimo_unidades": "SAPTELE"}))
    check_true("sap_tele_alias_com_dhcp_server_1_flag", _should_emit_dhcp_server_1({"acronimo_unidades": "SAP-TELE"}))
    check_eq(
        "dhcp_lan_seds",
        _resolve_dhcp_lan_range({"acronimo_unidades": "SEDS"}, "10.22.1.6/24"),
        ("10.22.1.10", "10.22.1.60"),
    )
    check_eq(
        "dhcp_lan_detran_vazio",
        _resolve_dhcp_lan_range({"acronimo_unidades": "DETRAN"}, "10.22.1.6/24"),
        ("", ""),
    )


def test_ip_lan_cidr_23_preservado_no_csv():
    """Prefixo /23 não deve ser alterado para /24 na geração do blueprint."""
    ip_lan = "10.131.25.1/23"
    pairs = dict(
        _build_blueprint_rede_lan_row_pairs(
            {
                "acronimo_unidades": "DETRAN",
                "hostname_unidades": "HOST-TEST",
                "ip_lan_01_unidades": ip_lan,
            },
            {"serial_equipamentos": "SN123"},
            [],
        )
    )
    check_eq("ip_lan_cidr23_ip", pairs["MV_IP_LAN"], "10.131.25.1")
    check_eq("ip_lan_cidr23_mask", pairs["MV_MASK_LAN"], "255.255.254.0")
    check_eq("ip_lan_cidr23_rede", pairs["MV_REDE_LAN"], "10.131.25.0")


def test_cabecalhos_detram_novo():
    pairs = _build_blueprint_rede_lan_row_pairs(
        _planilha_exemplo_unidade(),
        _planilha_exemplo_equipamento(),
        _planilha_exemplo_links(),
    )
    headers = [h for h, _ in pairs]
    expected_start = [
        "Serial Number",
        "Device Blueprint",
        "Name",
        "MV_LOCALIDADE",
        "MV_LATITUDE",
        "MV_LONGITUDE",
        "MV_HOSTNAME_SPK",
        "MV_MGMT_PRODESP",
        "MV_IP_BGP",
        "MV_MGMT_VIVO",
        "MV_REDE_LAN",
        "MV_IP_LAN",
        "MV_MASK_LAN",
        "MV_DHCP_START_LAN",
        "MV_DHCP_END_LAN",
        "MV_REDE_VOZ",
        "MV_IP_VOZ",
        "MV_MASK_VOZ",
    ]
    check_eq("cabecalhos_inicio", headers[: len(expected_start)], expected_start)
    check_true("sem_cabecalhos_legados", "MV_10_" not in headers)
    check_true("sem_dhcp_server_1_detran", "MV_dhcp_server_1_start" not in headers)
    check_eq("dhcp_lan_start_vazio", dict(pairs).get("MV_DHCP_START_LAN"), "")
    check_eq("dhcp_lan_end_vazio", dict(pairs).get("MV_DHCP_END_LAN"), "")
    check_true("sem_mv_10_252", "MV_10_252" not in headers)


def _read_legacy_mv10(acronimo, ip_lan="10.14.128.1/24"):
    unidade = {
        "acronimo_unidades": acronimo,
        "hostname_unidades": "test-host",
        "ip_lan_01_unidades": ip_lan,
        "loopback_cliente_unidades": "10.252.1.1",
        "loopback_on_bgp_unidades": "10.253.1.1",
        "loopback_vivo_unidades": "10.254.1.1",
    }
    equipamento = {"serial_equipamentos": "SN123"}
    links = [{
        "tipo_links": "MPLS", "ip_wan_links": "10.1.1.1", "ip_gateway_links": "10.1.1.2",
        "ip_mascara_links": "255.255.255.252", "velocidade_links": "100", "id_vgr_links": "999",
    }]
    with tempfile.TemporaryDirectory() as tmp:
        from prodesp.prodesp.blueprint import prodesp_csv_generator
        old_dir = prodesp_csv_generator.CSV_DIR
        try:
            prodesp_csv_generator.CSV_DIR = tmp
            path = gerar_csv_blueprint_prodesp(unidade, equipamento, links)
            with open(path, encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f, delimiter=";")
                headers = next(reader)
                values = next(reader)
            return dict(zip(headers, values))
        finally:
            prodesp_csv_generator.CSV_DIR = old_dir


def test_valores_planilha():
    pairs = dict(
        _build_blueprint_rede_lan_row_pairs(
            _planilha_exemplo_unidade(),
            _planilha_exemplo_equipamento(),
            _planilha_exemplo_links(),
        )
    )
    check_eq("serial", pairs["Serial Number"], "FGT40FTK25034989")
    check_eq("device", pairs["Device Blueprint"], DETRAN_DEVICE_BLUEPRINT)
    check_eq("rede_lan", pairs["MV_REDE_LAN"], "10.138.42.128")
    check_eq("ip_lan", pairs["MV_IP_LAN"], "10.138.42.129")
    check_eq("mask_lan", pairs["MV_MASK_LAN"], "255.255.255.248")
    check_eq("mv_rede_voz", pairs["MV_REDE_VOZ"], "")
    check_eq("mv_ip_voz", pairs["MV_IP_VOZ"], "")
    check_eq("mv_mask_voz", pairs["MV_MASK_VOZ"], "")
    check_eq("mgmt_prodesp", pairs["MV_MGMT_PRODESP"], "10.252.3.131")
    check_eq("description_inet", pairs["MV_DESCRIPTION_INET_1"], "SAI-BL_INET1_2187527_300Mb")
    check_eq("description_mpls", pairs["MV_DESCRIPTION_MPLS_1"], "SCM_MPLS1_2155440_34Mb")
    check_eq("bandwidth_inet", pairs["MV_BANDWIDTH_INET_1"], "300")
    check_eq("bandwidth_mpls", pairs["MV_BANDWIDTH_MPLS_1"], "34")


def test_sap_csv_modelo_rede_lan_minus_one():
    """SAP usa layout MV_REDE_LAN com regra nova (IP − 1) e MV_dhcp_server_1_*."""
    ip = "10.138.42.129/29"
    row_sap = _read_legacy_mv10("SAP", ip_lan=ip)
    row_pcesp = _read_legacy_mv10("PCESP", ip_lan=ip)
    check_eq("sap_device_blueprint", row_sap.get("Device Blueprint"), SAP_DEVICE_BLUEPRINT)
    check_true("sap_tem_mv_rede_lan", "MV_REDE_LAN" in row_sap)
    check_true("sap_sem_mv_10", "MV_10_" not in row_sap)
    check_eq("sap_rede_lan_minus_one", row_sap.get("MV_REDE_LAN"), "10.138.42.128")
    check_eq("sap_dhcp_lan_start_vazio", row_sap.get("MV_DHCP_START_LAN"), "")
    check_eq("sap_dhcp_lan_end_vazio", row_sap.get("MV_DHCP_END_LAN"), "")
    check_eq("sap_dhcp_server_1_start", row_sap.get("MV_dhcp_server_1_start"), "10.138.42.10")
    check_eq("sap_dhcp_server_1_end", row_sap.get("MV_dhcp_server_1_end"), "10.138.42.250")
    check_eq("sap_mv_rede_voz_vazio", row_sap.get("MV_REDE_VOZ"), "")
    check_eq("sap_mv_ip_voz_vazio", row_sap.get("MV_IP_VOZ"), "")
    check_eq("sap_mv_mask_voz_vazio", row_sap.get("MV_MASK_VOZ"), "")
    check_true("pcesp_fallback_rede_lan", "MV_REDE_LAN" in row_pcesp)
    check_true("pcesp_fallback_sem_mv10", "MV_10_" not in row_pcesp)
    check_eq("pcesp_fallback_rede_lan_val", row_pcesp.get("MV_REDE_LAN"), "10.138.42.128")
    check_eq("pcesp_fallback_device", row_pcesp.get("Device Blueprint"), "BP_OES_40F")


def test_seds_csv_rede_zero_e_dhcp_lan():
    """SEDS: MV_REDE_LAN .0; MV_DHCP_START/END .10–.60; sem dhcp_server_1."""
    ip = "10.22.1.6/24"
    pairs = dict(
        _build_blueprint_rede_lan_row_pairs(
            {
                "acronimo_unidades": "SEDS",
                "hostname_unidades": "SEDS-TEST",
                "ip_lan_01_unidades": ip,
            },
            {"serial_equipamentos": "SN123", "modelo_equipamentos": "FortiGate 40F"},
            [],
        )
    )
    check_eq("seds_device", pairs["Device Blueprint"], SEDS_DEVICE_BLUEPRINT)
    check_eq("seds_rede_lan_zero", pairs["MV_REDE_LAN"], "10.22.1.0")
    check_eq("seds_ip_lan", pairs["MV_IP_LAN"], "10.22.1.6")
    check_eq("seds_dhcp_start", pairs["MV_DHCP_START_LAN"], "10.22.1.10")
    check_eq("seds_dhcp_end", pairs["MV_DHCP_END_LAN"], "10.22.1.60")
    check_true("seds_sem_dhcp_server_1", "MV_dhcp_server_1_start" not in pairs)


def test_procon_csv_como_detran():
    """PROCON: layout REDE_LAN, IP − 1, DHCP LAN vazio, template PROCOM_."""
    ip = "10.138.42.129/29"
    pairs = dict(
        _build_blueprint_rede_lan_row_pairs(
            {
                "acronimo_unidades": "PROCON",
                "hostname_unidades": "PROCON-TEST",
                "ip_lan_01_unidades": ip,
            },
            {"serial_equipamentos": "SN123", "modelo_equipamentos": "FortiGate 40F"},
            [],
        )
    )
    check_eq("procon_device", pairs["Device Blueprint"], PROCON_DEVICE_BLUEPRINT)
    check_eq("procon_rede_lan_minus_one", pairs["MV_REDE_LAN"], "10.138.42.128")
    check_eq("procon_dhcp_lan_vazio", pairs["MV_DHCP_START_LAN"], "")
    check_true("procon_sem_dhcp_server_1", "MV_dhcp_server_1_start" not in pairs)


def test_pro_sangue_csv_como_procon():
    """PRO-SANGUE: layout REDE_LAN (igual PROCON), IP − 1, template PROSANGUE_."""
    ip = "10.138.42.129/29"
    pairs = dict(
        _build_blueprint_rede_lan_row_pairs(
            {
                "acronimo_unidades": "PRO-SANGUE",
                "hostname_unidades": "PROSANGUE-TEST",
                "ip_lan_01_unidades": ip,
            },
            {"serial_equipamentos": "SN123", "modelo_equipamentos": "FortiGate 40F"},
            [],
        )
    )
    check_eq("pro_sangue_device", pairs["Device Blueprint"], PROSANGUE_DEVICE_BLUEPRINT)
    check_eq("pro_sangue_rede_lan_minus_one", pairs["MV_REDE_LAN"], "10.138.42.128")
    check_eq("pro_sangue_dhcp_lan_vazio", pairs["MV_DHCP_START_LAN"], "")
    check_true("pro_sangue_sem_dhcp_server_1", "MV_dhcp_server_1_start" not in pairs)


def test_sp_aguas_csv_como_procon():
    """SP-AGUAS: layout REDE_LAN (igual PROCON), IP − 1, template SPAGUAS_."""
    ip = "10.138.42.129/29"
    pairs = dict(
        _build_blueprint_rede_lan_row_pairs(
            {
                "acronimo_unidades": "SP-AGUAS",
                "hostname_unidades": "SPAGUAS-TEST",
                "ip_lan_01_unidades": ip,
            },
            {"serial_equipamentos": "SN123", "modelo_equipamentos": "FortiGate 40F"},
            [],
        )
    )
    check_eq("sp_aguas_device", pairs["Device Blueprint"], SPAGUAS_DEVICE_BLUEPRINT)
    check_eq("sp_aguas_rede_lan_minus_one", pairs["MV_REDE_LAN"], "10.138.42.128")
    check_eq("sp_aguas_dhcp_lan_vazio", pairs["MV_DHCP_START_LAN"], "")
    check_true("sp_aguas_sem_dhcp_server_1", "MV_dhcp_server_1_start" not in pairs)


def test_der_sde_nao_usam_mv10_legado():
    for acr in ("DER", "SDE"):
        row = _read_legacy_mv10(acr, ip_lan="10.138.42.129/29")
        check_true(f"{acr.lower()}_tem_mv_rede_lan", "MV_REDE_LAN" in row)
        check_true(f"{acr.lower()}_sem_mv_10", "MV_10_" not in row)
        check_eq(f"{acr.lower()}_rede_lan_minus_one", row.get("MV_REDE_LAN"), "10.138.42.128")


def test_fallback_bp_oes_usa_rede_lan():
    """Acrônimo fora do catálogo: Device BP_OES_*, layout MV_REDE_LAN (não MV_10_)."""
    unidade = {
        "acronimo_unidades": "PCESP",
        "hostname_unidades": "pcesp-test",
        "ip_lan_01_unidades": "10.14.128.1/24",
        "loopback_cliente_unidades": "10.252.1.1",
        "loopback_on_bgp_unidades": "10.253.1.1",
        "loopback_vivo_unidades": "10.254.1.1",
    }
    equipamento = {"serial_equipamentos": "SN123"}
    links = [
        {
            "tipo_links": "MPLS",
            "ip_wan_links": "10.1.1.1",
            "ip_gateway_links": "10.1.1.2",
            "ip_mascara_links": "255.255.255.252",
            "velocidade_links": "100",
            "id_vgr_links": "999",
        }
    ]
    with tempfile.TemporaryDirectory() as tmp:
        from prodesp.prodesp.blueprint import prodesp_csv_generator

        old_dir = prodesp_csv_generator.CSV_DIR
        try:
            prodesp_csv_generator.CSV_DIR = tmp
            path = gerar_csv_blueprint_prodesp(unidade, equipamento, links)
            with open(path, encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f, delimiter=";")
                headers = next(reader)
                values = next(reader)
            row = dict(zip(headers, values))
            check_true("pcesp_tem_mv_rede_lan", "MV_REDE_LAN" in headers)
            check_true("pcesp_sem_mv_10", "MV_10_" not in headers)
            check_true("pcesp_sem_dhcp_server_1", "MV_dhcp_server_1_start" not in headers)
            check_eq("pcesp_device", row.get("Device Blueprint"), "BP_OES_40F")
            check_eq("pcesp_rede_lan_minus_one", row.get("MV_REDE_LAN"), "10.14.128.0")
            check_eq(
                "pcesp_device_resolve",
                _resolve_device_blueprint(unidade),
                "BP_OES_40F",
            )
        finally:
            prodesp_csv_generator.CSV_DIR = old_dir


def test_mv_opcionais_csv_colunas():
    unidade = {
        **_planilha_exemplo_unidade(),
        "mv_ip_transito_unidades": "10.250.1.1",
        "mv_mask_transito_unidades": "255.255.255.0",
        "mv_ip_swt_unidades": "10.250.2.1",
        "mv_rede_voz_unidades": "10.20.0.0",
        "mv_mask_voz_unidades": "255.255.255.0",
        "mv_rede_lan_assoc_unidades": "10.30.0.0",
        "mv_mask_lan_assoc_unidades": "255.255.255.0",
        "mv_rede_totem_unidades": "10.40.0.0",
        "mv_mask_totem_unidades": "255.255.255.128",
    }
    pairs = build_blueprint_row_pairs(
        unidade, _planilha_exemplo_equipamento(), _planilha_exemplo_links()
    )
    data = dict(pairs)
    check_eq("mv ip transito csv", data.get("MV_IP_TRANSITO"), "10.250.1.1")
    check_eq("mv rede voz csv", data.get("MV_REDE_VOZ"), "10.20.0.0")
    check_eq("mv mask totem csv", data.get("MV_MASK_TOTEM"), "255.255.255.128")


def test_lan_sec_ter_qua_e_wifi_guest_csv():
    from prodesp.prodesp.blueprint.prodesp_csv_generator import split_ip_and_mask_from_cidr
    from prodesp.prodesp.blueprint.prodesp_equipment import blueprint_intf_fields_for_equipment

    check_eq(
        "split_cidr",
        split_ip_and_mask_from_cidr("10.151.10.10/24"),
        ("10.151.10.10", "255.255.255.0"),
    )
    check_eq("split_sem_cidr", split_ip_and_mask_from_cidr("10.1.1.1"), ("10.1.1.1", ""))

    unidade = {
        "acronimo_unidades": "DETRAN",
        "hostname_unidades": "HOST-LAN",
        "ip_lan_01_unidades": "10.14.128.1/24",
        "loopback_cliente_unidades": "10.252.1.1",
        "loopback_on_bgp_unidades": "10.253.1.1",
        "loopback_vivo_unidades": "10.254.1.1",
        "mv_ip_lan_sec_unidades": "10.152.10.6/24",
        "mv_rede_lan_sec_unidades": "10.152.10.0",
        "mv_ip_lan_ter_unidades": "10.153.10.6/24",
        "mv_rede_lan_ter_unidades": "10.153.10.0",
        "mv_ip_lan_qua_unidades": "10.154.10.6/25",
        "mv_rede_lan_qua_unidades": "10.154.10.0",
        "mv_rede_wifi_guest_unidades": "10.160.10.0",
        "mv_ip_wifi_guest_unidades": "10.160.10.10/24",
        "mv_dhcp_start_wifi_guest_unidades": "10.160.10.20",
        "mv_dhcp_end_wifi_guest_unidades": "10.160.10.50",
        "mv_reserva_start_wifi_guest_unidades": "10.160.10.100",
        "mv_reserva_end_wifi_guest_unidades": "10.160.10.110",
    }
    eq = {"serial_equipamentos": "FGT40FTK25008428", "modelo_equipamentos": "FortiGate 40F"}
    data = dict(_build_blueprint_rede_lan_row_pairs(unidade, eq, []))
    check_eq("lan_sec_ip", data.get("MV_IP_LAN_SEC"), "10.152.10.6")
    check_eq("lan_sec_mask", data.get("MV_MASK_LAN_SEC"), "255.255.255.0")
    check_eq("lan_sec_rede", data.get("MV_REDE_LAN_SEC"), "10.152.10.0")
    check_eq("lan_ter_ip", data.get("MV_IP_LAN_TER"), "10.153.10.6")
    check_eq("lan_qua_mask", data.get("MV_MASK_LAN_QUA"), "255.255.255.128")
    check_eq("wifi_ip", data.get("MV_IP_WIFI_GUEST"), "10.160.10.10")
    check_eq("wifi_mask", data.get("MV_MASK_WIFI_GUEST"), "255.255.255.0")
    check_eq("wifi_reserva_start", data.get("MV_RESERVA_START_WIFI_GUEST"), "10.160.10.100")
    check_eq("intf_inet_1_40f", data.get("MV_INTF_INET_1"), "wan")
    check_eq("intf_lan_40f", data.get("MV_INTF_LAN"), "lan1")

    intf_60 = blueprint_intf_fields_for_equipment("FortiGate 60F", "")
    check_eq("intf_60_inet1", intf_60["MV_INTF_INET_1"], "wan1")
    intf_120 = blueprint_intf_fields_for_equipment("FortiGate 120G", "")
    check_eq("intf_120_lan", intf_120["MV_INTF_LAN"], "port16")
    intf_unk = blueprint_intf_fields_for_equipment("FortiGate 70F", "")
    check_eq("intf_unk_vazio", intf_unk["MV_INTF_INET_1"], "")
    intf_empty = blueprint_intf_fields_for_equipment("", "")
    check_eq("intf_empty", intf_empty["MV_INTF_LAN"], "")


def test_lan_wifi_csv_stubs_vazios():
    """Sem LAN/WiFi no banco: headers existem e saem vazios (não omitidos)."""
    unidade = {
        "acronimo_unidades": "DETRAN",
        "hostname_unidades": "HOST-EMPTY",
        "ip_lan_01_unidades": "10.14.128.1/24",
        "loopback_cliente_unidades": "10.252.1.1",
        "loopback_on_bgp_unidades": "10.253.1.1",
        "loopback_vivo_unidades": "10.254.1.1",
    }
    eq = {"serial_equipamentos": "FGT40FTK25008428", "modelo_equipamentos": "FortiGate 40F"}
    data = dict(_build_blueprint_rede_lan_row_pairs(unidade, eq, []))
    for hdr in (
        "MV_IP_LAN_SEC",
        "MV_MASK_LAN_SEC",
        "MV_REDE_LAN_SEC",
        "MV_IP_LAN_TER",
        "MV_MASK_LAN_TER",
        "MV_IP_LAN_QUA",
        "MV_MASK_LAN_QUA",
        "MV_IP_WIFI_GUEST",
        "MV_MASK_WIFI_GUEST",
        "MV_RESERVA_END_WIFI_GUEST",
    ):
        check_true(f"stub header {hdr}", hdr in data)
        check_eq(f"stub vazio {hdr}", data.get(hdr), "")


def main():
    test_identificacao_detran()
    test_lan_extra_cascade_validation()
    test_device_blueprint_modelo_equipamento()
    test_dpesp_selj_der_sde_csv_modelo_rede_lan()
    test_rede_lan_regras()
    test_ip_lan_cidr_23_preservado_no_csv()
    test_cabecalhos_detram_novo()
    test_valores_planilha()
    test_sap_csv_modelo_rede_lan_minus_one()
    test_seds_csv_rede_zero_e_dhcp_lan()
    test_procon_csv_como_detran()
    test_der_sde_nao_usam_mv10_legado()
    test_fallback_bp_oes_usa_rede_lan()
    test_mv_opcionais_csv_colunas()
    test_lan_sec_ter_qua_e_wifi_guest_csv()
    test_lan_wifi_csv_stubs_vazios()

    print(f"OK: {len(OK)}")
    for name in OK:
        print(f"  + {name}")
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for msg in FAILURES:
            print(f"  - {msg}")
        raise SystemExit(1)
    print("Todos os testes DETRAN blueprint passaram.")


if __name__ == "__main__":
    main()
