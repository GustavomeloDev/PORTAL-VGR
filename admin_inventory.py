"""Inventário admin: listagem/CRUD/transferência de equipamentos e links (global).

Rotas usam ``_prodesp_require_admin_api``. SQL parametrizado; ordenação/busca com whitelist.
"""
from __future__ import annotations

import threading
import unicodedata
from datetime import date, datetime, timedelta, time
from typing import Any, Mapping, Optional

from .db_field_limits import validate_equipamento_fields, validate_link_fields
from .blueprint.link_vivo_rules import normalize_link_api_payload
from .blueprint.prodesp_equipment import (
    DEFAULT_MODELO_EQUIPAMENTO,
    SERIAL_MODEL_FRAGMENTS_ORDERED,
    infer_modelo_equipamento_from_serial,
)
from .blueprint.redundante_critico_rules import applies_redundante_critico
from .conclusao_equipamento_rules import (
    serial_fortinet_valido,
    validate_serial_fortinet_format,
)
from .data_revision import attach_to_payload, current_revision
from .link_format_rules import (
    is_designador_link_fora_padrao,
    is_id_vgr_link_fora_padrao,
)
from .link_uniqueness_rules import find_link_uniqueness_errors
from .sensitive_fields_crypto import (
    decrypt_sensitive_row_inplace,
    encrypt_sensitive_db_column,
)

# Modo client (PortalDt/login): carrega o inventário no browser — busca global e
# searchList do ColumnControl usam o dataset completo (não só a página atual).
_CLIENT_ROW_CAP = 25000

MSG_UNIDADE_CONFLITO = (
    "A unidade deste registro foi alterada por outro administrador. "
    "Atualize a lista e tente novamente."
)


def _norm_unidade_id(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        n = int(val)
    except (TypeError, ValueError):
        return None
    return None if n == 0 else n


def check_expected_unidade(current_uid: Any, payload: Mapping[str, Any] | None) -> Optional[str]:
    """Se o cliente enviou ``expected_id_unidade``, exige igualdade com o FK atual (anti last-write-wins)."""
    if not isinstance(payload, Mapping) or "expected_id_unidade" not in payload:
        return None
    if _norm_unidade_id(current_uid) != _norm_unidade_id(payload.get("expected_id_unidade")):
        return MSG_UNIDADE_CONFLITO
    return None


def is_unidade_conflito_msg(msg: Optional[str]) -> bool:
    return bool(msg) and msg == MSG_UNIDADE_CONFLITO


# (coluna_db, valor_antigo, valor_novo) — auditoria 1 linha por campo (padrão blueprint)
FieldChange = tuple[str, Any, Any]


def _hist_norm(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _hist_values_differ(old: Any, new: Any) -> bool:
    return _hist_norm(old) != _hist_norm(new)


def _audit_hist_value(col: str, value: Any) -> Any:
    """Valor seguro para a trilha: senha PPPoE nunca em claro."""
    if col == "pppoe_pass_links":
        return "(definida)" if _hist_norm(value) else ""
    if value is None:
        return None
    return value


def _audit_hist_pair(col: str, old: Any, new: Any) -> Optional[tuple[Any, Any]]:
    """Par (antigo, novo) para log, ou None se não houver mudança auditável."""
    if not _hist_values_differ(old, new):
        return None
    if col == "pppoe_pass_links":
        had = bool(_hist_norm(old))
        has = bool(_hist_norm(new))
        if had and has:
            return "(definida)", "(redefinida)"
        if had and not has:
            return "(definida)", None
        if not had and has:
            return None, "(definida)"
        return None
    aud_old = _audit_hist_value(col, old)
    aud_new = _audit_hist_value(col, new)
    if _hist_norm(aud_old) == "" and _hist_norm(aud_new) == "":
        return None
    return (
        None if _hist_norm(aud_old) == "" else aud_old,
        None if _hist_norm(aud_new) == "" else aud_new,
    )


def collect_field_changes(
    old_map: Mapping[str, Any], new_map: Mapping[str, Any]
) -> list[FieldChange]:
    """Diff coluna a coluna (chaves de new_map); ignora iguais e senha sem mudança real."""
    out: list[FieldChange] = []
    for col, new_v in new_map.items():
        pair = _audit_hist_pair(col, old_map.get(col), new_v)
        if pair is None:
            continue
        out.append((col, pair[0], pair[1]))
    return out


_LINK_ENCRYPT_COLS: frozenset[str] = frozenset(
    {"pppoe_user_links", "pppoe_pass_links"}
)


def apply_partial_update(
    cursor,
    *,
    table: str,
    pk_column: str,
    pk_value: int,
    old_map: Mapping[str, Any],
    new_map: Mapping[str, Any],
    encrypt_cols: frozenset[str] | None = None,
) -> list[FieldChange]:
    """``UPDATE`` só colunas com diff real. Retorna changes para histórico (vazio = noop).

    Nomes de tabela/coluna vêm do código (mapa controlado), não de input do cliente.
    """
    changes = collect_field_changes(old_map, new_map)
    if not changes:
        return []
    enc = encrypt_cols or frozenset()
    cols = [c for c, _, _ in changes]
    set_sql = ", ".join(f"`{c}` = %s" for c in cols)
    params: list[Any] = []
    for c in cols:
        v = new_map.get(c)
        if c in enc:
            v = encrypt_sensitive_db_column(c, v)
        params.append(v)
    params.append(pk_value)
    cursor.execute(
        f"UPDATE `{table}` SET {set_sql} WHERE `{pk_column}` = %s",
        tuple(params),
    )
    return changes


def snapshot_field_changes_delete(row: Mapping[str, Any], cols: tuple[str, ...]) -> list[FieldChange]:
    """Snapshot pré-DELETE: uma linha por coluna com valor (senha mascarada)."""
    out: list[FieldChange] = []
    for col in cols:
        pair = _audit_hist_pair(col, row.get(col), None)
        if pair is None:
            continue
        out.append((col, pair[0], pair[1]))
    return out


def registrar_field_changes(
    conn,
    tabela: str,
    id_registro: int,
    changes: list[FieldChange],
    *,
    operacao: str = "UPDATE",
) -> None:
    """Grava N linhas em historico (1 por campo). Commit fica com o chamador."""
    if not changes:
        return
    from prodesp.prodesp.historico import registrar_log

    for col, old_v, new_v in changes:
        op = operacao
        if old_v is not None and (new_v is None or _hist_norm(new_v) == ""):
            op = "DELETE"
        elif (old_v is None or _hist_norm(old_v) == "") and new_v is not None:
            op = "INSERT"
        registrar_log(conn, tabela, id_registro, col, old_v, new_v, op)


_EQ_AUDIT_COLS: tuple[str, ...] = (
    "id_unidades_equipamentos",
    "modelo_equipamentos",
    "serial_equipamentos",
    "versao_equipamentos",
    "descricao_equipamentos",
    "mac_equipamentos",
    "licenca_equipamentos",
)

_LINK_AUDIT_COLS: tuple[str, ...] = (
    "id_unidades_links",
    "id_vgr_links",
    "designador_links",
    "tipo_links",
    "operadora_links",
    "vlan_links",
    "ip_wan_links",
    "redundante_critico_links",
    "ip_gateway_links",
    "ip_mascara_links",
    "velocidade_links",
    "pppoe_user_links",
    "pppoe_pass_links",
)


def _is_client_mode(args: Mapping[str, Any]) -> bool:
    return str(args.get("mode") or "").strip().lower() in ("client", "1", "true", "all")


# Modelos aceitos no admin (select) — alinhado aos modais de atendimento + fragments do serial
_ALLOWED_MODELOS_EQUIP: frozenset[str] = frozenset(
    {label for _, label in SERIAL_MODEL_FRAGMENTS_ORDERED}
    | {
        "FortiGate 3200F",
        "FortiGate 3700F",
        "FortiGate 600F",
        "FortiSwitch 2048F",
        DEFAULT_MODELO_EQUIPAMENTO,
    }
)

_AUTO_DESC_FIREWALL = frozenset(
    {
        "FortiGate 40F",
        "FortiGate 60F",
        "FortiGate 120G",
        "FortiGate 900G",
        "FortiGate 3200F",
        "FortiGate 3700F",
        "FortiGate 600F",
    }
)


def resolve_modelo_equipamento(serial: str, requested: Any = None) -> tuple[str, Optional[str]]:
    """Modelo vem do serial quando o serial contém fragmento conhecido; senão só whitelist."""
    s = (serial or "").upper().replace(" ", "")
    if s:
        for fragment, label in SERIAL_MODEL_FRAGMENTS_ORDERED:
            if fragment in s:
                return label, None
    req = str(requested or "").strip()
    if not req:
        return DEFAULT_MODELO_EQUIPAMENTO, None
    if req not in _ALLOWED_MODELOS_EQUIP:
        return "", (
            f"Modelo «{req}» não permitido. Use o serial Fortinet (mapeia o modelo) "
            "ou selecione um modelo da lista oficial."
        )
    return req, None


def resolve_descricao_equipamento(modelo: str, requested: Any = None) -> str:
    """Descrição automática por modelo (como na fila); ignora texto livre arbitrário."""
    m = str(modelo or "").strip()
    if m in _AUTO_DESC_FIREWALL:
        return "Firewall - Stand Alone"
    if m == "FortiSwitch 2048F":
        return "Switch"
    req = str(requested or "").strip()
    return req[:120] if req else ""


# Colunas ordenáveis (índice DataTables → expressão SQL)
EQ_ORDER_WHITELIST: tuple[str, ...] = (
    "e.id_equipamentos",
    "e.serial_equipamentos",
    "e.modelo_equipamentos",
    "e.versao_equipamentos",
    "u.id_vgr_unidades",
    "u.hostname_unidades",
    "u.acronimo_unidades",
    "u.nome_unidades",
    "_att.status_atendimentos",
    "_att.analista_caderno_teste_atendimentos",
)

LINK_ORDER_WHITELIST: tuple[str, ...] = (
    "l.id_link",
    "l.tipo_links",
    "l.operadora_links",
    "l.designador_links",
    "l.id_vgr_links",
    "l.ip_wan_links",
    "u.id_vgr_unidades",
    "u.hostname_unidades",
    "u.acronimo_unidades",
    "_att.status_atendimentos",
    "_att.analista_caderno_teste_atendimentos",
)


def _sql_join_ultimo_atendimento(unidade_fk_sql: str) -> str:
    """Último atendimento via MAX(id) — só para páginas server-side pequenas.

    Evitar no mode=client: o antigo GROUP_CONCAT em *toda* a tabela atendimentos
    chegava a ~60s na listagem admin de links.
    """
    return f"""
        LEFT JOIN atendimentos _att
          ON _att.id_atendimentos = (
            SELECT MAX(a2.id_atendimentos)
            FROM atendimentos a2
            WHERE a2.id_unidades_atendimentos = {unidade_fk_sql}
          )
    """


_SQL_ULTIMO_ATENDIMENTO_COLS = """
          COALESCE(_att.status_atendimentos, '') AS status_ultimo_atendimento,
          COALESCE(_att.analista_caderno_teste_atendimentos, '') AS analista_caderno_ultimo
"""

_ATT_MAP_CHUNK = 800

# Cache processo: listagem client-mode por revisão (invalida no bump).
_client_list_cache: dict[str, tuple[int, dict[str, Any]]] = {}
_client_list_lock = threading.Lock()


def _client_list_cache_get(kind: str, *, force: bool = False) -> Optional[dict[str, Any]]:
    if force:
        return None
    rev = current_revision()
    with _client_list_lock:
        hit = _client_list_cache.get(kind)
    if not hit or hit[0] != rev:
        return None
    payload = dict(hit[1])
    # Schema da listagem mudou → descarta (ex.: normalização versao).
    schema = payload.get("inventory_list_schema")
    if schema is not None and int(schema) != int(INVENTORY_LIST_SCHEMA):
        return None
    if kind == "equipamentos":
        for row in payload.get("data") or []:
            if isinstance(row, dict) and "versao" in row:
                row["versao"] = normalize_versao_equipamento(row.get("versao"))
    return payload


def _client_list_cache_put(kind: str, payload: dict[str, Any]) -> None:
    rev = current_revision()
    stored = {
        k: v
        for k, v in payload.items()
        if k not in ("data_revision", "server_time", "revision")
    }
    with _client_list_lock:
        _client_list_cache[kind] = (rev, stored)


def reset_client_list_cache_for_tests() -> None:
    with _client_list_lock:
        _client_list_cache.clear()


def _client_list_force_refresh(args: Mapping[str, Any]) -> bool:
    """force/nocache=1: ignora cache de listagem (Atualizar / bust após SQL offline)."""
    raw = args.get("force") if args.get("force") is not None else args.get("nocache")
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes")


def normalize_versao_equipamento(value: Any) -> str:
    """Remove prefixo «v» de versão FortiOS (v7.4.11 → 7.4.11)."""
    s = str(value or "").strip()
    if len(s) >= 2 and s[0] in "vV" and s[1].isdigit():
        return s[1:].strip()
    return s


def _unit_ids_from_rows(rows: list[Mapping[str, Any]]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for row in rows:
        uid = row.get("id_unidade")
        if uid in (None, "", 0, "0"):
            continue
        try:
            n = int(uid)
        except (TypeError, ValueError):
            continue
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _fetch_ultimo_atendimento_map(
    cursor, unit_ids: list[int]
) -> dict[int, tuple[str, str]]:
    """Mapa unidade → (status, analista) só para IDs da página — O(unidades da lista)."""
    result: dict[int, tuple[str, str]] = {}
    if not unit_ids:
        return result
    for i in range(0, len(unit_ids), _ATT_MAP_CHUNK):
        chunk = unit_ids[i : i + _ATT_MAP_CHUNK]
        placeholders = ",".join(["%s"] * len(chunk))
        cursor.execute(
            f"""
            SELECT
              a.id_unidades_atendimentos AS id_unidade,
              COALESCE(a.status_atendimentos, '') AS status_ultimo_atendimento,
              COALESCE(a.analista_caderno_teste_atendimentos, '') AS analista_caderno_ultimo
            FROM atendimentos a
            INNER JOIN (
              SELECT
                id_unidades_atendimentos AS _uid,
                MAX(id_atendimentos) AS _mid
              FROM atendimentos
              WHERE id_unidades_atendimentos IN ({placeholders})
              GROUP BY id_unidades_atendimentos
            ) _pick ON _pick._mid = a.id_atendimentos
            """,
            chunk,
        )
        for row in cursor.fetchall() or []:
            try:
                uid = int(row["id_unidade"])
            except (TypeError, ValueError, KeyError):
                continue
            result[uid] = (
                str(row.get("status_ultimo_atendimento") or ""),
                str(row.get("analista_caderno_ultimo") or ""),
            )
    return result


def _apply_ultimo_atendimento(
    rows: list[dict[str, Any]], att_map: dict[int, tuple[str, str]]
) -> None:
    for item in rows:
        uid = item.get("id_unidade")
        key: Optional[int] = None
        if uid not in (None, "", 0, "0"):
            try:
                key = int(uid)
            except (TypeError, ValueError):
                key = None
        st, an = att_map.get(key, ("", "")) if key is not None else ("", "")
        item["status_ultimo_atendimento"] = st
        item["analista_caderno_ultimo"] = an


# Versão do payload da listagem admin (invalida cache do browser quando sobe)
# 7 = columnControl value alinhado ao normalize do DataTables (acentos).
INVENTORY_LIST_SCHEMA = 8

# Opções searchList leves (baixa cardinalidade) — alta cardinalidade = lazy no browser.
_EQ_COLUMN_CONTROL_KEYS = (
    "modelo",
    "versao",
    "acronimo",
    "nome_unidade",
    "status_ultimo_atendimento",
    "analista_caderno_ultimo",
)
_LINK_COLUMN_CONTROL_KEYS = (
    "tipo",
    "operadora",
    "acronimo",
    "status_ultimo_atendimento",
    "analista_caderno_ultimo",
)
_CC_EMPTY_AS_DASH = frozenset(
    {"status_ultimo_atendimento", "analista_caderno_ultimo"}
)


def _dt_search_value(text: str) -> str:
    """Espelha DataTables ``_normalize(str, false)`` em ``ext.type.search``.

    O filtro client-side do ColumnControl compara ``values.includes(val)`` com
    ``_aFilterData``, que passa por esse normalize — sem isso, «Concluído»
    (opção) nunca casa com «Concluido» (filtro).
    """
    if not isinstance(text, str) or not text:
        return text
    nfd = unicodedata.normalize("NFD", text)
    if len(nfd) != len(text):
        return "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return text


def _build_column_control(
    rows: list[Mapping[str, Any]], keys: tuple[str, ...]
) -> dict[str, list[dict[str, str]]]:
    """Opções searchList: label (UI) + value (match do filtro DT). Sem HTML."""
    buckets: dict[str, dict[str, str]] = {k: {} for k in keys}
    for row in rows:
        for key in keys:
            raw = row.get(key)
            text = "" if raw is None else str(raw).strip()
            if key in _CC_EMPTY_AS_DASH:
                label = text or "—"
            else:
                label = text
            value = _dt_search_value(label)
            if value not in buckets[key]:
                buckets[key][value] = label
    out: dict[str, list[dict[str, str]]] = {}
    for key in keys:
        items = sorted(buckets[key].items(), key=lambda kv: kv[1].casefold())
        out[key] = [{"label": lab, "value": val} for val, lab in items]
    return out


def resolve_unidade_id(
    cursor,
    *,
    id_unidade: Any = None,
    id_vgr: Any = None,
) -> tuple[Optional[int], Optional[str]]:
    """Retorna (id_unidades, mensagem_erro)."""
    if id_unidade not in (None, ""):
        try:
            uid = int(id_unidade)
        except (TypeError, ValueError):
            return None, "ID da unidade inválido."
        cursor.execute(
            "SELECT id_unidades FROM unidades WHERE id_unidades = %s",
            (uid,),
        )
        row = cursor.fetchone()
        if not row:
            return None, "Unidade não encontrada."
        return uid, None

    vgr = str(id_vgr or "").strip()
    if not vgr:
        return None, "Informe id_unidade ou id_vgr da unidade destino."
    cursor.execute(
        "SELECT id_unidades FROM unidades WHERE id_vgr_unidades = %s",
        (vgr,),
    )
    row = cursor.fetchone()
    if not row:
        return None, f"Unidade com ID VGR '{vgr}' não encontrada."
    uid = row["id_unidades"] if isinstance(row, dict) else row[0]
    return int(uid), None


def _dt_args(args: Mapping[str, Any]) -> dict[str, Any]:
    def _int(name: str, default: int) -> int:
        try:
            return int(args.get(name, default) or default)
        except (TypeError, ValueError):
            return default

    search = ""
    raw = args.get("search[value]") or args.get("search") or ""
    if isinstance(raw, dict):
        search = str(raw.get("value") or "").strip()
    else:
        search = str(raw).strip()

    order_col = _int("order[0][column]", 0)
    order_dir = str(args.get("order[0][dir]") or "asc").lower()
    if order_dir not in ("asc", "desc"):
        order_dir = "asc"
    return {
        "draw": _int("draw", 1),
        "start": max(0, _int("start", 0)),
        "length": min(200, max(10, _int("length", 25))),
        "search": search,
        "order_col": order_col,
        "order_dir": order_dir,
    }


def _like_params(search: str, n: int) -> list[str]:
    term = f"%{search}%"
    return [term] * n


def _client_unchanged_payload(args: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Se mode=client e since_revision == revisão atual, evita reenviar o dataset."""
    if not _is_client_mode(args):
        return None
    raw = args.get("since_revision")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        since = int(raw)
    except (TypeError, ValueError):
        return None
    rev = current_revision()
    if since != rev:
        return None
    return attach_to_payload(
        {
            "success": True,
            "unchanged": True,
            "data": [],
            "recordsTotal": 0,
            "recordsFiltered": 0,
            "mode": "client",
            "inventory_list_schema": INVENTORY_LIST_SCHEMA,
        }
    )


# Flags «fora do padrão» — regras em link_format_rules (reexport p/ testes/KPIs).


def _apply_link_fora_flags(item: dict[str, Any]) -> dict[str, Any]:
    item["id_vgr_fora_padrao"] = 1 if is_id_vgr_link_fora_padrao(item.get("id_vgr_link")) else 0
    item["designador_fora_padrao"] = (
        1
        if is_designador_link_fora_padrao(item.get("designador"), item.get("operadora"))
        else 0
    )
    return item


def _equipamento_row_item(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    for k, v in list(item.items()):
        if v is None:
            item[k] = ""
    serial = item.get("serial") or ""
    item["fgt_padrao"] = 1 if serial_fortinet_valido(serial) else 0
    item["associado"] = 1 if item.get("id_unidade") not in ("", None, 0, "0") else 0
    if "versao" in item:
        item["versao"] = normalize_versao_equipamento(item.get("versao"))
    return item


def _equipamento_list_row_item(row: Mapping[str, Any]) -> dict[str, Any]:
    """Linha da grade admin — só colunas/KPIs visíveis (detalhe via GET /equipamentos/<id>)."""
    item = {
        "id": row.get("id"),
        "id_unidade": row.get("id_unidade"),
        "serial": row.get("serial") or "",
        "modelo": row.get("modelo") or "",
        "versao": normalize_versao_equipamento(row.get("versao")),
        "id_vgr": row.get("id_vgr") or "",
        "hostname": row.get("hostname") or "",
        "acronimo": row.get("acronimo") or "",
        "nome_unidade": row.get("nome_unidade") or "",
        "status_ultimo_atendimento": row.get("status_ultimo_atendimento") or "",
        "analista_caderno_ultimo": row.get("analista_caderno_ultimo") or "",
    }
    for k, v in list(item.items()):
        if v is None:
            item[k] = ""
    serial = item.get("serial") or ""
    item["fgt_padrao"] = 1 if serial_fortinet_valido(serial) else 0
    item["associado"] = 1 if item.get("id_unidade") not in ("", None, 0, "0") else 0
    return item


def _link_row_item(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    # Listagem: não traz ciphertext da senha (só flag) — evita decrypt em massa.
    pass_flag = item.pop("pppoe_pass_set_flag", None)
    decrypt_sensitive_row_inplace(item)
    user_plain = item.get("pppoe_user_links") or item.get("pppoe_user") or ""
    if pass_flag is None:
        pass_set = bool(item.get("pppoe_pass_links"))
    else:
        try:
            pass_set = int(pass_flag) == 1
        except (TypeError, ValueError):
            pass_set = bool(pass_flag)
    item["pppoe_user"] = user_plain
    item["pppoe_pass"] = "••••••" if pass_set else ""
    item["pppoe_pass_set"] = pass_set
    item.pop("pppoe_user_links", None)
    item.pop("pppoe_pass_links", None)
    for k, v in list(item.items()):
        if v is None:
            item[k] = ""
    item["associado"] = 1 if item.get("id_unidade") not in ("", None, 0, "0") else 0
    try:
        item["redundante_critico"] = int(item.get("redundante_critico") or 0)
    except (TypeError, ValueError):
        item["redundante_critico"] = 0
    return _apply_link_fora_flags(item)


def _link_list_row_item(row: Mapping[str, Any]) -> dict[str, Any]:
    """Linha da grade admin — sem PPPoE/decrypt (detalhe via GET /links/<id>)."""
    item = {
        "id": row.get("id"),
        "id_unidade": row.get("id_unidade"),
        "tipo": row.get("tipo") or "",
        "operadora": row.get("operadora") or "",
        "designador": row.get("designador") or "",
        "id_vgr_link": row.get("id_vgr_link") or "",
        "ip_wan": row.get("ip_wan") or "",
        "id_vgr": row.get("id_vgr") or "",
        "hostname": row.get("hostname") or "",
        "acronimo": row.get("acronimo") or "",
        "status_ultimo_atendimento": row.get("status_ultimo_atendimento") or "",
        "analista_caderno_ultimo": row.get("analista_caderno_ultimo") or "",
        "redundante_critico": 0,
    }
    for k, v in list(item.items()):
        if v is None:
            item[k] = ""
    item["associado"] = 1 if item.get("id_unidade") not in ("", None, 0, "0") else 0
    try:
        item["redundante_critico"] = int(row.get("redundante_critico") or 0)
    except (TypeError, ValueError):
        item["redundante_critico"] = 0
    return _apply_link_fora_flags(item)


def parse_unidade_ids_param(raw: Any, *, max_ids: int = 100) -> list[int]:
    """Whitelist de IDs inteiros (API de enrich da página visível)."""
    if raw is None or raw == "":
        return []
    parts: list[str]
    if isinstance(raw, (list, tuple)):
        parts = [str(x) for x in raw]
    else:
        parts = str(raw).replace(";", ",").split(",")
    out: list[int] = []
    seen: set[int] = set()
    for p in parts:
        p = p.strip()
        if not p:
            continue
        try:
            n = int(p)
        except (TypeError, ValueError):
            continue
        if n <= 0 or n in seen:
            continue
        seen.add(n)
        out.append(n)
        if len(out) >= max_ids:
            break
    return out


def ultimo_atendimento_map_payload(cursor, raw_ids: Any) -> dict[str, Any]:
    """Mapa id_unidade → status/analista (máx. 100) para enrich da página DataTables."""
    ids = parse_unidade_ids_param(raw_ids, max_ids=100)
    att = _fetch_ultimo_atendimento_map(cursor, ids)
    mapped = {
        str(uid): {"status": st, "analista": an}
        for uid, (st, an) in att.items()
    }
    return {"success": True, "map": mapped, "count": len(mapped)}


def search_unidades(cursor, q: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Busca unidades por id_vgr / acrônimo / hostname / nome (admin typeahead)."""
    term = str(q or "").strip()
    if len(term) < 2:
        return []
    try:
        lim = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        lim = 20
    like = f"%{term}%"
    cursor.execute(
        """
        SELECT
          id_unidades AS id_unidade,
          id_vgr_unidades AS id_vgr,
          COALESCE(acronimo_unidades, '') AS acronimo,
          COALESCE(hostname_unidades, '') AS hostname,
          COALESCE(nome_unidades, '') AS nome
        FROM unidades
        WHERE id_vgr_unidades LIKE %s
           OR acronimo_unidades LIKE %s
           OR hostname_unidades LIKE %s
           OR nome_unidades LIKE %s
        ORDER BY
          CASE WHEN id_vgr_unidades = %s THEN 0
               WHEN id_vgr_unidades LIKE %s THEN 1
               ELSE 2 END,
          nome_unidades
        LIMIT %s
        """,
        (like, like, like, like, term, f"{term}%", lim),
    )
    rows = []
    for row in cursor.fetchall() or []:
        item = dict(row)
        for k, v in list(item.items()):
            if v is None:
                item[k] = ""
        item["label"] = " · ".join(
            p
            for p in (
                str(item.get("id_vgr") or "").strip(),
                str(item.get("acronimo") or "").strip(),
                str(item.get("hostname") or "").strip(),
                str(item.get("nome") or "").strip(),
            )
            if p
        )
        rows.append(item)
    return rows


def _format_atendimento_ctx_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normaliza tipos MySQL (date/datetime/timedelta/time) para JSON."""
    item = dict(row)
    for k, v in list(item.items()):
        if v is None:
            item[k] = ""
        elif isinstance(v, timedelta):
            # TIME do MySQL chega como timedelta via connector
            total = int(v.total_seconds())
            if total < 0:
                total = 0
            hh, rem = divmod(total, 3600)
            mm, ss = divmod(rem, 60)
            item[k] = f"{hh:02d}:{mm:02d}:{ss:02d}"
        elif isinstance(v, time):
            item[k] = v.strftime("%H:%M:%S")
        elif isinstance(v, datetime):
            item[k] = v.isoformat(sep=" ", timespec="seconds")
        elif isinstance(v, date):
            item[k] = v.isoformat()
        elif hasattr(v, "isoformat"):
            try:
                item[k] = v.isoformat()
            except Exception:
                item[k] = str(v)
    return item


def _atendimentos_da_unidade(cursor, id_unidade: int, *, limit: int = 12) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
          a.id_atendimentos AS id,
          a.data_atendimentos AS data,
          a.horario_inicio_atendimentos AS horario_inicio,
          a.status_atendimentos AS status,
          a.substatus_atendimentos AS substatus,
          a.analista_atuante_atendimentos AS analista_gestao,
          a.analista_configuracao_atendimentos AS analista_config,
          a.analista_caderno_teste_atendimentos AS analista_caderno
        FROM atendimentos a
        WHERE a.id_unidades_atendimentos = %s
        ORDER BY a.data_atendimentos DESC, a.horario_inicio_atendimentos DESC
        LIMIT %s
        """,
        (id_unidade, limit),
    )
    return [_format_atendimento_ctx_row(r) for r in (cursor.fetchall() or [])]


def _unidade_resumo(cursor, id_unidade: int) -> Optional[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
          id_unidades AS id_unidade,
          id_vgr_unidades AS id_vgr,
          COALESCE(nome_unidades, '') AS nome,
          COALESCE(acronimo_unidades, '') AS acronimo,
          COALESCE(hostname_unidades, '') AS hostname,
          COALESCE(municipio_unidades, '') AS municipio,
          COALESCE(estado_unidades, '') AS estado
        FROM unidades
        WHERE id_unidades = %s
        LIMIT 1
        """,
        (id_unidade,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    item = dict(row)
    for k, v in list(item.items()):
        if v is None:
            item[k] = ""
    return item


def _equipamentos_da_unidade(
    cursor,
    id_unidade: int,
    *,
    exclude_id: Optional[int] = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    params: list[Any] = [id_unidade]
    excl = ""
    if exclude_id is not None:
        excl = " AND e.id_equipamentos <> %s"
        params.append(int(exclude_id))
    try:
        lim = max(1, min(20, int(limit)))
    except (TypeError, ValueError):
        lim = 8
    params.append(lim)
    cursor.execute(
        f"""
        SELECT
          e.id_equipamentos AS id,
          COALESCE(e.modelo_equipamentos, '') AS modelo,
          COALESCE(e.serial_equipamentos, '') AS serial,
          COALESCE(e.descricao_equipamentos, '') AS descricao
        FROM equipamentos e
        WHERE e.id_unidades_equipamentos = %s
          AND COALESCE(e.deleted_equipamentos, 0) = 0
          {excl}
        ORDER BY e.id_equipamentos DESC
        LIMIT %s
        """,
        params,
    )
    rows = []
    for r in cursor.fetchall() or []:
        item = dict(r)
        for k, v in list(item.items()):
            if v is None:
                item[k] = ""
        rows.append(item)
    return rows


def _links_da_unidade(
    cursor,
    id_unidade: int,
    *,
    exclude_id: Optional[int] = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    params: list[Any] = [id_unidade]
    excl = ""
    if exclude_id is not None:
        excl = " AND l.id_link <> %s"
        params.append(int(exclude_id))
    try:
        lim = max(1, min(20, int(limit)))
    except (TypeError, ValueError):
        lim = 8
    params.append(lim)
    cursor.execute(
        f"""
        SELECT
          l.id_link AS id,
          COALESCE(l.tipo_links, '') AS tipo,
          COALESCE(l.operadora_links, '') AS operadora,
          COALESCE(l.designador_links, '') AS designador,
          COALESCE(l.id_vgr_links, '') AS id_vgr_link,
          COALESCE(l.ip_wan_links, '') AS ip_wan
        FROM links l
        WHERE l.id_unidades_links = %s
          {excl}
        ORDER BY l.id_link DESC
        LIMIT %s
        """,
        params,
    )
    rows = []
    for r in cursor.fetchall() or []:
        item = dict(r)
        for k, v in list(item.items()):
            if v is None:
                item[k] = ""
        rows.append(item)
    return rows


def _contexto_unidade_pack(
    cursor,
    id_unidade: Optional[int],
    *,
    exclude_equipamento_id: Optional[int] = None,
    exclude_link_id: Optional[int] = None,
) -> dict[str, Any]:
    if not id_unidade:
        return {
            "unidade": None,
            "atendimentos": [],
            "equipamentos_relacionados": [],
            "links_relacionados": [],
        }
    return {
        "unidade": _unidade_resumo(cursor, id_unidade),
        "atendimentos": _atendimentos_da_unidade(cursor, id_unidade),
        "equipamentos_relacionados": _equipamentos_da_unidade(
            cursor, id_unidade, exclude_id=exclude_equipamento_id
        ),
        "links_relacionados": _links_da_unidade(
            cursor, id_unidade, exclude_id=exclude_link_id
        ),
    }


def contexto_unidade_by_vgr(
    cursor, id_vgr: str
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Contexto da unidade por ID VGR (preview na criação / typeahead)."""
    vgr = str(id_vgr or "").strip()
    if not vgr:
        return None, "Informe o ID VGR."
    cursor.execute(
        """
        SELECT id_unidades AS id_unidade
        FROM unidades
        WHERE id_vgr_unidades = %s
        LIMIT 1
        """,
        (vgr,),
    )
    row = cursor.fetchone()
    if not row:
        return None, "Unidade não encontrada."
    try:
        uid = int(row.get("id_unidade"))
    except (TypeError, ValueError):
        return None, "Unidade inválida."
    pack = _contexto_unidade_pack(cursor, uid)
    return {"success": True, **pack}, None


def contexto_equipamento(cursor, eq_id: int) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    cursor.execute(
        """
        SELECT
          e.id_equipamentos AS id,
          e.id_unidades_equipamentos AS id_unidade,
          e.modelo_equipamentos AS modelo,
          e.serial_equipamentos AS serial,
          e.versao_equipamentos AS versao,
          e.mac_equipamentos AS mac,
          e.licenca_equipamentos AS licenca,
          e.descricao_equipamentos AS descricao
        FROM equipamentos e
        WHERE e.id_equipamentos = %s
          AND COALESCE(e.deleted_equipamentos, 0) = 0
        LIMIT 1
        """,
        (eq_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None, "Equipamento não encontrado."
    item = _equipamento_row_item(row)
    try:
        uid_i = int(item.get("id_unidade")) if item.get("id_unidade") not in ("", None) else None
    except (TypeError, ValueError):
        uid_i = None
    pack = _contexto_unidade_pack(
        cursor, uid_i, exclude_equipamento_id=int(eq_id)
    )
    return {
        "success": True,
        "equipamento": item,
        **pack,
    }, None


def contexto_link(cursor, link_id: int) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    cursor.execute(
        """
        SELECT
          l.id_link AS id,
          l.id_unidades_links AS id_unidade,
          l.tipo_links AS tipo,
          l.operadora_links AS operadora,
          l.designador_links AS designador,
          l.id_vgr_links AS id_vgr_link,
          l.ip_wan_links AS ip_wan,
          l.redundante_critico_links AS redundante_critico
        FROM links l
        WHERE l.id_link = %s
        LIMIT 1
        """,
        (link_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None, "Link não encontrado."
    item = dict(row)
    for k, v in list(item.items()):
        if v is None:
            item[k] = ""
    try:
        item["redundante_critico"] = int(item.get("redundante_critico") or 0)
    except (TypeError, ValueError):
        item["redundante_critico"] = 0
    _apply_link_fora_flags(item)
    try:
        uid_i = int(item.get("id_unidade")) if item.get("id_unidade") not in ("", None) else None
    except (TypeError, ValueError):
        uid_i = None
    pack = _contexto_unidade_pack(cursor, uid_i, exclude_link_id=int(link_id))
    return {
        "success": True,
        "link": item,
        **pack,
    }, None


def list_equipamentos_datatable(cursor, args: Mapping[str, Any]) -> dict[str, Any]:
    """Lista equipamentos para DataTables.

    ``mode=client`` (padrão das telas admin PortalDt): retorna até ``_CLIENT_ROW_CAP``
    linhas **slim** (só colunas/KPIs da grade). Detalhe completo = GET por id.
    Status/analista na listagem (batch ``MAX(id)``) + ``columnControl`` leve.

    ``since_revision`` (com mode=client): se igual à revisão atual, ``unchanged=true``.
    """
    short = _client_unchanged_payload(args)
    if short is not None:
        return short

    client = _is_client_mode(args)
    force = _client_list_force_refresh(args)
    if client and not force:
        cached = _client_list_cache_get("equipamentos")
        if cached is not None:
            out = attach_to_payload(cached)
            out["from_cache"] = True
            return out

    dt = _dt_args(args)
    if client:
        total = 0
    else:
        cursor.execute(
            "SELECT COUNT(*) AS c FROM equipamentos WHERE COALESCE(deleted_equipamentos, 0) = 0"
        )
        total = int((cursor.fetchone() or {}).get("c") or 0)

    where = ["COALESCE(e.deleted_equipamentos, 0) = 0"]
    params: list[Any] = []
    if not client and dt["search"]:
        where.append(
            """(
              e.serial_equipamentos LIKE %s OR e.modelo_equipamentos LIKE %s
              OR e.versao_equipamentos LIKE %s OR e.descricao_equipamentos LIKE %s
              OR e.mac_equipamentos LIKE %s OR CAST(e.id_equipamentos AS CHAR) LIKE %s
              OR u.id_vgr_unidades LIKE %s OR u.hostname_unidades LIKE %s
              OR u.acronimo_unidades LIKE %s OR u.nome_unidades LIKE %s
            )"""
        )
        params.extend(_like_params(dt["search"], 10))

    where_sql = " AND ".join(where)
    if client:
        order_expr = EQ_ORDER_WHITELIST[0]
        order_dir = "desc"
        limit_sql = "LIMIT %s"
        page_params = list(params) + [_CLIENT_ROW_CAP]
        att_cols = "'' AS status_ultimo_atendimento, '' AS analista_caderno_ultimo"
        cursor.execute(
            f"""
            SELECT
              e.id_equipamentos AS id,
              e.id_unidades_equipamentos AS id_unidade,
              e.modelo_equipamentos AS modelo,
              e.serial_equipamentos AS serial,
              e.versao_equipamentos AS versao,
              u.id_vgr_unidades AS id_vgr,
              u.hostname_unidades AS hostname,
              u.acronimo_unidades AS acronimo,
              u.nome_unidades AS nome_unidade,
              {att_cols}
            FROM equipamentos e
            LEFT JOIN unidades u ON u.id_unidades = e.id_unidades_equipamentos
            WHERE {where_sql}
            ORDER BY {order_expr} {order_dir}
            {limit_sql}
            """,
            page_params,
        )
        data = [_equipamento_list_row_item(row) for row in (cursor.fetchall() or [])]
        _apply_ultimo_atendimento(
            data, _fetch_ultimo_atendimento_map(cursor, _unit_ids_from_rows(data))
        )
        total = len(data)
        filtered = total
        cc_opts = _build_column_control(data, _EQ_COLUMN_CONTROL_KEYS)
    else:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM equipamentos e
            LEFT JOIN unidades u ON u.id_unidades = e.id_unidades_equipamentos
            WHERE {where_sql}
            """,
            params,
        )
        filtered = int((cursor.fetchone() or {}).get("c") or 0)
        order_expr = EQ_ORDER_WHITELIST[0]
        if 0 <= dt["order_col"] < len(EQ_ORDER_WHITELIST):
            order_expr = EQ_ORDER_WHITELIST[dt["order_col"]]
        order_dir = dt["order_dir"]
        limit_sql = "LIMIT %s, %s"
        page_params = list(params) + [dt["start"], dt["length"]]
        att_join = _sql_join_ultimo_atendimento("e.id_unidades_equipamentos")
        att_cols = _SQL_ULTIMO_ATENDIMENTO_COLS
        cursor.execute(
            f"""
            SELECT
              e.id_equipamentos AS id,
              e.id_unidades_equipamentos AS id_unidade,
              e.modelo_equipamentos AS modelo,
              e.serial_equipamentos AS serial,
              e.mac_equipamentos AS mac,
              e.licenca_equipamentos AS licenca,
              e.versao_equipamentos AS versao,
              e.descricao_equipamentos AS descricao,
              u.id_vgr_unidades AS id_vgr,
              u.hostname_unidades AS hostname,
              u.acronimo_unidades AS acronimo,
              u.nome_unidades AS nome_unidade,
              {att_cols}
            FROM equipamentos e
            LEFT JOIN unidades u ON u.id_unidades = e.id_unidades_equipamentos
            {att_join}
            WHERE {where_sql}
            ORDER BY {order_expr} {order_dir}
            {limit_sql}
            """,
            page_params,
        )
        data = [_equipamento_row_item(row) for row in (cursor.fetchall() or [])]
        cc_opts = None

    payload = {
        "draw": dt["draw"],
        "recordsTotal": total,
        "recordsFiltered": filtered,
        "data": data,
        "success": True,
        "mode": "client" if client else "server",
        "inventory_list_schema": INVENTORY_LIST_SCHEMA,
    }
    if client and cc_opts is not None:
        payload["columnControl"] = cc_opts
    if client:
        _client_list_cache_put("equipamentos", payload)
    return attach_to_payload(payload)


def list_links_datatable(cursor, args: Mapping[str, Any]) -> dict[str, Any]:
    """Lista links para DataTables (``mode=client`` = dataset slim no browser).

    Sem PPPoE/decrypt na listagem — detalhe completo + decrypt no GET ``/links/<id>``.
    Status/analista na listagem (batch ``MAX(id)``) + ``columnControl`` leve.
    """
    short = _client_unchanged_payload(args)
    if short is not None:
        return short

    client = _is_client_mode(args)
    force = _client_list_force_refresh(args)
    if client and not force:
        cached = _client_list_cache_get("links")
        if cached is not None:
            out = attach_to_payload(cached)
            out["from_cache"] = True
            return out

    dt = _dt_args(args)
    if not client:
        cursor.execute("SELECT COUNT(*) AS c FROM links")
        total = int((cursor.fetchone() or {}).get("c") or 0)
    else:
        total = 0

    where = ["1=1"]
    params: list[Any] = []
    if not client and dt["search"]:
        where.append(
            """(
              l.designador_links LIKE %s OR l.tipo_links LIKE %s
              OR l.operadora_links LIKE %s OR l.id_vgr_links LIKE %s
              OR l.ip_wan_links LIKE %s OR l.ip_gateway_links LIKE %s
              OR l.vlan_links LIKE %s OR CAST(l.id_link AS CHAR) LIKE %s
              OR u.id_vgr_unidades LIKE %s OR u.hostname_unidades LIKE %s
              OR u.acronimo_unidades LIKE %s OR u.nome_unidades LIKE %s
            )"""
        )
        params.extend(_like_params(dt["search"], 12))

    where_sql = " AND ".join(where)
    if client:
        order_expr = LINK_ORDER_WHITELIST[0]
        order_dir = "desc"
        limit_sql = "LIMIT %s"
        page_params = list(params) + [_CLIENT_ROW_CAP]
        att_join = ""
        att_cols = "'' AS status_ultimo_atendimento, '' AS analista_caderno_ultimo"
    else:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM links l
            LEFT JOIN unidades u ON u.id_unidades = l.id_unidades_links
            WHERE {where_sql}
            """,
            params,
        )
        filtered = int((cursor.fetchone() or {}).get("c") or 0)
        order_expr = LINK_ORDER_WHITELIST[0]
        if 0 <= dt["order_col"] < len(LINK_ORDER_WHITELIST):
            order_expr = LINK_ORDER_WHITELIST[dt["order_col"]]
        order_dir = dt["order_dir"]
        limit_sql = "LIMIT %s, %s"
        page_params = list(params) + [dt["start"], dt["length"]]
        att_join = _sql_join_ultimo_atendimento("l.id_unidades_links")
        att_cols = _SQL_ULTIMO_ATENDIMENTO_COLS

    if client:
        cursor.execute(
            f"""
            SELECT
              l.id_link AS id,
              l.id_unidades_links AS id_unidade,
              l.tipo_links AS tipo,
              l.operadora_links AS operadora,
              l.designador_links AS designador,
              l.id_vgr_links AS id_vgr_link,
              l.ip_wan_links AS ip_wan,
              l.redundante_critico_links AS redundante_critico,
              u.id_vgr_unidades AS id_vgr,
              u.hostname_unidades AS hostname,
              u.acronimo_unidades AS acronimo,
              {att_cols}
            FROM links l
            LEFT JOIN unidades u ON u.id_unidades = l.id_unidades_links
            WHERE {where_sql}
            ORDER BY {order_expr} {order_dir}
            {limit_sql}
            """,
            page_params,
        )
        data = [_link_list_row_item(row) for row in (cursor.fetchall() or [])]
        _apply_ultimo_atendimento(
            data, _fetch_ultimo_atendimento_map(cursor, _unit_ids_from_rows(data))
        )
        total = len(data)
        filtered = total
        cc_opts = _build_column_control(data, _LINK_COLUMN_CONTROL_KEYS)
    else:
        cursor.execute(
            f"""
            SELECT
              l.id_link AS id,
              l.id_unidades_links AS id_unidade,
              l.tipo_links AS tipo,
              l.operadora_links AS operadora,
              l.designador_links AS designador,
              l.id_vgr_links AS id_vgr_link,
              l.ip_wan_links AS ip_wan,
              l.ip_gateway_links AS ip_gateway,
              l.ip_mascara_links AS ip_mascara,
              l.vlan_links AS vlan,
              l.velocidade_links AS velocidade,
              l.redundante_critico_links AS redundante_critico,
              l.pppoe_user_links,
              CASE
                WHEN l.pppoe_pass_links IS NOT NULL AND l.pppoe_pass_links <> '' THEN 1
                ELSE 0
              END AS pppoe_pass_set_flag,
              u.id_vgr_unidades AS id_vgr,
              u.hostname_unidades AS hostname,
              u.acronimo_unidades AS acronimo,
              u.nome_unidades AS nome_unidade,
              {att_cols}
            FROM links l
            LEFT JOIN unidades u ON u.id_unidades = l.id_unidades_links
            {att_join}
            WHERE {where_sql}
            ORDER BY {order_expr} {order_dir}
            {limit_sql}
            """,
            page_params,
        )
        data = [_link_row_item(row) for row in (cursor.fetchall() or [])]
        cc_opts = None

    payload = {
        "draw": dt["draw"],
        "recordsTotal": total,
        "recordsFiltered": filtered,
        "data": data,
        "success": True,
        "mode": "client" if client else "server",
        "inventory_list_schema": INVENTORY_LIST_SCHEMA,
    }
    if client and cc_opts is not None:
        payload["columnControl"] = cc_opts
    if client:
        _client_list_cache_put("links", payload)
    return attach_to_payload(payload)


def create_equipamento(
    cursor, payload: Mapping[str, Any]
) -> tuple[Optional[int], list[FieldChange], Optional[str]]:
    uid, err = resolve_unidade_id(
        cursor,
        id_unidade=payload.get("id_unidade"),
        id_vgr=payload.get("id_vgr"),
    )
    if err:
        return None, [], err

    eq = {
        "modelo": payload.get("modelo"),
        "serial": payload.get("serial"),
        "versao": payload.get("versao"),
        "descricao": payload.get("descricao"),
    }
    len_err = validate_equipamento_fields(eq)
    if len_err:
        return None, [], len_err

    serial = (eq.get("serial") or "").strip().upper()
    if not serial:
        return None, [], "Serial é obrigatório."
    fmt_err = validate_serial_fortinet_format(serial, obrigatorio=True)
    if fmt_err:
        return None, [], fmt_err
    modelo, modelo_err = resolve_modelo_equipamento(serial, eq.get("modelo"))
    if modelo_err:
        return None, [], modelo_err
    versao = (eq.get("versao") or "").strip() or "7.4.11"
    descricao = resolve_descricao_equipamento(modelo, eq.get("descricao"))
    mac = str(payload.get("mac") or "").strip()
    licenca = str(payload.get("licenca") or "").strip()

    cursor.execute(
        """
        SELECT u.id_vgr_unidades
        FROM equipamentos e
        JOIN unidades u ON e.id_unidades_equipamentos = u.id_unidades
        WHERE e.serial_equipamentos = %s
          AND e.id_unidades_equipamentos IS NOT NULL
          AND COALESCE(e.deleted_equipamentos, 0) = 0
        LIMIT 1
        """,
        (serial,),
    )
    collision = cursor.fetchone()
    if collision:
        vgr = collision["id_vgr_unidades"] if isinstance(collision, dict) else collision[0]
        return None, [], f"Erro: O Serial '{serial}' já pertence ao ID VGR {vgr}."

    new_map = {
        "modelo_equipamentos": modelo,
        "serial_equipamentos": serial,
        "versao_equipamentos": versao,
        "descricao_equipamentos": descricao,
        "mac_equipamentos": mac or None,
        "licenca_equipamentos": licenca or None,
        "id_unidades_equipamentos": uid,
    }
    changes = collect_field_changes({}, new_map)

    cursor.execute(
        """
        INSERT INTO equipamentos (
          modelo_equipamentos, serial_equipamentos, versao_equipamentos,
          descricao_equipamentos, mac_equipamentos, licenca_equipamentos,
          id_unidades_equipamentos, deleted_equipamentos
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
        """,
        (modelo, serial, versao, descricao, mac or None, licenca or None, uid),
    )
    return int(cursor.lastrowid), changes, None


def update_equipamento(
    cursor, eq_id: int, payload: Mapping[str, Any]
) -> tuple[list[FieldChange], Optional[str]]:
    cursor.execute(
        """
        SELECT id_equipamentos, id_unidades_equipamentos, modelo_equipamentos,
               serial_equipamentos, versao_equipamentos, descricao_equipamentos,
               mac_equipamentos, licenca_equipamentos
        FROM equipamentos WHERE id_equipamentos = %s
        """,
        (eq_id,),
    )
    row = cursor.fetchone()
    if not row:
        return [], "Equipamento não encontrado."

    eq = {
        "modelo": payload.get("modelo", row.get("modelo_equipamentos")),
        "serial": payload.get("serial", row.get("serial_equipamentos")),
        "versao": payload.get("versao", row.get("versao_equipamentos")),
        "descricao": payload.get("descricao", row.get("descricao_equipamentos")),
    }
    len_err = validate_equipamento_fields(eq)
    if len_err:
        return [], len_err

    serial = (eq.get("serial") or "").strip().upper()
    if not serial:
        return [], "Serial é obrigatório."
    fmt_err = validate_serial_fortinet_format(serial, obrigatorio=True)
    if fmt_err:
        return [], fmt_err
    modelo, modelo_err = resolve_modelo_equipamento(serial, eq.get("modelo"))
    if modelo_err:
        return [], modelo_err
    versao = (eq.get("versao") or "").strip() or "7.4.11"
    descricao = resolve_descricao_equipamento(modelo, eq.get("descricao"))
    mac = str(payload.get("mac", row.get("mac_equipamentos") or "")).strip()
    licenca = str(payload.get("licenca", row.get("licenca_equipamentos") or "")).strip()
    uid = row.get("id_unidades_equipamentos")

    if serial:
        cursor.execute(
            """
            SELECT u.id_vgr_unidades
            FROM equipamentos e
            JOIN unidades u ON e.id_unidades_equipamentos = u.id_unidades
            WHERE e.serial_equipamentos = %s
              AND e.id_equipamentos != %s
              AND e.id_unidades_equipamentos IS NOT NULL
              AND (%s IS NULL OR e.id_unidades_equipamentos != %s)
              AND COALESCE(e.deleted_equipamentos, 0) = 0
            LIMIT 1
            """,
            (serial, eq_id, uid, uid),
        )
        collision = cursor.fetchone()
        if collision:
            vgr = collision["id_vgr_unidades"] if isinstance(collision, dict) else collision[0]
            return [], f"Erro: O Serial '{serial}' já pertence ao ID VGR {vgr}."

    new_map = {
        "modelo_equipamentos": modelo,
        "serial_equipamentos": serial,
        "versao_equipamentos": versao,
        "descricao_equipamentos": descricao,
        "mac_equipamentos": mac or None,
        "licenca_equipamentos": licenca or None,
    }
    changes = apply_partial_update(
        cursor,
        table="equipamentos",
        pk_column="id_equipamentos",
        pk_value=eq_id,
        old_map=row,
        new_map=new_map,
    )
    return changes, None


def transfer_equipamento(
    cursor, eq_id: int, payload: Mapping[str, Any]
) -> tuple[list[FieldChange], Optional[str]]:
    uid, err = resolve_unidade_id(
        cursor,
        id_unidade=payload.get("id_unidade"),
        id_vgr=payload.get("id_vgr"),
    )
    if err:
        return [], err
    cursor.execute(
        "SELECT id_equipamentos, serial_equipamentos, id_unidades_equipamentos FROM equipamentos WHERE id_equipamentos = %s",
        (eq_id,),
    )
    row = cursor.fetchone()
    if not row:
        return [], "Equipamento não encontrado."
    conflito = check_expected_unidade(row.get("id_unidades_equipamentos"), payload)
    if conflito:
        return [], conflito
    serial = (row.get("serial_equipamentos") or "").strip().upper()
    if serial:
        cursor.execute(
            """
            SELECT u.id_vgr_unidades
            FROM equipamentos e
            JOIN unidades u ON e.id_unidades_equipamentos = u.id_unidades
            WHERE e.serial_equipamentos = %s
              AND e.id_equipamentos != %s
              AND e.id_unidades_equipamentos IS NOT NULL
              AND e.id_unidades_equipamentos != %s
              AND COALESCE(e.deleted_equipamentos, 0) = 0
            LIMIT 1
            """,
            (serial, eq_id, uid),
        )
        collision = cursor.fetchone()
        if collision:
            vgr = collision["id_vgr_unidades"] if isinstance(collision, dict) else collision[0]
            return [], f"O Serial '{serial}' já pertence ao ID VGR {vgr}."

    changes = apply_partial_update(
        cursor,
        table="equipamentos",
        pk_column="id_equipamentos",
        pk_value=eq_id,
        old_map={"id_unidades_equipamentos": row.get("id_unidades_equipamentos")},
        new_map={"id_unidades_equipamentos": uid},
    )
    return changes, None


def desassociar_equipamento(
    cursor, eq_id: int, payload: Mapping[str, Any] | None = None
) -> tuple[list[FieldChange], Optional[str]]:
    cursor.execute(
        "SELECT id_equipamentos, id_unidades_equipamentos FROM equipamentos WHERE id_equipamentos = %s",
        (eq_id,),
    )
    row = cursor.fetchone()
    if not row:
        return [], "Equipamento não encontrado."
    conflito = check_expected_unidade(row.get("id_unidades_equipamentos"), payload)
    if conflito:
        return [], conflito
    changes = apply_partial_update(
        cursor,
        table="equipamentos",
        pk_column="id_equipamentos",
        pk_value=eq_id,
        old_map={"id_unidades_equipamentos": row.get("id_unidades_equipamentos")},
        new_map={"id_unidades_equipamentos": None},
    )
    return changes, None


def delete_equipamento(
    cursor, eq_id: int
) -> tuple[list[FieldChange], Optional[str]]:
    cursor.execute(
        """
        SELECT id_equipamentos, id_unidades_equipamentos, modelo_equipamentos,
               serial_equipamentos, versao_equipamentos, descricao_equipamentos,
               mac_equipamentos, licenca_equipamentos
        FROM equipamentos WHERE id_equipamentos = %s
        """,
        (eq_id,),
    )
    row = cursor.fetchone()
    if not row:
        return [], "Equipamento não encontrado."
    changes = snapshot_field_changes_delete(row, _EQ_AUDIT_COLS)
    cursor.execute("DELETE FROM equipamentos WHERE id_equipamentos = %s", (eq_id,))
    return changes, None


def create_link(
    cursor, payload: Mapping[str, Any]
) -> tuple[Optional[int], list[FieldChange], Optional[str]]:
    uid, err = resolve_unidade_id(
        cursor,
        id_unidade=payload.get("id_unidade"),
        id_vgr=payload.get("id_vgr_unidade") or payload.get("id_vgr"),
    )
    if err:
        return None, [], err

    link_fields = dict(payload)
    # id_vgr no normalize = ID VGR do circuito (não da unidade)
    if payload.get("id_vgr_link") not in (None, ""):
        link_fields["id_vgr"] = payload.get("id_vgr_link")
    elif "id_vgr_unidade" in payload:
        link_fields["id_vgr"] = payload.get("id_vgr_link") or ""

    lnk = normalize_link_api_payload(link_fields)
    if not applies_redundante_critico(lnk.get("tipo"), lnk.get("operadora")):
        lnk["redundante_critico_links"] = 0
        lnk["redundante_critico"] = 0
    len_err = validate_link_fields(lnk)
    if len_err:
        return None, [], len_err
    uniq = find_link_uniqueness_errors(cursor, lnk, exclude_link_id=None, id_unidade=uid)
    if uniq:
        return None, [], uniq[0]

    new_map = {
        "id_unidades_links": uid,
        "id_vgr_links": lnk.get("id_vgr"),
        "designador_links": (lnk.get("designador") or "").strip(),
        "tipo_links": lnk.get("tipo"),
        "operadora_links": lnk.get("operadora"),
        "vlan_links": lnk.get("vlan"),
        "ip_wan_links": lnk.get("ip_wan"),
        "redundante_critico_links": lnk.get("redundante_critico_links", 0),
        "ip_gateway_links": lnk.get("ip_gateway"),
        "ip_mascara_links": lnk.get("ip_mascara"),
        "velocidade_links": lnk.get("velocidade"),
        "pppoe_user_links": lnk.get("pppoe_user"),
        "pppoe_pass_links": lnk.get("pppoe_pass"),
    }
    changes = collect_field_changes({}, new_map)

    cursor.execute(
        """
        INSERT INTO links (
          id_unidades_links, id_vgr_links, designador_links, tipo_links, operadora_links,
          vlan_links, ip_wan_links, redundante_critico_links, ip_gateway_links,
          ip_mascara_links, velocidade_links, pppoe_user_links, pppoe_pass_links
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            uid,
            lnk.get("id_vgr"),
            (lnk.get("designador") or "").strip(),
            lnk.get("tipo"),
            lnk.get("operadora"),
            lnk.get("vlan"),
            lnk.get("ip_wan"),
            lnk.get("redundante_critico_links", 0),
            lnk.get("ip_gateway"),
            lnk.get("ip_mascara"),
            lnk.get("velocidade"),
            encrypt_sensitive_db_column("pppoe_user_links", lnk.get("pppoe_user")),
            encrypt_sensitive_db_column("pppoe_pass_links", lnk.get("pppoe_pass")),
        ),
    )
    return int(cursor.lastrowid), changes, None


def update_link(
    cursor, link_id: int, payload: Mapping[str, Any]
) -> tuple[list[FieldChange], Optional[str]]:
    cursor.execute(
        """
        SELECT id_link, designador_links, tipo_links, operadora_links, vlan_links,
               ip_wan_links, ip_gateway_links, ip_mascara_links, velocidade_links,
               pppoe_user_links, pppoe_pass_links, id_vgr_links, id_unidades_links,
               redundante_critico_links
        FROM links WHERE id_link = %s
        """,
        (link_id,),
    )
    row = cursor.fetchone()
    if not row:
        return [], "Link não encontrado."
    decrypt_sensitive_row_inplace(row)

    merged = {
        "designador": payload.get("designador", row.get("designador_links")),
        "tipo": payload.get("tipo", row.get("tipo_links")),
        "operadora": payload.get("operadora", row.get("operadora_links")),
        "vlan": payload.get("vlan", row.get("vlan_links")),
        "ip_wan": payload.get("ip_wan", row.get("ip_wan_links")),
        "redundante_critico": payload.get(
            "redundante_critico", row.get("redundante_critico_links")
        ),
        "ip_gateway": payload.get("ip_gateway", row.get("ip_gateway_links")),
        "ip_mascara": payload.get("ip_mascara", row.get("ip_mascara_links")),
        "velocidade": payload.get("velocidade", row.get("velocidade_links")),
        "pppoe_user": payload.get("pppoe_user", row.get("pppoe_user_links")),
        "pppoe_pass": payload.get("pppoe_pass", row.get("pppoe_pass_links")),
        "id_vgr": payload.get("id_vgr", row.get("id_vgr_links")),
    }
    # Senha mascarada na UI: manter existente
    if str(merged.get("pppoe_pass") or "").strip() in ("", "••••••", "******"):
        merged["pppoe_pass"] = row.get("pppoe_pass_links")

    lnk = normalize_link_api_payload(merged, row)
    if not applies_redundante_critico(lnk.get("tipo"), lnk.get("operadora")):
        lnk["redundante_critico_links"] = 0
        lnk["redundante_critico"] = 0
    len_err = validate_link_fields(lnk)
    if len_err:
        return [], len_err
    uniq = find_link_uniqueness_errors(
        cursor,
        lnk,
        exclude_link_id=link_id,
        id_unidade=row.get("id_unidades_links"),
    )
    if uniq:
        return [], uniq[0]

    new_map = {
        "id_vgr_links": lnk.get("id_vgr"),
        "designador_links": (lnk.get("designador") or "").strip(),
        "tipo_links": lnk.get("tipo"),
        "operadora_links": lnk.get("operadora"),
        "vlan_links": lnk.get("vlan"),
        "ip_wan_links": lnk.get("ip_wan"),
        "redundante_critico_links": lnk.get("redundante_critico_links", 0),
        "ip_gateway_links": lnk.get("ip_gateway"),
        "ip_mascara_links": lnk.get("ip_mascara"),
        "velocidade_links": lnk.get("velocidade"),
        "pppoe_user_links": lnk.get("pppoe_user"),
        "pppoe_pass_links": lnk.get("pppoe_pass"),
    }
    changes = apply_partial_update(
        cursor,
        table="links",
        pk_column="id_link",
        pk_value=link_id,
        old_map=row,
        new_map=new_map,
        encrypt_cols=_LINK_ENCRYPT_COLS,
    )
    return changes, None


def transfer_link(
    cursor, link_id: int, payload: Mapping[str, Any]
) -> tuple[list[FieldChange], Optional[str]]:
    uid, err = resolve_unidade_id(
        cursor,
        id_unidade=payload.get("id_unidade"),
        id_vgr=payload.get("id_vgr"),
    )
    if err:
        return [], err
    cursor.execute(
        """
        SELECT id_link, designador_links, tipo_links, operadora_links, vlan_links,
               ip_wan_links, ip_gateway_links, ip_mascara_links, velocidade_links,
               pppoe_user_links, pppoe_pass_links, id_vgr_links, id_unidades_links,
               redundante_critico_links
        FROM links WHERE id_link = %s
        """,
        (link_id,),
    )
    row = cursor.fetchone()
    if not row:
        return [], "Link não encontrado."
    conflito = check_expected_unidade(row.get("id_unidades_links"), payload)
    if conflito:
        return [], conflito
    decrypt_sensitive_row_inplace(row)
    lnk = normalize_link_api_payload(
        {
            "designador": row.get("designador_links"),
            "tipo": row.get("tipo_links"),
            "operadora": row.get("operadora_links"),
            "vlan": row.get("vlan_links"),
            "ip_wan": row.get("ip_wan_links"),
            "redundante_critico": row.get("redundante_critico_links"),
            "ip_gateway": row.get("ip_gateway_links"),
            "ip_mascara": row.get("ip_mascara_links"),
            "velocidade": row.get("velocidade_links"),
            "pppoe_user": row.get("pppoe_user_links"),
            "pppoe_pass": row.get("pppoe_pass_links"),
            "id_vgr": row.get("id_vgr_links"),
        },
        row,
    )
    uniq = find_link_uniqueness_errors(
        cursor, lnk, exclude_link_id=link_id, id_unidade=uid
    )
    if uniq:
        return [], uniq[0]
    changes = apply_partial_update(
        cursor,
        table="links",
        pk_column="id_link",
        pk_value=link_id,
        old_map={"id_unidades_links": row.get("id_unidades_links")},
        new_map={"id_unidades_links": uid},
    )
    return changes, None


def desassociar_link(
    cursor, link_id: int, payload: Mapping[str, Any] | None = None
) -> tuple[list[FieldChange], Optional[str]]:
    cursor.execute(
        "SELECT id_link, id_unidades_links FROM links WHERE id_link = %s",
        (link_id,),
    )
    row = cursor.fetchone()
    if not row:
        return [], "Link não encontrado."
    conflito = check_expected_unidade(row.get("id_unidades_links"), payload)
    if conflito:
        return [], conflito
    changes = apply_partial_update(
        cursor,
        table="links",
        pk_column="id_link",
        pk_value=link_id,
        old_map={"id_unidades_links": row.get("id_unidades_links")},
        new_map={"id_unidades_links": None},
    )
    return changes, None


def delete_link(
    cursor, link_id: int
) -> tuple[list[FieldChange], Optional[str]]:
    cursor.execute(
        """
        SELECT id_link, designador_links, tipo_links, operadora_links, vlan_links,
               ip_wan_links, ip_gateway_links, ip_mascara_links, velocidade_links,
               pppoe_user_links, pppoe_pass_links, id_vgr_links, id_unidades_links,
               redundante_critico_links
        FROM links WHERE id_link = %s
        """,
        (link_id,),
    )
    row = cursor.fetchone()
    if not row:
        return [], "Link não encontrado."
    decrypt_sensitive_row_inplace(row)
    changes = snapshot_field_changes_delete(row, _LINK_AUDIT_COLS)
    cursor.execute("DELETE FROM links WHERE id_link = %s", (link_id,))
    return changes, None
