"""Validação de payload de cadastros VGR (clientes e unidades)."""

from __future__ import annotations

import ipaddress
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_UF_OK = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

_TIPO_UNIDADE_OK = {"MATRIZ", "FILIAL", "POLO", "CD", "OUTRO"}
_TOPOLOGIA_UNIDADE_OK = {"HUB", "SPOKE"}
_TIPO_PROJETO_OK = {"PRATELEIRA", "ESPECIAL"}


def _trim(value: Any, max_len: int) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len]


def normalize_cnpj(value: Any) -> str | None:
    """
    Aceita formatado ou só dígitos; valida dígitos verificadores (core) e
    grava mask XX.XXX.XXX/XXXX-XX.
    """
    if value is None:
        return None
    digits = re.sub(r"\D+", "", str(value))
    if not digits:
        return None
    if len(digits) != 14:
        raise ValueError("CNPJ deve ter 14 dígitos.")
    from core.utils.validators import validate_cnpj

    if not validate_cnpj(digits):
        raise ValueError("CNPJ inválido: dígitos verificadores não conferem.")
    return (
        f"{digits[0:2]}.{digits[2:5]}.{digits[5:8]}/"
        f"{digits[8:12]}-{digits[12:14]}"
    )


def normalize_cep(value: Any) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D+", "", str(value))
    if not digits:
        return None
    if len(digits) not in (8,):
        raise ValueError("CEP deve ter 8 dígitos.")
    return f"{digits[0:5]}-{digits[5:8]}"


def normalize_uf(value: Any) -> str | None:
    s = _trim(value, 2)
    if s is None:
        return None
    uf = s.upper()
    if uf not in _UF_OK:
        raise ValueError("UF inválida.")
    return uf


_COORD_QUANT = Decimal("0.00000001")  # DECIMAL(10,8) / DECIMAL(11,8)


def normalize_coordenada(value: Any, *, label: str, limite: int) -> str | None:
    """
    Latitude/longitude decimal (core.utils.coordinates): aceita vírgula PT-BR,
    valida faixa (±90 / ±180) e arredonda para 8 casas (precisão da coluna).
    """
    if value is None or str(value).strip() == "":
        return None
    from core.utils.coordinates import normalize_coordinate, validate_coordinate

    err = validate_coordinate(value, field_label=label)
    if err:
        raise ValueError(err)
    d = Decimal(normalize_coordinate(value))
    if abs(d) > limite:
        raise ValueError(f"{label} fora do intervalo permitido (-{limite} a {limite}).")
    return str(d.quantize(_COORD_QUANT, rounding=ROUND_HALF_UP))


def normalize_tipo_unidade(value: Any) -> str:
    s = (_trim(value, 32) or "FILIAL").upper()
    if s not in _TIPO_UNIDADE_OK:
        raise ValueError("Tipo de unidade inválido.")
    return s

def normalize_topologia_unidades(value: Any) -> str | None:
    s = _trim(value, 20)
    if s is None:
        return None
    topo = s.upper()
    if topo not in _TOPOLOGIA_UNIDADE_OK:
        raise ValueError("Topologia da unidade inválida.")
    return topo

def normalize_tipo_projeto(value: Any) -> str:
    s = (_trim(value, 32) or "PRATELEIRA").upper()
    if s not in _TIPO_PROJETO_OK:
        raise ValueError("Tipo do projeto inválido.")
    return s


def _as_bool01(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return 1 if value else 0
    s = str(value).strip().lower()
    if s in ("1", "true", "sim", "on", "yes"):
        return 1
    if s in ("0", "false", "nao", "não", "off", "no", ""):
        return 0
    return default


def parse_cliente_payload(raw: dict[str, Any] | None, *, partial: bool = False) -> dict[str, Any]:
    """Valida e normaliza campos de cliente. partial=False exige razao_social."""
    raw = raw or {}
    razao = _trim(raw.get("razao_social"), 255)
    if not partial and not razao:
        raise ValueError("Razão social é obrigatória.")

    out: dict[str, Any] = {}
    if razao is not None or not partial:
        out["razao_social"] = razao

    if "cnpj_cliente" in raw or not partial:
        out["cnpj_cliente"] = normalize_cnpj(raw.get("cnpj_cliente"))
    if "endereco_principal" in raw or not partial:
        out["endereco_principal"] = _trim(raw.get("endereco_principal"), 500)
    if "cidade" in raw or not partial:
        out["cidade"] = _trim(raw.get("cidade"), 100)
    if "uf" in raw or not partial:
        out["uf"] = normalize_uf(raw.get("uf"))
    if "cep" in raw or not partial:
        out["cep"] = normalize_cep(raw.get("cep"))
    if "lider_tecnico" in raw or not partial:
        out["lider_tecnico"] = _trim(raw.get("lider_tecnico"), 128)
    # Antes não era lido: o UPDATE gravava NULL e apagava o GP/CS a cada edição.
    if "nome_gp_cs_clientes" in raw or not partial:
        out["nome_gp_cs_clientes"] = _trim(raw.get("nome_gp_cs_clientes"), 255)

    if "ativo" in raw:
        out["ativo"] = _as_bool01(raw.get("ativo"), 1)

    return out


def parse_unidade_payload(raw: dict[str, Any] | None, *, partial: bool = False) -> dict[str, Any]:
    """Valida unidade. Exige id_cliente e nome_unidade no modo completo."""
    raw = raw or {}
    out: dict[str, Any] = {}

    if "id_cliente" in raw or not partial:
        try:
            id_cliente = int(raw.get("id_cliente"))
        except (TypeError, ValueError):
            raise ValueError("Cliente é obrigatório.") from None
        if id_cliente <= 0:
            raise ValueError("Cliente é obrigatório.")
        out["id_cliente"] = id_cliente

    nome = _trim(raw.get("nome_unidade"), 255)
    if not partial and not nome:
        raise ValueError("Nome da unidade é obrigatório.")
    if nome is not None or not partial:
        out["nome_unidade"] = nome

    if "cnpj_unidade" in raw or not partial:
        out["cnpj_unidade"] = normalize_cnpj(raw.get("cnpj_unidade"))

    if "id_vgr" in raw or not partial:
        from core.utils.text_ids import sanitize_pasted_text
        id_vgr_raw = raw.get("id_vgr")
        if id_vgr_raw is None or str(id_vgr_raw).strip() == "":
            out["id_vgr"] = None
        else:
            out["id_vgr"] = sanitize_pasted_text(id_vgr_raw)[:32] or None

    if "codigo_unidade" in raw or not partial:
        out["codigo_unidade"] = _trim(raw.get("codigo_unidade"), 64)

    if "codigo_identificacao" in raw or not partial:
        out["codigo_identificacao"] = _trim(raw.get("codigo_identificacao"), 64)

    if "tipo_unidade" in raw or not partial:
        out["tipo_unidade"] = normalize_tipo_unidade(raw.get("tipo_unidade"))

    if "tipo_projeto" in raw or not partial:
        out["tipo_projeto"] = normalize_tipo_projeto(raw.get("tipo_projeto"))

    if "contato_unidade" in raw or not partial:
        out["contato_unidade"] = _trim(raw.get("contato_unidade"), 255)     

    if "topologia_unidades" in raw or not partial:
        out["topologia_unidades"] = normalize_topologia_unidades(raw.get("topologia_unidades"))

    if "endereco" in raw or not partial:
        out["endereco"] = _trim(raw.get("endereco"), 500)

    if "bairro" in raw or not partial:
        out["bairro"] = _trim(raw.get("bairro"), 120)

    if "cidade" in raw or not partial:
        out["cidade"] = _trim(raw.get("cidade"), 100)

    if "uf" in raw or not partial:
        out["uf"] = normalize_uf(raw.get("uf"))

    if "cep" in raw or not partial:
        out["cep"] = normalize_cep(raw.get("cep"))

    # Coordenadas (core.utils.coordinates) — antes eram ignoradas no save.
    if "latitude" in raw or not partial:
        out["latitude"] = normalize_coordenada(raw.get("latitude"), label="Latitude", limite=90)
    if "longitude" in raw or not partial:
        out["longitude"] = normalize_coordenada(
            raw.get("longitude"), label="Longitude", limite=180
        )
    if "latitude" in out and "longitude" in out:
        if bool(out["latitude"]) != bool(out["longitude"]):
            raise ValueError("Informe latitude e longitude juntas (ou deixe ambas vazias).")

    if "ha" in raw or not partial:
        out["ha"] = _as_bool01(raw.get("ha"), 0)

    if "ativo" in raw:
        out["ativo"] = _as_bool01(raw.get("ativo"), 1)

    return out


def apply_matriz_endereco_from_cliente(
    data: dict[str, Any],
    cliente: dict[str, Any] | None,
) -> dict[str, Any]:
    """MATRIZ: se endereço vazio, copia do cliente (ainda editável)."""
    if not cliente:
        return data
    if (data.get("tipo_unidade") or "").upper() != "MATRIZ":
        return data
    if not data.get("endereco") and cliente.get("endereco_principal"):
        data["endereco"] = cliente.get("endereco_principal")
    if not data.get("cidade") and cliente.get("cidade"):
        data["cidade"] = cliente.get("cidade")
    if not data.get("uf") and cliente.get("uf"):
        data["uf"] = cliente.get("uf")
    if not data.get("cep") and cliente.get("cep"):
        data["cep"] = cliente.get("cep")
    return data


_TIPO_SERVICO_OK = {"SDWAN", "SDWIFI", "SDLAN"}
_TIPO_LINK_OK = {
    "WAN", "LAN", "LOOPBACK_VIVO", "LOOPBACK_CLIENTE", "LOOPBACK_ON_BGP",
    "TRANSITO", "TUNNEL", "DHCP_SERVER", "EXCLUDED_RANGE", "AP_RANGE", "REDE_VLAN",
}
_TIPO_LINK_UNIDADE = _TIPO_LINK_OK - {"WAN"}
_MODO_CONEXAO_OK = {"STATIC", "DHCP", "PPPOE", "MPLS"}


def is_tipo_link_unidade(tipo: str | None) -> bool:
    """LAN+ = conectividade da unidade (sem equipamento). WAN = no equipamento."""
    return bool(tipo) and str(tipo).upper() in _TIPO_LINK_UNIDADE


def parse_equipamento_payload(raw: dict[str, Any] | None, *, partial: bool = False) -> dict[str, Any]:
    raw = raw or {}
    out: dict[str, Any] = {}

    if "id_unidade" in raw or not partial:
        try:
            id_unidade = int(raw.get("id_unidade"))
        except (TypeError, ValueError):
            raise ValueError("Unidade é obrigatória.") from None
        if id_unidade <= 0:
            raise ValueError("Unidade é obrigatória.")
        out["id_unidade"] = id_unidade

    serial = _trim(raw.get("serial"), 100)
    if not partial and not serial:
        raise ValueError("Serial é obrigatório.")
    if serial is not None or not partial:
        out["serial"] = serial

    if "vendor" in raw or not partial:
        out["vendor"] = _trim(raw.get("vendor"), 50)
    if "modelo" in raw or not partial:
        out["modelo"] = _trim(raw.get("modelo"), 80)

    # Serial Fortinet: só quando vendor/modelo do payload indicam a família
    # (core.utils.fortinet_serial — extensível por novos fragments de modelo).
    from core.utils.fortinet_serial import (
        infer_modelo_from_serial,
        is_fortinet_family,
        normalizar_serial,
        validate_serial_fortinet_format,
    )

    vendor_chk = out.get("vendor")
    modelo_chk = out.get("modelo")
    if is_fortinet_family(vendor_chk, modelo_chk):
        serial_chk = out.get("serial")
        if serial_chk is not None or not partial:
            err = validate_serial_fortinet_format(serial_chk, obrigatorio=not partial)
            if err:
                raise ValueError(err)
            if serial_chk:
                out["serial"] = normalizar_serial(serial_chk)
                # Modelo vem do serial (fragmento 40F/120G…); alias «FG 40F» vira
                # rótulo oficial — mesmo comportamento do bindModeloLockedFromSerial.
                inferido = infer_modelo_from_serial(out["serial"], strict=True)
                if inferido:
                    out["modelo"] = inferido
                elif out.get("modelo"):
                    from core.utils.fortinet_serial import normalize_modelo_fortigate

                    out["modelo"] = normalize_modelo_fortigate(out["modelo"])[:80] or None
    if "hostname" in raw or not partial:
        from core.utils.text_ids import normalizar_hostname, validate_hostname

        host_raw = raw.get("hostname")
        if host_raw is None or str(host_raw).strip() == "":
            out["hostname"] = None
        else:
            err_h = validate_hostname(host_raw)
            if err_h:
                raise ValueError(err_h)
            out["hostname"] = normalizar_hostname(host_raw)[:80]
    if "licenca" in raw or not partial:
        out["licenca"] = _trim(raw.get("licenca"), 120)
    if "tipo_servico" in raw or not partial:
        ts = _trim(raw.get("tipo_servico"), 16)
        if ts:
            ts = ts.upper()
            if ts not in _TIPO_SERVICO_OK:
                raise ValueError("Tipo de serviço inválido.")
            out["tipo_servico"] = ts
        else:
            out["tipo_servico"] = None
    if "tkt_sae" in raw or not partial:
        out["tkt_sae"] = _trim(raw.get("tkt_sae"), 64)
    if "tkt_noc" in raw or not partial:
        from core.utils.ticket_noc import (
            normalizar_ticket_noc,
            validate_ticket_noc_format,
        )

        tkt = raw.get("tkt_noc")
        if tkt is None or str(tkt).strip() == "":
            out["tkt_noc"] = None
        else:
            err_t = validate_ticket_noc_format(tkt)
            if err_t:
                raise ValueError(err_t)
            out["tkt_noc"] = normalizar_ticket_noc(tkt)[:64]

    if "fortcloud_key" in raw:
        fk = raw.get("fortcloud_key")
        if fk is None or str(fk).strip() == "":
            out["fortcloud_key"] = None
            out["_clear_or_skip_fortcloud"] = True
        else:
            out["fortcloud_key"] = str(fk).strip()[:255]
            out["_set_fortcloud"] = True

    if "ativo" in raw:
        out["ativo"] = _as_bool01(raw.get("ativo"), 1)
    return out


# ---------------------------------------------------------------------------
# Regras de rede/link reaproveitadas do core (calculadora IPv4, operadora,
# VLAN, ranges, pendências VIVO). Mensagens sem SQL/traceback.
# ---------------------------------------------------------------------------

_TIPOS_LINK_COM_RANGE = {"DHCP_SERVER", "EXCLUDED_RANGE", "AP_RANGE"}
_VLAN_RE = re.compile(r"^(?:VLAN)?(\d{1,4})$", re.IGNORECASE)


def _link_label(out: dict[str, Any]) -> str:
    return f"Link {out.get('tipo_link') or ''}".strip()


def _ip_input(value: Any) -> str:
    """Remove espaços e troca vírgula por ponto (colagem PT-BR / Excel)."""
    from core.utils.network import normalize_ip_text

    return normalize_ip_text(value).replace(",", ".")


def _mask_from_prefix(text: str) -> str | None:
    """'10.0.0.1/30' → '255.255.255.252'; None se não houver prefixo válido."""
    if "/" not in text:
        return None
    try:
        return str(ipaddress.IPv4Network(f"0.0.0.0/{text.split('/', 1)[1]}").netmask)
    except ValueError:
        return None


def parse_operadora(select_value: Any, outros_value: Any = None) -> str | None:
    """VIVO/CLARO/TIM/OI ou OUTROS + texto (core.utils.operadora). Sentinel não é gravado."""
    from core.utils.operadora import OPERADORA_SENTINEL_OUTROS, resolve_operadora

    sel = re.sub(r"\s+", " ", str(select_value or "").strip()).upper()
    op = resolve_operadora(select_value, outros_value)
    if sel == OPERADORA_SENTINEL_OUTROS and not op:
        raise ValueError("Operadora «OUTROS»: informe o nome da operadora.")
    return op or None


def normalize_vlan(value: Any) -> str | None:
    """VLAN ID 802.1Q (1–4094). Aceita '100' ou 'VLAN 100'; grava só o número."""
    s = _trim(value, 50)
    if s is None:
        return None
    m = _VLAN_RE.match(re.sub(r"\s+", "", s))
    if not m or not 1 <= int(m.group(1)) <= 4094:
        raise ValueError("VLAN inválida: informe o ID numérico entre 1 e 4094.")
    return str(int(m.group(1)))


def normalize_id_vgr_equipamento(value: Any) -> str | None:
    """ID VGR do equipamento: limpa colagem (ZWSP, aspas, espaços) — core.text_ids."""
    from core.utils.text_ids import sanitize_pasted_text

    s = sanitize_pasted_text(value)
    if not s:
        return None
    if len(s) > 64:
        raise ValueError("ID VGR do equipamento aceita no máximo 64 caracteres.")
    return s


def _validate_link_rede(out: dict[str, Any]) -> None:
    """
    Campos isolados primeiro (IPv4, máscara contígua) e depois o grupo
    (core.utils.network.validate_ip_mask_group): gateway e subrede na mesma
    rede do IP; IP não pode ser rede/broadcast. Prefixo CIDR alimenta a
    máscara vazia (ou precisa conferir com ela). Ranges dentro da rede.
    """
    from core.utils.network import (
        canonicalize_ipv4,
        canonicalize_network_address,
        ipv4_interface,
        ipv4_network_address,
        validate_ip_mask_group,
        validate_ipv4_field,
        validate_netmask_field,
    )

    label = _link_label(out)

    if out.get("mascara"):
        mask_txt = _ip_input(out["mascara"])
        err = validate_netmask_field(mask_txt, label="Máscara")
        if err:
            raise ValueError(err)
        out["mascara"] = canonicalize_ipv4(mask_txt)

    def _absorve_prefixo(txt: str, campo: str) -> None:
        pm = _mask_from_prefix(txt)
        if not pm:
            return
        if not out.get("mascara"):
            out["mascara"] = pm
        elif out["mascara"] != pm:
            raise ValueError(
                f"{label}: o prefixo /{txt.split('/', 1)[1]} de «{campo}» não confere "
                f"com a máscara {out['mascara']} (esperado {pm})."
            )

    if out.get("ip_address"):
        ip_txt = _ip_input(out["ip_address"])
        err = validate_ipv4_field(ip_txt, label="IP", allow_cidr=True)
        if err:
            raise ValueError(err)
        _absorve_prefixo(ip_txt, "IP")
        out["ip_address"] = ip_txt

    if out.get("gateway"):
        gw_txt = _ip_input(out["gateway"])
        err = validate_ipv4_field(gw_txt, label="Gateway", allow_cidr=False)
        if err:
            raise ValueError(err)
        out["gateway"] = gw_txt

    if out.get("subrede"):
        sub_txt = _ip_input(out["subrede"])
        err = validate_ipv4_field(sub_txt, label="Subrede", allow_cidr=True)
        if err:
            raise ValueError(err)
        _absorve_prefixo(sub_txt, "Subrede")
        out["subrede"] = canonicalize_network_address(sub_txt)

    err = validate_ip_mask_group(
        ip=out.get("ip_address"),
        mascara=out.get("mascara"),
        gateway=out.get("gateway"),
        subrede=out.get("subrede"),
        label=label,
    )
    if err:
        raise ValueError(err)

    # Sem IP (ex.: DHCP_SERVER): a subrede precisa ser o endereço de rede da máscara.
    if not out.get("ip_address") and out.get("subrede") and out.get("mascara"):
        net = ipv4_network_address(out["subrede"], out["mascara"])
        if net and net != out["subrede"]:
            raise ValueError(
                f"{label}: subrede {out['subrede']} não é endereço de rede para a "
                f"máscara {out['mascara']} (esperado {net})."
            )

    for key, lbl in (("range_start", "Início do range"), ("range_end", "Fim do range")):
        if out.get(key):
            v = _ip_input(out[key])
            err = validate_ipv4_field(v, label=lbl, allow_cidr=False)
            if err:
                raise ValueError(err)
            out[key] = canonicalize_ipv4(v)

    if "range_start" in out and "range_end" in out:
        rs, rend = out.get("range_start"), out.get("range_end")
        if bool(rs) != bool(rend):
            raise ValueError(f"{label}: informe o início e o fim do range.")
        if rs and rend:
            a, b = ipaddress.IPv4Address(rs), ipaddress.IPv4Address(rend)
            if a > b:
                raise ValueError(
                    f"{label}: início do range ({rs}) maior que o fim ({rend})."
                )
            base = out.get("ip_address") or out.get("subrede")
            iface = (
                ipv4_interface(base, out.get("mascara"))
                if base and out.get("mascara")
                else None
            )
            if iface is not None:
                net = iface.network
                for addr, lbl in ((a, "Início do range"), (b, "Fim do range")):
                    if addr not in net:
                        raise ValueError(
                            f"{label}: {lbl} {addr} fora da rede "
                            f"{net.network_address}/{net.prefixlen}."
                        )
                    if net.prefixlen < 31 and addr in (
                        net.network_address,
                        net.broadcast_address,
                    ):
                        raise ValueError(
                            f"{label}: {lbl} {addr} não pode ser o endereço de "
                            "rede nem o de broadcast."
                        )


def link_avisos(data: dict[str, Any]) -> list[str]:
    """
    Pendências VIVO (core.utils.link_vivo) — avisos, NÃO bloqueiam o save:
    máscara /30·/31·/29 (MPLS), gateway = IP WAN − 1, designador (LP) vazio.
    """
    tipo = str(data.get("tipo_link") or "").upper()
    modo = str(data.get("modo_conexao") or "").upper()
    if tipo != "WAN" or modo not in ("STATIC", "MPLS"):
        return []
    from core.utils.link_vivo import collect_vivo_link_pendencias

    return collect_vivo_link_pendencias(
        modo=modo,
        operadora=data.get("operadora"),
        ip=data.get("ip_address"),
        mascara=data.get("mascara"),
        gateway=data.get("gateway"),
        designador=data.get("designador"),
    )


def parse_link_payload(raw: dict[str, Any] | None, *, partial: bool = False) -> dict[str, Any]:
    raw = raw or {}
    out: dict[str, Any] = {}

    if "id_unidade" in raw or not partial:
        try:
            id_unidade = int(raw.get("id_unidade"))
        except (TypeError, ValueError):
            raise ValueError("Unidade é obrigatória.") from None
        if id_unidade <= 0:
            raise ValueError("Unidade é obrigatória.")
        out["id_unidade"] = id_unidade

    if "tipo_link" in raw or not partial:
        tl = (_trim(raw.get("tipo_link"), 32) or "").upper()
        if not tl or tl not in _TIPO_LINK_OK:
            raise ValueError("Tipo de link inválido.")
        out["tipo_link"] = tl

    tipo_eff = out.get("tipo_link")

    # Equipamento: obrigatório só em WAN; LAN+ = conectividade da unidade (NULL).
    if "id_equipamento" in raw or (not partial and tipo_eff == "WAN"):
        if tipo_eff and tipo_eff != "WAN":
            out["id_equipamento"] = None
        elif tipo_eff == "WAN" or (
            "id_equipamento" in raw and (raw.get("id_equipamento") not in (None, ""))
        ):
            try:
                id_eq = int(raw.get("id_equipamento"))
            except (TypeError, ValueError):
                raise ValueError("Equipamento é obrigatório para link WAN.") from None
            if id_eq <= 0:
                raise ValueError("Equipamento é obrigatório para link WAN.")
            out["id_equipamento"] = id_eq
        elif not partial and (tipo_eff is None or tipo_eff == "WAN"):
            raise ValueError("Equipamento é obrigatório para link WAN.")
        else:
            out["id_equipamento"] = None
    elif tipo_eff and tipo_eff != "WAN":
        out["id_equipamento"] = None

    if "modo_conexao" in raw or not partial:
        mc = _trim(raw.get("modo_conexao"), 16)
        if mc:
            mc = mc.upper()
            if mc not in _MODO_CONEXAO_OK:
                raise ValueError("Modo de conexão inválido.")
            out["modo_conexao"] = mc
        else:
            out["modo_conexao"] = None

    # Modo STATIC/DHCP/PPPOE/MPLS só faz sentido em WAN.
    if (out.get("tipo_link") or tipo_eff) and (out.get("tipo_link") or tipo_eff) != "WAN":
        out["modo_conexao"] = None
        out["id_equipamento"] = None

    if "ordem" in raw or not partial:
        ordem_raw = raw.get("ordem")
        if ordem_raw is None or str(ordem_raw).strip() == "":
            out["ordem"] = None
        else:
            try:
                out["ordem"] = int(ordem_raw)
            except (TypeError, ValueError):
                raise ValueError("Ordem inválida.") from None

    for key, maxlen in (
        ("id_vgr_link", 64),
        ("identificador", 50),
        ("designador", 100),
        ("ip_address", 50),
        ("mascara", 50),
        ("gateway", 50),
        ("subrede", 50),
        ("vlan", 50),
        ("velocidade", 50),
        ("range_start", 50),
        ("range_end", 50),
    ):
        if key in raw or not partial:
            out[key] = _trim(raw.get(key), maxlen)

    from core.utils.link_required import validate_link_required_by_modo
    from core.utils.network import validate_wan_gateway_distinct
    from core.utils.text_ids import (
        sanitize_pasted_text,
        validate_designador_vivo_format,
        validate_id_vgr_link_format,
        validate_no_whitespace,
    )
    from core.utils.velocity import normalize_velocity_mbps, validate_velocity_mbps

    # Operadora: select principal (VIVO/CLARO/TIM/OI) ou OUTROS + texto livre
    # (core.utils.operadora). Precisa vir antes do designador (regra só VIVO).
    if "operadora" in raw or "operadora_outros" in raw or not partial:
        out["operadora"] = parse_operadora(raw.get("operadora"), raw.get("operadora_outros"))

    if "id_vgr_link" in out and out.get("id_vgr_link"):
        out["id_vgr_link"] = sanitize_pasted_text(out["id_vgr_link"])[:64] or None
        err_id = validate_id_vgr_link_format(out["id_vgr_link"])
        if err_id:
            raise ValueError(err_id)
    if "designador" in out and out.get("designador"):
        out["designador"] = sanitize_pasted_text(out["designador"])[:100] or None
        err_ws = validate_no_whitespace(out["designador"], "Designador")
        if err_ws:
            raise ValueError(err_ws)
        err_des = validate_designador_vivo_format(
            out["designador"], out.get("operadora")
        )
        if err_des:
            raise ValueError(err_des)

    if out.get("velocidade"):
        err_vel = validate_velocity_mbps(out["velocidade"])
        if err_vel:
            raise ValueError(err_vel)
        out["velocidade"] = normalize_velocity_mbps(out["velocidade"]) or out["velocidade"]

    if out.get("vlan"):
        out["vlan"] = normalize_vlan(out["vlan"])

    # IP / máscara / gateway / subrede / ranges + calculadora (core.utils.network).
    _validate_link_rede(out)

    err_pair = validate_wan_gateway_distinct(
        out.get("ip_address"),
        out.get("gateway"),
        label=_link_label(out),
    )
    if err_pair:
        raise ValueError(err_pair)

    for secret in ("contato_operadora", "telefone_reparo", "pppoe_user", "pppoe_pass"):
        if secret in raw:
            val = raw.get(secret)
            if val is None or str(val).strip() == "":
                out[secret] = None
                out[f"_skip_{secret}"] = True
            else:
                out[secret] = str(val).strip()[:255]
                out[f"_set_{secret}"] = True

    # Obrigatórios por modo (core.utils.link_required):
    #   STATIC/MPLS → IP + máscara + gateway; VIVO → ID VGR + porta;
    #   PPPOE → usuário/senha (novos ou já gravados: has_pppoe_*).
    if not partial:
        req_payload = dict(out)
        req_payload["_require_pppoe_creds"] = True
        req_payload["has_pppoe_user"] = _as_bool01(raw.get("has_pppoe_user"), 0)
        req_payload["has_pppoe_pass"] = _as_bool01(raw.get("has_pppoe_pass"), 0)
        err_req = validate_link_required_by_modo(req_payload, exigir_mascara=True)
        if err_req:
            raise ValueError(err_req)

    if "ativo" in raw:
        out["ativo"] = _as_bool01(raw.get("ativo"), 1)
    return out


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_cpf(value: Any) -> str | None:
    """Aceita formatado ou só dígitos; valida DV; grava XXX.XXX.XXX-XX."""
    if value is None:
        return None
    digits = re.sub(r"\D+", "", str(value))
    if not digits:
        return None
    if len(digits) != 11:
        raise ValueError("CPF deve ter 11 dígitos.")
    from core.utils.validators import validate_cpf

    if not validate_cpf(digits):
        raise ValueError("CPF inválido.")
    return f"{digits[0:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"


def normalize_rg(value: Any) -> str | None:
    return _trim(value, 32)


def normalize_telefone_field(value: Any) -> str | None:
    return _trim(value, 64)


def normalize_email(value: Any) -> str:
    s = _trim(value, 255)
    if not s:
        raise ValueError("E-mail inválido.")
    if not _EMAIL_RE.match(s):
        raise ValueError(f"E-mail inválido: {s[:40]}")
    return s.lower()


def parse_emails_list(raw: Any) -> list[str]:
    """Lista 1–N de e-mails únicos (ordem preservada)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[,;\n]+", raw)
    elif isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        raise ValueError("Lista de e-mails inválida.")
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if p is None or str(p).strip() == "":
            continue
        em = normalize_email(p)
        if em in seen:
            continue
        seen.add(em)
        out.append(em)
    if len(out) > 20:
        raise ValueError("Máximo de 20 e-mails por Field.")
    return out


def parse_contratada_ids(raw: Any) -> list[int]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValueError("Contratadas inválidas.")
    out: list[int] = []
    seen: set[int] = set()
    for item in raw:
        try:
            cid = int(item)
        except (TypeError, ValueError):
            raise ValueError("Contratada inválida.") from None
        if cid <= 0 or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def parse_field_payload(raw: dict[str, Any] | None, *, partial: bool = False) -> dict[str, Any]:
    """
    Payload Field (P10).

    PII (rg/cpf): presente no dict só se enviado; string vazia = limpar.
    E-mails: chave ``emails`` (lista) substitui o conjunto quando presente.
    Contratadas: chave ``id_contratadas`` (lista) quando presente.
    """
    raw = raw or {}
    out: dict[str, Any] = {}

    nome = _trim(raw.get("nome"), 128)
    if not partial and not nome:
        raise ValueError("Nome é obrigatório.")
    if nome is not None or not partial:
        out["nome"] = nome

    if "telefone" in raw or not partial:
        out["telefone"] = normalize_telefone_field(raw.get("telefone"))

    if "rg" in raw:
        out["rg"] = normalize_rg(raw.get("rg"))
        out["_set_rg"] = True
    if "cpf" in raw:
        out["cpf"] = normalize_cpf(raw.get("cpf"))
        out["_set_cpf"] = True

    if "emails" in raw:
        out["emails"] = parse_emails_list(raw.get("emails"))
        out["_set_emails"] = True
    elif not partial:
        out["emails"] = []
        out["_set_emails"] = True

    if "id_contratadas" in raw:
        out["id_contratadas"] = parse_contratada_ids(raw.get("id_contratadas"))
        out["_set_contratadas"] = True
    elif not partial:
        out["id_contratadas"] = []
        out["_set_contratadas"] = True

    if "ativo" in raw:
        out["ativo"] = _as_bool01(raw.get("ativo"), 1)
    return out


def parse_contratada_payload(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    nome = _trim(raw.get("nome_contratada") or raw.get("nome"), 255)
    if not nome:
        raise ValueError("Nome da contratada é obrigatório.")
    out: dict[str, Any] = {"nome_contratada": nome}
    if raw.get("cnpj") not in (None, ""):
        out["cnpj"] = normalize_cnpj(raw.get("cnpj"))
    else:
        out["cnpj"] = None
    if "ativo" in raw:
        out["ativo"] = _as_bool01(raw.get("ativo"), 1)
    else:
        out["ativo"] = 1
    return out


def mask_pii_for_historico(label: str, value: str | None) -> str | None:
    """Não grava PII em claro no histórico."""
    if value is None or str(value).strip() == "":
        return None
    digits = re.sub(r"\D+", "", str(value))
    if label == "cpf" and len(digits) >= 4:
        return f"***{digits[-4:]}"
    return "***"