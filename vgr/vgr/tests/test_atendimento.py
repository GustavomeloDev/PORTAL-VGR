"""Testes — validators e catálogo de atendimento VGR."""

from __future__ import annotations

import unittest

from vgr.vgr.operacao.catalogo_atendimento import (
    STATUS_FINAIS,
    is_status_final,
    is_substatus_gestao,
)
from vgr.vgr.operacao.validators_atendimento import parse_atendimento_payload


class TestAtendimentoValidators(unittest.TestCase):
    def test_unidade_obrigatoria(self):
        with self.assertRaises(ValueError):
            parse_atendimento_payload({"status_atendimento": "Em Atendimento"})

    def test_walk_in_ok(self):
        d = parse_atendimento_payload(
            {
                "id_unidade": 5,
                "id_agendamento": "",
                "status_atendimento": "Em Atendimento",
                "substatus_atendimento": "Aguarda Gestão",
            }
        )
        self.assertIsNone(d["id_agendamento"])
        self.assertEqual(d["status_atendimento"], "Em Atendimento")

    def test_status_invalido(self):
        with self.assertRaises(ValueError):
            parse_atendimento_payload(
                {"id_unidade": 1, "status_atendimento": "Inventado"}
            )

    def test_final(self):
        self.assertTrue(is_status_final("Quebra"))
        self.assertFalse(is_status_final("Em Atendimento"))
        self.assertIn("Concluído", STATUS_FINAIS)

    def test_gestao(self):
        self.assertTrue(is_substatus_gestao("Aguarda Gestão"))
        self.assertTrue(is_substatus_gestao("Triagem"))
        self.assertFalse(is_substatus_gestao("Em Configuração Remota"))

    def test_parse_observacoes_log(self):
        from vgr.vgr.operacao.repo_atendimento import parse_observacoes_log

        rows = parse_observacoes_log(
            "[2026-04-12 10:00 | Ana] Field a caminho\ntexto solto"
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["quem"], "Ana")
        self.assertEqual(rows[0]["texto"], "Field a caminho")
        self.assertEqual(rows[1]["texto"], "texto solto")


if __name__ == "__main__":
    unittest.main()
