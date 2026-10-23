"""Testes — unicidade canônica de IPv4 (sem banco)."""

from __future__ import annotations

import unittest

from core.utils.ip_unicidade import (
    cliente_aplica_unicidade_vlan,
    ipv4_iguais,
    msg_ip_duplicado_global,
    msg_vlan_ips_iguais_na_unidade,
    primeiro_conflito,
)


class TestIpUnicidade(unittest.TestCase):
    def test_ipv4_iguais_canônico(self):
        self.assertTrue(ipv4_iguais("10.0.0.1", "10.0.0.1"))
        self.assertFalse(ipv4_iguais("10.0.0.1", "10.0.0.2"))
        self.assertFalse(ipv4_iguais("", "10.0.0.1"))

    def test_opt_in_vlan(self):
        self.assertTrue(
            cliente_aplica_unicidade_vlan("01.928.075/0001-08", {"01.928.075/0001-08"})
        )
        self.assertFalse(
            cliente_aplica_unicidade_vlan("00.000.000/0001-00", {"01.928.075/0001-08"})
        )
        self.assertFalse(cliente_aplica_unicidade_vlan("01.928.075/0001-08", None))

    def test_msg_global_sem_unidade(self):
        msg = msg_ip_duplicado_global("Loopback Vivo", "10.9.0.1")
        self.assertIn("10.9.0.1", msg)
        self.assertNotIn("loja", msg.lower())

    def test_vlan_mesma_unidade(self):
        self.assertIn("mesmo IP", msg_vlan_ips_iguais_na_unidade("10.1.1.1"))

    def test_primeiro_conflito(self):
        hit = primeiro_conflito(
            [{"ip_address": "10.0.0.2"}, {"ip_address": "10.0.0.1"}],
            "10.0.0.1",
        )
        self.assertEqual(hit["ip_address"], "10.0.0.1")

    def test_wan_vivo_so_aplica_vivo(self):
        from core.utils.ip_unicidade import aplica_unicidade_ip_wan_vivo

        self.assertTrue(aplica_unicidade_ip_wan_vivo("VIVO"))
        self.assertFalse(aplica_unicidade_ip_wan_vivo("CLARO"))

    def test_wan_vivo_mesmo_formulario(self):
        from core.utils.ip_unicidade import issues_unicidade_wan_vivo

        issues = issues_unicidade_wan_vivo(
            [
                {"field": "wan_1", "ip": "187.1.1.1", "operadora": "VIVO"},
                {"field": "wan_2", "ip": "187.1.1.1", "operadora": "VIVO"},
            ]
        )
        fields = {i["field"] for i in issues}
        self.assertEqual(fields, {"wan_1", "wan_2"})
        self.assertTrue(all("já está em uso" in i["message"] for i in issues))

    def test_wan_claro_nao_unica(self):
        from core.utils.ip_unicidade import issues_unicidade_wan_vivo

        issues = issues_unicidade_wan_vivo(
            [
                {"field": "wan_1", "ip": "187.1.1.1", "operadora": "CLARO"},
                {"field": "wan_2", "ip": "187.1.1.1", "operadora": "VTAL"},
            ]
        )
        self.assertEqual(issues, [])

    def test_wan_vivo_global_finder(self):
        from core.utils.ip_unicidade import TIPO_LINK_WAN, issues_unicidade_wan_vivo

        called = {}

        def finder(tipo, ip, *, id_cliente=None, exclude_id_unidade=None, exclude_id_link=None):
            called["tipo"] = tipo
            called["id_cliente"] = id_cliente
            called["exclude_id_link"] = exclude_id_link
            return [{"ip_address": ip, "nome_unidade": "Outro Cliente"}]

        issues = issues_unicidade_wan_vivo(
            [
                {
                    "field": "wan_1",
                    "ip": "187.1.1.1",
                    "operadora": "VIVO",
                    "id_link": 99,
                }
            ],
            finder=finder,
        )
        self.assertEqual(called["tipo"], TIPO_LINK_WAN)
        self.assertIsNone(called["id_cliente"])
        self.assertEqual(called["exclude_id_link"], 99)
        self.assertEqual(len(issues), 1)
        self.assertNotIn("Outro Cliente", issues[0]["message"])


if __name__ == "__main__":
    unittest.main()
