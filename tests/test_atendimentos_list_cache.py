"""Testes do cache da lista de atendimentos PRODESP.

Rodar:

    .venv_portal_pessoal\\Scripts\\python.exe -m pytest prodesp/prodesp/tests/test_atendimentos_list_cache.py -q
"""
from __future__ import annotations

import os
import time
import unittest
from unittest import mock

from prodesp.prodesp import atendimentos_list_cache


class TestAtendimentosListCache(unittest.TestCase):
    def setUp(self):
        atendimentos_list_cache.bust()

    def tearDown(self):
        atendimentos_list_cache.bust()

    def test_ttl_hit_and_bust(self):
        with mock.patch.dict(os.environ, {"PRODESP_ATENDIMENTOS_LIST_CACHE_TTL_SEC": "30"}):
            atendimentos_list_cache.set({"todos": [{"id": 1}]})
            hit = atendimentos_list_cache.get()
            self.assertIsNotNone(hit)
            self.assertEqual(hit["todos"][0]["id"], 1)
            atendimentos_list_cache.bust()
            self.assertIsNone(atendimentos_list_cache.get())

    def test_ttl_expiry(self):
        with mock.patch.dict(os.environ, {"PRODESP_ATENDIMENTOS_LIST_CACHE_TTL_SEC": "1"}):
            atendimentos_list_cache.set({"todos": []})
            time.sleep(1.05)
            self.assertIsNone(atendimentos_list_cache.get())

    def test_default_ttl_60(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRODESP_ATENDIMENTOS_LIST_CACHE_TTL_SEC", None)
            self.assertEqual(atendimentos_list_cache._ttl_sec(), 60)

    def test_processed_cache_per_user(self):
        with mock.patch.dict(os.environ, {"PRODESP_ATENDIMENTOS_LIST_CACHE_TTL_SEC": "30"}):
            atendimentos_list_cache.set({"todos": [{"id_atendimento": 1}]})
            atendimentos_list_cache.set_processed(
                "u1:0:IMPLANTAÇÃO:Ana",
                {"atendimentos": [{"id_atendimento": 1}], "resumo": {"total_geral": 0}},
            )
            hit = atendimentos_list_cache.get_processed("u1:0:IMPLANTAÇÃO:Ana")
            self.assertIsNotNone(hit)
            self.assertEqual(hit["atendimentos"][0]["id_atendimento"], 1)
            self.assertIsNone(atendimentos_list_cache.get_processed("u2:0:IMPLANTAÇÃO:Bob"))
            atendimentos_list_cache.bust()
            self.assertIsNone(atendimentos_list_cache.get_processed("u1:0:IMPLANTAÇÃO:Ana"))

    def test_processed_cleared_on_raw_refresh(self):
        with mock.patch.dict(os.environ, {"PRODESP_ATENDIMENTOS_LIST_CACHE_TTL_SEC": "30"}):
            atendimentos_list_cache.set({"todos": []})
            atendimentos_list_cache.set_processed("k", {"atendimentos": [], "resumo": {}})
            atendimentos_list_cache.set({"todos": [{"id_atendimento": 2}]})
            self.assertIsNone(atendimentos_list_cache.get_processed("k"))

    def test_resumo_cache(self):
        with mock.patch.dict(os.environ, {"PRODESP_ATENDIMENTOS_LIST_CACHE_TTL_SEC": "30"}):
            atendimentos_list_cache.set_resumo({"total_geral": 10, "agendados": 2})
            hit = atendimentos_list_cache.get_resumo()
            self.assertEqual(hit["total_geral"], 10)
            atendimentos_list_cache.bust()
            self.assertIsNone(atendimentos_list_cache.get_resumo())


if __name__ == "__main__":
    unittest.main()
