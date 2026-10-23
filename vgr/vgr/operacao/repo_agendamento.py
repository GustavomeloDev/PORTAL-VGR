"""CRUD agendamentos VGR (P3/P4/P11/P12) + associação Field com snapshot."""

from __future__ import annotations

import logging
from typing import Any

from core.security.encryption import encrypt_text
from vgr.credentials.db_connection import get_vgr_db_connection
from vgr.vgr.cadastros import repo_field as repo_f
from vgr.vgr.cadastros import repo_inventario as repo_inv
from vgr.vgr.operacao import repo_atendimento as repo_at
from vgr.vgr.operacao.catalogo_agendamento import (
    CHECKLIST_FIELDS,
    STATUS_AGENDADO,
    STATUS_DEFAULT,
    STATUS_IMPRODUTIVA,
)
from vgr.vgr.operacao.catalogo_atendimento import STATUS_OPERACIONAL

log = logging.getLogger("VGR.repo_agendamento")


def _rows(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        return list(cur.fetchall() or [])
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _one(sql: str, params: tuple | list | None = None) -> dict[str, Any] | None:
    rows = _rows(sql, params)
    return rows[0] if rows else None


def _exec(sql: str, params: tuple | list | None = None) -> tuple[int | None, int]:
    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        last_id = cur.lastrowid
        return (int(last_id) if last_id else None, int(cur.rowcount or 0))
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def list_agendamentos(*, apenas_ativos: bool = False) -> list[dict[str, Any]]:
    where = "WHERE a.ativo = 1" if apenas_ativos else ""
    return _rows(
        f"""
        SELECT
          a.id_agendamento, a.id_unidade, u.nome_unidade, u.id_cliente, u.ha,
          c.razao_social, a.status_agendamento, a.substatus_agendamento,
          a.data_agendamento, a.hora_agendamento, a.hora_inicio, a.hora_fim,
          a.tipo, a.analista_destino, a.analista_livre, a.ativo,
          a.criado_em, a.atualizado_em,
          (SELECT COUNT(*) FROM agendamento_fields af WHERE af.id_agendamento = a.id_agendamento)
            AS fields_count,
          (SELECT t.id_atendimento FROM atendimentos t
             WHERE t.id_agendamento = a.id_agendamento LIMIT 1) AS id_atendimento
        FROM agendamentos a
        INNER JOIN unidades u ON u.id_unidade = a.id_unidade
        INNER JOIN clientes c ON c.id_cliente = u.id_cliente
        {where}
        ORDER BY a.id_agendamento DESC
        """
    )


def get_agendamento(id_agendamento: int) -> dict[str, Any] | None:
    row = _one(
        """
        SELECT
          a.*, u.nome_unidade, u.id_cliente, u.ha, c.razao_social,
          (SELECT t.id_atendimento FROM atendimentos t
             WHERE t.id_agendamento = a.id_agendamento LIMIT 1) AS id_atendimento
        FROM agendamentos a
        INNER JOIN unidades u ON u.id_unidade = a.id_unidade
        INNER JOIN clientes c ON c.id_cliente = u.id_cliente
        WHERE a.id_agendamento = %s
        """,
        (id_agendamento,),
    )
    if not row:
        return None
    row["fields"] = list_fields_do_agendamento(id_agendamento)
    row["id_fields"] = [int(f["id_field"]) for f in row["fields"]]
    return row


def list_fields_do_agendamento(id_agendamento: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id_agendamento_field, id_field, ordem, snap_nome, snap_telefone,
               snap_emails, snap_contratada_nome, id_contratada,
               (snap_rg_enc IS NOT NULL AND snap_rg_enc <> '') AS has_rg,
               (snap_cpf_enc IS NOT NULL AND snap_cpf_enc <> '') AS has_cpf
        FROM agendamento_fields
        WHERE id_agendamento = %s
        ORDER BY ordem, id_agendamento_field
        """,
        (id_agendamento,),
    )


def _append_status_log(
    cur,
    id_agendamento: int,
    *,
    status_ant: str | None,
    status_novo: str,
    sub_ant: str | None,
    sub_novo: str | None,
    usuario_re: str | None,
    usuario_nome: str | None,
    observacao: str | None = None,
) -> None:
    if status_ant == status_novo and (sub_ant or None) == (sub_novo or None):
        return
    cur.execute(
        """
        INSERT INTO agendamento_status_log (
          id_agendamento, status_anterior, status_novo,
          substatus_anterior, substatus_novo,
          usuario_re, usuario_nome, observacao
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id_agendamento,
            status_ant,
            status_novo,
            sub_ant,
            sub_novo,
            usuario_re,
            usuario_nome,
            observacao,
        ),
    )


def _replace_fields(cur, id_agendamento: int, id_fields: list[int]) -> None:
    cur.execute(
        "DELETE FROM agendamento_fields WHERE id_agendamento = %s", (id_agendamento,)
    )
    for ordem, fid in enumerate(id_fields, start=1):
        field = repo_f.get_field(int(fid), decrypt_pii=True)
        if not field or not int(field.get("ativo") or 0):
            raise ValueError(f"Field #{fid} inválido ou inativo.")
        emails = field.get("emails") or []
        contratadas = field.get("contratadas") or []
        contratada_nome = contratadas[0]["nome_contratada"] if contratadas else None
        id_contratada = (
            int(contratadas[0]["id_contratada"]) if contratadas else None
        )
        cur.execute(
            """
            INSERT INTO agendamento_fields (
              id_agendamento, id_field, ordem, snap_nome, snap_telefone,
              snap_rg_enc, snap_cpf_enc, snap_emails, snap_contratada_nome, id_contratada
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                id_agendamento,
                fid,
                ordem,
                field.get("nome"),
                field.get("telefone"),
                encrypt_text(field.get("rg")) if field.get("rg") else None,
                encrypt_text(field.get("cpf")) if field.get("cpf") else None,
                ",".join(emails)[:500] if emails else None,
                contratada_nome,
                id_contratada,
            ),
        )


def _checklist_values(data: dict[str, Any]) -> tuple:
    return tuple(int(data.get(q) or 0) for q in CHECKLIST_FIELDS)


def create_agendamento(
    data: dict[str, Any],
    *,
    usuario_re: str | None = None,
    usuario_nome: str | None = None,
) -> int:
    status = data.get("status_agendamento") or STATUS_DEFAULT
    if status == STATUS_AGENDADO:
        raise ValueError(
            "Use a ação Confirmar Agendado para publicar o atendimento (P4)."
        )

    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor()
        cols_q = ", ".join(CHECKLIST_FIELDS)
        placeholders_q = ", ".join(["%s"] * len(CHECKLIST_FIELDS))
        cur.execute(
            f"""
            INSERT INTO agendamentos (
              id_unidade, status_agendamento, substatus_agendamento,
              data_agendamento, hora_agendamento, hora_inicio, hora_fim,
              tipo, analista_destino, analista_livre, observacoes,
              {cols_q}, ativo, criado_por_re, atualizado_por_re
            ) VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              {placeholders_q}, %s, %s, %s
            )
            """,
            (
                data["id_unidade"],
                status,
                data.get("substatus_agendamento"),
                data.get("data_agendamento"),
                data.get("hora_agendamento"),
                data.get("hora_inicio"),
                data.get("hora_fim"),
                data.get("tipo"),
                data.get("analista_destino"),
                int(data.get("analista_livre") or 0),
                data.get("observacoes"),
                *_checklist_values(data),
                int(data.get("ativo", 1)),
                usuario_re,
                usuario_re,
            ),
        )
        new_id = int(cur.lastrowid)
        if data.get("_set_fields"):
            _replace_fields(cur, new_id, data.get("id_fields") or [])
        _append_status_log(
            cur,
            new_id,
            status_ant=None,
            status_novo=status,
            sub_ant=None,
            sub_novo=data.get("substatus_agendamento"),
            usuario_re=usuario_re,
            usuario_nome=usuario_nome,
            observacao="create",
        )
        conn.commit()
        return new_id
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def update_agendamento(
    id_agendamento: int,
    data: dict[str, Any],
    *,
    usuario_re: str | None = None,
    usuario_nome: str | None = None,
    allow_status_agendado: bool = False,
) -> bool:
    existing = get_agendamento(id_agendamento)
    if not existing:
        return False

    status = data.get("status_agendamento", existing["status_agendamento"])
    # Transição para Agendado só via confirmar_agendado
    if (
        status == STATUS_AGENDADO
        and existing["status_agendamento"] != STATUS_AGENDADO
        and not allow_status_agendado
    ):
        raise ValueError(
            "Use a ação Confirmar Agendado para publicar o atendimento (P4)."
        )

    merged = dict(existing)
    merged.update(data)
    for q in CHECKLIST_FIELDS:
        if q not in data:
            merged[q] = int(existing.get(q) or 0)

    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor()
        set_q = ", ".join(f"{q} = %s" for q in CHECKLIST_FIELDS)
        cur.execute(
            f"""
            UPDATE agendamentos SET
              id_unidade = %s,
              status_agendamento = %s,
              substatus_agendamento = %s,
              data_agendamento = %s,
              hora_agendamento = %s,
              hora_inicio = %s,
              hora_fim = %s,
              tipo = %s,
              analista_destino = %s,
              analista_livre = %s,
              observacoes = %s,
              {set_q},
              atualizado_por_re = %s
            WHERE id_agendamento = %s
            """,
            (
                merged["id_unidade"],
                status,
                merged.get("substatus_agendamento"),
                merged.get("data_agendamento"),
                merged.get("hora_agendamento"),
                merged.get("hora_inicio"),
                merged.get("hora_fim"),
                merged.get("tipo"),
                merged.get("analista_destino"),
                int(merged.get("analista_livre") or 0),
                merged.get("observacoes"),
                *_checklist_values(merged),
                usuario_re,
                id_agendamento,
            ),
        )
        if data.get("_set_fields"):
            _replace_fields(cur, id_agendamento, data.get("id_fields") or [])
        _append_status_log(
            cur,
            id_agendamento,
            status_ant=existing.get("status_agendamento"),
            status_novo=status,
            sub_ant=existing.get("substatus_agendamento"),
            sub_novo=merged.get("substatus_agendamento"),
            usuario_re=usuario_re,
            usuario_nome=usuario_nome,
        )
        conn.commit()
        return True
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def set_agendamento_ativo(id_agendamento: int, ativo: int) -> bool:
    _, n = _exec(
        "UPDATE agendamentos SET ativo = %s WHERE id_agendamento = %s",
        (1 if int(ativo) else 0, id_agendamento),
    )
    return n > 0


def assert_ha_ok(id_unidade: int) -> None:
    """P12: unidades.ha=1 exige 2× SDWAN ativos."""
    uni = repo_inv.get_unidade(id_unidade)
    if not uni:
        raise ValueError("Unidade não encontrada.")
    if not int(uni.get("ha") or 0):
        return
    n = repo_inv.count_equipamentos_sdwan(id_unidade)
    if n < 2:
        raise ValueError(
            f"HA exige 2 equipamentos SDWAN ativos na unidade (encontrados: {n})."
        )


def confirmar_agendado(
    id_agendamento: int,
    *,
    confirmar: bool,
    usuario_re: str | None = None,
    usuario_nome: str | None = None,
) -> dict[str, Any]:
    """P4: confirmação UI → status Agendado + cria atendimento 1→1."""
    if not confirmar:
        raise ValueError("Confirmação obrigatória para publicar Agendado.")
    existing = get_agendamento(id_agendamento)
    if not existing:
        raise ValueError("Agendamento não encontrado.")
    if not int(existing.get("ativo") or 0):
        raise ValueError("Agendamento inativo.")
    assert_ha_ok(int(existing["id_unidade"]))

    id_at = existing.get("id_atendimento")
    created_atendimento = False
    if not id_at:
        at_data = {
            "id_unidade": int(existing["id_unidade"]),
            "id_agendamento": id_agendamento,
            "status_atendimento": STATUS_OPERACIONAL,
            "substatus_atendimento": "Aguarda Gestão",
            "analista_atuante": existing.get("analista_destino"),
            "ativo": 1,
        }
        id_at = repo_at.create_atendimento(
            at_data, usuario_re=usuario_re, usuario_nome=usuario_nome
        )
        created_atendimento = True

    if existing["status_agendamento"] != STATUS_AGENDADO:
        update_agendamento(
            id_agendamento,
            {
                "id_unidade": existing["id_unidade"],
                "status_agendamento": STATUS_AGENDADO,
                "substatus_agendamento": existing.get("substatus_agendamento"),
                "data_agendamento": existing.get("data_agendamento"),
                "hora_agendamento": existing.get("hora_agendamento"),
                "hora_inicio": existing.get("hora_inicio"),
                "hora_fim": existing.get("hora_fim"),
                "tipo": existing.get("tipo"),
                "analista_destino": existing.get("analista_destino"),
                "analista_livre": existing.get("analista_livre"),
                "observacoes": existing.get("observacoes"),
                **{q: existing.get(q) for q in CHECKLIST_FIELDS},
            },
            usuario_re=usuario_re,
            usuario_nome=usuario_nome,
            allow_status_agendado=True,
        )

    row = get_agendamento(id_agendamento)
    return {
        "agendamento": row,
        "id_atendimento": id_at,
        "created_atendimento": created_atendimento,
    }


def marcar_improdutivo(
    id_agendamento: int,
    *,
    usuario_re: str | None = None,
    usuario_nome: str | None = None,
    observacao: str | None = None,
) -> dict[str, Any]:
    """P3: quebra → Improdutiva; nova agenda é novo registro (CRUD separado)."""
    existing = get_agendamento(id_agendamento)
    if not existing:
        raise ValueError("Agendamento não encontrado.")
    update_agendamento(
        id_agendamento,
        {
            "id_unidade": existing["id_unidade"],
            "status_agendamento": STATUS_IMPRODUTIVA,
            "substatus_agendamento": existing.get("substatus_agendamento"),
            "data_agendamento": existing.get("data_agendamento"),
            "hora_agendamento": existing.get("hora_agendamento"),
            "hora_inicio": existing.get("hora_inicio"),
            "hora_fim": existing.get("hora_fim"),
            "tipo": existing.get("tipo"),
            "analista_destino": existing.get("analista_destino"),
            "analista_livre": existing.get("analista_livre"),
            "observacoes": observacao or existing.get("observacoes"),
            **{q: existing.get(q) for q in CHECKLIST_FIELDS},
        },
        usuario_re=usuario_re,
        usuario_nome=usuario_nome,
    )
    return {
        "agendamento": get_agendamento(id_agendamento),
        "message": "Agendamento marcado como Improdutiva. Crie um novo registro para reagendar (P3).",
    }


def aplicar_status_sugerido(
    id_agendamento: int,
    status_novo: str,
    *,
    usuario_re: str | None = None,
    usuario_nome: str | None = None,
) -> dict[str, Any]:
    """P11-B: AGENDAMENTO confirma sugestão vinda de final de atendimento."""
    from vgr.vgr.operacao.catalogo_agendamento import STATUS_AGENDAMENTO_SET

    if status_novo not in STATUS_AGENDAMENTO_SET:
        raise ValueError("Status sugerido inválido.")
    if status_novo == STATUS_AGENDADO:
        raise ValueError("Sugestão Agendado deve usar Confirmar Agendado.")
    existing = get_agendamento(id_agendamento)
    if not existing:
        raise ValueError("Agendamento não encontrado.")
    update_agendamento(
        id_agendamento,
        {
            "id_unidade": existing["id_unidade"],
            "status_agendamento": status_novo,
            "substatus_agendamento": existing.get("substatus_agendamento"),
            "data_agendamento": existing.get("data_agendamento"),
            "hora_agendamento": existing.get("hora_agendamento"),
            "hora_inicio": existing.get("hora_inicio"),
            "hora_fim": existing.get("hora_fim"),
            "tipo": existing.get("tipo"),
            "analista_destino": existing.get("analista_destino"),
            "analista_livre": existing.get("analista_livre"),
            "observacoes": existing.get("observacoes"),
            **{q: existing.get(q) for q in CHECKLIST_FIELDS},
        },
        usuario_re=usuario_re,
        usuario_nome=usuario_nome,
    )
    return {"agendamento": get_agendamento(id_agendamento)}
