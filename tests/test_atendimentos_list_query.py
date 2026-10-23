"""Testes — atendimentos_list_query (P3).

Rodar:
    .venv_portal_pessoal\\Scripts\\python.exe -m pytest prodesp/prodesp/tests/test_atendimentos_list_query.py -q
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from prodesp.prodesp.atendimentos_list_query import (
    build_count_query,
    build_full_list_query,
    build_paginated_query,
    effective_scope,
    parse_card_filter,
    parse_col_search_values,
    parse_dt_request_args,
    resumo_from_substatus_rows,
    slim_list_row,
    sql_scope_where,
)


class TestAtendimentosListQuery(unittest.TestCase):
    def test_effective_scope_admin_default_completo(self):
        self.assertEqual(effective_scope(None, is_admin=True), "completo")
        self.assertEqual(effective_scope("", is_admin=True), "completo")

    def test_effective_scope_admin_explicit_fila(self):
        self.assertEqual(effective_scope("fila", is_admin=True), "fila")

    def test_effective_scope_non_admin_forces_fila(self):
        self.assertEqual(effective_scope("completo", is_admin=False), "fila")
        self.assertEqual(effective_scope(None, is_admin=False), "fila")

    def test_parse_col_search_values(self):
        self.assertEqual(parse_col_search_values("^Concluído$"), ["Concluído"])
        self.assertEqual(
            parse_col_search_values("^(Em Atendimento|Agendado)$"),
            ["Em Atendimento", "Agendado"],
        )
        self.assertEqual(parse_col_search_values("12345"), ["12345"])

    def test_sql_scope_fila_excludes_final_status(self):
        sql = sql_scope_where("fila")
        self.assertIn("Concluído", sql)
        self.assertIn("id_atendimento IS NULL", sql)
        self.assertEqual(sql_scope_where("completo"), "1=1")

    def test_parse_card_filter_whitelist(self):
        sql, params = parse_card_filter("mode:migrados")
        self.assertIn("Concluído", sql)
        self.assertEqual(params, [])
        sql2, params2 = parse_card_filter("status:Agendado")
        self.assertIn("status_atendimento", sql2)
        self.assertEqual(params2, ["Agendado"])
        sql3, _ = parse_card_filter("'; DROP TABLE--")
        self.assertEqual(sql3, "1=1")

    def test_parse_dt_request_args(self):
        args = parse_dt_request_args({
            "draw": "2",
            "start": "10",
            "length": "25",
            "order[0][column]": "4",
            "order[0][dir]": "asc",
            "search[value]": "vgr",
            "columns[0][search][value]": "123",
            "scope": "fila",
            "card_filter": "mode:agendados",
        })
        self.assertEqual(args["draw"], 2)
        self.assertEqual(args["start"], 10)
        self.assertEqual(args["length"], 25)
        self.assertEqual(args["order_col"], 4)
        self.assertEqual(args["global_search"], "vgr")
        self.assertEqual(args["col_searches"][0], "123")
        self.assertEqual(args["card_filter"], "mode:agendados")

    def test_build_queries_contain_lst(self):
        q, _ = build_full_list_query("fila")
        self.assertIn("lst AS", q)
        self.assertIn("Em Atendimento", q)
        self.assertIn("LIMIT", build_paginated_query("fila", start=0, length=10, order_col=4, order_dir="desc")[0])
        self.assertIn("records_total", build_count_query("fila")[0])

    def test_default_order_priority_operacional(self):
        args = parse_dt_request_args({"draw": "1"})
        self.assertEqual(args["order_col"], 16)
        self.assertEqual(args["order_dir"], "asc")
        sql, _ = build_paginated_query(
            "fila", start=0, length=10, order_col=16, order_dir="asc"
        )
        self.assertIn("Em Atendimento", sql)
        self.assertIn("Agendado", sql)

    def test_resumo_from_substatus_rows(self):
        resumo = resumo_from_substatus_rows(
            [{"substatus": "Triagem", "cnt": 3}, {"substatus": "Concluído", "cnt": 99}],
            agendados=5,
        )
        self.assertEqual(resumo["agendados"], 5)
        self.assertGreaterEqual(resumo["total_geral"], 3)

    def test_slim_list_row(self):
        row = {
            "id_vgr": "1",
            "horario_finalizacao": "12:00",
            "tempo_total_geral": 100,
            "id_unidade": 9,
        }
        slim_list_row(row)
        self.assertNotIn("horario_finalizacao", row)
        self.assertNotIn("tempo_total_geral", row)
        self.assertNotIn("id_unidade", row)
        self.assertEqual(row["id_vgr"], "1")

    def test_list_server_side_env(self):
        from prodesp.prodesp import atendimentos_list_query as mod

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRODESP_ATENDIMENTOS_LIST_SERVER_SIDE", None)
            self.assertFalse(mod.list_server_side_enabled())
        with mock.patch.dict(os.environ, {"PRODESP_ATENDIMENTOS_LIST_SERVER_SIDE": "1"}):
            self.assertTrue(mod.list_server_side_enabled())

    def test_list_delta_enabled_default_off(self):
        from prodesp.prodesp import atendimentos_list_query as mod

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRODESP_ATENDIMENTOS_LIST_DELTA", None)
            self.assertFalse(mod.list_delta_enabled())
        with mock.patch.dict(os.environ, {"PRODESP_ATENDIMENTOS_LIST_DELTA": "1"}):
            self.assertTrue(mod.list_delta_enabled())

    def test_row_in_scope(self):
        from prodesp.prodesp.atendimentos_list_query import row_in_scope

        self.assertTrue(row_in_scope({"status_atendimento": "Quebra"}, "completo"))
        self.assertFalse(row_in_scope({"status_atendimento": "Quebra"}, "fila"))
        self.assertTrue(row_in_scope({"status_atendimento": "Em Atendimento"}, "fila"))
        self.assertTrue(row_in_scope({"status_atendimento": ""}, "fila"))

    def test_build_rows_by_ids_query(self):
        from prodesp.prodesp.atendimentos_list_query import build_rows_by_ids_query

        sql, params = build_rows_by_ids_query([1, 2, 2, 0, "x"])
        self.assertIn("IN (%s, %s)", sql)
        self.assertEqual(params, [1, 2])
        with self.assertRaises(ValueError):
            build_rows_by_ids_query([])


if __name__ == "__main__":
    unittest.main()
