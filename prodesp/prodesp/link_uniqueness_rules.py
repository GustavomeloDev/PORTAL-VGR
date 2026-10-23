"""
Regras de unicidade PRODESP (links e loopbacks).

Bloqueia cadastro/atualização com mensagem objetiva: campo, valor e registro conflitante.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence

_IP_STRIP_RE = re.compile(r"\s+")


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _norm_ip(value: Any) -> str:
    return _IP_STRIP_RE.sub("", str(value or "").strip()).lower().split("/")[0]


def _norm_operadora(value: Any) -> str:
    return _norm_text(value).upper()


def _first(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _link_label(hit: Mapping[str, Any]) -> str:
    tipo = _norm_text(hit.get("tipo_links") or hit.get("tipo")) or "Link"
    des = _norm_text(hit.get("designador_links") or hit.get("designador"))
    op = _norm_text(hit.get("operadora_links") or hit.get("operadora"))
    parts = [tipo]
    if des:
        parts.append(f"Designador {des}")
    if op:
        parts.append(f"Operadora {op}")
    return " — ".join(parts)


def format_link_collision_message(
    campo: str,
    valor: str,
    hit: Mapping[str, Any],
    *,
    same_unit: bool = False,
    found_as: str = "",
) -> str:
    """Mensagem padrão: o que está duplicado + onde + para quem."""
    id_vgr = _norm_text(hit.get("id_vgr_unidades") or hit.get("id_vgr"))
    link_desc = _link_label(hit)
    where = f"no {link_desc}"
    if id_vgr:
        where += f" da unidade ID VGR {id_vgr}"
    if found_as:
        where += f" (já usado como {found_as})"
    if same_unit:
        return (
            f"{campo} «{valor}» já está cadastrado {where} (mesma unidade). "
            "Confira a qual link esse valor pertence antes de salvar."
        )
    return (
        f"{campo} «{valor}» já está cadastrado {where}. "
        "Não é permitido repetir este valor. Corrija antes de salvar."
    )


def format_loopback_collision_message(
    campo: str,
    valor: str,
    hit: Mapping[str, Any],
    *,
    same_unit: bool = False,
    found_as: str = "",
) -> str:
    id_vgr = _norm_text(hit.get("id_vgr_unidades"))
    found = found_as or "loopback"
    if same_unit:
        return (
            f"{campo} «{valor}» já está usado nesta mesma unidade como {found}. "
            "Os loopbacks Vivo, Cliente e On BGP devem ser distintos."
        )
    return (
        f"{campo} «{valor}» já está cadastrado na unidade ID VGR {id_vgr or '—'} "
        f"como {found}. Não é permitido repetir loopback entre unidades."
    )


def _normalize_exclude_link_ids(
    exclude_link_id: Any = None,
    exclude_link_ids: Optional[Sequence[Any]] = None,
) -> list[Any]:
    ids: list[Any] = []
    seen: set[str] = set()
    for raw in list(exclude_link_ids or []) + ([exclude_link_id] if exclude_link_id is not None else []):
        if raw is None:
            continue
        text = str(raw).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ids.append(raw)
    return ids or [-1]


def _fetch_link_ip_collision(
    cursor,
    ip_norm: str,
    exclude_link_id: Any = None,
    exclude_link_ids: Optional[Sequence[Any]] = None,
) -> Optional[dict]:
    if not ip_norm:
        return None
    ex_ids = _normalize_exclude_link_ids(exclude_link_id, exclude_link_ids)
    placeholders = ", ".join(["%s"] * len(ex_ids))
    cursor.execute(
        f"""
        SELECT
            ln.id_link,
            ln.id_unidades_links,
            ln.tipo_links,
            ln.designador_links,
            ln.operadora_links,
            ln.ip_wan_links,
            ln.ip_gateway_links,
            u.id_vgr_unidades,
            CASE
                WHEN LOWER(REPLACE(TRIM(IFNULL(ln.ip_wan_links, '')), ' ', '')) = %s THEN 'IP WAN'
                ELSE 'IP Gateway'
            END AS found_as
        FROM links ln
        JOIN unidades u ON ln.id_unidades_links = u.id_unidades
        WHERE ln.id_link NOT IN ({placeholders})
          AND (
                LOWER(REPLACE(TRIM(IFNULL(ln.ip_wan_links, '')), ' ', '')) = %s
             OR LOWER(REPLACE(TRIM(IFNULL(ln.ip_gateway_links, '')), ' ', '')) = %s
          )
        LIMIT 1
        """,
        (ip_norm, *ex_ids, ip_norm, ip_norm),
    )
    return cursor.fetchone()


def _fetch_link_field_collision_by_operadora(
    cursor,
    *,
    column: str,
    value: str,
    operadora: str,
    exclude_link_id: Any = None,
    exclude_link_ids: Optional[Sequence[Any]] = None,
) -> Optional[dict]:
    if not value or not operadora:
        return None
    if column not in ("designador_links", "id_vgr_links"):
        raise ValueError("coluna não permitida")
    ex_ids = _normalize_exclude_link_ids(exclude_link_id, exclude_link_ids)
    placeholders = ", ".join(["%s"] * len(ex_ids))
    cursor.execute(
        f"""
        SELECT
            ln.id_link,
            ln.id_unidades_links,
            ln.tipo_links,
            ln.designador_links,
            ln.operadora_links,
            u.id_vgr_unidades
        FROM links ln
        JOIN unidades u ON ln.id_unidades_links = u.id_unidades
        WHERE ln.id_link NOT IN ({placeholders})
          AND UPPER(TRIM(IFNULL(ln.operadora_links, ''))) = %s
          AND TRIM(IFNULL(ln.`{column}`, '')) = %s
        LIMIT 1
        """,
        (*ex_ids, operadora, value),
    )
    return cursor.fetchone()


def _fetch_link_field_collision_global(
    cursor,
    *,
    column: str,
    value: str,
    exclude_link_id: Any = None,
    exclude_link_ids: Optional[Sequence[Any]] = None,
) -> Optional[dict]:
    """Fallback quando operadora não foi informada."""
    if not value:
        return None
    if column not in ("designador_links", "id_vgr_links"):
        raise ValueError("coluna não permitida")
    ex_ids = _normalize_exclude_link_ids(exclude_link_id, exclude_link_ids)
    placeholders = ", ".join(["%s"] * len(ex_ids))
    cursor.execute(
        f"""
        SELECT
            ln.id_link,
            ln.id_unidades_links,
            ln.tipo_links,
            ln.designador_links,
            ln.operadora_links,
            u.id_vgr_unidades
        FROM links ln
        JOIN unidades u ON ln.id_unidades_links = u.id_unidades
        WHERE ln.id_link NOT IN ({placeholders})
          AND TRIM(IFNULL(ln.`{column}`, '')) = %s
        LIMIT 1
        """,
        (*ex_ids, value),
    )
    return cursor.fetchone()


def find_link_uniqueness_errors(
    cursor,
    payload: Mapping[str, Any],
    *,
    exclude_link_id: Any = None,
    exclude_link_ids: Optional[Sequence[Any]] = None,
    id_unidade: Any = None,
    skip_keys: Optional[set[tuple]] = None,
) -> list[str]:
    """
    Valida unicidade de um link (WAN, Gateway, Designador, ID VGR do link).
    Retorna lista de mensagens (vazia se ok).
    `skip_keys`: chaves já reportadas no lote (ex.: ("wan", ip)) para evitar eco.
    """
    errors: list[str] = []
    skip = skip_keys or set()
    tipo = _norm_text(_first(payload, "tipo", "tipo_links")).upper()
    des = _norm_text(_first(payload, "designador", "designador_links"))
    operadora = _norm_operadora(_first(payload, "operadora", "operadora_links"))
    id_vgr_link = _norm_text(_first(payload, "id_vgr", "id_vgr_links"))
    wan = _norm_ip(_first(payload, "ip_wan", "ip_wan_links"))
    gw = _norm_ip(_first(payload, "ip_gateway", "ip_gateway_links"))
    unit_id = id_unidade
    ex_ids = _normalize_exclude_link_ids(exclude_link_id, exclude_link_ids)

    if wan and gw and wan == gw and ("wan_eq_gw", wan) not in skip:
        label = f"Link {tipo}" if tipo else "Link"
        if des:
            label += f" — Designador: {des}"
        errors.append(
            f"{label}: IP WAN e Gateway não podem ser iguais. "
            "Corrija os campos IP WAN e Gateway."
        )

    for campo, ip_val, key_prefix in (("IP WAN", wan, "wan"), ("IP Gateway", gw, "gw")):
        if not ip_val or (key_prefix, ip_val) in skip:
            continue
        hit = _fetch_link_ip_collision(
            cursor, ip_val, exclude_link_ids=ex_ids
        )
        if not hit:
            continue
        same = bool(unit_id and str(hit.get("id_unidades_links")) == str(unit_id))
        errors.append(
            format_link_collision_message(
                campo,
                ip_val,
                hit,
                same_unit=same,
                found_as=_norm_text(hit.get("found_as")),
            )
        )

    if des and operadora and ("des", operadora, des) not in skip:
        hit = _fetch_link_field_collision_by_operadora(
            cursor,
            column="designador_links",
            value=des,
            operadora=operadora,
            exclude_link_ids=ex_ids,
        )
        if hit:
            same = bool(unit_id and str(hit.get("id_unidades_links")) == str(unit_id))
            errors.append(
                format_link_collision_message(
                    "Designador",
                    des,
                    hit,
                    same_unit=same,
                )
            )
    elif des and ("des", "", des) not in skip:
        hit = _fetch_link_field_collision_global(
            cursor,
            column="designador_links",
            value=des,
            exclude_link_ids=ex_ids,
        )
        if hit:
            same = bool(unit_id and str(hit.get("id_unidades_links")) == str(unit_id))
            errors.append(
                format_link_collision_message(
                    "Designador",
                    des,
                    hit,
                    same_unit=same,
                )
            )

    if id_vgr_link and operadora and ("vgr", operadora, id_vgr_link) not in skip:
        hit = _fetch_link_field_collision_by_operadora(
            cursor,
            column="id_vgr_links",
            value=id_vgr_link,
            operadora=operadora,
            exclude_link_ids=ex_ids,
        )
        if hit:
            same = bool(unit_id and str(hit.get("id_unidades_links")) == str(unit_id))
            errors.append(
                format_link_collision_message(
                    "ID VGR do link",
                    id_vgr_link,
                    hit,
                    same_unit=same,
                )
            )
    elif id_vgr_link and ("vgr", "", id_vgr_link) not in skip:
        hit = _fetch_link_field_collision_global(
            cursor,
            column="id_vgr_links",
            value=id_vgr_link,
            exclude_link_ids=ex_ids,
        )
        if hit:
            same = bool(unit_id and str(hit.get("id_unidades_links")) == str(unit_id))
            errors.append(
                format_link_collision_message(
                    "ID VGR do link",
                    id_vgr_link,
                    hit,
                    same_unit=same,
                )
            )

    return errors


def _loopback_field_label(column: str) -> str:
    return {
        "loopback_vivo_unidades": "Loopback Vivo",
        "loopback_cliente_unidades": "Loopback Cliente",
        "loopback_on_bgp_unidades": "Loopback On BGP",
    }.get(column, column)


def find_loopback_uniqueness_errors(
    cursor,
    loopbacks: Mapping[str, Any],
    *,
    exclude_unidade_id: Any = None,
) -> list[str]:
    """
    Valida unicidade dos loopbacks (entre si na unidade e contra outras unidades).
    `loopbacks` aceita chaves com ou sem sufixo `_unidades`.
    """
    mapping = {
        "vivo": "loopback_vivo_unidades",
        "loopback_vivo": "loopback_vivo_unidades",
        "loopback_vivo_unidades": "loopback_vivo_unidades",
        "cliente": "loopback_cliente_unidades",
        "loopback_cliente": "loopback_cliente_unidades",
        "loopback_cliente_unidades": "loopback_cliente_unidades",
        "bgp": "loopback_on_bgp_unidades",
        "loopback_on_bgp": "loopback_on_bgp_unidades",
        "loopback_on_bgp_unidades": "loopback_on_bgp_unidades",
    }
    values: dict[str, str] = {}
    for key, col in mapping.items():
        if key in loopbacks and loopbacks[key] is not None:
            ip = _norm_ip(loopbacks[key])
            if ip:
                values[col] = ip

    # Garante as três chaves canônicas se vierem só pelas colunas
    for col in (
        "loopback_vivo_unidades",
        "loopback_cliente_unidades",
        "loopback_on_bgp_unidades",
    ):
        if col in loopbacks and col not in values:
            ip = _norm_ip(loopbacks[col])
            if ip:
                values[col] = ip

    errors: list[str] = []
    # Dentro da mesma unidade: IPs distintos entre os três campos
    by_ip: dict[str, list[str]] = {}
    for col, ip in values.items():
        by_ip.setdefault(ip, []).append(col)
    for ip, cols in by_ip.items():
        if len(cols) > 1:
            labels = " e ".join(_loopback_field_label(c) for c in cols)
            errors.append(
                format_loopback_collision_message(
                    labels,
                    ip,
                    {"id_vgr_unidades": ""},
                    same_unit=True,
                    found_as="outro campo de loopback",
                )
            )

    ex = exclude_unidade_id if exclude_unidade_id else -1
    for col, ip in values.items():
        cursor.execute(
            """
            SELECT
                id_unidades,
                id_vgr_unidades,
                CASE
                    WHEN LOWER(REPLACE(TRIM(IFNULL(loopback_vivo_unidades, '')), ' ', '')) = %s
                        THEN 'Loopback Vivo'
                    WHEN LOWER(REPLACE(TRIM(IFNULL(loopback_cliente_unidades, '')), ' ', '')) = %s
                        THEN 'Loopback Cliente'
                    ELSE 'Loopback On BGP'
                END AS found_as
            FROM unidades
            WHERE id_unidades != %s
              AND (
                    LOWER(REPLACE(TRIM(IFNULL(loopback_vivo_unidades, '')), ' ', '')) = %s
                 OR LOWER(REPLACE(TRIM(IFNULL(loopback_cliente_unidades, '')), ' ', '')) = %s
                 OR LOWER(REPLACE(TRIM(IFNULL(loopback_on_bgp_unidades, '')), ' ', '')) = %s
              )
            LIMIT 1
            """,
            (ip, ip, ex, ip, ip, ip),
        )
        hit = cursor.fetchone()
        if hit:
            errors.append(
                format_loopback_collision_message(
                    _loopback_field_label(col),
                    ip,
                    hit,
                    same_unit=False,
                    found_as=_norm_text(hit.get("found_as")),
                )
            )
    return errors


def resolve_existing_link_id_for_unit(
    cursor,
    payload: Mapping[str, Any],
    *,
    id_unidade: Any,
) -> Optional[Any]:
    """
    Localiza o id_link da mesma unidade que este payload está atualizando
    (mesmo designador e/ou ID VGR do link), para excluir da checagem de
    unicidade. Sem isso, update sem id no payload colide consigo mesmo.
    """
    if not id_unidade:
        return None
    des = _norm_text(_first(payload, "designador", "designador_links"))
    id_vgr_link = _norm_text(_first(payload, "id_vgr", "id_vgr_links"))
    tipo = _norm_text(_first(payload, "tipo", "tipo_links")).upper()
    if not des and not id_vgr_link:
        return None

    clauses: list[str] = []
    params: list[Any] = [id_unidade]
    if des:
        clauses.append("TRIM(IFNULL(ln.designador_links, '')) = %s")
        params.append(des)
    if id_vgr_link:
        clauses.append("TRIM(IFNULL(ln.id_vgr_links, '')) = %s")
        params.append(id_vgr_link)
    where_match = " OR ".join(clauses)

    cursor.execute(
        f"""
        SELECT ln.id_link, ln.tipo_links
        FROM links ln
        WHERE ln.id_unidades_links = %s
          AND ({where_match})
        ORDER BY
          CASE
            WHEN UPPER(TRIM(IFNULL(ln.tipo_links, ''))) = %s THEN 0
            WHEN TRIM(IFNULL(ln.tipo_links, '')) = '' THEN 1
            WHEN TRIM(IFNULL(ln.tipo_links, '')) = '-' THEN 1
            ELSE 2
          END,
          ln.id_link
        LIMIT 1
        """,
        (*params, tipo or ""),
    )
    hit = cursor.fetchone()
    if not hit:
        return None
    return hit.get("id_link") if isinstance(hit, Mapping) else hit[0]


def find_batch_link_uniqueness_errors(
    cursor,
    links: Sequence[Mapping[str, Any]],
    *,
    id_unidade: Any = None,
) -> list[str]:
    """
    Valida uma lista de links (ex.: preview Blueprint), incluindo duplicatas
    internas do próprio lote além das do banco.
    """
    errors: list[str] = []
    seen_wan: dict[str, str] = {}
    seen_gw: dict[str, str] = {}
    seen_des_op: dict[tuple[str, str], str] = {}
    seen_vgr_op: dict[tuple[str, str], str] = {}
    skip_keys: set[tuple] = set()

    batch_ids: list[Any] = []
    for link in links or []:
        if not isinstance(link, Mapping):
            continue
        lid = link.get("id_link") or link.get("id")
        if lid is not None and str(lid).strip():
            batch_ids.append(lid)
        elif id_unidade:
            resolved = resolve_existing_link_id_for_unit(
                cursor, link, id_unidade=id_unidade
            )
            if resolved is not None and str(resolved).strip():
                batch_ids.append(resolved)

    for idx, link in enumerate(links or []):
        if not isinstance(link, Mapping):
            continue
        tipo = _norm_text(_first(link, "tipo", "tipo_links")).upper() or f"#{idx + 1}"
        des = _norm_text(_first(link, "designador", "designador_links"))
        label = f"Link {tipo}" + (f" — {des}" if des else "")

        wan = _norm_ip(_first(link, "ip_wan", "ip_wan_links"))
        gw = _norm_ip(_first(link, "ip_gateway", "ip_gateway_links"))
        operadora = _norm_operadora(_first(link, "operadora", "operadora_links"))
        id_vgr_link = _norm_text(_first(link, "id_vgr", "id_vgr_links"))

        if wan:
            if wan in seen_wan:
                errors.append(
                    f"IP WAN «{wan}» repetido entre {seen_wan[wan]} e {label} no mesmo formulário."
                )
                skip_keys.add(("wan", wan))
            else:
                seen_wan[wan] = label
            if wan in seen_gw:
                errors.append(
                    f"IP WAN «{wan}» de {label} coincide com o Gateway de {seen_gw[wan]} no formulário."
                )
                skip_keys.add(("wan", wan))
                skip_keys.add(("gw", wan))
        if gw:
            if gw in seen_gw:
                errors.append(
                    f"IP Gateway «{gw}» repetido entre {seen_gw[gw]} e {label} no mesmo formulário."
                )
                skip_keys.add(("gw", gw))
            else:
                seen_gw[gw] = label
            if gw in seen_wan and seen_wan.get(gw) != label:
                errors.append(
                    f"IP Gateway «{gw}» de {label} coincide com o WAN de {seen_wan[gw]} no formulário."
                )
                skip_keys.add(("gw", gw))
                skip_keys.add(("wan", gw))

        if des and operadora:
            key = (operadora, des)
            if key in seen_des_op:
                errors.append(
                    f"Designador «{des}» (Operadora {operadora}) repetido entre "
                    f"{seen_des_op[key]} e {label} no formulário."
                )
                skip_keys.add(("des", operadora, des))
            else:
                seen_des_op[key] = label

        if id_vgr_link and operadora:
            key = (operadora, id_vgr_link)
            if key in seen_vgr_op:
                errors.append(
                    f"ID VGR do link «{id_vgr_link}» (Operadora {operadora}) repetido entre "
                    f"{seen_vgr_op[key]} e {label} no formulário."
                )
                skip_keys.add(("vgr", operadora, id_vgr_link))
            else:
                seen_vgr_op[key] = label

        errors.extend(
            find_link_uniqueness_errors(
                cursor,
                link,
                exclude_link_ids=batch_ids,
                id_unidade=id_unidade,
                skip_keys=skip_keys,
            )
        )

    # Dedup mensagens preservando ordem
    out: list[str] = []
    seen: set[str] = set()
    for msg in errors:
        if msg not in seen:
            seen.add(msg)
            out.append(msg)
    return out
