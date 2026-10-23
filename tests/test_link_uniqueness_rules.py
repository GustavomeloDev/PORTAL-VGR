"""Testes das regras de unicidade PRODESP (mensagens e dedup de lote)."""
import unittest
from unittest.mock import MagicMock

from prodesp.prodesp.link_uniqueness_rules import (
    find_batch_link_uniqueness_errors,
    find_link_uniqueness_errors,
    find_loopback_uniqueness_errors,
    format_link_collision_message,
    format_loopback_collision_message,
)


class TestLinkUniquenessMessages(unittest.TestCase):
    def test_format_other_unit(self):
        msg = format_link_collision_message(
            "IP WAN",
            "10.1.1.1",
            {
                "id_vgr_unidades": "2218794",
                "tipo_links": "MPLS",
                "designador_links": "LP_SCM",
                "operadora_links": "VIVO",
            },
            found_as="IP WAN",
        )
        self.assertIn("IP WAN «10.1.1.1»", msg)
        self.assertIn("2218794", msg)
        self.assertIn("LP_SCM", msg)
        self.assertIn("já usado como IP WAN", msg)

    def test_format_same_unit(self):
        msg = format_link_collision_message(
            "Designador",
            "LP_SCM",
            {
                "id_vgr_unidades": "99",
                "tipo_links": "STATIC",
                "designador_links": "LP_SCM",
                "operadora_links": "VIVO",
            },
            same_unit=True,
        )
        self.assertIn("mesma unidade", msg)
        self.assertIn("qual link", msg)

    def test_wan_equals_gateway(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        errors = find_link_uniqueness_errors(
            cursor,
            {
                "tipo": "MPLS",
                "designador": "LP_A",
                "operadora": "VIVO",
                "ip_wan": "10.1.1.1",
                "ip_gateway": "10.1.1.1",
            },
        )
        self.assertTrue(any("não podem ser iguais" in e for e in errors))

    def test_batch_internal_duplicate_wan(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        errors = find_batch_link_uniqueness_errors(
            cursor,
            [
                {
                    "id_link": 1,
                    "tipo_links": "MPLS",
                    "designador_links": "A",
                    "operadora_links": "VIVO",
                    "ip_wan_links": "10.1.1.2",
                    "ip_gateway_links": "10.1.1.1",
                },
                {
                    "id_link": 2,
                    "tipo_links": "STATIC",
                    "designador_links": "B",
                    "operadora_links": "CLARO",
                    "ip_wan_links": "10.1.1.2",
                    "ip_gateway_links": "10.1.1.3",
                },
            ],
        )
        self.assertTrue(any("IP WAN «10.1.1.2» repetido" in e for e in errors))
        # Não deve ecoar colisão DB do outro link do mesmo lote
        self.assertFalse(any("já está cadastrado" in e for e in errors))

    def test_batch_excludes_all_ids_from_db_lookup(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        find_batch_link_uniqueness_errors(
            cursor,
            [
                {
                    "id_link": 10,
                    "tipo_links": "MPLS",
                    "designador_links": "A",
                    "operadora_links": "VIVO",
                    "ip_wan_links": "10.1.1.2",
                    "ip_gateway_links": "10.1.1.1",
                },
                {
                    "id_link": 20,
                    "tipo_links": "STATIC",
                    "designador_links": "B",
                    "operadora_links": "VIVO",
                    "ip_wan_links": "10.1.1.4",
                    "ip_gateway_links": "10.1.1.3",
                },
            ],
        )
        # Cada consulta de IP deve excluir ambos os IDs do lote
        for call in cursor.execute.call_args_list:
            sql = call[0][0]
            params = call[0][1]
            if "ip_wan_links" in sql and "NOT IN" in sql:
                self.assertIn(10, params)
                self.assertIn(20, params)

    def test_batch_resolves_missing_id_as_update_same_unit(self):
        """Sem id_link no payload, resolve pelo designador na unidade e não auto-bloqueia."""
        cursor = MagicMock()
        # 1) resolve STATIC → id 55; 2+) lookups de colisão → None
        cursor.fetchone.side_effect = [
            {"id_link": 55, "tipo_links": ""},
            None,
            None,
            None,
            None,
            None,
        ]

        errors = find_batch_link_uniqueness_errors(
            cursor,
            [
                {
                    "tipo_links": "STATIC",
                    "designador_links": "115693279117195",
                    "operadora_links": "VIVO",
                    "id_vgr_links": "2160994",
                    "ip_wan_links": "186.238.81.67",
                    "ip_gateway_links": "186.238.81.66",
                }
            ],
            id_unidade=99,
        )
        self.assertFalse(any("já está cadastrado" in e for e in errors))
        resolve_sql = cursor.execute.call_args_list[0][0][0]
        self.assertIn("id_unidades_links", resolve_sql)
        # Exclude 55 nas consultas de colisão
        for call in cursor.execute.call_args_list[1:]:
            sql = call[0][0]
            params = call[0][1]
            if "NOT IN" in sql:
                self.assertIn(55, params)

    def test_batch_still_blocks_true_duplicate_after_resolve(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {"id_link": 55, "tipo_links": ""},  # resolve próprio registro
            None,  # wan
            None,  # gw
            {  # designador em OUTRO id da mesma unidade
                "id_link": 77,
                "id_unidades_links": 99,
                "tipo_links": "",
                "designador_links": "DUP",
                "operadora_links": "VIVO",
                "id_vgr_unidades": "2184589",
            },
            None,  # id_vgr
        ]
        errors = find_batch_link_uniqueness_errors(
            cursor,
            [
                {
                    "tipo_links": "STATIC",
                    "designador_links": "DUP",
                    "operadora_links": "VIVO",
                    "id_vgr_links": "999",
                    "ip_wan_links": "10.0.0.2",
                    "ip_gateway_links": "10.0.0.1",
                }
            ],
            id_unidade=99,
        )
        self.assertTrue(any("Designador" in e and "já está cadastrado" in e for e in errors))

    def test_loopback_same_unit_collision(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        errors = find_loopback_uniqueness_errors(
            cursor,
            {
                "loopback_vivo_unidades": "10.254.1.1",
                "loopback_cliente_unidades": "10.254.1.1",
                "loopback_on_bgp_unidades": "10.253.1.1",
            },
            exclude_unidade_id=1,
        )
        self.assertTrue(any("mesma unidade" in e for e in errors))

    def test_loopback_other_unit_message(self):
        msg = format_loopback_collision_message(
            "Loopback Vivo",
            "10.254.1.1",
            {"id_vgr_unidades": "123"},
            found_as="Loopback Cliente",
        )
        self.assertIn("10.254.1.1", msg)
        self.assertIn("123", msg)
        self.assertIn("Loopback Cliente", msg)


if __name__ == "__main__":
    unittest.main()
