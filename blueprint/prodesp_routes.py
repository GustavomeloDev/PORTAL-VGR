"""Rotas Flask de Blueprint PRODESP (salvar unidade/equipamento/links e download CSV)."""
import os
import re
from flask import request, render_template, redirect, url_for, send_from_directory, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import safe_join
from prodesp.app import prodesp_bp, get_db_connection, CSV_DIR
from prodesp.prodesp.historico import registrar_log
from prodesp.prodesp.entity_select import (
    sql_select_equipamentos_by_unidade,
    sql_select_links_by_unidade,
    sql_select_unidades_by_id,
    sql_select_unidades_by_id_vgr,
)
from prodesp.prodesp.blueprint.link_vivo_rules import normalize_vivo_link_fields
from prodesp.prodesp.blueprint.redundante_critico_rules import apply_redundante_critico_to_link
from prodesp.prodesp.link_format_rules import sanitize_link_pasted_text
from prodesp.prodesp.link_uniqueness_rules import (
    find_batch_link_uniqueness_errors,
    find_loopback_uniqueness_errors,
)
from prodesp.prodesp.blueprint.link_velocity_rules import normalize_velocity_mbps
from prodesp.prodesp.blueprint.prodesp_csv_generator import (
    apply_blueprint_confirm_overrides,
    apply_blueprint_equipamento_overrides,
    build_blueprint_confirm_payload,
    gerar_csv_blueprint_prodesp,
    validar_dados_blueprint,
)
from prodesp.prodesp.blueprint.prodesp_equipment import infer_modelo_equipamento_from_serial, SERIAL_MODEL_FRAGMENTS_ORDERED
from prodesp.prodesp.conclusao_equipamento_rules import (
    unidade_tem_atendimento_exigindo_serial_padrao,
    validate_serial_fortinet_para_blueprint,
)
from prodesp.prodesp.db_field_limits import (
    UNIDADES_CIDR_DB_COLUMNS,
    UNIDADES_LAN_EXTRA_SPEC,
    UNIDADES_MV_CIDR_JS_KEYS,
    UNIDADES_MV_OPCIONAIS_SPEC,
    blueprint_form_field_limits_for_template,
    blueprint_mv_opcionais_form_field_limits,
    lan_extra_template_fields,
    message_from_mysql_exception,
    mv_opcionais_template_fields,
    normalize_coordinate_for_db,
    sanitize_ip_cidr_field,
    sanitize_plain_ipv4_field,
    validate_blueprint_form_limits,
    validate_coordinate_for_db,
)
from core.logger import get_logger
from core.portal_flash import portal_flash


logging = get_logger("PRODESP")

_BLUEPRINT_FLASH_SCOPE = "prodesp"
_MYSQL_DUPLICATE_KEY_ERRNO = 1062
_MYSQL_BAD_DECIMAL_ERRNO = 1366


def _flash_blueprint(message: str, category: str = "info") -> None:
    portal_flash(message, category, scope=_BLUEPRINT_FLASH_SCOPE)


def mensagem_serial_duplicado(serial: str, id_vgr) -> str:
    """Mensagem alinhada à rota equipamentos-update (atendimentos)."""
    return f"Erro: O Serial '{serial}' já pertence ao ID VGR {id_vgr}."


def buscar_colisao_serial_equipamento(
    cursor, serial: str, exclude_eq_id=None, *, exclude_unidade_id=None
):
    """
    Retorna id_vgr da unidade que já possui o serial, ou None.
    ``exclude_unidade_id``: ignora colisão na própria unidade (create/update atendimento).
    """
    serial = (serial or "").strip().upper()
    if not serial:
        return None
    sql = """
        SELECT u.id_vgr_unidades
        FROM equipamentos eq
        JOIN unidades u ON eq.id_unidades_equipamentos = u.id_unidades
        WHERE eq.serial_equipamentos = %s AND eq.id_equipamentos != %s
    """
    params: list = [serial, exclude_eq_id if exclude_eq_id else -1]
    if exclude_unidade_id not in (None, ""):
        sql += " AND eq.id_unidades_equipamentos != %s"
        params.append(exclude_unidade_id)
    sql += " LIMIT 1"
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if not row:
        return None
    return row.get("id_vgr_unidades") if isinstance(row, dict) else row[0]


def _is_mysql_duplicate_key(exc: BaseException) -> bool:
    return getattr(exc, "errno", None) == _MYSQL_DUPLICATE_KEY_ERRNO


def _is_mysql_bad_decimal(exc: BaseException) -> bool:
    return getattr(exc, "errno", None) == _MYSQL_BAD_DECIMAL_ERRNO


def _blueprint_exception_message(exc: BaseException) -> str:
    """Mensagem amigável para erros MySQL no fluxo de blueprint."""
    user_msg, is_client = message_from_mysql_exception(exc)
    if is_client:
        return user_msg
    if _is_mysql_bad_decimal(exc):
        return (
            "Não foi possível salvar: latitude ou longitude inválida. "
            "Use número decimal com ponto ou vírgula (ex.: -22.4351324)."
        )
    return "Erro ao processar solicitação. Tente novamente ou contate o suporte."


def _validate_blueprint_coordinates(form):
    errors = []
    for field_name, label in (
        ("latitude_unidades", "Latitude"),
        ("longitude_unidades", "Longitude"),
    ):
        err = validate_coordinate_for_db(form.get(field_name), field_label=label)
        if err:
            errors.append(err)
    return errors


def _is_blueprint_orphan_link_tipo(tipo) -> bool:
    """Tipo vazio/legado: não encaixa em MPLS/STATIC até o update do Blueprint."""
    t = _norm_link_field(tipo)
    return not t or t == "-"


def _links_dict_from_list(links_list):
    """
    Monta slots MPLS/STATIC para o formulário.
    Links com tipo_links vazio (legado) ocupam o slot livre — sem isso o
    hidden *_id_link fica vazio e a unicidade trata update como insert.
    """
    rows = [dict(l) for l in (links_list or [])]
    mpls = next((l for l in rows if l.get("tipo_links") == "MPLS"), None)
    static = next((l for l in rows if l.get("tipo_links") == "STATIC"), None)
    used_ids = {
        str(l.get("id_link"))
        for l in (mpls, static)
        if l is not None and l.get("id_link") is not None and str(l.get("id_link")).strip()
    }
    orphans = [
        l
        for l in rows
        if str(l.get("id_link") or "") not in used_ids
        and _is_blueprint_orphan_link_tipo(l.get("tipo_links"))
    ]
    if mpls is None and orphans:
        mpls = orphans.pop(0)
    if static is None and orphans:
        static = orphans.pop(0)
    return {"MPLS": mpls or {}, "STATIC": static or {}}


def _blueprint_acronimo_hint(limit: int = 12) -> str:
    try:
        from prodesp.prodesp.blueprint.blueprint_catalog import list_hint_acronimos

        items = list_hint_acronimos(limit=limit)
        if items:
            return ", ".join(items)
    except Exception:
        pass
    return "DETRAN, PROCON, PRO-SANGUE…"


def _render_blueprint_page(
    unidade,
    equipamento,
    links_list,
    download_link=None,
    blueprint_error=None,
):
    equipamentos = [equipamento] if equipamento else []
    return render_template(
        "prodesp_criar_blueprint.html",
        unidade=unidade,
        equipamentos=equipamentos,
        links=_links_dict_from_list(links_list),
        download_link=download_link,
        blueprint_error=blueprint_error,
        blueprint_field_limits=blueprint_form_field_limits_for_template(),
        blueprint_acronimo_hint=_blueprint_acronimo_hint(),
        serial_model_rules=SERIAL_MODEL_FRAGMENTS_ORDERED,
        prodesp_mv_opcionais_fields=mv_opcionais_template_fields(),
        prodesp_lan_extra_fields=lan_extra_template_fields(),
        prodesp_mv_field_limits=blueprint_mv_opcionais_form_field_limits(),
    )


def _load_blueprint_form_preview(cursor, id_vgr, form):
    """Monta unidade/equipamento/links como ficarão após o submit (sem gravar)."""
    cursor.execute(sql_select_unidades_by_id_vgr(), (id_vgr,))
    old_unidade = cursor.fetchone()
    if not old_unidade:
        return None

    id_unidade = old_unidade["id_unidades"]
    ip_lan_transito = _sanitize_ip_field(form.get("mpls_ip_gateway"))
    unit_updates = _parse_blueprint_unit_updates(form, ip_lan_transito)

    new_serial = (form.get("serial_equipamentos") or "").strip().upper()
    new_versao = (form.get("versao_equipamentos") or "").strip() or None
    new_modelo = infer_modelo_equipamento_from_serial(new_serial) if new_serial else ""

    cursor.execute(
        sql_select_equipamentos_by_unidade(ativos_only=True, limit_one=True),
        (id_unidade,),
    )
    old_eq = cursor.fetchone()
    cursor.execute(sql_select_links_by_unidade(), (id_unidade,))
    unit_links = cursor.fetchall()

    preview_unidade = dict(old_unidade)
    preview_unidade.update(unit_updates)
    preview_equipamento = _preview_equipamento_for_blueprint(old_eq, new_serial, new_versao, new_modelo)
    preview_links = _preview_links_for_blueprint(unit_links, form, id_unidade)
    return preview_unidade, preview_equipamento, preview_links


def _blueprint_error_page(id_vgr, form, message, cursor=None):
    """
    Exibe erro na tela de blueprint com formulário preenchido.
    Alerta inline (blueprint_error): o redirect anterior apagava dados e a mensagem
    não aparecia (flash sem escopo prodesp + página vazia).
    """
    own_conn = None
    own_cursor = None
    db_cursor = cursor
    if db_cursor is None:
        own_conn = get_db_connection()
        own_cursor = own_conn.cursor(dictionary=True)
        db_cursor = own_cursor
    try:
        preview = _load_blueprint_form_preview(db_cursor, id_vgr, form)
        if preview:
            preview_unidade, preview_equipamento, preview_links = preview
            return _render_blueprint_page(
                preview_unidade,
                preview_equipamento,
                preview_links,
                blueprint_error=message,
            )
    except Exception as inner:
        logging.exception("prodesp - falha ao renderizar blueprint após erro: %s", inner)
    finally:
        if own_cursor:
            own_cursor.close()
        if own_conn:
            own_conn.close()
    return redirect(url_for("prodesp.criar_blueprint_prodesp_page"))


def _parse_blueprint_unit_updates(form, ip_lan_transito):
    updates = {
        "acronimo_unidades": (form.get("acronimo_unidades") or "").strip(),
        "hostname_unidades": (form.get("hostname_unidades") or "").strip(),
        "ip_lan_01_unidades": _sanitize_ip_field(form.get("ip_lan_01_unidades")),
        "loopback_vivo_unidades": _sanitize_ip_field(form.get("loopback_vivo_unidades")),
        "loopback_cliente_unidades": _sanitize_ip_field(form.get("loopback_cliente_unidades")),
        "loopback_on_bgp_unidades": _sanitize_ip_field(form.get("loopback_on_bgp_unidades")),
        "ip_lan_transito_unidades": ip_lan_transito,
        "latitude_unidades": normalize_coordinate_for_db(form.get("latitude_unidades")),
        "longitude_unidades": normalize_coordinate_for_db(form.get("longitude_unidades")),
    }
    for js, db_col, _, _, _ in UNIDADES_MV_OPCIONAIS_SPEC:
        raw = form.get(db_col) or ""
        if js in UNIDADES_MV_CIDR_JS_KEYS or db_col in UNIDADES_CIDR_DB_COLUMNS:
            updates[db_col] = sanitize_ip_cidr_field(raw)
        else:
            updates[db_col] = sanitize_plain_ipv4_field(raw)
    for _js, db_col, _csv, _mask, _label, _max, kind in UNIDADES_LAN_EXTRA_SPEC:
        raw = form.get(db_col) or ""
        if kind == "cidr":
            updates[db_col] = sanitize_ip_cidr_field(raw)
        else:
            updates[db_col] = sanitize_plain_ipv4_field(raw)
    return updates


_BLUEPRINT_LINK_DB_COLUMNS = frozenset(
    {
        "tipo_links",
        "operadora_links",
        "id_vgr_links",
        "designador_links",
        "ip_wan_links",
        "redundante_critico_links",
        "ip_gateway_links",
        "ip_mascara_links",
        "vlan_links",
        "velocidade_links",
    }
)


def _resolve_blueprint_existing_link(unit_links, link_type, form, link_data=None):
    """
    Prioridade: hidden *_id_link do formulário → designador/ID VGR → tipo_links.
    Garante update do mesmo registro mesmo com tipo_links vazio no banco.
    """
    prefix = link_type.lower()
    form_link_id = _norm_link_field(form.get(f"{prefix}_id_link"))
    rows = [dict(r) for r in (unit_links or [])]

    if form_link_id:
        by_id = next(
            (r for r in rows if _norm_link_field(r.get("id_link")) == form_link_id),
            None,
        )
        if by_id:
            return by_id

    id_vgr = (link_data or {}).get("id_vgr_links")
    designador = (link_data or {}).get("designador_links")
    if id_vgr is None and designador is None:
        id_vgr = form.get(f"{prefix}id_vgr")
        designador = form.get(f"{prefix}designador")

    found = _find_link_row_for_blueprint(rows, link_type, id_vgr, designador)
    if found:
        return found
    return next((r for r in rows if r.get("tipo_links") == link_type), None)


def _parse_blueprint_link_data(form, link_type, existing_link=None):
    prefix = f"{link_type.lower()}_"
    redundante_raw = form.get(f"{prefix}redundante_critico")
    redundante_critico = redundante_raw in ("on", "1", "true", "True", True)
    link = {
        "tipo_links": link_type,
        "operadora_links": (form.get(f"{prefix}operadora") or "").strip(),
        "id_vgr_links": sanitize_link_pasted_text(form.get(f"{prefix}id_vgr")),
        "designador_links": sanitize_link_pasted_text(form.get(f"{prefix}designador")),
        "ip_wan_links": _sanitize_ip_field(form.get(f"{prefix}ip_wan")),
        "redundante_critico_links": 1 if redundante_critico else 0,
        "redundante_critico": redundante_critico,
        "ip_gateway_links": _sanitize_ip_field(form.get(f"{prefix}ip_gateway")),
        "ip_mascara_links": _sanitize_ip_field(form.get(f"{prefix}ip_mascara")),
        "vlan_links": (form.get(f"{prefix}vlan") or "").strip(),
        "velocidade_links": normalize_velocity_mbps(form.get(f"{prefix}velocidade")),
    }
    link = apply_redundante_critico_to_link(link, existing_link)
    link = normalize_vivo_link_fields(link)
    # Whitelist: o UPDATE/INSERT usa as chaves como nomes de coluna MySQL.
    return {k: v for k, v in link.items() if k in _BLUEPRINT_LINK_DB_COLUMNS}


def _preview_links_for_blueprint(unit_links, form, id_unidade):
    """Estado dos links após o submit do formulário (validação pré-commit)."""
    unit_links = [dict(r) for r in unit_links]
    preview = []

    for link_type in ("MPLS", "STATIC"):
        old_link = _resolve_blueprint_existing_link(unit_links, link_type, form)
        link_data = _parse_blueprint_link_data(form, link_type, old_link)
        old_link = _resolve_blueprint_existing_link(
            unit_links, link_type, form, link_data
        )
        if old_link:
            merged = dict(old_link)
            merged.update(link_data)
            preview.append(merged)
        elif _link_form_has_meaningful_content(link_data):
            preview.append({**link_data, "id_unidades_links": id_unidade})
        else:
            fallback = next((dict(r) for r in unit_links if r.get("tipo_links") == link_type), None)
            if fallback:
                preview.append(fallback)

    return preview


def _preview_equipamento_for_blueprint(old_eq, new_serial, new_versao, new_modelo):
    if not (new_serial or "").strip():
        return dict(old_eq) if old_eq else {}
    preview = dict(old_eq) if old_eq else {}
    preview.update(
        {
            "serial_equipamentos": new_serial,
            "versao_equipamentos": new_versao,
            "modelo_equipamentos": new_modelo,
        }
    )
    return preview


def _norm_link_field(v):
    return (str(v or "").strip())


def _sanitize_ip_field(value):
    """Remove qualquer espaço em branco (digitado, colado etc.) em valores de IP/CIDR."""
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value), flags=re.UNICODE)


def _link_form_has_meaningful_content(link_data):
    """Ignora tipo_links: evita INSERT só com o tipo preenchido."""
    for k, v in link_data.items():
        if k == "tipo_links":
            continue
        if _norm_link_field(v):
            return True
    return False


def _find_link_row_for_blueprint(unit_links, link_type, id_vgr, designador):
    """
    Localiza a linha de link a atualizar: mesma unidade e (ID VGR igual OU designador igual),
    com preferência pelo mesmo tipo e por registros com tipo vazio (evita duplicata do print).
    Se não houver ID/designador no formulário, usa o legado por tipo_links.
    """
    id_v = _norm_link_field(id_vgr)
    des = _norm_link_field(designador)

    def row_matches(r):
        rid = _norm_link_field(r.get("id_vgr_links"))
        rds = _norm_link_field(r.get("designador_links"))
        same_id = bool(id_v) and rid == id_v
        same_des = bool(des) and rds == des
        return same_id or same_des

    candidates = [r for r in unit_links if row_matches(r)]
    if not candidates:
        for r in unit_links:
            if r.get("tipo_links") == link_type:
                return r
        return None
    for r in candidates:
        if r.get("tipo_links") == link_type:
            return r
    for r in candidates:
        t = _norm_link_field(r.get("tipo_links"))
        if not t or t == "-":
            return r
    return candidates[0]

@prodesp_bp.route('/criar_blueprint')
@login_required
def criar_blueprint_prodesp_page():
    """
    Renderiza a página para criação de Blueprint do cliente PRODESP.
    """
    return render_template(
        'prodesp_criar_blueprint.html',
        blueprint_field_limits=blueprint_form_field_limits_for_template(),
        serial_model_rules=SERIAL_MODEL_FRAGMENTS_ORDERED,
        prodesp_mv_opcionais_fields=mv_opcionais_template_fields(),
        prodesp_lan_extra_fields=lan_extra_template_fields(),
        prodesp_mv_field_limits=blueprint_mv_opcionais_form_field_limits(),
        blueprint_acronimo_hint=_blueprint_acronimo_hint(),
    )

@prodesp_bp.route('/buscar_unidade_blueprint', methods=['POST'])
@login_required
def buscar_unidade_blueprint():
    """
    Busca os dados de uma unidade, seus equipamentos e links pelo id_vgr.
    """
    id_vgr = request.form.get('id_vgr')
    if not id_vgr:
        _flash_blueprint("Por favor, digite um ID VGR para buscar.", "warning")
        return redirect(url_for('prodesp.criar_blueprint_prodesp_page'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Buscar dados da Unidade
        cursor.execute(sql_select_unidades_by_id_vgr(), (id_vgr,))
        unidade = cursor.fetchone()

        if not unidade:
            _flash_blueprint(f"Nenhuma unidade encontrada com o ID VGR: {id_vgr}.", "danger")
            return redirect(url_for('prodesp.criar_blueprint_prodesp_page'))

        id_unidade = unidade['id_unidades']

        # 2. Buscar Equipamentos
        cursor.execute(sql_select_equipamentos_by_unidade(ativos_only=True, limit_one=False), (id_unidade,))
        equipamentos = cursor.fetchall()
        
        # 3. Buscar Links
        cursor.execute(sql_select_links_by_unidade(), (id_unidade,))
        links_db = cursor.fetchall()
        links = _links_dict_from_list(links_db)

        _flash_blueprint(f"Dados da unidade {id_vgr} carregados com sucesso!", "success")
        return render_template(
            'prodesp_criar_blueprint.html',
            unidade=unidade,
            equipamentos=equipamentos,
            links=links,
            blueprint_field_limits=blueprint_form_field_limits_for_template(),
            serial_model_rules=SERIAL_MODEL_FRAGMENTS_ORDERED,
            prodesp_mv_opcionais_fields=mv_opcionais_template_fields(),
            prodesp_lan_extra_fields=lan_extra_template_fields(),
            prodesp_mv_field_limits=blueprint_mv_opcionais_form_field_limits(),
            blueprint_acronimo_hint=_blueprint_acronimo_hint(),
        )

    except Exception as e:
        logging.error(f"prodesp - Erro ao buscar dados para blueprint {id_vgr}: {e}")
        _flash_blueprint("Erro ao buscar dados. Tente novamente ou contate o suporte.", "danger")
        return redirect(url_for('prodesp.criar_blueprint_prodesp_page'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@prodesp_bp.route('/gerar_blueprint_prodesp', methods=['POST'])
@login_required
def gerar_blueprint_prodesp_action():
    """
    Salva as alterações no banco de dados, registra no histórico e gera o arquivo CSV de Blueprint para PRODESP.
    """
    id_vgr = request.form.get('id_vgr_unidades')
    if not id_vgr:
        _flash_blueprint("ID VGR não fornecido.", "danger")
        return redirect(url_for('prodesp.criar_blueprint_prodesp_page'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(sql_select_unidades_by_id_vgr(), (id_vgr,))
        old_unidade = cursor.fetchone()
        if not old_unidade:
            _flash_blueprint("Unidade não encontrada.", "danger")
            return redirect(url_for('prodesp.criar_blueprint_prodesp_page'))

        id_unidade = old_unidade['id_unidades']

        ip_lan_transito = _sanitize_ip_field(request.form.get("mpls_ip_gateway"))
        unit_updates = _parse_blueprint_unit_updates(request.form, ip_lan_transito)

        preview = _load_blueprint_form_preview(cursor, id_vgr, request.form)
        if not preview:
            _flash_blueprint("Unidade não encontrada.", "danger")
            return redirect(url_for('prodesp.criar_blueprint_prodesp_page'))
        preview_unidade, preview_equipamento, preview_links = preview

        new_serial = (request.form.get('serial_equipamentos') or '').strip().upper()
        cursor.execute(sql_select_equipamentos_by_unidade(ativos_only=True, limit_one=True), (id_unidade,))
        old_eq = cursor.fetchone()

        if new_serial:
            eq_id = old_eq['id_equipamentos'] if old_eq else None
            vgr_colisao = buscar_colisao_serial_equipamento(cursor, new_serial, eq_id)
            if vgr_colisao:
                return _blueprint_error_page(
                    id_vgr,
                    request.form,
                    mensagem_serial_duplicado(new_serial, vgr_colisao),
                    cursor=cursor,
                )
            exige_padrao = unidade_tem_atendimento_exigindo_serial_padrao(cursor, id_unidade)
            fmt_serial = validate_serial_fortinet_para_blueprint(
                new_serial, exige_padrao=exige_padrao
            )
            if fmt_serial:
                return _blueprint_error_page(
                    id_vgr,
                    request.form,
                    fmt_serial,
                    cursor=cursor,
                )

        coord_errors = _validate_blueprint_coordinates(request.form)
        if coord_errors:
            return _blueprint_error_page(id_vgr, request.form, " ".join(coord_errors), cursor=cursor)

        limit_errors = validate_blueprint_form_limits(request.form)
        if limit_errors:
            return _blueprint_error_page(id_vgr, request.form, " ".join(limit_errors), cursor=cursor)

        is_valid, errors = validar_dados_blueprint(preview_unidade, preview_equipamento, preview_links)
        if not is_valid:
            error_msg = (
                "Não foi possível gerar o Blueprint. Faltam os seguintes dados obrigatórios: "
                + ", ".join(errors)
            )
            return _blueprint_error_page(id_vgr, request.form, error_msg, cursor=cursor)

        uniq_link_errs = find_batch_link_uniqueness_errors(
            cursor,
            preview_links,
            id_unidade=id_unidade,
        )
        if uniq_link_errs:
            return _blueprint_error_page(
                id_vgr,
                request.form,
                " ".join(uniq_link_errs),
                cursor=cursor,
            )

        uniq_lb_errs = find_loopback_uniqueness_errors(
            cursor,
            {
                "loopback_vivo_unidades": unit_updates.get("loopback_vivo_unidades"),
                "loopback_cliente_unidades": unit_updates.get("loopback_cliente_unidades"),
                "loopback_on_bgp_unidades": unit_updates.get("loopback_on_bgp_unidades"),
            },
            exclude_unidade_id=id_unidade,
        )
        if uniq_lb_errs:
            return _blueprint_error_page(
                id_vgr,
                request.form,
                " ".join(uniq_lb_errs),
                cursor=cursor,
            )

        new_versao = (request.form.get('versao_equipamentos') or '').strip() or None
        new_modelo = infer_modelo_equipamento_from_serial(new_serial) if new_serial else ''

        for col, new_val in unit_updates.items():
            old_val = old_unidade.get(col)
            if str(new_val or '') != str(old_val or ''):
                cursor.execute(f"UPDATE unidades SET `{col}` = %s WHERE id_unidades = %s", (new_val, id_unidade))
                registrar_log(conn, 'unidades', id_unidade, col, old_val, new_val, 'UPDATE')

        if old_eq:
            eq_id = old_eq['id_equipamentos']
            for col, new_val in (
                ('serial_equipamentos', new_serial),
                ('versao_equipamentos', new_versao),
                ('modelo_equipamentos', new_modelo),
            ):
                old_val = old_eq.get(col)
                if str(new_val or '') != str(old_val or ''):
                    cursor.execute(f"UPDATE equipamentos SET `{col}` = %s WHERE id_equipamentos = %s", (new_val, eq_id))
                    registrar_log(conn, 'equipamentos', eq_id, col, old_val, new_val, 'UPDATE')
        elif new_serial:
            # Re-lê antes do INSERT (duplo clique / race): outro request pode ter criado o eq.
            cursor.execute(
                sql_select_equipamentos_by_unidade(ativos_only=True, limit_one=True),
                (id_unidade,),
            )
            raced = cursor.fetchone()
            if raced:
                old_eq = raced
                eq_id = old_eq["id_equipamentos"]
                for col, new_val in (
                    ("serial_equipamentos", new_serial),
                    ("versao_equipamentos", new_versao),
                    ("modelo_equipamentos", new_modelo),
                ):
                    old_val = old_eq.get(col)
                    if str(new_val or "") != str(old_val or ""):
                        cursor.execute(
                            f"UPDATE equipamentos SET `{col}` = %s WHERE id_equipamentos = %s",
                            (new_val, eq_id),
                        )
                        registrar_log(conn, "equipamentos", eq_id, col, old_val, new_val, "UPDATE")
            else:
                try:
                    cursor.execute(
                        "INSERT INTO equipamentos (id_unidades_equipamentos, serial_equipamentos, modelo_equipamentos, versao_equipamentos) VALUES (%s, %s, %s, %s)",
                        (id_unidade, new_serial, new_modelo or "FortiGate 70F", new_versao),
                    )
                    new_id = cursor.lastrowid
                    registrar_log(
                        conn, "equipamentos", new_id, "serial_equipamentos", None, new_serial, "INSERT"
                    )
                except Exception as insert_exc:
                    if not _is_mysql_duplicate_key(insert_exc):
                        raise
                    # UNIQUE serial: outro request ganhou a corrida — reaproveita se for a mesma unidade.
                    vgr_colisao = buscar_colisao_serial_equipamento(cursor, new_serial, None)
                    cursor.execute(
                        sql_select_equipamentos_by_unidade(ativos_only=True, limit_one=True),
                        (id_unidade,),
                    )
                    same_unit_eq = cursor.fetchone()
                    if same_unit_eq and (
                        str(same_unit_eq.get("serial_equipamentos") or "").strip().upper() == new_serial
                    ):
                        pass  # idempotente: segue geração com o equipamento já gravado
                    else:
                        return _blueprint_error_page(
                            id_vgr,
                            request.form,
                            mensagem_serial_duplicado(new_serial, vgr_colisao or "—"),
                            cursor=cursor,
                        )

        for link_type in ('MPLS', 'STATIC'):
            cursor.execute(sql_select_links_by_unidade(), (id_unidade,))
            unit_links_now = cursor.fetchall()
            old_link = _resolve_blueprint_existing_link(
                unit_links_now, link_type, request.form
            )
            link_data = _parse_blueprint_link_data(request.form, link_type, old_link)
            old_link = _resolve_blueprint_existing_link(
                unit_links_now, link_type, request.form, link_data
            )

            if old_link:
                updates = []
                params = []
                for col, val in link_data.items():
                    if str(val or '') != str(old_link.get(col) or ''):
                        updates.append(f"`{col}` = %s")
                        params.append(val)
                        registrar_log(conn, 'links', old_link['id_link'], col, old_link.get(col), val, 'UPDATE')
                if updates:
                    sql = f"UPDATE links SET {', '.join(updates)} WHERE id_link = %s"
                    cursor.execute(sql, (*params, old_link['id_link']))
            elif _link_form_has_meaningful_content(link_data):
                cols = ", ".join([f"`{k}`" for k in link_data.keys()] + ["id_unidades_links"])
                placeholders = ", ".join(["%s"] * (len(link_data) + 1))
                vals = list(link_data.values()) + [id_unidade]
                cursor.execute(f"INSERT INTO links ({cols}) VALUES ({placeholders})", vals)
                new_id = cursor.lastrowid
                registrar_log(conn, 'links', new_id, 'tipo_links', None, link_type, 'INSERT')

        cursor.execute(sql_select_unidades_by_id(), (id_unidade,))
        unidade = cursor.fetchone()
        cursor.execute(sql_select_equipamentos_by_unidade(ativos_only=True, limit_one=True), (id_unidade,))
        equipamento = cursor.fetchone() or {}
        cursor.execute(sql_select_links_by_unidade(), (id_unidade,))
        links = cursor.fetchall()

        arquivo_completo = gerar_csv_blueprint_prodesp(unidade, equipamento, links)
        filename = os.path.basename(arquivo_completo)

        registrar_log(conn, 'unidades', id_unidade, 'blueprint_gerado', None, filename, 'INSERT')
        conn.commit()

        try:
            from prodesp.app import _prodesp_mutations_cache_bust

            _prodesp_mutations_cache_bust()
        except Exception:
            pass

        _flash_blueprint(f"Dados atualizados e Blueprint '{filename}' gerado com sucesso!", "success")
        download_link = url_for('prodesp.download_prodesp_blueprint', filename=filename)
        return _render_blueprint_page(unidade, equipamento, links, download_link=download_link)

    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"prodesp - Erro ao salvar e gerar blueprint para {id_vgr}: {e}")
        err_msg = _blueprint_exception_message(e)
        if id_vgr and request.form:
            return _blueprint_error_page(id_vgr, request.form, err_msg, cursor=cursor)
        _flash_blueprint(err_msg, "danger")
        return redirect(url_for('prodesp.criar_blueprint_prodesp_page'))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@prodesp_bp.route('/api/preview_blueprint_prodesp/<id_vgr>', methods=['GET', 'POST'])
@login_required
def api_preview_blueprint_prodesp(id_vgr):
    """Prévia para modal de confirmação (hostname, LANs, máscaras, device BP + motivo).

    Body JSON:
    - ``form``: campos do formulário Criar Blueprint (mesma montagem do submit final);
    - ``overrides``: ajustes do modal (hostname/LAN/máscara/serial) sobre a prévia.
    Sem ``form``, mantém o caminho legado (banco + overrides de unidade/equipamento).
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql_select_unidades_by_id_vgr(), (id_vgr,))
        unidade = cursor.fetchone()
        if not unidade:
            return jsonify({"success": False, "message": "Unidade não encontrada."}), 404

        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            body = {}
        form_payload = body.get("form") if isinstance(body.get("form"), dict) else None
        overrides = body.get("overrides") if isinstance(body.get("overrides"), dict) else {}

        if form_payload is not None:
            preview = _load_blueprint_form_preview(cursor, id_vgr, form_payload)
            if not preview:
                return jsonify({"success": False, "message": "Unidade não encontrada."}), 404
            preview_unidade, preview_equipamento, preview_links = preview
            unidade_adj, _mask_logs = apply_blueprint_confirm_overrides(
                preview_unidade, overrides
            )
            equipamento_adj = apply_blueprint_equipamento_overrides(
                preview_equipamento, overrides
            )
            links_adj = preview_links
        else:
            id_unidade = unidade["id_unidades"]
            cursor.execute(
                sql_select_equipamentos_by_unidade(ativos_only=True, limit_one=True),
                (id_unidade,),
            )
            equipamento = cursor.fetchone() or {}
            cursor.execute(sql_select_links_by_unidade(), (id_unidade,))
            links = cursor.fetchall()
            unidade_adj, _mask_logs = apply_blueprint_confirm_overrides(unidade, overrides)
            equipamento_adj = apply_blueprint_equipamento_overrides(equipamento, overrides)
            links_adj = links

        is_valid, errors = validar_dados_blueprint(
            unidade_adj, equipamento_adj, links_adj
        )
        payload = build_blueprint_confirm_payload(
            unidade_adj, equipamento_adj, links_adj
        )
        payload["valid"] = is_valid
        payload["errors"] = errors
        return jsonify({"success": True, "confirm": payload})
    except Exception:
        logging.exception("prodesp - Erro no preview de blueprint para %s", id_vgr)
        return jsonify({
            "success": False,
            "message": "Não foi possível montar a confirmação do blueprint.",
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@prodesp_bp.route('/api/gerar_blueprint_prodesp/<id_vgr>', methods=['POST'])
@login_required
def api_gerar_blueprint_prodesp(id_vgr):
    """
    API para gerar o Blueprint a partir de um ID VGR.
    Body JSON opcional: { confirm: true, overrides: { hostname, ip_lan_*, mask_lan* } }.
    Sem confirm=true devolve a prévia (compatível com fluxo antigo via confirm no 2º passo).
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            body = {}
        confirm = bool(body.get("confirm"))
        overrides = body.get("overrides") if isinstance(body.get("overrides"), dict) else {}

        # 1. Buscar dados
        cursor.execute(sql_select_unidades_by_id_vgr(), (id_vgr,))
        unidade = cursor.fetchone()
        if not unidade:
            return jsonify({'success': False, 'message': 'Unidade não encontrada.'}), 404

        id_unidade = unidade['id_unidades']
        
        cursor.execute(sql_select_equipamentos_by_unidade(ativos_only=True, limit_one=True), (id_unidade,))
        equipamento = cursor.fetchone() or {}

        cursor.execute(sql_select_links_by_unidade(), (id_unidade,))
        links = cursor.fetchall()

        unidade_adj, mask_logs = apply_blueprint_confirm_overrides(unidade, overrides)
        equipamento_adj = apply_blueprint_equipamento_overrides(equipamento, overrides)

        serial_eq = (equipamento_adj.get("serial_equipamentos") or "").strip().upper()
        if serial_eq:
            vgr_colisao = buscar_colisao_serial_equipamento(
                cursor,
                serial_eq,
                equipamento_adj.get("id_equipamentos") or equipamento.get("id_equipamentos"),
            )
            if vgr_colisao:
                return jsonify({
                    'success': False,
                    'message': mensagem_serial_duplicado(serial_eq, vgr_colisao),
                }), 400
            exige_padrao = unidade_tem_atendimento_exigindo_serial_padrao(cursor, id_unidade)
            fmt_serial = validate_serial_fortinet_para_blueprint(
                serial_eq, exige_padrao=exige_padrao
            )
            if fmt_serial:
                return jsonify({"success": False, "message": fmt_serial}), 400

        if not confirm:
            is_valid, errors = validar_dados_blueprint(unidade_adj, equipamento_adj, links)
            payload = build_blueprint_confirm_payload(unidade_adj, equipamento_adj, links)
            payload["valid"] = is_valid
            payload["errors"] = errors
            return jsonify({
                "success": True,
                "needs_confirm": True,
                "confirm": payload,
            })

        # 2. Validar dados obrigatórios antes de gerar
        is_valid, errors = validar_dados_blueprint(unidade_adj, equipamento_adj, links)
        if not is_valid:
            error_msg = "Não foi possível gerar o Blueprint. Faltam os seguintes dados obrigatórios: " + ", ".join(errors)
            return jsonify({'success': False, 'message': error_msg}), 400

        uniq_link_errs = find_batch_link_uniqueness_errors(
            cursor,
            links,
            id_unidade=id_unidade,
        )
        if uniq_link_errs:
            return jsonify({
                'success': False,
                'message': uniq_link_errs[0],
                'errors': uniq_link_errs,
            }), 400

        uniq_lb_errs = find_loopback_uniqueness_errors(
            cursor,
            {
                "loopback_vivo_unidades": unidade_adj.get("loopback_vivo_unidades"),
                "loopback_cliente_unidades": unidade_adj.get("loopback_cliente_unidades"),
                "loopback_on_bgp_unidades": unidade_adj.get("loopback_on_bgp_unidades"),
            },
            exclude_unidade_id=id_unidade,
        )
        if uniq_lb_errs:
            return jsonify({
                'success': False,
                'message': uniq_lb_errs[0],
                'errors': uniq_lb_errs,
            }), 400

        # Persistir hostname/IPs alterados na confirmação + máscaras (CIDR)
        persist_cols = (
            "hostname_unidades",
            "ip_lan_01_unidades",
            "mv_ip_lan_sec_unidades",
            "mv_ip_lan_ter_unidades",
            "mv_ip_lan_qua_unidades",
            "mv_rede_lan_sec_unidades",
            "mv_rede_lan_ter_unidades",
            "mv_rede_lan_qua_unidades",
        )
        for col in persist_cols:
            new_val = unidade_adj.get(col)
            old_val = unidade.get(col)
            if str(new_val or "") != str(old_val or ""):
                cursor.execute(
                    f"UPDATE unidades SET `{col}` = %s WHERE id_unidades = %s",
                    (new_val, id_unidade),
                )
                registrar_log(conn, "unidades", id_unidade, col, old_val, new_val, "UPDATE")

        for mlog in mask_logs:
            registrar_log(
                conn,
                "unidades",
                id_unidade,
                mlog["campo"],
                mlog["antigo"],
                mlog["novo"],
                "UPDATE",
            )

        # 3. Gerar CSV
        arquivo_completo = gerar_csv_blueprint_prodesp(unidade_adj, equipamento_adj, links)
        filename = os.path.basename(arquivo_completo)
        
        # 3. Registrar Log
        registrar_log(conn, 'unidades', id_unidade, 'blueprint_gerado', None, filename, 'INSERT')
        conn.commit()

        try:
            from prodesp.app import _prodesp_mutations_cache_bust

            _prodesp_mutations_cache_bust()
        except Exception:
            pass

        return jsonify({
            'success': True,
            'message': f"Blueprint '{filename}' gerado com sucesso!",
            'download_url': url_for('prodesp.download_prodesp_blueprint', filename=filename)
        })

    except Exception as e:
        logging.exception("prodesp - Erro na API de blueprint para %s", id_vgr)
        return jsonify({
            'success': False,
            'message': 'Não foi possível gerar o blueprint. Tente novamente ou contate o suporte.',
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@prodesp_bp.route('/download/blueprint/<filename>')
@login_required
def download_prodesp_blueprint(filename):
    """
    Download do blueprint gerado.
    """
    if not filename or os.path.basename(filename) != filename:
        return jsonify(success=False, message="Arquivo inválido."), 400
    safe_path = safe_join(CSV_DIR, filename)
    if safe_path is None or not os.path.isfile(safe_path):
        return jsonify(success=False, message="Arquivo não encontrado."), 404
    return send_from_directory(CSV_DIR, filename, as_attachment=True)
