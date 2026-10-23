"""Testes Sprint 2 — cache User / projetos / permissões."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class UserCacheModuleTests(unittest.TestCase):
    def setUp(self):
        from login import user_cache

        user_cache.bust_all_users()
        user_cache.bust_projetos_catalogo()

    def tearDown(self):
        from login import user_cache

        user_cache.bust_all_users()
        user_cache.bust_projetos_catalogo()

    def test_user_payload_hit_and_bust(self):
        from login import user_cache

        with mock.patch.dict(
            os.environ,
            {"LOGIN_USER_CACHE": "true", "LOGIN_USER_CACHE_TTL_SEC": "60"},
        ):
            self.assertIsNone(user_cache.get_user_payload(42))
            user_cache.set_user_payload(42, {"id_user": 42, "nome_user": "Ana"}, ["IMPLANTAÇÃO"])
            hit = user_cache.get_user_payload(42)
            self.assertIsNotNone(hit)
            row, extras = hit
            self.assertEqual(row["nome_user"], "Ana")
            self.assertEqual(extras, ["IMPLANTAÇÃO"])
            user_cache.bust_user(42)
            self.assertIsNone(user_cache.get_user_payload(42))

    def test_user_cache_disabled(self):
        from login import user_cache

        with mock.patch.dict(os.environ, {"LOGIN_USER_CACHE": "0"}):
            user_cache.set_user_payload(1, {"id_user": 1}, [])
            self.assertIsNone(user_cache.get_user_payload(1))

    def test_projetos_catalogo_and_permitidos(self):
        from login import user_cache

        with mock.patch.dict(os.environ, {"LOGIN_PROJETOS_CACHE_TTL_SEC": "300"}):
            user_cache.set_projetos_catalogo(True, [{"id_projeto": 1, "nome_projeto": "PRODESP"}])
            rows = user_cache.get_projetos_catalogo(True)
            self.assertEqual(len(rows), 1)
            user_cache.set_projetos_permitidos(7, False, [{"id_projeto": 1}])
            self.assertEqual(len(user_cache.get_projetos_permitidos(7, False)), 1)
            user_cache.bust_projetos_catalogo()
            self.assertIsNone(user_cache.get_projetos_catalogo(True))
            self.assertIsNone(user_cache.get_projetos_permitidos(7, False))

    def test_memo_permitidos_sem_request_nao_segura_lista(self):
        from login import user_cache

        self.assertIsNone(user_cache.memo_projetos_permitidos(3, False))
        user_cache.set_memo_projetos_permitidos(3, False, [{"id_projeto": 16}])
        self.assertIsNone(user_cache.memo_projetos_permitidos(3, False))


if __name__ == "__main__":
    unittest.main()
