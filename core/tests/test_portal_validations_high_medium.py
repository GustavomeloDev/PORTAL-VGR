"""Testes dos utilitários de validação compartilhados (prioridade alta/média)."""

from __future__ import annotations

import unittest

from core.utils.coordinates import normalize_coordinate, validate_coordinate
from core.utils.fortinet_serial import infer_modelo_from_serial
from core.utils.link_required import (
    WAN_GRUPO_COMUNS,
    WAN_GRUPO_DHCP,
    WAN_GRUPO_ID_VGR,
    WAN_GRUPO_IP,
    WAN_GRUPO_PPPOE,
    WAN_GRUPO_VLAN,
    csv_wan_link_type,
    validate_link_required_by_modo,
    wan_campo_visivel,
    wan_grupos_visiveis,
)
from core.utils.network import validate_wan_gateway_distinct, wan_equals_gateway
from core.utils.text_ids import (
    is_designador_vivo_fora_padrao,
    is_id_vgr_link_fora_padrao,
    sanitize_pasted_text,
    validate_hostname,
    validate_id_vgr_link_format,
    validate_no_whitespace,
)
from core.utils.ticket_noc import validate_ticket_noc_format
from core.utils.velocity import normalize_velocity_mbps, validate_velocity_mbps


class TestTextIds(unittest.TestCase):
    def test_sanitize_paste(self):
        self.assertEqual(sanitize_pasted_text("\u200b1234567\u00a0"), "1234567")
        self.assertEqual(sanitize_pasted_text('"1234567"'), "1234567")

    def test_id_vgr_link(self):
        self.assertTrue(is_id_vgr_link_fora_padrao("123"))
        self.assertFalse(is_id_vgr_link_fora_padrao("1234567"))
        self.assertIsNotNone(validate_id_vgr_link_format("12/34"))

    def test_designador_vivo(self):
        self.assertTrue(is_designador_vivo_fora_padrao("123", "VIVO"))
        self.assertFalse(is_designador_vivo_fora_padrao("123", "CLARO"))
        self.assertFalse(
            is_designador_vivo_fora_padrao("123456789012345", "VIVO")
        )

    def test_hostname_ws(self):
        self.assertIsNotNone(validate_hostname("host name"))
        self.assertIsNone(validate_hostname("host-name"))

    def test_no_whitespace(self):
        self.assertIsNotNone(validate_no_whitespace("a b", "X"))


class TestNetworkExtra(unittest.TestCase):
    def test_wan_gw(self):
        self.assertTrue(wan_equals_gateway("10.0.0.1/24", "10.0.0.1"))
        self.assertIsNotNone(
            validate_wan_gateway_distinct("10.0.0.1", "10.0.0.1")
        )


class TestVelocityCoordsTicket(unittest.TestCase):
    def test_velocity(self):
        self.assertEqual(normalize_velocity_mbps("1G"), "1000")
        self.assertEqual(normalize_velocity_mbps("300 Mbps"), "300")
        self.assertIsNotNone(validate_velocity_mbps("abc"))
        self.assertEqual(normalize_velocity_mbps("20 Mbps"), "20")
        self.assertEqual(normalize_velocity_mbps("  40  "), "40")

    def test_coords(self):
        self.assertEqual(normalize_coordinate("-23,5505"), "-23.5505")
        self.assertIsNotNone(validate_coordinate("abc", field_label="Lat"))
        self.assertIsNone(validate_coordinate("", field_label="Lat"))
        self.assertIsNotNone(
            validate_coordinate("", field_label="Latitude", obrigatorio=True)
        )

    def test_ticket(self):
        self.assertIsNone(validate_ticket_noc_format("1680355"))
        self.assertIsNotNone(validate_ticket_noc_format("0680355"))


class TestFortinetInferAndRequired(unittest.TestCase):
    def test_infer(self):
        self.assertEqual(
            infer_modelo_from_serial("FGT40FTK2409D6QK"), "FortiGate 40F"
        )

    def test_required_static_vivo(self):
        err = validate_link_required_by_modo(
            {
                "tipo_link": "WAN",
                "modo_conexao": "STATIC",
                "operadora": "VIVO",
                "ip_address": "10.0.0.2",
                "gateway": "10.0.0.1",
            }
        )
        self.assertIsNotNone(err)
        self.assertIn("ID VGR", err)

    def test_required_static_vivo_ok(self):
        err = validate_link_required_by_modo(
            {
                "tipo_link": "WAN",
                "modo_conexao": "STATIC",
                "operadora": "VIVO",
                "ip_address": "10.0.0.2",
                "gateway": "10.0.0.1",
                "id_vgr_link": "1234567",
                "identificador": "wan1",
            }
        )
        self.assertIsNone(err)

    def test_required_static_mascara_opt_in(self):
        err = validate_link_required_by_modo(
            {
                "tipo_link": "WAN",
                "modo_conexao": "STATIC",
                "operadora": "VTAL",
                "ip_address": "10.0.0.2",
                "gateway": "10.0.0.1",
            },
            exigir_mascara=True,
        )
        self.assertIsNotNone(err)
        self.assertIn("Máscara", err)

    def test_lan_sem_modo(self):
        err = validate_link_required_by_modo(
            {
                "tipo_link": "LAN",
                "modo_conexao": "STATIC",
                "ip_address": "10.0.0.1/24",
            }
        )
        self.assertIsNone(err)


class TestWanVisibilidade(unittest.TestCase):
    def test_static_mostra_ip_vlan_id_vgr(self):
        vis = wan_grupos_visiveis("STATIC")
        self.assertIn(WAN_GRUPO_IP, vis)
        self.assertIn(WAN_GRUPO_VLAN, vis)
        self.assertIn(WAN_GRUPO_ID_VGR, vis)
        self.assertIn(WAN_GRUPO_COMUNS, vis)
        self.assertNotIn(WAN_GRUPO_PPPOE, vis)
        self.assertNotIn(WAN_GRUPO_DHCP, vis)
        self.assertTrue(wan_campo_visivel("MPLS", WAN_GRUPO_IP))

    def test_dhcp_sem_ip(self):
        vis = wan_grupos_visiveis("DHCP")
        self.assertIn(WAN_GRUPO_DHCP, vis)
        self.assertNotIn(WAN_GRUPO_IP, vis)
        self.assertNotIn(WAN_GRUPO_PPPOE, vis)
        self.assertFalse(wan_campo_visivel("DHCP", WAN_GRUPO_IP))

    def test_pppoe_credenciais(self):
        vis = wan_grupos_visiveis("pppoe")
        self.assertIn(WAN_GRUPO_PPPOE, vis)
        self.assertNotIn(WAN_GRUPO_IP, vis)

    def test_id_vgr_so_vivo(self):
        vis_vtal = wan_grupos_visiveis(
            "STATIC", operadora="VTAL", id_vgr_so_vivo=True
        )
        self.assertNotIn(WAN_GRUPO_ID_VGR, vis_vtal)
        vis_vivo = wan_grupos_visiveis(
            "STATIC", operadora="VIVO", id_vgr_so_vivo=True
        )
        self.assertIn(WAN_GRUPO_ID_VGR, vis_vivo)

    def test_csv_link_type_vlan_quando_vlan_wan(self):
        self.assertEqual(csv_wan_link_type("STATIC", "100"), "vlan")
        self.assertEqual(csv_wan_link_type("STATIC", ""), "static")
        self.assertEqual(csv_wan_link_type("DHCP", None), "dhcp")
        self.assertEqual(csv_wan_link_type("STATIC", "0"), "static")


class TestLinkVivo(unittest.TestCase):
    def test_mascara_par_impar_mpls(self):
        from core.utils.link_vivo import (
            VIVO_MASK_EVEN,
            VIVO_MASK_MPLS,
            VIVO_MASK_ODD,
            collect_vivo_link_pendencias,
            derive_vivo_gateway_from_wan,
            derive_vivo_mask_from_wan,
        )

        self.assertEqual(derive_vivo_mask_from_wan("187.12.125.110", "STATIC"), VIVO_MASK_EVEN)
        self.assertEqual(derive_vivo_mask_from_wan("187.115.201.143", "STATIC"), VIVO_MASK_ODD)
        self.assertEqual(derive_vivo_mask_from_wan("187.115.201.143", "MPLS"), VIVO_MASK_MPLS)
        self.assertEqual(
            derive_vivo_gateway_from_wan("187.115.201.143"), "187.115.201.142"
        )
        pend = collect_vivo_link_pendencias(
            modo="MPLS",
            operadora="VIVO",
            ip="187.115.201.143",
            mascara="255.255.255.254",
            gateway="187.115.201.142",
            designador="310000222013591",
        )
        self.assertTrue(any("248" in p or "/29" in p for p in pend))
        self.assertFalse(
            collect_vivo_link_pendencias(
                modo="STATIC",
                operadora="VTAL",
                ip="187.12.125.110",
                mascara="255.255.255.252",
                gateway="187.12.125.109",
                designador="MGBHE1000020947",
            )
        )


class TestOperadora(unittest.TestCase):
    def test_normalize_e_outros(self):
        from core.utils.operadora import (
            OPERADORA_SENTINEL_OUTROS,
            normalize_operadora,
            operadora_outros_value,
            operadora_select_value,
            resolve_operadora,
        )

        self.assertEqual(normalize_operadora(" vtal "), "VTAL")
        self.assertEqual(normalize_operadora("OUTROS"), "")
        self.assertEqual(resolve_operadora("VIVO", "vtal"), "VIVO")
        self.assertEqual(resolve_operadora("OUTROS", "vtal"), "VTAL")
        self.assertIsNone(resolve_operadora("OUTROS", ""))
        self.assertEqual(resolve_operadora("", "", fallback="claro"), "CLARO")
        self.assertEqual(operadora_select_value("VTAL"), OPERADORA_SENTINEL_OUTROS)
        self.assertEqual(operadora_select_value("vivo"), "VIVO")
        self.assertEqual(operadora_outros_value("vtal"), "VTAL")
        self.assertEqual(operadora_outros_value("VIVO"), "")


if __name__ == "__main__":
    unittest.main()
