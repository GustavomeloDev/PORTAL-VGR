"""Servidor TFTP temporário (Python puro) para receber exportação do FortiGate."""
from __future__ import annotations

import os
import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Optional

_OP_RRQ = 1
_OP_WRQ = 2
_OP_DATA = 3
_OP_ACK = 4
_OP_ERROR = 5

_LOG = None


def _logger():
    global _LOG
    if _LOG is None:
        from core.logger import get_logger

        _LOG = get_logger("PRODESP")
    return _LOG


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _ip_via_udp_route(target: str) -> str:
    target = (target or "").strip()
    if not target:
        return ""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target, 9))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        sock.close()
    return ""


def tftp_mode() -> str:
    """
    local (padrão) = TFTP temporário na máquina do Portal, conforme requisito original.
    jump = fallback opcional — TFTP no jump Linux (PRODESP_TFTP_MODE=jump).
    """
    mode = (_env("PRODESP_TFTP_MODE", "local") or "local").strip().lower()
    return mode if mode in ("jump", "local") else "local"


def resolve_tftp_server_ip(*, jump_host: str, fgt_ip: str) -> str:
    """IP informado ao FortiGate como destino TFTP."""
    manual = _env("PRODESP_TFTP_IP")
    if manual:
        return manual
    if tftp_mode() == "jump":
        return (jump_host or _env("PRODESP_JUMP_HOST_1", "172.19.40.2")).strip()
    return detect_portal_tftp_ip(fallback_host=jump_host)


def detect_portal_tftp_ip(*, fallback_host: str = "") -> str:
    """
    IP local do Portal usado como destino TFTP pelo FortiGate.
    Prioridade: PRODESP_TFTP_IP > rota UDP ao jump (mesmo caminho SSH) > hostname.
    """
    manual = _env("PRODESP_TFTP_IP")
    if manual:
        return manual

    for target in (fallback_host, _env("PRODESP_JUMP_HOST_1", "172.19.40.2")):
        ip = _ip_via_udp_route(target)
        if ip:
            return ip

    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def tftp_port() -> int:
    try:
        return max(1, min(65535, int(_env("PRODESP_TFTP_PORT", "69") or "69")))
    except ValueError:
        return 69


def tftp_timeout_sec() -> float:
    try:
        return max(5.0, min(300.0, float(_env("PRODESP_TFTP_TIMEOUT", "120") or "120")))
    except ValueError:
        return 120.0


@dataclass
class TftpReceiveResult:
    ok: bool
    filename: str = ""
    path: str = ""
    bytes_received: int = 0
    error: str = ""


class TftpWriteServer:
    """
    Servidor TFTP mínimo (WRQ → DATA → ACK) em thread daemon.

    FortiGate envia todos os pacotes TFTP para a porta do servidor (69).
    A transferência usa o mesmo socket da escuta — não porta efêmera.
    """

    def __init__(self, root_dir: str, *, port: Optional[int] = None, timeout: float = 120.0):
        self.root_dir = os.path.abspath(root_dir)
        os.makedirs(self.root_dir, exist_ok=True)
        self.port = port if port is not None else tftp_port()
        self.timeout = timeout
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._result = TftpReceiveResult(ok=False)
        self._lock = threading.Lock()

    @property
    def result(self) -> TftpReceiveResult:
        with self._lock:
            return self._result

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        with self._lock:
            self._result = TftpReceiveResult(ok=False)
        self._thread = threading.Thread(target=self._run, name="prodesp-tftp", daemon=True)
        self._thread.start()
        time.sleep(0.15)

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _set_result(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self._result, k, v)

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock = sock
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.port))
            sock.settimeout(1.0)
            deadline = time.time() + self.timeout
            while not self._stop.is_set() and time.time() < deadline:
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if len(data) < 4:
                    continue
                opcode = struct.unpack("!H", data[:2])[0]
                if opcode == _OP_WRQ:
                    _logger().info(
                        "TFTP WRQ de %s:%s (%d bytes)",
                        addr[0],
                        addr[1],
                        len(data),
                    )
                    self._handle_wrq(sock, data, addr)
                    if self.result.ok:
                        _logger().info(
                            "TFTP recebido: %s (%d bytes)",
                            self.result.filename,
                            self.result.bytes_received,
                        )
                        break
        finally:
            try:
                sock.close()
            except OSError:
                pass
            self._sock = None

    def _handle_wrq(self, sock: socket.socket, data: bytes, addr) -> None:
        parts = data[2:].split(b"\x00")
        if len(parts) < 2:
            return
        filename = parts[0].decode("utf-8", errors="replace").strip()
        if not filename or ".." in filename or filename.startswith(("/", "\\")):
            self._send_error(sock, addr, 2, "Acesso negado")
            return
        safe_name = os.path.basename(filename.replace("\\", "/"))
        dest_path = os.path.join(self.root_dir, safe_name)

        block = 0
        received = 0
        last_ack = struct.pack("!HH", _OP_ACK, 0)
        sock.sendto(last_ack, addr)

        deadline = time.time() + self.timeout
        sock.settimeout(2.0)
        try:
            with open(dest_path, "wb") as handle:
                while not self._stop.is_set() and time.time() < deadline:
                    try:
                        pkt, from_addr = sock.recvfrom(65535)
                    except socket.timeout:
                        sock.sendto(last_ack, addr)
                        continue
                    except OSError:
                        break
                    if len(pkt) < 4:
                        continue
                    op, blk = struct.unpack("!HH", pkt[:4])
                    if op == _OP_WRQ:
                        continue
                    if op != _OP_DATA:
                        continue
                    if blk == block + 1:
                        chunk = pkt[4:]
                        handle.write(chunk)
                        received += len(chunk)
                        block += 1
                        last_ack = struct.pack("!HH", _OP_ACK, block)
                        sock.sendto(last_ack, from_addr)
                        if len(chunk) < 512:
                            self._set_result(
                                ok=True,
                                filename=safe_name,
                                path=dest_path,
                                bytes_received=received,
                                error="",
                            )
                            return
                    elif blk == block and block > 0:
                        sock.sendto(last_ack, from_addr)
            self._set_result(ok=False, error="Timeout aguardando pacotes TFTP.")
        except OSError as exc:
            self._set_result(ok=False, error=f"Falha ao gravar arquivo TFTP: {exc}")

    def _send_error(self, sock: socket.socket, addr, code: int, msg: str) -> None:
        payload = struct.pack("!H", _OP_ERROR) + struct.pack("!H", code) + msg.encode("utf-8") + b"\x00"
        sock.sendto(payload, addr)


# Script mínimo enviado ao jump via SFTP (python3 stdlib only).
_JUMP_TFTP_RECEIVER_SCRIPT = r'''#!/usr/bin/env python3
import argparse, os, socket, struct, sys, time
OP_WRQ, OP_DATA, OP_ACK = 2, 3, 4

def serve(root, port, timeout):
    os.makedirs(root, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(1.0)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        if len(data) < 4 or struct.unpack("!H", data[:2])[0] != OP_WRQ:
            continue
        parts = data[2:].split(b"\x00")
        if len(parts) < 2:
            continue
        name = os.path.basename(parts[0].decode("utf-8", errors="replace"))
        if not name or ".." in name:
            continue
        path = os.path.join(root, name)
        block = 0
        last_ack = struct.pack("!HH", OP_ACK, 0)
        sock.sendto(last_ack, addr)
        sock.settimeout(2.0)
        with open(path, "wb") as handle:
            while time.time() < deadline:
                try:
                    pkt, from_addr = sock.recvfrom(65535)
                except socket.timeout:
                    sock.sendto(last_ack, addr)
                    continue
                if len(pkt) < 4:
                    continue
                op, blk = struct.unpack("!HH", pkt[:4])
                if op != OP_DATA:
                    continue
                if blk == block + 1:
                    chunk = pkt[4:]
                    handle.write(chunk)
                    block += 1
                    last_ack = struct.pack("!HH", OP_ACK, block)
                    sock.sendto(last_ack, from_addr)
                    if len(chunk) < 512:
                        with open(os.path.join(root, ".tftp_ok"), "w") as ok:
                            ok.write(name)
                        return 0
                elif blk == block and block > 0:
                    sock.sendto(last_ack, from_addr)
    return 1

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--port", type=int, default=69)
    p.add_argument("--timeout", type=int, default=120)
    args = p.parse_args()
    sys.exit(serve(args.root, args.port, args.timeout))
'''


class LocalTftpSession:
    """TFTP na máquina do Portal."""

    def __init__(self, server_ip: str):
        self.server_ip = server_ip
        self.staging_dir = ""
        self._srv: Optional[TftpWriteServer] = None

    def start(self) -> None:
        import tempfile

        self.staging_dir = tempfile.mkdtemp(prefix="prodesp_cert_tftp_")
        port = tftp_port()
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("0.0.0.0", port))
            probe.close()
        except OSError as exc:
            raise RuntimeError(
                f"Não foi possível abrir UDP {port} no Portal ({exc}). "
                "No Windows, porta 69 pode exigir executar como Administrador "
                "ou liberar firewall inbound UDP 69."
            ) from exc
        self._srv = TftpWriteServer(self.staging_dir, timeout=tftp_timeout_sec(), port=port)
        self._srv.start()
        _logger().info(
            "TFTP local ativo: FGT deve enviar para %s:%s (pasta %s)",
            self.server_ip,
            port,
            self.staging_dir,
        )

    def stop(self) -> None:
        if self._srv:
            self._srv.stop()
            self._srv = None
        if self.staging_dir and os.path.isdir(self.staging_dir):
            import shutil

            shutil.rmtree(self.staging_dir, ignore_errors=True)
        self.staging_dir = ""

    def restart(self) -> None:
        if self._srv:
            self._srv.stop()
        if not self.staging_dir:
            import tempfile

            self.staging_dir = tempfile.mkdtemp(prefix="prodesp_cert_tftp_")
        self._srv = TftpWriteServer(self.staging_dir, timeout=tftp_timeout_sec())
        self._srv.start()

    def wait_for_file(self, expected_name: str, timeout: float) -> TftpReceiveResult:
        if not self._srv:
            return TftpReceiveResult(ok=False, error="Servidor TFTP local inativo.")
        deadline = time.time() + timeout
        while time.time() < deadline:
            res = self._srv.result
            if res.ok and res.path and os.path.isfile(res.path):
                if not expected_name or res.filename == expected_name or expected_name in res.filename:
                    return res
            time.sleep(0.25)
        return TftpReceiveResult(ok=False, error="Timeout TFTP local aguardando arquivo.")


class JumpTftpSession:
    """TFTP no jump server Linux — FGT envia para IP do jump (rede alcançável)."""

    def __init__(self, jump_ssh, *, server_ip: str):
        self.jump = jump_ssh
        self.server_ip = server_ip
        self.remote_dir = f"/tmp/prodesp_cert_{int(time.time())}"
        self.remote_script = "/tmp/prodesp_tftp_recv.py"
        self.remote_log = "/tmp/prodesp_tftp.log"
        self.pid = ""
        self.local_staging = ""
        self._started = False

    def _exec(self, cmd: str, *, timeout: float = 30.0) -> tuple[int, str, str]:
        _stdin, stdout, stderr = self.jump.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return code, out, err

    def start(self) -> None:
        import tempfile

        port = tftp_port()
        code, out, err = self._exec(f"mkdir -p {self.remote_dir}")
        if code != 0:
            raise RuntimeError(f"Falha ao criar pasta TFTP no jump: {err or out}")

        sftp = self.jump.open_sftp()
        try:
            with sftp.file(self.remote_script, "w") as handle:
                handle.write(_JUMP_TFTP_RECEIVER_SCRIPT)
            sftp.chmod(self.remote_script, 0o755)
        finally:
            sftp.close()

        py = _env("PRODESP_JUMP_PYTHON", "python3")
        use_sudo = _env("PRODESP_JUMP_TFTP_SUDO", "1").lower() in ("1", "true", "yes")
        prefix = "sudo -n " if use_sudo else ""
        timeout = int(tftp_timeout_sec())
        cmd = (
            f"nohup {prefix}{py} {self.remote_script} --root {self.remote_dir} "
            f"--port {port} --timeout {timeout} > {self.remote_log} 2>&1 & echo $!"
        )
        code, out, err = self._exec(cmd)
        if code != 0:
            raise RuntimeError(f"Falha ao iniciar TFTP no jump: {err or out}")
        self.pid = (out or "").strip().split()[-1] if (out or "").strip() else ""
        self.local_staging = tempfile.mkdtemp(prefix="prodesp_cert_jump_")
        self._started = True
        time.sleep(0.6)
        _logger().info(
            "TFTP jump: FGT → %s:%s (dir=%s pid=%s sudo=%s)",
            self.server_ip,
            port,
            self.remote_dir,
            self.pid or "?",
            use_sudo,
        )

    def stop(self) -> None:
        if self.pid:
            self._exec(f"kill {self.pid} 2>/dev/null || true")
        self._exec(
            f"rm -rf {self.remote_dir} {self.remote_script} {self.remote_log} 2>/dev/null || true"
        )
        if self.local_staging and os.path.isdir(self.local_staging):
            import shutil

            shutil.rmtree(self.local_staging, ignore_errors=True)
        self._started = False

    def restart(self) -> None:
        self.stop()
        self.remote_dir = f"/tmp/prodesp_cert_{int(time.time())}"
        self.start()

    def wait_for_file(self, expected_name: str, timeout: float) -> TftpReceiveResult:
        if not self._started:
            return TftpReceiveResult(ok=False, error="Sessão TFTP jump inativa.")
        remote_path = f"{self.remote_dir}/{expected_name}"
        remote_ok = f"{self.remote_dir}/.tftp_ok"
        deadline = time.time() + timeout
        while time.time() < deadline:
            code, out, _err = self._exec(
                f"test -f {remote_path} && echo OK || test -f {remote_ok} && cat {remote_ok}",
                timeout=10.0,
            )
            if "OK" in out or (out.strip() and expected_name in out):
                local_path = os.path.join(self.local_staging, expected_name)
                sftp = self.jump.open_sftp()
                try:
                    sftp.get(remote_path, local_path)
                finally:
                    sftp.close()
                size = os.path.getsize(local_path) if os.path.isfile(local_path) else 0
                if size > 0:
                    _logger().info("TFTP jump: arquivo recebido %s (%d bytes)", expected_name, size)
                    return TftpReceiveResult(
                        ok=True,
                        filename=expected_name,
                        path=local_path,
                        bytes_received=size,
                    )
            time.sleep(0.75)
        _code, _out, err = self._exec(f"tail -n 20 {self.remote_log} 2>/dev/null || true", timeout=10.0)
        hint = (err or _out or "").strip()[:300]
        return TftpReceiveResult(
            ok=False,
            error=f"Timeout TFTP no jump aguardando «{expected_name}»." + (f" Log: {hint}" if hint else ""),
        )


def create_tftp_session(jump_ssh, *, jump_host: str, fgt_ip: str):
    """Factory: sessão TFTP local ou no jump conforme PRODESP_TFTP_MODE."""
    server_ip = resolve_tftp_server_ip(jump_host=jump_host, fgt_ip=fgt_ip)
    if tftp_mode() == "local":
        return LocalTftpSession(server_ip), server_ip
    if jump_ssh is None:
        raise RuntimeError("Modo TFTP jump requer conexão SSH ao jump server.")
    return JumpTftpSession(jump_ssh, server_ip=server_ip), server_ip
