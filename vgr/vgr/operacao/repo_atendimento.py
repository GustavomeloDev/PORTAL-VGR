"""CRUD atendimentos VGR (P3/P4/P6/P13)."""
from __future__ import annotations

import logging
from typing import Any

from vgr.credentials.db_connection import get_vgr_db_connection
from vgr.vgr.operacao.catalogo_atendimento import (
    STATUS_OPERACIONAL,
    is_status_agendado,
    is_status_final,
    is_substatus_gestao,
    substatus_padrao,
)

log = logging.getLogger("VGR.repo_atendimento")

# ID VGR do equipamento ativo da unidade, por tipo de serviço (reflexo do inventário)
_SQL_ID_VGR_POR_SERVICO = """
(SELECT e.id_vgr FROM equipamentos e
   WHERE e.id_unidade = t.id_unidade AND e.ativo = 1
     AND e.tipo_servico = 'SDWAN'
   ORDER BY e.id_equipamento LIMIT 1) AS id_vgr_sdwan,
(SELECT e.id_vgr FROM equipamentos e
   WHERE e.id_unidade = t.id_unidade AND e.ativo = 1
     AND e.tipo_servico = 'SDWIFI'
   ORDER BY e.id_equipamento LIMIT 1) AS id_vgr_sdwifi,
(SELECT e.id_vgr FROM equipamentos e
   WHERE e.id_unidade = t.id_unidade AND e.ativo = 1
     AND e.tipo_servico = 'SDLAN'
   ORDER BY e.id_equipamento LIMIT 1) AS id_vgr_sdlan
"""


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


def list_atendimentos(*, apenas_ativos: bool = False) -> list[dict[str, Any]]:
    where = "WHERE t.ativo = 1" if apenas_ativos else ""
    return _rows(
        f"""
        SELECT
          t.id_atendimento, t.id_unidade, u.nome_unidade, u.id_cliente,
          c.razao_social, t.id_agendamento,
          t.status_atendimento, t.substatus_atendimento, t.analista_atuante,
          t.atendimento_iniciado, t.abertura, t.fechamento, t.ativo,
          t.abertura AS data_atendimento,
          t.criado_em, t.atualizado_em,
          a.data_agendamento, a.hora_agendamento, a.status_agendamento,
          {_SQL_ID_VGR_POR_SERVICO}
        FROM atendimentos t
        INNER JOIN unidades u ON u.id_unidade = t.id_unidade
        INNER JOIN clientes c ON c.id_cliente = u.id_cliente
        LEFT JOIN agendamentos a ON a.id_agendamento = t.id_agendamento
        {where}
        ORDER BY t.id_atendimento DESC
        """
    )

def list_atendimentos_operacao() -> list[dict[str, Any]]:
    """Fila operacional (padrão PRODESP):

    - Tabela: atendimentos ativos de QUALQUER data, exceto status 'Concluído'
      (histórico operacional visível, como na fila PRODESP para não-admin);
    - Cards da fila (dia atual): derivados client-side sobre estas linhas
      (vgrRowDiaAtual em vgr_atendimentos.js).
    """
    return _rows(
        f"""
        SELECT
          t.id_atendimento, t.id_unidade, u.nome_unidade, u.id_cliente,
          c.razao_social, t.id_agendamento,
          t.status_atendimento, t.substatus_atendimento, t.analista_atuante,
          t.atendimento_iniciado, t.abertura, t.fechamento, t.ativo,
          t.abertura AS data_atendimento,
          t.criado_em, t.atualizado_em,
          a.data_agendamento, a.hora_agendamento, a.status_agendamento,
          {_SQL_ID_VGR_POR_SERVICO}
        FROM atendimentos t
        INNER JOIN unidades u ON u.id_unidade = t.id_unidade
        INNER JOIN clientes c ON c.id_cliente = u.id_cliente
        LEFT JOIN agendamentos a ON a.id_agendamento = t.id_agendamento
        WHERE t.ativo = 1
          AND COALESCE(t.status_atendimento, '') <> 'Concluído'
        ORDER BY t.id_atendimento DESC
        """
    )

def get_atendimento(id_atendimento: int) -> dict[str, Any] | None:
    row = _one(
        f"""
        SELECT
          t.id_atendimento, t.id_unidade, u.nome_unidade, u.id_cliente,
          c.razao_social, t.id_agendamento,
          t.status_atendimento, t.substatus_atendimento, t.analista_atuante,
          t.atendimento_iniciado, t.abertura, t.fechamento, t.observacoes,
          t.abertura AS data_atendimento,
          t.ativo, t.criado_em, t.atualizado_em,
          t.criado_por_re, t.atualizado_por_re,
          a.status_agendamento, a.substatus_agendamento AS agenda_substatus,
          a.data_agendamento, a.hora_agendamento, a.hora_inicio, a.hora_fim,
          a.analista_destino AS agenda_analista,
          a.q_compra_equip, a.q_equip_mam, a.q_email_agendamento, a.q_lote,
          a.q_ticket_aberto, a.q_confirma_csi_gp, a.q_tem_problema,
            a.tipo AS agenda_tipo,
            {_SQL_ID_VGR_POR_SERVICO}
        FROM atendimentos t
        INNER JOIN unidades u ON u.id_unidade = t.id_unidade
        INNER JOIN clientes c ON c.id_cliente = u.id_cliente
        LEFT JOIN agendamentos a ON a.id_agendamento = t.id_agendamento
        WHERE t.id_atendimento = %s
        """,
        (id_atendimento,),
    )
    if not row:
        return None

    row["fields"] = list_fields_do_atendimento(id_atendimento)
    if not row["fields"] and row.get("id_agendamento"):
        from vgr.vgr.operacao.repo_agendamento import list_fields_do_agendamento

        row["fields"] = list_fields_do_agendamento(int(row["id_agendamento"]))
        row["fields_origem"] = "agendamento"
    else:
        row["fields_origem"] = "atendimento" if row["fields"] else None

    eq_tkt = _one(
        """
        SELECT id_equipamento, hostname, serial, tkt_noc, tipo_servico
        FROM equipamentos
        WHERE id_unidade = %s AND ativo = 1
        ORDER BY
          CASE WHEN tipo_servico = 'SDWAN' THEN 0 ELSE 1 END,
          id_equipamento
        LIMIT 1
        """,
        (int(row["id_unidade"]),),
    )
    row["id_equipamento_tkt"] = eq_tkt.get("id_equipamento") if eq_tkt else None
    row["tkt_noc"] = (eq_tkt or {}).get("tkt_noc")
    row["eq_tkt_label"] = None
    if eq_tkt:
        row["eq_tkt_label"] = (
            eq_tkt.get("hostname")
            or eq_tkt.get("serial")
            or f"#{eq_tkt.get('id_equipamento')}"
        )

    row["observacoes_log"] = parse_observacoes_log(row.get("observacoes"))

    _ck = (
        "q_compra_equip",
        "q_equip_mam",
        "q_email_agendamento",
        "q_lote",
        "q_ticket_aberto",
        "q_confirma_csi_gp",
        "q_tem_problema",
    )
    if row.get("id_agendamento"):
        row["checklist_agenda"] = {k: int(row.get(k) or 0) for k in _ck}
    else:
        row["checklist_agenda"] = None
    for k in _ck:
        row.pop(k, None)

    row["status_log"] = list_atendimento_status_log(id_atendimento)
    return row


def parse_observacoes_log(texto: str | None) -> list[dict[str, str]]:
    """Linhas no formato `[YYYY-MM-DD HH:MM | quem] texto` (P0)."""
    if not texto or not str(texto).strip():
        return []
    out: list[dict[str, str]] = []
    for raw_line in str(texto).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and "] " in line:
            meta, _, resto = line[1:].partition("] ")
            partes = [p.strip() for p in meta.split("|", 1)]
            out.append(
                {
                    "quando": partes[0] if partes else "",
                    "quem": partes[1] if len(partes) > 1 else "",
                    "texto": resto.strip(),
                }
            )
        else:
            out.append({"quando": "", "quem": "", "texto": line})
    return out


def list_atendimento_status_log(id_atendimento: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id_log, status_anterior, status_novo,
               substatus_anterior, substatus_novo,
               usuario_re, usuario_nome, observacao, criado_em
        FROM atendimento_status_log
        WHERE id_atendimento = %s
        ORDER BY id_log DESC
        LIMIT 100
        """,
        (id_atendimento,),
    )


def list_fields_do_atendimento(id_atendimento: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id_atendimento_field, id_field, ordem, snap_nome, snap_telefone,
               snap_emails, snap_contratada_nome, id_contratada,
               (snap_rg_enc IS NOT NULL AND snap_rg_enc <> '') AS has_rg,
               (snap_cpf_enc IS NOT NULL AND snap_cpf_enc <> '') AS has_cpf
        FROM atendimento_fields
        WHERE id_atendimento = %s
        ORDER BY ordem, id_atendimento_field
        """,
        (id_atendimento,),
    )


def ensure_fields_from_agendamento(id_atendimento: int) -> list[dict[str, Any]]:
    """Copia snapshot do agendamento para atendimento_fields se ainda vazio."""
    existing = list_fields_do_atendimento(id_atendimento)
    if existing:
        return existing
    atend = _one(
        "SELECT id_agendamento FROM atendimentos WHERE id_atendimento = %s",
        (id_atendimento,),
    )
    if not atend or not atend.get("id_agendamento"):
        return []
    from vgr.vgr.operacao.repo_agendamento import list_fields_do_agendamento

    origem = list_fields_do_agendamento(int(atend["id_agendamento"]))
    if not origem:
        return []
    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor()
        for ordem, f in enumerate(origem, start=1):
            cur.execute(
                """
                INSERT INTO atendimento_fields (
                  id_atendimento, id_field, ordem, snap_nome, snap_telefone,
                  snap_rg_enc, snap_cpf_enc, snap_emails, snap_contratada_nome,
                  id_contratada
                )
                SELECT %s, id_field, %s, snap_nome, snap_telefone,
                       snap_rg_enc, snap_cpf_enc, snap_emails, snap_contratada_nome,
                       id_contratada
                FROM agendamento_fields
                WHERE id_agendamento_field = %s
                """,
                (
                    id_atendimento,
                    ordem,
                    int(f["id_agendamento_field"]),
                ),
            )
        conn.commit()
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
    return list_fields_do_atendimento(id_atendimento)


def update_atendimento_field_snap(
    id_atendimento: int,
    id_field: int,
    *,
    snap_nome: str | None = None,
    snap_telefone: str | None = None,
    snap_contratada_nome: str | None = None,
) -> bool:
    ensure_fields_from_agendamento(id_atendimento)
    _, n = _exec(
        """
        UPDATE atendimento_fields SET
          snap_nome = COALESCE(%s, snap_nome),
          snap_telefone = COALESCE(%s, snap_telefone),
          snap_contratada_nome = COALESCE(%s, snap_contratada_nome)
        WHERE id_atendimento = %s AND id_field = %s
        """,
        (
            snap_nome,
            snap_telefone,
            snap_contratada_nome,
            id_atendimento,
            id_field,
        ),
    )
    return n > 0


def create_atendimento_field_direct(
    id_atendimento: int,
    id_field: int,
    *,
    snap_nome: str | None = None,
    snap_telefone: str | None = None,
    snap_contratada_nome: str | None = None,
) -> int:
    """Vincula um Field ao atendimento gravando o snapshot informado (cadastro direto)."""
    last_id, _ = _exec(
        """
        INSERT INTO atendimento_fields (
          id_atendimento, id_field, ordem, snap_nome, snap_telefone,
          snap_rg_enc, snap_cpf_enc, snap_emails, snap_contratada_nome,
          id_contratada
        ) VALUES (%s, %s, 1, %s, %s, NULL, NULL, NULL, %s, NULL)
        """,
        (
            id_atendimento,
            id_field,
            snap_nome,
            snap_telefone,
            snap_contratada_nome,
        ),
    )
    if not last_id:
        raise RuntimeError("insert_atendimento_field_sem_id")
    return last_id


def append_observacao(
    id_atendimento: int,
    texto: str,
    *,
    usuario_re: str | None = None,
    usuario_nome: str | None = None,
) -> str:
    from datetime import datetime

    texto = (texto or "").strip()
    if not texto:
        raise ValueError("Observação vazia.")
    if len(texto) > 2000:
        raise ValueError("Observação excede 2000 caracteres.")
    row = get_atendimento(id_atendimento)
    if not row:
        raise ValueError("Atendimento não encontrado.")
    quando = datetime.now().strftime("%Y-%m-%d %H:%M")
    quem = (usuario_nome or usuario_re or "sistema").strip()[:80]
    linha = f"[{quando} | {quem}] {texto}"
    atual = (row.get("observacoes") or "").rstrip()
    novo = f"{atual}\n{linha}" if atual else linha
    if len(novo) > 5000:
        raise ValueError("Limite de observações do atendimento atingido.")
    _exec(
        """
        UPDATE atendimentos
        SET observacoes = %s, atualizado_por_re = %s
        WHERE id_atendimento = %s
        """,
        (novo, usuario_re, id_atendimento),
    )
    return novo


def get_agendamento_resumo(id_agendamento: int) -> dict[str, Any] | None:
    return _one(
        """
        SELECT id_agendamento, id_unidade, status_agendamento,
               substatus_agendamento, data_agendamento, hora_agendamento,
               ativo
        FROM agendamentos
        WHERE id_agendamento = %s
        """,
        (id_agendamento,),
    )


def find_atendimento_id_by_agendamento(
    id_agendamento: int, *, exclude_id: int | None = None
) -> int | None:
    if exclude_id is None:
        row = _one(
            """
            SELECT id_atendimento FROM atendimentos
            WHERE id_agendamento = %s
            LIMIT 1
            """,
            (id_agendamento,),
        )
    else:
        row = _one(
            """
            SELECT id_atendimento FROM atendimentos
            WHERE id_agendamento = %s AND id_atendimento <> %s
            LIMIT 1
            """,
            (id_agendamento, exclude_id),
        )
    return int(row["id_atendimento"]) if row else None


def _append_status_log(
    cur,
    id_atendimento: int,
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
        INSERT INTO atendimento_status_log (
          id_atendimento, status_anterior, status_novo,
          substatus_anterior, substatus_novo,
          usuario_re, usuario_nome, observacao
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id_atendimento,
            status_ant,
            status_novo,
            sub_ant,
            sub_novo,
            usuario_re,
            usuario_nome,
            observacao,
        ),
    )


def _deve_marcar_iniciado(status: str | None, sub: str | None) -> bool:
    """P13: atendimento inicia ao sair da gestão ou ao entrar em status final.
    'Agendado' é fase de preparação -> NÃO inicia, NÃO seta abertura e
    NÃO trava o analista atuante.
    """
    if is_status_final(status):
        return True
    if is_status_agendado(status):
        return False
    return (status or "").strip() == STATUS_OPERACIONAL and not is_substatus_gestao(sub)


def create_atendimento(
    data: dict[str, Any],
    *,
    usuario_re: str | None = None,
    usuario_nome: str | None = None,
) -> int:
    status = (data.get("status_atendimento") or STATUS_OPERACIONAL).strip()
    sub = (
        data.get("substatus_atendimento")
        or substatus_padrao(status)
        or "Aguarda Gestão"
    ).strip()
    iniciado = int(data.get("atendimento_iniciado") or 0)
    if _deve_marcar_iniciado(status, sub):
        iniciado = 1
    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO atendimentos (
              id_unidade, id_agendamento, status_atendimento, substatus_atendimento,
              analista_atuante, atendimento_iniciado, abertura, fechamento,
              observacoes, ativo, criado_por_re, atualizado_por_re
            ) VALUES (
              %s, %s, %s, %s, %s, %s,
              CASE WHEN %s = 1 THEN NOW() ELSE NULL END,
              CASE WHEN %s THEN NOW() ELSE NULL END,
              %s, %s, %s, %s
            )
            """,
            (
                data["id_unidade"],
                data.get("id_agendamento"),
                status,
                sub,
                data.get("analista_atuante"),
                iniciado,
                iniciado,
                1 if is_status_final(status) else 0,
                data.get("observacoes"),
                int(data.get("ativo", 1)),
                usuario_re,
                usuario_re,
            ),
        )
        new_id = int(cur.lastrowid)
        _append_status_log(
            cur,
            new_id,
            status_ant=None,
            status_novo=status,
            sub_ant=None,
            sub_novo=sub,
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


def update_atendimento(
    id_atendimento: int,
    data: dict[str, Any],
    *,
    usuario_re: str | None = None,
    usuario_nome: str | None = None,
    allow_troca_analista: bool = False,
) -> bool:
    existing = get_atendimento(id_atendimento)
    if not existing:
        return False
    status = data.get("status_atendimento", existing["status_atendimento"])
    sub = data.get(
        "substatus_atendimento", existing.get("substatus_atendimento")
    )
    analista = (
        data["analista_atuante"]
        if "analista_atuante" in data
        else existing.get("analista_atuante")
    )
    obs = data.get("observacoes")
    if obs is None:
        obs = existing.get("observacoes")
    id_ag = (
        data["id_agendamento"]
        if "id_agendamento" in data
        else existing.get("id_agendamento")
    )
    id_uni = data.get("id_unidade", existing["id_unidade"])
    iniciado = int(existing.get("atendimento_iniciado") or 0)
    ja_iniciado = iniciado == 1
    if data.get("atendimento_iniciado") is not None:
        if int(data["atendimento_iniciado"]):
            iniciado = 1
    if _deve_marcar_iniciado(status, sub):
        iniciado = 1
    # Ao iniciar: se analista vazio, usa o usuário da sessão (P0 / P13).
    if iniciado and not (analista or "").strip():
        analista = (
            usuario_nome or usuario_re or existing.get("analista_atuante") or ""
        ).strip() or None
    # P13: trava o analista SOMENTE se o atendimento já estava iniciado antes.
    if iniciado and ja_iniciado and not allow_troca_analista:
        old_a = (existing.get("analista_atuante") or "").strip()
        new_a = (analista or "").strip()
        if old_a and new_a and old_a != new_a:
            raise ValueError(
                "Troca de analista bloqueada após início do atendimento (P13)."
            )
    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE atendimentos SET
              id_unidade = %s,
              id_agendamento = %s,
              status_atendimento = %s,
              substatus_atendimento = %s,
              analista_atuante = %s,
              atendimento_iniciado = %s,
              abertura = CASE
                WHEN %s = 1 AND abertura IS NULL THEN NOW()
                ELSE abertura
              END,
              fechamento = CASE
                WHEN %s = 1 THEN COALESCE(fechamento, NOW())
                ELSE NULL
              END,
              observacoes = %s,
              atualizado_por_re = %s
            WHERE id_atendimento = %s
            """,
            (
                id_uni,
                id_ag,
                status,
                sub,
                analista,
                iniciado,
                1 if iniciado else 0,
                1 if is_status_final(status) else 0,
                obs,
                usuario_re,
                id_atendimento,
            ),
        )
        n = int(cur.rowcount or 0)
        _append_status_log(
            cur,
            id_atendimento,
            status_ant=existing.get("status_atendimento"),
            status_novo=status,
            sub_ant=existing.get("substatus_atendimento"),
            sub_novo=sub,
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


def set_atendimento_ativo(id_atendimento: int, ativo: int) -> bool:
    _, n = _exec(
        "UPDATE atendimentos SET ativo = %s WHERE id_atendimento = %s",
        (1 if int(ativo) else 0, id_atendimento),
    )
    return n > 0