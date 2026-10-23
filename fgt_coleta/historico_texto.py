"""Texto de auditoria da coleta FGT (histórico do portal)."""

from __future__ import annotations

from typing import Optional, Sequence

_HISTORICO_COLETA_TEXTO_MAX = 8000


def truncar_texto_historico_coleta(texto: str, *, max_len: int = _HISTORICO_COLETA_TEXTO_MAX) -> str:
    t = (texto or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 16].rstrip() + "\n… [truncado]"


def _sanitizar_motivo(motivo: str, *, max_len: int = 800) -> str:
    t = " ".join((motivo or "").split())
    return t[:max_len]


def historico_coleta_sucesso(
    *,
    hostname: str = "",
    identificador: str = "",
    elapsed_seconds: float = 0,
    commands_run: int = 0,
    log_chars: int = 0,
    parcial: bool = False,
    resumo_limpeza_admin: str = "",
    avisos: Optional[Sequence[str]] = None,
) -> str:
    titulo = (
        "Coleta de logs FGT concluída com ressalvas."
        if parcial
        else "Coleta de logs FGT concluída com sucesso."
    )
    lines = [titulo]
    if elapsed_seconds:
        lines.append(f"Tempo: {elapsed_seconds}s")
    if hostname:
        lines.append(f"Hostname: {hostname}")
    if identificador:
        lines.append(f"Unidade: {identificador}")
    if commands_run:
        lines.append(f"Comandos executados: {commands_run}")
    if log_chars:
        lines.append(f"Tamanho do log gravado: {log_chars} caracteres")
    if (resumo_limpeza_admin or "").strip():
        lines.extend(["", resumo_limpeza_admin.strip()])
    if avisos:
        aviso_txt = "; ".join(str(a).strip() for a in avisos if a and str(a).strip())
        if aviso_txt:
            lines.extend(["", f"Avisos: {_sanitizar_motivo(aviso_txt, max_len=1200)}"])
    return truncar_texto_historico_coleta("\n".join(lines).strip())


def historico_coleta_falha(
    *,
    hostname: str = "",
    identificador: str = "",
    motivo: str = "",
    resumo_limpeza_admin: str = "",
) -> str:
    lines = ["Falha na coleta de logs FGT."]
    if hostname:
        lines.append(f"Hostname: {hostname}")
    if identificador:
        lines.append(f"Unidade: {identificador}")
    lines.extend(["", f"Motivo: {_sanitizar_motivo(motivo)}"])
    if (resumo_limpeza_admin or "").strip():
        lines.extend(["", resumo_limpeza_admin.strip()])
    return truncar_texto_historico_coleta("\n".join(lines).strip())
