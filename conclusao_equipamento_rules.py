"""
Regras de conclusão PRODESP: serial Fortinet válido e cruzamento com coleta FGT.

P0 — formato de serial (bloqueia provisórios tipo «123»).
P1 — se houver coleta com get sys status, Hostname/Serial/Version devem bater.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence

from prodesp.prodesp.blueprint.prodesp_equipment import SERIAL_MODEL_FRAGMENTS_ORDERED
from prodesp.prodesp.caderno.fgt_sys_status import (
    CMD_GET_SYS_STATUS,
    parse_get_sys_status,
)

# Modelos conhecidos no serial (40F, 60F, …) — mesma família do infer_modelo
_MODEL_FRAGMENTS = tuple(frag for frag, _ in SERIAL_MODEL_FRAGMENTS_ORDERED)
_MODEL_ALT = "|".join(re.escape(f) for f in _MODEL_FRAGMENTS)

# Ex.: FGT40FTK2409D6QK, FGT60FTK25001234; 120G usa prefixo FG (sem T): FG120GTK25006244
SERIAL_FORTINET_REGEX = re.compile(
    rf"^(?:FGT|FG)(?:{_MODEL_ALT})TK[A-Z0-9]{{6,10}}$",
    re.IGNORECASE,
)

_FAKE_SERIALS = frozenset(
    {
        "123",
        "1234",
        "12345",
        "123456",
        "000",
        "0000",
        "0",
        "1",
        "12",
        "999",
        "TEST",
        "TESTE",
        "TEMP",
        "PROVISORIO",
        "PROVISÓRIO",
        "N/A",
        "NA",
        "XXX",
        "XXXX",
        "SERIAL",
        "SERIALNUM",
        "FGT40F",
        "FGT60F",
    }
)

_RE_VERSAO_NUM = re.compile(r"v?(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)
_RE_RESUMO_VERSION = re.compile(
    r"(?im)^\s*Version do equipamento\s*:\s*(.+?)\s*$"
)
_RE_RESUMO_SERIAL = re.compile(r"(?im)^\s*N[uú]mero de Serie\s*:\s*(\S+)\s*$")
_RE_RESUMO_HOSTNAME = re.compile(r"(?im)^\s*Hostname\s*:\s*(\S+)\s*$")


def normalizar_serial(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).upper()


def normalizar_hostname(value: Any) -> str:
    return str(value or "").strip().lower()


def extrair_versao_comparavel(value: Any) -> str:
    """«FortiGate-40F v7.4.11» ou «7.4.11» → «7.4.11»."""
    text = str(value or "").strip()
    if not text or text == "—":
        return ""
    m = _RE_VERSAO_NUM.search(text)
    return m.group(1) if m else re.sub(r"\s+", "", text).lower()


def serial_fortinet_valido(value: Any) -> bool:
    s = normalizar_serial(value)
    if not s or s in _FAKE_SERIALS:
        return False
    if "X" * 3 in s:  # FGT40FXXXXXXX
        return False
    if s.isdigit() and len(s) <= 8:
        return False
    return bool(SERIAL_FORTINET_REGEX.match(s))


def validate_serial_fortinet_format(value: Any, *, obrigatorio: bool = True) -> Optional[str]:
    s = normalizar_serial(value)
    if not s:
        if obrigatorio:
            return (
                "Para Status e Substatus «Concluído», cadastre o número de série "
                "real do FortiGate (não use provisório)."
            )
        return None
    if serial_fortinet_valido(s):
        return None
    return (
        f"Número de série «{s}» inválido ou provisório. "
        "Informe o serial Fortinet no padrão FGT40FTK… / FGT60FTK… / FG120GTK… "
        "(ex.: FGT40FTK2409D6QK ou FG120GTK25006244), sem valores como 123 ou TEST."
    )


# Status em que o Field já está / esteve em contato — serial provisório não deve passar no Blueprint.
STATUS_ATENDIMENTO_EXIGEM_SERIAL_FORTINET = (
    "Em Atendimento",
    "Concluído",
    "Concluído Parcial",
)


def _status_exige_serial_fortinet(status: Any) -> bool:
    s = str(status or "").strip().lower()
    if not s:
        return False
    s_norm = (
        s.replace("í", "i")
        .replace("ó", "o")
        .replace("á", "a")
        .replace("é", "e")
        .replace("ú", "u")
    )
    if "em atendimento" in s_norm:
        return True
    if "conclu" in s_norm:
        return True
    return False


def unidade_tem_atendimento_exigindo_serial_padrao(cursor, id_unidade: Any) -> bool:
    """
    True se a unidade tem ao menos um atendimento Em Atendimento,
    Concluído ou Concluído Parcial (serial FGT deve estar no padrão).
    """
    if id_unidade in (None, ""):
        return False
    cursor.execute(
        """
        SELECT status_atendimentos AS status
        FROM atendimentos
        WHERE id_unidades_atendimentos = %s
        """,
        (id_unidade,),
    )
    rows = cursor.fetchall() or []
    for row in rows:
        st = row.get("status") if isinstance(row, Mapping) else (row[0] if row else "")
        if _status_exige_serial_fortinet(st):
            return True
    return False


def validate_serial_fortinet_para_blueprint(
    serial: Any,
    *,
    exige_padrao: bool,
) -> Optional[str]:
    """
    Blueprint antecipado: permite serial fora do padrão se a unidade ainda não
    tiver atendimento Em Atendimento / Concluído / Concluído Parcial.
    Com esses status, serial preenchido deve ser Fortinet válido.
    """
    s = normalizar_serial(serial)
    if not s:
        return None
    if not exige_padrao:
        return None
    err = validate_serial_fortinet_format(s, obrigatorio=False)
    if err:
        return (
            f"{err} "
            "A unidade já possui atendimento Em Atendimento, Concluído ou "
            "Concluído Parcial — use o serial real do Field."
        )
    return None


def _parse_logs_por_comando(logs_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not (logs_text or "").strip():
        return out
    parts = re.split(r"---\s*(.+?)\s*---", logs_text, flags=re.DOTALL)
    i = 1
    while i + 1 < len(parts):
        cmd = parts[i].strip()
        body = parts[i + 1].strip()
        if cmd and not cmd.startswith("==="):
            out[cmd] = body
        i += 2
    return out


def extrair_sys_status_dos_logs(logs_text: str) -> dict[str, str]:
    """
    Lê Version/Serial/Hostname da coleta (resumo ou saída bruta de get sys status).
    Retorna dict vazio se não houver dados úteis.
    """
    raw = logs_text or ""
    if not raw.strip():
        return {}

    try:
        from prodesp.prodesp.caderno.fgt_ssh_collector import extrair_bloco_coleta_fgt

        bloco = extrair_bloco_coleta_fgt(raw) or raw
    except Exception:
        bloco = raw

    parsed = parse_get_sys_status(_parse_logs_por_comando(bloco).get(CMD_GET_SYS_STATUS, ""))
    if not (parsed.get("serial") or parsed.get("hostname") or parsed.get("version")):
        # Fallback: linhas do resumo «--- sys status — resumo ---»
        m_v = _RE_RESUMO_VERSION.search(bloco)
        m_s = _RE_RESUMO_SERIAL.search(bloco)
        m_h = _RE_RESUMO_HOSTNAME.search(bloco)
        parsed = {
            "version": (m_v.group(1).strip() if m_v else ""),
            "serial": (m_s.group(1).strip() if m_s else ""),
            "hostname": (m_h.group(1).strip() if m_h else ""),
            "version_raw": "",
        }
        if parsed.get("version") == "—":
            parsed["version"] = ""
        if parsed.get("serial") == "—":
            parsed["serial"] = ""
        if parsed.get("hostname") == "—":
            parsed["hostname"] = ""

    if not (parsed.get("serial") or parsed.get("hostname") or parsed.get("version")):
        return {}
    return parsed


def _primeiro_equipamento(equipamentos: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    for eq in equipamentos or []:
        if not isinstance(eq, Mapping):
            continue
        serial = normalizar_serial(
            eq.get("serial") or eq.get("serial_equipamentos")
        )
        if not serial:
            continue
        return {
            "serial": serial,
            "versao": str(
                eq.get("versao") or eq.get("versao_equipamentos") or ""
            ).strip(),
            "modelo": str(
                eq.get("modelo") or eq.get("modelo_equipamentos") or ""
            ).strip(),
        }
    return {"serial": "", "versao": "", "modelo": ""}


def validate_conclusao_equipamento(
    *,
    hostname_unidade: Any,
    equipamentos: Sequence[Mapping[str, Any]],
    logs_atendimentos: Any = "",
    exigir_cruzamento_log: bool = True,
) -> list[str]:
    """
    Validações para Status+Substatus Concluído.
    Retorna lista de mensagens (vazia = ok).
    """
    errors: list[str] = []
    eq = _primeiro_equipamento(equipamentos)
    serial_cad = eq.get("serial") or ""

    if not serial_cad:
        errors.append(
            "Para Status e Substatus «Concluído», cadastre o equipamento com o "
            "número de série real do FortiGate (aba Equipamentos)."
        )
    else:
        fmt_err = validate_serial_fortinet_format(serial_cad, obrigatorio=True)
        if fmt_err:
            errors.append(fmt_err)

    if not exigir_cruzamento_log:
        return errors

    coletado = extrair_sys_status_dos_logs(str(logs_atendimentos or ""))
    if not coletado:
        # Sem coleta / sem get sys status: não bloqueia cruzamento (só formato).
        return errors

    host_cad = normalizar_hostname(hostname_unidade)
    host_log = normalizar_hostname(coletado.get("hostname"))
    if host_log and host_cad and host_cad != host_log:
        errors.append(
            f"Hostname divergente da coleta FGT: cadastrado «{hostname_unidade}» × "
            f"coletado «{coletado.get('hostname')}». "
            "Corrija o Hostname na unidade ou recolete os logs."
        )
    elif host_log and not host_cad:
        errors.append(
            f"Hostname não cadastrado, mas a coleta FGT retornou «{coletado.get('hostname')}». "
            "Preencha o Hostname da unidade antes de concluir."
        )

    serial_log = normalizar_serial(coletado.get("serial"))
    if serial_log and serial_cad and serial_cad != serial_log:
        errors.append(
            f"Número de série divergente da coleta FGT: cadastrado «{serial_cad}» × "
            f"coletado «{serial_log}». "
            "Atualize o serial do equipamento (não use provisório) antes de concluir."
        )
    elif serial_log and not serial_cad:
        errors.append(
            f"Equipamento sem serial cadastrado; a coleta FGT retornou «{serial_log}». "
            "Cadastre esse serial antes de concluir."
        )

    ver_cad = extrair_versao_comparavel(eq.get("versao"))
    ver_log = extrair_versao_comparavel(coletado.get("version"))
    if ver_cad and ver_log and ver_cad != ver_log:
        errors.append(
            f"Versão do equipamento divergente da coleta FGT: cadastrado «{eq.get('versao')}» × "
            f"coletado «{coletado.get('version')}». "
            "Atualize a versão do equipamento antes de concluir."
        )

    return errors
