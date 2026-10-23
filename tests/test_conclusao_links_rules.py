"""Testes do cruzamento de links × coleta FGT na conclusão."""
from __future__ import annotations

import unittest

from prodesp.prodesp.conclusao_links_rules import (
    infer_peer_gateway,
    parse_description_link_meta,
    validate_conclusao_links,
)

_LOGS_SAMPLE = """
--- COLETA FGT AUTO INÍCIO ---
--- get sys interface physical ---
==[lan3]
		mode: static
		ip: 10.250.28.98 255.255.255.248
		status: up
==[wan]
		mode: static
		ip: 187.92.26.18 255.255.255.252
		status: up
--- show sys interface ---
    edit "wan"
        set ip 187.92.26.18 255.255.255.252
        set description "SAI-BL_INET1_2187678_100Mb"
        set alias "INET-1"
        set estimated-upstream-bandwidth 100000
        set estimated-downstream-bandwidth 100000
        set role wan
    next
    edit "lan3"
        set ip 10.250.28.98 255.255.255.248
        set description "SCM_MPLS1_1693458_10Mb"
        set alias "MPLS-1"
        set estimated-upstream-bandwidth 10000
        set estimated-downstream-bandwidth 10000
        set role wan
    next
--- COLETA FGT AUTO FIM ---
"""

_LINKS_OK = [
    {
        "tipo_links": "STATIC",
        "designador_links": "114293672113097",
        "operadora_links": "VIVO",
        "id_vgr_links": "2187678",
        "ip_wan_links": "187.92.26.18",
        "ip_gateway_links": "187.92.26.17",
        "ip_mascara_links": "255.255.255.252",
        "velocidade_links": "100",
    },
    {
        "tipo_links": "MPLS",
        "designador_links": "114290169345890",
        "operadora_links": "VIVO",
        "id_vgr_links": "1693458",
        "ip_wan_links": "10.250.28.98",
        "ip_gateway_links": "10.250.28.97",
        "ip_mascara_links": "255.255.255.248",
        "velocidade_links": "10",
    },
]


class TestConclusaoLinks(unittest.TestCase):
    def test_parse_description(self):
        meta = parse_description_link_meta("SAI-BL_INET1_2187678_100Mb")
        self.assertEqual(meta["id_vgr"], "2187678")
        self.assertEqual(meta["velocidade_mbps"], "100")
        self.assertEqual(meta["circuito"], "SAI-BL")

    def test_peer_gateway_30(self):
        self.assertEqual(
            infer_peer_gateway("187.92.26.18", "255.255.255.252"),
            "187.92.26.17",
        )

    def test_peer_gateway_29_vazio(self):
        self.assertEqual(
            infer_peer_gateway("10.250.28.98", "255.255.255.248"),
            "",
        )

    def test_sem_coleta_nao_bloqueia(self):
        errs = validate_conclusao_links(
            links=_LINKS_OK,
            logs_atendimentos="sem interface",
        )
        self.assertEqual(errs, [])

    def test_links_ok_com_coleta(self):
        errs = validate_conclusao_links(
            links=_LINKS_OK,
            logs_atendimentos=_LOGS_SAMPLE,
        )
        self.assertEqual(errs, [], msg=errs)

    def test_wan_divergente(self):
        links = [dict(_LINKS_OK[0])]
        links[0]["ip_wan_links"] = "187.92.26.19"
        errs = validate_conclusao_links(links=links, logs_atendimentos=_LOGS_SAMPLE)
        self.assertTrue(any("IP WAN" in e for e in errs), errs)

    def test_gateway_divergente_static(self):
        links = [dict(_LINKS_OK[0])]
        links[0]["ip_gateway_links"] = "187.92.26.16"
        errs = validate_conclusao_links(links=links, logs_atendimentos=_LOGS_SAMPLE)
        self.assertTrue(any("Gateway" in e for e in errs), errs)

    def test_id_vgr_divergente(self):
        links = [dict(_LINKS_OK[0])]
        links[0]["id_vgr_links"] = "9999999"
        errs = validate_conclusao_links(links=links, logs_atendimentos=_LOGS_SAMPLE)
        self.assertTrue(any("ID VGR" in e for e in errs), errs)

    def test_velocidade_divergente(self):
        links = [dict(_LINKS_OK[1])]
        links[0]["velocidade_links"] = "50"
        errs = validate_conclusao_links(links=links, logs_atendimentos=_LOGS_SAMPLE)
        self.assertTrue(any("Velocidade" in e for e in errs), errs)

    def test_mpls_gateway_via_arp(self):
        logs = (
            _LOGS_SAMPLE.replace(
                "--- COLETA FGT AUTO FIM ---",
                "--- get sys arp ---\n"
                "10.250.28.97 0 00:11:22:33:44:55 lan3\n"
                "--- COLETA FGT AUTO FIM ---",
            )
        )
        links = [dict(_LINKS_OK[1])]
        links[0]["ip_gateway_links"] = "10.250.28.96"
        errs = validate_conclusao_links(links=links, logs_atendimentos=logs)
        self.assertTrue(any("Gateway" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
