"""CRUD Field / contratadas (P10) — PII criptografado na aplicação."""
from __future__ import annotations

import logging
from typing import Any

from core.security.encryption import decrypt_text, encrypt_text
from vgr.credentials.db_connection import get_vgr_db_connection
from vgr.vgr.cadastros.validators import mask_pii_for_historico

log = logging.getLogger("VGR.repo_field")


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


def list_contratadas(*, apenas_ativos: bool = True) -> list[dict[str, Any]]:
    where = "WHERE ativo = 1" if apenas_ativos else ""
    return _rows(
        f"""
        SELECT id_contratada, nome_contratada, cnpj, ativo
        FROM contratadas
        {where}
        ORDER BY nome_contratada
        """
    )


def get_contratada(id_contratada: int) -> dict[str, Any] | None:
    return _one(
        """
        SELECT id_contratada, nome_contratada, cnpj, ativo, criado_em, atualizado_em
        FROM contratadas
        WHERE id_contratada = %s
        """,
        (id_contratada,),
    )


def create_contratada(data: dict[str, Any]) -> int:
    last_id, _ = _exec(
        """
        INSERT INTO contratadas (nome_contratada, cnpj, ativo)
        VALUES (%s, %s, %s)
        """,
        (
            data["nome_contratada"],
            data.get("cnpj"),
            int(data.get("ativo", 1)),
        ),
    )
    if not last_id:
        raise RuntimeError("insert_contratada_sem_id")
    return last_id


def list_fields() -> list[dict[str, Any]]:
    """Lista sem PII (rg/cpf/emails em claro)."""
    return _rows(
        """
        SELECT
          f.id_field,
          f.nome,
          f.telefone,
          f.ativo,
          f.criado_em,
          f.atualizado_em,
          (SELECT COUNT(*) FROM field_emails e WHERE e.id_field = f.id_field) AS emails_count,
          (
            SELECT GROUP_CONCAT(c.nome_contratada ORDER BY c.nome_contratada SEPARATOR ', ')
            FROM field_contratadas fc
            INNER JOIN contratadas c ON c.id_contratada = fc.id_contratada
            WHERE fc.id_field = f.id_field AND fc.ativo = 1
          ) AS contratadas_resumo,
          (f.rg_enc IS NOT NULL AND f.rg_enc <> '') AS has_rg,
          (f.cpf_enc IS NOT NULL AND f.cpf_enc <> '') AS has_cpf
        FROM fields f
        ORDER BY f.nome, f.id_field
        """
    )


def typeahead_fields(q: str, limit: int = 20) -> list[dict[str, Any]]:
    term = (q or "").strip()
    if len(term) < 2:
        return []
    lim = max(1, min(int(limit), 50))
    like = f"%{term}%"
    return _rows(
        """
        SELECT
          f.id_field,
          f.nome,
          f.telefone,
          (SELECT COUNT(*) FROM field_emails e WHERE e.id_field = f.id_field) AS emails_count
        FROM fields f
        WHERE f.ativo = 1
          AND (f.nome LIKE %s OR IFNULL(f.telefone, '') LIKE %s)
        ORDER BY f.nome
        LIMIT %s""",
        (like, like, lim),
    )


def _decrypt_field_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    out["rg"] = decrypt_text(out.pop("rg_enc", None)) if row.get("rg_enc") else None
    out["cpf"] = decrypt_text(out.pop("cpf_enc", None)) if row.get("cpf_enc") else None
    out.pop("rg_enc", None)
    out.pop("cpf_enc", None)
    return out


def get_field(id_field: int, *, decrypt_pii: bool = True) -> dict[str, Any] | None:
    row = _one(
        """
        SELECT id_field, nome, telefone, rg_enc, cpf_enc, ativo, criado_em, atualizado_em
        FROM fields
        WHERE id_field = %s
        """,
        (id_field,),
    )
    if not row:
        return None
    if decrypt_pii:
        out = _decrypt_field_row(row)
    else:
        out = {
            "id_field": row["id_field"],
            "nome": row["nome"],
            "telefone": row["telefone"],
            "ativo": row["ativo"],
            "criado_em": row.get("criado_em"),
            "atualizado_em": row.get("atualizado_em"),
            "has_rg": bool(row.get("rg_enc")),
            "has_cpf": bool(row.get("cpf_enc")),
        }
    assert out is not None
    emails_enc = _rows(
        """
        SELECT id_field_email, email, ordem
        FROM field_emails
        WHERE id_field = %s
        ORDER BY ordem, id_field_email
        """,
        (id_field,),
    )
    out["emails"] = [decrypt_text(e["email"]) or e["email"] for e in emails_enc]
    contratadas = _rows(
        """
        SELECT c.id_contratada, c.nome_contratada, c.cnpj, fc.inicio, fc.fim, fc.ativo
        FROM field_contratadas fc
        INNER JOIN contratadas c ON c.id_contratada = fc.id_contratada
        WHERE fc.id_field = %s AND fc.ativo = 1
        ORDER BY c.nome_contratada
        """,
        (id_field,),
    )
    out["contratadas"] = contratadas
    out["id_contratadas"] = [int(c["id_contratada"]) for c in contratadas]
    return out


def _insert_historico(
    cur,
    id_field: int,
    campo: str,
    valor_antigo: str | None,
    valor_novo: str | None,
    *,
    usuario_re: str | None,
    usuario_nome: str | None,
) -> None:
    if (valor_antigo or None) == (valor_novo or None):
        return
    cur.execute(
        """
        INSERT INTO field_historico
          (id_field, campo, valor_antigo, valor_novo, usuario_re, usuario_nome)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (id_field, campo, valor_antigo, valor_novo, usuario_re, usuario_nome),
    )


def _replace_emails(cur, id_field: int, emails: list[str]) -> None:
    cur.execute("DELETE FROM field_emails WHERE id_field = %s", (id_field,))
    for i, em in enumerate(emails, start=1):
        cur.execute(
            """
            INSERT INTO field_emails (id_field, email, ordem)
            VALUES (%s, %s, %s)
            """,
            (id_field, encrypt_text(em), i),
        )


def _replace_contratadas(cur, id_field: int, ids: list[int]) -> None:
    cur.execute("DELETE FROM field_contratadas WHERE id_field = %s", (id_field,))
    for cid in ids:
        cur.execute(
            """
            INSERT INTO field_contratadas (id_field, id_contratada, ativo)
            VALUES (%s, %s, 1)
            """,
            (id_field, cid),
        )


def create_field(
    data: dict[str, Any],
    *,
    usuario_re: str | None = None,
    usuario_nome: str | None = None,
) -> int:
    rg_enc = encrypt_text(data["rg"]) if data.get("rg") else None
    cpf_enc = encrypt_text(data["cpf"]) if data.get("cpf") else None
    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO fields (nome, telefone, rg_enc, cpf_enc, ativo)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                data["nome"],
                data.get("telefone"),
                rg_enc,
                cpf_enc,
                int(data.get("ativo", 1)),
            ),
        )
        new_id = int(cur.lastrowid)
        if data.get("_set_emails"):
            _replace_emails(cur, new_id, data.get("emails") or [])
        if data.get("_set_contratadas"):
            _replace_contratadas(cur, new_id, data.get("id_contratadas") or [])
        _insert_historico(
            cur,
            new_id,
            "create",
            None,
            data["nome"],
            usuario_re=usuario_re,
            usuario_nome=usuario_nome,
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


def update_field(
    id_field: int,
    data: dict[str, Any],
    *,
    usuario_re: str | None = None,
    usuario_nome: str | None = None,
) -> bool:
    existing = get_field(id_field, decrypt_pii=True)
    if not existing:
        return False
    nome = data.get("nome", existing["nome"])
    telefone = data["telefone"] if "telefone" in data else existing.get("telefone")
    rg = data["rg"] if data.get("_set_rg") else existing.get("rg")
    cpf = data["cpf"] if data.get("_set_cpf") else existing.get("cpf")
    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE fields SET
              nome = %s, telefone = %s, rg_enc = %s, cpf_enc = %s
            WHERE id_field = %s
            """,
            (
                nome,
                telefone,
                encrypt_text(rg) if rg else None,
                encrypt_text(cpf) if cpf else None,
                id_field,
            ),
        )
        changed = int(cur.rowcount or 0) > 0
        _insert_historico(
            cur,
            id_field,
            "nome",
            existing.get("nome"),
            nome,
            usuario_re=usuario_re,
            usuario_nome=usuario_nome,
        )
        _insert_historico(
            cur,
            id_field,
            "telefone",
            existing.get("telefone"),
            telefone,
            usuario_re=usuario_re,
            usuario_nome=usuario_nome,
        )
        _insert_historico(
            cur,
            id_field,
            "rg",
            mask_pii_for_historico("rg", existing.get("rg")),
            mask_pii_for_historico("rg", rg),
            usuario_re=usuario_re,
            usuario_nome=usuario_nome,
        )
        _insert_historico(
            cur,
            id_field,
            "cpf",
            mask_pii_for_historico("cpf", existing.get("cpf")),
            mask_pii_for_historico("cpf", cpf),
            usuario_re=usuario_re,
            usuario_nome=usuario_nome,
        )
        if data.get("_set_emails"):
            _replace_emails(cur, id_field, data.get("emails") or [])
            changed = True
            _insert_historico(
                cur,
                id_field,
                "emails",
                str(len(existing.get("emails") or [])),
                str(len(data.get("emails") or [])),
                usuario_re=usuario_re,
                usuario_nome=usuario_nome,
            )
        if data.get("_set_contratadas"):
            _replace_contratadas(cur, id_field, data.get("id_contratadas") or [])
            changed = True
        conn.commit()
        return changed
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


def set_field_ativo(id_field: int, ativo: int) -> bool:
    _, n = _exec(
        "UPDATE fields SET ativo = %s WHERE id_field = %s",
        (1 if int(ativo) else 0, id_field),
    )
    return n > 0


def contratadas_existem(ids: list[int]) -> bool:
    if not ids:
        return True
    placeholders = ",".join(["%s"] * len(ids))
    row = _one(
        f"""
        SELECT COUNT(*) AS n
        FROM contratadas
        WHERE id_contratada IN ({placeholders}) AND ativo = 1
        """,
        tuple(ids),
    )
    return bool(row and int(row["n"]) == len(ids))


def find_field_id_by_nome(nome: str, *, apenas_ativos: bool = True) -> int | None:
    """Retorna id_field pelo nome exato (evita duplicar master no cadastro direto)."""
    if not nome:
        return None
    sql = "SELECT id_field FROM fields WHERE nome = %s"
    if apenas_ativos:
        sql += " AND ativo = 1"
    sql += " LIMIT 1"
    row = _one(sql, (nome,))
    return int(row["id_field"]) if row else None