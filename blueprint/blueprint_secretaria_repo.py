"""CRUD + load do catálogo prodesp_blueprint_secretaria (admin + cache runtime)."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from prodesp.prodesp.blueprint.blueprint_catalog import (
    BlueprintSecretariaRule,
    StaticCatalog,
    invalidate_catalog_cache,
    normalize_acronimo,
    parse_aliases_field,
    rule_from_row,
    rule_to_public_dict,
    set_db_catalog_loader,
    validate_acronimo_token,
    validate_dhcp_octeto,
    validate_layout,
    validate_rede_regra,
    validate_template,
)

_TABLE = "prodesp_blueprint_secretaria"
_ALIAS = "prodesp_blueprint_secretaria_alias"

# Colunas auditadas em `historico` (1 linha/campo; quem = current_user no registrar_log).
_AUDIT_FIELDS = (
    "acronimo",
    "nome_exibicao",
    "ativo",
    "device_blueprint_template",
    "layout_csv",
    "rede_lan_regra",
    "aplica_sufixo_lan_dinamico",
    "dhcp_lan_start_octeto",
    "dhcp_lan_end_octeto",
    "emite_dhcp_server_1",
    "legado_omitir_dhcp_server",
    "mostrar_em_hint_ui",
    "observacao",
    "aliases",
)


def _aliases_audit_str(aliases: Any) -> str:
    if not aliases:
        return ""
    if isinstance(aliases, str):
        parts = [p.strip() for p in aliases.replace(";", ",").split(",") if p.strip()]
    else:
        parts = [str(a).strip() for a in aliases if str(a).strip()]
    return ",".join(sorted({normalize_acronimo(a) for a in parts if a}))


def _audit_map_from_parsed(row: Mapping[str, Any]) -> dict[str, Any]:
    """Mapa de auditoria a partir do dict de parse_payload."""
    return {
        "acronimo": row.get("acronimo") or "",
        "nome_exibicao": row.get("nome_exibicao") or "",
        "ativo": int(row.get("ativo") or 0),
        "device_blueprint_template": row.get("device_blueprint_template") or "",
        "layout_csv": row.get("layout_csv") or "",
        "rede_lan_regra": row.get("rede_lan_regra") or "",
        "aplica_sufixo_lan_dinamico": int(row.get("aplica_sufixo_lan_dinamico") or 0),
        "dhcp_lan_start_octeto": row.get("dhcp_lan_start_octeto") or "",
        "dhcp_lan_end_octeto": row.get("dhcp_lan_end_octeto") or "",
        "emite_dhcp_server_1": int(row.get("emite_dhcp_server_1") or 0),
        "legado_omitir_dhcp_server": int(row.get("legado_omitir_dhcp_server") or 0),
        "mostrar_em_hint_ui": int(row.get("mostrar_em_hint_ui") or 0),
        "observacao": row.get("observacao") or "",
        "aliases": _aliases_audit_str(row.get("aliases")),
    }


def _audit_map_from_rule(rule: BlueprintSecretariaRule) -> dict[str, Any]:
    return {
        "acronimo": rule.acronimo or "",
        "nome_exibicao": rule.nome_exibicao or "",
        "ativo": 1 if rule.ativo else 0,
        "device_blueprint_template": rule.device_blueprint_template or "",
        "layout_csv": rule.layout_csv or "",
        "rede_lan_regra": rule.rede_lan_regra or "",
        "aplica_sufixo_lan_dinamico": 1 if rule.aplica_sufixo_lan_dinamico else 0,
        "dhcp_lan_start_octeto": rule.dhcp_lan_start_octeto or "",
        "dhcp_lan_end_octeto": rule.dhcp_lan_end_octeto or "",
        "emite_dhcp_server_1": 1 if rule.emite_dhcp_server_1 else 0,
        "legado_omitir_dhcp_server": 1 if rule.legado_omitir_dhcp_server else 0,
        "mostrar_em_hint_ui": 1 if rule.mostrar_em_hint_ui else 0,
        "observacao": rule.observacao or "",
        "aliases": _aliases_audit_str(rule.aliases),
    }


def _write_historico(
    conn,
    sec_id: int,
    old_map: Mapping[str, Any],
    new_map: Mapping[str, Any],
    *,
    operacao: str = "UPDATE",
) -> None:
    """Persiste diff em historico na mesma conexão (commit do chamador)."""
    if conn is None:
        return
    from prodesp.prodesp.admin_inventory import (
        collect_field_changes,
        registrar_field_changes,
        snapshot_field_changes_delete,
    )

    if operacao == "DELETE":
        changes = snapshot_field_changes_delete(old_map, _AUDIT_FIELDS)
        registrar_field_changes(
            conn, _TABLE, int(sec_id), changes, operacao="DELETE"
        )
        return
    if operacao == "INSERT":
        changes = collect_field_changes({}, dict(new_map))
        registrar_field_changes(
            conn, _TABLE, int(sec_id), changes, operacao="INSERT"
        )
        return
    changes = collect_field_changes(old_map, new_map)
    registrar_field_changes(conn, _TABLE, int(sec_id), changes, operacao="UPDATE")


def ensure_db_loader_registered(get_connection) -> None:
    """Registra loader que usa a factory de conexão do app PRODESP."""

    def _load() -> StaticCatalog:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        try:
            rules = load_all_rules(cur)
            return StaticCatalog(rules)
        finally:
            cur.close()
            conn.close()

    set_db_catalog_loader(_load)


def load_all_rules(cursor) -> list[BlueprintSecretariaRule]:
    cursor.execute(
        f"""
        SELECT id, acronimo, nome_exibicao, ativo, device_blueprint_template,
               layout_csv, rede_lan_regra, aplica_sufixo_lan_dinamico,
               dhcp_lan_start_octeto, dhcp_lan_end_octeto, emite_dhcp_server_1,
               legado_omitir_dhcp_server, mostrar_em_hint_ui, observacao,
               updated_at, updated_by
        FROM {_TABLE}
        ORDER BY acronimo
        """
    )
    rows = cursor.fetchall() or []
    if not rows:
        return []
    ids = [int(r["id"]) for r in rows]
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(
        f"SELECT alias, secretaria_id FROM {_ALIAS} WHERE secretaria_id IN ({placeholders})",
        tuple(ids),
    )
    alias_rows = cursor.fetchall() or []
    by_id: dict[int, list[str]] = {i: [] for i in ids}
    for ar in alias_rows:
        sid = int(ar["secretaria_id"])
        by_id.setdefault(sid, []).append(str(ar["alias"]))
    return [rule_from_row(r, by_id.get(int(r["id"]), [])) for r in rows]


def get_rule_by_id(cursor, sec_id: int) -> Optional[BlueprintSecretariaRule]:
    cursor.execute(
        f"""
        SELECT id, acronimo, nome_exibicao, ativo, device_blueprint_template,
               layout_csv, rede_lan_regra, aplica_sufixo_lan_dinamico,
               dhcp_lan_start_octeto, dhcp_lan_end_octeto, emite_dhcp_server_1,
               legado_omitir_dhcp_server, mostrar_em_hint_ui, observacao,
               updated_at, updated_by
        FROM {_TABLE} WHERE id = %s
        """,
        (int(sec_id),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    cursor.execute(
        f"SELECT alias FROM {_ALIAS} WHERE secretaria_id = %s ORDER BY alias",
        (int(sec_id),),
    )
    aliases = [str(r["alias"]) for r in (cursor.fetchall() or [])]
    return rule_from_row(row, aliases)


def list_for_datatable(cursor) -> dict[str, Any]:
    """Payload client DataTables (lista completa admin)."""
    rules = load_all_rules(cursor)
    data = [rule_to_public_dict(r) for r in rules]
    return {
        "success": True,
        "data": data,
        "recordsTotal": len(data),
        "recordsFiltered": len(data),
    }


def _boolish(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "sim", "yes", "on"):
        return True
    if s in ("0", "false", "nao", "não", "no", "off", ""):
        return False
    return bool(val)


def parse_payload(payload: Mapping[str, Any], *, is_create: bool) -> tuple[Optional[dict], Optional[str]]:
    acr_raw = payload.get("acronimo")
    acr, err = validate_acronimo_token(acr_raw if acr_raw is not None else "")
    if err:
        return None, err
    tpl, err = validate_template(payload.get("device_blueprint_template"))
    if err:
        return None, err
    layout, err = validate_layout(payload.get("layout_csv"))
    if err:
        return None, err
    rede, err = validate_rede_regra(payload.get("rede_lan_regra"))
    if err:
        return None, err
    d_start, err = validate_dhcp_octeto(payload.get("dhcp_lan_start_octeto"), "DHCP start")
    if err:
        return None, err
    d_end, err = validate_dhcp_octeto(payload.get("dhcp_lan_end_octeto"), "DHCP end")
    if err:
        return None, err
    if (d_start is None) ^ (d_end is None):
        return None, "DHCP start e end devem ser informados juntos (ou ambos vazios)."
    aliases, err = parse_aliases_field(payload.get("aliases"))
    if err:
        return None, err
    if acr in aliases:
        return None, "Alias não pode repetir o acrônimo canônico."
    nome = payload.get("nome_exibicao")
    nome_s = str(nome).strip() if nome not in (None, "") else acr
    if len(nome_s) > 120:
        return None, "nome_exibicao excede 120 caracteres."
    obs = payload.get("observacao")
    obs_s = str(obs).strip() if obs not in (None, "") else None
    if obs_s and len(obs_s) > 500:
        return None, "observacao excede 500 caracteres."

    row = {
        "acronimo": acr,
        "nome_exibicao": nome_s,
        "ativo": 1 if _boolish(payload.get("ativo"), True) else 0,
        "device_blueprint_template": tpl,
        "layout_csv": layout,
        "rede_lan_regra": rede,
        "aplica_sufixo_lan_dinamico": 1 if _boolish(payload.get("aplica_sufixo_lan_dinamico"), True) else 0,
        "dhcp_lan_start_octeto": d_start,
        "dhcp_lan_end_octeto": d_end,
        "emite_dhcp_server_1": 1 if _boolish(payload.get("emite_dhcp_server_1"), False) else 0,
        "legado_omitir_dhcp_server": 1 if _boolish(payload.get("legado_omitir_dhcp_server"), False) else 0,
        "mostrar_em_hint_ui": 1 if _boolish(payload.get("mostrar_em_hint_ui"), True) else 0,
        "observacao": obs_s,
        "aliases": aliases,
    }
    if is_create and not row["acronimo"]:
        return None, "acrônimo obrigatório."
    return row, None


def _collision_error(cursor, acronimo: str, aliases: list[str], exclude_id: Optional[int]) -> Optional[str]:
    keys = [acronimo] + list(aliases)
    for key in keys:
        # canônico em secretaria
        if exclude_id is None:
            cursor.execute(f"SELECT id FROM {_TABLE} WHERE acronimo = %s LIMIT 1", (key,))
        else:
            cursor.execute(
                f"SELECT id FROM {_TABLE} WHERE acronimo = %s AND id <> %s LIMIT 1",
                (key, int(exclude_id)),
            )
        if cursor.fetchone():
            return f"Acrônimo/alias '{key}' já existe como canônico de outra secretaria."
        # alias table
        if exclude_id is None:
            cursor.execute(f"SELECT secretaria_id FROM {_ALIAS} WHERE alias = %s LIMIT 1", (key,))
        else:
            cursor.execute(
                f"SELECT secretaria_id FROM {_ALIAS} WHERE alias = %s AND secretaria_id <> %s LIMIT 1",
                (key, int(exclude_id)),
            )
        hit = cursor.fetchone()
        if hit:
            return f"Acrônimo/alias '{key}' já está em uso."
    return None


def create_secretaria(
    cursor,
    payload: Mapping[str, Any],
    *,
    updated_by: str = "",
    conn=None,
) -> tuple[Optional[int], Optional[str]]:
    row, err = parse_payload(payload, is_create=True)
    if err or not row:
        return None, err or "payload inválido"
    err = _collision_error(cursor, row["acronimo"], row["aliases"], None)
    if err:
        return None, err
    cursor.execute(
        f"""
        INSERT INTO {_TABLE} (
          acronimo, nome_exibicao, ativo, device_blueprint_template, layout_csv,
          rede_lan_regra, aplica_sufixo_lan_dinamico, dhcp_lan_start_octeto,
          dhcp_lan_end_octeto, emite_dhcp_server_1, legado_omitir_dhcp_server,
          mostrar_em_hint_ui, observacao, updated_by
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            row["acronimo"],
            row["nome_exibicao"],
            row["ativo"],
            row["device_blueprint_template"],
            row["layout_csv"],
            row["rede_lan_regra"],
            row["aplica_sufixo_lan_dinamico"],
            row["dhcp_lan_start_octeto"],
            row["dhcp_lan_end_octeto"],
            row["emite_dhcp_server_1"],
            row["legado_omitir_dhcp_server"],
            row["mostrar_em_hint_ui"],
            row["observacao"],
            (updated_by or "")[:120] or None,
        ),
    )
    new_id = int(cursor.lastrowid)
    _replace_aliases(cursor, new_id, row["aliases"])
    _write_historico(
        conn,
        new_id,
        {},
        _audit_map_from_parsed(row),
        operacao="INSERT",
    )
    invalidate_catalog_cache()
    return new_id, None


def update_secretaria(
    cursor,
    sec_id: int,
    payload: Mapping[str, Any],
    *,
    updated_by: str = "",
    conn=None,
) -> tuple[bool, Optional[str]]:
    existing = get_rule_by_id(cursor, sec_id)
    if not existing:
        return False, "Secretaria não encontrada."
    row, err = parse_payload(payload, is_create=False)
    if err or not row:
        return False, err or "payload inválido"
    err = _collision_error(cursor, row["acronimo"], row["aliases"], int(sec_id))
    if err:
        return False, err
    old_map = _audit_map_from_rule(existing)
    cursor.execute(
        f"""
        UPDATE {_TABLE} SET
          acronimo=%s, nome_exibicao=%s, ativo=%s, device_blueprint_template=%s,
          layout_csv=%s, rede_lan_regra=%s, aplica_sufixo_lan_dinamico=%s,
          dhcp_lan_start_octeto=%s, dhcp_lan_end_octeto=%s, emite_dhcp_server_1=%s,
          legado_omitir_dhcp_server=%s, mostrar_em_hint_ui=%s, observacao=%s,
          updated_by=%s
        WHERE id=%s
        """,
        (
            row["acronimo"],
            row["nome_exibicao"],
            row["ativo"],
            row["device_blueprint_template"],
            row["layout_csv"],
            row["rede_lan_regra"],
            row["aplica_sufixo_lan_dinamico"],
            row["dhcp_lan_start_octeto"],
            row["dhcp_lan_end_octeto"],
            row["emite_dhcp_server_1"],
            row["legado_omitir_dhcp_server"],
            row["mostrar_em_hint_ui"],
            row["observacao"],
            (updated_by or "")[:120] or None,
            int(sec_id),
        ),
    )
    cursor.execute(f"DELETE FROM {_ALIAS} WHERE secretaria_id = %s", (int(sec_id),))
    _replace_aliases(cursor, int(sec_id), row["aliases"])
    _write_historico(
        conn,
        int(sec_id),
        old_map,
        _audit_map_from_parsed(row),
        operacao="UPDATE",
    )
    invalidate_catalog_cache()
    return True, None


def soft_deactivate(
    cursor, sec_id: int, *, updated_by: str = "", conn=None
) -> tuple[bool, Optional[str]]:
    existing = get_rule_by_id(cursor, sec_id)
    if not existing:
        return False, "Secretaria não encontrada."
    old_map = _audit_map_from_rule(existing)
    cursor.execute(
        f"UPDATE {_TABLE} SET ativo=0, updated_by=%s WHERE id=%s",
        ((updated_by or "")[:120] or None, int(sec_id)),
    )
    new_map = dict(old_map)
    new_map["ativo"] = 0
    _write_historico(conn, int(sec_id), old_map, new_map, operacao="UPDATE")
    invalidate_catalog_cache()
    return True, None


def delete_hard(cursor, sec_id: int, *, conn=None) -> tuple[bool, Optional[str]]:
    existing = get_rule_by_id(cursor, sec_id)
    if not existing:
        return False, "Secretaria não encontrada."
    old_map = _audit_map_from_rule(existing)
    # Histórico antes do DELETE (snapshot com valor antigo → vazio)
    _write_historico(conn, int(sec_id), old_map, {}, operacao="DELETE")
    cursor.execute(f"DELETE FROM {_TABLE} WHERE id=%s", (int(sec_id),))
    invalidate_catalog_cache()
    return True, None


def _replace_aliases(cursor, sec_id: int, aliases: list[str]) -> None:
    for a in aliases:
        cursor.execute(
            f"INSERT INTO {_ALIAS} (alias, secretaria_id) VALUES (%s, %s)",
            (normalize_acronimo(a), int(sec_id)),
        )


def table_exists(cursor) -> bool:
    try:
        cursor.execute(f"SELECT 1 FROM {_TABLE} LIMIT 1")
        cursor.fetchone()
        return True
    except Exception:
        return False
