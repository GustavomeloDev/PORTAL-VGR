"""Testes unitários — exportação de certificados FortiGate (sem SSH real)."""
from __future__ import annotations

import os
import socket
import struct
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from prodesp.config_paths import resolve_certificados_local_base, resolve_pasta_certificado
from prodesp.prodesp.caderno.fgt_cert_exporter import (
    CertExportResult,
    _extract_pem_blocks,
    _parse_local_cert_names,
    _sanitizar_motivo_historico,
    _sanitize_filename_part,
    _unique_dest_path,
    certificado_export_method,
    exportar_pem_certificado_cli,
)
from prodesp.prodesp.caderno.fgt_ssh_tftp import TftpWriteServer, detect_portal_tftp_ip, resolve_tftp_server_ip, tftp_mode


class TestCertificadoExport(unittest.TestCase):
    def test_parse_local_cert_names_get(self):
        raw = """
        == [ vpn certificate local ]
        name: Cert_SSLVPN
        subject: CN=sslvpn
        name: Fortinet_CA_SSL
        """
        names = _parse_local_cert_names(raw)
        self.assertEqual(names, ["Cert_SSLVPN", "Fortinet_CA_SSL"])

    def test_certificados_alvo_config_default(self):
        from prodesp.prodesp.caderno.fgt_cert_exporter import (
            CertExportTarget,
            _certificados_alvo_config,
            _extensao_certificado,
        )

        with patch.dict(
            os.environ,
            {"PRODESP_CERTIFICADO_FGT_NOME": "", "PRODESP_CERTIFICADO_FGT_FORMATO": ""},
            clear=False,
        ):
            targets = _certificados_alvo_config()
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0], CertExportTarget(name="Fortinet_CA_SSL", formato="cer"))
        self.assertEqual(_extensao_certificado("cer"), ".cer")
        self.assertEqual(_extensao_certificado("p12"), ".p12")

        from prodesp.prodesp.caderno.fgt_cert_exporter import (
            _eh_certificado_builtin_fortinet,
            _filtrar_certificados_exportaveis,
            _parse_cert_blocks_exportaveis,
        )

        self.assertTrue(_eh_certificado_builtin_fortinet("Fortinet_SSL"))
        self.assertFalse(_eh_certificado_builtin_fortinet("Cert_SSLVPN"))
        names = _filtrar_certificados_exportaveis(
            ["Fortinet_SSL", "Cert_SSLVPN", "Fortinet_CA_SSL"]
        )
        self.assertEqual(names, ["Cert_SSLVPN"])
        raw = """
        name: Fortinet_SSL
        source: factory
        name: Cert_SSLVPN
        source: user
        """
        self.assertEqual(_parse_cert_blocks_exportaveis(raw), ["Cert_SSLVPN"])

        raw = """
        Local certificate
          Name        CN
          Cert_SSLVPN O=Test
        """
        names = _parse_local_cert_names(raw)
        self.assertEqual(names, ["Cert_SSLVPN"])

    def test_sanitize_filename_part(self):
        self.assertEqual(_sanitize_filename_part("FW-SP 001"), "FW-SP_001")

    def test_nome_arquivo_certificado_exportado(self):
        from prodesp.prodesp.caderno.fgt_cert_exporter import _nome_arquivo_certificado_exportado

        self.assertEqual(_nome_arquivo_certificado_exportado("Fortinet_CA_SSL", ".cer"), "Fortinet_CA_SSL.cer")
        self.assertEqual(_nome_arquivo_certificado_exportado("Cert_SSLVPN", ".p12"), "Cert_SSLVPN.p12")

    def test_unique_dest_path_nao_sobrescreve(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "a.p12")
            with open(base, "wb") as handle:
                handle.write(b"x")
            alt = _unique_dest_path(tmp, "a.p12")
            self.assertNotEqual(alt, base)
            self.assertTrue(alt.endswith("_2.p12") or alt.endswith("a_2.p12"))

    def test_resolve_pasta_certificado(self):
        with patch.dict(os.environ, {"PRODESP_CERTIFICADO_LOCAL_DIR": ""}, clear=False):
            path = resolve_pasta_certificado("DIPOL", "FW-SP-001", rede=False)
            self.assertIn("DIPOL", path)
            self.assertIn("FW-SP-001", path)
            base = resolve_certificados_local_base()
            self.assertIn(base, path)
            self.assertIn(os.path.join("var", "certificados"), base.replace("/", os.sep))

    def test_resolve_pasta_certificado_rede_por_acronimo(self):
        with patch.dict(
            os.environ,
            {
                "PRODESP_CERTIFICADO_NETWORK_DIR": r"C:\Certificados\Padrao",
                "PRODESP_CERTIFICADO_NETWORK_DIRS": (
                    r"DER=C:\Certificados\DER;"
                    r"POUPATEMPO=C:\Certificados\POUPATEMPO"
                ),
            },
            clear=False,
        ):
            der = resolve_pasta_certificado("DER", "fw-sp-001", rede=True)
            pt = resolve_pasta_certificado("POUPATEMPO", "fw-rj-002", rede=True)
            dipol = resolve_pasta_certificado("DIPOL", "fw-003", rede=True)
        self.assertEqual(der, os.path.join(r"C:\Certificados\DER", "fw-sp-001"))
        self.assertEqual(pt, os.path.join(r"C:\Certificados\POUPATEMPO", "fw-rj-002"))
        self.assertTrue(dipol.endswith(os.path.join("DIPOL", "fw-003")))

    def test_historico_sucesso(self):
        from prodesp.prodesp.caderno.fgt_cert_exporter import CertExportItem

        result = CertExportResult(
            ok=True,
            hostname="FW-SP-001",
            acronimo="DIPOL",
            elapsed_seconds=43.6,
            items=[
                CertExportItem(
                    ok=True,
                    cert_name="Cert_SSLVPN",
                    filename="Fortinet_CA_SSL.cer",
                    path_interno=r"C:\secret\var\certificados\DIPOL\FW-SP-001\x.p12",
                    path_externo=r"C:\Users\gusta\OneDrive\Certificados\DIPOL\FW-SP-001\x.p12",
                    metodo="CLI SSH (show full-configuration)",
                )
            ],
        )
        hist = result.historico_sucesso()
        self.assertIn("Exportação de certificado concluída com sucesso", hist)
        self.assertIn("Cert_SSLVPN", hist)
        self.assertIn("Método: CLI SSH (show full-configuration)", hist)
        self.assertIn("Pasta interna: DIPOL/FW-SP-001/", hist)
        self.assertIn("Cópia na rede: sim (DIPOL/FW-SP-001/)", hist)
        self.assertNotIn("C:\\", hist)
        self.assertNotIn("OneDrive", hist)

    def test_historico_falha(self):
        result = CertExportResult(ok=False, hostname="FW-SP-001", acronimo="DIPOL")
        hist = result.historico_falha("Timeout na conexão SSH.")
        self.assertIn("Falha na exportação", hist)
        self.assertIn("Timeout", hist)
        self.assertIn("Hostname: FW-SP-001", hist)

    def test_sanitizar_motivo_historico(self):
        raw = (
            "Fortinet_Factory: Build-in certificate not allowed; "
            "Fortinet_SSL: Build-in certificate not allowed; "
            r"C:\Users\gusta\secret\file.cer: erro"
        )
        out = _sanitizar_motivo_historico(raw)
        self.assertNotIn("C:\\Users", out)
        self.assertIn("build-in", out.lower())

    def test_certificado_auto_export_config(self):
        from prodesp.prodesp.caderno.certificado_auto_export import (
            acronimo_elegivel_auto_export,
            acronimos_auto_export_certificado,
            is_atendimento_concluido_completo,
            transicao_para_concluido_completo,
        )

        with patch.dict(
            os.environ,
            {
                "PRODESP_CERTIFICADO_AUTO_EXPORT": "1",
                "PRODESP_CERTIFICADO_AUTO_ACRONYMS": "POUPATEMPO,DER",
            },
            clear=False,
        ):
            self.assertEqual(acronimos_auto_export_certificado(), {"POUPATEMPO", "DER"})
            self.assertTrue(acronimo_elegivel_auto_export("poupatempo"))
            self.assertFalse(acronimo_elegivel_auto_export("DPESP"))

        with patch.dict(
            os.environ,
            {"PRODESP_CERTIFICADO_AUTO_ACRONYMS": "*"},
            clear=False,
        ):
            self.assertIsNone(acronimos_auto_export_certificado())
            self.assertTrue(acronimo_elegivel_auto_export("QUALQUER"))

        self.assertTrue(is_atendimento_concluido_completo("Concluído", "Concluído"))
        self.assertFalse(is_atendimento_concluido_completo("Concluído Parcial", "Concluído"))
        self.assertTrue(
            transicao_para_concluido_completo(
                "Em Atendimento",
                "Em Configuração",
                "Concluído",
                "Concluído",
            )
        )
        self.assertFalse(
            transicao_para_concluido_completo(
                "Concluído",
                "Concluído",
                "Concluído",
                "Concluído",
            )
        )

    @patch("prodesp.prodesp.caderno.certificado_auto_export.threading.Thread")
    def test_tentar_agendar_exportacao_certificado_automatica(self, mock_thread):
        from prodesp.prodesp.caderno.certificado_auto_export import (
            tentar_agendar_exportacao_certificado_automatica,
        )

        with patch.dict(
            os.environ,
            {
                "PRODESP_CERTIFICADO_AUTO_EXPORT": "1",
                "PRODESP_CERTIFICADO_AUTO_ACRONYMS": "POUPATEMPO",
            },
            clear=False,
        ):
            ok = tentar_agendar_exportacao_certificado_automatica(
                99,
                acronimo="POUPATEMPO",
                old_status="Em Atendimento",
                old_substatus="Em Caderno de Teste",
                new_status="Concluído",
                new_substatus="Concluído",
            )
        self.assertTrue(ok)
        mock_thread.assert_called_once()

    @patch("prodesp.prodesp.caderno.fgt_cert_exporter.exec_fgt_cli")
    def test_exportar_pem_certificado_cli(self, mock_exec):
        pem = (
            "-----BEGIN CERTIFICATE-----\n"
            "MIIBkTCB+wIJAK\n"
            "-----END CERTIFICATE-----\n"
        )
        mock_exec.return_value = f"name: Fortinet_CA_SSL\n{pem}"
        shell = MagicMock()
        out, metodo = exportar_pem_certificado_cli(shell, "Fortinet_CA_SSL")
        self.assertIn("BEGIN CERTIFICATE", out)
        self.assertIn("CLI SSH", metodo)
        mock_exec.assert_called()

    def test_extract_pem_blocks(self):
        raw = """
        name: Fortinet_CA_SSL
        -----BEGIN CERTIFICATE-----
        MIIBkTCB+wIJAK
        -----END CERTIFICATE-----
        """
        blocks = _extract_pem_blocks(raw)
        self.assertEqual(len(blocks), 1)
        self.assertIn("BEGIN CERTIFICATE", blocks[0])

    def test_certificado_export_method(self):
        with patch.dict(os.environ, {"PRODESP_CERTIFICADO_EXPORT_METHOD": "cli"}, clear=False):
            self.assertEqual(certificado_export_method(), "cli")
        with patch.dict(os.environ, {"PRODESP_CERTIFICADO_EXPORT_METHOD": "invalid"}, clear=False):
            self.assertEqual(certificado_export_method(), "auto")


    @patch("socket.socket")
    def test_detect_portal_tftp_ip_manual(self, mock_socket_cls):
        with patch.dict(os.environ, {"PRODESP_TFTP_IP": "192.168.10.5"}, clear=False):
            ip = detect_portal_tftp_ip(fallback_host="172.19.40.2")
        self.assertEqual(ip, "192.168.10.5")
        mock_socket_cls.assert_not_called()

    @patch("socket.socket")
    def test_detect_portal_tftp_ip(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.getsockname.return_value = ("192.168.1.50", 54321)
        mock_socket_cls.return_value = mock_sock
        with patch.dict(os.environ, {"PRODESP_TFTP_IP": ""}, clear=False):
            ip = detect_portal_tftp_ip(fallback_host="172.19.40.2")
        self.assertEqual(ip, "192.168.1.50")

    def test_tftp_mode_local_default(self):
        with patch.dict(os.environ, {"PRODESP_TFTP_MODE": "", "PRODESP_TFTP_IP": ""}, clear=False):
            self.assertEqual(tftp_mode(), "local")

    def test_tftp_mode_jump_override(self):
        with patch.dict(
            os.environ,
            {"PRODESP_TFTP_MODE": "jump", "PRODESP_TFTP_IP": ""},
            clear=False,
        ):
            ip = resolve_tftp_server_ip(jump_host="172.25.135.2", fgt_ip="10.254.8.42")
        self.assertEqual(ip, "172.25.135.2")

    def test_tftp_write_server_recebe_arquivo(self):
        import tempfile

        from prodesp.prodesp.caderno.fgt_ssh_tftp import TftpWriteServer

        with tempfile.TemporaryDirectory() as tmp:
            port = 18769
            srv = TftpWriteServer(tmp, port=port, timeout=10.0)
            srv.start()
            time.sleep(0.2)
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                payload = b"test.cer\x00octet\x00"
                wrq = struct.pack("!H", 2) + payload
                client.sendto(wrq, ("127.0.0.1", port))
                time.sleep(0.2)
                data1 = struct.pack("!HH", 3, 1) + b"hello-cert"
                client.sendto(data1, ("127.0.0.1", port))
                deadline = time.time() + 5
                while time.time() < deadline:
                    if srv.result.ok:
                        break
                    time.sleep(0.1)
                self.assertTrue(srv.result.ok, srv.result.error)
                self.assertTrue(os.path.isfile(os.path.join(tmp, "test.cer")))
            finally:
                client.close()
                srv.stop()

    def test_recipients_por_acronimo_e_cc(self):
        from prodesp.prodesp.caderno.certificado_export_service import (
            _cc_recipients_from_env,
            _parse_email_map_por_acronimo,
            _recipients_from_env,
        )

        mapa = _parse_email_map_por_acronimo(
            "POUPATEMPO=daniel@apoio.gov.br;DER=tana@apoio.gov.br,outro@apoio.gov.br"
        )
        self.assertEqual(mapa["POUPATEMPO"], ["daniel@apoio.gov.br"])
        self.assertEqual(mapa["DER"], ["tana@apoio.gov.br", "outro@apoio.gov.br"])

        env = {
            "PRODESP_CERTIFICADO_EMAIL_TO_ACRONIMOS": (
                "POUPATEMPO=daniel@apoio.gov.br;DER=tana@apoio.gov.br"
            ),
            "PRODESP_CERTIFICADO_EMAIL_TO": "fallback@telefonica.com",
            "PRODESP_CERTIFICADO_EMAIL_CC": "caq@telefonica.com",
        }
        with patch.dict(os.environ, env, clear=False):
            # acrônimo mapeado → destinatário específico
            self.assertEqual(_recipients_from_env("poupatempo"), ["daniel@apoio.gov.br"])
            self.assertEqual(_recipients_from_env("DER"), ["tana@apoio.gov.br"])
            # acrônimo fora do mapa → lista global (comportamento atual)
            self.assertEqual(_recipients_from_env("DIPOL"), ["fallback@telefonica.com"])
            self.assertEqual(_recipients_from_env(""), ["fallback@telefonica.com"])
            # CC fixo; deduplica se já estiver no Para
            self.assertEqual(
                _cc_recipients_from_env(["daniel@apoio.gov.br"]), ["caq@telefonica.com"]
            )
            self.assertEqual(_cc_recipients_from_env(["CAQ@telefonica.com"]), [])

        # sem mapa → tudo pela lista global (modo antigo)
        with patch.dict(
            os.environ,
            {
                "PRODESP_CERTIFICADO_EMAIL_TO_ACRONIMOS": "",
                "PRODESP_CERTIFICADO_EMAIL_TO": "a@x.com;b@y.com",
            },
            clear=False,
        ):
            self.assertEqual(_recipients_from_env("POUPATEMPO"), ["a@x.com", "b@y.com"])

    @patch("prodesp.prodesp.blueprint.agendamento_csv_notifier.send_graph_html_email")
    def test_enviar_email_certificados_usa_acronimo_e_cc(self, mock_send):
        from prodesp.prodesp.caderno.certificado_export_service import _enviar_email_certificados
        from prodesp.prodesp.caderno.fgt_cert_exporter import CertExportItem

        mock_send.return_value = True
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "Fortinet_CA_SSL.cer")
            with open(path, "wb") as handle:
                handle.write(b"cert")
            result = CertExportResult(
                ok=True,
                hostname="fw-sp-001",
                acronimo="POUPATEMPO",
                items=[
                    CertExportItem(
                        cert_name="Fortinet_CA_SSL",
                        ok=True,
                        filename="Fortinet_CA_SSL.cer",
                        path_interno=path,
                    )
                ],
            )
            env = {
                "PRODESP_CERTIFICADO_EMAIL_TO_ACRONIMOS": (
                    "POUPATEMPO=daniel@apoio.gov.br;DER=tana@apoio.gov.br"
                ),
                "PRODESP_CERTIFICADO_EMAIL_TO": "fallback@telefonica.com",
                "PRODESP_CERTIFICADO_EMAIL_CC": "caq@telefonica.com",
                "PRODESP_CERTIFICADO_EMAIL_ATTACH": "zip",
            }
            with patch.dict(os.environ, env, clear=False):
                ok, msg = _enviar_email_certificados(result, unidade={})
        self.assertTrue(ok, msg)
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["recipients"], ["daniel@apoio.gov.br"])
        self.assertEqual(kwargs["cc_recipients"], ["caq@telefonica.com"])

    def test_build_certificado_email_corporativo(self):
        from prodesp.prodesp.caderno.certificado_export_service import (
            build_certificado_email_html,
            build_certificado_email_subject,
        )
        from prodesp.prodesp.caderno.fgt_cert_exporter import CertExportItem, CertExportResult

        result = CertExportResult(
            ok=True,
            hostname="fw-sp-001",
            acronimo="DIPOL",
            loopback_ip="10.254.6.39",
            elapsed_seconds=42.1,
            items=[
                CertExportItem(
                    cert_name="Fortinet_CA_SSL",
                    ok=True,
                    filename="Fortinet_CA_SSL.cer",
                    metodo="CLI SSH (show full-configuration)",
                )
            ],
        )
        unidade = {
            "id_vgr_unidades": "1234567",
            "id_intragov_unidades": "IG-9988",
            "nome_unidades": "Unidade Teste",
            "ip_lan_01_unidades": "10.1.1.1/29",
        }
        subject = build_certificado_email_subject(result, unidade)
        body = build_certificado_email_html(result, unidade)
        self.assertIn("VGR 1234567", subject)
        self.assertIn("DIPOL", subject)
        self.assertIn("CAQ - AIOPS", body)
        self.assertIn("ID VGR", body)
        self.assertIn("1234567", body)
        self.assertIn("ID Intragov", body)
        self.assertIn("IG-9988", body)
        self.assertIn("LAN 01", body)
        self.assertIn(".zip", body)

    def test_preparar_anexos_certificado_zip(self):
        import tempfile

        from prodesp.prodesp.caderno.certificado_export_service import _preparar_anexos_certificado
        from prodesp.prodesp.caderno.fgt_cert_exporter import CertExportItem

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "Fortinet_CA_SSL.cer")
            with open(path, "wb") as handle:
                handle.write(b"test-cert")
            with patch.dict(os.environ, {"PRODESP_CERTIFICADO_EMAIL_ATTACH": "zip"}, clear=False):
                atts = _preparar_anexos_certificado(
                    [
                        CertExportItem(
                            cert_name="Fortinet_CA_SSL",
                            ok=True,
                            filename="Fortinet_CA_SSL.cer",
                            path_interno=path,
                        )
                    ]
                )
            self.assertEqual(len(atts), 1)
            self.assertEqual(atts[0]["name"], "Fortinet_CA_SSL.zip")
            self.assertEqual(atts[0]["contentType"], "application/zip")

    @patch("prodesp.prodesp.caderno.fgt_cert_exporter.exportar_certificados_fgt")
    @patch("prodesp.prodesp.caderno.certificado_export_service.carregar_contexto_atendimento")
    def test_exportar_atendimento_sem_loopback(self, mock_ctx, mock_export):
        from prodesp.prodesp.caderno.certificado_export_service import exportar_certificados_atendimento

        mock_ctx.return_value = {"unidade": {"loopback_vivo_unidades": ""}}
        conn = MagicMock()
        cursor = MagicMock()
        out = exportar_certificados_atendimento(
            cursor, conn, 99, enviar_email=False, registrar_auditoria=False
        )
        self.assertFalse(out["ok"])
        mock_export.assert_not_called()

    @patch("prodesp.prodesp.caderno.certificado_export_service._enviar_email_certificados")
    @patch("prodesp.prodesp.caderno.certificado_export_service.exportar_certificados_fgt")
    @patch("prodesp.prodesp.caderno.certificado_export_service.carregar_contexto_atendimento")
    @patch("prodesp.prodesp.caderno.certificado_export_service.registrar_log")
    def test_exportar_atendimento_sucesso(self, mock_log, mock_ctx, mock_export, mock_email):
        from prodesp.prodesp.caderno.certificado_export_service import exportar_certificados_atendimento
        from prodesp.prodesp.caderno.fgt_cert_exporter import CertExportItem

        mock_ctx.return_value = {
            "unidade": {
                "loopback_vivo_unidades": "10.0.0.1",
                "acronimo_unidades": "DIPOL",
                "hostname_unidades": "FW-SP-001",
            }
        }
        mock_export.return_value = CertExportResult(
            ok=True,
            hostname="FW-SP-001",
            acronimo="DIPOL",
            loopback_ip="10.0.0.1",
            items=[
                CertExportItem(
                    cert_name="Cert_SSLVPN",
                    ok=True,
                    filename="x.p12",
                    path_interno="/tmp/x.p12",
                    path_externo="",
                )
            ],
        )
        mock_email.return_value = (True, "")
        conn = MagicMock()
        cursor = MagicMock()
        out = exportar_certificados_atendimento(cursor, conn, 1)
        self.assertTrue(out["ok"])
        mock_log.assert_called_once()
        conn.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
