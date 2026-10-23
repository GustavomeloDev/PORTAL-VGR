"""Testes de relatorio_tempos.

Rodar:

    .venv_portal_pessoal\\Scripts\\python.exe -m pytest prodesp/prodesp/gestao/test_relatorio_tempos.py -q
"""
from __future__ import annotations

import unittest
from datetime import datetime

import pytz

from prodesp.prodesp.gestao.relatorio_tempos import (
    COL_TEMPO_ATENDIMENTO,
    COL_TEMPO_VITA,
    inferir_fim_corte_atendimento,
    metricas_atendimento_logs,
)

TZ = pytz.timezone("America/Sao_Paulo")


class TestRelatorioTempos(unittest.TestCase):
    def test_tempo_vita_e_atendimento_config(self):
        logs = [
            {
                "valor_novo_log": "Aguardando Config. Remota",
                "alterado_em_log": datetime(2026, 6, 11, 9, 0, 0),
            },
            {
                "valor_novo_log": "Em Configuração Remota",
                "alterado_em_log": datetime(2026, 6, 11, 9, 30, 0),
            },
            {
                "valor_novo_log": "Aguardando Cliente",
                "alterado_em_log": datetime(2026, 6, 11, 10, 0, 0),
            },
            {
                "valor_novo_log": "Em Configuração do MPLS",
                "alterado_em_log": datetime(2026, 6, 11, 10, 30, 0),
            },
            {
                "valor_novo_log": "Concluído",
                "alterado_em_log": datetime(2026, 6, 11, 11, 0, 0),
            },
        ]
        fim = TZ.localize(datetime(2026, 6, 11, 11, 0, 0))
        m = metricas_atendimento_logs(logs, TZ, fim_corte=fim)
        self.assertEqual(m["Tempo Aguardando Config. Remota"], "00:30:00")
        self.assertEqual(m["Tempo Em Configuração Remota"], "00:30:00")
        self.assertEqual(m["Tempo Aguardando Cliente"], "00:30:00")
        self.assertEqual(m["Tempo Em Configuração do MPLS"], "00:30:00")
        self.assertEqual(m[COL_TEMPO_ATENDIMENTO], "01:00:00")
        self.assertEqual(m[COL_TEMPO_VITA], "02:00:00")

    def test_tempo_vita_concluido_nao_conta_ate_hoje(self):
        """Último substatus Concluído não pode somar dias até a geração do relatório."""
        logs = [
            {
                "valor_novo_log": "Em Configuração Remota",
                "alterado_em_log": datetime(2026, 6, 11, 9, 0, 0),
            },
            {
                "valor_novo_log": "Concluído",
                "alterado_em_log": datetime(2026, 6, 11, 10, 0, 0),
            },
        ]
        status_logs = [
            {
                "tipo_campo_log": "status",
                "valor_novo_log": "Concluído",
                "alterado_em_log": datetime(2026, 6, 11, 10, 0, 0),
            }
        ]
        fim = inferir_fim_corte_atendimento(status_logs=status_logs, tz_sp=TZ)
        m = metricas_atendimento_logs(logs, TZ, fim_corte=fim)
        self.assertEqual(m["Tempo Em Configuração Remota"], "01:00:00")
        self.assertEqual(m[COL_TEMPO_VITA], "01:00:00")
        self.assertLess(int(m[COL_TEMPO_VITA].split(":")[0]), 10)


if __name__ == "__main__":
    unittest.main()
