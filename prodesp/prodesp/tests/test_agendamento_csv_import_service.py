"""Testes — importação em lote CSV agendamento PRODESP."""
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from prodesp.prodesp.agendamento_csv_import_service import (
    _carregar_ultima_data_concluido_por_unidade,
    processar_importacao_agendamento_csv,
)


def _norm_hora(val):
    from datetime import datetime

    s = str(val or "").strip()
    if not s:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).strftime("%H:%M:%S")
        except ValueError:
            continue
    return None


class TestAgendamentoCsvImportService(unittest.TestCase):
    def test_carregar_concluido_em_lote(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {"id_unidades_atendimentos": 10, "data_concluido": date(2026, 7, 7)},
            {"id_unidades_atendimentos": 20, "data_concluido": date(2026, 6, 1)},
        ]
        out = _carregar_ultima_data_concluido_por_unidade(cursor, [10, 20])
        self.assertEqual(out[10], date(2026, 7, 7))
        self.assertEqual(out[20], date(2026, 6, 1))
        self.assertIn("GROUP BY", cursor.execute.call_args[0][0])

    @patch(
        "prodesp.prodesp.agendamento_csv_import_service._carregar_unidades_por_vgr"
    )
    @patch(
        "prodesp.prodesp.agendamento_csv_import_service._carregar_ultima_data_concluido_por_unidade"
    )
    @patch("prodesp.prodesp.agendamento_csv_import_service.registrar_logs_lote")
    def test_processamento_aplica_update_unico(
        self, mock_logs, mock_concluido, mock_unidades
    ):
        mock_unidades.return_value = {
            "100": {
                "id_unidades": 1,
                "id_vgr_unidades": "100",
                "data_agendamento_unidades": None,
                "hora_agendamento_unidades": None,
                "contratada_planejada_unidades": None,
                "field_planejada_unidades": None,
                "contato_field_planejada_unidades": None,
            }
        }
        mock_concluido.return_value = {}

        conn = MagicMock()
        cursor = MagicMock()

        body = [
            {
                "id_vgr": "100",
                "data_agendamento": "2026-07-10",
                "hora_agendamento": "14:30",
                "contratada": "DELFIA",
            }
        ]
        result = processar_importacao_agendamento_csv(
            conn,
            cursor,
            body,
            date(2026, 7, 7),
            user_re="teste",
            user_nome="Teste",
            normalize_hora_fn=_norm_hora,
            horas_equivalent_fn=lambda a, b: str(a) == str(b),
            format_hora_input_fn=lambda v: str(v)[:5] if v else None,
            time_from_value_fn=lambda v: None,
            mensagem_bloqueio_concluido_fn=lambda d: f"concluido {d}",
        )

        self.assertEqual(result.updated_count, 1)
        self.assertEqual(len(result.sucessos), 1)
        update_sql = cursor.execute.call_args[0][0]
        self.assertIn("UPDATE unidades SET", update_sql)
        self.assertTrue(mock_logs.called)


if __name__ == "__main__":
    unittest.main()
