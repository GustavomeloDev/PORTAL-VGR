"""Coleta SSH FortiGate: direto no loopback ou via jump (paramiko)."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import paramiko

from core.fgt_coleta.admin_cleanup import (
    LIMPEZA_ADMIN_ERRO_MARKER,
    executar_limpeza_admin_fgt,
    extrair_resumo_limpeza_admin_coleta,
)
from core.fgt_coleta.cli_help import format_fgt_cli_help_command
from core.fgt_coleta.commands import comandos_perfil
from core.fgt_coleta.credentials import resolve_fgt_ssh_credentials
from core.fgt_coleta.sys_status import montar_resumo_sys_status, parse_get_sys_status

log = logging.getLogger("core.fgt_coleta")

_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_MORE_RE = re.compile(r"--\s*More\s*--", re.IGNORECASE)
_CLI_HELP_SUFFIX_RE = re.compile(r"\s*\?\s*$")
_DEFAULT_CMD_TIMEOUT = 28.0
_CMD_TIMEOUTS = {
    "show system interface": 60.0,
    "show sys interface": 60.0,
    "diagnose sys sdwan service4": 45.0,
    "diagnose sys sdwan health-check": 35.0,
    "get router info routing-table all": 40.0,
}


@dataclass
class FgtCollectResult:
    ok: bool
    logs_text: str = ""
    errors: list[str] = field(default_factory=list)
    commands_run: int = 0
    admin_resumo: str = ""
    sys_status: dict[str, str] = field(default_factory=dict)


def _fgt_prompt_ready(buf: bytes) -> bool:
    try:
        text = buf.decode("utf-8", errors="replace")
    except Exception:
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    last = lines[-1]
    return bool(re.search(r"#\s*$", last)) and len(last) < 120


def _shell_has_more(text: str) -> bool:
    if not text:
        return False
    return bool(_MORE_RE.search(text.rstrip()[-80:]))


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
    cleaned: list[str] = []
    for line in out.splitlines():
        stripped = line.strip()
        if stripped == cmd:
            continue
        if _MORE_RE.fullmatch(stripped):
            continue
        if stripped.endswith("#") and len(stripped) < 80:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _cmd_timeout(cmd: str) -> float:
    c = (cmd or "").strip()
    if c.startswith("execute ping"):
        return 22.0
    return _CMD_TIMEOUTS.get(c, _DEFAULT_CMD_TIMEOUT)


def _disable_cli_pager(shell) -> None:
    for line in ("config system console", "set output standard", "end"):
        shell.send(line + "\n")
        time.sleep(0.12)
    _read_until_prompt(shell, timeout=12.0)


def _exec_cli(shell, command: str) -> str:
    cmd = command.strip()
    shell.send(cmd + "\n")
    time.sleep(0.15)
    out = _read_until_prompt(shell, timeout=_cmd_timeout(cmd))
    return _clean_cli_output(out, cmd)


def _clear_cli_line(shell) -> None:
    shell.send("\x03")
    time.sleep(0.12)
    _read_until_prompt(shell, timeout=8.0)


def _exec_cli_help(shell, partial_command: str, *, log_label: str = "") -> str:
    del log_label
    partial = _CLI_HELP_SUFFIX_RE.sub("", partial_command.strip()).strip()
    cmd = format_fgt_cli_help_command(partial)
    shell.send(cmd + "\n")
    time.sleep(0.25)
    out = _read_until_prompt(shell, timeout=_DEFAULT_CMD_TIMEOUT)
    _clear_cli_line(shell)
    return _clean_cli_output(out, partial)


def _exec_cli_config_delete_admin(shell) -> str:
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


def _connect_direct(ip: str, user: str, password: str, timeout: float) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        ip,
        port=22,
        username=user,
        password=password,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def _connect_jump(
    ip: str,
    *,
    user: str,
    password: str,
    jump_host: str,
    jump_port: int,
    jump_user: str,
    jump_password: str,
    timeout: float,
) -> tuple[paramiko.SSHClient, paramiko.SSHClient]:
    jump = paramiko.SSHClient()
    jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    jump.connect(
        jump_host,
        port=jump_port,
        username=jump_user,
        password=jump_password,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        look_for_keys=False,
        allow_agent=False,
    )
    transport = jump.get_transport()
    if not transport:
        jump.close()
        raise RuntimeError("Transporte SSH do jump indisponível.")
    channel = transport.open_channel("direct-tcpip", (ip, 22), ("127.0.0.1", 0), timeout=timeout)
    fgt = paramiko.SSHClient()
    fgt.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    fgt.connect(
        ip,
        username=user,
        password=password,
        sock=channel,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        look_for_keys=False,
        allow_agent=False,
    )
    return jump, fgt


def _sanitizar_erro_ssh(msg: str, *, password: str = "") -> str:
    text = " ".join((msg or "").split())
    if password and password in text:
        text = text.replace(password, "***")
    return text[:400] or "Falha na coleta SSH."


def coletar_logs_fgt(
    loopback_ip: str,
    *,
    perfil: str = "dma",
    progress_cb: Optional[Callable[[str], None]] = None,
) -> FgtCollectResult:
    """Executa whitelist do perfil + limpeza do usuário admin (mesmo fluxo PRODESP)."""
    ip = (loopback_ip or "").strip()
    if not ip or not _IP_RE.match(ip):
        return FgtCollectResult(ok=False, errors=["Loopback Vivo inválido para coleta SSH."])
    creds = resolve_fgt_ssh_credentials()
    if not creds.password:
        return FgtCollectResult(
            ok=False,
            errors=["Credencial FGT não configurada (FGT_SSH_PASSWORD ou PRODESP_FGT_PASSWORD)."],
        )
    cmds = comandos_perfil(perfil)
    jump = None
    fgt = None
    errors: list[str] = []
    blocks: list[str] = [f"=== FGT {ip} ==="]
    total = 0
    sys_parsed: dict[str, str] = {}
    try:
        if creds.mode == "jump":
            if not (creds.jump_host and creds.jump_user and creds.jump_password):
                return FgtCollectResult(
                    ok=False,
                    errors=[
                        "Modo jump exige FGT_JUMP_HOST / FGT_JUMP_USER / FGT_JUMP_PASSWORD "
                        "(ou PRODESP_JUMP_*)."
                    ],
                )
            if progress_cb:
                progress_cb(f"Conectando via jump {creds.jump_host}")
            jump, fgt = _connect_jump(
                ip,
                user=creds.user,
                password=creds.password,
                jump_host=creds.jump_host,
                jump_port=creds.jump_port,
                jump_user=creds.jump_user,
                jump_password=creds.jump_password,
                timeout=15.0,
            )
        else:
            if progress_cb:
                progress_cb(f"Conectando direto em {ip}")
            fgt = _connect_direct(ip, creds.user, creds.password, timeout=15.0)
        shell = fgt.invoke_shell(width=200, height=50)
        time.sleep(0.6)
        _read_until_prompt(shell, timeout=12.0)
        try:
            _disable_cli_pager(shell)
        except Exception:
            log.warning("Não foi possível desativar pager CLI FortiOS.")

        sys_out = ""
        for cmd in cmds:
            if progress_cb:
                progress_cb(cmd)
            try:
                out = _exec_cli(shell, cmd)
                blocks.append(f"--- {cmd} ---\n{out or '(sem saída)'}")
                total += 1
                if cmd in ("get system status", "get sys status"):
                    sys_out = out or ""
            except Exception as exc:
                msg = f"Falha em «{cmd}»: {type(exc).__name__}"
                errors.append(msg)
                blocks.append(f"--- {cmd} ---\nERRO: {msg}")

        if sys_out:
            sys_parsed = parse_get_sys_status(sys_out)
            resumo = montar_resumo_sys_status(sys_parsed)
            if resumo:
                blocks.append(resumo)

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
            total += admin_cmds
        except Exception as exc:
            msg = f"Falha na limpeza do usuário admin: {type(exc).__name__}"
            errors.append(msg)
            blocks.append(f"{LIMPEZA_ADMIN_ERRO_MARKER}\nERRO: {msg}")

        text = "\n\n".join(blocks)
        admin_resumo = extrair_resumo_limpeza_admin_coleta(text)
        return FgtCollectResult(
            ok=len(errors) == 0,
            logs_text=text,
            errors=errors,
            commands_run=total,
            admin_resumo=admin_resumo,
            sys_status=sys_parsed,
        )
    except Exception as exc:
        msg = _sanitizar_erro_ssh(str(exc), password=creds.password)
        log.warning("coletar_logs_fgt ref=%s: %s", ip, type(exc).__name__)
        return FgtCollectResult(ok=False, errors=[msg])
    finally:
        for client in (fgt, jump):
            if client is None:
                continue
            try:
                client.close()
            except Exception:
                pass
