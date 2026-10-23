"""Geração e validação do CSV de Blueprint PRODESP (SD-WAN)."""
import os
import csv
import re
from datetime import datetime

from prodesp.prodesp.blueprint.blueprint_catalog import (
    DEFAULT_DEVICE_BLUEPRINT,
    rule_for_unidade,
)
from prodesp.prodesp.blueprint.link_velocity_rules import normalize_velocity_mbps
from prodesp.prodesp.blueprint.prodesp_equipment import (
    blueprint_intf_fields_for_equipment,
    infer_modelo_equipamento_from_serial,
    resolve_fortigate_model_fragment,
)
from prodesp.prodesp.db_field_limits import (
    UNIDADES_LAN_EXTRA_SPEC,
    UNIDADES_MV_CIDR_JS_KEYS,
    UNIDADES_MV_OPCIONAIS_SPEC,
)

# Definindo CSV_DIR relativo ao arquivo atual para evitar problemas de importação circular se prodesp.app não estiver carregado
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CSV_DIR = os.path.join(BASE_DIR, "static", "csv_prodesp")

def cidr_to_mask(cidr):
    """Converte prefixo CIDR (ex: /24) para máscara decimal (ex: 255.255.255.0)"""
    if cidr is None or str(cidr).strip() == "":
        return ""
    try:
        prefix = int(str(cidr).replace("/", ""))
        if prefix < 0 or prefix > 32:
            return ""
        if prefix == 0:
            return "0.0.0.0"
        mask = (0xffffffff >> (32 - prefix)) << (32 - prefix)
        return f"{(mask >> 24) & 0xff}.{(mask >> 16) & 0xff}.{(mask >> 8) & 0xff}.{mask & 0xff}"
    except Exception:
        return ""


def mask_to_cidr_prefix(mask_dotted: str) -> str:
    """'255.255.255.0' → '/24'; inválido → ''."""
    raw = (mask_dotted or "").strip()
    if not raw:
        return ""
    try:
        parts = [int(p) for p in raw.split(".")]
        if len(parts) != 4 or any(p < 0 or p > 255 for p in parts):
            return ""
        bits = 0
        for p in parts:
            bits = (bits << 8) | p
        # Conta bits 1 contíguos a partir do MSB
        prefix = 0
        seen_zero = False
        for i in range(31, -1, -1):
            if (bits >> i) & 1:
                if seen_zero:
                    return ""
                prefix += 1
            else:
                seen_zero = True
        return f"/{prefix}"
    except Exception:
        return ""


def format_mask_option_label(mask_dotted: str, cidr: str | None = None) -> str:
    """'255.255.255.0' + '/24' → '255.255.255.0 - /24'."""
    m = (mask_dotted or "").strip()
    c = (cidr or mask_to_cidr_prefix(m) or "").strip()
    if m and c:
        return f"{m} - {c}"
    return m or c or ""


def split_ip_and_mask_from_cidr(value):
    """'10.1.1.1/24' → ('10.1.1.1', '255.255.255.0'); sem CIDR → (ip, '')."""
    raw = (value or "").strip()
    if not raw:
        return "", ""
    ip = raw.split("/")[0].strip()
    cidr_match = re.search(r"/(\d+)", raw)
    mask = cidr_to_mask(cidr_match.group(0)) if cidr_match else ""
    return ip, mask


def apply_mask_to_ip_cidr(ip_cidr: str, mask_dotted: str) -> str:
    """Troca o /nn de um IP/CIDR pela máscara dotted escolhida."""
    raw = (ip_cidr or "").strip()
    if not raw:
        return raw
    ip = raw.split("/")[0].strip()
    prefix = mask_to_cidr_prefix(mask_dotted)
    if not ip or not prefix:
        return raw
    return f"{ip}{prefix}"


def _lan_ip_filled(value) -> bool:
    return bool((value or "").strip())


def _lan_tier_filled(dados_unidade, ip_col: str, rede_col: str | None = None) -> bool:
    """Nível LAN conta se houver IP e/ou Rede LAN preenchidos."""
    u = dados_unidade or {}
    if _lan_ip_filled(u.get(ip_col)):
        return True
    if rede_col and _lan_ip_filled(u.get(rede_col)):
        return True
    return False


def count_lan_ips_filled(dados_unidade) -> int:
    """
    Conta níveis LAN em cascata: 1 (LAN1) … 4 (LAN1+SEC+TER+QUA).
    Cada nível SEC/TER/QUA conta com IP **ou** Rede LAN.
    LAN 1 exige IP (Rede LAN 1 é calculada a partir dele).
    Buracos (ex.: TER sem SEC) não avançam o contador.
    """
    u = dados_unidade or {}
    if not _lan_tier_filled(u, "ip_lan_01_unidades"):
        return 0
    n = 1
    if not _lan_tier_filled(u, "mv_ip_lan_sec_unidades", "mv_rede_lan_sec_unidades"):
        return n
    n = 2
    if not _lan_tier_filled(u, "mv_ip_lan_ter_unidades", "mv_rede_lan_ter_unidades"):
        return n
    n = 3
    if not _lan_tier_filled(u, "mv_ip_lan_qua_unidades", "mv_rede_lan_qua_unidades"):
        return n
    return 4


def _lan_count_suffix(lan_count: int) -> str:
    n = max(1, min(4, int(lan_count or 1)))
    return {1: "_1", 2: "_1_2", 3: "_1_2_3", 4: "_1_2_3_4"}[n]


def _apply_lan_count_to_device_blueprint(template: str, lan_count: int) -> tuple[str, str]:
    """
    Ajusta o segmento REDE_LAN_* conforme níveis LAN (IP e/ou Rede) preenchidos.
    Ex.: …_REDE_LAN_1 → …_REDE_LAN_1_2_3; TJ …_REDE_LAN_1_VOZ_WIFI → …_1_2_3_VOZ_WIFI.
    Retorna (template_ajustado, motivo_pt).
    """
    n = max(1, min(4, int(lan_count or 1)))
    suffix = _lan_count_suffix(n)
    labels = {1: "LAN 1", 2: "LAN 1 + SEC", 3: "LAN 1 + SEC + TER", 4: "LAN 1 + SEC + TER + QUA"}
    motivo = (
        f"Device Blueprint escolhido pelo acrônimo e pelos IPs/Redes LAN preenchidos "
        f"({labels[n]} → REDE_LAN{suffix})."
    )
    tpl = template or ""
    if not tpl or "REDE_LAN" not in tpl.upper():
        return tpl, motivo
    novo = _RE_REDE_LAN_SEGMENT.sub(rf"\1{suffix}", tpl, count=1)
    return novo, motivo


def resolve_device_blueprint_detail(dados_unidade, dados_equipamento=None) -> dict:
    """
    Resolve Device Blueprint + motivo (para confirmação / CSV).
    Fonte: catálogo ``prodesp_blueprint_secretaria`` (ou seed/teste via blueprint_catalog).
    """
    acr = (dados_unidade.get("acronimo_unidades") or "").strip().upper()
    eq = dados_equipamento or {}
    frag = resolve_fortigate_model_fragment(
        eq.get("modelo_equipamentos") or eq.get("modelo"),
        eq.get("serial_equipamentos") or eq.get("serial"),
    )
    rule = rule_for_unidade(dados_unidade)
    has_custom = rule is not None
    base = (rule.device_blueprint_template if has_custom else DEFAULT_DEVICE_BLUEPRINT) or DEFAULT_DEVICE_BLUEPRINT
    with_modelo = _apply_modelo_to_device_blueprint(base, frag)
    lan_count = count_lan_ips_filled(dados_unidade)
    aplica_sufixo_lan = (
        has_custom
        and bool(rule.aplica_sufixo_lan_dinamico)
        and "REDE_LAN" in with_modelo.upper()
        and lan_count >= 1
    )
    if aplica_sufixo_lan:
        final, motivo = _apply_lan_count_to_device_blueprint(with_modelo, lan_count)
    else:
        final = with_modelo
        if has_custom and not rule.aplica_sufixo_lan_dinamico:
            motivo = (
                f"Device Blueprint fixo do acrônimo '{acr}' "
                f"(sem expansão REDE_LAN_1/_1_2/_1_2_3/_1_2_3_4)."
            )
        elif lan_count < 1 and has_custom:
            motivo = (
                f"Device Blueprint base do acrônimo '{acr}' "
                f"(IP/Rede LAN ainda não informados para sufixo dinâmico)."
            )
        else:
            motivo = (
                f"Device Blueprint padrão para acrônimo '{acr or '—'}' "
                f"(sem sufixo dinâmico REDE_LAN)."
            )
    return {
        "device_blueprint": final,
        "device_blueprint_base": with_modelo,
        "lan_count": lan_count,
        "motivo": motivo,
        "acronimo": acr,
        "modelo_fragment": frag,
    }

def get_network_address(ip_with_cidr):
    """Retorna o endereço de rede (final .0) a partir de um IP/CIDR"""
    if not ip_with_cidr:
        return ""
    ip = ip_with_cidr.split('/')[0]
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0"
    return ""

def get_ip_lan_minus_one(ip_with_cidr):
    """
    Endereço de rede LAN = IP do ip_lan (sem máscara) com -1 no valor de 32 bits.
    Usado em DIPOL (MV_10_), DETRAN regra nova (MV_REDE_LAN) e demais unidades
    do modelo blueprint REDE_LAN com regra ``nova``.
    Ex.: 10.75.13.193/26 -> 10.75.13.192; 10.138.42.129/29 -> 10.138.42.128
    """
    if not ip_with_cidr:
        return ""
    ip = ip_with_cidr.split("/")[0].strip()
    parts = ip.split(".")
    if len(parts) != 4:
        return ""
    try:
        o = [int(p) for p in parts]
        n = (o[0] << 24) | (o[1] << 16) | (o[2] << 8) | o[3]
        n = (n - 1) & 0xFFFFFFFF
        return f"{(n >> 24) & 0xFF}.{(n >> 16) & 0xFF}.{(n >> 8) & 0xFF}.{n & 0xFF}"
    except (ValueError, TypeError):
        return ""


# Alias legado (DIPOL / código anterior)
get_ip_lan_mv_10_dipol = get_ip_lan_minus_one

def get_ip_with_suffix(ip_with_cidr, suffix):
    """Retorna o IP com um sufixo específico (ex: .1, .10, .250)"""
    if not ip_with_cidr:
        return ""
    ip = ip_with_cidr.split('/')[0]
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.{suffix}"
    return ""

def format_velocity(velocity):
    """Velocidade de link no CSV em Mbps (sem zeros extras no final)."""
    return normalize_velocity_mbps(velocity)


def _legado_omitir_dhcp_server(dados_unidade) -> bool:
    """Builder legado: omite colunas MV_dhcp_server_1_* (ex. DIPOL no catálogo)."""
    rule = rule_for_unidade(dados_unidade)
    return bool(rule and rule.legado_omitir_dhcp_server)


# Opções de máscara na confirmação do blueprint (dotted + CIDR).
BLUEPRINT_MASK_OPTIONS: tuple[tuple[str, str], ...] = tuple(
    (cidr_to_mask(prefix), f"/{prefix}") for prefix in range(0, 33)
)


_RE_REDE_LAN_SEGMENT = re.compile(
    r"(REDE_LAN)(?:_1(?:_2(?:_3(?:_4)?)?)?)?",
    re.IGNORECASE,
)

_RE_DEVICE_MODELO_FRAGMENT = re.compile(
    r"_(?:400F|200F|100F|90G|80F|70F|60F|40F)(?=_|$)",
    re.IGNORECASE,
)


def _apply_modelo_to_device_blueprint(template: str, modelo_fragment: str) -> str:
    """Troca o fragmento de modelo no template (ex.: _40F_ → _60F_)."""
    frag = (modelo_fragment or "40F").strip().upper() or "40F"
    if not template:
        return template
    if not _RE_DEVICE_MODELO_FRAGMENT.search(template):
        return template
    return _RE_DEVICE_MODELO_FRAGMENT.sub(f"_{frag}", template)


def _uses_blueprint_rede_lan_modelo(dados_unidade):
    """
    Layout CSV REDE_LAN vs legado (MV_10_).
    - Com regra no catálogo: usa o layout da linha.
    - Sem regra (fallback BP_OES): REDE_LAN (não mais o builder legado).
    """
    rule = rule_for_unidade(dados_unidade)
    if rule is None:
        return True
    return rule.layout_csv == "rede_lan"


def _normalize_rede_lan_regra(regra):
    """
    Regra de cálculo do endereço de rede LAN:
    - nova: IP LAN - 1 (padrão)
    - antiga: endereço de rede .0
    """
    r = (regra or "nova").strip().lower()
    if r in ("antiga", "old", "legado"):
        return "antiga"
    return "nova"


def _resolve_rede_lan(ip_lan_base, regra):
    if _normalize_rede_lan_regra(regra) == "antiga":
        return get_network_address(ip_lan_base)
    return get_ip_lan_minus_one(ip_lan_base)


def _rede_lan_regra_for_unidade(dados_unidade):
    """``.0`` se rule.rede_lan_regra == antiga; senão IP LAN − 1."""
    rule = rule_for_unidade(dados_unidade)
    if rule and _normalize_rede_lan_regra(rule.rede_lan_regra) == "antiga":
        return "antiga"
    return "nova"


def _resolve_dhcp_lan_range(dados_unidade, ip_lan_base: str) -> tuple[str, str]:
    """
    MV_DHCP_START_LAN / MV_DHCP_END_LAN a partir do IP LAN (mesmo prefixo /3 octetos).
    Sem octetos no catálogo → colunas vazias (coluna ainda emitida no REDE_LAN).
    """
    rule = rule_for_unidade(dados_unidade)
    if not rule or not rule.dhcp_lan_start_octeto or not rule.dhcp_lan_end_octeto:
        return "", ""
    return (
        get_ip_with_suffix(ip_lan_base, rule.dhcp_lan_start_octeto),
        get_ip_with_suffix(ip_lan_base, rule.dhcp_lan_end_octeto),
    )


def _should_emit_dhcp_server_1(dados_unidade) -> bool:
    """MV_dhcp_server_1_* no layout REDE_LAN (flag do catálogo)."""
    rule = rule_for_unidade(dados_unidade)
    return bool(rule and rule.emite_dhcp_server_1)


def _resolve_device_blueprint(dados_unidade, dados_equipamento=None):
    """
    Device Blueprint no CSV por acrônimo + modelo + quantidade de IPs LAN preenchidos.
    """
    return resolve_device_blueprint_detail(dados_unidade, dados_equipamento)[
        "device_blueprint"
    ]

def format_location(dados):
    """Monta a string de localização concatenando campos"""
    parts = []
    fields = [
        'endereco_unidades', 'numero_unidades', 'bairro_unidades', 
        'cep_unidades', 'municipio_unidades', 'estado_unidades'
    ]
    for field in fields:
        val = dados.get(field)
        if val:
            # Substitui espaços por underline e limpa caracteres especiais simples
            clean_val = str(val).strip().replace(' ', '_').replace(',', '_').replace('-', '_')
            if field == 'cep_unidades' and clean_val:
                parts.append(f"Cep_{clean_val}")
            else:
                parts.append(clean_val)
    
    return "_".join(parts)


def format_lat_lon_csv_excel_pt_br(value):
    """
    Latitude/longitude no CSV com delimitador ';' para Excel em locale PT-BR.
    Nesse ambiente o ponto é separador de milhar; usa vírgula como decimal para
    evitar leitura errada (ex.: -23.54258200 virando milhões).
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    try:
        n = float(s.replace(",", "."))
    except (ValueError, TypeError):
        return s
    t = f"{n:.12f}".rstrip("0").rstrip(".")
    if t == "-0":
        t = "0"
    return t.replace(".", ",")


def validar_dados_blueprint(unidade, equipamento, links):
    """
    Valida se todos os campos obrigatórios para o Blueprint estão preenchidos.
    Retorna (True, []) se válido, ou (False, [lista_de_erros]) se inválido.
    """
    erros = []
    
    # 1. Validação Unidade
    if not unidade.get('hostname_unidades'):
        erros.append("Hostname da Unidade")
    
    if not str(unidade.get('acronimo_unidades') or '').strip():
        erros.append("Sigla Secretaria (Acrônimo)")
    
    ip_lan = unidade.get('ip_lan_01_unidades', '')
    if not ip_lan:
        erros.append("IP LAN 1")
    elif '/' not in ip_lan:
        erros.append("IP LAN 1 (Deve conter a máscara CIDR, ex: /24)")

    for _js, db_col, _csv, _mask, label, _max, kind in UNIDADES_LAN_EXTRA_SPEC:
        if kind != "cidr":
            continue
        val = (unidade.get(db_col) or "").strip()
        if val and "/" not in val:
            erros.append(f"{label} (Deve conter a máscara CIDR, ex: /24)")

    sec = _lan_ip_filled(unidade.get("mv_ip_lan_sec_unidades"))
    ter = _lan_ip_filled(unidade.get("mv_ip_lan_ter_unidades"))
    qua = _lan_ip_filled(unidade.get("mv_ip_lan_qua_unidades"))
    if ter and not sec:
        erros.append("IP LAN TER exige IP LAN SEC preenchido")
    if qua and not sec:
        erros.append("IP LAN QUA exige IP LAN SEC preenchido")
    if qua and not ter:
        erros.append("IP LAN QUA exige IP LAN TER preenchido")

    for js, db_col, _csv, label, _max in UNIDADES_MV_OPCIONAIS_SPEC:
        if js not in UNIDADES_MV_CIDR_JS_KEYS:
            continue
        val = (unidade.get(db_col) or "").strip()
        if val and "/" not in val:
            erros.append(f"{label} (Deve conter a máscara CIDR, ex: /24)")
    
    if not unidade.get('loopback_cliente_unidades'):
        erros.append("Loopback Cliente")
    if not unidade.get('loopback_on_bgp_unidades'):
        erros.append("Loopback On BGP")
    if not unidade.get('loopback_vivo_unidades'):
        erros.append("Loopback Vivo")
        
    # 2. Validação Equipamento
    if not equipamento or not equipamento.get('serial_equipamentos'):
        erros.append("Serial Number do Equipamento")
        
    # 3. Validação Links
    link_mpls = next((l for l in links if l.get('tipo_links') == 'MPLS'), None)
    link_static = next((l for l in links if l.get('tipo_links') == 'STATIC'), None)
    
    if not link_mpls and not link_static:
        erros.append("Pelo menos um link (MPLS ou STATIC) deve estar cadastrado")
    
    if link_mpls:
        prefix = "Link MPLS"
        if not str(link_mpls.get('operadora_links') or '').strip():
            erros.append(f"{prefix}: Operadora")
        if not str(link_mpls.get('designador_links') or '').strip():
            erros.append(f"{prefix}: Designador")
        if not link_mpls.get('ip_wan_links'): erros.append(f"{prefix}: IP WAN")
        if not link_mpls.get('ip_gateway_links'): erros.append(f"{prefix}: IP Gateway")
        if not link_mpls.get('ip_mascara_links'): erros.append(f"{prefix}: IP Máscara")
        if not link_mpls.get('velocidade_links'): erros.append(f"{prefix}: Velocidade")
        if link_mpls.get('operadora_links') == 'VIVO' and not link_mpls.get('id_vgr_links'):
            erros.append(f"{prefix}: ID VGR (Obrigatório para VIVO)")
            
    if link_static:
        prefix = "Link STATIC"
        if not str(link_static.get('operadora_links') or '').strip():
            erros.append(f"{prefix}: Operadora")
        if not str(link_static.get('designador_links') or '').strip():
            erros.append(f"{prefix}: Designador")
        if not link_static.get('ip_wan_links'): erros.append(f"{prefix}: IP WAN")
        if not link_static.get('ip_gateway_links'): erros.append(f"{prefix}: IP Gateway")
        if not link_static.get('ip_mascara_links'): erros.append(f"{prefix}: IP Máscara")
        if not link_static.get('velocidade_links'): erros.append(f"{prefix}: Velocidade")
        if link_static.get('operadora_links') == 'VIVO' and not link_static.get('id_vgr_links'):
            erros.append(f"{prefix}: ID VGR (Obrigatório para VIVO)")

    from prodesp.prodesp.db_field_limits import validate_links_business_rules_for_blueprint

    erros.extend(validate_links_business_rules_for_blueprint(links))

    if erros:
        return False, erros
    return True, []


_LAN_MASK_OVERRIDE_KEYS = (
    ("lan", "ip_lan_01_unidades", "Máscara LAN 1 (blueprint)"),
    ("lan_sec", "mv_ip_lan_sec_unidades", "Máscara LAN SEC (blueprint)"),
    ("lan_ter", "mv_ip_lan_ter_unidades", "Máscara LAN TER (blueprint)"),
    ("lan_qua", "mv_ip_lan_qua_unidades", "Máscara LAN QUA (blueprint)"),
)

_LAN_IP_OVERRIDE_KEYS = (
    ("hostname", "hostname_unidades"),
    ("ip_lan_01", "ip_lan_01_unidades"),
    ("mv_ip_lan_sec", "mv_ip_lan_sec_unidades"),
    ("mv_ip_lan_ter", "mv_ip_lan_ter_unidades"),
    ("mv_ip_lan_qua", "mv_ip_lan_qua_unidades"),
    ("mv_rede_lan_sec", "mv_rede_lan_sec_unidades"),
    ("mv_rede_lan_ter", "mv_rede_lan_ter_unidades"),
    ("mv_rede_lan_qua", "mv_rede_lan_qua_unidades"),
)


def blueprint_mask_options_payload() -> list[dict[str, str]]:
    return [
        {
            "mask": m,
            "cidr": c,
            "label": format_mask_option_label(m, c),
        }
        for m, c in BLUEPRINT_MASK_OPTIONS
    ]


def build_blueprint_confirm_payload(unidade, equipamento, links) -> dict:
    """Payload da tela de confirmação antes de gerar o CSV."""
    u = dict(unidade or {})
    eq = equipamento or {}
    ls = links or []
    detail = resolve_device_blueprint_detail(u, eq)

    def _lan_block(key: str, db_col: str, label: str) -> dict:
        raw = (u.get(db_col) or "").strip()
        ip, mask = split_ip_and_mask_from_cidr(raw)
        cidr = mask_to_cidr_prefix(mask) if mask else ""
        return {
            "key": key,
            "label": label,
            "filled": bool(raw),
            "ip_cidr": raw,
            "ip": ip,
            "mask": mask,
            "mask_label": format_mask_option_label(mask, cidr) if mask else "",
            "mapped_mask": mask,
        }

    lans = [
        _lan_block("lan", "ip_lan_01_unidades", "IP LAN 1"),
        _lan_block("lan_sec", "mv_ip_lan_sec_unidades", "IP LAN SEC"),
        _lan_block("lan_ter", "mv_ip_lan_ter_unidades", "IP LAN TER"),
        _lan_block("lan_qua", "mv_ip_lan_qua_unidades", "IP LAN QUA"),
    ]

    # Rede LAN 1 (calculada) + Rede SEC/TER/QUA (editáveis)
    ip_lan1 = (u.get("ip_lan_01_unidades") or "").strip()
    rede_lan1 = _resolve_rede_lan(ip_lan1, _rede_lan_regra_for_unidade(u)) if ip_lan1 else ""
    redes = [
        {
            "key": "rede_lan",
            "label": "Rede LAN 1 (calculada)",
            "filled": bool(rede_lan1),
            "value": rede_lan1,
            "editable": False,
            "db_col": None,
            "lan_key": "lan",
        },
        {
            "key": "rede_lan_sec",
            "label": "Rede LAN SEC",
            "filled": bool((u.get("mv_rede_lan_sec_unidades") or "").strip()),
            "value": (u.get("mv_rede_lan_sec_unidades") or "").strip(),
            "editable": True,
            "db_col": "mv_rede_lan_sec_unidades",
            "js_key": "mv_rede_lan_sec",
            "lan_key": "lan_sec",
        },
        {
            "key": "rede_lan_ter",
            "label": "Rede LAN TER",
            "filled": bool((u.get("mv_rede_lan_ter_unidades") or "").strip()),
            "value": (u.get("mv_rede_lan_ter_unidades") or "").strip(),
            "editable": True,
            "db_col": "mv_rede_lan_ter_unidades",
            "js_key": "mv_rede_lan_ter",
            "lan_key": "lan_ter",
        },
        {
            "key": "rede_lan_qua",
            "label": "Rede LAN QUA",
            "filled": bool((u.get("mv_rede_lan_qua_unidades") or "").strip()),
            "value": (u.get("mv_rede_lan_qua_unidades") or "").strip(),
            "editable": True,
            "db_col": "mv_rede_lan_qua_unidades",
            "js_key": "mv_rede_lan_qua",
            "lan_key": "lan_qua",
        },
    ]

    # Exibe IP+máscara na confirmação se houver IP ou Rede no nível (máscara sem IP)
    default_mask = "255.255.255.0"
    rede_filled = {r["lan_key"]: r["filled"] for r in redes if r.get("lan_key")}
    for lan in lans:
        key = lan["key"]
        ov_mask = (u.get(f"_blueprint_mask_{key}") or "").strip()
        has_rede = bool(rede_filled.get(key))
        lan["show"] = bool(lan["filled"] or key == "lan" or has_rede)
        if not lan["mapped_mask"]:
            lan["mapped_mask"] = ov_mask or (default_mask if has_rede else "")
            lan["mask"] = lan["mapped_mask"]
            lan["mask_label"] = (
                format_mask_option_label(lan["mask"], mask_to_cidr_prefix(lan["mask"]))
                if lan["mask"]
                else ""
            )
        lan["allow_mask_without_ip"] = has_rede and not lan["filled"]


    gateways = []
    for link in ls:
        tipo = (link.get("tipo_links") or "").strip().upper()
        if tipo not in ("MPLS", "STATIC"):
            continue
        gateways.append(
            {
                "tipo": tipo,
                "operadora": (link.get("operadora_links") or "").strip(),
                "designador": (link.get("designador_links") or "").strip(),
                "ip_wan": (link.get("ip_wan_links") or "").strip(),
                "gateway": (link.get("ip_gateway_links") or "").strip(),
                "mascara": (link.get("ip_mascara_links") or "").strip(),
            }
        )

    return {
        "hostname": (u.get("hostname_unidades") or "").strip(),
        "id_vgr": (u.get("id_vgr_unidades") or "").strip(),
        "acronimo": detail["acronimo"],
        "lans": lans,
        "redes": redes,
        "gateways": gateways,
        "device_blueprint": detail["device_blueprint"],
        "device_blueprint_motivo": detail["motivo"],
        "lan_count": detail["lan_count"],
        "mask_options": blueprint_mask_options_payload(),
    }


def apply_blueprint_confirm_overrides(unidade: dict, overrides: dict | None) -> tuple[dict, list[dict]]:
    """
    Aplica hostname/IPs/máscaras da confirmação.
    Retorna (unidade_ajustada, logs_mascara) onde cada log é
    {campo, antigo, novo} quando a máscara escolhida ≠ mapeada pelo CIDR
    (ou quando há máscara sem IP — só Rede LAN).
    """
    u = dict(unidade or {})
    ov = overrides if isinstance(overrides, dict) else {}
    mask_logs: list[dict] = []

    for js_key, db_col in _LAN_IP_OVERRIDE_KEYS:
        if js_key not in ov:
            continue
        val = ov.get(js_key)
        if val is None:
            continue
        u[db_col] = str(val).strip()

    for mask_key, db_col, hist_campo in _LAN_MASK_OVERRIDE_KEYS:
        chosen = (ov.get(f"mask_{mask_key}") or ov.get(mask_key) or "").strip()
        override_attr = f"_blueprint_mask_{mask_key}"
        if not chosen:
            u.pop(override_attr, None)
            continue

        current = (u.get(db_col) or "").strip()
        if current:
            _ip, mapped = split_ip_and_mask_from_cidr(current)
            u[db_col] = apply_mask_to_ip_cidr(current, chosen)
            # Com IP: máscara também no override (CSV usa CIDR; override reforça)
            u[override_attr] = chosen
            if mapped and chosen != mapped:
                mask_logs.append(
                    {
                        "campo": hist_campo,
                        "antigo": format_mask_option_label(mapped, mask_to_cidr_prefix(mapped)),
                        "novo": format_mask_option_label(chosen, mask_to_cidr_prefix(chosen)),
                    }
                )
            continue

        # Sem IP: mantém máscara para emitir MV_MASK_LAN_* junto da Rede
        prev = (unidade.get(override_attr) or "").strip()
        u[override_attr] = chosen
        if chosen != prev:
            mask_logs.append(
                {
                    "campo": hist_campo,
                    "antigo": format_mask_option_label(prev, mask_to_cidr_prefix(prev))
                    if prev
                    else "— (sem IP LAN)",
                    "novo": format_mask_option_label(chosen, mask_to_cidr_prefix(chosen)),
                }
            )

    return u, mask_logs


def apply_blueprint_equipamento_overrides(
    equipamento: dict | None, overrides: dict | None
) -> dict:
    """
    Mescla serial/versao digitados no formulário (ou overrides JSON) sobre o
    equipamento do banco — a prévia do modal deve validar o que o analista
    digitou, nao so o que ja estava gravado.
    """
    eq = dict(equipamento or {})
    ov = overrides if isinstance(overrides, dict) else {}

    serial = (
        ov.get("serial_equipamentos")
        if "serial_equipamentos" in ov
        else ov.get("serial")
    )
    if serial is not None:
        serial_n = re.sub(r"\s+", "", str(serial).strip()).upper()
        if serial_n:
            eq["serial_equipamentos"] = serial_n
            modelo = infer_modelo_equipamento_from_serial(serial_n)
            if modelo:
                eq["modelo_equipamentos"] = modelo

    if "versao_equipamentos" in ov and ov.get("versao_equipamentos") is not None:
        versao = str(ov.get("versao_equipamentos") or "").strip()
        if versao:
            eq["versao_equipamentos"] = versao

    return eq


def _mv_opcional_unidade(dados_unidade, db_col: str) -> str:
    return (dados_unidade.get(db_col) or "").strip()


def _mv_opcionais_row_pairs(dados_unidade) -> list[tuple[str, str]]:
    """Emite MV opcionais; campos CIDR saem sem máscara + MV_MASK_* derivado."""
    pairs: list[tuple[str, str]] = []
    for js, db_col, csv_hdr, _, _ in UNIDADES_MV_OPCIONAIS_SPEC:
        raw = _mv_opcional_unidade(dados_unidade, db_col)
        if js in UNIDADES_MV_CIDR_JS_KEYS:
            ip, mask = split_ip_and_mask_from_cidr(raw)
            pairs.append((csv_hdr, ip))
            if csv_hdr.startswith("MV_IP_"):
                pairs.append((csv_hdr.replace("MV_IP_", "MV_MASK_", 1), mask))
        else:
            pairs.append((csv_hdr, raw))
    return pairs


def _lan_extra_triple(dados_unidade, rede_db: str, ip_db: str) -> tuple[str, str, str]:
    rede = _mv_opcional_unidade(dados_unidade, rede_db)
    ip, mask = split_ip_and_mask_from_cidr(_mv_opcional_unidade(dados_unidade, ip_db))
    # Máscara da confirmação quando não há IP/CIDR (ex.: só Rede LAN SEC)
    override_key = {
        "mv_ip_lan_sec_unidades": "_blueprint_mask_lan_sec",
        "mv_ip_lan_ter_unidades": "_blueprint_mask_lan_ter",
        "mv_ip_lan_qua_unidades": "_blueprint_mask_lan_qua",
    }.get(ip_db)
    if override_key:
        ov_mask = (dados_unidade.get(override_key) or "").strip()
        if ov_mask:
            mask = ov_mask
    return rede, ip, mask


def _lan_extra_row_pairs_csv_order(dados_unidade) -> list[tuple[str, str]]:
    """Ordem CSV: REDE → IP → MASK para SEC, TER e QUA."""
    pairs: list[tuple[str, str]] = []
    for suffix, rede_db, ip_db in (
        ("SEC", "mv_rede_lan_sec_unidades", "mv_ip_lan_sec_unidades"),
        ("TER", "mv_rede_lan_ter_unidades", "mv_ip_lan_ter_unidades"),
        ("QUA", "mv_rede_lan_qua_unidades", "mv_ip_lan_qua_unidades"),
    ):
        rede, ip, mask = _lan_extra_triple(dados_unidade, rede_db, ip_db)
        # Emite máscara se houver IP ou Rede (cenário só-rede + mask na confirmação)
        if not mask and (rede or ip):
            mask = ""
        pairs.extend(
            [
                (f"MV_REDE_LAN_{suffix}", rede),
                (f"MV_IP_LAN_{suffix}", ip),
                (f"MV_MASK_LAN_{suffix}", mask),
            ]
        )
    return pairs


def _wifi_guest_row_pairs(dados_unidade) -> list[tuple[str, str]]:
    rede = _mv_opcional_unidade(dados_unidade, "mv_rede_wifi_guest_unidades")
    ip, mask = split_ip_and_mask_from_cidr(
        _mv_opcional_unidade(dados_unidade, "mv_ip_wifi_guest_unidades")
    )
    return [
        ("MV_REDE_WIFI_GUEST", rede),
        ("MV_IP_WIFI_GUEST", ip),
        ("MV_MASK_WIFI_GUEST", mask),
        (
            "MV_DHCP_START_WIFI_GUEST",
            _mv_opcional_unidade(dados_unidade, "mv_dhcp_start_wifi_guest_unidades"),
        ),
        (
            "MV_DHCP_END_WIFI_GUEST",
            _mv_opcional_unidade(dados_unidade, "mv_dhcp_end_wifi_guest_unidades"),
        ),
        (
            "MV_RESERVA_START_WIFI_GUEST",
            _mv_opcional_unidade(dados_unidade, "mv_reserva_start_wifi_guest_unidades"),
        ),
        (
            "MV_RESERVA_END_WIFI_GUEST",
            _mv_opcional_unidade(dados_unidade, "mv_reserva_end_wifi_guest_unidades"),
        ),
    ]


def _intf_row_pairs(dados_equipamento) -> list[tuple[str, str]]:
    fields = blueprint_intf_fields_for_equipment(
        dados_equipamento.get("modelo_equipamentos"),
        dados_equipamento.get("serial_equipamentos"),
    )
    return list(fields.items())


def _build_blueprint_rede_lan_row_pairs(dados_unidade, dados_equipamento, dados_links):
    """
    CSV no modelo REDE_LAN (cabeçalhos MV_REDE_LAN, MV_IP_LAN, MV_MGMT_PRODESP, …).
    Origem: planilha DETRAN_BP_MODELO_v1; reutilizável por outros acrônimos no futuro.
    """
    serial_number = dados_equipamento.get("serial_equipamentos", "")
    device_blueprint = _resolve_device_blueprint(dados_unidade, dados_equipamento)
    name = dados_unidade.get("hostname_unidades", "")

    ip_lan_base = dados_unidade.get("ip_lan_01_unidades", "")
    mv_rede_lan = _resolve_rede_lan(ip_lan_base, _rede_lan_regra_for_unidade(dados_unidade))
    mv_ip_lan = ip_lan_base.split("/")[0].strip() if ip_lan_base else ""
    mv_dhcp_start_lan, mv_dhcp_end_lan = _resolve_dhcp_lan_range(dados_unidade, ip_lan_base)

    cidr_match = re.search(r"/(\d+)", ip_lan_base)
    mv_mask_lan = cidr_to_mask(cidr_match.group(0)) if cidr_match else ""

    link_mpls = next((l for l in dados_links if l.get("tipo_links") == "MPLS"), {})
    link_static = next((l for l in dados_links if l.get("tipo_links") == "STATIC"), {})

    id_vgr_mpls = link_mpls.get("id_vgr_links", "")
    vel_mpls = normalize_velocity_mbps(link_mpls.get("velocidade_links", ""))
    mv_description_mpls_1 = (
        f"SCM_MPLS1_{id_vgr_mpls}_{vel_mpls}Mb" if id_vgr_mpls and vel_mpls else ""
    )

    id_vgr_static = link_static.get("id_vgr_links", "")
    vel_static = normalize_velocity_mbps(link_static.get("velocidade_links", ""))
    mv_description_inet_1 = (
        f"SAI-BL_INET1_{id_vgr_static}_{vel_static}Mb" if id_vgr_static and vel_static else ""
    )

    row_pairs = [
        ("Serial Number", serial_number),
        ("Device Blueprint", device_blueprint),
        ("Name", name),
        ("MV_LOCALIDADE", format_location(dados_unidade)),
        ("MV_LATITUDE", format_lat_lon_csv_excel_pt_br(dados_unidade.get("latitude_unidades"))),
        ("MV_LONGITUDE", format_lat_lon_csv_excel_pt_br(dados_unidade.get("longitude_unidades"))),
        ("MV_HOSTNAME_SPK", name),
        ("MV_MGMT_PRODESP", dados_unidade.get("loopback_cliente_unidades", "")),
        ("MV_IP_BGP", dados_unidade.get("loopback_on_bgp_unidades", "")),
        ("MV_MGMT_VIVO", dados_unidade.get("loopback_vivo_unidades", "")),
        ("MV_REDE_LAN", mv_rede_lan),
        ("MV_IP_LAN", mv_ip_lan),
        ("MV_MASK_LAN", mv_mask_lan),
        ("MV_DHCP_START_LAN", mv_dhcp_start_lan),
        ("MV_DHCP_END_LAN", mv_dhcp_end_lan),
        ("MV_REDE_VOZ", _mv_opcional_unidade(dados_unidade, "mv_rede_voz_unidades")),
        ("MV_IP_VOZ", ""),
        ("MV_MASK_VOZ", _mv_opcional_unidade(dados_unidade, "mv_mask_voz_unidades")),
        ("MV_IP_TRANSITO", _mv_opcional_unidade(dados_unidade, "mv_ip_transito_unidades")),
        ("MV_MASK_TRANSITO", _mv_opcional_unidade(dados_unidade, "mv_mask_transito_unidades")),
        ("MV_IP_SWT", _mv_opcional_unidade(dados_unidade, "mv_ip_swt_unidades")),
        ("MV_REDE_LAN_ASSOC", _mv_opcional_unidade(dados_unidade, "mv_rede_lan_assoc_unidades")),
        ("MV_MASK_LAN_ASSOC", _mv_opcional_unidade(dados_unidade, "mv_mask_lan_assoc_unidades")),
        ("MV_REDE_TOTEM", _mv_opcional_unidade(dados_unidade, "mv_rede_totem_unidades")),
        ("MV_MASK_TOTEM", _mv_opcional_unidade(dados_unidade, "mv_mask_totem_unidades")),
    ]
    row_pairs.extend(_lan_extra_row_pairs_csv_order(dados_unidade))
    row_pairs.extend(_wifi_guest_row_pairs(dados_unidade))
    row_pairs.extend(
        [
        ("MV_IP_INET_1", link_static.get("ip_wan_links", "")),
        ("MV_MASK_INET_1", link_static.get("ip_mascara_links", "")),
        ("MV_GTW_INET_1", link_static.get("ip_gateway_links", "")),
        ("MV_DESCRIPTION_INET_1", mv_description_inet_1),
        ("MV_BANDWIDTH_INET_1", format_velocity(link_static.get("velocidade_links", ""))),
        ("MV_IP_MPLS_1", link_mpls.get("ip_wan_links", "")),
        ("MV_GTW_MPLS_1", link_mpls.get("ip_gateway_links", "")),
        ("MV_DESCRIPTION_MPLS_1", mv_description_mpls_1),
        ("MV_BANDWIDTH_MPLS_1", format_velocity(link_mpls.get("velocidade_links", ""))),
        ]
    )
    row_pairs.extend(_intf_row_pairs(dados_equipamento))
    if _should_emit_dhcp_server_1(dados_unidade):
        row_pairs.extend(
            [
                ("MV_dhcp_server_1_start", get_ip_with_suffix(ip_lan_base, "10")),
                ("MV_dhcp_server_1_end", get_ip_with_suffix(ip_lan_base, "250")),
            ]
        )
    return row_pairs


def _build_blueprint_legacy_row_pairs(dados_unidade, dados_equipamento, dados_links):
    """Modelo legado (MV_10_, DIPOL, etc.)."""
    omit_dhcp = _legado_omitir_dhcp_server(dados_unidade)

    serial_number = dados_equipamento.get("serial_equipamentos", "")
    device_blueprint = _resolve_device_blueprint(dados_unidade, dados_equipamento)
    name = dados_unidade.get("hostname_unidades", "")
    mv_hostname_spk = dados_unidade.get("hostname_unidades", "")

    ip_lan_base = dados_unidade.get("ip_lan_01_unidades", "")
    mv_10_ = _resolve_rede_lan(ip_lan_base, _rede_lan_regra_for_unidade(dados_unidade))
    if omit_dhcp:
        mv_dhcp_server_1_start = ""
        mv_dhcp_server_1_end = ""
    else:
        mv_dhcp_server_1_start = get_ip_with_suffix(ip_lan_base, "10")
        mv_dhcp_server_1_end = get_ip_with_suffix(ip_lan_base, "250")
    mv_ip_lan1 = ip_lan_base.split("/")[0].strip() if ip_lan_base else ""

    cidr_match = re.search(r"/(\d+)", ip_lan_base)
    mv_lan1_mask = cidr_to_mask(cidr_match.group(0)) if cidr_match else ""

    mv_10_252 = dados_unidade.get("loopback_cliente_unidades", "")
    mv_lo_mgmt_prodesp = dados_unidade.get("loopback_cliente_unidades", "")
    mv_10_253 = dados_unidade.get("loopback_on_bgp_unidades", "")
    mv_lo_on_bgp = dados_unidade.get("loopback_on_bgp_unidades", "")
    mv_10_254 = dados_unidade.get("loopback_vivo_unidades", "")
    mv_lo_mgmt_vivo = dados_unidade.get("loopback_vivo_unidades", "")

    link_mpls = next((l for l in dados_links if l.get("tipo_links") == "MPLS"), {})
    link_static = next((l for l in dados_links if l.get("tipo_links") == "STATIC"), {})

    mv_ip_lan3 = link_mpls.get("ip_wan_links", "")
    mv_gtw_mpls1 = link_mpls.get("ip_gateway_links", "")
    mv_mpls1_mask = link_mpls.get("ip_mascara_links", "")
    mv_mpls1_bandwidth = format_velocity(link_mpls.get("velocidade_links", ""))

    id_vgr_mpls = link_mpls.get("id_vgr_links", "")
    vel_mpls = normalize_velocity_mbps(link_mpls.get("velocidade_links", ""))
    mv_description_mpls1 = f"SCM_MPLS1_{id_vgr_mpls}_{vel_mpls}Mb" if id_vgr_mpls and vel_mpls else ""

    mv_ip_wan = link_static.get("ip_wan_links", "")
    mv_gtw_wan = link_static.get("ip_gateway_links", "")
    mv_inet1_mask = link_static.get("ip_mascara_links", "")
    mv_inet1_bandwidth = format_velocity(link_static.get("velocidade_links", ""))

    id_vgr_static = link_static.get("id_vgr_links", "")
    vel_static = normalize_velocity_mbps(link_static.get("velocidade_links", ""))
    mv_description_inet1 = (
        f"SAI-BL_INET1_{id_vgr_static}_{vel_static}Mb" if id_vgr_static and vel_static else ""
    )

    mv_description_inet2 = "SAI-BLI_INET2_"

    mv_latitude = format_lat_lon_csv_excel_pt_br(dados_unidade.get("latitude_unidades"))
    mv_longitude = format_lat_lon_csv_excel_pt_br(dados_unidade.get("longitude_unidades"))
    mv_location = format_location(dados_unidade)

    row_pairs = [
        ("Serial Number", serial_number),
        ("Device Blueprint", device_blueprint),
        ("Name", name),
        ("MV_HOSTNAME_SPK", mv_hostname_spk),
        ("MV_10_", mv_10_),
    ]
    if not omit_dhcp:
        row_pairs.extend(
            [
                ("MV_dhcp_server_1_start", mv_dhcp_server_1_start),
                ("MV_dhcp_server_1_end", mv_dhcp_server_1_end),
            ]
        )
    row_pairs.extend(
        [
            ("MV_IP_lan1", mv_ip_lan1),
            ("MV_lan1_mask", mv_lan1_mask),
            ("MV_10_252", mv_10_252),
            ("MV_lo_MGMT_PRODESP", mv_lo_mgmt_prodesp),
            ("MV_10_253", mv_10_253),
            ("MV_lo_On_BGP", mv_lo_on_bgp),
            ("MV_10_254", mv_10_254),
            ("MV_lo_MGMT_VIVO", mv_lo_mgmt_vivo),
            ("MV_IP_lan3", mv_ip_lan3),
            ("MV_GTW_MPLS1", mv_gtw_mpls1),
            ("MV_mpls1_mask", mv_mpls1_mask),
            ("MV_mpls1_bandwidth", mv_mpls1_bandwidth),
            ("MV_DESCRIPTION_MPLS1", mv_description_mpls1),
            ("MV_IP_wan", mv_ip_wan),
            ("MV_GTW_WAN", mv_gtw_wan),
            ("MV_inet1_mask", mv_inet1_mask),
            ("MV_inet1_bandwidth", mv_inet1_bandwidth),
            ("MV_DESCRIPTION_INET1", mv_description_inet1),
            ("MV_DESCRIPTION_INET2", mv_description_inet2),
        ]
    )
    row_pairs.extend(_mv_opcionais_row_pairs(dados_unidade))
    row_pairs.extend(_lan_extra_row_pairs_csv_order(dados_unidade))
    row_pairs.extend(_intf_row_pairs(dados_equipamento))
    row_pairs.extend(
        [
            ("MV_latitude", mv_latitude),
            ("MV_longitude", mv_longitude),
            ("MV_location", mv_location),
        ]
    )
    return row_pairs


def build_blueprint_row_pairs(dados_unidade, dados_equipamento, dados_links):
    """Retorna lista (coluna, valor) para uma linha do CSV de blueprint."""
    if _uses_blueprint_rede_lan_modelo(dados_unidade):
        return _build_blueprint_rede_lan_row_pairs(
            dados_unidade,
            dados_equipamento,
            dados_links,
        )
    return _build_blueprint_legacy_row_pairs(dados_unidade, dados_equipamento, dados_links)


def _write_blueprint_csv_file(headers, value_rows, nome_arquivo):
    arquivo_completo = os.path.join(CSV_DIR, nome_arquivo)
    os.makedirs(CSV_DIR, exist_ok=True)
    with open(arquivo_completo, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        for row in value_rows:
            writer.writerow(row)
    return arquivo_completo


def gerar_csv_blueprint_prodesp_lote(
    registros,
    *,
    nome_arquivo=None,
    ignorar_invalidos=False,
):
    """
    Gera um único CSV com várias unidades.
    registros: iterable de (unidade, equipamento, links).
    Retorna (caminho_arquivo, erros_por_id_vgr).
    """
    rows: list[list] = []
    headers_ref = None
    erros: dict[str, list[str]] = {}

    for dados_unidade, dados_equipamento, dados_links in registros:
        id_vgr = str(dados_unidade.get("id_vgr_unidades") or "").strip()
        ok, validation_errors = validar_dados_blueprint(
            dados_unidade, dados_equipamento, dados_links
        )
        if not ok:
            if ignorar_invalidos:
                erros[id_vgr] = validation_errors
                continue
            raise ValueError(f"ID VGR {id_vgr}: {', '.join(validation_errors)}")

        row_pairs = build_blueprint_row_pairs(
            dados_unidade, dados_equipamento, dados_links
        )
        headers, values = zip(*row_pairs)
        headers = list(headers)
        if headers_ref is None:
            headers_ref = headers
        elif headers_ref != headers:
            acr = (dados_unidade.get("acronimo_unidades") or "").strip()
            raise ValueError(
                f"ID VGR {id_vgr} ({acr}): colunas do blueprint divergem do restante do lote."
            )
        rows.append(list(values))

    if not rows or headers_ref is None:
        raise ValueError("Nenhuma unidade válida para gerar blueprint em lote.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome = nome_arquivo or f"blueprint_prodesp_lote_{timestamp}.csv"
    path = _write_blueprint_csv_file(headers_ref, rows, nome)
    return path, erros


def gerar_csv_blueprint_prodesp(dados_unidade, dados_equipamento, dados_links):
    """
    Gera o CSV de Blueprint para PRODESP seguindo as regras de mapeamento.

    Endereço de rede LAN (MV_10_ / MV_REDE_LAN): IP LAN - 1 para todos os acrônimos,
    exceto SAP (endereço de rede .0).
    """
    row_pairs = build_blueprint_row_pairs(dados_unidade, dados_equipamento, dados_links)
    headers, values = zip(*row_pairs)
    name = (dados_unidade.get("hostname_unidades") or "unidade").strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"blueprint_prodesp_{name.lower()}_{timestamp}.csv"
    return _write_blueprint_csv_file(list(headers), [list(values)], nome_arquivo)
