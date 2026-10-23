"""Consultas de inventário VGR (listagens DataTables client-side)."""

from __future__ import annotations

import logging
from typing import Any

from vgr.credentials.db_connection import get_vgr_db_connection

log = logging.getLogger("VGR.repo")

# ID VGR da unidade agora vive em equipamentos (unidades.id_vgr foi removido).
# Representante: equipamento ativo SDWAN; fallback: primeiro equipamento ativo.
_SQL_ID_VGR_UNIDADE = """
COALESCE(
 (SELECT e.id_vgr FROM equipamentos e
  WHERE e.id_unidade = u.id_unidade AND e.ativo = 1
    AND e.tipo_servico = 'SDWAN'
  ORDER BY e.id_equipamento LIMIT 1),
 (SELECT e.id_vgr FROM equipamentos e
  WHERE e.id_unidade = u.id_unidade AND e.ativo = 1
  ORDER BY e.id_equipamento LIMIT 1)
) AS id_vgr
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
    """INSERT/UPDATE/DELETE. Retorna (lastrowid, rowcount)."""
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


def list_clientes(*, apenas_ativos: bool = False) -> list[dict[str, Any]]:
    where = "WHERE ativo = 1" if apenas_ativos else ""
    return _rows(
        f"""
        SELECT id_cliente, razao_social, cnpj_cliente, cidade, uf, nome_gp_cs_clientes, lider_tecnico,
               ativo, criado_em, atualizado_em
        FROM clientes
        {where}
        ORDER BY razao_social
        """
    )


def get_cliente(id_cliente: int) -> dict[str, Any] | None:
    return _one(
        """
        SELECT id_cliente, razao_social, cnpj_cliente, endereco_principal, cidade, uf, cep,
               nome_gp_cs_clientes, lider_tecnico, ativo, criado_em, atualizado_em
        FROM clientes
        WHERE id_cliente = %s
        """,
        (id_cliente,),
    )


def find_cliente_id_by_cnpj(cnpj: str, *, exclude_id: int | None = None) -> int | None:
    """Retorna id_cliente se já existir o mesmo CNPJ (texto exato armazenado)."""
    if not cnpj:
        return None
    if exclude_id is None:
        row = _one(
            "SELECT id_cliente FROM clientes WHERE cnpj_cliente = %s LIMIT 1",
            (cnpj,),
        )
    else:
        row = _one(
            """
            SELECT id_cliente FROM clientes
            WHERE cnpj_cliente = %s AND id_cliente <> %s
            LIMIT 1
            """,
            (cnpj, exclude_id),
        )
    return int(row["id_cliente"]) if row else None


def create_cliente(data: dict[str, Any]) -> int:
    last_id, _ = _exec(
        """
        INSERT INTO clientes (
          razao_social, cnpj_cliente, endereco_principal, cidade, uf, cep,
          lider_tecnico, nome_gp_cs_clientes, ativo
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            data["razao_social"],
            data.get("cnpj_cliente"),
            data.get("endereco_principal"),
            data.get("cidade"),
            data.get("uf"),
            data.get("cep"),
            data.get("lider_tecnico"),
            data.get("nome_gp_cs_clientes"),
            int(data.get("ativo", 1)),
        ),
    )
    if not last_id:
        raise RuntimeError("insert_cliente_sem_id")
    return last_id


def update_cliente(id_cliente: int, data: dict[str, Any]) -> bool:
    _, n = _exec(
        """
        UPDATE clientes SET
          razao_social = %s,
          cnpj_cliente = %s,
          endereco_principal = %s,
          cidade = %s,
          uf = %s,
          cep = %s,
          lider_tecnico = %s,
          nome_gp_cs_clientes = %s
        WHERE id_cliente = %s
        """,
        (
            data["razao_social"],
            data.get("cnpj_cliente"),
            data.get("endereco_principal"),
            data.get("cidade"),
            data.get("uf"),
            data.get("cep"),
            data.get("lider_tecnico"),
            data.get("nome_gp_cs_clientes"),
            id_cliente,
        ),
    )
    return n > 0


def set_cliente_ativo(id_cliente: int, ativo: int) -> bool:
    _, n = _exec(
        "UPDATE clientes SET ativo = %s WHERE id_cliente = %s",
        (1 if int(ativo) else 0, id_cliente),
    )
    return n > 0


def list_clientes_opcoes(*, apenas_ativos: bool = True) -> list[dict[str, Any]]:
    """Opções enxutas para select (CRUD unidades)."""
    where = "WHERE ativo = 1" if apenas_ativos else ""
    return _rows(
        f"""
        SELECT id_cliente, razao_social
        FROM clientes
        {where}
        ORDER BY razao_social
        """
    )


def list_unidades(
    *,
    id_cliente: int | None = None,
    apenas_ativos: bool = False,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if id_cliente is not None:
        clauses.append("u.id_cliente = %s")
        params.append(id_cliente)
    if apenas_ativos:
        clauses.append("u.ativo = 1")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return _rows(
        f"""
        SELECT u.id_unidade, u.id_cliente, c.razao_social, u.nome_unidade, u.contato_unidade, u.cnpj_unidade,
               {_SQL_ID_VGR_UNIDADE}, u.codigo_unidade, u.tipo_unidade, u.tipo_projeto, u.topologia_unidades, u.cidade, u.uf, u.ha, u.ativo,
               u.criado_em, u.atualizado_em
        FROM unidades u
        INNER JOIN clientes c ON c.id_cliente = u.id_cliente
        {where}
        ORDER BY c.razao_social, u.nome_unidade
        """,
        params,
    )


def get_unidade(id_unidade: int) -> dict[str, Any] | None:
    return _one(
        f"""
        SELECT u.id_unidade, u.id_cliente, c.razao_social, c.cnpj_cliente, c.lider_tecnico,
               c.endereco_principal AS cliente_endereco_principal,
               c.cidade AS cliente_cidade, c.uf AS cliente_uf, c.cep AS cliente_cep,
               u.nome_unidade, u.contato_unidade, u.cnpj_unidade, {_SQL_ID_VGR_UNIDADE}, u.topologia_unidades, u.codigo_unidade, u.codigo_identificacao,
               u.tipo_unidade, u.tipo_projeto, u.endereco, u.bairro, u.cidade, u.uf, u.cep,
               u.latitude, u.longitude, u.ha, u.ativo, u.criado_em, u.atualizado_em
        FROM unidades u
        INNER JOIN clientes c ON c.id_cliente = u.id_cliente
        WHERE u.id_unidade = %s
        """,
        (id_unidade,),
    )

def find_unidade_id_by_equipamento_id_vgr(id_vgr: str) -> int | None:
    """Resolve a unidade pelo ID VGR gravado em equipamentos.id_vgr (prioriza ativos)."""
    if not id_vgr:
        return None
    row = _one(
        """
        SELECT id_unidade FROM equipamentos
        WHERE id_vgr = %s
        ORDER BY ativo DESC, id_equipamento ASC
        LIMIT 1
        """,
        (id_vgr,),
    )
    return int(row["id_unidade"]) if row else None    

def create_unidade(data: dict[str, Any]) -> int:
    last_id, _ = _exec(
        """
        INSERT INTO unidades (
        id_cliente, nome_unidade, contato_unidade, cnpj_unidade, codigo_unidade,
        codigo_identificacao, tipo_unidade, tipo_projeto, topologia_unidades, endereco, bairro, cidade, uf, cep,
        latitude, longitude, ha, ativo
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            data["id_cliente"],
            data["nome_unidade"],
            data.get("contato_unidade"),
            data.get("cnpj_unidade"),
            data.get("codigo_unidade"),
            data.get("codigo_identificacao"),
            data.get("tipo_unidade") or "FILIAL",
            data.get("tipo_projeto") or "PRATELEIRA",
            data.get("topologia_unidades"),
            data.get("endereco"),
            data.get("bairro"),
            data.get("cidade"),
            data.get("uf"),
            data.get("cep"),
            data.get("latitude"),
            data.get("longitude"),
            int(data.get("ha", 0)),
            int(data.get("ativo", 1)),
        ),
    )
    if not last_id:
        raise RuntimeError("insert_unidade_sem_id")
    return last_id


def update_unidade(id_unidade: int, data: dict[str, Any]) -> bool:
    _, n = _exec(
        """
        UPDATE unidades SET
            id_cliente = %s,
            nome_unidade = %s,
            contato_unidade = %s,
            cnpj_unidade = %s,
            codigo_unidade = %s,
            codigo_identificacao = %s,
            tipo_unidade = %s,
            tipo_projeto = %s,
            topologia_unidades = %s,
            endereco = %s,
            bairro = %s,
            cidade = %s,
            uf = %s,
            cep = %s,
            latitude = %s,
            longitude = %s,
            ha = %s
        WHERE id_unidade = %s
        """,
        (
            data["id_cliente"],
            data["nome_unidade"],
            data.get("contato_unidade"),
            data.get("cnpj_unidade"),
            data.get("codigo_unidade"),
            data.get("codigo_identificacao"),
            data.get("tipo_unidade") or "FILIAL",
            data.get("tipo_projeto") or "PRATELEIRA",
            data.get("topologia_unidades"),
            data.get("endereco"),
            data.get("bairro"),
            data.get("cidade"),
            data.get("uf"),
            data.get("cep"),
            data.get("latitude"),
            data.get("longitude"),
            int(data.get("ha", 0)),
            id_unidade,
        ),
    )
    return n > 0


def set_unidade_ativo(id_unidade: int, ativo: int) -> bool:
    _, n = _exec(
        "UPDATE unidades SET ativo = %s WHERE id_unidade = %s",
        (1 if int(ativo) else 0, id_unidade),
    )
    return n > 0


def list_agendamentos_by_unidade(id_unidade: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id_agendamento, id_unidade, status_agendamento, substatus_agendamento,
               data_agendamento, hora_agendamento, tipo, analista_destino, analista_livre, ativo
        FROM agendamentos
        WHERE id_unidade = %s
        ORDER BY data_agendamento DESC, id_agendamento DESC
        """,
        (id_unidade,),
    )


def list_atendimentos_by_unidade(id_unidade: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id_atendimento, id_unidade, id_agendamento, status_atendimento, substatus_atendimento,
               analista_atuante, atendimento_iniciado, abertura, fechamento, ativo
        FROM atendimentos
        WHERE id_unidade = %s
        ORDER BY id_atendimento DESC
        """,
        (id_unidade,),
    )


def list_agendamentos_by_cliente(id_cliente: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT a.id_agendamento, a.id_unidade, u.nome_unidade, a.status_agendamento,
               a.substatus_agendamento, a.data_agendamento, a.hora_agendamento,
               a.tipo, a.analista_destino, a.analista_livre, a.ativo
        FROM agendamentos a
        INNER JOIN unidades u ON u.id_unidade = a.id_unidade
        WHERE u.id_cliente = %s
        ORDER BY a.data_agendamento DESC, a.id_agendamento DESC
        """,
        (id_cliente,),
    )


def list_atendimentos_by_cliente(id_cliente: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT t.id_atendimento, t.id_unidade, u.nome_unidade, t.id_agendamento,
               t.status_atendimento, t.substatus_atendimento, t.analista_atuante,
               t.atendimento_iniciado, t.abertura, t.fechamento, t.ativo
        FROM atendimentos t
        INNER JOIN unidades u ON u.id_unidade = t.id_unidade
        WHERE u.id_cliente = %s
        ORDER BY t.id_atendimento DESC
        """,
        (id_cliente,),
    )


def list_equipamentos_by_unidade(id_unidade: int) -> list[dict[str, Any]]:
    """Lista equipamentos — sem fortcloud_key (sensível)."""
    return _rows(
        """
        SELECT id_equipamento, id_unidade, vendor, modelo, serial, hostname,
               id_vgr, licenca, tipo_servico, tkt_sae, tkt_noc, ativo,
               criado_em, atualizado_em
        FROM equipamentos
        WHERE id_unidade = %s
        ORDER BY COALESCE(tipo_servico, ''), id_equipamento
        """,
        (id_unidade,),
    )


def count_equipamentos_sdwan(id_unidade: int) -> int:
    """Equipamentos ativos com tipo_servico = SDWAN, usado no card da unidade."""
    row = _one(
        """
        SELECT COUNT(*) AS n
        FROM equipamentos
        WHERE id_unidade = %s AND ativo = 1 AND tipo_servico = 'SDWAN'
        """,
        (id_unidade,),
    )
    return int(row["n"]) if row else 0


def get_equipamento(id_equipamento: int) -> dict[str, Any] | None:
    """Inclui flag has_fortcloud_key; nunca devolve a chave em claro na listagem."""
    row = _one(
        """
        SELECT id_equipamento, id_unidade, vendor, modelo, serial, hostname,
               id_vgr, licenca, tipo_servico, tkt_sae, tkt_noc, ativo,
               criado_em, atualizado_em,
               (fortcloud_key IS NOT NULL AND fortcloud_key <> '') AS has_fortcloud_key
        FROM equipamentos
        WHERE id_equipamento = %s
        """,
        (id_equipamento,),
    )
    return row


def find_equipamento_id_by_serial(serial: str, *, exclude_id: int | None = None) -> int | None:
    if not serial:
        return None
    if exclude_id is None:
        row = _one(
            "SELECT id_equipamento FROM equipamentos WHERE serial = %s LIMIT 1",
            (serial,),
        )
    else:
        row = _one(
            """
            SELECT id_equipamento FROM equipamentos
            WHERE serial = %s AND id_equipamento <> %s
            LIMIT 1
            """,
            (serial, exclude_id),
        )
    return int(row["id_equipamento"]) if row else None


def create_equipamento(data: dict[str, Any]) -> int:
    from core.security.encryption import encrypt_text

    fk = data.get("fortcloud_key")
    fk_enc = encrypt_text(fk) if fk else None
    last_id, _ = _exec(
        """
        INSERT INTO equipamentos (
          id_unidade, vendor, modelo, serial, hostname, id_vgr, licenca, fortcloud_key,
          tipo_servico, tkt_sae, tkt_noc, ativo
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            data["id_unidade"],
            data.get("vendor"),
            data.get("modelo"),
            data["serial"],
            data.get("hostname"),
            data.get("id_vgr"),
            data.get("licenca"),
            fk_enc,
            data.get("tipo_servico"),
            data.get("tkt_sae"),
            data.get("tkt_noc"),
            int(data.get("ativo", 1)),
        ),
    )
    if not last_id:
        raise RuntimeError("insert_equipamento_sem_id")
    return last_id


def update_equipamento_tkt_noc(id_equipamento: int, tkt_noc: str | None) -> bool:
    """Atualiza só o Ticket NOC (painel de atendimento / P0)."""
    _, n = _exec(
        "UPDATE equipamentos SET tkt_noc = %s WHERE id_equipamento = %s",
        (tkt_noc, id_equipamento),
    )
    return n > 0


def update_equipamento(id_equipamento: int, data: dict[str, Any]) -> bool:
    from core.security.encryption import encrypt_text

    if data.get("_set_fortcloud"):
        fk_enc = encrypt_text(data.get("fortcloud_key"))
        _, n = _exec(
            """
            UPDATE equipamentos SET
              id_unidade = %s, vendor = %s, modelo = %s, serial = %s, hostname = %s,
              id_vgr = %s, licenca = %s, fortcloud_key = %s, tipo_servico = %s, tkt_sae = %s,
              tkt_noc = %s
            WHERE id_equipamento = %s
            """,
            (
                data["id_unidade"],
                data.get("vendor"),
                data.get("modelo"),
                data["serial"],
                data.get("hostname"),
                data.get("id_vgr"),
                data.get("licenca"),
                fk_enc,
                data.get("tipo_servico"),
                data.get("tkt_sae"),
                data.get("tkt_noc"),
                id_equipamento,
            ),
        )
    else:
        _, n = _exec(
            """
            UPDATE equipamentos SET
              id_unidade = %s, vendor = %s, modelo = %s, serial = %s, hostname = %s,
              id_vgr = %s, licenca = %s, tipo_servico = %s, tkt_sae = %s, tkt_noc = %s
            WHERE id_equipamento = %s
            """,
            (
                data["id_unidade"],
                data.get("vendor"),
                data.get("modelo"),
                data["serial"],
                data.get("hostname"),
                data.get("id_vgr"),
                data.get("licenca"),
                data.get("tipo_servico"),
                data.get("tkt_sae"),
                data.get("tkt_noc"),
                id_equipamento,
            ),
        )
    return n > 0


def set_equipamento_ativo(id_equipamento: int, ativo: int) -> bool:
    _, n = _exec(
        "UPDATE equipamentos SET ativo = %s WHERE id_equipamento = %s",
        (1 if int(ativo) else 0, id_equipamento),
    )
    return n > 0


def list_links_by_unidade(id_unidade: int) -> list[dict[str, Any]]:
    """Lista links (WAN e conectividade da unidade) — sem secrets em claro."""
    return _rows(
        """
        SELECT id_link, id_unidade, id_equipamento, tipo_link, modo_conexao, ordem,
               id_vgr_link, identificador, designador, ip_address, mascara, gateway,
               subrede, vlan, velocidade, operadora, range_start, range_end, ativo,
               criado_em, atualizado_em
        FROM links
        WHERE id_unidade = %s
        ORDER BY COALESCE(ordem, 0), id_link
        """,
        (id_unidade,),
    )


def get_link(id_link: int) -> dict[str, Any] | None:
    return _one(
        """
        SELECT id_link, id_unidade, id_equipamento, tipo_link, modo_conexao, ordem,
               id_vgr_link, identificador, designador, ip_address, mascara, gateway,
               subrede, vlan, velocidade, operadora, range_start, range_end, ativo,
               criado_em, atualizado_em,
               (pppoe_user IS NOT NULL AND pppoe_user <> '') AS has_pppoe_user,
               (pppoe_pass IS NOT NULL AND pppoe_pass <> '') AS has_pppoe_pass,
               (contato_operadora IS NOT NULL AND contato_operadora <> '') AS has_contato_operadora,
               (telefone_reparo IS NOT NULL AND telefone_reparo <> '') AS has_telefone_reparo
        FROM links
        WHERE id_link = %s
        """,
        (id_link,),
    )


def find_link_id_by_ip_host(ip_address: str, *, exclude_id: int | None = None) -> int | None:
    """
    Compara só o host (sem /prefixo): 10.0.0.1/24 ≡ 10.0.0.1.
    O app envia o IPv4 canônico (core.utils.network.canonicalize_ipv4).
    """
    if not ip_address:
        return None
    if exclude_id is None:
        row = _one(
            """
            SELECT id_link FROM links
            WHERE SUBSTRING_INDEX(ip_address, '/', 1) = %s
            LIMIT 1
            """,
            (ip_address,),
        )
    else:
        row = _one(
            """
            SELECT id_link FROM links
            WHERE SUBSTRING_INDEX(ip_address, '/', 1) = %s AND id_link <> %s
            LIMIT 1
            """,
            (ip_address, exclude_id),
        )
    return int(row["id_link"]) if row else None


def find_link_id_by_id_vgr_link(id_vgr_link: str, *, exclude_id: int | None = None) -> int | None:
    if not id_vgr_link:
        return None
    if exclude_id is None:
        row = _one(
            "SELECT id_link FROM links WHERE id_vgr_link = %s LIMIT 1",
            (id_vgr_link,),
        )
    else:
        row = _one(
            """
            SELECT id_link FROM links
            WHERE id_vgr_link = %s AND id_link <> %s
            LIMIT 1
            """,
            (id_vgr_link, exclude_id),
        )
    return int(row["id_link"]) if row else None


def find_link_id_by_designador_operadora(
    designador: str, operadora: str | None, *, exclude_id: int | None = None
) -> int | None:
    if not designador:
        return None
    if exclude_id is None:
        row = _one(
            """
            SELECT id_link FROM links
            WHERE designador = %s AND operadora <=> %s
            LIMIT 1
            """,
            (designador, operadora),
        )
    else:
        row = _one(
            """
            SELECT id_link FROM links
            WHERE designador = %s AND operadora <=> %s AND id_link <> %s
            LIMIT 1
            """,
            (designador, operadora, exclude_id),
        )
    return int(row["id_link"]) if row else None


def create_link(data: dict[str, Any]) -> int:
    from core.security.encryption import encrypt_text

    def _enc(key: str):
        if data.get(f"_set_{key}"):
            return encrypt_text(data.get(key))
        return None

    last_id, _ = _exec(
        """
        INSERT INTO links (
          id_unidade, id_equipamento, tipo_link, modo_conexao, ordem, id_vgr_link,
          identificador, designador, ip_address, mascara, gateway, subrede, vlan,
          velocidade, operadora, contato_operadora, telefone_reparo,
          pppoe_user, pppoe_pass, range_start, range_end, ativo
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        """,
        (
            data["id_unidade"],
            data.get("id_equipamento"),
            data["tipo_link"],
            data.get("modo_conexao"),
            data.get("ordem"),
            data.get("id_vgr_link"),
            data.get("identificador"),
            data.get("designador"),
            data.get("ip_address"),
            data.get("mascara"),
            data.get("gateway"),
            data.get("subrede"),
            data.get("vlan"),
            data.get("velocidade"),
            data.get("operadora"),
            _enc("contato_operadora"),
            _enc("telefone_reparo"),
            _enc("pppoe_user"),
            _enc("pppoe_pass"),
            data.get("range_start"),
            data.get("range_end"),
            int(data.get("ativo", 1)),
        ),
    )
    if not last_id:
        raise RuntimeError("insert_link_sem_id")
    return last_id


def update_link(id_link: int, data: dict[str, Any]) -> bool:
    from core.security.encryption import encrypt_text

    # Base update sem secrets; aplica secrets só quando _set_*
    _, n = _exec(
        """
        UPDATE links SET
          id_unidade = %s, id_equipamento = %s, tipo_link = %s, modo_conexao = %s,
          ordem = %s, id_vgr_link = %s, identificador = %s, designador = %s,
          ip_address = %s, mascara = %s, gateway = %s, subrede = %s, vlan = %s,
          velocidade = %s, operadora = %s, range_start = %s, range_end = %s
        WHERE id_link = %s
        """,
        (
            data["id_unidade"],
            data.get("id_equipamento"),
            data["tipo_link"],
            data.get("modo_conexao"),
            data.get("ordem"),
            data.get("id_vgr_link"),
            data.get("identificador"),
            data.get("designador"),
            data.get("ip_address"),
            data.get("mascara"),
            data.get("gateway"),
            data.get("subrede"),
            data.get("vlan"),
            data.get("velocidade"),
            data.get("operadora"),
            data.get("range_start"),
            data.get("range_end"),
            id_link,
        ),
    )
    changed = n > 0
    # Colunas whitelist — nunca interpolar input do usuário no nome da coluna.
    for col in ("contato_operadora", "telefone_reparo", "pppoe_user", "pppoe_pass"):
        if data.get(f"_set_{col}"):
            _, ns = _exec(
                f"UPDATE links SET {col} = %s WHERE id_link = %s",
                (encrypt_text(data.get(col)), id_link),
            )
            changed = changed or ns > 0
    return changed


def set_link_ativo(id_link: int, ativo: int) -> bool:
    _, n = _exec(
        "UPDATE links SET ativo = %s WHERE id_link = %s",
        (1 if int(ativo) else 0, id_link),
    )
    return n > 0