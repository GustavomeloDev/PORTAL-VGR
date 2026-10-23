"""Exportação de certificados locais FortiGate via SSH + TFTP (mesma conexão da coleta de logs)."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from prodesp.config_paths import (
    iter_pastas_certificado,
    network_base_ready,
    resolve_pasta_certificado,
)
from prodesp.prodesp.caderno.fgt_ssh_collector import (
    close_ssh_clients,
    connect_fgt,
    exec_fgt_cli,
    open_fgt_shell,
)
from prodesp.prodesp.caderno.fgt_ssh_tftp import (
    create_tftp_session,
    tftp_mode,
    tftp_port,
    tftp_timeout_sec,
)

_LOG = None


def _logger():
    global _LOG
    if _LOG is None:
        from core.logger import get_logger

        _LOG = get_logger("PRODESP")
    return _LOG


@dataclass
class CertExportItem:
    cert_name: str
    ok: bool
    filename: str = ""
    path_interno: str = ""
    path_externo: str = ""
    metodo: str = ""
    error: str = ""


def _pasta_relativa_historico(acronimo: str, hostname: str) -> str:
    acr = _sanitize_filename_part(acronimo) or "_sem_acronimo"
    host = _sanitize_filename_part(hostname) or "_sem_hostname"
    return f"{acr}/{host}/"


def _sanitizar_motivo_historico(motivo: str, *, max_len: int = 480) -> str:
    """Remove caminhos absolutos e compacta erros repetitivos antes de gravar no histórico."""
    text = (motivo or "").strip()
    if not text:
        return "Falha desconhecida."

    text = re.sub(r"[A-Za-z]:\\[^\s;\"']+", "[caminho omitido]", text)
    text = re.sub(r"/(?:Users|home|var/tmp|tmp)/[^\s;\"']+", "[caminho omitido]", text)

    partes = [p.strip() for p in re.split(r";(?=\s*\S+?:)", text) if p.strip()]
    if len(partes) > 2:
        padroes = {
            "built-in" in p.lower() or "build-in" in p.lower()
            for p in partes
        }
        if len(padroes) == 1 and True in padroes:
            primeiro = partes[0]
            if ":" in primeiro:
                cert = primeiro.split(":", 1)[0].strip()
                text = (
                    f"{cert}: certificado built-in Fortinet não exportável via TFTP "
                    f"(+{len(partes) - 1} certificado(s) Fortinet_* com o mesmo erro)."
                )
            else:
                text = f"{primeiro} (+{len(partes) - 1} erro(s) semelhante(s))."
        else:
            text = "; ".join(partes[:3])
            if len(partes) > 3:
                text += f" (+{len(partes) - 3} erro(s) adicional(is))."

    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


@dataclass
class CertExportResult:
    ok: bool
    hostname: str = ""
    acronimo: str = ""
    loopback_ip: str = ""
    tftp_ip: str = ""
    items: list[CertExportItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def historico_sucesso(self) -> str:
        lines = ["Exportação de certificado concluída com sucesso."]
        if self.elapsed_seconds:
            lines.append(f"Tempo: {self.elapsed_seconds}s")
        for it in self.items:
            if not it.ok:
                continue
            pasta = _pasta_relativa_historico(self.acronimo, self.hostname)
            lines.extend(
                [
                    "",
                    f"Hostname: {self.hostname or '—'}",
                    f"Secretaria: {self.acronimo or '—'}",
                    f"Certificado: {it.cert_name}",
                    f"Arquivo: {it.filename}",
                ]
            )
            if it.metodo:
                lines.append(f"Método: {it.metodo}")
            lines.append(f"Pasta interna: {pasta}")
            lines.append(
                f"Cópia na rede: sim ({pasta})" if it.path_externo else "Cópia na rede: não"
            )
        return "\n".join(lines).strip()

    def historico_falha(self, motivo: str) -> str:
        lines = ["Falha na exportação de certificado."]
        if self.hostname:
            lines.append(f"Hostname: {self.hostname}")
        if self.acronimo:
            lines.append(f"Secretaria: {self.acronimo}")
        lines.extend(["", f"Motivo: {_sanitizar_motivo_historico(motivo)}"])
        return "\n".join(lines).strip()


def _sanitize_filename_part(value: str, *, max_len: int = 60) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (value or "").strip())
    s = re.sub(r"\s+", "_", s).strip("._ ")
    return (s[:max_len] if s else "cert") or "cert"


def _unique_dest_path(directory: str, basename: str) -> str:
    os.makedirs(directory, exist_ok=True)
    candidate = os.path.join(directory, basename)
    if not os.path.exists(candidate):
        return candidate
    stem, ext = os.path.splitext(basename)
    n = 2
    while True:
        alt = os.path.join(directory, f"{stem}_{n}{ext}")
        if not os.path.exists(alt):
            return alt
        n += 1


@dataclass
class CertExportTarget:
    """Certificado alvo da exportação PRODESP (nome + formato FortiOS)."""

    name: str
    formato: str = "cer"  # cer | p12


def _certificados_alvo_config() -> list[CertExportTarget]:
    """
    Alvo padrão PRODESP: Fortinet_CA_SSL em .cer (documentação Fortinet).
    PRODESP_CERTIFICADO_FGT_NOME / PRODESP_CERTIFICADO_FGT_FORMATO no .env.
    """
    nome_raw = (os.environ.get("PRODESP_CERTIFICADO_FGT_NOME") or "Fortinet_CA_SSL").strip()
    fmt = (os.environ.get("PRODESP_CERTIFICADO_FGT_FORMATO") or "cer").strip().lower()
    if fmt not in ("cer", "p12"):
        fmt = "cer"
    targets: list[CertExportTarget] = []
    for part in nome_raw.replace(";", ",").split(","):
        n = part.strip()
        if n:
            targets.append(CertExportTarget(name=n, formato=fmt))
    return targets or [CertExportTarget(name="Fortinet_CA_SSL", formato="cer")]


def _eh_certificado_builtin_fortinet(cert_name: str, block: str = "") -> bool:
    """Certificados factory Fortinet (Fortinet_*) — p12 bloqueado; cer permitido para alvos configurados."""
    name = (cert_name or "").strip()
    if name.startswith("Fortinet_"):
        return True
    text = (block or "").lower()
    if re.search(r"source:\s*factory", text):
        return True
    if re.search(r"\bbuiltin\b", text):
        return True
    if re.search(r"build-in certificate", text):
        return True
    return False


def _parse_config_edit_cert_names(cli_output: str) -> list[str]:
    """Nomes em show full-configuration vpn certificate local (só entradas de config)."""
    names: list[str] = []
    for m in re.finditer(r'^\s*edit\s+"([^"]+)"', cli_output or "", re.MULTILINE):
        n = m.group(1).strip()
        if n and not _eh_certificado_builtin_fortinet(n) and n not in names:
            names.append(n)
    return names


def _parse_cert_blocks_exportaveis(cli_output: str) -> list[str]:
    """Parse get vpn certificate local por blocos, excluindo factory/built-in."""
    raw = cli_output or ""
    names: list[str] = []
    if not re.search(r"^\s*name:\s*", raw, re.MULTILINE | re.IGNORECASE):
        return names
    blocks = re.split(r"(?=^\s*name:\s*)", raw, flags=re.MULTILINE | re.IGNORECASE)
    for block in blocks:
        m = re.search(r"^\s*name:\s*(.+)$", block, re.MULTILINE | re.IGNORECASE)
        if not m:
            continue
        n = m.group(1).strip().strip('"')
        if not n or _eh_certificado_builtin_fortinet(n, block):
            continue
        if n not in names:
            names.append(n)
    return names


def _filtrar_certificados_exportaveis(names: list[str]) -> list[str]:
    return [n for n in names if not _eh_certificado_builtin_fortinet(n)]


def _parse_local_cert_names(cli_output: str) -> list[str]:
    """Extrai nomes de certificados locais a partir de get/show vpn certificate local."""
    raw = cli_output or ""
    names: list[str] = []

    for m in re.finditer(r"^\s*name:\s*(.+)$", raw, re.MULTILINE | re.IGNORECASE):
        n = m.group(1).strip().strip('"')
        if n and n not in names:
            names.append(n)
    if names:
        return names

    for m in re.finditer(r'^\s*edit\s+"([^"]+)"', raw, re.MULTILINE):
        n = m.group(1).strip()
        if n and n not in names:
            names.append(n)
    if names:
        return names

    skip = {
        "name",
        "subject",
        "issuer",
        "---",
        "certificate",
        "local",
        "cn",
        "type",
        "status",
        "valid",
        "invalid",
        "rsa",
        "ecdsa",
        "2048",
        "4096",
        "list",
        "==",
        "config",
        "edit",
        "set",
        "next",
        "end",
    }
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("=="):
            continue
        if re.match(r"^[-=]+$", stripped):
            continue
        if re.match(r"^(Local certificate|Certificate Name|Name\s+CN)", stripped, re.I):
            continue
        token = stripped.split()[0] if stripped.split() else ""
        low = token.lower().strip('"')
        if not token or low in skip or token.endswith(":"):
            continue
        if token.startswith("FG") and len(token) > 20:
            continue
        cert = token.strip('"')
        if cert not in names:
            names.append(cert)
    return names


def _fgt_export_indica_falha(cli_output: str) -> bool:
    """Detecta falha real no retorno FortiOS (evita falso positivo em campos «subject»)."""
    text = (cli_output or "").lower()
    patterns = (
        r"command fail",
        r"command failed",
        r"return code [1-9]",
        r"entry not found",
        r"no such certificate",
        r"cannot export",
        r"failed to export",
        r"error:\s",
        r"invalid certificate",
        r"password.*not.*set",
        r"no password",
    )
    return any(re.search(p, text) for p in patterns)


def certificado_export_method() -> str:
    """
    auto = .cer tenta CLI (SSH) primeiro, depois TFTP; .p12 usa TFTP.
    cli = somente extração PEM via SSH (sem TFTP).
    tftp = somente TFTP (comportamento anterior).
    """
    raw = (_env("PRODESP_CERTIFICADO_EXPORT_METHOD", "auto") or "auto").strip().lower()
    return raw if raw in ("auto", "cli", "tftp") else "auto"


def _extract_pem_blocks(text: str) -> list[str]:
    return re.findall(
        r"\s*-----BEGIN CERTIFICATE-----[\r\n]+(?:[A-Za-z0-9+/=\r\n ]+)-----END CERTIFICATE-----",
        text or "",
        re.MULTILINE,
    )


def _normalize_pem(pem: str) -> str:
    body = (pem or "").strip()
    if not body:
        return ""
    if not body.endswith("\n"):
        body += "\n"
    return body


def exportar_pem_certificado_cli(shell, cert_name: str) -> tuple[str, str]:
    """
    Obtém certificado .cer (PEM) via CLI SSH — sem TFTP/FTP.
    Retorna (pem, rótulo do método) ou ("", "").
    """
    quoted = _quote_cert_name(cert_name)
    commands = [
        (f"get vpn certificate local {quoted}", "CLI SSH (get vpn certificate local)"),
        ("get vpn certificate local", "CLI SSH (get vpn certificate local)"),
        (f"show vpn certificate local {quoted}", "CLI SSH (show vpn certificate local)"),
        ("show vpn certificate local", "CLI SSH (show vpn certificate local)"),
    ]
    for cmd, label in commands:
        try:
            out = exec_fgt_cli(shell, cmd)
            blocks = _extract_pem_blocks(out)
            if blocks:
                _logger().info("PEM «%s» obtido via CLI (%s)", cert_name, cmd)
                return _normalize_pem(blocks[0]), label
        except Exception as exc:
            _logger().warning("CLI cert (%s): %s", cmd, exc)

    try:
        for line in ("config vpn certificate local", f"edit {quoted}", "show full-configuration", "end"):
            out = exec_fgt_cli(shell, line)
            blocks = _extract_pem_blocks(out)
            if blocks:
                _logger().info("PEM «%s» obtido via config/show full-configuration", cert_name)
                return _normalize_pem(blocks[0]), "CLI SSH (show full-configuration)"
    except Exception as exc:
        _logger().warning("CLI cert config/show: %s", exc)

    return "", ""


def _gravar_pem_temporario(pem: str, directory: str, filename: str) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(pem)
    return path


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _quote_cert_name(cert_name: str) -> str:
    """FortiOS exige aspas se o nome tiver espaço."""
    name = (cert_name or "").strip()
    if re.search(r"\s", name) and not (name.startswith('"') and name.endswith('"')):
        return f'"{name}"'
    return name


def _log_ips_locais_portal() -> None:
    """Diagnóstico: IPs da máquina do Portal (útil para PRODESP_TFTP_IP)."""
    import socket

    from prodesp.prodesp.caderno.fgt_ssh_tftp import _ip_via_udp_route

    collected: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            collected.add(info[4][0])
    except OSError:
        pass
    jump = _env("PRODESP_JUMP_HOST_1", "172.19.40.2")
    via_jump = _ip_via_udp_route(jump)
    if via_jump:
        collected.add(via_jump)
    if collected:
        _logger().info("IPs locais Portal (candidatos TFTP): %s", ", ".join(sorted(collected)))


def resolver_certificados_alvo_fgt(shell) -> tuple[list[CertExportTarget], list[str]]:
    """
    Confere no FGT se o(s) certificado(s) alvo PRODESP existem.
    Retorna (alvos resolvidos, todos os nomes locais listados).
    """
    alvo_cfg = _certificados_alvo_config()
    todos: list[str] = []
    for cmd in ("get vpn certificate local", "show vpn certificate local"):
        try:
            out = exec_fgt_cli(shell, cmd)
            names = _parse_local_cert_names(out)
            if names:
                todos = names
                break
        except Exception as exc:
            _logger().warning("listar certificados (%s): %s", cmd, exc)

    on_device = set(todos)
    resolved = [t for t in alvo_cfg if t.name in on_device]
    missing = [t.name for t in alvo_cfg if t.name not in on_device]
    if resolved:
        _logger().info(
            "certificado(s) alvo PRODESP no FGT: %s",
            ", ".join(f"{t.name} ({t.formato})" for t in resolved),
        )
    if missing:
        _logger().warning("certificado(s) alvo ausente(s) no FGT: %s", ", ".join(missing))
    return resolved, todos


def _extensao_certificado(formato: str) -> str:
    return ".p12" if (formato or "").lower() == "p12" else ".cer"


def _nome_arquivo_certificado_exportado(cert_name: str, ext: str) -> str:
    """Padrão operacional: Fortinet_CA_SSL.cer (sem hostname/timestamp)."""
    part = _sanitize_filename_part(cert_name) or "cert"
    return f"{part}{ext}"


def _mover_certificado_recebido(
    *,
    staging_path: str,
    acronimo: str,
    hostname: str,
    cert_name: str,
    timestamp: datetime,
    ext: str = ".cer",
) -> tuple[str, str, str]:
    del timestamp  # mantido na assinatura — pasta {acronimo}/{hostname}/ já identifica a unidade
    basename = _nome_arquivo_certificado_exportado(cert_name, ext)

    pasta_interna = resolve_pasta_certificado(acronimo, hostname, rede=False)
    os.makedirs(pasta_interna, exist_ok=True)
    path_interno = os.path.join(pasta_interna, basename)
    shutil.copy2(staging_path, path_interno)

    path_externo = ""
    for pasta_externa in iter_pastas_certificado(acronimo, hostname, rede=True):
        if not pasta_externa:
            continue
        if not network_base_ready(pasta_externa):
            _logger().info(
                "Base de certificado indisponível, tentando fallback: %s", pasta_externa
            )
            continue
        try:
            os.makedirs(pasta_externa, exist_ok=True)
            dest = os.path.join(pasta_externa, basename)
            shutil.copy2(staging_path, dest)
            path_externo = dest
            break
        except OSError as exc:
            _logger().warning("cópia certificado rede falhou (%s): %s", pasta_externa, exc)

    return basename, path_interno, path_externo


def exportar_certificados_fgt(
    loopback_ip: str,
    *,
    acronimo: str,
    hostname: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> CertExportResult:
    """
    Conecta no FGT (jump → loopback), lista certificados locais e exporta via CLI SSH
    (PEM/.cer) ou TFTP conforme PRODESP_CERTIFICADO_EXPORT_METHOD.
    """
    t0 = time.time()
    errors: list[str] = []
    items: list[CertExportItem] = []
    ip = (loopback_ip or "").strip()
    host = (hostname or "").strip()
    acr = (acronimo or "").strip()

    jump = None
    fgt = None
    shell = None
    tftp_session = None

    try:
        if progress_cb:
            progress_cb("Conectando via jump server…")
        jump, fgt, via = connect_fgt(ip)
        if progress_cb:
            progress_cb(f"Conectado via jump {via}")

        shell = open_fgt_shell(fgt)
        cert_targets, todos_certs = resolver_certificados_alvo_fgt(shell)
        if not cert_targets:
            alvo_nomes = ", ".join(t.name for t in _certificados_alvo_config())
            if todos_certs:
                msg = (
                    f"Certificado alvo «{alvo_nomes}» não encontrado no FortiGate. "
                    f"Certificados locais detectados: {len(todos_certs)}."
                )
            else:
                msg = f"Certificado alvo «{alvo_nomes}» não encontrado no FortiGate."
            return CertExportResult(
                ok=False,
                hostname=host,
                acronimo=acr,
                loopback_ip=ip,
                errors=[msg],
                elapsed_seconds=round(time.time() - t0, 1),
            )

        method = certificado_export_method()
        _log_ips_locais_portal()
        staging_dir = tempfile.mkdtemp(prefix="prodesp_cert_staging_")
        tftp_session = None
        tftp_ip = ""
        tftp_started = False
        use_tftp = method == "tftp" or (method == "auto" and any(t.formato == "p12" for t in cert_targets))

        if use_tftp or method == "auto":
            tftp_session, tftp_ip = create_tftp_session(jump, jump_host=via, fgt_ip=ip)
            port = tftp_port()
            _logger().info(
                "Export method=%s TFTP=%s FGT=%s → %s:%s",
                method,
                tftp_mode(),
                ip,
                tftp_ip,
                port,
            )
            if use_tftp:
                tftp_session.start()
                tftp_started = True
                if progress_cb:
                    progress_cb(f"Servidor TFTP ativo em {tftp_ip}:{port} ({tftp_mode()})")

        for target in cert_targets:
            cert_name = target.name
            fmt = target.formato
            ext = _extensao_certificado(fmt)
            if progress_cb:
                progress_cb(f"Exportando certificado «{cert_name}» ({fmt})…")
            ts = datetime.now()
            staging_name = (
                f"export_{_sanitize_filename_part(cert_name)}_{ts.strftime('%Y%m%d_%H%M%S')}{ext}"
            )
            exported = False

            if fmt == "cer" and method in ("auto", "cli"):
                if progress_cb:
                    progress_cb(f"Obtendo «{cert_name}» via CLI SSH…")
                pem, metodo_cli = exportar_pem_certificado_cli(shell, cert_name)
                if pem:
                    try:
                        staging_path = _gravar_pem_temporario(pem, staging_dir, staging_name)
                        fname, path_int, path_ext = _mover_certificado_recebido(
                            staging_path=staging_path,
                            acronimo=acr,
                            hostname=host,
                            cert_name=cert_name,
                            timestamp=ts,
                            ext=ext,
                        )
                        items.append(
                            CertExportItem(
                                cert_name=cert_name,
                                ok=True,
                                filename=fname,
                                path_interno=path_int,
                                path_externo=path_ext,
                                metodo=metodo_cli,
                            )
                        )
                        exported = True
                    except OSError as exc:
                        items.append(
                            CertExportItem(
                                cert_name=cert_name,
                                ok=False,
                                error=f"Falha ao gravar arquivo: {exc}",
                            )
                        )
                        errors.append(f"{cert_name}: {exc}")
                elif method == "cli":
                    msg = (
                        f"Certificado «{cert_name}» não retornou PEM via CLI SSH. "
                        "Fortinet_CA_SSL built-in pode exigir TFTP ou exportação manual pela GUI."
                    )
                    items.append(CertExportItem(cert_name=cert_name, ok=False, error=msg))
                    errors.append(f"{cert_name}: {msg}")
                    continue

            if exported:
                continue

            if method == "cli":
                continue

            if not tftp_session:
                tftp_session, tftp_ip = create_tftp_session(jump, jump_host=via, fgt_ip=ip)
            if not tftp_started:
                tftp_session.start()
                tftp_started = True
                if progress_cb:
                    progress_cb(f"Fallback TFTP em {tftp_ip}:{tftp_port()}")

            quoted = _quote_cert_name(cert_name)
            cmd = (
                f"execute vpn certificate local export tftp {quoted} {fmt} "
                f"{staging_name} {tftp_ip}"
            )
            try:
                out = exec_fgt_cli(shell, cmd)
                if _fgt_export_indica_falha(out):
                    err_detail = (out or "").strip().replace("\n", " ")[:400]
                    err_msg = f"FortiGate retornou erro: {err_detail or '(sem detalhe)'}"
                    _logger().warning("export cert «%s»: %s", cert_name, err_msg)
                    items.append(
                        CertExportItem(cert_name=cert_name, ok=False, error=err_msg)
                    )
                    errors.append(f"{cert_name}: {err_msg}")
                    continue
            except Exception as exc:
                err_msg = str(exc) or type(exc).__name__
                items.append(CertExportItem(cert_name=cert_name, ok=False, error=err_msg))
                errors.append(f"{cert_name}: {err_msg}")
                continue

            deadline = time.time() + tftp_timeout_sec()
            res = tftp_session.wait_for_file(staging_name, max(5.0, deadline - time.time()))
            if not res.ok or not res.path or not os.path.isfile(res.path):
                msg = res.error or (
                    f"Timeout TFTP aguardando certificado «{cert_name}». "
                    f"Verifique se o FGT alcança {tftp_ip}:69."
                )
                items.append(CertExportItem(cert_name=cert_name, ok=False, error=msg))
                errors.append(f"{cert_name}: {msg}")
                continue

            try:
                fname, path_int, path_ext = _mover_certificado_recebido(
                    staging_path=res.path,
                    acronimo=acr,
                    hostname=host,
                    cert_name=cert_name,
                    timestamp=ts,
                    ext=ext,
                )
                items.append(
                    CertExportItem(
                        cert_name=cert_name,
                        ok=True,
                        filename=fname,
                        path_interno=path_int,
                        path_externo=path_ext,
                        metodo="TFTP",
                    )
                )
            except OSError as exc:
                items.append(
                    CertExportItem(
                        cert_name=cert_name,
                        ok=False,
                        error=f"Falha ao gravar arquivo: {exc}",
                    )
                )

            tftp_session.restart()

        if staging_dir and os.path.isdir(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)

        ok_any = any(it.ok for it in items)
        if not ok_any and not errors:
            errors.append("Nenhum certificado foi exportado com sucesso.")
        elif not ok_any and errors:
            _logger().warning("exportação certificados FGT %s falhou: %s", ip, "; ".join(errors[:5]))
        return CertExportResult(
            ok=ok_any,
            hostname=host,
            acronimo=acr,
            loopback_ip=ip,
            tftp_ip=tftp_ip,
            items=items,
            errors=errors,
            elapsed_seconds=round(time.time() - t0, 1),
        )
    except Exception as exc:
        msg = str(exc).strip() or type(exc).__name__
        _logger().warning("exportar_certificados_fgt %s: %s", ip, msg)
        return CertExportResult(
            ok=False,
            hostname=host,
            acronimo=acr,
            loopback_ip=ip,
            items=items,
            errors=[msg],
            elapsed_seconds=round(time.time() - t0, 1),
        )
    finally:
        if tftp_session:
            tftp_session.stop()
        close_ssh_clients(fgt, jump)
