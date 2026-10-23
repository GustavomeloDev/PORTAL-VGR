"""Testes da fachada de enriquecimento (sem APIs externas)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.utils.endereco_enriquecimento import enriquecer_endereco_portal


class TestEnriquecerPortal(unittest.TestCase):
    @patch("core.utils.endereco_enriquecimento.enriquecer_endereco_unidade")
    def test_mapeia_cidade_uf(self, mock_fn):
        mock_fn.return_value = {
            "success": True,
            "updates": {"municipio": "Belo Horizonte", "estado": "MG"},
            "warnings": [],
            "message": "ok",
        }
        result = enriquecer_endereco_portal(
            {"endereco": "Rua Curitiba 1001", "cidade": "BH", "uf": "MG"}
        )
        sent = mock_fn.call_args[0][0]
        self.assertEqual(sent["municipio"], "BH")
        self.assertEqual(sent["estado"], "MG")
        self.assertEqual(result["updates"]["cidade"], "Belo Horizonte")
        self.assertEqual(result["updates"]["uf"], "MG")

    @patch("core.utils.endereco_enriquecimento.enriquecer_endereco_unidade")
    def test_trunca_entrada(self, mock_fn):
        mock_fn.return_value = {"success": True, "updates": {}, "message": "ok"}
        enriquecer_endereco_portal({"endereco": "A" * 800})
        sent = mock_fn.call_args[0][0]
        self.assertEqual(len(sent["endereco"]), 500)


class TestMotorCore(unittest.TestCase):
    def test_engine_no_core(self):
        from core.utils import endereco_enriquecimento_engine as motor

        self.assertTrue(callable(motor.enriquecer_endereco_unidade))
        src = motor.__file__
        self.assertIn("core", src.replace("\\", "/"))
        with open(src, encoding="utf-8") as fh:
            body = fh.read()
        self.assertNotIn("prodesp.credentials", body)
        self.assertNotIn('get_logger("PRODESP")', body)
