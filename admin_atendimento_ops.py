"""Operações administrativas — exclusão de atendimento e remoção de agendamento."""
from __future__ import annotations

from typing import Any, Optional

MSG_AGENDAMENTO_REMOVIDO = "Agendamento removido (admin)"
MSG_ATENDIMENTO_REMOVIDO = "Atendimento removido (admin)"


class AdminAtendimentoOpsError(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message = message
        self.status = status
        super().__init__(message)


def _format_agendamento_label(data_ag, hora_ag) -> str:
    parts: list[str] = []
    if data_ag:
        parts.append(str(data_ag)[:10])
    if hora_ag:
        parts.append(str(hora_ag)[:8])
    return " ".join(parts).strip() or "—"


def _format_atendimento_label(row: dict[str, Any]) -> str:
    """Resumo do atendimento para valor_antigo no histórico da unidade."""
    parts: list[str] = [str(row.get("id_atendimentos") or "")]
    data_att = row.get("data_atendimentos")
    if data_att:
        parts.append(str(data_att)[:10])
    status = (row.get("status_atendimentos") or "").strip()
    if status:
        parts.append(status)
    sub = (row.get("substatus_atendimentos") or "").strip()
    if sub:
        parts.append(sub)
    return " — ".join(p for p in parts if p)


def admin_excluir_atendimento(conn, cursor, id_atendimento: int) -> dict[str, Any]:
    """Remove atendimento e dependências; registra histórico na unidade."""
    from prodesp.prodesp.historico import registrar_log

    cursor.execute(
        """
        SELECT id_atendimentos, id_unidades_atendimentos, data_atendimentos,
               status_atendimentos, substatus_atendimentos
        FROM atendimentos
        WHERE id_atendimentos = %s
        """,
        (id_atendimento,),
    )
    row = cursor.fetchone()
    if not row:
        raise AdminAtendimentoOpsError("Atendimento não encontrado.", 404)

    id_unidade = int(row["id_unidades_atendimentos"])

    registrar_log(
        conn,
        "unidades",
        id_unidade,
        "Atendimento",
        _format_atendimento_label(row),
        MSG_ATENDIMENTO_REMOVIDO,
        "DELETE",
    )

    cur2 = conn.cursor()
    try:
        cur2.execute(
            "DELETE FROM atendimentos_status_log WHERE id_atendimentos_log = %s",
            (id_atendimento,),
        )
        cur2.execute(
            "DELETE FROM observacoes WHERE id_atendimentos_observacoes = %s",
            (id_atendimento,),
        )
        cur2.execute(
            "DELETE FROM atendimentos_fora_padrao WHERE id_atendimento = %s",
            (id_atendimento,),
        )
        cur2.execute(
            """
            DELETE FROM historico
            WHERE tabela_afetada_historico = 'atendimentos'
              AND id_registro_afetado_historico = %s
            """,
            (id_atendimento,),
        )
        cur2.execute(
            "DELETE FROM atendimentos WHERE id_atendimentos = %s",
            (id_atendimento,),
        )
    finally:
        cur2.close()

    return {"id_atendimento": id_atendimento, "id_unidade": id_unidade}


def _unidade_por_id_ou_vgr(
    cursor,
    *,
    id_unidade: Optional[int] = None,
    id_vgr: Optional[str] = None,
) -> dict[str, Any]:
    if id_unidade:
        cursor.execute(
            """
            SELECT id_unidades, id_vgr_unidades,
                   data_agendamento_unidades, hora_agendamento_unidades
            FROM unidades
            WHERE id_unidades = %s
            """,
            (id_unidade,),
        )
    elif id_vgr:
        vgr = str(id_vgr).strip()
        if not vgr:
            raise AdminAtendimentoOpsError("ID VGR inválido.", 400)
        cursor.execute(
            """
            SELECT id_unidades, id_vgr_unidades,
                   data_agendamento_unidades, hora_agendamento_unidades
            FROM unidades
            WHERE id_vgr_unidades = %s
            """,
            (vgr,),
        )
    else:
        raise AdminAtendimentoOpsError("Identificador da unidade ausente.", 400)

    row = cursor.fetchone()
    if not row:
        raise AdminAtendimentoOpsError("Unidade não encontrada.", 404)
    return row


def admin_remover_agendamento(
    conn,
    cursor,
    *,
    id_unidade: Optional[int] = None,
    id_vgr: Optional[str] = None,
) -> dict[str, Any]:
    """Limpa data/hora de agendamento da unidade e registra histórico."""
    from prodesp.prodesp.historico import registrar_log

    row = _unidade_por_id_ou_vgr(cursor, id_unidade=id_unidade, id_vgr=id_vgr)
    uid = int(row["id_unidades"])
    old_data = row.get("data_agendamento_unidades")
    old_hora = row.get("hora_agendamento_unidades")

    if not old_data and not old_hora:
        raise AdminAtendimentoOpsError("Unidade não possui agendamento para remover.", 400)

    if old_data:
        cursor.execute(
            """
            SELECT id_atendimentos
            FROM atendimentos
            WHERE id_unidades_atendimentos = %s AND data_atendimentos = %s
            LIMIT 1
            """,
            (uid, old_data),
        )
        if cursor.fetchone():
            raise AdminAtendimentoOpsError(
                "Existe atendimento vinculado a esta agenda. "
                "Exclua o atendimento antes de remover o agendamento.",
                409,
            )

    label = _format_agendamento_label(old_data, old_hora)
    registrar_log(
        conn,
        "unidades",
        uid,
        "Agendamento",
        label,
        MSG_AGENDAMENTO_REMOVIDO,
        "DELETE",
    )
    if old_data is not None:
        registrar_log(
            conn,
            "unidades",
            uid,
            "data_agendamento_unidades",
            str(old_data)[:10],
            None,
            "DELETE",
        )
    if old_hora is not None:
        registrar_log(
            conn,
            "unidades",
            uid,
            "hora_agendamento_unidades",
            str(old_hora)[:8],
            None,
            "DELETE",
        )

    cur2 = conn.cursor()
    try:
        cur2.execute(
            """
            UPDATE unidades
            SET data_agendamento_unidades = NULL,
                hora_agendamento_unidades = NULL
            WHERE id_unidades = %s
            """,
            (uid,),
        )
    finally:
        cur2.close()

    return {"id_unidade": uid, "id_vgr": row.get("id_vgr_unidades")}
