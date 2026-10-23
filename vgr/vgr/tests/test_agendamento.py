"""Testes — validators/catálogo de agendamento VGR."""

from __future__ import annotations

import unittest

from vgr.vgr.operacao.catalogo_agendamento import (
    STATUS_AGENDADO,
    SUGESTAO_POR_STATUS_ATENDIMENTO,
)
from vgr.vgr.operacao.validators_agendamento import parse_agendamento_payload


class TestAgendamentoValidators(unittest.TestCase):
    def test_unidade_obrigatoria(self):
        with self.assertRaises(ValueError):
            parse_agendamento_payload({"status_agendamento": "Agendado"})

    def test_payload_ok(self):
        d = parse_agendamento_payload(
            {
                "id_unidade": 3,
                "status_agendamento": "Pendente envio a logística",
                "tipo": "Prateleira",
                "data_agendamento": "2026-08-20",
                "hora_agendamento": "14:30",
                "analista_livre": 1,
                "analista_destino": "alguem",
                "q_lote": 1,
                "id_fields": [1, 2, 2],
            }
        )
        self.assertEqual(d["tipo"], "Prateleira")
        self.assertIsNone(d["analista_destino"])
        self.assertEqual(d["q_lote"], 1)
        self.assertEqual(d["id_fields"], [1, 2])

    def test_status_invalido(self):
        with self.assertRaises(ValueError):
            parse_agendamento_payload(
                {"id_unidade": 1, "status_agendamento": "Status Fake"}
            )

    def test_sugestao_p11(self):
        self.assertEqual(
            SUGESTAO_POR_STATUS_ATENDIMENTO["Quebra"], "Improdutiva"
        )
        self.assertEqual(STATUS_AGENDADO, "Agendado")


if __name__ == "__main__":
    unittest.main()
