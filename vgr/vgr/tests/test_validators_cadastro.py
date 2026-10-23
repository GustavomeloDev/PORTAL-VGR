"""Testes unitários — validação de payload de cadastros VGR."""

from __future__ import annotations

import unittest

from vgr.vgr.cadastros.validators import (
    apply_matriz_endereco_from_cliente,
    mask_pii_for_historico,
    normalize_cnpj,
    normalize_cep,
    normalize_uf,
    parse_cliente_payload,
    parse_contratada_payload,
    parse_equipamento_payload,
    parse_field_payload,
    parse_link_payload,
    parse_unidade_payload,
)


class TestClienteValidators(unittest.TestCase):
    def test_razao_obrigatoria(self):
        with self.assertRaises(ValueError):
            parse_cliente_payload({"razao_social": "  "})

    def test_payload_ok(self):
        d = parse_cliente_payload(
            {
                "razao_social": " Acme LTDA ",
                "cnpj_cliente": "11222333000181",
                "uf": "sp",
                "cep": "01310100",
                "cidade": "São Paulo",
            }
        )
        self.assertEqual(d["razao_social"], "Acme LTDA")
        self.assertEqual(d["cnpj_cliente"], "11.222.333/0001-81")
        self.assertEqual(d["uf"], "SP")
        self.assertEqual(d["cep"], "01310-100")

    def test_cnpj_invalido(self):
        with self.assertRaises(ValueError):
            normalize_cnpj("123")

    def test_uf_invalida(self):
        with self.assertRaises(ValueError):
            normalize_uf("XX")

    def test_cep_vazio(self):
        self.assertIsNone(normalize_cep(""))
        self.assertIsNone(normalize_cep(None))


class TestUnidadeValidators(unittest.TestCase):
    def test_unidade_ok(self):
        d = parse_unidade_payload(
            {
                "id_cliente": 1,
                "nome_unidade": "Matriz SP",
                "tipo_unidade": "matriz",
                "ha": "1",
            }
        )
        self.assertEqual(d["tipo_unidade"], "MATRIZ")
        self.assertEqual(d["ha"], 1)

    def test_matriz_copia_endereco(self):
        data = parse_unidade_payload(
            {"id_cliente": 1, "nome_unidade": "HQ", "tipo_unidade": "MATRIZ"}
        )
        data = apply_matriz_endereco_from_cliente(
            data,
            {
                "endereco_principal": "Rua A, 1",
                "cidade": "Campinas",
                "uf": "SP",
                "cep": "13000-000",
            },
        )
        self.assertEqual(data["endereco"], "Rua A, 1")
        self.assertEqual(data["cidade"], "Campinas")


class TestEquipamentoValidators(unittest.TestCase):
    def test_serial_obrigatorio(self):
        with self.assertRaises(ValueError):
            parse_equipamento_payload({"id_unidade": 1, "serial": "  "})

    def test_tipo_servico_invalido(self):
        with self.assertRaises(ValueError):
            parse_equipamento_payload(
                {"id_unidade": 1, "serial": "ABC", "tipo_servico": "FOO"}
            )

    def test_forticloud_opcional_nao_enviado(self):
        d = parse_equipamento_payload({"id_unidade": 1, "serial": "SN-1"})
        self.assertNotIn("fortcloud_key", d)
        self.assertNotIn("_set_fortcloud", d)

    def test_forticloud_set(self):
        d = parse_equipamento_payload(
            {"id_unidade": 1, "serial": "SN-1", "fortcloud_key": " secret "}
        )
        self.assertEqual(d["fortcloud_key"], "secret")
        self.assertTrue(d.get("_set_fortcloud"))

    def test_serial_fortinet_rejeita_provisorio(self):
        with self.assertRaises(ValueError) as ctx:
            parse_equipamento_payload(
                {
                    "id_unidade": 1,
                    "serial": "123",
                    "vendor": "Fortinet",
                    "modelo": "FortiGate 40F",
                }
            )
        self.assertIn("série", str(ctx.exception).lower())

    def test_serial_fortinet_ok_normaliza(self):
        d = parse_equipamento_payload(
            {
                "id_unidade": 1,
                "serial": "  fgt40ftk2409d6qk ",
                "vendor": "Fortinet",
            }
        )
        self.assertEqual(d["serial"], "FGT40FTK2409D6QK")
        self.assertEqual(d["modelo"], "FortiGate 40F")

    def test_serial_nao_fortinet_livre(self):
        d = parse_equipamento_payload(
            {"id_unidade": 1, "serial": "SN-CISCO-1", "vendor": "Cisco"}
        )
        self.assertEqual(d["serial"], "SN-CISCO-1")

    def test_hostname_sem_espaco(self):
        with self.assertRaises(ValueError):
            parse_equipamento_payload(
                {"id_unidade": 1, "serial": "SN-1", "hostname": "host name"}
            )

    def test_ticket_noc_formato(self):
        with self.assertRaises(ValueError):
            parse_equipamento_payload(
                {"id_unidade": 1, "serial": "SN-1", "tkt_noc": "abc"}
            )
        d = parse_equipamento_payload(
            {"id_unidade": 1, "serial": "SN-1", "tkt_noc": "1680355"}
        )
        self.assertEqual(d["tkt_noc"], "1680355")


class TestLinkValidators(unittest.TestCase):
    def test_equipamento_obrigatorio_wan(self):
        with self.assertRaises(ValueError):
            parse_link_payload({"id_unidade": 1, "tipo_link": "WAN"})

    def test_lan_sem_equipamento(self):
        d = parse_link_payload(
            {
                "id_unidade": 1,
                "tipo_link": "LAN",
                "ip_address": "10.0.0.1/24",
            }
        )
        self.assertIsNone(d["id_equipamento"])
        self.assertEqual(d["tipo_link"], "LAN")

    def test_lan_ignora_equipamento_enviado(self):
        d = parse_link_payload(
            {
                "id_unidade": 1,
                "id_equipamento": 2,
                "tipo_link": "LAN",
                "modo_conexao": "STATIC",
                "ip_address": "10.0.0.1/24",
            }
        )
        self.assertIsNone(d["id_equipamento"])
        self.assertIsNone(d["modo_conexao"])

    def test_tipo_link_invalido(self):
        with self.assertRaises(ValueError):
            parse_link_payload(
                {"id_unidade": 1, "id_equipamento": 2, "tipo_link": "XYZ"}
            )

    def test_ip_invalido(self):
        with self.assertRaises(ValueError):
            parse_link_payload(
                {
                    "id_unidade": 1,
                    "id_equipamento": 2,
                    "tipo_link": "WAN",
                    "ip_address": "999.1.1.1",
                }
            )

    def test_gateway_sem_cidr(self):
        with self.assertRaises(ValueError):
            parse_link_payload(
                {
                    "id_unidade": 1,
                    "id_equipamento": 2,
                    "tipo_link": "WAN",
                    "gateway": "10.0.0.1/24",
                }
            )

    def test_ip_igual_gateway(self):
        with self.assertRaises(ValueError):
            parse_link_payload(
                {
                    "id_unidade": 1,
                    "id_equipamento": 2,
                    "tipo_link": "WAN",
                    "ip_address": "10.0.0.1",
                    "gateway": "10.0.0.1",
                }
            )

    def test_id_vgr_link_curto(self):
        with self.assertRaises(ValueError):
            parse_link_payload(
                {
                    "id_unidade": 1,
                    "id_equipamento": 2,
                    "tipo_link": "WAN",
                    "id_vgr_link": "123",
                }
            )

    def test_static_vivo_exige_id_vgr(self):
        with self.assertRaises(ValueError) as ctx:
            parse_link_payload(
                {
                    "id_unidade": 1,
                    "id_equipamento": 2,
                    "tipo_link": "WAN",
                    "modo_conexao": "STATIC",
                    "operadora": "VIVO",
                    "ip_address": "10.0.0.2",
                    "gateway": "10.0.0.1",
                }
            )
        self.assertIn("ID VGR", str(ctx.exception))

    def test_lan_limpa_modo(self):
        d = parse_link_payload(
            {
                "id_unidade": 1,
                "id_equipamento": 2,
                "tipo_link": "LAN",
                "modo_conexao": "STATIC",
                "ip_address": "10.0.0.1/24",
            }
        )
        self.assertIsNone(d["modo_conexao"])
        self.assertIsNone(d["id_equipamento"])

    def test_velocidade_normaliza(self):
        d = parse_link_payload(
            {
                "id_unidade": 1,
                "id_equipamento": 2,
                "tipo_link": "WAN",
                "velocidade": "1G",
            }
        )
        self.assertEqual(d["velocidade"], "1000")

    def test_ip_cidr_ok(self):
        d = parse_link_payload(
            {
                "id_unidade": 1,
                "tipo_link": "LAN",
                "ip_address": "10.0.0.1/24",
                "gateway": "10.0.0.254",
            }
        )
        self.assertEqual(d["ip_address"], "10.0.0.1/24")
        self.assertEqual(d["gateway"], "10.0.0.254")
        self.assertIsNone(d["id_equipamento"])

    def test_pppoe_blank_skip(self):
        d = parse_link_payload(
            {
                "id_unidade": 1,
                "id_equipamento": 2,
                "tipo_link": "WAN",
                "pppoe_user": "  ",
            }
        )
        self.assertTrue(d.get("_skip_pppoe_user"))
        self.assertNotIn("_set_pppoe_user", d)

    def test_link_ok(self):
        d = parse_link_payload(
            {
                "id_unidade": 10,
                "id_equipamento": 20,
                "tipo_link": "wan",
                "modo_conexao": "static",
                "ip_address": "10.0.0.1",
                "mascara": "255.255.255.0",
                "gateway": "10.0.0.254",
            }
        )
        self.assertEqual(d["tipo_link"], "WAN")
        self.assertEqual(d["modo_conexao"], "STATIC")
        self.assertEqual(d["ip_address"], "10.0.0.1")
        self.assertEqual(d["gateway"], "10.0.0.254")


def _wan(**extra):
    base = {
        "id_unidade": 1,
        "id_equipamento": 2,
        "tipo_link": "WAN",
        "modo_conexao": "STATIC",
        "operadora": "CLARO",
        "ip_address": "187.51.205.114",
        "mascara": "255.255.255.252",
        "gateway": "187.51.205.113",
    }
    base.update(extra)
    return base


class TestLinkCalculadoraIpv4(unittest.TestCase):
    """Calculadora IP + máscara (core.utils.network) aplicada ao link VGR."""

    def test_wan_30_ok_os_dois_hosts(self):
        parse_link_payload(_wan())
        parse_link_payload(_wan(ip_address="187.51.205.113", gateway="187.51.205.114"))

    def test_static_exige_mascara(self):
        with self.assertRaises(ValueError) as ctx:
            parse_link_payload(_wan(mascara=""))
        self.assertIn("Máscara", str(ctx.exception))

    def test_mascara_nao_contigua(self):
        with self.assertRaises(ValueError) as ctx:
            parse_link_payload(_wan(mascara="255.255.0.255"))
        self.assertIn("máscara", str(ctx.exception).lower())

    def test_gateway_fora_da_rede(self):
        with self.assertRaises(ValueError) as ctx:
            parse_link_payload(_wan(gateway="187.51.205.1"))
        self.assertIn("não pertence à rede", str(ctx.exception))

    def test_ip_endereco_de_rede(self):
        with self.assertRaises(ValueError) as ctx:
            parse_link_payload(_wan(ip_address="187.51.205.112"))
        self.assertIn("endereço de rede", str(ctx.exception))

    def test_cidr_preenche_mascara_vazia(self):
        d = parse_link_payload(_wan(ip_address="187.51.205.114/30", mascara=""))
        self.assertEqual(d["mascara"], "255.255.255.252")

    def test_cidr_divergente_da_mascara(self):
        with self.assertRaises(ValueError) as ctx:
            parse_link_payload(_wan(ip_address="187.51.205.114/29"))
        self.assertIn("prefixo", str(ctx.exception))

    def test_mascara_virgula_normaliza(self):
        d = parse_link_payload(_wan(mascara="255,255,255,252"))
        self.assertEqual(d["mascara"], "255.255.255.252")

    def test_lan_subrede_deve_ser_rede(self):
        with self.assertRaises(ValueError) as ctx:
            parse_link_payload(
                {
                    "id_unidade": 1,
                    "tipo_link": "LAN",
                    "ip_address": "10.1.2.254",
                    "mascara": "255.255.255.0",
                    "subrede": "10.1.2.254",
                }
            )
        self.assertIn("esperado 10.1.2.0", str(ctx.exception))

    def test_lan_subrede_ok(self):
        d = parse_link_payload(
            {
                "id_unidade": 1,
                "tipo_link": "LAN",
                "ip_address": "10.1.2.254",
                "mascara": "255.255.255.0",
                "subrede": "10.1.2.0",
            }
        )
        self.assertEqual(d["subrede"], "10.1.2.0")

    def test_dhcp_server_range_ok(self):
        d = parse_link_payload(
            {
                "id_unidade": 1,
                "tipo_link": "DHCP_SERVER",
                "mascara": "255.255.255.0",
                "subrede": "10.1.2.0",
                "range_start": "10.1.2.100",
                "range_end": "10.1.2.200",
            }
        )
        self.assertEqual(d["range_start"], "10.1.2.100")

    def test_range_fora_da_rede(self):
        with self.assertRaises(ValueError) as ctx:
            parse_link_payload(
                {
                    "id_unidade": 1,
                    "tipo_link": "DHCP_SERVER",
                    "mascara": "255.255.255.0",
                    "subrede": "10.1.2.0",
                    "range_start": "10.1.2.100",
                    "range_end": "10.1.3.10",
                }
            )
        self.assertIn("fora da rede", str(ctx.exception))

    def test_range_invertido(self):
        with self.assertRaises(ValueError):
            parse_link_payload(
                {
                    "id_unidade": 1,
                    "tipo_link": "AP_RANGE",
                    "range_start": "10.1.2.200",
                    "range_end": "10.1.2.100",
                }
            )

    def test_range_incompleto(self):
        with self.assertRaises(ValueError):
            parse_link_payload(
                {"id_unidade": 1, "tipo_link": "AP_RANGE", "range_start": "10.1.2.200"}
            )


class TestLinkOperadoraVlanVivo(unittest.TestCase):
    def test_operadora_outros_texto(self):
        d = parse_link_payload(_wan(operadora="OUTROS", operadora_outros=" vtal "))
        self.assertEqual(d["operadora"], "VTAL")

    def test_operadora_outros_sem_texto(self):
        with self.assertRaises(ValueError):
            parse_link_payload(_wan(operadora="OUTROS", operadora_outros=""))

    def test_operadora_legado_mantida(self):
        d = parse_link_payload(_wan(operadora="outra"))
        self.assertEqual(d["operadora"], "OUTRA")

    def test_vlan_normaliza(self):
        self.assertEqual(parse_link_payload(_wan(vlan="VLAN 100"))["vlan"], "100")

    def test_vlan_fora_da_faixa(self):
        with self.assertRaises(ValueError):
            parse_link_payload(_wan(vlan="5000"))

    def test_designador_vivo_curto(self):
        with self.assertRaises(ValueError):
            parse_link_payload(
                _wan(operadora="VIVO", id_vgr_link="1234567", identificador="wan1",
                     designador="123")
            )

    def test_vivo_avisos_nao_bloqueiam(self):
        from vgr.vgr.cadastros.validators import link_avisos

        d = parse_link_payload(
            _wan(operadora="VIVO", id_vgr_link="1234567", identificador="wan1",
                 ip_address="187.51.205.114", gateway="187.51.205.113")
        )
        avisos = link_avisos(d)
        self.assertTrue(any("Designador" in a for a in avisos))
        self.assertTrue(all("máscara" not in a.lower() or "/30" in a for a in avisos))

    def test_pppoe_create_exige_credenciais(self):
        with self.assertRaises(ValueError) as ctx:
            parse_link_payload(_wan(modo_conexao="PPPOE", ip_address="", mascara="", gateway=""))
        self.assertIn("PPPoE", str(ctx.exception))

    def test_pppoe_update_aceita_credencial_gravada(self):
        d = parse_link_payload(
            _wan(modo_conexao="PPPOE", ip_address="", mascara="", gateway="",
                 has_pppoe_user=1, has_pppoe_pass=1)
        )
        self.assertEqual(d["modo_conexao"], "PPPOE")


class TestCadastroCoreRegras(unittest.TestCase):
    def test_cnpj_dv_invalido(self):
        with self.assertRaises(ValueError) as ctx:
            normalize_cnpj("11.222.333/0001-82")
        self.assertIn("verificadores", str(ctx.exception))

    def test_unidade_coordenadas(self):
        d = parse_unidade_payload(
            {"id_cliente": 1, "nome_unidade": "X", "latitude": "-23,5505", "longitude": "-46.6333"}
        )
        self.assertEqual(d["latitude"], "-23.55050000")
        self.assertEqual(d["longitude"], "-46.63330000")

    def test_unidade_latitude_fora_faixa(self):
        with self.assertRaises(ValueError):
            parse_unidade_payload(
                {"id_cliente": 1, "nome_unidade": "X", "latitude": "123", "longitude": "1"}
            )

    def test_unidade_coordenada_sozinha(self):
        with self.assertRaises(ValueError):
            parse_unidade_payload({"id_cliente": 1, "nome_unidade": "X", "latitude": "-23.5"})

    def test_cliente_preserva_gp_cs(self):
        d = parse_cliente_payload({"razao_social": "A", "nome_gp_cs_clientes": " Maria "})
        self.assertEqual(d["nome_gp_cs_clientes"], "Maria")

    def test_modelo_fortinet_vem_do_serial(self):
        d = parse_equipamento_payload(
            {"id_unidade": 1, "serial": "FG120GTK25006244", "vendor": "Fortinet",
             "modelo": "FortiGate 40F"}
        )
        self.assertEqual(d["modelo"], "FortiGate 120G")


class TestFieldValidators(unittest.TestCase):
    def test_nome_obrigatorio(self):
        with self.assertRaises(ValueError):
            parse_field_payload({"nome": "  "})

    def test_cpf_invalido(self):
        with self.assertRaises(ValueError):
            parse_field_payload({"nome": "João", "cpf": "11111111111"})

    def test_field_ok_com_emails(self):
        d = parse_field_payload(
            {
                "nome": " Técnico X ",
                "telefone": "11999990000",
                "cpf": "52998224725",
                "rg": "12.345.678-9",
                "emails": ["A@Exemplo.com", "a@exemplo.com", "b@exemplo.com"],
                "id_contratadas": [1, 1, 2],
            }
        )
        self.assertEqual(d["nome"], "Técnico X")
        self.assertEqual(d["cpf"], "529.982.247-25")
        self.assertEqual(d["emails"], ["a@exemplo.com", "b@exemplo.com"])
        self.assertEqual(d["id_contratadas"], [1, 2])
        self.assertTrue(d.get("_set_cpf"))
        self.assertTrue(d.get("_set_emails"))

    def test_email_invalido(self):
        with self.assertRaises(ValueError):
            parse_field_payload({"nome": "X", "emails": ["nao-e-email"]})

    def test_mask_historico(self):
        self.assertEqual(mask_pii_for_historico("cpf", "529.982.247-25"), "***4725")
        self.assertEqual(mask_pii_for_historico("rg", "123"), "***")

    def test_contratada_payload(self):
        d = parse_contratada_payload({"nome": "Empresa Y", "cnpj": "11222333000181"})
        self.assertEqual(d["nome_contratada"], "Empresa Y")
        self.assertEqual(d["cnpj"], "11.222.333/0001-81")


if __name__ == "__main__":
    unittest.main()
