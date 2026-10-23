"""Flash com escopo login deve aparecer em pos_login (sem precisar de logout)."""

from __future__ import annotations

import unittest

from flask import Flask

from core.portal_flash import portal_flash, portal_flashed_messages


class TestPortalFlashPosLogin(unittest.TestCase):
    def test_acesso_negado_aparece_no_pos_login(self):
        app = Flask(__name__)
        app.secret_key = "test-flash"
        with app.test_request_context("/pos_login"):
            portal_flash("Acesso negado ao módulo DMA.", "warning", scope="login")
            shown = portal_flashed_messages(
                view_scope=None, endpoint="login.pos_login"
            )
            self.assertEqual(
                shown, [("warning", "Acesso negado ao módulo DMA.")]
            )

    def test_escopo_modulo_nao_aparece_no_pos_login(self):
        app = Flask(__name__)
        app.secret_key = "test-flash"
        with app.test_request_context("/pos_login"):
            portal_flash("Erro DMA.", "danger", scope="dma")
            shown = portal_flashed_messages(
                view_scope=None, endpoint="login.pos_login"
            )
            self.assertEqual(shown, [])


if __name__ == "__main__":
    unittest.main()
