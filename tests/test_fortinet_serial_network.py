"""Testes dos utilitários Fortinet serial e network (core)."""

from __future__ import annotations

import unittest

from core.utils.fortinet_serial import (
    FORTINET_MODEL_FRAGMENTS_ORDERED,
    fortinet_model_fragments,
    fortinet_modelo_fragment,
    infer_modelo_from_serial,
    is_fortinet_family,
    msg_serial_duplicado_global,
    normalize_modelo_fortigate,
    normalizar_serial,
    resolve_modelo_equipamento,
    serial_fortinet_valido,
    validate_serial_fortinet_format,
)
from core.utils.network import (
    canonicalize_ipv4,
    canonicalize_network_address,
    ipv4_network_address,
    is_valid_dotted_netmask,
    is_valid_ipv4,
    is_valid_ipv4_cidr,
    normalize_ipv4_excel_artifact,
    validate_ip_mask_group,
    validate_ipv4_field,
    validate_netmask_field,
    wan_equals_gateway,
)


class TestFortinetSerial(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(normalizar_serial("  fgt40ftk2409d6qk "), "FGT40FTK2409D6QK")

    def test_serial_ok(self):
        self.assertTrue(serial_fortinet_valido("FGT40FTK2409D6QK"))
        self.assertTrue(serial_fortinet_valido("FG120GTK25006244"))
        self.assertTrue(serial_fortinet_valido("FGT-40FTK2409D6QK"))

    def test_msg_serial_duplicado_global(self):
        msg = msg_serial_duplicado_global("  fgt40ftk2409bnjp ")
        self.assertIn("FGT40FTK2409BNJP", msg)
        self.assertNotIn("unidade", msg.lower())
        self.assertNotIn("cliente", msg.lower())

    def test_serial_fake(self):
        self.assertFalse(serial_fortinet_valido("123"))
        self.assertFalse(serial_fortinet_valido("TEST"))
        self.assertFalse(serial_fortinet_valido("FGT40F"))
        self.assertFalse(serial_fortinet_valido("FGT40FXXXXXXX"))
        self.assertFalse(serial_fortinet_valido("FGT40FTKAGUAS"))
        self.assertFalse(serial_fortinet_valido("FGT40FTK767676"))

    def test_validate_message(self):
        self.assertIsNone(validate_serial_fortinet_format("FGT40FTK2409D6QK"))
        err = validate_serial_fortinet_format("123")
        self.assertIsNotNone(err)
        self.assertIn("inválido", err.lower())

    def test_extra_model_fragment(self):
        # modelo hipotético ainda não na lista base
        fake = "FGT55HTK25001234"
        self.assertFalse(serial_fortinet_valido(fake))
        self.assertTrue(
            serial_fortinet_valido(fake, extra_model_fragments=("55H",))
        )

    def test_fragments_include_base(self):
        frags = fortinet_model_fragments()
        self.assertIn("40F", frags)
        self.assertEqual(frags[0], FORTINET_MODEL_FRAGMENTS_ORDERED[0])

    def test_is_fortinet_family(self):
        self.assertTrue(is_fortinet_family("Fortinet", None))
        self.assertTrue(is_fortinet_family(None, "FortiGate 40F"))
        self.assertFalse(is_fortinet_family("Cisco", "ISR"))
        self.assertFalse(is_fortinet_family(None, None))

    def test_normalize_modelo_alias(self):
        self.assertEqual(normalize_modelo_fortigate("FG 40F"), "FortiGate 40F")
        self.assertEqual(normalize_modelo_fortigate("FG-40F"), "FortiGate 40F")
        self.assertEqual(normalize_modelo_fortigate("FortiGate 40F"), "FortiGate 40F")
        self.assertEqual(fortinet_modelo_fragment("FG 40F"), "40F")
        self.assertEqual(fortinet_modelo_fragment("FortiGate 400F"), "400F")

    def test_resolve_modelo_serial_vence(self):
        modelo, err = resolve_modelo_equipamento("FGT40FTK2409D6QK", "FortiGate 900G")
        self.assertEqual(modelo, "FortiGate 40F")
        self.assertIsNone(err)

    def test_resolve_modelo_alias_sem_serial(self):
        modelo, err = resolve_modelo_equipamento("", "FG 60F")
        self.assertEqual(modelo, "FortiGate 60F")
        self.assertIsNone(err)

    def test_resolve_modelo_livre_bloqueado(self):
        modelo, err = resolve_modelo_equipamento("XYZ", "Qualquer Coisa")
        self.assertEqual(modelo, "")
        self.assertIsNotNone(err)

    def test_infer_strict(self):
        self.assertEqual(
            infer_modelo_from_serial("FGT40FTK2409D6QK", strict=True),
            "FortiGate 40F",
        )
        self.assertEqual(infer_modelo_from_serial("XYZ", strict=True), "")
        self.assertEqual(infer_modelo_from_serial("XYZ"), "FortiGate 40F")


class TestNetwork(unittest.TestCase):
    def test_ipv4(self):
        self.assertTrue(is_valid_ipv4("10.0.0.1"))
        self.assertTrue(is_valid_ipv4(" 192.168.1.10 "))
        self.assertFalse(is_valid_ipv4("10.0.0.256"))
        self.assertFalse(is_valid_ipv4("10.0.0.1/24"))

    def test_cidr(self):
        self.assertTrue(is_valid_ipv4_cidr("10.0.0.1/24"))
        self.assertTrue(is_valid_ipv4_cidr("10.0.0.1/0"))
        self.assertTrue(is_valid_ipv4_cidr("10.0.0.1/32"))
        self.assertFalse(is_valid_ipv4_cidr("10.0.0.1/33"))
        self.assertFalse(is_valid_ipv4_cidr("10.0.0.1"))

    def test_wan_gw(self):
        self.assertTrue(wan_equals_gateway("10.0.0.1", "10.0.0.1"))
        self.assertFalse(wan_equals_gateway("10.0.0.1", "10.0.0.2"))

    def test_validate_field(self):
        self.assertIsNone(validate_ipv4_field("10.0.0.1", label="WAN"))
        self.assertIsNotNone(validate_ipv4_field("10.0.0.1/24", label="WAN"))
        self.assertIsNone(
            validate_ipv4_field("10.0.0.1/24", label="LAN", allow_cidr=True)
        )


class TestExcelIpv4Artifact(unittest.TestCase):
    def test_12_digits(self):
        self.assertEqual(
            normalize_ipv4_excel_artifact(187115201143),
            "187.115.201.143",
        )
        self.assertEqual(
            normalize_ipv4_excel_artifact("255255255128"),
            "255.255.255.128",
        )

    def test_already_dotted(self):
        self.assertEqual(
            normalize_ipv4_excel_artifact("10.1.2.254"),
            "10.1.2.254",
        )


class TestIpMaskCalculator(unittest.TestCase):
    def test_network_address(self):
        self.assertEqual(
            ipv4_network_address("187.51.205.114", "255.255.255.252"),
            "187.51.205.112",
        )
        self.assertEqual(
            ipv4_network_address("10.1.2.254", "255.255.255.0"),
            "10.1.2.0",
        )

    def test_wan_ok(self):
        self.assertIsNone(
            validate_ip_mask_group(
                ip="187.51.205.114",
                mascara="255.255.255.252",
                gateway="187.51.205.113",
                label="WAN 1",
            )
        )

    def test_gateway_outra_rede(self):
        err = validate_ip_mask_group(
            ip="187.51.205.114",
            mascara="255.255.255.252",
            gateway="187.51.205.1",
            label="WAN 1",
        )
        self.assertIsNotNone(err)
        self.assertIn("não pertence", err)

    def test_vlan_subrede_divergente(self):
        err = validate_ip_mask_group(
            ip="10.1.2.254",
            mascara="255.255.255.0",
            subrede="10.1.40.0",
            label="VLAN 1",
        )
        self.assertIsNotNone(err)
        self.assertIn("10.1.2.0", err)

    def test_subrede_cidr_ok(self):
        self.assertIsNone(
            validate_ip_mask_group(
                ip="10.1.2.254",
                mascara="255.255.255.0",
                subrede="10.1.2.0/24",
                label="LAN",
            )
        )

    def test_mascara_nao_contigua(self):
        self.assertFalse(is_valid_dotted_netmask("255.255.0.255"))
        self.assertIsNotNone(
            validate_netmask_field("255.255.0.255", label="Máscara LAN")
        )

    def test_canonicalize_network_cidr(self):
        self.assertEqual(canonicalize_network_address("10.1.2.0/24"), "10.1.2.0")

    def test_vazio_nao_bloqueia(self):
        self.assertIsNone(validate_ip_mask_group(ip="", mascara="", label="LAN"))


class TestCanonicalizeIpv4(unittest.TestCase):
    def test_cidr_e_virgula(self):
        self.assertEqual(canonicalize_ipv4("169.250.0.3/32"), "169.250.0.3")
        self.assertEqual(canonicalize_ipv4("172,19,55,241"), "172.19.55.241")

    def test_leading_zeros(self):
        self.assertEqual(canonicalize_ipv4("010.001.002.254"), "10.1.2.254")

    def test_dma_lan(self):
        self.assertEqual(canonicalize_ipv4("10.1.2.254"), "10.1.2.254")


if __name__ == "__main__":
    unittest.main()
