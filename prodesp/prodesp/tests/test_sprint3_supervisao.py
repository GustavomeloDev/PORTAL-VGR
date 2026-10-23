"""Testes Sprint 3 — Supervisão cache / poll."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class SupervisaoCacheTests(unittest.TestCase):
    def setUp(self):
        from login import supervisao_cache

        supervisao_cache.bust_all()

    def tearDown(self):
        from login import supervisao_cache

        supervisao_cache.bust_all()

    def test_hit_miss_ttl(self):
        from login import supervisao_cache

        with mock.patch.dict(os.environ, {"LOGIN_SUPERVISAO_CACHE_TTL_SEC": "30"}):
            key = supervisao_cache.make_key("resumo", projetos=["PRODESP"], di="2026-07-01")
            self.assertIsNone(supervisao_cache.get(key))
            supervisao_cache.set(key, {"kpi": {"total": 3}})
            hit = supervisao_cache.get(key)
            self.assertEqual(hit["kpi"]["total"], 3)

    def test_ttl_zero(self):
        from login import supervisao_cache

        with mock.patch.dict(os.environ, {"LOGIN_SUPERVISAO_CACHE_TTL_SEC": "0"}):
            key = supervisao_cache.make_key("a", x=1)
            supervisao_cache.set(key, {"ok": True})
            self.assertIsNone(supervisao_cache.get(key))


class ScopePreferParticipacaoTests(unittest.TestCase):
    def test_scope_uses_participacao_by_default(self):
        from login.models import AtendimentoGlobal

        with mock.patch.dict(os.environ, {"LOGIN_SUPERVISAO_SCOPE_GLOBAL": "false"}):
            sql, _ = AtendimentoGlobal._scope_atendimentos_supervisao(projetos=["PRODESP"])
            self.assertIn("vw_atendimentos_participacao_analista", sql)
            self.assertNotIn("vw_atendimentos_global", sql)

    def test_scope_global_flag(self):
        from login.models import AtendimentoGlobal

        with mock.patch.dict(os.environ, {"LOGIN_SUPERVISAO_SCOPE_GLOBAL": "1"}):
            sql, _ = AtendimentoGlobal._scope_atendimentos_supervisao(projetos=["PRODESP"])
            self.assertIn("vw_atendimentos_global", sql)


if __name__ == "__main__":
    unittest.main()
