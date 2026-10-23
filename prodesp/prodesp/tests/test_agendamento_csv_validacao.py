"""Testes — validação CSV de agendamento PRODESP.

Rodar:
    .venv_portal_pessoal\\Scripts\\python.exe -m pytest prodesp/prodesp/tests/test_agendamento_csv_validacao.py -q
"""
from __future__ import annotations

import unittest
from datetime import date

from prodesp.prodesp.agendamento_csv_validacao import (
    CONTRATADAS_PERMITIDAS,
    MSG_DUPLICATA_VGR,
    csv_valor_ausente,
    data_agendamento_anterior_hoje,
    validar_agendamento_csv_linha,
    validar_field_contratada_csv,
    validar_id_vgr_csv,
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


class TestAgendamentoCsvValidacao(unittest.TestCase):
    def test_csv_valor_ausente_placeholders(self):
        self.assertTrue(csv_valor_ausente(""))
        self.assertTrue(csv_valor_ausente("—"))
        self.assertTrue(csv_valor_ausente("-"))
        self.assertFalse(csv_valor_ausente("DELFIA"))

    def test_id_vgr_numerico(self):
        self.assertIsNone(validar_id_vgr_csv("2213783"))
        self.assertIn("inválido", validar_id_vgr_csv("ABC") or "")
        self.assertIn("obrigatório", validar_id_vgr_csv("") or "")

    def test_agenda_exige_contratada_data_hora(self):
        err, hora, contr, _cont = validar_agendamento_csv_linha(
            id_vgr="1",
            data_agendamento="2026-07-10",
            hora_agendamento="10:00",
            contratada="",
            tem_agenda=True,
            normalize_hora_fn=_norm_hora,
        )
        self.assertIn("Contratada obrigatória", err or "")
        self.assertIsNone(hora)
        self.assertIsNone(contr)

    def test_hora_texto_invalida(self):
        err, hora, contr, _ = validar_agendamento_csv_linha(
            id_vgr="99",
            data_agendamento="2026-07-10",
            hora_agendamento="A/C",
            contratada="DELFIA",
            tem_agenda=True,
            normalize_hora_fn=_norm_hora,
        )
        self.assertIn("Hora inválida", err or "")
        self.assertIn("A/C", err or "")
        self.assertIsNone(hora)
        self.assertIsNone(contr)

    def test_data_invalida(self):
        err, _, _, _ = validar_agendamento_csv_linha(
            id_vgr="1",
            data_agendamento="31/02/2026",
            hora_agendamento="10:00",
            contratada="DELFIA",
            tem_agenda=True,
            normalize_hora_fn=_norm_hora,
        )
        self.assertIn("Data inválida", err or "")

    def test_field_exige_contato(self):
        err, _, _, _ = validar_agendamento_csv_linha(
            id_vgr="1",
            data_agendamento="2026-07-10",
            hora_agendamento="10:00",
            contratada="DELFIA",
            field_planejado="Técnico João",
            contato_field="",
            tem_agenda=True,
            normalize_hora_fn=_norm_hora,
        )
        self.assertIn("Contato Field obrigatório", err or "")

    def test_field_empresa_deve_bater_contratada(self):
        err = validar_field_contratada_csv("DELFIA", "MAMInfo")
        self.assertIn("não corresponde", err or "")

    def test_field_nome_livre_ok(self):
        err = validar_field_contratada_csv("DELFIA", "João Silva")
        self.assertIsNone(err)

    def test_linha_valida(self):
        err, hora, contr, cont = validar_agendamento_csv_linha(
            id_vgr="100",
            data_agendamento="2026-07-10",
            hora_agendamento="14:30",
            contratada="delfia",
            field_planejado="DELFIA",
            contato_field="11999998888",
            tem_agenda=True,
            normalize_hora_fn=_norm_hora,
        )
        self.assertIsNone(err)
        self.assertEqual(hora, "14:30:00")
        self.assertEqual(contr, "DELFIA")
        self.assertEqual(cont, "11999998888")
        self.assertIn(contr, CONTRATADAS_PERMITIDAS)

    def test_data_passada(self):
        msg = data_agendamento_anterior_hoje("2020-01-01", date(2026, 7, 7))
        self.assertIn("anterior a hoje", msg or "")

    def test_msg_duplicata(self):
        self.assertIn("duplicado", MSG_DUPLICATA_VGR.lower())

    def test_motivo_corrigivel(self):
        from prodesp.prodesp.agendamento_csv_validacao import motivo_agendamento_csv_corrigivel

        self.assertFalse(
            motivo_agendamento_csv_corrigivel(
                "Unidade já possui atendimento concluído em 07/07/2026."
            )
        )
        self.assertFalse(
            motivo_agendamento_csv_corrigivel(
                "Unidade não encontrada (ID VGR inexistente na base)."
            )
        )
        self.assertTrue(
            motivo_agendamento_csv_corrigivel(
                "Contratada inválida (MAMInfo). Valores permitidos: DELFIA"
            )
        )
        self.assertFalse(motivo_agendamento_csv_corrigivel(MSG_DUPLICATA_VGR))


class TestAgendamentoCsvNotifierPrevia(unittest.TestCase):
    def test_parse_rejeitadas_previa_payload(self):
        from prodesp.prodesp.blueprint.agendamento_csv_notifier import (
            parse_rejeitadas_previa_payload,
        )

        rows = parse_rejeitadas_previa_payload(
            [
                {
                    "id_vgr": "123",
                    "data_agendamento": "2026-07-10",
                    "hora_agendamento": "10:00",
                    "contratada": "DELFIA",
                    "motivo": "Hora inválida (A/C).",
                },
                {"id_vgr": "", "motivo": "ignorada"},
                "invalido",
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id_vgr, "123")
        self.assertIn("Hora inválida", rows[0].detalhe)

    def test_resumo_inclui_rejeitadas_previa(self):
        from prodesp.prodesp.blueprint.agendamento_csv_notifier import (
            AgendamentoCsvLinha,
            AgendamentoCsvRelatorio,
            build_email_html,
            build_resumo_from_relatorio,
            build_subject,
        )

        rel = AgendamentoCsvRelatorio(
            sucessos=[AgendamentoCsvLinha(id_vgr="1")],
            rejeitadas_previa=[
                AgendamentoCsvLinha(id_vgr="9", detalhe="Contratada inválida.")
            ],
        )
        resumo = build_resumo_from_relatorio(rel)
        self.assertIn("pré-validação", resumo)
        self.assertIn("não enviadas", resumo)
        self.assertIn("prévia", build_subject(rel))
        html = build_email_html(rel)
        self.assertIn("Rejeitadas na pré-validação", html)
        self.assertIn("Contratada inválida", html)


if __name__ == "__main__":
    unittest.main()
