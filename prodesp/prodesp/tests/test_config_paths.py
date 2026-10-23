"""Caminhos principal (Telefonica\\) + fallback (OneDrive - Telefonica\\)."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from prodesp.config_paths import (
    _default_path_candidates,
    list_prodesp_path_candidates,
    network_base_ready,
)


class ProdespConfigPathsTests(unittest.TestCase):
    def test_defaults_principal_e_fallback(self):
        with mock.patch("prodesp.config_paths._windows_user", return_value="caqdev"):
            cad_p, cad_f = _default_path_candidates("caderno_teste_rede_base")
            cert_p, cert_f = _default_path_candidates("certificados_rede_base")
        self.assertEqual(
            cad_p,
            os.path.join(
                r"C:\Users\caqdev",
                "Telefonica",
                "Projeto_Prodesp.TMBNL - Documentos",
                "Rollout - Prodesp",
                "Caderno de Testes",
            ),
        )
        self.assertEqual(
            cad_f,
            os.path.join(
                r"C:\Users\caqdev",
                "OneDrive - Telefonica",
                "Documentos - Projeto_Prodesp.TMBNL",
                "Rollout - Prodesp",
                "Caderno de Testes",
            ),
        )
        self.assertIn(os.path.join("Telefonica", "Projeto_Prodesp.TMBNL - Documentos"), cert_p)
        self.assertIn(
            os.path.join("OneDrive - Telefonica", "Documentos - Projeto_Prodesp.TMBNL"),
            cert_f,
        )

    def test_candidates_sem_ini_usam_codigo(self):
        with mock.patch("prodesp.config_paths._ini_get", return_value=""):
            with mock.patch("prodesp.config_paths._windows_user", return_value="caqdev"):
                cands = list_prodesp_path_candidates("caderno_teste_rede_base")
        self.assertGreaterEqual(len(cands), 2)
        self.assertIn("Telefonica", cands[0])
        self.assertNotIn("OneDrive - Telefonica", cands[0])
        self.assertIn("OneDrive - Telefonica", cands[1])

    def test_network_base_ready_tempdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(network_base_ready(tmp))
            self.assertTrue(network_base_ready(os.path.join(tmp, "sub", "pasta")))

    def test_network_base_ready_nao_inventa_raiz_telefonica(self):
        fake = os.path.join(r"C:\Users\naoexiste_xyz", "Telefonica", "Lib", "sub")
        self.assertFalse(network_base_ready(fake))


if __name__ == "__main__":
    unittest.main()
