"""Testes Sprint 1 — timing, cache notif, DRY CTE."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from flask import Flask, jsonify


class TimingDecoratorTests(unittest.TestCase):
    def test_injects_server_ms(self):
        from core.utils.timing import with_server_ms

        app = Flask(__name__)

        @app.get("/x")
        @with_server_ms
        def x():
            return jsonify({"ok": True})

        client = app.test_client()
        with mock.patch.dict(os.environ, {"PORTAL_TIMING": "true"}):
            rv = client.get("/x")
        self.assertEqual(rv.status_code, 200)
        data = rv.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("server_ms", data)
        self.assertIsInstance(data["server_ms"], (int, float))
        self.assertIn("X-Portal-Server-Ms", rv.headers)

    def test_timing_off(self):
        from core.utils.timing import with_server_ms

        app = Flask(__name__)

        @app.get("/y")
        @with_server_ms
        def y():
            return jsonify({"ok": True})

        client = app.test_client()
        with mock.patch.dict(os.environ, {"PORTAL_TIMING": "0"}):
            rv = client.get("/y")
        data = rv.get_json()
        self.assertNotIn("server_ms", data)


class NotifCountCacheTests(unittest.TestCase):
    def setUp(self):
        from login import notif_count_cache

        notif_count_cache.bust_all()

    def tearDown(self):
        from login import notif_count_cache

        notif_count_cache.bust_all()

    def test_hit_and_bust(self):
        from login import notif_count_cache

        with mock.patch.dict(os.environ, {"LOGIN_NOTIF_COUNT_CACHE_TTL_SEC": "60"}):
            self.assertIsNone(notif_count_cache.get(1, "IMPLANTAÇÃO"))
            notif_count_cache.set(1, "IMPLANTAÇÃO", 2, 3)
            hit = notif_count_cache.get(1, "IMPLANTAÇÃO")
            self.assertEqual(hit, (2, 3))
            notif_count_cache.bust_user(1)
            self.assertIsNone(notif_count_cache.get(1, "IMPLANTAÇÃO"))

    def test_ttl_zero_disables(self):
        from login import notif_count_cache

        with mock.patch.dict(os.environ, {"LOGIN_NOTIF_COUNT_CACHE_TTL_SEC": "0"}):
            notif_count_cache.set(9, None, 1, 1)
            self.assertIsNone(notif_count_cache.get(9, None))


class CteDryTests(unittest.TestCase):
    def test_app_delegates_to_list_query(self):
        from prodesp.app import _prodesp_sql_cte_ultimo_substatus_log_agg
        from prodesp.prodesp.atendimentos_list_query import sql_cte_ultimo_substatus_log_agg

        self.assertEqual(
            _prodesp_sql_cte_ultimo_substatus_log_agg().strip(),
            sql_cte_ultimo_substatus_log_agg().strip(),
        )
        self.assertIn("ult_sub_log_agg AS", _prodesp_sql_cte_ultimo_substatus_log_agg())


class DbHealthScoreTests(unittest.TestCase):
    def test_score_bounds(self):
        from login.db_health import _health_score

        s = _health_score(
            {
                "Threads_connected": 10,
                "max_connections": 151,
                "Innodb_buffer_pool_read_requests": 10000,
                "Innodb_buffer_pool_reads": 1,
            },
            [{"avg_s": 0.1}],
        )
        self.assertGreaterEqual(s, 0)
        self.assertLessEqual(s, 100)
        self.assertGreaterEqual(s, 80)


if __name__ == "__main__":
    unittest.main()
