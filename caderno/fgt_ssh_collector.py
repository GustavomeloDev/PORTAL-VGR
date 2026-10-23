"""
Coleta SSH FortiGate via Jump Server PRODESP (paramiko).
Credenciais somente via variáveis de ambiente — nunca no código.
"""
from __future__ import annotations

import os
import re
import socket
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import paramiko

from prodesp.prodesp.caderno.fgt_admin_cleanup import (
    LIMPEZA_ADMIN_ERRO_MARKER,
    executar_limpeza_admin_fgt,
)
from prodesp.prodesp.caderno.fgt_command_registry import (
    comando_diag_dvm_device_list,
    comandos_para_acronimo,
    id_intragov_para_grep_fmg,
)
from prodesp.prodesp.caderno.fgt_sys_status import (
    CMD_GET_SYS_STATUS,
    montar_resumo_sys_status,
    parse_get_sys_status,
)
from prodesp.prodesp.db_field_limits import LOGS_ATENDIMENTOS_MAX, truncate_mysql_text_field

_LOG = None


def _logger():
    global _LOG
    if _LOG is None:
        from core.logger import get_logger

        _LOG = get_logger("PRODESP")
    return _LOG


@dataclass
class FgtCollectResult:
    ok: bool
    logs_text: str = ""
    errors: list[str] = field(default_factory=list)
    commands_run: int = 0


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _timeout_sec(env_name: str, default: float, *, min_sec: float = 3.0, max_sec: float = 60.0) -> float:
    try:
        val = float(_env(env_name, str(default)) or default)
    except (TypeError, ValueError):
        val = default
    return max(min_sec, min(max_sec, val))


def _ssh_connect_timeout() -> float:
    """Timeout para SSH no jump server (segundos)."""
    return _timeout_sec("PRODESP_SSH_CONNECT_TIMEOUT", 10.0, max_sec=30.0)


def _ssh_channel_timeout() -> float:
    """Timeout para túnel jump → loopback FGT (equipamento offline falha rápido)."""
    return _timeout_sec("PRODESP_SSH_CHANNEL_TIMEOUT", 15.0, max_sec=30.0)


def _diag_ping_enabled() -> bool:
    raw = (_env("PRODESP_SSH_DIAG_PING", "1") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _diag_ping_count() -> int:
    """Quantidade de ICMP no diagnóstico (padrão 5; máx. 10)."""
    try:
        n = int(_env("PRODESP_SSH_DIAG_PING_COUNT", "5") or "5")
    except (TypeError, ValueError):
        n = 5
    return max(1, min(10, n))


@dataclass(frozen=True)
class _JumpAttempt:
    host: str
    port: int
    phase: str
    error: str
    error_type: str = ""


def _is_auth_error(exc: Optional[BaseException] = None, *, text: str = "", err_type: str = "") -> bool:
    err_s = (text or (str(exc) if exc else "")).strip().lower()
    et = (err_type or (type(exc).__name__ if exc else "")).lower()
    if "authentication" in err_s or "auth fail" in err_s or "permission denied" in err_s:
        return True
    if "authenticationexception" in et or et == "authenticationexception":
        return True
    if "authentication" in et:
        return True
    return False


def _is_fgt_ssh_closed_error(exc: Optional[BaseException] = None, *, text: str = "", err_type: str = "") -> bool:
    """Peer fechou o stream no handshake SSH (EOF / Connection closed / reset)."""
    et = (err_type or (type(exc).__name__ if exc else "")).lower()
    err_s = (text or (str(exc) if exc else "")).strip().lower()
    if et in ("eoferror",):
        return True
    if "eof" in err_s or "connection closed" in err_s or "connection reset" in err_s:
        return True
    if "remotely closed" in err_s or "server closed" in err_s:
        return True
    return False


def _friendly_connect_error(
    loopback_ip: str,
    last_err: Optional[Exception],
    *,
    phase: str = "",
    jump_host: str = "",
    jump_port: int = 0,
    connect_timeout: float = 0.0,
    channel_timeout: float = 0.0,
) -> str:
    ip = (loopback_ip or "").strip()
    err_s = str(last_err or "").strip().lower()
    err_type = type(last_err).__name__ if last_err else ""
    jump_label = f"{jump_host}:{jump_port}" if jump_host else "jump server"

    if phase == "tunnel":
        return (
            f"Jump ({jump_label}) autenticou, mas o túnel SSH até o FortiGate ({ip}:22) "
            f"não abriu em {channel_timeout:.0f}s (equipamento offline, sem rota no jump ou "
            f"TCP forwarding bloqueado). No jump, teste: ssh vvita@{ip}"
        )
    if phase == "fgt":
        if _is_auth_error(last_err, text=err_s, err_type=err_type):
            return (
                f"Falha de autenticação SSH no FortiGate ({ip}:22). "
                f"Verifique PRODESP_FGT_USER / PRODESP_FGT_PASSWORD."
            )
        if _is_fgt_ssh_closed_error(last_err, text=err_s, err_type=err_type):
            return (
                f"Jump ({jump_label}) autenticou e o túnel para {ip}:22 foi aberto, "
                f"mas o FortiGate encerrou a conexão SSH antes do login "
                f"(porta 22 fechou o fluxo). Verifique allowaccess ssh, trusted hosts e "
                f"serviço SSH nesta unidade. No jump: ssh vvita@{ip}"
            )
        return (
            f"Túnel via {jump_label} abriu, mas o FortiGate ({ip}:22) não respondeu SSH: "
            f"{type(last_err).__name__ if last_err else 'erro'}"
            + (f" — {last_err}" if last_err and str(last_err).strip() else "")
        )

    if phase == "jump":
        if _is_auth_error(last_err, text=err_s, err_type=err_type):
            return (
                f"Falha de autenticação no jump ({jump_label}). "
                f"Verifique PRODESP_JUMP_USER / PRODESP_JUMP_PASSWORD."
            )
        timeout_hint = f" em {connect_timeout:.0f}s" if connect_timeout else ""
        return (
            f"Jump ({jump_label}) inacessível{timeout_hint}: host bloqueado, IP/porta incorretos "
            f"ou firewall. FortiGate ({ip}:22) não foi contactado."
        )

    if _is_auth_error(last_err, text=err_s, err_type=err_type):
        return f"Falha de autenticação SSH no FortiGate ({ip}:22). Verifique credenciais PRODESP_FGT_*."
    if last_err:
        return f"Não foi possível conectar ao FortiGate ({ip}:22): {last_err}"
    return f"Não foi possível conectar ao FortiGate ({ip}:22) via jump server."


def _jump_endpoints_label(attempts: list[_JumpAttempt]) -> str:
    seen: set[tuple[str, int]] = set()
    labels: list[str] = []
    for att in attempts:
        key = (att.host, att.port)
        if key in seen:
            continue
        seen.add(key)
        labels.append(f"{att.host}:{att.port}")
    return ", ".join(labels)


def _summarize_connect_failures(
    loopback_ip: str,
    attempts: list[_JumpAttempt],
    *,
    connect_timeout: float,
    channel_timeout: float,
    ping_diag: str = "",
) -> str:
    """Mensagem final: culpa jump, túnel ou FGT conforme fases registradas nas tentativas."""
    ip = (loopback_ip or "").strip()
    if not attempts:
        base = f"Não foi possível conectar ao FortiGate ({ip}:22) via jump server."
        return f"{base}\n{ping_diag}".strip() if ping_diag else base

    endpoints = _jump_endpoints_label(attempts)
    any_tunnel_or_fgt = any(a.phase in ("tunnel", "fgt") for a in attempts)
    all_jump = all(a.phase == "jump" for a in attempts)
    fgt_or_tunnel = [a for a in attempts if a.phase in ("tunnel", "fgt")]
    all_fgt_closed = fgt_or_tunnel and all(
        a.phase == "fgt"
        and _is_fgt_ssh_closed_error(text=a.error, err_type=a.error_type)
        for a in fgt_or_tunnel
    )

    if all_jump:
        base = (
            f"Jump server(s) inacessível(is) ({endpoints}): sem resposta SSH "
            f"(IP/porta incorretos, host bloqueado ou firewall). "
            f"Confira PRODESP_JUMP_HOST_1/2, portas e reinício do serviço após alterar o .env. "
            f"FortiGate ({ip}:22) não foi contactado."
        )
        return base  # sem ping — não chegou no destino

    if any_tunnel_or_fgt:
        via = _jump_endpoints_label(fgt_or_tunnel) or endpoints
        if all_fgt_closed:
            base = (
                f"Jump ({via}) autenticou, mas em todas as tentativas o FortiGate ({ip}:22) "
                f"encerrou o SSH antes do login (porta 22 fechou o fluxo). "
                f"Problema típico da unidade (allowaccess/trusted-host/serviço SSH), "
                f"não do path portal→jump. No jump: ssh vvita@{ip}"
            )
        else:
            base = (
                f"Jump ({via}) conectou, mas o FortiGate ({ip}:22) não respondeu via túnel SSH "
                f"(offline, sem rota, ACL ou serviço SSH). "
                f"No jump, teste: ssh vvita@{ip}"
            )
        if ping_diag:
            return f"{base}\n{ping_diag}".strip()
        return base

    last = attempts[-1]
    base = _friendly_connect_error(
        ip,
        Exception(last.error),
        phase=last.phase,
        jump_host=last.host,
        jump_port=last.port,
        connect_timeout=connect_timeout,
        channel_timeout=channel_timeout,
    )
    if ping_diag and last.phase in ("tunnel", "fgt"):
        return f"{base}\n{ping_diag}".strip()
    return base


def _attempts_need_ping_diag(attempts: list[_JumpAttempt]) -> bool:
    """Ping L3 jump→FGT em falhas de rede/SSH; nunca em erro de autenticação."""
    if not _diag_ping_enabled() or not attempts:
        return False
    dest_phases = [a for a in attempts if a.phase in ("tunnel", "fgt")]
    if not dest_phases:
        return False
    if all(_is_auth_error(text=a.error, err_type=a.error_type) for a in dest_phases):
        return False
    return True


def _parse_ping_summary(raw: str, *, count: int, ip: str) -> str:
    text = (raw or "").strip()
    if not text:
        return (
            f"Diagnóstico (ping -c {count} {ip} a partir do jump): sem saída do comando ping."
        )
    header = f"Diagnóstico (ping -c {count} {ip} a partir do jump):"
    loss_m = re.search(
        r"(\d+)\s+packets?\s+transmitted,?\s*(\d+)\s+(?:packets?\s+)?received,?\s*"
        r"([\d.]+)\s*%\s*packet\s*loss",
        text,
        re.I,
    )
    if not loss_m:
        loss_m = re.search(
            r"Packets:\s*Sent\s*=\s*(\d+),\s*Received\s*=\s*(\d+),\s*Lost\s*=\s*\d+\s*\(([\d]+)%\s*loss\)",
            text,
            re.I,
        )
    rtt_m = re.search(
        r"rtt\s+min/avg/max(?:/mdev)?\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)",
        text,
        re.I,
    )
    if loss_m:
        tx, rx, loss = loss_m.group(1), loss_m.group(2), loss_m.group(3)
        line = f"{tx} enviados, {rx} recebidos, {loss}% loss"
        if rtt_m:
            line += f"; rtt avg {rtt_m.group(2)} ms"
        try:
            loss_f = float(loss)
        except ValueError:
            loss_f = -1.0
        if loss_f == 0:
            hint = (
                "Rede L3 até o IP parece ok — foque em SSH/ACL/serviço na caixa "
                "(ping OK não garante SSH)."
            )
        elif loss_f >= 100:
            hint = "Sem eco ICMP até o IP neste jump — confira rota, loopback e se a caixa está na VPN."
        else:
            hint = "Perda ICMP parcial — rede instável ou filtragem; valide também o SSH na :22."
        return f"{header} {line}. {hint}"
    # fallback: primeiras linhas úteis
    compact = " | ".join(ln.strip() for ln in text.splitlines() if ln.strip())[:280]
    return f"{header} {compact}"


def _ping_fgt_via_jump(
    jump: "paramiko.SSHClient",
    fgt_ip: str,
    *,
    count: Optional[int] = None,
) -> str:
    """Executa ping no jump (Linux) até o loopback FGT. IP já validado no caller."""
    n = count if count is not None else _diag_ping_count()
    # -c count; -W 2s wait; IP só dígitos/pontos (caller valida)
    cmd = f"ping -c {int(n)} -W 2 {fgt_ip} 2>&1"
    try:
        _stdin, stdout, stderr = jump.exec_command(cmd, timeout=max(12.0, float(n) * 3.0 + 4.0))
        out = (stdout.read() or b"").decode("utf-8", errors="replace")
        err = (stderr.read() or b"").decode("utf-8", errors="replace")
        raw = (out + err).strip()
        if "not found" in raw.lower() or "command not found" in raw.lower():
            return (
                f"Diagnóstico (ping -c {n} {fgt_ip}): comando ping ausente no jump."
            )
        return _parse_ping_summary(raw, count=n, ip=fgt_ip)
    except Exception as exc:
        return (
            f"Diagnóstico (ping -c {n} {fgt_ip}): indisponível ({type(exc).__name__})."
        )


def _open_jump_client(
    host: str,
    port: int,
    *,
    jump_user: str,
    jump_pass: str,
    connect_timeout: float,
) -> paramiko.SSHClient:
    jump = paramiko.SSHClient()
    jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    jump.connect(
        host,
        port=port,
        username=jump_user,
        password=jump_pass,
        timeout=connect_timeout,
        banner_timeout=connect_timeout,
        auth_timeout=connect_timeout,
        look_for_keys=False,
        allow_agent=False,
    )
    return jump


def _run_connect_failure_ping_diag(
    loopback_ip: str,
    attempts: list[_JumpAttempt],
    *,
    jump_user: str,
    jump_pass: str,
    connect_timeout: float,
) -> str:
    if not _attempts_need_ping_diag(attempts):
        return ""
    # Preferir último jump que chegou em tunnel/fgt (principal ou backup)
    cand = next((a for a in reversed(attempts) if a.phase in ("tunnel", "fgt")), None)
    if not cand:
        return ""
    jump = None
    try:
        jump = _open_jump_client(
            cand.host,
            cand.port,
            jump_user=jump_user,
            jump_pass=jump_pass,
            connect_timeout=connect_timeout,
        )
        return _ping_fgt_via_jump(jump, loopback_ip)
    except Exception as exc:
        return (
            f"Diagnóstico (ping a partir do jump {cand.host}:{cand.port}): "
            f"não foi possível reabrir o jump ({type(exc).__name__})."
        )
    finally:
        if jump:
            try:
                jump.close()
            except Exception:
                pass


def _jump_hosts() -> list[str]:
    hosts = [
        _env("PRODESP_JUMP_HOST_1", "172.19.40.2"),
        _env("PRODESP_JUMP_HOST_2", "172.19.40.3"),
    ]
    return [h for h in hosts if h]


def _jump_ports_for_host(host: str, index: int) -> list[int]:
    """
    Portas SSH do jump por host: principal (3122/.2, 3222/.3) e fallback 22 (ambiente de teste).
    PRODESP_JUMP_PORT_1 / _2 sobrescrevem; PRODESP_JUMP_PORT_FALLBACK (default 22).
    """
    defaults_primary = (3122, 3222)
    env_primary = [
        _env("PRODESP_JUMP_PORT_1", ""),
        _env("PRODESP_JUMP_PORT_2", ""),
    ]
    last_octet = host.rsplit(".", 1)[-1]
    octet_port = {"2": 3122, "3": 3222}

    if index < len(env_primary) and env_primary[index]:
        primary = int(env_primary[index])
    elif last_octet in octet_port:
        primary = octet_port[last_octet]
    elif index < len(defaults_primary):
        primary = defaults_primary[index]
    else:
        primary = int(_env("PRODESP_JUMP_PORT", "22") or "22")

    fallback = int(_env("PRODESP_JUMP_PORT_FALLBACK", _env("PRODESP_JUMP_PORT", "22")) or "22")
    if primary == fallback:
        return [primary]
    return [primary, fallback]


def _montar_lista_comandos(
    acronimo: str,
    modelo: str,
    interfaces: Optional[tuple[str, ...]] = None,
) -> list[str]:
    del modelo, interfaces  # show sys interface (completo) substitui mapa por modelo
    return comandos_para_acronimo(acronimo)


def _fgt_prompt_ready(buf: bytes) -> bool:
    """Detecta prompt FortiOS no final do buffer (evita parar em '#' no meio da saída)."""
    try:
        text = buf.decode("utf-8", errors="replace")
    except Exception:
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    last = lines[-1]
    return bool(re.search(r"#\s*$", last)) and len(last) < 120


_CMD_TIMEOUTS: dict[str, float] = {
    "show firewall policy": 120.0,
    "show sys interface": 60.0,
    "diagnose sys sdwan service4": 45.0,
    "get sys interface physical": 40.0,
    "diag sys sdwan health-check status": 35.0,
    "diagnose sys sip-proxy calls": 25.0,
}
_DEFAULT_CMD_TIMEOUT = 28.0
_MORE_RE = re.compile(r"--\s*More\s*--", re.IGNORECASE)
_CLI_HELP_SUFFIX_RE = re.compile(r"\s*\?\s*$")


def format_fgt_cli_help_command(partial_command: str) -> str:
    """
    Monta comando de ajuda FortiOS com espaço obrigatório antes de «?».

    «show sys admin ?» e «show sys admin  ?» funcionam; «show sys admin?» não.
    O mesmo vale para «execute disconnect-admin-session ?» (única forma de listar INDEX).
    """
    base = _CLI_HELP_SUFFIX_RE.sub("", (partial_command or "").strip()).strip()
    if not base:
        raise ValueError("comando parcial vazio para ajuda CLI FortiOS")
    return f"{base} ?"


def _shell_has_more(text: str) -> bool:
    if not text:
        return False
    tail = text.rstrip()[-80:]
    return bool(_MORE_RE.search(tail))


def _disable_cli_pager(shell) -> None:
    """Desativa pager FortiOS (--More--) para coletas longas."""
    for line in ("config system console", "set output standard", "end"):
        shell.send(line + "\n")
        time.sleep(0.12)
    _read_until_prompt(shell, timeout=12.0)


def _read_until_prompt(shell, timeout: float = 30.0) -> str:
    buf = b""
    deadline = time.time() + timeout
    idle_start: Optional[float] = None
    while time.time() < deadline:
        if shell.recv_ready():
            chunk = shell.recv(65535)
            if not chunk:
                break
            buf += chunk
            idle_start = None
            text = buf.decode("utf-8", errors="replace")
            if _shell_has_more(text):
                shell.send(" ")
                continue
            if _fgt_prompt_ready(buf):
                break
        else:
            if idle_start is None:
                idle_start = time.time()
            elif time.time() - idle_start >= 1.2:
                text = buf.decode("utf-8", errors="replace")
                if _shell_has_more(text):
                    shell.send(" ")
                    idle_start = None
                    continue
                if _fgt_prompt_ready(buf):
                    break
            time.sleep(0.08)
    return buf.decode("utf-8", errors="replace")


def _clean_cli_output(out: str, cmd: str) -> str:
    lines = out.splitlines()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == cmd:
            continue
        if _MORE_RE.fullmatch(stripped):
            continue
        if stripped.endswith("#") and len(stripped) < 80:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _cmd_timeout_sec(cmd: str) -> float:
    c = (cmd or "").strip()
    if c.startswith("diag dvm device list"):
        return 90.0
    if c.startswith("execute vpn certificate local export"):
        try:
            return max(30.0, min(300.0, float(_env("PRODESP_CERTIFICADO_EXPORT_TIMEOUT", "120") or "120")))
        except ValueError:
            return 120.0
    return _CMD_TIMEOUTS.get(c, _DEFAULT_CMD_TIMEOUT)


def _exec_cli(shell, command: str) -> str:
    cmd = command.strip()
    timeout = _cmd_timeout_sec(cmd)
    shell.send(cmd + "\n")
    time.sleep(0.15)
    out = _read_until_prompt(shell, timeout=timeout)
    return _clean_cli_output(out, cmd)


def _clear_cli_line(shell) -> None:
    """Cancela comando parcial no console FortiOS (ex.: após «?» de ajuda)."""
    shell.send("\x03")
    time.sleep(0.12)
    _read_until_prompt(shell, timeout=8.0)


def _exec_cli_help(shell, partial_command: str, *, log_label: str = "") -> str:
    """
    Executa ajuda CLI (sempre «<parcial> ?» com espaço antes do ?).
    Limpa a linha parcial antes do próximo comando.
    """
    partial = _CLI_HELP_SUFFIX_RE.sub("", partial_command.strip()).strip()
    cmd = format_fgt_cli_help_command(partial)
    shell.send(cmd + "\n")
    time.sleep(0.25)
    out = _read_until_prompt(shell, timeout=_DEFAULT_CMD_TIMEOUT)
    _clear_cli_line(shell)
    cleaned = _clean_cli_output(out, partial)
    if log_label and log_label != partial:
        return cleaned
    return cleaned


def _exec_cli_config_delete_admin(shell) -> str:
    """Bloco config sys admin / delete admin / end (log passo a passo)."""
    chunks: list[str] = []
    for line in ("config sys admin", "delete admin", "end"):
        shell.send(line + "\n")
        time.sleep(0.15)
        timeout = 20.0 if line == "delete admin" else 12.0
        out = _read_until_prompt(shell, timeout=timeout)
        step_out = _clean_cli_output(out, line).strip()
        if step_out:
            chunks.append(f">>> {line}\n{step_out}")
        else:
            chunks.append(f">>> {line}\n(ok — FortiOS sem saída para este passo)")
    return "\n".join(chunks).strip()


def _connect_fgt(loopback_ip: str) -> tuple[paramiko.SSHClient, paramiko.SSHClient, str]:
    jump_user = _env("PRODESP_JUMP_USER")
    jump_pass = _env("PRODESP_JUMP_PASSWORD")
    fgt_user = _env("PRODESP_FGT_USER", "vvita")
    fgt_pass = _env("PRODESP_FGT_PASSWORD")
    connect_timeout = _ssh_connect_timeout()
    channel_timeout = _ssh_channel_timeout()

    if not jump_user or not jump_pass:
        raise RuntimeError(
            "Credenciais do jump não configuradas (PRODESP_JUMP_USER / PRODESP_JUMP_PASSWORD)."
        )
    if not fgt_pass:
        raise RuntimeError("Credencial FGT não configurada (PRODESP_FGT_PASSWORD).")

    ip = (loopback_ip or "").strip()
    if not ip or not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        raise ValueError("Loopback Vivo inválido para coleta SSH.")

    attempts: list[_JumpAttempt] = []
    jump_hosts = _jump_hosts()
    jump_plan = [
        (host, port)
        for idx, host in enumerate(jump_hosts)
        for port in _jump_ports_for_host(host, idx)
    ]
    _logger().info(
        "Coleta SSH FGT %s — jumps configurados: %s",
        ip,
        ", ".join(f"{h}:{p}" for h, p in jump_plan) or "(nenhum)",
    )
    for idx, jump_host in enumerate(jump_hosts):
        for jump_port in _jump_ports_for_host(jump_host, idx):
            jump = paramiko.SSHClient()
            jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            phase = "jump"
            try:
                jump.connect(
                    jump_host,
                    port=jump_port,
                    username=jump_user,
                    password=jump_pass,
                    timeout=connect_timeout,
                    banner_timeout=connect_timeout,
                    auth_timeout=connect_timeout,
                    look_for_keys=False,
                    allow_agent=False,
                )
                transport = jump.get_transport()
                if not transport:
                    raise RuntimeError("Transporte SSH do jump indisponível.")
                transport.set_keepalive(5)
                _logger().info(
                    "Jump %s:%s autenticado; abrindo túnel SSH para FGT %s:22",
                    jump_host,
                    jump_port,
                    ip,
                )
                phase = "tunnel"
                dest = (ip, 22)
                channel = transport.open_channel(
                    "direct-tcpip", dest, ("127.0.0.1", 0), timeout=channel_timeout
                )
                if channel is None:
                    raise TimeoutError(f"Túnel jump→FGT expirou ({channel_timeout:.0f}s)")
                channel.settimeout(channel_timeout)
                phase = "fgt"
                fgt = paramiko.SSHClient()
                fgt.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                fgt.connect(
                    ip,
                    username=fgt_user,
                    password=fgt_pass,
                    sock=channel,
                    timeout=channel_timeout,
                    banner_timeout=channel_timeout,
                    auth_timeout=channel_timeout,
                    look_for_keys=False,
                    allow_agent=False,
                )
                return jump, fgt, jump_host
            except (paramiko.SSHException, socket.error, OSError, TimeoutError, EOFError) as exc:
                attempts.append(
                    _JumpAttempt(
                        host=jump_host,
                        port=jump_port,
                        phase=phase,
                        error=str(exc) or type(exc).__name__,
                        error_type=type(exc).__name__,
                    )
                )
                try:
                    jump.close()
                except Exception:
                    pass
                if phase == "jump":
                    log_msg = "Falha ao conectar/autenticar no jump %s:%s: %s"
                    log_args = (jump_host, jump_port, exc)
                elif phase == "tunnel":
                    log_msg = (
                        "Jump %s:%s autenticou, mas túnel SSH para FGT %s:22 expirou (%ss): %s"
                    )
                    log_args = (jump_host, jump_port, ip, channel_timeout, exc)
                else:
                    log_msg = "Jump %s:%s — túnel aberto, mas FGT %s:22 falhou SSH: %s"
                    log_args = (jump_host, jump_port, ip, exc)
                _logger().warning(log_msg, *log_args)
                continue
    ping_diag = _run_connect_failure_ping_diag(
        ip,
        attempts,
        jump_user=jump_user,
        jump_pass=jump_pass,
        connect_timeout=connect_timeout,
    )
    if ping_diag:
        _logger().info("Coleta SSH FGT %s — %s", ip, ping_diag.replace("\n", " | "))
    raise RuntimeError(
        _summarize_connect_failures(
            ip,
            attempts,
            connect_timeout=connect_timeout,
            channel_timeout=channel_timeout,
            ping_diag=ping_diag,
        )
    )


FMG_PORTAL_ONLY_INI = "=== FMG DEVICE LIST (somente portal) ==="
FMG_PORTAL_ONLY_FIM = "=== FMG DEVICE LIST FIM ==="
_FMG_HOST_PADRAO = "10.254.253.6"
_FMG_BLOCK_RE = re.compile(
    re.escape(FMG_PORTAL_ONLY_INI) + r".*?" + re.escape(FMG_PORTAL_ONLY_FIM),
    re.DOTALL,
)
_IPV4_RE = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")


def _ipv4_valido(ip: str) -> bool:
    if not _IPV4_RE.fullmatch(ip or ""):
        return False
    return all(0 <= int(parte) <= 255 for parte in ip.split("."))


def _fmg_host() -> str:
    host = _env("PRODESP_FMG_HOST", _FMG_HOST_PADRAO) or _FMG_HOST_PADRAO
    if not _ipv4_valido(host):
        raise ValueError("PRODESP_FMG_HOST inválido.")
    return host


def _fmg_credentials() -> tuple[str, str]:
    user = _env("PRODESP_FMG_USER") or _env("PRODESP_FGT_USER", "vvita")
    password = _env("PRODESP_FMG_PASSWORD") or _env("PRODESP_FGT_PASSWORD")
    return user, password


def _open_ssh_via_jump(
    jump: paramiko.SSHClient,
    host: str,
    username: str,
    password: str,
) -> paramiko.SSHClient:
    """Abre SSH a partir do jump já autenticado (túnel direct-tcpip, origem no jump)."""
    if not username or not password:
        raise RuntimeError(
            "Credencial do FortiManager não configurada "
            "(PRODESP_FMG_PASSWORD ou PRODESP_FGT_PASSWORD)."
        )
    if not _ipv4_valido(host):
        raise ValueError("Host FortiManager inválido.")
    transport = jump.get_transport() if jump is not None else None
    if transport is None or not transport.is_active():
        raise RuntimeError("Sessão do jump indisponível para o FortiManager.")
    channel_timeout = _ssh_channel_timeout()
    channel = transport.open_channel(
        "direct-tcpip",
        (host, 22),
        ("127.0.0.1", 0),
        timeout=channel_timeout,
    )
    if channel is None:
        raise TimeoutError(f"Túnel jump→FortiManager expirou ({channel_timeout:.0f}s)")
    channel.settimeout(channel_timeout)
    remote = paramiko.SSHClient()
    remote.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        remote.connect(
            host,
            username=username,
            password=password,
            sock=channel,
            timeout=channel_timeout,
            banner_timeout=channel_timeout,
            auth_timeout=channel_timeout,
            look_for_keys=False,
            allow_agent=False,
        )
    except Exception:
        try:
            remote.close()
        except Exception:
            pass
        try:
            channel.close()
        except Exception:
            pass
        raise
    return remote


def _bloco_fmg_portal(corpo: str) -> str:
    return f"{FMG_PORTAL_ONLY_INI}\n{corpo.rstrip()}\n{FMG_PORTAL_ONLY_FIM}"


def remover_bloco_fmg_portal(text: str) -> str:
    """Tira a consulta FortiManager do texto que alimenta o caderno de teste."""
    raw = text or ""
    if FMG_PORTAL_ONLY_INI not in raw:
        return raw
    cleaned = _FMG_BLOCK_RE.sub("\n", raw)
    if FMG_PORTAL_ONLY_INI in cleaned:
        cleaned = cleaned.split(FMG_PORTAL_ONLY_INI, 1)[0]
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _coletar_fmg_device_list(
    jump: paramiko.SSHClient,
    *,
    id_intragov: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> tuple[str, str, int]:
    """
    No jump, após sair do FortiGate, consulta o FortiManager.

    Retorna (bloco_para_o_portal, erro_ou_vazio, comandos_executados).
    """
    id8 = id_intragov_para_grep_fmg(id_intragov)
    if not id8:
        msg = (
            "Consulta FortiManager não executada: ID Intragov ausente ou inválido "
            "(esperado número com sufixo /26, ex.: 0309472/26)."
        )
        return _bloco_fmg_portal(f"ERRO: {msg}"), msg, 0

    try:
        cmd = comando_diag_dvm_device_list(id8)
        host = _fmg_host()
    except ValueError as exc:
        msg = str(exc).strip() or "Parâmetro FortiManager inválido."
        return _bloco_fmg_portal(f"ERRO: {msg}"), msg, 0

    fmg = None
    try:
        if progress_cb:
            progress_cb(f"FortiManager {host}")
        user, password = _fmg_credentials()
        _logger().info("Coleta FMG %s via jump — id %s", host, id8)
        fmg = _open_ssh_via_jump(jump, host, user, password)
        shell = fmg.invoke_shell(width=400, height=80)
        time.sleep(0.6)
        _read_until_prompt(shell, timeout=12.0)
        out = _exec_cli(shell, cmd)
        try:
            shell.send("exit\n")
        except Exception:
            pass
        corpo = (
            f"FortiManager {host} | ID {id8}\n"
            f"--- {cmd} ---\n"
            f"{out or '(sem saída)'}"
        )
        return _bloco_fmg_portal(corpo), "", 1
    except Exception as exc:
        _logger().warning("Coleta FMG %s falhou: %s", host, type(exc).__name__)
        if isinstance(exc, (RuntimeError, ValueError, TimeoutError)):
            msg = str(exc).strip() or f"Falha ao consultar o FortiManager: {type(exc).__name__}"
        else:
            msg = f"Falha ao consultar o FortiManager: {type(exc).__name__}"
        return _bloco_fmg_portal(f"--- {cmd} ---\nERRO: {msg}"), msg, 0
    finally:
        close_ssh_clients(fmg)


def coletar_logs_fgt(
    loopback_ip: str,
    *,
    acronimo: str = "",
    modelo: str = "",
    equipamentos: Optional[list[dict]] = None,
    interfaces: Optional[tuple[str, ...]] = None,
    id_intragov: str = "",
    progress_cb: Optional[Callable[[str], None]] = None,
) -> FgtCollectResult:
    """
    Conecta no FGT e executa whitelist de comandos.
    equipamentos: lista {serial, modelo} — um bloco de log por serial cadastrado.
    """
    errors: list[str] = []
    blocks: list[str] = []
    cmds = _montar_lista_comandos(acronimo, modelo, interfaces)
    serials = equipamentos or [{"serial": "", "modelo": modelo}]
    if not serials:
        serials = [{"serial": "", "modelo": modelo}]

    jump = None
    fgt = None
    try:
        jump, fgt, via = _connect_fgt(loopback_ip)
        if progress_cb:
            progress_cb(f"Conectado via jump {via}")

        shell = fgt.invoke_shell(width=200, height=50)
        time.sleep(0.6)
        _read_until_prompt(shell, timeout=12.0)
        try:
            _disable_cli_pager(shell)
        except Exception:
            _logger().warning("Não foi possível desativar pager CLI FortiOS; fallback --More-- ativo.")

        total_cmds = 0
        serials_list = [
            (eq.get("serial") or "").strip()
            for eq in serials
            if (eq.get("serial") or "").strip()
        ]
        header = f"=== FGT {loopback_ip}"
        if serials_list:
            header += " | Serial(is): " + ", ".join(serials_list)
        header += " ==="
        blocks.append(header)

        sys_status_out = ""
        for cmd in cmds:
            if progress_cb:
                progress_cb(cmd)
            try:
                out = _exec_cli(shell, cmd)
                blocks.append(f"--- {cmd} ---\n{out or '(sem saída)'}")
                total_cmds += 1
                if cmd == CMD_GET_SYS_STATUS:
                    sys_status_out = out or ""
            except Exception as exc:
                msg = f"Falha em «{cmd}»: {type(exc).__name__}"
                errors.append(msg)
                blocks.append(f"--- {cmd} ---\nERRO: {msg}")

        if sys_status_out:
            resumo_sys = montar_resumo_sys_status(parse_get_sys_status(sys_status_out))
            if resumo_sys:
                blocks.append(resumo_sys)

        try:
            admin_blocks, admin_errors, admin_cmds = executar_limpeza_admin_fgt(
                shell,
                exec_help=lambda partial, label: _exec_cli_help(shell, partial, log_label=label),
                exec_cmd=lambda cmd: _exec_cli(shell, cmd),
                exec_config_delete=lambda: _exec_cli_config_delete_admin(shell),
                progress_cb=progress_cb,
            )
            blocks.extend(admin_blocks)
            errors.extend(admin_errors)
            total_cmds += admin_cmds
        except Exception as exc:
            msg = f"Falha na limpeza do usuário admin: {type(exc).__name__}"
            errors.append(msg)
            blocks.append(f"{LIMPEZA_ADMIN_ERRO_MARKER}\nERRO: {msg}")

        try:
            shell.send("exit\n")
        except Exception:
            pass
        close_ssh_clients(fgt)
        fgt = None

        try:
            fmg_text, fmg_err, fmg_n = _coletar_fmg_device_list(
                jump,
                id_intragov=id_intragov,
                progress_cb=progress_cb,
            )
        except Exception as exc:
            msg = f"Falha ao consultar o FortiManager: {type(exc).__name__}"
            _logger().warning("Coleta FMG interrompida: %s", type(exc).__name__)
            errors.append(msg)
            blocks.append(_bloco_fmg_portal(f"ERRO: {msg}"))
        else:
            if fmg_text:
                blocks.append(fmg_text)
            if fmg_err:
                errors.append(fmg_err)
            total_cmds += fmg_n

        text = "\n\n".join(blocks)
        return FgtCollectResult(
            ok=len(errors) == 0,
            logs_text=text,
            errors=errors,
            commands_run=total_cmds,
        )
    except Exception as exc:
        msg = str(exc).strip() if str(exc) else type(exc).__name__
        # Mensagens de connect / jump / FGT já são legíveis — sem stack completo no log.
        friendly = (
            "fortigate" in msg.lower()
            or "jump" in msg.lower()
            or "credencial" in msg.lower()
            or "túnel" in msg.lower()
            or "tunel" in msg.lower()
            or "ssh" in msg.lower()
            or "diagnóstico" in msg.lower()
            or "diagnostico" in msg.lower()
            or type(exc).__name__ in ("RuntimeError", "ValueError", "EOFError")
        )
        if friendly:
            _logger().warning("coletar_logs_fgt ref=%s: %s", loopback_ip, msg)
        else:
            _logger().exception("coletar_logs_fgt ref=%s", loopback_ip)
        return FgtCollectResult(
            ok=False,
            logs_text="",
            errors=[msg or "Falha na coleta SSH."],
        )
    finally:
        for cli in (fgt, jump):
            if cli:
                try:
                    cli.close()
                except Exception:
                    pass


def connect_fgt(loopback_ip: str) -> tuple[paramiko.SSHClient, paramiko.SSHClient, str]:
    """Conexão jump → túnel → FGT (reutilizável por coleta de logs e exportação de certificados)."""
    return _connect_fgt(loopback_ip)


def open_fgt_shell(fgt_client: paramiko.SSHClient):
    """Abre shell interativo FortiOS com pager desativado."""
    shell = fgt_client.invoke_shell(width=200, height=50)
    time.sleep(0.6)
    _read_until_prompt(shell, timeout=12.0)
    try:
        _disable_cli_pager(shell)
    except Exception:
        _logger().warning("Não foi possível desativar pager CLI FortiOS; fallback --More-- ativo.")
    return shell


def exec_fgt_cli(shell, command: str) -> str:
    return _exec_cli(shell, command)


def close_ssh_clients(*clients) -> None:
    for cli in clients:
        if cli:
            try:
                cli.close()
            except Exception:
                pass


_COLETA_MARKER_INI = "--- COLETA FGT AUTO INÍCIO ---"
_COLETA_MARKER_FIM = "--- COLETA FGT AUTO FIM ---"
_LEGACY_COLETA_LOG_PREFIX_RE = re.compile(
    r"^\[—\]\s*—:\s*(?=--- COLETA FGT AUTO INÍCIO ---)",
    re.MULTILINE,
)
_LEGACY_UI_LOG_LINE_PREFIX_RE = re.compile(r"(?m)^\[—\]\s*—:\s*")


def _strip_legacy_coleta_log_prefix(text: str) -> str:
    """Remove prefixo UI legado «[—] —:» (artefato do parseManualLogChunk no portal)."""
    raw = (text or "").strip()
    if not raw:
        return ""
    raw = _LEGACY_UI_LOG_LINE_PREFIX_RE.sub("", raw)
    return _LEGACY_COLETA_LOG_PREFIX_RE.sub("", raw).strip()


def sanitize_logs_atendimento_for_db(text: str) -> str:
    """Normaliza logs antes de gravar em atendimentos.logs_atendimentos."""
    return _strip_legacy_coleta_log_prefix(text)


def substituir_bloco_coleta_fgt(existing: str, new_block: str, max_chars: int = LOGS_ATENDIMENTOS_MAX) -> str:
    """Substitui bloco automático anterior; preserva logs manuais fora dos marcadores."""
    existing = sanitize_logs_atendimento_for_db(existing or "")
    new_block = sanitize_logs_atendimento_for_db(new_block or "")
    if not new_block:
        return existing
    wrapped = f"{_COLETA_MARKER_INI}\n{new_block}\n{_COLETA_MARKER_FIM}"
    if _COLETA_MARKER_INI in existing and _COLETA_MARKER_FIM in existing:
        antes = existing.split(_COLETA_MARKER_INI)[0].rstrip()
        depois = existing.split(_COLETA_MARKER_FIM, 1)[-1].lstrip()
        combined = f"{antes}\n\n{wrapped}\n\n{depois}".strip()
    elif existing:
        combined = f"{existing}\n\n{wrapped}".strip()
    else:
        combined = wrapped
    return truncate_mysql_text_field(combined, max_bytes=max_chars)


def extrair_bloco_coleta_fgt(text: str) -> str:
    """Retorna só o conteúdo entre os marcadores da coleta automática."""
    raw = (text or "").strip()
    if _COLETA_MARKER_INI not in raw or _COLETA_MARKER_FIM not in raw:
        return ""
    return raw.split(_COLETA_MARKER_INI, 1)[1].split(_COLETA_MARKER_FIM, 1)[0].strip()
