"""Testes de relatorio_observacoes (download_report + e-mail gestão).

Rodar:

    .venv_portal_pessoal\\Scripts\\python.exe -m pytest prodesp/prodesp/gestao/test_relatorio_observacoes.py -q
"""
from __future__ import annotations

import unittest
from datetime import datetime
from unittest import mock

from prodesp.prodesp.gestao.relatorio_observacoes import (
    carregar_observacoes_map,
    carregar_substatus_historico_map,
    date_range_exclusive,
    format_linha_substatus_historico,
    observacoes_linha_relatorio,
)


class TestRelatorioObservacoes(unittest.TestCase):
    def test_date_range_exclusive(self):
        start, end_ex = date_range_exclusive("2026-06-01", "2026-06-11")
        self.assertEqual(start, "2026-06-01")
        self.assertEqual(end_ex, "2026-06-12")

    def test_carregar_observacoes_map_params(self):
        cursor = mock.MagicMock()
        cursor.fetchall.return_value = [
            {
                "id_observacoes": 1,
                "id_atendimentos_observacoes": 10,
                "id_unidades_observacoes": 1,
                "observacoes": "teste",
                "timestamp_observacoes": datetime(2026, 6, 11, 9, 0),
            }
        ]
        por_att, por_u = carregar_observacoes_map(
            cursor, "2026-06-11", "2026-06-12"
        )
        cursor.execute.assert_called_once()
        params = cursor.execute.call_args[0][1]
        self.assertEqual(params, ("2026-06-11", "2026-06-12"))
        self.assertIn(10, por_att)
        self.assertEqual(len(por_u), 0)
        self.assertEqual(por_att[10][0][1], "11/06/2026 09:00: teste")

    def test_format_linha_substatus(self):
        entrada = format_linha_substatus_historico(
            {
                "id_log_historico": 99,
                "valor_antigo_historico": "Aguarda Gestão",
                "valor_novo_historico": "Em Configuração Remota",
                "usuario_re_historico": "RE001",
                "usuario_nome_historico": "Maria Silva",
                "data_alteracao_historico": datetime(2026, 6, 11, 14, 30),
            }
        )
        self.assertEqual(entrada[1], "11/06/2026 14:30: [Substatus] «Em Configuração Remota»")

    def test_carregar_substatus_historico_map_vazio(self):
        cursor = mock.MagicMock()
        self.assertEqual(carregar_substatus_historico_map(cursor, []), {})
        cursor.execute.assert_not_called()

    def test_observacoes_linha_ordem_desc_e_substatus(self):
        row = {"id_atendimentos": 5, "id_unidades": 2}
        por_att = {
            5: [
                (datetime(2026, 6, 11, 9, 0), "11/06/2026 09:00: obs antiga", 1),
                (datetime(2026, 6, 11, 15, 0), "11/06/2026 15:00: obs recente", 2),
            ]
        }
        por_u = {2: [(datetime(2026, 6, 11, 10, 0), "11/06/2026 10:00: unidade", 3)]}
        por_sub = {
            5: [
                (
                    datetime(2026, 6, 11, 12, 0),
                    "11/06/2026 12:00: [Substatus] «Aguardando Caderno de Teste»",
                    10,
                ),
            ]
        }
        out = observacoes_linha_relatorio(row, por_att, por_u, por_sub)
        linhas = out.split("\n")
        self.assertEqual(linhas[0], "11/06/2026 15:00: obs recente")
        self.assertEqual(linhas[1], "11/06/2026 12:00: [Substatus] «Aguardando Caderno de Teste»")
        self.assertEqual(linhas[2], "11/06/2026 10:00: unidade")
        self.assertEqual(linhas[3], "11/06/2026 09:00: obs antiga")

    def test_observacoes_linha_dedup(self):
        row = {"id_atendimentos": 5, "id_unidades": 2}
        linha_dup = "11/06/2026 10:00: igual"
        por_att = {5: [(datetime(2026, 6, 11, 10, 0), linha_dup, 1)]}
        por_u = {2: [(datetime(2026, 6, 11, 10, 0), linha_dup, 2)]}
        out = observacoes_linha_relatorio(row, por_att, por_u)
        self.assertEqual(out.split("\n"), [linha_dup])


if __name__ == "__main__":
    unittest.main()
