"""P3 — entity_select unidades/equipamentos/links (sem DB)."""

from __future__ import annotations

import unittest


class EntitySelectTests(unittest.TestCase):
    def test_unidades_sem_star(self):
        from prodesp.prodesp.entity_select import (
            UNIDADE_TABLE_COLS,
            sql_select_unidades_by_id,
            sql_select_unidades_by_id_vgr,
        )

        self.assertIn("id_unidades", UNIDADE_TABLE_COLS)
        self.assertIn("mv_mask_totem_unidades", UNIDADE_TABLE_COLS)
        for sql in (sql_select_unidades_by_id(), sql_select_unidades_by_id_vgr()):
            self.assertNotIn("SELECT *", sql)
            self.assertIn("`id_unidades`", sql)

    def test_equipamentos_ativos_limit(self):
        from prodesp.prodesp.entity_select import sql_select_equipamentos_by_unidade

        sql = sql_select_equipamentos_by_unidade(ativos_only=True, limit_one=True)
        self.assertNotIn("SELECT *", sql)
        self.assertIn("deleted_equipamentos` = 0", sql)
        self.assertIn("LIMIT 1", sql)

    def test_links(self):
        from prodesp.prodesp.entity_select import (
            LINK_TABLE_COLS,
            sql_select_link_by_id_and_unidade,
            sql_select_links_by_unidade,
        )

        self.assertIn("pppoe_pass_links", LINK_TABLE_COLS)
        self.assertIn("redundante_critico_links", LINK_TABLE_COLS)
        sql = sql_select_links_by_unidade(order=True)
        self.assertIn("ORDER BY", sql)
        self.assertNotIn("SELECT *", sql_select_link_by_id_and_unidade())


if __name__ == "__main__":
    unittest.main()
