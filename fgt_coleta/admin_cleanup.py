"""
Limpeza do usuário local «admin» no FortiGate ao final da coleta SSH.

Cópia reutilizável (core). O caderno PRODESP mantém o mesmo fluxo no próprio pacote.

Fluxo condicional:
1. show sys admin ?  — lista usuários (ajuda CLI); se inconclusivo, show sys admin (config)
2. get system info admin status — verifica se admin está logado
3. execute disconnect-admin-session ? — única forma de listar INDEX (sem « ?» não lista)
4. execute disconnect-admin-session <INDEX> — desconecta cada sessão pelo número
5. config sys admin / delete admin / end — remove o usuário
"""
from __future__ import annotations

import re
from typing import Callable, Optional, Protocol

_CMD_SHOW_ADMIN = "show sys admin"
_CMD_SHOW_ADMIN_HELP = "show sys admin ?"  # label de log; envio real via format_fgt_cli_help_command
_CMD_ADMIN_STATUS = "get system info admin status"
_CMD_DISCONNECT_HELP = "execute disconnect-admin-session ?"  # só ajuda « ?» lista INDEX
_CMD_DISCONNECT = "execute disconnect-admin-session"
_CMD_DELETE_BLOCK = "config sys admin / delete admin / end"

_DELETE_LOGGED_IN_RE = re.compile(
    r"cannot delete admin while\s+'admin'\s+is logged in",
    re.IGNORECASE,
)
_DISCONNECT_INDEX_RE = re.compile(r"^\s*(\d+)\s+admin(?:\s+|$)", re.IGNORECASE)
_USERNAME_LINE_RE = re.compile(r"^[\w.-]+$")
_EDIT_USER_RE = re.compile(r'^\s*edit\s+"([^"]+)"\s*$', re.IGNORECASE)
# Tokens de sintaxe FortiOS — não são nomes de usuário (ex.: bloco config sys admin).
_FORTIOS_CLI_TOKENS_IGNORAR = frozenset(
    {
        "end",
        "next",
        "set",
        "unset",
        "config",
        "edit",
        "append",
        "delete",
        "show",
        "get",
        "execute",
        "diagnose",
    }
)


class _ShellLike(Protocol):
    def send(self, data: str) -> None: ...


def parse_usuarios_show_sys_admin(text: str) -> set[str]:
    """Extrai nomes da ajuda «show sys admin ?» ou do bloco «edit "…"» em show sys admin."""
    users: set[str] = set()
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.endswith("#"):
            continue
        low = s.lower()
        if "user name" in low or low.startswith("config system admin"):
            continue
        edit_m = _EDIT_USER_RE.match(s)
        if edit_m:
            users.add(edit_m.group(1))
            continue
        if _USERNAME_LINE_RE.fullmatch(s):
            if low in _FORTIOS_CLI_TOKENS_IGNORAR:
                continue
            users.add(s)
    return users


def admin_existe_na_caixa(text: str) -> bool:
    """True se o usuário local exato «admin» existe (não confunde com tacacs-admin etc.)."""
    return "admin" in parse_usuarios_show_sys_admin(text)


def admin_esta_logado(text: str) -> bool:
    """True se «admin» aparece na lista de usuários logados."""
    in_users = False
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("logged in users"):
            in_users = True
            continue
        if low.startswith("username") and "type" in low:
            in_users = True
            continue
        if not in_users:
            continue
        parts = s.split()
        if parts and parts[0].lower() == "admin":
            return True
    return False


def parse_indexes_admin_disconnect(text: str) -> list[int]:
    """INDEX de todas as sessões do usuário admin em «execute disconnect-admin-session ?»."""
    indexes: list[int] = []
    for line in (text or "").splitlines():
        m = _DISCONNECT_INDEX_RE.match(line)
        if m:
            indexes.append(int(m.group(1)))
    return indexes


def delete_admin_falhou_por_logado(text: str) -> bool:
    return bool(_DELETE_LOGGED_IN_RE.search(text or ""))


def resumir_lista_usuarios(text: str) -> str:
    users = sorted(parse_usuarios_show_sys_admin(text))
    return ", ".join(users) if users else "(nenhum)"


def formatar_saida_cli(
    out: Optional[str],
    *,
    vazio_ok: bool = False,
    nota_se_vazio: str = "",
) -> str:
    text = (out or "").strip()
    if text:
        return text
    if vazio_ok and nota_se_vazio:
        return nota_se_vazio
    return "(sem saída)"


def interpretar_saida_delete_admin(delete_out: str) -> tuple[bool, str]:
    """FortiOS costuma não ecoar texto após «delete admin» — saída vazia pode ser sucesso."""
    raw = (delete_out or "").strip()
    if delete_admin_falhou_por_logado(raw):
        return False, raw
    if raw and "command fail" in raw.lower():
        if "cannot delete" in raw.lower():
            return False, raw
        return False, raw
    if not raw:
        return True, (
            "OK — bloco config/delete/end concluído sem erro.\n"
            "Nota: FortiOS normalmente não ecoa confirmação após «delete admin»."
        )
    return True, raw


def montar_resumo_limpeza_admin(
    *,
    texto_detecao: str,
    via_config: bool,
    admin_logado: bool,
    indexes_desconectados: list[int],
    delete_ok: bool,
    delete_msg: str,
    texto_verificacao: str,
) -> str:
    linhas = [
        "=== Limpeza usuário local «admin» ===",
        (
            "Detecção: usuário «admin» encontrado"
            + (" (via show sys admin — config)" if via_config else " (via show sys admin ?)")
            + f".\nUsuários listados: {resumir_lista_usuarios(texto_detecao)}."
        ),
    ]
    if admin_logado:
        if indexes_desconectados:
            idx_txt = ", ".join(str(i) for i in indexes_desconectados)
            linhas.append(f"Sessão: admin estava logado — desconectado INDEX {idx_txt}.")
        else:
            linhas.append(
                "Sessão: admin constava como logado, mas nenhum INDEX foi listado em "
                "«execute disconnect-admin-session ?»."
            )
    else:
        linhas.append("Sessão: admin não estava logado no momento da verificação.")

    if delete_ok:
        linhas.append(f"Remoção: {delete_msg.splitlines()[0]}")
    else:
        linhas.append(f"Remoção: FALHA — {delete_msg.splitlines()[0][:200]}")

    if admin_existe_na_caixa(texto_verificacao):
        linhas.append(
            "Verificação pós-delete: FALHA — usuário «admin» ainda aparece na listagem.\n"
            f"Usuários atuais: {resumir_lista_usuarios(texto_verificacao)}."
        )
    else:
        linhas.append(
            "Verificação pós-delete: OK — usuário «admin» não consta mais.\n"
            f"Usuários restantes: {resumir_lista_usuarios(texto_verificacao)}."
        )
    return "\n".join(linhas)


LIMPEZA_ADMIN_RESUMO_MARKER = "--- limpeza admin — resumo ---"
LIMPEZA_ADMIN_ERRO_MARKER = "--- limpeza admin ---"


def _extrair_bloco_marcador_coleta(text: str, marker: str) -> str:
    """Recorta um bloco «--- … ---» até o próximo marcador «--- » ou fim."""
    after = text.split(marker, 1)[1]
    body_lines: list[str] = []
    for line in after.splitlines():
        if line.strip().startswith("--- ") and body_lines:
            break
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    if not body:
        return marker.strip()
    return f"{marker.strip()}\n{body}".strip()


def extrair_resumo_limpeza_admin_coleta(text: str) -> str:
    """
    Extrai o resumo da limpeza do usuário «admin» da saída bruta da coleta FGT.

    Usado no historico do portal: cada nova coleta substitui o bloco automático em
    logs_atendimentos, mas o resumo precisa ficar registrado por execução.
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    if LIMPEZA_ADMIN_RESUMO_MARKER in raw:
        return _extrair_bloco_marcador_coleta(raw, LIMPEZA_ADMIN_RESUMO_MARKER)
    if LIMPEZA_ADMIN_ERRO_MARKER in raw:
        block = _extrair_bloco_marcador_coleta(raw, LIMPEZA_ADMIN_ERRO_MARKER)
        if "ERRO:" in block.upper():
            return block
    return ""


def executar_limpeza_admin_fgt(
    shell: _ShellLike,
    *,
    exec_help: Callable[[str, str], str],
    exec_cmd: Callable[[str], str],
    exec_config_delete: Callable[[], str],
    progress_cb: Optional[Callable[[str], None]] = None,
) -> tuple[list[str], list[str], int]:
    """
    Executa fluxo de remoção do admin. Retorna (blocos_log, erros, comandos_executados).
    Callbacks injetados para testes sem SSH.
    """
    blocks: list[str] = []
    errors: list[str] = []
    cmds_run = 0
    indexes_desconectados: list[int] = []
    texto_detecao = ""
    via_config = False
    admin_logado = False
    delete_ok = False
    delete_msg = ""

    def _run_help(label: str, partial: str) -> str:
        nonlocal cmds_run
        if progress_cb:
            progress_cb(label)
        out = exec_help(partial, label)
        body = formatar_saida_cli(out)
        if partial == _CMD_SHOW_ADMIN and admin_existe_na_caixa(out):
            body += f"\n\n→ Usuário «admin» detectado. Demais: {resumir_lista_usuarios(out)}."
        blocks.append(f"--- {label} ---\n{body}")
        cmds_run += 1
        return out

    def _run_cmd(cmd: str) -> str:
        nonlocal cmds_run
        if progress_cb:
            progress_cb(cmd)
        out = exec_cmd(cmd)
        blocks.append(f"--- {cmd} ---\n{formatar_saida_cli(out)}")
        cmds_run += 1
        return out

    def _disconnect_all_admin_sessions() -> None:
        nonlocal indexes_desconectados
        # FortiOS: sem « ?» não há listagem de INDEX — apenas ajuda CLI.
        help_out = _run_help(_CMD_DISCONNECT_HELP, _CMD_DISCONNECT)
        indexes = parse_indexes_admin_disconnect(help_out)
        if not indexes:
            blocks.append(
                "--- execute disconnect-admin-session ---\n"
                "Nenhum INDEX do usuário «admin» listado (nenhuma sessão ativa para desconectar)."
            )
            return
        for idx in indexes:
            indexes_desconectados.append(idx)
            _run_cmd(f"{_CMD_DISCONNECT} {idx}")

    # 1) Usuário admin existe? (ajuda «?»; fallback para config completa)
    show_out = _run_help(_CMD_SHOW_ADMIN_HELP, _CMD_SHOW_ADMIN)
    admin_exists = admin_existe_na_caixa(show_out)
    texto_detecao = show_out
    if not admin_exists:
        show_full = _run_cmd(_CMD_SHOW_ADMIN)
        admin_exists = admin_existe_na_caixa(show_full)
        if admin_exists:
            texto_detecao = show_full
            via_config = True
    if not admin_exists:
        blocks.append(
            f"{LIMPEZA_ADMIN_RESUMO_MARKER}\n"
            "Usuário «admin» não cadastrado; etapa de limpeza ignorada."
        )
        return blocks, errors, cmds_run

    # 2) Admin logado?
    status_out = _run_cmd(_CMD_ADMIN_STATUS)
    admin_logado = admin_esta_logado(status_out)
    if admin_logado:
        _disconnect_all_admin_sessions()

    # 3) Delete (com retry se ainda logado)
    max_tentativas = 3
    for tentativa in range(1, max_tentativas + 1):
        if progress_cb:
            progress_cb(_CMD_DELETE_BLOCK)
        delete_out = exec_config_delete()
        delete_ok, delete_msg = interpretar_saida_delete_admin(delete_out)
        blocks.append(f"--- {_CMD_DELETE_BLOCK} ---\n{delete_msg}")
        cmds_run += 1

        if delete_ok and not delete_admin_falhou_por_logado(delete_out or ""):
            break

        if delete_out and delete_admin_falhou_por_logado(delete_out):
            if tentativa >= max_tentativas:
                delete_ok = False
                delete_msg = (
                    "FALHA — não foi possível remover: sessão admin ainda ativa após desconexões."
                )
                errors.append(delete_msg)
                break
            _disconnect_all_admin_sessions()
            continue

        if not delete_ok:
            errors.append(f"Falha ao remover usuário admin: {delete_msg.strip()[:200]}")
            break

    # 4) Verificação pós-delete (show sys admin ?)
    verify_out = _run_help(_CMD_SHOW_ADMIN_HELP, _CMD_SHOW_ADMIN)
    if admin_existe_na_caixa(verify_out):
        errors.append("Usuário «admin» ainda listado após tentativa de remoção.")

    blocks.append(
        f"{LIMPEZA_ADMIN_RESUMO_MARKER}\n"
        + montar_resumo_limpeza_admin(
            texto_detecao=texto_detecao,
            via_config=via_config,
            admin_logado=admin_logado,
            indexes_desconectados=indexes_desconectados,
            delete_ok=delete_ok,
            delete_msg=delete_msg,
            texto_verificacao=verify_out,
        )
    )

    return blocks, errors, cmds_run
