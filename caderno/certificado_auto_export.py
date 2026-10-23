"""Exportação automática de certificado ao concluir atendimento (Concluído / Concluído)."""
from __future__ import annotations

import os
import threading
import unicodedata
from typing import Optional

_LOG = None


def _logger():
    global _LOG
    if _LOG is None:
        from core.logger import get_logger

        _LOG = get_logger("PRODESP")
    return _LOG


def _norm_status(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value or "").strip())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.casefold()


def certificado_auto_export_habilitado() -> bool:
    raw = (os.environ.get("PRODESP_CERTIFICADO_AUTO_EXPORT") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on", "sim")


def acronimos_auto_export_certificado() -> Optional[set[str]]:
    """
    None = todas as secretarias.
    set(...) = lista explícita (PRODESP_CERTIFICADO_AUTO_ACRONYMS).
    """
    raw = (os.environ.get("PRODESP_CERTIFICADO_AUTO_ACRONYMS") or "POUPATEMPO,DER").strip()
    if not raw or raw == "*":
        return None
    return {part.strip().upper() for part in raw.replace(";", ",").split(",") if part.strip()}


def is_atendimento_concluido_completo(status: object, substatus: object) -> bool:
    st = _norm_status(status)
    sub = _norm_status(substatus)
    return st in ("concluido",) and sub in ("concluido",)


def acronimo_elegivel_auto_export(acronimo: object) -> bool:
    if not certificado_auto_export_habilitado():
        return False
    allowed = acronimos_auto_export_certificado()
    if allowed is None:
        return True
    return (str(acronimo or "").strip().upper()) in allowed


def transicao_para_concluido_completo(
    old_status: object,
    old_substatus: object,
    new_status: object,
    new_substatus: object,
) -> bool:
    """True apenas na primeira vez que o par status/substatus vira Concluído/Concluído."""
    if not is_atendimento_concluido_completo(new_status, new_substatus):
        return False
    return not is_atendimento_concluido_completo(old_status, old_substatus)


def tentar_agendar_exportacao_certificado_automatica(
    id_atendimento: int,
    *,
    acronimo: object,
    old_status: object,
    old_substatus: object,
    new_status: object,
    new_substatus: object,
) -> bool:
    """
    Agenda exportação em background se elegível.
    Retorna True se a thread foi disparada.
    """
    if not transicao_para_concluido_completo(old_status, old_substatus, new_status, new_substatus):
        return False
    acr = (str(acronimo or "").strip().upper())
    if not acronimo_elegivel_auto_export(acr):
        _logger().info(
            "certificado auto-export ignorado atendimento=%s acronimo=%s (fora da lista ou desabilitado)",
            id_atendimento,
            acr or "(vazio)",
        )
        return False
    agendar_exportacao_certificado_automatica(id_atendimento, acronimo=acr)
    return True


def agendar_exportacao_certificado_automatica(id_atendimento: int, *, acronimo: str = "") -> None:
    """Dispara exportação em thread daemon — não bloqueia o save do atendimento."""

    def _run() -> None:
        conn = None
        cursor = None
        try:
            from prodesp.credentials.db_connection import get_prodesp_db_connection
            from prodesp.prodesp.caderno.certificado_export_service import exportar_certificados_atendimento

            conn = get_prodesp_db_connection()
            cursor = conn.cursor(dictionary=True)
            exportar_certificados_atendimento(
                cursor,
                conn,
                id_atendimento,
                automatico=True,
            )
        except Exception as exc:
            _logger().warning(
                "certificado auto-export atendimento=%s acronimo=%s falhou: %s",
                id_atendimento,
                acronimo or "?",
                exc,
            )
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    _logger().info(
        "certificado auto-export agendado atendimento=%s acronimo=%s",
        id_atendimento,
        acronimo or "?",
    )
    threading.Thread(
        target=_run,
        name=f"prodesp-cert-auto-{id_atendimento}",
        daemon=True,
    ).start()
