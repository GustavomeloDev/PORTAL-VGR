"""Testes do pacote reutilizável core.fgt_coleta (sem SSH real)."""

from __future__ import annotations

import inspect
import os
import unittest
from unittest.mock import patch

from core.fgt_coleta.commands import FGT_COMMANDS_DMA, comandos_perfil
from core.fgt_coleta.credentials import resolve_fgt_ssh_credentials
from core.fgt_coleta.historico_texto import historico_coleta_sucesso
from core.fgt_coleta.stamp import (
    firmware_carimbo,
    formatar_velocidade_carimbo,
    frase_admin_carimbo,
    montar_carimbo_noc,
)
from core.fgt_coleta.sys_status import (
    frase_fortimanager,
    frase_licenca_forticloud,
    parse_get_sys_status,
)


class TestComandosDma(unittest.TestCase):
    def test_whitelist_exata(self):
        self.assertEqual(
            comandos_perfil("dma"),
            [
                "get system status",
                "execute ping-options use-sdwan yes",
                "execute ping 8.8.8.8",
                "execute ping google.com",
                "execute ping service.fortiguard.net",
                "execute ping update.fortiguard.net",
                "execute ping guard.fortinet.net",
                "get ipsec tunnel list",
                "get router info bgp summary",
                "get router info routing-table all",
                "get system arp",
                "show system interface",
                "diagnose sys sdwan member",
                "diagnose sys sdwan health-check",
                "diagnose sys sdwan service4",
            ],
        )
        self.assertEqual(comandos_perfil("desconhecido"), list(FGT_COMMANDS_DMA))


class TestCredenciais(unittest.TestCase):
    def test_preferencia_fgt_ssh_com_fallback_prodesp(self):
        env = {
            "FGT_SSH_USER": "dma-user",
            "FGT_SSH_PASSWORD": "segredo-dma",
            "FGT_SSH_MODE": "direct",
            "PRODESP_FGT_USER": "vvita",
            "PRODESP_FGT_PASSWORD": "segredo-prodesp",
        }
        with patch.dict(os.environ, env, clear=False):
            creds = resolve_fgt_ssh_credentials()
        self.assertEqual(creds.user, "dma-user")
        self.assertEqual(creds.password, "segredo-dma")
        self.assertEqual(creds.mode, "direct")

    def test_fallback_prodesp(self):
        env = {
            "FGT_SSH_USER": "",
            "FGT_SSH_PASSWORD": "",
            "FGT_SSH_MODE": "direct",
            "PRODESP_FGT_USER": "vvita",
            "PRODESP_FGT_PASSWORD": "segredo-prodesp",
        }
        with patch.dict(os.environ, env, clear=False):
            creds = resolve_fgt_ssh_credentials()
        self.assertEqual(creds.user, "vvita")
        self.assertEqual(creds.password, "segredo-prodesp")


class TestStamp(unittest.TestCase):
    def test_frase_admin(self):
        self.assertEqual(
            frase_admin_carimbo("Verificação pós-delete: OK — usuário «admin» não consta mais."),
            "Usuário admin deletado",
        )
        self.assertEqual(
            frase_admin_carimbo("Usuário «admin» não cadastrado; etapa de limpeza ignorada."),
            "Usuário admin não cadastrado",
        )
        self.assertEqual(
            frase_admin_carimbo("Verificação pós-delete: FALHA — usuário «admin» ainda aparece"),
            "Falha ao remover usuário admin",
        )

    def test_firmware_e_velocidade(self):
        self.assertEqual(
            firmware_carimbo("FortiGate-100F v7.4.12,build2795,250901 (GA.M)"),
            "Firmware atualizado para 7.4.12",
        )
        self.assertEqual(formatar_velocidade_carimbo("400"), "400MB")
        self.assertEqual(formatar_velocidade_carimbo("400 Mbps"), "400MB")

    def test_carimbo_modelo_inicial(self):
        texto = montar_carimbo_noc(
            loopback="172.19.67.27",
            frase_admin="Usuário admin deletado",
            firmware="Firmware atualizado para 7.4.12",
            licenca_forticloud="Licença ativa na FortiCloud",
            fortimanager="Fortigate cadastrado no FortiManager",
            id_vgr="1806928",
            topologia="FILIAIS",
            solucao="G",
            fornecedor="FORTINET",
            modelo="FortiGate-100F",
            chave_licenca="6391MH343822",
            serial="FG100FTK23064362",
            links=[
                {
                    "ordem": 1,
                    "operadora": "VIVO",
                    "velocidade": "400",
                    "designador": "110080185881490",
                    "id_vgr_link": "1858848",
                    "ip_wan": "186.238.214.70",
                    "telefone_reparo": "10315",
                    "topologia": "HUB and Spoke",
                    "tipo": "Spoke",
                    "solucao": "G",
                    "fornecedor": "FORTINET",
                    "modelo": "FG100F",
                    "serial": "FG100FTK23064362 / FG100FTK23077463",
                }
            ],
            logs_texto="=== FGT 172.19.67.27 ===",
        )
        self.assertIn("Loopback: 172.19.67.27", texto)
        self.assertIn("Usuário admin deletado", texto)
        self.assertIn("Firmware atualizado para 7.4.12", texto)
        self.assertIn("Licença ativa na FortiCloud", texto)
        self.assertIn("Fortigate cadastrado no FortiManager", texto)
        self.assertIn("ID VGR: 1806928", texto)
        self.assertIn("TOPOLOGIA: FILIAIS", texto)
        self.assertIn("SOLUÇÃO: G", texto)
        self.assertIn("LINK 1 - IP DEDICADO: VIVO", texto)
        self.assertIn("Velocidade: 400MB", texto)
        self.assertIn("Tel de Reparo: 10315", texto)
        self.assertIn("=== FGT 172.19.67.27 ===", texto)


class TestSysStatus(unittest.TestCase):
    def test_parse_e_frases(self):
        body = (
            "Version: FortiGate-100F v7.4.12,build2795,250901 (GA.M)\n"
            "Serial-Number: FG100FTK23064362\n"
            "Hostname: dma-spk-loja081-01\n"
            "License Status: Valid\n"
            "FortiManager: Registered\n"
        )
        parsed = parse_get_sys_status(body)
        self.assertEqual(parsed["serial"], "FG100FTK23064362")
        self.assertIn("v7.4.12", parsed["version"])
        self.assertEqual(frase_licenca_forticloud(parsed), "Licença ativa na FortiCloud")
        self.assertEqual(frase_fortimanager(parsed), "Fortigate cadastrado no FortiManager")
        self.assertEqual(frase_fortimanager({}), "")


class TestHistoricoTexto(unittest.TestCase):
    def test_inclui_resumo_admin(self):
        txt = historico_coleta_sucesso(
            hostname="dma-spk-loja081-01",
            identificador="Loja 081",
            elapsed_seconds=12.3,
            commands_run=20,
            log_chars=1000,
            parcial=False,
            resumo_limpeza_admin="Usuário «admin» não consta mais.",
        )
        self.assertIn("Coleta de logs FGT concluída com sucesso.", txt)
        self.assertIn("Usuário «admin» não consta mais.", txt)


class TestCollectorIsolation(unittest.TestCase):
    def test_core_nao_importa_prodesp(self):
        from core.fgt_coleta import collector

        src = inspect.getsource(collector)
        self.assertNotIn("from prodesp", src)
        self.assertNotIn("import prodesp", src)

    def test_loopback_invalido_nao_conecta(self):
        from core.fgt_coleta.collector import coletar_logs_fgt

        with patch("core.fgt_coleta.collector._connect_direct") as conn:
            out = coletar_logs_fgt("nao-e-ip")
        conn.assert_not_called()
        self.assertFalse(out.ok)
        self.assertTrue(out.errors)


if __name__ == "__main__":
    unittest.main()
