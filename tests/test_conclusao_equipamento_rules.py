"""Testes das regras de conclusão (serial Fortinet + cruzamento com coleta)."""
import unittest

from prodesp.prodesp.conclusao_equipamento_rules import (
    extrair_sys_status_dos_logs,
    serial_fortinet_valido,
    unidade_tem_atendimento_exigindo_serial_padrao,
    validate_conclusao_equipamento,
    validate_serial_fortinet_format,
    validate_serial_fortinet_para_blueprint,
)


class TestConclusaoEquipamentoRules(unittest.TestCase):
    def test_serial_real_ok(self):
        self.assertTrue(serial_fortinet_valido("FGT40FTK2409D6QK"))
        self.assertTrue(serial_fortinet_valido("fgt40ftk25009285"))
        self.assertIsNone(validate_serial_fortinet_format("FGT60FTK25001234"))

    def test_serial_fg120g_ok(self):
        for sn in (
            "FG120GTK25006244",
            "FG120GTK25004510",
            "FG120GTK25006562",
            "FG120GTK25005990",
            "FG120GTK25007172",
        ):
            self.assertTrue(serial_fortinet_valido(sn), sn)
            self.assertIsNone(validate_serial_fortinet_format(sn), sn)
        self.assertTrue(serial_fortinet_valido("fg120gtk25006244"))
        # Prefixo FGT + 120G também aceito (forma alternativa)
        self.assertTrue(serial_fortinet_valido("FGT120GTK25006244"))

    def test_serial_provisorio_bloqueado(self):
        for bad in ("123", "123456", "TEST", "FGT40F", "FGT40FXXXXXXX", "SERIALNUM"):
            self.assertFalse(serial_fortinet_valido(bad), bad)
            self.assertIsNotNone(validate_serial_fortinet_format(bad))

    def test_conclusao_sem_equipamento(self):
        errs = validate_conclusao_equipamento(
            hostname_unidade="host-1",
            equipamentos=[],
            logs_atendimentos="",
        )
        self.assertTrue(any("série" in e.lower() or "serial" in e.lower() for e in errs))

    def test_conclusao_serial_provisorio(self):
        errs = validate_conclusao_equipamento(
            hostname_unidade="host-1",
            equipamentos=[{"serial": "123", "versao": "7.4.11"}],
            logs_atendimentos="",
        )
        self.assertTrue(any("provisório" in e.lower() or "inválido" in e.lower() for e in errs))

    def test_cruzamento_serial_hostname_divergente(self):
        logs = """
=== FGT 10.254.0.1 ===

--- get sys status ---
Version: FortiGate-40F v7.4.11,build2878,260126 (GA.M)
Serial-Number: FGT40FTK2409D6QK
Hostname: sap-spk-c1-c2-id-00309472

--- sys status — resumo ---
Version do equipamento: FortiGate-40F v7.4.11
Número de Serie: FGT40FTK2409D6QK
Hostname: sap-spk-c1-c2-id-00309472
"""
        errs = validate_conclusao_equipamento(
            hostname_unidade="hostname-errado",
            equipamentos=[
                {"serial": "FGT40FTK99999999", "versao": "7.4.10"},
            ],
            logs_atendimentos=logs,
        )
        self.assertTrue(any("hostname" in e.lower() for e in errs))
        self.assertTrue(any("série" in e.lower() or "serie" in e.lower() for e in errs))
        self.assertTrue(any("versão" in e.lower() or "versao" in e.lower() for e in errs))

    def test_cruzamento_ok_quando_bate(self):
        logs = """
--- get sys status ---
Version: FortiGate-40F v7.4.11,build2878,260126 (GA.M)
Serial-Number: FGT40FTK2409D6QK
Hostname: sap-spk-c1-c2-id-00309472
"""
        errs = validate_conclusao_equipamento(
            hostname_unidade="sap-spk-c1-c2-id-00309472",
            equipamentos=[
                {"serial": "FGT40FTK2409D6QK", "versao": "7.4.11"},
            ],
            logs_atendimentos=logs,
        )
        self.assertEqual(errs, [])

    def test_sem_coleta_nao_exige_cruzamento(self):
        errs = validate_conclusao_equipamento(
            hostname_unidade="qualquer-host",
            equipamentos=[{"serial": "FGT40FTK2409D6QK", "versao": "7.4.11"}],
            logs_atendimentos="",
        )
        self.assertEqual(errs, [])

    def test_extrair_sys_status(self):
        parsed = extrair_sys_status_dos_logs(
            "--- get sys status ---\nSerial-Number: FGT40FTK2409D6QK\nHostname: h1\n"
            "Version: FortiGate-40F v7.4.11,build1\n"
        )
        self.assertEqual(parsed.get("serial"), "FGT40FTK2409D6QK")
        self.assertEqual(parsed.get("hostname"), "h1")
        self.assertIn("7.4.11", parsed.get("version") or "")

    def test_blueprint_serial_antecipado_permite_provisorio(self):
        self.assertIsNone(
            validate_serial_fortinet_para_blueprint("123", exige_padrao=False)
        )
        self.assertIsNone(
            validate_serial_fortinet_para_blueprint("FGT40FTK2409D6QK", exige_padrao=False)
        )

    def test_blueprint_serial_com_atendimento_bloqueia_provisorio(self):
        err = validate_serial_fortinet_para_blueprint("123", exige_padrao=True)
        self.assertIsNotNone(err)
        self.assertIn("Em Atendimento", err)
        self.assertIsNone(
            validate_serial_fortinet_para_blueprint("FGT40FTK2409D6QK", exige_padrao=True)
        )

    def test_unidade_tem_atendimento_exigindo_serial(self):
        from unittest.mock import MagicMock

        cur = MagicMock()
        cur.fetchall.return_value = [{"status": "Quebra"}]
        self.assertFalse(unidade_tem_atendimento_exigindo_serial_padrao(cur, 1))
        cur.fetchall.return_value = [{"status": "Em Atendimento"}]
        self.assertTrue(unidade_tem_atendimento_exigindo_serial_padrao(cur, 1))
        cur.fetchall.return_value = [{"status": "Concluído Parcial"}]
        self.assertTrue(unidade_tem_atendimento_exigindo_serial_padrao(cur, 1))


if __name__ == "__main__":
    unittest.main()
