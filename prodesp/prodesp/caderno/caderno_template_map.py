"""
Âncoras do template MULTI-OES v3 — células e linhas de comando (aba CARIMBO NOC).
"""
from __future__ import annotations

# Valor fixo da célula C12 (MODELO DE SOLUÇÃO) no template PRODESP
CADERNO_MODELO_SOLUCAO_VALOR = "G"

# Aba CADERNO DE TESTE — coluna C
CADERNO_CELLS: dict[str, str] = {
    "id_intragov": "C6",
    "id_vgr": "C7",
    "acronimo": "C8",
    "site_name": "C9",
    "localidade": "C10",
    "topologia": "C11",
    "modelo_solucao": "C12",
    "fornecedor": "C13",
    "modelo_equipamento": "C14",
    "redundancia_ha": "C15",
    "hostname_primario": "C16",
    "serial_primario": "C17",
    "ip_mgmt": "C18",
    "dhcp_server": "C19",
    "dhcp_relay": "C20",
    "vlan": "C21",
    "multi_ip_lan": "C22",
    "voip_tipo": "C23",
    "voip_nome": "C24",
    "voip_telefone": "C25",
}

# CARIMBO NOC — blocos de link (coluna D = Info Device)
CARIMBO_LINK_SAI_BL: dict[str, int] = {
    "interface": 30,
    "circuito": 31,
    "tecnologia": 32,
    "id_vantive": 33,
    "velocidade": 34,
    "description": 35,
    "ip_wan": 36,
    "remoto": 37,
}

CARIMBO_LINK_SAI_BLI: dict[str, int] = {
    "interface": 41,
    "circuito": 42,
    "tecnologia": 43,
    "id_vantive": 44,
    "velocidade": 45,
    "description": 46,
    "ip_wan": 47,
    "remoto": 48,
}

CARIMBO_LINK_SCM_MPLS: dict[str, int] = {
    "interface": 52,
    "circuito": 53,
    "tecnologia": 54,
    "id_vantive": 55,
    "velocidade": 56,
    "description": 57,
    "ip_wan": 58,
    "remoto": 59,
}

# Comando (texto na col E) → linha âncora; saída colada em E na linha seguinte (ex.: E62 → E63)
CARIMBO_LOG_COL = 5
CARIMBO_LOG_ROW_OFFSET = 1


def carimbo_log_destino(cmd_anchor_row: int) -> tuple[int, int]:
    """Retorna (linha, coluna) onde colar a saída do comando (col E, linha após o comando)."""
    return cmd_anchor_row + CARIMBO_LOG_ROW_OFFSET, CARIMBO_LOG_COL


def carimbo_log_fim_bloco(cmd_anchor_row: int) -> int:
    """Última linha disponível do bloco de log (col E) para o comando."""
    for addr in CARIMBO_LOG_MERGE_RANGES:
        parts = addr.split(":")
        r1 = int(parts[0][1:])
        r2 = int(parts[1][1:])
        if r1 <= cmd_anchor_row <= r2:
            return r2
    anchors = sorted(set(CARIMBO_CMD_ANCHOR_ROWS.values()) | {CARIMBO_SHOW_INTERFACE_ANCHOR_ROW})
    for anchor in anchors:
        if anchor > cmd_anchor_row:
            return anchor - 1
    return cmd_anchor_row + 30


CARIMBO_CMD_ANCHOR_ROWS: dict[str, int] = {
    "get sys fortiguard-service status": 62,
    "get sys performance status": 92,
    "diagnose sys sip-proxy calls": 117,
    "diagnose fdsm central-mgmt-status": 153,
    "get sys fortianalyzer-connectivity status": 167,
    "get sys ha status": 181,
    "diag sys sdwan health-check status": 335,
    "diagnose sys sdwan service4": 201,
    "get ipsec tunnel list": 365,
    "get sys interface physical": 444,
    "exec dhcp lease-list": 553,
    "show firewall policy": 603,
    "get sys arp": 1337,
}

# Aliases para matching de saída show sys interface
CARIMBO_SHOW_INTERFACE_ANCHOR_ROW = 395

# Áreas mescladas (col B — placeholder visual) — desfeitas via COM se necessário
CARIMBO_LOG_MERGE_RANGES: tuple[str, ...] = (
    "B62:D89",
    "B92:D115",
    "B117:D150",
    "B153:D164",
    "B167:D178",
    "B181:D198",
    "B201:D332",
    "B335:D362",
    "B365:D392",
    "B395:D441",
    "B444:D550",
    "B553:D600",
    "B603:D1334",
    "B1337:D1415",
)

# Itens CADERNO DE TESTE (linha → comando OBS col F, quando houver)
CADERNO_ITEM_ROWS: dict[str, int] = {
    "get sys fortiguard-service status": 29,
    "get sys performance status": 30,
    "diagnose fdsm central-mgmt-status": 31,
    "get sys fortianalyzer-connectivity status": 32,
    "get sys ha status": 33,
    "diag sys sdwan health-check status": 34,
    "get ipsec tunnel list": 35,
    "show sys interface": 36,
    "get sys interface physical": 37,
    "exec dhcp lease-list": 38,
    "get sys arp": 39,
    "Site ESAQ": 40,
}

# Linhas de testes Cliente (executor informado pelo analista)
CADERNO_ITEM_ROWS_CLIENTE: tuple[int, ...] = tuple(range(41, 50))

STATUS_PENDENTE = "⚠️Pendente"
STATUS_CONCLUIDO = "✔️ Concluido"
STATUS_FALHOU = "❌ Falhou"
STATUS_NA = "ℹ️ N/A"

CADERNO_STATUS_OPCOES: tuple[str, ...] = (
    STATUS_PENDENTE,
    STATUS_CONCLUIDO,
    STATUS_FALHOU,
    STATUS_NA,
)

# Testes com status informado pelo analista (aba CADERNO DE TESTE, coluna E)
CADERNO_TESTES_ANALISTA: tuple[dict[str, object], ...] = (
    {"row": 40, "label": "Teste de Velocidade - Bandwidth", "responsavel": "Vivo Vita"},
    {"row": 41, "label": "Testes de Voz - Inter-Site (Entre Secretária)", "responsavel": "Cliente"},
    {"row": 42, "label": "Testes de Voz - Entre Ramais", "responsavel": "Cliente"},
    {"row": 43, "label": "Testes de Voz - Ligações Externa (Celular e/ou Call-Center)", "responsavel": "Cliente"},
    {"row": 44, "label": "Teste de Navegação Web - DIA", "responsavel": "Cliente"},
    {"row": 45, "label": "Teste de Navegação Web - SIA", "responsavel": "Cliente"},
    {"row": 46, "label": "Teste de Aplicação Cliente (VoIP, DNS, ERP, Cloud, Website)", "responsavel": "Cliente"},
    {"row": 47, "label": "Teste de Autenticação (Ldap, Radius, User Local)", "responsavel": "Cliente"},
    {"row": 48, "label": "Teste de Contigência dos Links", "responsavel": "Cliente"},
    {"row": 49, "label": "Testes de Conectivade Entre Unidades", "responsavel": "Cliente"},
)

CADERNO_TESTES_ANALISTA_ROWS: frozenset[int] = frozenset(
    int(t["row"]) for t in CADERNO_TESTES_ANALISTA
)

EXECUTOR_VIVO_VITA = "Vivo Vita"
EXECUTOR_CLIENTE = "Cliente"

ESAQ_IMAGE_CELL = "A13"
ESAQ_IMAGE_CELL_SPEEDTEST = "A40"
ESAQ_DISCLAIMER_RANGE = "A68:F74"
ESAQ_IMAGE_HEIGHT_CM = 14.28
ESAQ_IMAGE_WIDTH_CM = 30.09

ESAQ_PORTAL_INDISPONIVEL_TEXTO = (
    "Devido à instabilidade no site ESAQ - Brasil Banda Larga - Meça a qualidade da sua conexão, "
    "não está sendo possível realizar o teste de velocidade. Por esse motivo, estamos utilizando o site "
    "Speedtest by Ookla - Teste de Velocidade de Conexão da Internet para os testes de velocidade "
    "enquanto o problema persistir."
)

MODEL_TEMPLATE_FILENAME_XLSX = "MULTI-OES_CADERNO_DE_TESTE_ROLLOUT.v3.xlsx"
MODEL_TEMPLATE_FILENAME_XLSM = "MULTI-OES_CADERNO_DE_TESTE_ROLLOUT.v3.xlsm"
# Legado — preferir constantes por extensão
MODEL_TEMPLATE_FILENAME = MODEL_TEMPLATE_FILENAME_XLSM
