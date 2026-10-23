"""Testes do cache em memória do dashboard PRODESP.

Rodar:

    .venv_portal_pessoal\\Scripts\\python.exe -m pytest prodesp/prodesp/tests/test_dashboard_cache.py -q
"""
from __future__ import annotations

import os
import time
import unittest
from unittest import mock

from prodesp.prodesp import dashboard_cache


class TestDashboardCache(unittest.TestCase):
    def setUp(self):
        dashboard_cache.bust()

    def tearDown(self):
        dashboard_cache.bust()

    def test_ttl_miss_after_expiry(self):
        with mock.patch.dict(os.environ, {"PRODESP_DASHBOARD_CACHE_TTL_SEC": "1"}):
            dashboard_cache.set("2026-06-01", "2026-06-01", {"atendimentos": [1]})
            self.assertIsNotNone(dashboard_cache.get("2026-06-01", "2026-06-01"))
            time.sleep(1.05)
            self.assertIsNone(dashboard_cache.get("2026-06-01", "2026-06-01"))

    def test_bust_clears_all_keys(self):
        with mock.patch.dict(os.environ, {"PRODESP_DASHBOARD_CACHE_TTL_SEC": "60"}):
            dashboard_cache.set("2026-06-01", "2026-06-01", {"atendimentos": []})
            dashboard_cache.set("2026-06-02", "2026-06-02", {"atendimentos": []})
            dashboard_cache.bust()
            self.assertIsNone(dashboard_cache.get("2026-06-01", "2026-06-01"))
            self.assertIsNone(dashboard_cache.get("2026-06-02", "2026-06-02"))

    def test_ttl_zero_disables_cache(self):
        with mock.patch.dict(os.environ, {"PRODESP_DASHBOARD_CACHE_TTL_SEC": "0"}):
            dashboard_cache.set("2026-06-01", "2026-06-01", {"atendimentos": [1]})
            self.assertIsNone(dashboard_cache.get("2026-06-01", "2026-06-01"))

    def test_cache_meta_on_hit(self):
        with mock.patch.dict(os.environ, {"PRODESP_DASHBOARD_CACHE_TTL_SEC": "60"}):
            dashboard_cache.set(
                "2026-06-01",
                "2026-06-09",
                {"atendimentos": [], "scheduled": {}, "motivos_fora_padrao": []},
            )
            hit = dashboard_cache.get("2026-06-01", "2026-06-09")
            self.assertIsNotNone(hit)
            meta = hit.get("cache_meta") or {}
            self.assertTrue(meta.get("from_cache"))
            self.assertEqual(meta.get("ttl_sec"), 60)


if __name__ == "__main__":
    unittest.main()
