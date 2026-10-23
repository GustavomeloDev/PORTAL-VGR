"""Testes unitários — caderno de teste PRODESP (sem SSH).

Rodar (na raiz do repo, venv ativo):

    .venv_portal_pessoal\\Scripts\\python.exe -m pytest prodesp/prodesp/caderno/test_caderno_prodesp.py -q
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from typing import Any

from prodesp.prodesp.caderno.fgt_command_registry import comandos_para_acronimo
from prodesp.prodesp.caderno.fgt_model_interfaces import (
    interface_wan_internet,
    interfaces_show_por_modelo,
)
from prodesp.prodesp.caderno.gerador_caderno_prodesp import (
    _parse_logs_por_comando,
    gerar_caderno_prodesp,
)

# PNG 1x1 transparente
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class TestCadernoProdesp(unittest.TestCase):
    def test_comandos_todos_acronimos(self):
        cmds = comandos_para_acronimo("DIPOL")
        self.assertIn("get sys status", cmds)
        self.assertEqual(cmds[0], "get sys status")
        self.assertIn("exec dhcp lease-list", cmds)
        self.assertIn("show firewall policy", cmds)
        self.assertIn("show sys interface", cmds)
        self.assertIn("diagnose sys sdwan service4", cmds)
        self.assertIn("get sys arp", cmds)

    def test_parse_get_sys_status_resumo(self):
        from prodesp.prodesp.caderno.fgt_sys_status import (
            montar_resumo_sys_status,
            parse_get_sys_status,
        )

        raw = """
Version: FortiGate-40F v7.4.11,build2878,260126 (GA.M)
First GA patch build date: 230509
Serial-Number: FGT40FTK2409D6QK
BIOS version: 05000100
Hostname: sap-spk-c1-c2-id-00309472
Operation Mode: NAT
"""
        parsed = parse_get_sys_status(raw)
        self.assertEqual(parsed["version"], "FortiGate-40F v7.4.11")
        self.assertEqual(parsed["serial"], "FGT40FTK2409D6QK")
        self.assertEqual(parsed["hostname"], "sap-spk-c1-c2-id-00309472")
        resumo = montar_resumo_sys_status(parsed)
        self.assertIn("Version do equipamento: FortiGate-40F v7.4.11", resumo)
        self.assertIn("Número de Serie: FGT40FTK2409D6QK", resumo)
        self.assertIn("Hostname: sap-spk-c1-c2-id-00309472", resumo)

    def test_interfaces_fgt80(self):
        ifaces = interfaces_show_por_modelo("FGT-81F")
        self.assertIn("wan", ifaces)
        self.assertIn("lan3", ifaces)
        self.assertEqual(interface_wan_internet("FGT-81F"), "wan")

    def test_parse_logs_ultima_ocorrencia(self):
        raw = "--- get sys ha status ---\nv1\n--- get sys ha status ---\nv2"
        parsed = _parse_logs_por_comando(raw)
        self.assertEqual(parsed["get sys ha status"], "v2")

    def test_gerar_caderno_minimo(self):
        from prodesp.prodesp.caderno import gerador_caderno_prodesp as gen

        modelo = gen._modelo_path("openpyxl")
        if not os.path.isfile(modelo):
            self.skipTest("Template v3 (.xlsx ou .xlsm) não presente no workspace")
        if os.path.getsize(modelo) < 400_000:
            self.skipTest(
                "Template parece corrompido (tamanho reduzido). "
                "Restaure MULTI-OES_CADERNO_DE_TESTE_ROLLOUT.v3.xlsx ou .xlsm original."
            )

        dados = {
            "unidade": {
                "id_vgr_unidades": "TEST999",
                "acronimo_unidades": "TST",
                "nome_unidades": "Unidade Teste",
                "localidade_unidades": "Sao Paulo/SP",
                "topologia_unidades": "SD-WAN",
                "modelo_solucao_unidades": "G",
                "hostname_unidades": "fgt-test",
                "loopback_vivo_unidades": "10.0.0.1",
                "id_intragov_unidades": "IG999",
            },
            "equipamentos": [{"modelo_equipamentos": "FGT-81F", "serial_equipamentos": "FG81FTEST"}],
            "links": [
                {
                    "tipo_links": "STATIC",
                    "id_vgr_links": "111",
                    "velocidade_links": "100",
                    "ip_wan_links": "187.1.1.1/31",
                    "ip_gateway_links": "187.1.1.0",
                },
                {
                    "tipo_links": "MPLS",
                    "id_vgr_links": "222",
                    "velocidade_links": "10",
                    "ip_wan_links": "10.1.1.1/29",
                    "ip_gateway_links": "10.1.1.0",
                },
            ],
            "questionario": {
                "dhcp_server": "NÃO",
                "dhcp_relay": "NÃO",
                "vlan": "SIM",
                "multi_ip_lan": "NÃO",
                "voip_tipo": "N/A",
                "status_testes": {
                    str(r): (
                        "✔️ Concluido" if r == 40 else "⚠️Pendente"
                    )
                    for r in range(40, 50)
                },
            },
        }
        logs = (
            "--- get sys ha status ---\nHA: active\n"
            "--- show sys interface wan ---\nwan up\n"
            "--- diagnose sys sip-proxy calls ---\nsip-proxy ok"
        )
        with tempfile.TemporaryDirectory() as tmp:
            orig_gerados = gen.GERADOS_DIR
            try:
                gen.GERADOS_DIR = tmp
                paths = gerar_caderno_prodesp(
                    dados,
                    logs_text=logs,
                    imagem_esaq_b64=f"data:image/png;base64,{_TINY_PNG_B64}",
                    pasta_rede="",
                )
                self.assertTrue(os.path.isfile(paths.local))
                self.assertTrue(
                    paths.local.endswith(".xlsx") or paths.local.endswith(".xlsm"),
                    paths.local,
                )
            finally:
                gen.GERADOS_DIR = orig_gerados

    def test_validar_status_testes(self):
        from prodesp.prodesp.caderno.caderno_teste_service import validar_status_testes

        ok, _ = validar_status_testes({})
        self.assertFalse(ok)
        ok, _ = validar_status_testes({str(r): "⚠️Pendente" for r in range(40, 50)})
        self.assertTrue(ok)

    def test_montar_texto_carimbo_from_logs(self):
        from prodesp.prodesp.caderno.carimbo_noc_export import montar_texto_carimbo_from_logs

        raw = (
            "--- get sys ha status ---\nHA: active\n"
            "--- show sys interface wan ---\nwan up\n"
            "--- get sys fortiguard-service status ---\nFortiGuard OK"
        )
        texto = montar_texto_carimbo_from_logs(raw)
        self.assertIn("get sys fortiguard-service status", texto)
        self.assertIn("FortiGuard OK", texto)
        self.assertIn("get sys ha status", texto)
        self.assertIn("\n\n", texto)
        self.assertNotIn("\n\n\n", texto)

    def test_montar_texto_carimbo_completo_inclui_cabecalho(self):
        from prodesp.prodesp.caderno.carimbo_noc_export import montar_texto_carimbo_completo

        texto = montar_texto_carimbo_completo(
            unidade={
                "id_intragov_unidades": "00315767/26",
                "id_vgr_unidades": "2100577",
                "acronimo_unidades": "SDE",
                "nome_unidades": "SECRETARIA DE DESENVOLVIMENTO ECONOMICO",
                "localidade_unidades": "JAGUARIUNA/SP",
                "hostname_unidades": "sde-spk-c1-c2-id-00315767",
                "loopback_vivo_unidades": "10.254.1.230",
            },
            equipamentos=[{"modelo_equipamentos": "FGT-40F", "serial_equipamentos": "FGT40FTK2403D5AL"}],
            links=[
                {
                    "tipo_links": "STATIC",
                    "designador_links": "SAI-BL",
                    "id_vgr_links": "2161664",
                    "ip_wan_links": "179.0.127.150",
                    "ip_gateway_links": "179.0.127.149",
                    "ip_mascara_links": "255.255.255.252",
                    "velocidade_links": "30",
                },
                {
                    "tipo_links": "MPLS",
                    "designador_links": "SCM",
                    "id_vgr_links": "1516607",
                    "ip_wan_links": "10.250.13.206",
                    "ip_gateway_links": "10.250.13.201",
                    "ip_mascara_links": "255.255.255.248",
                    "velocidade_links": "4",
                },
            ],
            questionario={"dhcp_server": "NÃO", "dhcp_relay": "NÃO", "vlan": "NÃO", "multi_ip_lan": "NÃO"},
            logs_text="--- get sys fortiguard-service status ---\nFortiGuard OK\n",
        )
        self.assertIn("CARIMBO - SDWAN", texto)
        self.assertIn("ID SDWAN-VTV", texto)
        self.assertIn("2100577", texto)
        self.assertIn("Conectividade SAI-BL", texto)
        self.assertIn("Conectividade SCM", texto)
        self.assertIn("IP WAN:\t179.0.127.150/30", texto)

    def test_compactar_linhas_em_branco(self):
        from prodesp.prodesp.caderno.carimbo_noc_export import _compactar_linhas_em_branco

        self.assertEqual(_compactar_linhas_em_branco("a\n\n\n\nb"), "a\n\nb")
        self.assertEqual(_compactar_linhas_em_branco("a\n\nb"), "a\n\nb")

    def test_gerar_sem_esaq_falha(self):
        with self.assertRaises(ValueError):
            gerar_caderno_prodesp({"unidade": {}}, imagem_esaq_b64="")

    def test_resolve_pasta_rede_caderno(self):
        from prodesp.config_paths import resolve_pasta_rede_caderno, sanitize_pasta_acronimo

        with tempfile.TemporaryDirectory() as base:
            dest = resolve_pasta_rede_caderno("DIPOL", base_override=base)
            self.assertTrue(dest.endswith(os.path.join("DIPOL")))
            self.assertEqual(sanitize_pasta_acronimo("  SDE/SP  "), "SDE_SP")

    def test_copia_rede_por_acronimo(self):
        from prodesp.prodesp.caderno import gerador_caderno_prodesp as gen

        with tempfile.TemporaryDirectory() as tmp:
            local = os.path.join(tmp, "local")
            os.makedirs(local, exist_ok=True)
            src = os.path.join(local, "caderno.xlsm")
            with open(src, "wb") as f:
                f.write(b"x")
            with tempfile.TemporaryDirectory() as rede_base:
                rede = gen._copiar_caderno_para_rede(
                    src, "TST", pasta_rede_base=rede_base
                )
                self.assertIsNotNone(rede)
                self.assertTrue(os.path.isfile(rede))
                self.assertIn("TST", rede)

    def test_copia_rede_usa_fallback_se_principal_falhar(self):
        from prodesp.prodesp.caderno import gerador_caderno_prodesp as gen

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "caderno.xlsm")
            with open(src, "wb") as f:
                f.write(b"x")
            principal_file = os.path.join(tmp, "nao_e_pasta")
            with open(principal_file, "wb") as f:
                f.write(b"x")
            fallback = os.path.join(tmp, "fallback")
            os.makedirs(fallback, exist_ok=True)
            with unittest.mock.patch(
                "prodesp.config_paths.list_prodesp_path_candidates",
                return_value=[principal_file, fallback],
            ):
                rede = gen._copiar_caderno_para_rede(src, "TST")
            self.assertIsNotNone(rede)
            self.assertTrue(os.path.isfile(rede))
            self.assertIn(os.path.join("fallback", "TST"), rede)

    def test_gerar_portal_indisponivel_sem_duas_imagens_falha(self):
        with self.assertRaises(ValueError):
            gerar_caderno_prodesp(
                {"unidade": {}},
                portal_banda_larga_ok=False,
                imagem_erro_bbl_b64="",
                imagem_speedtest_b64="",
            )

    def test_texto_portal_indisponivel_definido(self):
        from prodesp.prodesp.caderno.caderno_template_map import ESAQ_PORTAL_INDISPONIVEL_TEXTO

        self.assertIn("Brasil Banda Larga", ESAQ_PORTAL_INDISPONIVEL_TEXTO)
        self.assertIn("Speedtest by Ookla", ESAQ_PORTAL_INDISPONIVEL_TEXTO)

    def test_extrair_arp_por_interface(self):
        from prodesp.prodesp.caderno.caderno_interface_resolver import extrair_arp_por_interface

        body = (
            "Address           Age(min)   Hardware Addr      Interface\n"
            "10.250.56.65      0          ec:9b:8b:5d:44:9a lan3\n"
            "189.44.60.253     0          a8:4f:b1:12:a9:a6 wan\n"
        )
        arp = extrair_arp_por_interface({"get sys arp": body})
        self.assertEqual(arp.get("lan3"), ["10.250.56.65"])
        self.assertEqual(arp.get("wan"), ["189.44.60.253"])

    def test_extrair_ips_interfaces_logs_show_sem_physical(self):
        from prodesp.prodesp.caderno.caderno_interface_resolver import extrair_ips_interfaces_logs

        por_cmd = {
            "show sys interface": (
                'config system interface\n'
                '    edit "lan3"\n'
                '        set ip 10.250.56.66 255.255.255.248\n'
                "    next\n"
                "end\n"
            ),
        }
        ips = extrair_ips_interfaces_logs(por_cmd)
        self.assertEqual(ips.get("lan3"), "10.250.56.66/29")

    def test_carimbo_ip_wan_remoto_cidr(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import format_carimbo_ip_wan_remoto

        link = {
            "ip_wan_links": "189.109.189.201",
            "ip_gateway_links": "189.109.189.200",
            "ip_mascara_links": "255.255.255.252",
        }
        ip_wan, remoto = format_carimbo_ip_wan_remoto(link)
        self.assertEqual(ip_wan, "189.109.189.201/30")
        self.assertEqual(remoto, "189.109.189.200")

    def test_carimbo_ip_wan_mpls_cadastro_sem_log_unidade_1417(self):
        """Regressão: /29 não deve usar host superior (.70); ip_wan_links é .66."""
        from prodesp.prodesp.caderno.caderno_carimbo_links import format_carimbo_ip_wan_remoto

        link = {
            "ip_wan_links": "10.250.56.66",
            "ip_gateway_links": "10.250.56.65",
            "ip_mascara_links": "255.255.255.248",
        }
        ip_wan, remoto = format_carimbo_ip_wan_remoto(link)
        self.assertEqual(ip_wan, "10.250.56.66/29")
        self.assertEqual(remoto, "10.250.56.65")

    def test_carimbo_ip_wan_mpls_log_show_interface_unidade_1417(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import format_carimbo_ip_wan_remoto

        link = {
            "id_vgr_links": "1746360",
            "ip_wan_links": "10.250.56.66",
            "ip_gateway_links": "10.250.56.65",
            "ip_mascara_links": "255.255.255.248",
        }
        ip_wan, remoto = format_carimbo_ip_wan_remoto(
            link,
            ip_interface_log="10.250.56.66/29",
            arp_neighbors=["10.250.56.65"],
        )
        self.assertEqual(ip_wan, "10.250.56.66/29")
        self.assertEqual(remoto, "10.250.56.65")

    def test_carimbo_ip_wan_static_log_wan_unidade_1417(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import format_carimbo_ip_wan_remoto

        link = {
            "ip_wan_links": "189.44.60.254",
            "ip_gateway_links": "189.44.60.253",
            "ip_mascara_links": "255.255.255.252",
        }
        ip_wan, remoto = format_carimbo_ip_wan_remoto(
            link,
            ip_interface_log="189.44.60.254/30",
            arp_neighbors=["189.44.60.253"],
        )
        self.assertEqual(ip_wan, "189.44.60.254/30")
        self.assertEqual(remoto, "189.44.60.253")

    def test_carimbo_ip_wan_remoto_mpls_dupla_validacao(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import format_carimbo_ip_wan_remoto

        link = {
            "ip_wan_links": "10.250.55.42",
            "ip_gateway_links": "10.250.55.41",
            "ip_mascara_links": "255.255.255.248",
        }
        ip_wan, remoto = format_carimbo_ip_wan_remoto(link, ip_interface_log="10.250.55.42/29")
        self.assertEqual(ip_wan, "10.250.55.42/29")
        self.assertEqual(remoto, "10.250.55.41")

    def test_carimbo_ip_wan_log_prevalece_quando_diverge_cadastro(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import format_carimbo_ip_wan_remoto

        link = {
            "ip_wan_links": "10.250.55.42",
            "ip_gateway_links": "10.250.55.41",
            "ip_mascara_links": "255.255.255.248",
        }
        ip_wan, remoto = format_carimbo_ip_wan_remoto(link, ip_interface_log="10.250.56.70/29")
        self.assertEqual(ip_wan, "10.250.56.70/29")
        self.assertEqual(remoto, "10.250.56.65")

    def test_carimbo_ip_wan_static_31_com_log(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import format_carimbo_ip_wan_remoto

        link = {
            "ip_wan_links": "189.108.21.253",
            "ip_gateway_links": "189.108.21.252",
            "ip_mascara_links": "255.255.255.254",
        }
        ip_wan, remoto = format_carimbo_ip_wan_remoto(link, ip_interface_log="189.108.21.253/31")
        self.assertEqual(ip_wan, "189.108.21.253/31")
        self.assertEqual(remoto, "189.108.21.252")

    def test_sai_bli_vazio_nao_inserir(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import (
            deve_exibir_bloco_sai_bli_no_carimbo,
            deve_inserir_bloco_sai_bli,
        )

        self.assertFalse(deve_inserir_bloco_sai_bli({}))
        self.assertFalse(deve_inserir_bloco_sai_bli({"id_vgr_links": "N/A"}))
        self.assertFalse(
            deve_exibir_bloco_sai_bli_no_carimbo(
                {
                    "interface": "a",
                    "circuito": "N/A",
                    "id_vantive": "N/A",
                    "description": "N/A__N/A_",
                }
            )
        )
        self.assertTrue(
            deve_exibir_bloco_sai_bli_no_carimbo(
                {
                    "interface": "a",
                    "circuito": "SAI-BLI",
                    "id_vantive": "999",
                    "velocidade": "10Mb",
                    "description": "SAI-BLI_INET2_999_10",
                    "ip_wan": "1.1.1.1/30",
                }
            )
        )

    def test_copiar_carimbo_omite_sai_bli_vazio(self):
        from prodesp.prodesp.caderno.carimbo_noc_export import extrair_texto_carimbo_coluna_e

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "static",
            "caderno_teste",
            "gerados",
            "DIPOL_ID_VGR_2177791_ID_INTRAGOV_00333169-26.xlsm",
        )
        if not os.path.isfile(path):
            self.skipTest("caderno gerado de referência ausente")
        texto = extrair_texto_carimbo_coluna_e(path)
        self.assertIn("Conectividade SAI-BL", texto)
        self.assertIn("Conectividade SCM", texto)
        self.assertNotIn("Conectividade SAI-BLI", texto)
        self.assertNotIn("CIRCUITO: N/A", texto)

    def test_nome_arquivo_caderno(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import nome_arquivo_caderno

        nome = nome_arquivo_caderno(
            {
                "acronimo_unidades": "PCSPO",
                "id_vgr_unidades": "2194308",
                "id_intragov_unidades": "00309492/26",
            }
        )
        self.assertEqual(nome, "PCSPO_ID_VGR_2194308_ID_INTRAGOV_00309492-26")

    def test_velocidade_carimbo_mb(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import format_velocidade_carimbo

        self.assertEqual(format_velocidade_carimbo("50"), "50Mb")

    def test_validar_questionario_obrigatorio(self):
        from prodesp.prodesp.caderno.caderno_teste_service import validar_questionario_obrigatorio

        ok, _ = validar_questionario_obrigatorio({"dhcp_server": "SIM"})
        self.assertFalse(ok)
        ok, _ = validar_questionario_obrigatorio(
            {
                "dhcp_server": "NÃO",
                "dhcp_relay": "NÃO",
                "vlan": "SIM",
                "multi_ip_lan": "NÃO",
                "voip_tipo": "N/A",
            }
        )
        self.assertTrue(ok)

    def test_coleta_usa_show_sys_interface_completo(self):
        cmds = comandos_para_acronimo("DIPOL")
        self.assertIn("show sys interface", cmds)
        self.assertFalse(any(c.startswith("show sys interface ") for c in cmds))

    def test_show_sys_interface_completo_por_description(self):
        from prodesp.prodesp.caderno.caderno_interface_resolver import (
            extrair_aliases_show_interface,
            extrair_ips_show_interface_completo,
            montar_show_interface_parts_para_carimbo,
        )

        body = (
            'config system interface\n'
            '    edit "wan"\n'
            '        set ip 189.109.189.201 255.255.255.254\n'
            '        set description "SAI-BL_INET1_2163125_50Mb"\n'
            '        set alias "INET1"\n'
            "    next\n"
            '    edit "lan3"\n'
            '        set ip 10.250.11.226 255.255.255.248\n'
            '        set description "SCM_MPLS1_1277551_8Mb"\n'
            '        set alias "MPLS-1"\n'
            "    next\n"
            '    edit "a"\n'
            '        set alias "INET2"\n'
            "    next\n"
            "end\n"
        )
        por_cmd = {"show sys interface": body}
        aliases = extrair_aliases_show_interface(por_cmd)
        self.assertIn("SAI-BL", aliases.get("wan", "").upper())
        self.assertIn("SCM", aliases.get("lan3", "").upper())
        self.assertEqual(aliases.get("a"), "INET2")

        ips = extrair_ips_show_interface_completo(body)
        self.assertEqual(ips.get("lan3"), "10.250.11.226/29")

        parts = montar_show_interface_parts_para_carimbo(por_cmd, ("wan", "lan3"))
        self.assertEqual(len(parts), 2)
        self.assertIn('edit "wan"', parts[0])
        self.assertIn('edit "lan3"', parts[1])

    def test_resolver_interface_scm_por_alias(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import resolver_links_carimbo
        from prodesp.prodesp.caderno.caderno_interface_resolver import (
            extrair_aliases_show_interface,
            resolver_interface_por_alias,
            resolver_interfaces_carimbo,
        )

        logs = {
            "show sys interface wan": 'set alias "SAI-BL_INET1_2163125_50"\n',
            "show sys interface lan3": 'set alias "SCM_MPLS1_1277551_8"\n',
            "show sys interface a": 'set alias "OUTRO"\n',
        }
        aliases = extrair_aliases_show_interface(logs)
        iface = resolver_interface_por_alias(
            aliases,
            marcadores=("SCM", "MPLS1"),
            descricao="SCM_MPLS1_1277551_8",
            fallback="a",
            excluir={"wan"},
        )
        self.assertEqual(iface, "lan3")

    def test_dipol_2177791_interfaces_por_log(self):
        """Cenário real FGT-40F: SCM em lan3 (physical), não em 'a'."""
        from prodesp.prodesp.caderno.caderno_carimbo_links import resolver_links_carimbo
        from prodesp.prodesp.caderno.caderno_interface_resolver import (
            extrair_aliases_show_interface,
            extrair_ips_interface_physical,
            resolver_interfaces_carimbo,
        )

        por_cmd = {
            "show sys interface": (
                'config system interface\n'
                '    edit "wan"\n'
                '        set description "SAI-BL_INET1_2163125_50Mb"\n'
                '        set alias "INET1"\n'
                "    next\n"
                '    edit "lan3"\n'
                '        set ip 10.250.11.226 255.255.255.248\n'
                '        set description "SCM_MPLS1_1277551_8Mb"\n'
                '        set alias "MPLS-1"\n'
                "    next\n"
                '    edit "a"\n'
                '        set alias "INET2"\n'
                "    next\n"
                "end\n"
            ),
            "get sys interface physical": (
                "== [onboard]\n\t==[lan3]\n\t\tip: 10.250.11.226 255.255.255.248\n"
                "\t==[wan]\n\t\tip: 189.109.189.201 255.255.255.254\n"
            ),
        }
        aliases = extrair_aliases_show_interface(por_cmd)
        self.assertIn("SAI-BL", aliases.get("wan", "").upper())
        ips = extrair_ips_interface_physical(por_cmd)
        self.assertEqual(ips.get("lan3"), "10.250.11.226/29")

        links = [
            {
                "tipo_links": "STATIC",
                "designador_links": "LP_SAI-BL",
                "id_vgr_links": "2163125",
                "velocidade_links": "50",
                "ip_wan_links": "189.109.189.201",
                "ip_mascara_links": "255.255.255.254",
            },
            {
                "tipo_links": "MPLS",
                "designador_links": "LP_SCM",
                "id_vgr_links": "1277551",
                "velocidade_links": "8",
                "ip_wan_links": "10.250.11.230",
                "ip_mascara_links": "255.255.255.248",
            },
        ]
        links_res = resolver_links_carimbo(links)
        ifaces = resolver_interfaces_carimbo(aliases, links_res, "FGT-40F", por_cmd)
        self.assertEqual(ifaces["sai_bl"], "wan")
        self.assertEqual(ifaces["scm"], "lan3")
        self.assertNotIn("sai_bli", ifaces)

    def test_resolver_interfaces_tres_links(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import resolver_links_carimbo
        from prodesp.prodesp.caderno.caderno_interface_resolver import (
            extrair_aliases_show_interface,
            resolver_interfaces_carimbo,
        )

        logs = {
            "show sys interface wan": 'set alias "SAI-BL_INET1_2163125_50"\n',
            "show sys interface lan3": 'set alias "SCM_MPLS1_1277551_8"\n',
            "show sys interface a": 'set alias "SAI-BLI_INET2_999_10"\n',
        }
        aliases = extrair_aliases_show_interface(logs)
        links = [
            {
                "tipo_links": "STATIC",
                "designador_links": "LP_SAI-BL",
                "id_vgr_links": "2163125",
                "velocidade_links": "50",
            },
            {
                "tipo_links": "STATIC",
                "designador_links": "LP_SAI-BLI",
                "id_vgr_links": "999",
                "velocidade_links": "10",
                "ip_wan_links": "1.1.1.1",
            },
            {
                "tipo_links": "MPLS",
                "designador_links": "LP_SCM",
                "id_vgr_links": "1277551",
                "velocidade_links": "8",
            },
        ]
        links_res = resolver_links_carimbo(links)
        ifaces = resolver_interfaces_carimbo(aliases, links_res, "FGT-81F")
        self.assertEqual(ifaces["sai_bl"], "wan")
        self.assertEqual(ifaces["scm"], "lan3")
        self.assertEqual(ifaces["sai_bli"], "a")

    def test_sai_bl_nao_casa_sai_bli(self):
        from prodesp.prodesp.caderno.caderno_interface_resolver import _marcador_casa_alias

        self.assertTrue(_marcador_casa_alias("SAI-BL", "SAI-BL_INET1_1_50"))
        self.assertFalse(_marcador_casa_alias("SAI-BL", "SAI-BLI_INET2_1_10"))
        self.assertTrue(_marcador_casa_alias("SAI-BLI", "SAI-BLI_INET2_1_10"))

    def test_resolver_interface_exclui_ja_usada(self):
        from prodesp.prodesp.caderno.caderno_interface_resolver import (
            extrair_aliases_show_interface,
            resolver_interface_por_alias,
        )

        logs = {
            "show sys interface a": 'set alias "SCM_MPLS1_1277551_8"\n',
            "show sys interface lan3": 'set alias "SCM_MPLS1_1277551_8"\n',
        }
        aliases = extrair_aliases_show_interface(logs)
        iface = resolver_interface_por_alias(
            aliases,
            marcadores=("SCM",),
            fallback="a",
            excluir={"a"},
        )
        self.assertEqual(iface, "lan3")

    def test_link_scm_por_designador(self):
        from prodesp.prodesp.caderno.caderno_carimbo_links import link_scm

        links = [
            {"tipo_links": "MPLS", "designador_links": "LP_OUTRO", "id_vgr_links": "1"},
            {"tipo_links": "STATIC", "designador_links": "LP_SCM", "id_vgr_links": "2"},
        ]
        scm = link_scm(links)
        self.assertEqual(scm.get("id_vgr_links"), "2")

    def test_parse_show_sys_admin_help(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import (
            admin_existe_na_caixa,
            parse_usuarios_show_sys_admin,
        )

        raw = (
            "name    User name.\n"
            "admin\n"
            "tacacs-admin\n"
            "tacacs-read-only\n"
            "vvita\n"
        )
        users = parse_usuarios_show_sys_admin(raw)
        self.assertEqual(users, {"admin", "tacacs-admin", "tacacs-read-only", "vvita"})
        self.assertNotIn("end", users)
        self.assertNotIn("next", users)
        self.assertTrue(admin_existe_na_caixa(raw))

    def test_parse_show_sys_admin_config_ignora_next_end(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import parse_usuarios_show_sys_admin

        raw = (
            "config system admin\n"
            '    edit "admin"\n'
            "        set accprofile super_admin\n"
            "    next\n"
            '    edit "vvita"\n'
            "    next\n"
            "end\n"
        )
        users = parse_usuarios_show_sys_admin(raw)
        self.assertEqual(users, {"admin", "vvita"})
        self.assertNotIn("end", users)
        self.assertNotIn("next", users)

    def test_parse_show_sys_admin_config_completo(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import (
            admin_existe_na_caixa,
            parse_usuarios_show_sys_admin,
        )

        raw = (
            "config system admin\n"
            '    edit "tacacs-admin"\n'
            "        set remote-auth enable\n"
            "    next\n"
            '    edit "admin"\n'
            "        set accprofile super_admin\n"
            "    next\n"
            "end\n"
        )
        users = parse_usuarios_show_sys_admin(raw)
        self.assertIn("admin", users)
        self.assertIn("tacacs-admin", users)
        self.assertNotIn("end", users)
        self.assertNotIn("next", users)
        self.assertTrue(admin_existe_na_caixa(raw))
        self.assertNotIn("tacacs-admin", {"admin"})

    def test_parse_admin_status_logado(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import admin_esta_logado

        raw = (
            "Logged in users: 2\n"
            "USERNAME        TYPE    FROM             TIME\n"
            "vvita           ssh     172.20.0.10      Sun Jun 21 11:53:34 2026\n"
            "admin           ssh     172.20.0.10      Sun Jun 21 12:11:13 2026\n"
        )
        self.assertTrue(admin_esta_logado(raw))
        self.assertFalse(
            admin_esta_logado(
                "Logged in users: 1\nUSERNAME TYPE FROM TIME\nvvita ssh 172.20.0.10 Sun\n"
            )
        )

    def test_parse_disconnect_admin_indexes(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import parse_indexes_admin_disconnect

        raw = (
            "Currently connected admins:\n"
            "INDEX USERNAME        TYPE    VDOM     PROFILE      FROM             TIME\n"
            "   0 vvita           ssh     root     super_admin  172.20.0.10      Sun\n"
            "   1 admin           ssh     root     super_admin  172.20.0.10      Sun\n"
            "   3 admin           ssh     root     super_admin  172.20.0.10      Sun\n"
        )
        self.assertEqual(parse_indexes_admin_disconnect(raw), [1, 3])

    def test_interpretar_saida_delete_admin_vazio_eh_sucesso(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import interpretar_saida_delete_admin

        ok, msg = interpretar_saida_delete_admin("")
        self.assertTrue(ok)
        self.assertIn("OK", msg)
        self.assertIn("não ecoa", msg.lower())

    def test_limpeza_admin_fluxo_condicional(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import executar_limpeza_admin_fgt

        calls: list[str] = []
        show_help_n = {"n": 0}

        def exec_help(partial: str, label: str) -> str:
            calls.append(label)
            if partial == "show sys admin":
                show_help_n["n"] += 1
                if show_help_n["n"] == 1:
                    return "admin\nvvita\n"
                return "vvita\n"
            if partial == "execute disconnect-admin-session":
                return "   1 admin           ssh     root\n"
            return ""

        def exec_cmd(cmd: str) -> str:
            calls.append(cmd)
            if cmd == "get system info admin status":
                return (
                    "Logged in users: 1\n"
                    "USERNAME TYPE FROM TIME\n"
                    "admin ssh 172.20.0.10 Sun\n"
                )
            return "ok"

        delete_calls = {"n": 0}

        def exec_delete() -> str:
            delete_calls["n"] += 1
            calls.append("delete")
            return ""

        blocks, errors, n = executar_limpeza_admin_fgt(
            shell=object(),
            exec_help=exec_help,
            exec_cmd=exec_cmd,
            exec_config_delete=exec_delete,
        )
        self.assertEqual(errors, [])
        self.assertIn("execute disconnect-admin-session 1", calls)
        self.assertIn("get system info admin status", calls)
        self.assertEqual(delete_calls["n"], 1)
        self.assertGreater(n, 0)
        self.assertTrue(any("limpeza admin — resumo" in b for b in blocks))
        self.assertTrue(any("Verificação pós-delete: OK" in b for b in blocks))
        self.assertTrue(any("delete admin" in b for b in blocks))

    def test_limpeza_admin_sem_usuario_admin(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import executar_limpeza_admin_fgt

        calls: list[str] = []

        blocks, errors, n = executar_limpeza_admin_fgt(
            shell=object(),
            exec_help=lambda _p, _l: "vvita\n",
            exec_cmd=lambda cmd: calls.append(cmd) or (
                'edit "vvita"\n' if cmd == "show sys admin" else ""
            ),
            exec_config_delete=lambda: calls.append("delete") or "",
        )
        self.assertEqual(errors, [])
        self.assertEqual(calls, ["show sys admin"])
        self.assertTrue(any("não cadastrado" in b for b in blocks))

    def test_limpeza_admin_fallback_show_config(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import executar_limpeza_admin_fgt

        calls: list[str] = []

        def exec_help(partial: str, _label: str) -> str:
            calls.append(f"help:{partial}")
            if partial == "show sys admin":
                return "vvita\ntacacs-admin\n"
            return ""

        def exec_cmd(cmd: str) -> str:
            calls.append(cmd)
            if cmd == "show sys admin":
                return 'config system admin\n    edit "admin"\n        set accprofile "super_admin"\n    next\nend\n'
            if cmd == "get system info admin status":
                return "Logged in users: 0\n"
            return "ok"

        blocks, errors, n = executar_limpeza_admin_fgt(
            shell=object(),
            exec_help=exec_help,
            exec_cmd=exec_cmd,
            exec_config_delete=lambda: calls.append("delete") or "",
        )
        self.assertEqual(errors, [])
        self.assertIn("show sys admin", calls)
        self.assertIn("delete", calls)
        self.assertFalse(any("não cadastrado" in b for b in blocks))
        self.assertTrue(any("Verificação pós-delete: OK" in b for b in blocks))

    def test_limpeza_admin_retry_delete_logado(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import executar_limpeza_admin_fgt

        delete_attempts = {"n": 0}
        show_help_n = {"n": 0}

        def exec_delete() -> str:
            delete_attempts["n"] += 1
            if delete_attempts["n"] == 1:
                return "Cannot delete admin while 'admin' is logged in!\nCommand fail. Return code -14"
            return ""

        def exec_help(partial, _l):
            if partial == "show sys admin":
                show_help_n["n"] += 1
                return "admin\n" if show_help_n["n"] == 1 else "vvita\n"
            return "   1 admin           ssh\n"

        blocks, errors, _n = executar_limpeza_admin_fgt(
            shell=object(),
            exec_help=exec_help,
            exec_cmd=lambda cmd: (
                "Logged in users: 1\nUSERNAME TYPE FROM TIME\nadmin ssh 172.20.0.10 Sun\n"
                if cmd == "get system info admin status"
                else "ok"
            ),
            exec_config_delete=exec_delete,
        )
        self.assertEqual(delete_attempts["n"], 2)
        self.assertEqual(errors, [])


    def test_format_fgt_cli_help_command_exige_espaco_antes_interrogacao(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import format_fgt_cli_help_command

        self.assertEqual(format_fgt_cli_help_command("show sys admin"), "show sys admin ?")
        self.assertEqual(format_fgt_cli_help_command("show sys admin?"), "show sys admin ?")
        self.assertEqual(format_fgt_cli_help_command("show sys admin ?"), "show sys admin ?")
        self.assertEqual(format_fgt_cli_help_command("show sys admin  ?"), "show sys admin ?")
        self.assertEqual(
            format_fgt_cli_help_command("execute disconnect-admin-session"),
            "execute disconnect-admin-session ?",
        )
        self.assertEqual(
            format_fgt_cli_help_command("execute disconnect-admin-session?"),
            "execute disconnect-admin-session ?",
        )

    def test_substituir_bloco_remove_prefixo_legacy_ui(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import (
            sanitize_logs_atendimento_for_db,
            substituir_bloco_coleta_fgt,
        )

        existing = (
            "[—] —: --- COLETA FGT AUTO INÍCIO ---\n"
            "conteudo antigo\n"
            "--- COLETA FGT AUTO FIM ---"
        )
        out = substituir_bloco_coleta_fgt(existing, "FGT 10.0.0.1")
        self.assertFalse(out.startswith("[—]"))
        self.assertIn("FGT 10.0.0.1", out)
        self.assertTrue(out.startswith("--- COLETA FGT AUTO INÍCIO ---"))

    def test_sanitize_logs_remove_prefixo_em_qualquer_linha(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import sanitize_logs_atendimento_for_db

        raw = (
            "log manual\n\n"
            "[—] —: --- COLETA FGT AUTO INÍCIO ---\n"
            "corpo\n"
            "--- COLETA FGT AUTO FIM ---"
        )
        out = sanitize_logs_atendimento_for_db(raw)
        self.assertNotIn("[—] —:", out)
        self.assertIn("--- COLETA FGT AUTO INÍCIO ---", out)


class TestFmgDeviceList(unittest.TestCase):
    def test_id_intragov_remove_sufixo_e_completa_8_digitos(self):
        from prodesp.prodesp.caderno.fgt_command_registry import (
            comando_diag_dvm_device_list,
            id_intragov_para_grep_fmg,
        )

        self.assertEqual(id_intragov_para_grep_fmg("0309472/26"), "00309472")
        self.assertEqual(id_intragov_para_grep_fmg("00309472/26"), "00309472")
        self.assertEqual(id_intragov_para_grep_fmg("00315767/26"), "00315767")
        self.assertEqual(id_intragov_para_grep_fmg(" 307483 "), "00307483")
        self.assertEqual(
            comando_diag_dvm_device_list("00309472"),
            "diag dvm device list | grep -A 2 -if 00309472",
        )

    def test_id_invalido_nao_monta_comando(self):
        from prodesp.prodesp.caderno.fgt_command_registry import (
            comando_diag_dvm_device_list,
            id_intragov_para_grep_fmg,
        )

        self.assertEqual(id_intragov_para_grep_fmg(""), "")
        self.assertEqual(id_intragov_para_grep_fmg("IG999"), "")
        self.assertEqual(id_intragov_para_grep_fmg("0309472;id"), "")
        self.assertEqual(id_intragov_para_grep_fmg("00309472$(id)/26"), "")
        with self.assertRaises(ValueError):
            comando_diag_dvm_device_list("00309472;id")
        with self.assertRaises(ValueError):
            comando_diag_dvm_device_list("309472")

    def test_comando_fmg_nao_entra_na_whitelist_do_fortigate(self):
        cmds = comandos_para_acronimo("SAP")
        self.assertFalse(any("dvm device" in c for c in cmds))

    def test_bloco_fmg_fica_no_portal_e_sai_do_caderno(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import (
            FMG_PORTAL_ONLY_FIM,
            FMG_PORTAL_ONLY_INI,
            remover_bloco_fmg_portal,
            substituir_bloco_coleta_fgt,
        )
        from prodesp.prodesp.caderno.gerador_caderno_prodesp import _parse_logs_por_comando

        fgt = "--- get sys status ---\nVersion: FortiGate-40F v7.0.4"
        fmg = (
            f"{FMG_PORTAL_ONLY_INI}\n"
            "FortiManager 10.254.253.6 | ID 00309472\n"
            "--- diag dvm device list | grep -A 2 -if 00309472 ---\n"
            "sap-spk-c1-c2-id-00309472\n"
            f"{FMG_PORTAL_ONLY_FIM}"
        )
        armazenado = substituir_bloco_coleta_fgt("", f"{fgt}\n\n{fmg}")
        self.assertIn("diag dvm device list", armazenado)
        self.assertIn("get sys status", armazenado)

        por_cmd = _parse_logs_por_comando(armazenado)
        self.assertIn("get sys status", por_cmd)
        self.assertNotIn("diag dvm device list | grep -A 2 -if 00309472", por_cmd)
        self.assertNotIn("00309472", remover_bloco_fmg_portal(armazenado))


class TestJumpPorts(unittest.TestCase):
    def test_portas_padrao_por_host(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import _jump_ports_for_host

        self.assertEqual(_jump_ports_for_host("172.19.40.2", 0), [3122, 22])
        self.assertEqual(_jump_ports_for_host("172.19.40.3", 1), [3222, 22])

    def test_porta_por_octeto_mesmo_com_indice_diferente(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import _jump_ports_for_host

        self.assertEqual(_jump_ports_for_host("10.0.0.2", 1), [3122, 22])
        self.assertEqual(_jump_ports_for_host("10.0.0.3", 0), [3222, 22])

    def test_env_sobrescreve_porta_principal(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import _jump_ports_for_host

        os.environ["PRODESP_JUMP_PORT_1"] = "4000"
        try:
            self.assertEqual(_jump_ports_for_host("172.19.40.2", 0), [4000, 22])
        finally:
            os.environ.pop("PRODESP_JUMP_PORT_1", None)

    def test_fallback_customizado(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import _jump_ports_for_host

        os.environ["PRODESP_JUMP_PORT_FALLBACK"] = "2222"
        try:
            self.assertEqual(_jump_ports_for_host("172.19.40.2", 0), [3122, 2222])
        finally:
            os.environ.pop("PRODESP_JUMP_PORT_FALLBACK", None)

    def test_mensagem_erro_fase_tunel(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import _friendly_connect_error

        msg = _friendly_connect_error(
            "10.254.3.205",
            TimeoutError("Timeout opening channel."),
            phase="tunnel",
            jump_host="172.19.40.2",
            jump_port=3122,
            channel_timeout=15.0,
        )
        self.assertIn("autenticou", msg)
        self.assertIn("túnel", msg.lower())
        self.assertIn("172.19.40.2:3122", msg)
        self.assertNotIn("falha de autenticação no jump", msg.lower())

    def test_resumo_todas_falhas_no_jump(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import (
            _JumpAttempt,
            _summarize_connect_failures,
        )

        attempts = [
            _JumpAttempt("172.25.135.2", 3122, "jump", "timed out"),
            _JumpAttempt("172.25.135.2", 22, "jump", "timed out"),
            _JumpAttempt("172.25.135.3", 3222, "jump", "timed out"),
            _JumpAttempt("172.25.135.3", 22, "jump", "timed out"),
        ]
        msg = _summarize_connect_failures(
            "10.254.6.239",
            attempts,
            connect_timeout=10.0,
            channel_timeout=15.0,
        )
        self.assertIn("Jump server(s) inacessível", msg)
        self.assertIn("172.25.135.2", msg)
        self.assertIn("não foi contactado", msg.lower())
        self.assertNotIn("FortiGate (10.254.6.239) indisponível", msg)

    def test_resumo_falha_tunel_nao_culpa_jump(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import (
            _JumpAttempt,
            _summarize_connect_failures,
        )

        attempts = [
            _JumpAttempt("172.19.40.2", 3122, "jump", "timed out"),
            _JumpAttempt("172.19.40.2", 22, "jump", "timed out"),
            _JumpAttempt("172.19.40.3", 3222, "tunnel", "Timeout opening channel."),
        ]
        msg = _summarize_connect_failures(
            "10.254.3.205",
            attempts,
            connect_timeout=10.0,
            channel_timeout=15.0,
        )
        self.assertIn("conectou", msg.lower())
        self.assertIn("10.254.3.205", msg)
        self.assertNotIn("Jump server(s) inacessível", msg)

    def test_mensagem_eof_fase_fgt(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import _friendly_connect_error

        msg = _friendly_connect_error(
            "10.254.9.218",
            EOFError(),
            phase="fgt",
            jump_host="172.19.40.2",
            jump_port=3122,
        )
        self.assertIn("encerrou a conexão SSH", msg)
        self.assertIn("10.254.9.218:22", msg)
        self.assertNotIn("EOFError", msg)
        self.assertNotIn("falha de autenticação", msg.lower())

    def test_resumo_todas_falhas_eof_fgt(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import (
            _JumpAttempt,
            _summarize_connect_failures,
        )

        attempts = [
            _JumpAttempt("172.19.40.2", 3122, "fgt", "EOFError", "EOFError"),
            _JumpAttempt("172.19.40.3", 3222, "fgt", "", "EOFError"),
        ]
        msg = _summarize_connect_failures(
            "10.254.9.218",
            attempts,
            connect_timeout=10.0,
            channel_timeout=15.0,
            ping_diag=(
                "Diagnóstico (ping -c 5 10.254.9.218 a partir do jump): "
                "5 enviados, 5 recebidos, 0.0% loss. Rede L3 ok."
            ),
        )
        self.assertIn("encerrou o SSH", msg)
        self.assertIn("10.254.9.218:22", msg)
        self.assertIn("Diagnóstico", msg)
        self.assertIn("0.0% loss", msg)
        self.assertNotIn("Jump server(s) inacessível", msg)

    def test_parse_ping_summary_ok(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import _parse_ping_summary

        raw = """
PING 10.254.9.218 (10.254.9.218) 56(84) bytes of data.
64 bytes from 10.254.9.218: icmp_seq=1 ttl=251 time=6.20 ms
--- 10.254.9.218 ping statistics ---
5 packets transmitted, 5 received, 0% packet loss, time 4005ms
rtt min/avg/max/mdev = 6.040/6.108/6.204/0.060 ms
"""
        out = _parse_ping_summary(raw, count=5, ip="10.254.9.218")
        self.assertIn("5 enviados", out)
        self.assertIn("0% loss", out)
        self.assertIn("SSH", out)

    def test_attempts_need_ping_skip_auth(self):
        from prodesp.prodesp.caderno.fgt_ssh_collector import (
            _JumpAttempt,
            _attempts_need_ping_diag,
        )

        os.environ["PRODESP_SSH_DIAG_PING"] = "1"
        try:
            auth_only = [
                _JumpAttempt(
                    "172.19.40.2",
                    3122,
                    "fgt",
                    "Authentication failed.",
                    "AuthenticationException",
                )
            ]
            self.assertFalse(_attempts_need_ping_diag(auth_only))
            eof = [_JumpAttempt("172.19.40.2", 3122, "fgt", "", "EOFError")]
            self.assertTrue(_attempts_need_ping_diag(eof))
            only_jump = [_JumpAttempt("172.19.40.2", 3122, "jump", "timed out")]
            self.assertFalse(_attempts_need_ping_diag(only_jump))
        finally:
            os.environ.pop("PRODESP_SSH_DIAG_PING", None)


class TestCadernoMensagens(unittest.TestCase):
    def test_mensagem_sucesso_com_sharepoint(self):
        from prodesp.prodesp.caderno.caderno_teste_service import mensagem_sucesso_geracao_caderno

        msg = mensagem_sucesso_geracao_caderno(copia_rede=True)
        self.assertIn("SharePoint da PRODESP", msg)
        self.assertNotIn("C:\\", msg)
        self.assertNotIn("OneDrive", msg)

    def test_mensagem_sucesso_sem_copia_rede(self):
        from prodesp.prodesp.caderno.caderno_teste_service import mensagem_sucesso_geracao_caderno

        msg = mensagem_sucesso_geracao_caderno(copia_rede=False)
        self.assertEqual(msg, "Caderno gerado com sucesso.")
        self.assertNotIn("SharePoint", msg)

    def test_resolver_motor_auto_prefere_com_no_windows(self):
        from prodesp.prodesp.caderno import gerador_caderno_prodesp as gen

        prev = os.environ.pop("PRODESP_CADERNO_ENGINE", None)
        try:
            motor = gen._resolver_motor_caderno()
            if sys.platform == "win32" and gen.excel_com_disponivel():
                self.assertEqual(motor, "excel_com")
            else:
                self.assertEqual(motor, "openpyxl")
        finally:
            if prev is not None:
                os.environ["PRODESP_CADERNO_ENGINE"] = prev

    def test_resolver_motor_caderno_padrao_openpyxl(self):
        from prodesp.prodesp.caderno import gerador_caderno_prodesp as gen

        prev = os.environ.get("PRODESP_CADERNO_ENGINE")
        os.environ["PRODESP_CADERNO_ENGINE"] = "openpyxl"
        try:
            self.assertEqual(gen._resolver_motor_caderno(), "openpyxl")
        finally:
            if prev is None:
                os.environ.pop("PRODESP_CADERNO_ENGINE", None)
            else:
                os.environ["PRODESP_CADERNO_ENGINE"] = prev

    def test_publicar_caderno_temp_para_destino(self):
        from prodesp.prodesp.caderno.gerador_caderno_excel_com import _publicar_caderno_gerado

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "caderno_out_temp.xlsx")
            dest = os.path.join(tmp, "SDE_ID_VGR_1.xlsx")
            with open(src, "wb") as handle:
                handle.write(b"PK")
            _publicar_caderno_gerado(src, dest)
            self.assertFalse(os.path.isfile(src), "temp deve ser removido após publicação")
            self.assertTrue(os.path.isfile(dest))
            with open(dest, "rb") as handle:
                self.assertEqual(handle.read(), b"PK")

    def test_publicar_caderno_substitui_destino_existente(self):
        from prodesp.prodesp.caderno.gerador_caderno_excel_com import _publicar_caderno_gerado

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "novo.xlsx")
            dest = os.path.join(tmp, "SDE_ID_VGR_1.xlsx")
            with open(src, "wb") as handle:
                handle.write(b"NOVO")
            with open(dest, "wb") as handle:
                handle.write(b"VELHO")
            _publicar_caderno_gerado(src, dest)
            with open(dest, "rb") as handle:
                self.assertEqual(handle.read(), b"NOVO")

    def test_excel_com_pool_n1_bloqueia_segundo_acesso(self):
        from prodesp.prodesp.caderno import gerador_caderno_excel_com as com

        held = threading.Event()
        release = threading.Event()
        errors: list[BaseException] = []

        def holder():
            try:
                with com.excel_com_serializado():
                    held.set()
                    release.wait(timeout=10)
            except BaseException as exc:
                errors.append(exc)

        t = threading.Thread(target=holder, daemon=True)
        prev_wait = os.environ.get("PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC")
        prev_pool = os.environ.get("PRODESP_CADERNO_EXCEL_POOL_SIZE")
        os.environ["PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC"] = "1"
        os.environ["PRODESP_CADERNO_EXCEL_POOL_SIZE"] = "1"
        com.reset_excel_com_pool_for_tests()
        try:
            t.start()
            self.assertTrue(held.wait(timeout=2), "holder não adquiriu o slot")
            with self.assertRaises(com.ExcelComBusyError) as ctx:
                with com.excel_com_serializado():
                    pass
            self.assertIn("limite", str(ctx.exception).lower())
            self.assertIn("máximo 1", str(ctx.exception).lower())
        finally:
            release.set()
            t.join(timeout=5)
            if prev_wait is None:
                os.environ.pop("PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC", None)
            else:
                os.environ["PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC"] = prev_wait
            if prev_pool is None:
                os.environ.pop("PRODESP_CADERNO_EXCEL_POOL_SIZE", None)
            else:
                os.environ["PRODESP_CADERNO_EXCEL_POOL_SIZE"] = prev_pool
            com.reset_excel_com_pool_for_tests()
        self.assertEqual(errors, [])

    def test_excel_com_pool_n2_permite_dois_bloqueia_terceiro(self):
        from prodesp.prodesp.caderno import gerador_caderno_excel_com as com

        release = threading.Event()
        errors: list[BaseException] = []
        acquired_count = 0
        count_lock = threading.Lock()
        both_held = threading.Event()

        def holder():
            nonlocal acquired_count
            try:
                with com.excel_com_serializado():
                    with count_lock:
                        acquired_count += 1
                        if acquired_count >= 2:
                            both_held.set()
                    release.wait(timeout=10)
            except BaseException as exc:
                errors.append(exc)

        prev_wait = os.environ.get("PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC")
        prev_pool = os.environ.get("PRODESP_CADERNO_EXCEL_POOL_SIZE")
        os.environ["PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC"] = "1"
        os.environ["PRODESP_CADERNO_EXCEL_POOL_SIZE"] = "2"
        com.reset_excel_com_pool_for_tests()
        threads = [threading.Thread(target=holder, daemon=True) for _ in range(2)]
        try:
            for t in threads:
                t.start()
            self.assertTrue(both_held.wait(timeout=3), "dois slots não foram adquiridos")
            with self.assertRaises(com.ExcelComBusyError) as ctx:
                with com.excel_com_serializado():
                    pass
            self.assertIn("máximo 2", str(ctx.exception).lower())
        finally:
            release.set()
            for t in threads:
                t.join(timeout=5)
            if prev_wait is None:
                os.environ.pop("PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC", None)
            else:
                os.environ["PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC"] = prev_wait
            if prev_pool is None:
                os.environ.pop("PRODESP_CADERNO_EXCEL_POOL_SIZE", None)
            else:
                os.environ["PRODESP_CADERNO_EXCEL_POOL_SIZE"] = prev_pool
            com.reset_excel_com_pool_for_tests()
        self.assertEqual(errors, [])

    def test_excel_com_pool_simula_4_analistas_concorrentes(self):
        """Simula .env POOL_SIZE=2 + WAIT=60: 4 gerações ao mesmo tempo.

        Excel real é mockado (sleep); valida fila do pool: no máx. 2 ativos e
        os 4 concluem (2º lote entra quando o 1º libera o slot).
        """
        from prodesp.prodesp.caderno import gerador_caderno_excel_com as com

        work_sec = 1.2
        results: dict[int, dict[str, Any]] = {}
        results_lock = threading.Lock()
        active = 0
        max_active = 0
        active_lock = threading.Lock()
        barrier = threading.Barrier(4)

        def fake_locked(*_a, **_kw):
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
                now_active = active
            try:
                time.sleep(work_sec)
            finally:
                with active_lock:
                    active -= 1
            return now_active

        def analista(idx: int):
            barrier.wait(timeout=5)
            t0 = time.monotonic()
            status = "ok"
            detail = ""
            try:
                com.gerar_caderno_via_excel_com(
                    "modelo.xlsx",
                    f"out_{idx}.xlsx",
                    valores_caderno={},
                    link_sai_bl={},
                    link_scm={},
                    logs_por_cmd={},
                    show_interface_parts=[],
                    itens_executor_status=[],
                )
            except com.ExcelComBusyError as exc:
                status = "busy"
                detail = str(exc)
            except Exception as exc:
                status = "error"
                detail = f"{type(exc).__name__}: {exc}"
            elapsed = time.monotonic() - t0
            with results_lock:
                results[idx] = {"status": status, "elapsed_s": round(elapsed, 2), "detail": detail}

        prev_wait = os.environ.get("PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC")
        prev_pool = os.environ.get("PRODESP_CADERNO_EXCEL_POOL_SIZE")
        os.environ["PRODESP_CADERNO_EXCEL_POOL_SIZE"] = "2"
        os.environ["PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC"] = "60"
        com.reset_excel_com_pool_for_tests()
        threads = [
            threading.Thread(target=analista, args=(i,), name=f"analista-{i}", daemon=True)
            for i in range(1, 5)
        ]
        try:
            with unittest.mock.patch.object(
                com, "_gerar_caderno_via_excel_com_locked", side_effect=fake_locked
            ):
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=30)
        finally:
            if prev_wait is None:
                os.environ.pop("PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC", None)
            else:
                os.environ["PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC"] = prev_wait
            if prev_pool is None:
                os.environ.pop("PRODESP_CADERNO_EXCEL_POOL_SIZE", None)
            else:
                os.environ["PRODESP_CADERNO_EXCEL_POOL_SIZE"] = prev_pool
            com.reset_excel_com_pool_for_tests()

        self.assertEqual(len(results), 4, f"resultados incompletos: {results}")
        ok = [i for i, r in sorted(results.items()) if r["status"] == "ok"]
        busy = [i for i, r in sorted(results.items()) if r["status"] == "busy"]
        err = [i for i, r in sorted(results.items()) if r["status"] == "error"]
        report_lines = [
            f"  analista-{i}: status={results[i]['status']} elapsed={results[i]['elapsed_s']}s"
            + (f" detail={results[i]['detail'][:80]}" if results[i]["detail"] else "")
            for i in sorted(results)
        ]
        report = "\n".join(report_lines)
        print(
            "\n[simulação 4 analistas | POOL_SIZE=2 | WAIT=60]\n"
            f"max_active={max_active}\n{report}\n"
        )
        self.assertEqual(err, [], f"erros inesperados:\n{report}")
        self.assertLessEqual(max_active, 2, f"pool vazou (max_active={max_active}):\n{report}")
        self.assertEqual(ok, [1, 2, 3, 4], f"com WAIT=60 todos devem concluir:\n{report}")
        self.assertEqual(busy, [], f"ninguém deveria receber busy com WAIT=60:\n{report}")
        # 2 ondas ~ work_sec cada → mais lentos ~ >= 2*work
        slow = [results[i]["elapsed_s"] for i in ok if results[i]["elapsed_s"] >= work_sec * 1.5]
        self.assertGreaterEqual(len(slow), 2, f"esperava 2ª onda enfileirada:\n{report}")

    def test_excel_com_job_timeout_kills_pid_and_raises(self):
        """Teto duro: worker lento → kill do PID + ExcelComTimeoutError; slot liberado."""
        from unittest.mock import patch

        from prodesp.prodesp.caderno import gerador_caderno_excel_com as com

        prev_to = os.environ.get("PRODESP_CADERNO_EXCEL_JOB_TIMEOUT_SEC")
        prev_wait = os.environ.get("PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC")
        prev_pool = os.environ.get("PRODESP_CADERNO_EXCEL_POOL_SIZE")
        os.environ["PRODESP_CADERNO_EXCEL_JOB_TIMEOUT_SEC"] = "1"
        os.environ["PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC"] = "5"
        os.environ["PRODESP_CADERNO_EXCEL_POOL_SIZE"] = "1"
        com.reset_excel_com_pool_for_tests()
        kill_calls: list[int] = []

        def fake_locked(*_a, pid_box=None, **_k):
            if pid_box is not None:
                pid_box["pid"] = 424242
            time.sleep(8)

        def fake_kill(pid: int) -> None:
            kill_calls.append(int(pid))

        try:
            with patch.object(com, "_gerar_caderno_via_excel_com_locked", side_effect=fake_locked):
                with patch.object(com, "_kill_excel_pid", side_effect=fake_kill):
                    with self.assertRaises(com.ExcelComTimeoutError) as ctx:
                        com.gerar_caderno_via_excel_com(
                            "modelo.xlsx",
                            "out.xlsx",
                            valores_caderno={},
                            link_sai_bl={},
                            link_scm={},
                            logs_por_cmd={},
                            show_interface_parts=[],
                            itens_executor_status=[],
                        )
            self.assertIn("tempo limite", str(ctx.exception).lower())
            self.assertEqual(kill_calls, [424242])
            # Slot liberado — novo acquire deve funcionar.
            with com.excel_com_serializado():
                pass
        finally:
            if prev_to is None:
                os.environ.pop("PRODESP_CADERNO_EXCEL_JOB_TIMEOUT_SEC", None)
            else:
                os.environ["PRODESP_CADERNO_EXCEL_JOB_TIMEOUT_SEC"] = prev_to
            if prev_wait is None:
                os.environ.pop("PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC", None)
            else:
                os.environ["PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC"] = prev_wait
            if prev_pool is None:
                os.environ.pop("PRODESP_CADERNO_EXCEL_POOL_SIZE", None)
            else:
                os.environ["PRODESP_CADERNO_EXCEL_POOL_SIZE"] = prev_pool
            com.reset_excel_com_pool_for_tests()

    def test_excel_com_busy_vira_caderno_geracao_error(self):
        from prodesp.prodesp.caderno import gerador_caderno_prodesp as gen
        from prodesp.prodesp.caderno.gerador_caderno_excel_com import ExcelComBusyError
        from prodesp.prodesp.caderno.gerador_caderno_prodesp import CadernoGeracaoError

        modelo = gen._modelo_path("excel_com")
        if not os.path.isfile(modelo):
            self.skipTest("Template v3 não presente no workspace")

        dados = {
            "unidade": {
                "id_vgr_unidades": "TEST999",
                "acronimo_unidades": "TST",
                "nome_unidades": "Unidade Teste",
                "localidade_unidades": "Sao Paulo/SP",
                "topologia_unidades": "SD-WAN",
                "modelo_solucao_unidades": "G",
                "hostname_unidades": "fgt-test",
                "loopback_vivo_unidades": "10.0.0.1",
                "id_intragov_unidades": "IG999",
            },
            "equipamentos": [{"modelo_equipamentos": "FGT-81F", "serial_equipamentos": "FG81FTEST"}],
            "links": [
                {
                    "tipo_links": "STATIC",
                    "id_vgr_links": "111",
                    "velocidade_links": "100",
                    "ip_wan_links": "187.1.1.1/31",
                    "ip_gateway_links": "187.1.1.0",
                },
                {
                    "tipo_links": "MPLS",
                    "id_vgr_links": "222",
                    "velocidade_links": "10",
                    "ip_wan_links": "10.1.1.1/29",
                    "ip_gateway_links": "10.1.1.0",
                },
            ],
            "questionario": {
                "dhcp_server": "NÃO",
                "dhcp_relay": "NÃO",
                "vlan": "SIM",
                "multi_ip_lan": "NÃO",
                "voip_tipo": "N/A",
                "status_testes": {
                    str(r): ("✔️ Concluido" if r == 40 else "⚠️Pendente") for r in range(40, 50)
                },
            },
        }
        logs = (
            "--- get sys ha status ---\nHA: active\n"
            "--- show sys interface wan ---\nwan up\n"
            "--- diagnose sys sip-proxy calls ---\nsip-proxy ok"
        )
        with tempfile.TemporaryDirectory() as tmp:
            orig_gerados = gen.GERADOS_DIR
            try:
                gen.GERADOS_DIR = tmp
                with unittest.mock.patch(
                    "prodesp.prodesp.caderno.gerador_caderno_prodesp.gerar_caderno_via_excel_com",
                    side_effect=ExcelComBusyError(
                        "O limite de gerações simultâneas de caderno via Excel no servidor foi atingido (máximo 2)."
                    ),
                ), unittest.mock.patch(
                    "prodesp.prodesp.caderno.gerador_caderno_prodesp._resolver_motor_caderno",
                    return_value="excel_com",
                ), unittest.mock.patch(
                    "prodesp.prodesp.caderno.gerador_caderno_prodesp.excel_com_disponivel",
                    return_value=True,
                ):
                    with self.assertRaises(CadernoGeracaoError) as ctx:
                        gerar_caderno_prodesp(
                            dados,
                            logs_text=logs,
                            imagem_esaq_b64=f"data:image/png;base64,{_TINY_PNG_B64}",
                            pasta_rede="",
                        )
                self.assertIn("limite", str(ctx.exception).lower())
            finally:
                gen.GERADOS_DIR = orig_gerados

    def test_resolve_gerados_dir_env_local(self):
        from prodesp.prodesp.caderno import gerador_caderno_prodesp as gen

        with tempfile.TemporaryDirectory() as tmp:
            prev = os.environ.get("PRODESP_CADERNO_LOCAL_DIR")
            os.environ["PRODESP_CADERNO_LOCAL_DIR"] = tmp
            try:
                self.assertEqual(gen.resolve_gerados_dir(), os.path.abspath(tmp))
            finally:
                if prev is None:
                    os.environ.pop("PRODESP_CADERNO_LOCAL_DIR", None)
                else:
                    os.environ["PRODESP_CADERNO_LOCAL_DIR"] = prev

    def test_truncate_mysql_text_field_respeita_bytes(self):
        from prodesp.prodesp.db_field_limits import LOGS_ATENDIMENTOS_MAX, truncate_mysql_text_field

        text = "á" * 40000
        out = truncate_mysql_text_field(text, max_bytes=LOGS_ATENDIMENTOS_MAX)
        self.assertLessEqual(len(out.encode("utf-8")), LOGS_ATENDIMENTOS_MAX)
        self.assertTrue(out.endswith("á") or out)


class TestCadernoHistorico(unittest.TestCase):
    def test_historico_coleta_sucesso_e_falha(self):
        from prodesp.prodesp.caderno.caderno_teste_service import (
            _CAMPO_HISTORICO_COLETA,
            _historico_coleta_falha,
            _historico_coleta_sucesso,
            _registrar_historico_caderno,
        )

        ok = _historico_coleta_sucesso(
            hostname="fgt-sp",
            acronimo="DETRAN",
            elapsed_seconds=12.5,
            commands_run=8,
            log_chars=45000,
            parcial=False,
            resumo_limpeza_admin=(
                "--- limpeza admin — resumo ---\n"
                "=== Limpeza usuário local «admin» ===\n"
                "Verificação pós-delete: OK — usuário «admin» não consta mais."
            ),
        )
        self.assertIn("concluída com sucesso", ok)
        self.assertIn("fgt-sp", ok)
        self.assertIn("45000", ok)
        self.assertIn("limpeza admin — resumo", ok)
        self.assertIn("Verificação pós-delete: OK", ok)

        fail = _historico_coleta_falha(
            hostname="fgt-sp",
            acronimo="DETRAN",
            motivo="Timeout SSH.",
        )
        self.assertIn("Falha na coleta", fail)
        self.assertIn("Timeout SSH", fail)

        conn = unittest.mock.MagicMock()
        with unittest.mock.patch(
            "prodesp.prodesp.caderno.caderno_teste_service.registrar_log"
        ) as mock_log:
            _registrar_historico_caderno(
                conn,
                99,
                _CAMPO_HISTORICO_COLETA,
                ok,
            )
            mock_log.assert_called_once()
            args = mock_log.call_args[0]
            self.assertEqual(args[1], "atendimentos")
            self.assertEqual(args[2], 99)
            self.assertEqual(args[3], _CAMPO_HISTORICO_COLETA)

    def test_historico_geracao_sucesso_e_falha(self):
        from prodesp.prodesp.caderno.caderno_teste_service import (
            _historico_geracao_falha,
            _historico_geracao_sucesso,
        )

        ok = _historico_geracao_sucesso(
            filename="Caderno_TESTE_123.xlsm",
            hostname="fgt-sp",
            acronimo="DER",
            copia_rede=True,
        )
        self.assertIn("gerado com sucesso", ok)
        self.assertIn("Caderno_TESTE_123.xlsm", ok)
        self.assertIn("SharePoint/rede: sim", ok)

        fail = _historico_geracao_falha(
            hostname="fgt-sp",
            acronimo="DER",
            motivo="Execute a coleta de logs FGT antes de gerar o caderno.",
        )
        self.assertIn("Falha na geração", fail)
        self.assertIn("coleta de logs", fail)

    def test_executar_coleta_registra_historico_falha_loopback(self):
        import unittest.mock as mock

        from prodesp.prodesp.caderno.caderno_teste_service import executar_coleta

        cursor = mock.MagicMock()
        conn = mock.MagicMock()
        with mock.patch(
            "prodesp.prodesp.caderno.caderno_teste_service.carregar_contexto_atendimento",
            return_value={
                "unidade": {
                    "hostname_unidades": "fgt-x",
                    "acronimo_unidades": "SAP",
                    "loopback_vivo_unidades": "",
                },
                "equipamentos": [],
                "logs_atendimentos": "",
            },
        ):
            with mock.patch(
                "prodesp.prodesp.caderno.caderno_teste_service._registrar_historico_caderno"
            ) as mock_hist:
                result = executar_coleta(cursor, conn, 42)
        self.assertFalse(result["ok"])
        mock_hist.assert_called_once()
        conn.commit.assert_called_once()


class TestExtrairResumoLimpezaAdminColeta(unittest.TestCase):
    def test_extrai_resumo_completo_admin_removido(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import extrair_resumo_limpeza_admin_coleta

        texto = (
            "=== FGT 10.0.0.1 ===\n\n"
            "--- limpeza admin — resumo ---\n"
            "=== Limpeza usuário local «admin» ===\n"
            "Detecção: usuário «admin» encontrado (via show sys admin ?).\n"
            "Verificação pós-delete: OK — usuário «admin» não consta mais.\n"
            "Usuários restantes: end, vvita."
        )
        out = extrair_resumo_limpeza_admin_coleta(texto)
        self.assertIn("limpeza admin — resumo", out)
        self.assertIn("Verificação pós-delete: OK", out)
        self.assertNotIn("=== FGT", out)

    def test_extrai_resumo_admin_nao_cadastrado(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import extrair_resumo_limpeza_admin_coleta

        texto = (
            "--- limpeza admin — resumo ---\n"
            "Usuário «admin» não cadastrado; etapa de limpeza ignorada."
        )
        out = extrair_resumo_limpeza_admin_coleta(texto)
        self.assertIn("não cadastrado", out)

    def test_extrai_bloco_erro_limpeza(self):
        from prodesp.prodesp.caderno.fgt_admin_cleanup import extrair_resumo_limpeza_admin_coleta

        texto = "--- limpeza admin ---\nERRO: TimeoutException"
        out = extrair_resumo_limpeza_admin_coleta(texto)
        self.assertIn("ERRO:", out)


if __name__ == "__main__":
    unittest.main()
