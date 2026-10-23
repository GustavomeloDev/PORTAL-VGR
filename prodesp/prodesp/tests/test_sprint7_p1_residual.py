"""Testes residual P1-02 / P1-03 — cache dashboard + projeção SQL."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class DashboardSelectTests(unittest.TestCase):
    def test_no_star_and_has_whitelist(self):
        from prodesp.prodesp.dashboard_select import (
            ATENDIMENTO_DASHBOARD_COLS,
            sql_atendimento_cols,
        )

        sql = sql_atendimento_cols("a")
        self.assertNotIn("a.*", sql)
        self.assertIn("a.`id_atendimentos`", sql)
        self.assertIn("status_atendimentos", sql)
        self.assertNotIn("logs_atendimentos", ATENDIMENTO_DASHBOARD_COLS)

    def test_null_base_keys(self):
        from prodesp.prodesp.dashboard_select import (
            ATENDIMENTO_DASHBOARD_COLS,
            atendimento_null_base,
        )

        base = atendimento_null_base()
        self.assertEqual(set(base), set(ATENDIMENTO_DASHBOARD_COLS))

    def test_sql_select_atendimento_by_id_sem_logs_perm(self):
        from prodesp.prodesp.dashboard_select import (
            ATENDIMENTO_COLS_SEM_LOGS,
            ATENDIMENTO_TABLE_COLS,
            sql_select_atendimento_by_id,
        )

        sql = sql_select_atendimento_by_id(include_logs=False)
        self.assertNotIn("SELECT *", sql)
        self.assertNotIn("`logs_atendimentos`", sql)
        self.assertIn("`status_atendimentos`", sql)
        self.assertIn("WHERE `id_atendimentos` = %s", sql)
        self.assertNotIn("FOR UPDATE", sql)
        self.assertEqual(
            set(ATENDIMENTO_COLS_SEM_LOGS),
            set(ATENDIMENTO_TABLE_COLS) - {"logs_atendimentos"},
        )

    def test_sql_select_atendimento_for_update_com_logs(self):
        from prodesp.prodesp.dashboard_select import sql_select_atendimento_by_id

        sql = sql_select_atendimento_by_id(include_logs=True, for_update=True)
        self.assertIn("`logs_atendimentos`", sql)
        self.assertIn("FOR UPDATE", sql)


class DashboardCacheTemposTests(unittest.TestCase):
    def test_set_get_includes_tempos_blob(self):
        from prodesp.prodesp import dashboard_cache

        dashboard_cache.bust()
        with mock.patch.dict(os.environ, {"PRODESP_DASHBOARD_CACHE_TTL_SEC": "60"}):
            dashboard_cache.set(
                "2026-07-01",
                "2026-07-01",
                {
                    "atendimentos": [{"id_atendimentos": 1}],
                    "scheduled": {},
                    "motivos_fora_padrao": [],
                    "tempos_etapa": {"resumo_ciclo": {"n": 1}},
                },
            )
            hit = dashboard_cache.get("2026-07-01", "2026-07-01")
            self.assertIsNotNone(hit)
            self.assertEqual(hit["tempos_etapa"]["resumo_ciclo"]["n"], 1)
            self.assertTrue(hit["cache_meta"]["from_cache"])
        dashboard_cache.bust()

    def test_bust_invalidates(self):
        from prodesp.prodesp import dashboard_cache

        with mock.patch.dict(os.environ, {"PRODESP_DASHBOARD_CACHE_TTL_SEC": "60"}):
            dashboard_cache.set("2026-07-02", "2026-07-02", {"atendimentos": []})
            dashboard_cache.bust()
            self.assertIsNone(dashboard_cache.get("2026-07-02", "2026-07-02"))


class CacheBackendMemoryTests(unittest.TestCase):
    def test_memory_roundtrip(self):
        from prodesp.prodesp import cache_backend

        with mock.patch.dict(os.environ, {"PRODESP_REDIS_URL": ""}):
            cache_backend.cache_bust()
            cache_backend.cache_set("t", {"x": 1}, 30, "a")
            self.assertEqual(cache_backend.cache_get("t", "a"), {"x": 1})
            cache_backend.cache_bust()
            self.assertIsNone(cache_backend.cache_get("t", "a"))


if __name__ == "__main__":
    unittest.main()
