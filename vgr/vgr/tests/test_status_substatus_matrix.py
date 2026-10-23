"""Testes matriz status/substatus VGR (espelho PRODESP + agenda legado)."""

from __future__ import annotations

import unittest

from vgr.vgr.operacao.catalogo_agendamento import (
    validar_par_status_substatus_agendamento,
)
from vgr.vgr.operacao.catalogo_atendimento import (
    validar_par_status_substatus,
)
from vgr.vgr.operacao.atendimento_business_rules import (
    destinos_substatus_permitidos_ag_gp,
    validar_transicao_substatus_ag_gp,
)
from vgr.vgr.operacao.validators_atendimento import parse_atendimento_payload
from vgr.vgr.operacao.validators_agendamento import parse_agendamento_payload


class TestParAtendimento(unittest.TestCase):
    def test_em_atendimento_fluxo_ok(self):
        self.assertIsNone(
            validar_par_status_substatus("Em Atendimento", "Aguarda Gestão")
        )
        self.assertIsNone(
            validar_par_status_substatus("Em Atendimento", "Com Suporte")
        )

    def test_quebra_tbra_so_sci_tecnica(self):
        self.assertIsNone(validar_par_status_substatus("Quebra TBRA", "Quebra SCI"))
        err = validar_par_status_substatus("Quebra TBRA", "Quebra Cliente")
        self.assertIsNotNone(err)

    def test_quebra_normal(self):
        self.assertIsNone(validar_par_status_substatus("Quebra", "Quebra Hardware"))
        err = validar_par_status_substatus("Quebra", "Quebra SCI")
        self.assertIsNotNone(err)

    def test_concluido_parcial(self):
        self.assertIsNone(
            validar_par_status_substatus(
                "Concluído Parcial", "Pendente Configuração Remota"
            )
        )
        err = validar_par_status_substatus("Concluído Parcial", "Aguarda Gestão")
        self.assertIsNotNone(err)

    def test_payload_rejeita_par_invalido(self):
        with self.assertRaises(ValueError):
            parse_atendimento_payload(
                {
                    "id_unidade": 1,
                    "status_atendimento": "Quebra TBRA",
                    "substatus_atendimento": "Aguarda Gestão",
                }
            )


class TestAgGpTransicao(unittest.TestCase):
    def test_gestao_pode_fila(self):
        dest = destinos_substatus_permitidos_ag_gp("Aguarda Gestão")
        self.assertIn("Aguardando Config. Remota", dest)

    def test_ag_gp_bloqueia_em_config(self):
        err = validar_transicao_substatus_ag_gp(
            "Aguarda Gestão", "Em Configuração Remota"
        )
        self.assertIsNotNone(err)


class TestParAgendamento(unittest.TestCase):
    def test_improdutiva_exige_sub(self):
        err = validar_par_status_substatus_agendamento("Improdutiva", None)
        self.assertIsNotNone(err)

    def test_improdutiva_ok(self):
        self.assertIsNone(
            validar_par_status_substatus_agendamento("Improdutiva", "quebra")
        )

    def test_outro_status_limpa(self):
        err = validar_par_status_substatus_agendamento(
            "Técnico em deslocamento", "quebra"
        )
        self.assertIsNotNone(err)

    def test_payload_rejeita_sub_fora_improdutiva(self):
        with self.assertRaises(ValueError):
            parse_agendamento_payload(
                {
                    "id_unidade": 1,
                    "status_agendamento": "Técnico em deslocamento",
                    "substatus_agendamento": "quebra",
                }
            )


if __name__ == "__main__":
    unittest.main()
