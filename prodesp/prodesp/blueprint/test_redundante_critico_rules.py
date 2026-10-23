"""Testes da regra Redundante Crítico (MPLS + VIVO) — flag + ip_wan único."""
import unittest

from prodesp.prodesp.blueprint.redundante_critico_rules import (
    REDUNDANTE_CRITICO_OFFSET,
    apply_redundante_critico_to_link,
    derive_base_from_stored,
    offset_ipv4,
    resolve_effective_ip_wan,
)


class TestRedundanteCriticoRules(unittest.TestCase):
    def test_offset_ipv4_plus_two(self):
        self.assertEqual(offset_ipv4("10.250.4.114", 2), "10.250.4.116")

    def test_offset_ipv4_minus_two(self):
        self.assertEqual(offset_ipv4("10.250.4.116", -2), "10.250.4.114")

    def test_derive_base_from_stored(self):
        self.assertEqual(derive_base_from_stored("10.250.4.114", False), "10.250.4.114")
        self.assertEqual(derive_base_from_stored("10.250.4.116", True), "10.250.4.114")

    def test_cenario_1_salvo_sem_opcao(self):
        result = apply_redundante_critico_to_link(
            {
                "tipo": "MPLS",
                "operadora": "VIVO",
                "ip_wan": "10.250.4.114",
                "ip_gateway": "10.250.4.113",
                "redundante_critico": False,
            }
        )
        self.assertEqual(result["ip_wan"], "10.250.4.114")
        self.assertEqual(result["redundante_critico_links"], 0)
        self.assertNotIn("ip_wan_base_links", result)

    def test_cenario_2_salvo_com_opcao_desde_inicio(self):
        result = apply_redundante_critico_to_link(
            {
                "tipo": "MPLS",
                "operadora": "VIVO",
                "ip_wan": "10.250.4.116",
                "ip_gateway": "10.250.4.113",
                "redundante_critico": True,
            }
        )
        self.assertEqual(result["ip_wan"], "10.250.4.116")
        self.assertEqual(result["redundante_critico_links"], 1)

    def test_cenario_3_marcado_posteriormente(self):
        existing = {
            "ip_wan_links": "10.250.4.114",
            "redundante_critico_links": 0,
        }
        result = apply_redundante_critico_to_link(
            {
                "tipo": "MPLS",
                "operadora": "VIVO",
                "ip_wan": "10.250.4.114",
                "redundante_critico": True,
            },
            existing=existing,
        )
        self.assertEqual(result["ip_wan"], "10.250.4.116")

    def test_cenario_4_desmarcado_depois(self):
        existing = {
            "ip_wan_links": "10.250.4.116",
            "redundante_critico_links": 1,
        }
        result = apply_redundante_critico_to_link(
            {
                "tipo": "MPLS",
                "operadora": "VIVO",
                "ip_wan": "10.250.4.116",
                "redundante_critico": False,
            },
            existing=existing,
        )
        self.assertEqual(result["ip_wan"], "10.250.4.114")
        self.assertEqual(result["redundante_critico_links"], 0)

    def test_nao_acumula_transformacao(self):
        existing = {
            "ip_wan_links": "10.250.4.116",
            "redundante_critico_links": 1,
        }
        result = apply_redundante_critico_to_link(
            {
                "tipo": "MPLS",
                "operadora": "VIVO",
                "ip_wan": "10.250.4.116",
                "redundante_critico": True,
            },
            existing=existing,
        )
        self.assertEqual(result["ip_wan"], "10.250.4.116")

    def test_edicao_wan_com_rc_ja_marcado_nao_soma_dois(self):
        """Bug atendimento: digitar .24 com RC salvo gravava .26."""
        existing = {
            "ip_wan_links": "10.159.20.20",
            "redundante_critico_links": 1,
        }
        result = apply_redundante_critico_to_link(
            {
                "tipo": "MPLS",
                "operadora": "VIVO",
                "ip_wan": "10.159.20.24",
                "redundante_critico": True,
            },
            existing=existing,
        )
        self.assertEqual(result["ip_wan"], "10.159.20.24")
        self.assertEqual(result["redundante_critico_links"], 1)

    def test_edicao_cola_base_planilha_com_rc_converte_uma_vez(self):
        """Com RC ativo, colar a base (= WAN−2) ainda converte para efetivo."""
        existing = {
            "ip_wan_links": "10.159.20.24",
            "redundante_critico_links": 1,
        }
        result = apply_redundante_critico_to_link(
            {
                "tipo": "MPLS",
                "operadora": "VIVO",
                "ip_wan": "10.159.20.22",
                "redundante_critico": True,
            },
            existing=existing,
        )
        self.assertEqual(result["ip_wan"], "10.159.20.24")

    def test_normalize_api_edicao_wan_com_rc(self):
        from prodesp.prodesp.blueprint.link_vivo_rules import normalize_link_api_payload

        existing = {
            "ip_wan_links": "10.159.20.20",
            "ip_gateway_links": "10.159.20.17",
            "redundante_critico_links": 1,
        }
        api = normalize_link_api_payload(
            {
                "tipo": "MPLS",
                "operadora": "VIVO",
                "ip_wan": "10.159.20.24",
                "ip_gateway": "10.159.20.17",
                "ip_mascara": "255.255.255.248",
                "redundante_critico": True,
            },
            existing=existing,
        )
        self.assertEqual(api["ip_wan"], "10.159.20.24")
        self.assertEqual(api["ip_gateway"], "10.159.20.21")  # WAN − 3
        self.assertEqual(api["redundante_critico_links"], 1)

    def test_toggle_via_resolve(self):
        self.assertEqual(
            resolve_effective_ip_wan("10.250.4.114", True, {"ip_wan_links": "10.250.4.114", "redundante_critico_links": 0}),
            "10.250.4.116",
        )
        self.assertEqual(
            resolve_effective_ip_wan("10.250.4.116", False, {"ip_wan_links": "10.250.4.116", "redundante_critico_links": 1}),
            "10.250.4.114",
        )

    def test_ignora_static_claro(self):
        payload = {
            "tipo": "STATIC",
            "operadora": "VIVO",
            "ip_wan": "10.1.1.2",
            "redundante_critico": True,
        }
        result = apply_redundante_critico_to_link(payload)
        self.assertEqual(result["ip_wan"], "10.1.1.2")
        self.assertNotIn("redundante_critico_links", result)

    def test_preserva_gateway_ao_ativar_flag(self):
        """Ao marcar RC, WAN += 2; gateway fica WAN−3 (= CPE original)."""
        existing = {
            "ip_wan_links": "10.250.83.34",
            "ip_gateway_links": "10.250.83.33",
            "redundante_critico_links": 0,
        }
        result = apply_redundante_critico_to_link(
            {
                "tipo": "MPLS",
                "operadora": "VIVO",
                "ip_wan": "10.250.83.36",
                "ip_gateway": "10.250.83.35",
                "redundante_critico": True,
            },
            existing=existing,
        )
        self.assertEqual(result["ip_wan"], "10.250.83.36")
        from prodesp.prodesp.blueprint.link_vivo_rules import normalize_vivo_link_fields

        normalized = normalize_vivo_link_fields(
            {
                "tipo_links": "MPLS",
                "operadora_links": "VIVO",
                "ip_wan_links": result["ip_wan"],
                "ip_gateway_links": result.get("ip_gateway") or "10.250.83.35",
                "redundante_critico_links": 1,
            }
        )
        self.assertEqual(normalized["ip_gateway_links"], "10.250.83.33")

    def test_normalize_vivo_gateway_menos_3_com_flag(self):
        from prodesp.prodesp.blueprint.link_vivo_rules import normalize_vivo_link_fields

        data = normalize_vivo_link_fields(
            {
                "tipo_links": "MPLS",
                "operadora_links": "VIVO",
                "ip_wan_links": "10.131.25.36",
                "ip_gateway_links": "",
                "redundante_critico_links": 1,
            }
        )
        self.assertEqual(data["ip_gateway_links"], "10.131.25.33")
        self.assertEqual(data["ip_mascara_links"], "255.255.255.248")

    def test_normalize_vivo_wan_from_gateway_com_flag(self):
        from prodesp.prodesp.blueprint.link_vivo_rules import normalize_vivo_link_fields

        data = normalize_vivo_link_fields(
            {
                "tipo_links": "MPLS",
                "operadora_links": "VIVO",
                "ip_wan_links": "",
                "ip_gateway_links": "10.131.25.36",
                "redundante_critico_links": 1,
            }
        )
        self.assertEqual(data["ip_wan_links"], "10.131.25.39")
        self.assertEqual(data["ip_gateway_links"], "10.131.25.36")

    def test_normalize_vivo_wan_from_gateway_sem_flag(self):
        from prodesp.prodesp.blueprint.link_vivo_rules import normalize_vivo_link_fields

        data = normalize_vivo_link_fields(
            {
                "tipo_links": "MPLS",
                "operadora_links": "VIVO",
                "ip_wan_links": "",
                "ip_gateway_links": "10.131.25.36",
                "redundante_critico_links": 0,
            }
        )
        self.assertEqual(data["ip_wan_links"], "10.131.25.37")
        self.assertEqual(data["ip_gateway_links"], "10.131.25.36")

    def test_offset_constant(self):
        self.assertEqual(REDUNDANTE_CRITICO_OFFSET, 2)


if __name__ == "__main__":
    unittest.main()
