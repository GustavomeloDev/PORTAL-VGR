# =================================================================================
# IMPORTS E CONFIGURAÇÕES INICIAIS
# =================================================================================
import os
import threading
import unicodedata
from core.logger import get_logger
from core.utils.timing import with_server_ms
import csv
from flask import Flask, abort, current_app, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from core.portal_flash import portal_flash
from flask_login import login_required, current_user
from collections import defaultdict
from datetime import datetime, timedelta, time, date
import pandas as pd
import io
from werkzeug.datastructures import Headers
from flask import Response
 
import pytz
import mysql.connector
from mysql.connector import Error
from werkzeug.utils import safe_join
from .prodesp.historico import registrar_log
from .prodesp.dashboard_select import sql_select_atendimento_by_id
from .prodesp.entity_select import (
    sql_select_link_by_id_and_unidade,
    sql_select_links_by_unidade,
    sql_select_unidades_by_id,
    sql_select_unidades_by_id_vgr,
)
from .credentials.db_connection import get_prodesp_db_connection
from .prodesp.endereco_enriquecimento import enriquecer_endereco_unidade
from .prodesp.db_field_limits import (
    UNIDADES_CIDR_DB_COLUMNS,
    UNIDADES_LAN_EXTRA_DB_COLUMNS,
    UNIDADES_MV_OPCIONAIS_DB_COLUMNS,
    blueprint_mv_opcionais_form_field_limits,
    form_field_limits_for_template,
    lan_extra_template_fields,
    message_from_mysql_exception,
    mv_opcionais_template_fields,
    normalize_coordinate_for_db,
    normalize_estado_unidade,
    sanitize_ip_cidr_field,
    sanitize_plain_ipv4_field,
    unidades_lan_extra_js_to_db,
    unidades_lan_extra_sql_select,
    unidades_mv_opcionais_js_to_db,
    unidades_mv_opcionais_sql_select,
    validate_coordinate_for_db,
    validate_create_payload,
    validate_equipamento_fields,
    validate_estado_unidade,
    validate_link_fields,
    validate_observacao_text,
    validate_update_field,
)
from .prodesp.blueprint.link_vivo_rules import normalize_link_api_payload
from .prodesp.link_uniqueness_rules import (
    find_link_uniqueness_errors,
    find_loopback_uniqueness_errors,
)
from .prodesp.sensitive_fields_crypto import (
    decrypt_export_links_cell,
    decrypt_export_telefone_cell,
    decrypt_sensitive_db_column,
    decrypt_sensitive_row_inplace,
    decrypt_sensitive_rows_inplace,
    encrypt_link_pppoe_db_dict,
    encrypt_sensitive_db_column,
    is_sensitive_db_column,
    sensitive_values_equal_for_db,
)
from .prodesp.blueprint.agendamento_csv_notifier import (
    AgendamentoCsvLinha,
    AgendamentoCsvRelatorio,
    build_resumo_from_relatorio,
    erro_linha,
    linha_from_row,
    parse_rejeitadas_previa_payload,
    send_agendamento_csv_report,
)
from .prodesp.blueprint.prodesp_equipment import (
    infer_modelo_equipamento_from_serial,
    SERIAL_MODEL_FRAGMENTS_ORDERED,
)
from .prodesp.atendimento_business_rules import (
    FINAL_STATUSES_ATENDIMENTO,
    STATUS_QUEBRA_TBRA,
    SUBSTATUS_AGUARDA_CONTRATADA,
    SUBSTATUS_AGUARDA_LICENCA,
    SUBSTATUS_AGUARDA_EXTERNO,
    SUBSTATUS_AGUARDA_GESTAO,
    SUBSTATUS_COM_SUPORTE,
    SUBSTATUS_INICIAL_FILA,
    SUBSTATUS_LEGACY_TRIAGEM,
    SUBSTATUS_EDICAO_AGENDAMENTO_GP,
    SUBSTATUS_QUEBRA_TBRA_SCI,
    SUBSTATUS_QUEBRA_TBRA_TECNICA,
    SUBSTATUS_QUEBRA_TBRA_VALUES,
    analista_coluna_para_substatus,
    avaliar_create_atendimento_duplicado,
    check_analista_mpls_em_config_mpls,
    check_atendimento_substatus_update,
    check_dados_field_create_em_atendimento,
    check_dados_field_triagem_para_fila_aguardando,
    check_hostname_obrigatorio_transicao,
    check_observacao_quebra_encerramento,
    check_observacao_substatus_transicao,
    observacao_quebra_encerramento_explicita,
    observacoes_payload_para_validacao_transicao,
    observacoes_transicao_explicitas_no_request,
    deve_registrar_analista_agendamento_gestao,
    is_retorno_de_fila,
    colunas_analista_liberar_substatus_transicao,
    is_substatus_gestao,
    is_substatus_quebra_normal,
    normalizar_substatus_fluxo,
    mensagem_substatus_obrigatorio_quebra,
    substatus_conta_como_gestao_kpi,
    update_envolve_substatus_ou_analista,
    row_api_para_validacao_edicao,
    validar_edicao_atendimento as _validar_edicao_atendimento_rules,
    validar_edicao_observacao_atendimento as _validar_edicao_observacao_atendimento_rules,
    validar_substatus_create_ag_gp,
)
 
from flask import Blueprint

# Configuração básica de logging
logging = get_logger("PRODESP")
 
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))
RESTORE_DIR = os.path.join(BASE_DIR, "restore")
CSV_DIR = os.path.join(BASE_DIR, "static", "csv_prodesp")

if not os.path.exists(CSV_DIR):
    os.makedirs(CSV_DIR)


prodesp_bp = Blueprint(
    'prodesp', __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/prodesp',
)


@prodesp_bp.before_request
def _prodesp_enforce_projeto_acesso():
    """SEC-004: exige acesso ao projeto PRODESP (card ou admin/supervisão)."""
    from login.portal_project_access import PROJETO_PRODESP, usuario_tem_acesso_modulo

    if request.endpoint and request.endpoint.endswith(".static"):
        return None
    if request.path.startswith(f"{prodesp_bp.url_prefix or ''}/static"):
        return None
    if not current_user.is_authenticated:
        return None
    if usuario_tem_acesso_modulo(current_user, PROJETO_PRODESP):
        return None
    msg = "Acesso negado ao módulo PRODESP."
    if request.is_json or (
        request.accept_mimetypes.best_match(["application/json", "text/html"])
        == "application/json"
    ):
        return jsonify(success=False, message=msg), 403
    portal_flash(msg, "warning", scope="login")
    return redirect(url_for("login.pos_login"))

# Perfis com menu GESTÃO (exceto dashboard restrito a não–só-implantação).
_PRODESP_PERFIS_MENU_GESTAO = frozenset({
    "SUPERVISORES",
    "GP",
    "AGENDAMENTO",
})

from prodesp.prodesp.agendamento_csv_import_service import processar_importacao_agendamento_csv
from prodesp.prodesp.agendamento_csv_validacao import (
    CONTRATADAS_PERMITIDAS,
    MSG_DUPLICATA_VGR,
    csv_valor_ausente as _prodesp_csv_valor_ausente,
    data_agendamento_anterior_hoje as _prodesp_data_agendamento_anterior_hoje,
    motivo_agendamento_csv_corrigivel,
    validar_agendamento_csv_linha as _validar_agendamento_csv_linha,
    validar_contratada_planejada as _prodesp_validar_contratada_planejada,
)

PRODESP_QUEBRA_MASSA_FIELD_PADRAO = "-"
PRODESP_QUEBRA_MASSA_CONTATO_PADRAO = "00000000000"


def _prodesp_normalizar_contato_field_planejado(val):
    """Somente dígitos, alinhado ao modal de atendimento (máx. 20)."""
    if val is None:
        return None
    digits = "".join(c for c in str(val) if c.isdigit())
    return digits[:20] if digits else None


def _prodesp_resolver_dados_field_quebra_massa(unidade):
    """
    Dados de field para quebra em massa: contratada do agendamento;
    field ausente → «-»; contato inválido/ausente → 11 zeros.
    Retorna (contratada, field, contato, erro).
    """
    contratada_canonica, err_contratada = _prodesp_validar_contratada_planejada(
        unidade.get('contratada_planejada_unidades')
    )
    if err_contratada:
        return None, None, None, err_contratada

    field_val = (unidade.get('field_planejada_unidades') or '').strip() or PRODESP_QUEBRA_MASSA_FIELD_PADRAO
    contato_val = _prodesp_normalizar_contato_field_planejado(
        unidade.get('contato_field_planejada_unidades')
    )
    if not contato_val or len(contato_val) < 10 or len(contato_val) > 11:
        contato_val = PRODESP_QUEBRA_MASSA_CONTATO_PADRAO
    return contratada_canonica, field_val, contato_val, None


def _prodesp_data_hora_atendimento_quebra_massa(unidade):
    """Data/hora do atendimento de quebra = data (e hora) do agendamento da unidade."""
    bruto_data = unidade.get('data_agendamento_unidades')
    if bruto_data is None:
        return None, None, None, 'Unidade sem data de agendamento.'
    if isinstance(bruto_data, datetime):
        agendamento_date = bruto_data.date()
    elif isinstance(bruto_data, date):
        agendamento_date = bruto_data
    else:
        try:
            agendamento_date = datetime.strptime(str(bruto_data)[:10], '%Y-%m-%d').date()
        except ValueError:
            return None, None, None, 'Data de agendamento inválida.'

    hora_str = normalize_hora_agendamento_db(unidade.get('hora_agendamento_unidades')) or '00:00:00'
    data_atendimentos_str = f"{agendamento_date.strftime('%Y-%m-%d')} {hora_str}"
    return data_atendimentos_str, hora_str, agendamento_date, None


def _prodesp_quebra_massa_dedupe_ids_vgr(ids_vgr):
    """Remove VGRs vazios/duplicados preservando a ordem."""
    seen = set()
    out = []
    for raw in ids_vgr or []:
        id_vgr = str(raw or "").strip()
        if not id_vgr or id_vgr in seen:
            continue
        seen.add(id_vgr)
        out.append(id_vgr)
    return out


def _prodesp_quebra_massa_processar_unidade(
    cur,
    conn,
    *,
    id_vgr,
    status,
    substatus,
    texto_obs,
    analista,
):
    """
    Cria um atendimento de quebra para uma unidade agendada.
    Transação curta por VGR (commit interno) para reduzir lock wait em lote.
    Retorna (criado_dict | None, mensagem_erro | None).
    """
    try:
        conn.start_transaction()
        cur.execute(
            """
            SELECT id_unidades, data_agendamento_unidades, hora_agendamento_unidades,
                   contratada_planejada_unidades,
                   field_planejada_unidades, contato_field_planejada_unidades
            FROM unidades WHERE TRIM(id_vgr_unidades) = %s
            FOR UPDATE
            """,
            (id_vgr,),
        )
        unidade = cur.fetchone()
        if not unidade:
            conn.rollback()
            return None, f"VGR {id_vgr}: unidade não encontrada."

        decrypt_sensitive_row_inplace(unidade)

        if not unidade.get("data_agendamento_unidades"):
            conn.rollback()
            return None, f"VGR {id_vgr}: unidade não está agendada."

        id_unidade = unidade["id_unidades"]
        data_atend_str, hora_atend_str, agendamento_date, err_data = (
            _prodesp_data_hora_atendimento_quebra_massa(unidade)
        )
        if err_data:
            conn.rollback()
            return None, f"VGR {id_vgr}: {err_data}"

        cur.execute(
            """
            SELECT 1 FROM atendimentos
            WHERE id_unidades_atendimentos = %s
              AND DATE(data_atendimentos) >= %s
            LIMIT 1
            """,
            (id_unidade, agendamento_date),
        )
        if cur.fetchone():
            conn.rollback()
            return None, f"VGR {id_vgr}: já possui atendimento na data do agendamento."

        contratada_val, field_val, contato_val, err_dados = _prodesp_resolver_dados_field_quebra_massa(
            unidade
        )
        if err_dados:
            conn.rollback()
            return None, f"VGR {id_vgr}: {err_dados}"

        insert_data = {
            "status_atendimentos": status,
            "substatus_atendimentos": substatus,
            "analista_atuante_atendimentos": analista,
            "analista_configuracao_atendimentos": "",
            "analista_mpls_atendimentos": "",
            "analista_caderno_teste_atendimentos": "",
            "contratada_atendimentos": contratada_val,
            "field_atendimentos": field_val,
            "contato_field_atendimentos": encrypt_sensitive_db_column(
                "contato_field_atendimentos", contato_val
            ),
            "logs_atendimentos": "",
            "id_unidades_atendimentos": id_unidade,
            "data_atendimentos": data_atend_str,
            "horario_inicio_atendimentos": hora_atend_str,
            "horario_finalizacao_atendimentos": hora_atend_str,
        }
        cols = "`, `".join(insert_data.keys())
        placeholders = ", ".join(["%s"] * len(insert_data))
        cur.execute(
            f"INSERT INTO atendimentos (`{cols}`) VALUES ({placeholders})",
            list(insert_data.values()),
        )
        new_id = cur.lastrowid
        _prodesp_vincular_observacoes_unidade_ao_atendimento(cur, conn, id_unidade, new_id)
        obs_ts = parse_date_string(data_atend_str, current_app.logger, new_id) or data_atend_str
        cur.execute(
            """
            INSERT INTO observacoes
                (id_unidades_observacoes, observacoes, timestamp_observacoes, id_atendimentos_observacoes)
            VALUES (%s, %s, %s, %s)
            """,
            (id_unidade, texto_obs, obs_ts, new_id),
        )
        registrar_log(conn, "atendimentos", new_id, "Observação", None, texto_obs, "INSERT")
        registrar_log(
            conn,
            "atendimentos",
            new_id,
            "status_atendimentos",
            None,
            f"Quebra em massa ({new_id})",
            "INSERT",
        )
        conn.commit()
        return {"id_vgr": id_vgr, "id_atendimento": new_id}, None
    except Error as e:
        try:
            conn.rollback()
        except Error:
            pass
        if getattr(e, "errno", None) == 1205:
            return None, (
                f"VGR {id_vgr}: registro em uso por outra operação. "
                "Aguarde e tente novamente (evite cliques duplicados)."
            )
        raise


def _prodesp_aplicar_planejado_em_row_agendado(row):
    """Expõe campos planejados da unidade nos nomes usados pelo dashboard/KPI."""
    if row.get("id_atendimentos") is not None:
        return
    row["contratada_atendimentos"] = row.get("contratada_planejada_unidades") or ""
    row["field_atendimentos"] = row.get("field_planejada_unidades") or ""
    row["contato_field_atendimentos"] = (
        decrypt_sensitive_db_column(
            "contato_field_planejada_unidades",
            row.get("contato_field_planejada_unidades"),
        )
        or ""
    )


# =================================================================================
# FUNÇÕES AUXILIARES - TEMPO/DATA ATENDIMENTO
# =================================================================================

def get_db_connection(*, use_pool: bool | None = None):
    return get_prodesp_db_connection(use_pool=use_pool)


def get_db_connection_long_running():
    """Relatórios e exports: conexão direta (não segura slot do pool entre SQL e pandas)."""
    return get_prodesp_db_connection(use_pool=False)


# Catálogo Device Blueprint (secretarias) — loader DB + cache de processo.
try:
    from prodesp.prodesp.blueprint.blueprint_secretaria_repo import ensure_db_loader_registered

    ensure_db_loader_registered(get_db_connection)
except Exception:
    pass


def _prodesp_json_error(exc, *, log, action: str, entity_id=None, **extra_json):
    """Mensagem amigável + log adequado (warning para erro de dados, exception para falha interna)."""
    msg, is_client = message_from_mysql_exception(exc)
    payload = {"message": msg, "success": False, **extra_json}
    if is_client:
        log.warning("prodesp - %s (id=%s): %s", action, entity_id, exc)
        return jsonify(payload), 400
    log.exception("prodesp - %s (id=%s)", action, entity_id)
    return jsonify(payload), 500


def _prodesp_is_admin(user):
    try:
        return int(getattr(user, "admin_user", 0) or 0) == 1
    except (TypeError, ValueError):
        return False


def _prodesp_status_concluido(status) -> bool:
    """Alinhado ao filtro da fila: não-admin não vê concluídos na tabela."""
    s = (str(status or "").strip().lower())
    return s in ("concluido", "concluído")


def _prodesp_hook_certificado_auto_export(
    id_atendimento,
    *,
    acronimo,
    old_status,
    old_substatus,
    new_status,
    new_substatus,
):
    """Dispara exportação automática de certificado após Concluído/Concluído (não bloqueia o save)."""
    try:
        from prodesp.prodesp.caderno.certificado_auto_export import (
            tentar_agendar_exportacao_certificado_automatica,
        )

        tentar_agendar_exportacao_certificado_automatica(
            id_atendimento,
            acronimo=acronimo,
            old_status=old_status,
            old_substatus=old_substatus,
            new_status=new_status,
            new_substatus=new_substatus,
        )
    except Exception as exc:
        logging.warning("certificado auto-export hook atendimento=%s: %s", id_atendimento, exc)


def _prodesp_ultima_data_atendimento_concluido(cursor, id_unidade):
    """Data do último atendimento com status Concluído da unidade, ou None."""
    cursor.execute(
        """
        SELECT data_atendimentos, status_atendimentos
        FROM atendimentos
        WHERE id_unidades_atendimentos = %s
        ORDER BY data_atendimentos DESC
        """,
        (id_unidade,),
    )
    for row in cursor.fetchall() or []:
        if not _prodesp_status_concluido(row.get("status_atendimentos")):
            continue
        bruto = row.get("data_atendimentos")
        if bruto is None:
            continue
        if isinstance(bruto, datetime):
            return bruto.date()
        if isinstance(bruto, date):
            return bruto
        try:
            return datetime.strptime(str(bruto)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def _prodesp_mensagem_bloqueio_agenda_unidade_concluida(data_concluido) -> str:
    if not data_concluido:
        return "Unidade já possui atendimento concluído."
    return f"Unidade já possui atendimento concluído em {data_concluido.strftime('%d/%m/%Y')}."


def _prodesp_csv_linha_export_dict(linha: AgendamentoCsvLinha) -> dict:
    motivo = (linha.detalhe or "").strip()
    return {
        'id_vgr': linha.id_vgr,
        'data_agendamento': linha.data_agendamento,
        'hora_agendamento': linha.hora_agendamento,
        'contratada': linha.contratada,
        'field': linha.field,
        'contato_field': linha.contato_field,
        'motivo': motivo,
        'corrigivel': motivo_agendamento_csv_corrigivel(motivo),
    }


def _prodesp_resposta_leitura_concluido(id_atendimento, user):
    """
    SEC-005 (PRODESP): bloqueia leitura de concluído na fila operacional para perfil
    somente IMPLANTAÇÃO, exceto analista atuante/secundário (painel analista / open_view).
    Admin e perfis de gestão (Agendamento, GP, SUPERVISORES) podem abrir no dashboard.
    Retorna (response, status_code) ou None se permitido.
    """
    if _prodesp_is_admin(user):
        return None
    if _prodesp_pode_acessar_dashboard_gestao(user):
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT status_atendimentos FROM atendimentos WHERE id_atendimentos = %s",
            (id_atendimento,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Atendimento não encontrado."), 404
        if _prodesp_status_concluido(row[0]):
            from login.portal_project_access import (
                PROJETO_PRODESP,
                usuario_pode_leitura_atendimento,
            )

            permitido, _motivo = usuario_pode_leitura_atendimento(
                user, PROJETO_PRODESP, id_atendimento
            )
            if not permitido:
                return jsonify(success=False, message="Atendimento não disponível."), 404
    finally:
        cursor.close()
        conn.close()
    return None


def _prodesp_is_agendamento_ou_gp(user):
    """GP/Agendamento com regras restritas de fila (não aplica se também for IMPLANTAÇÃO)."""
    if hasattr(user, "usa_regras_edicao_gp_agendamento_restritas"):
        return user.usa_regras_edicao_gp_agendamento_restritas()
    from login.portal_access_config import usuario_usa_regras_edicao_gp_agendamento_restritas

    return usuario_usa_regras_edicao_gp_agendamento_restritas(user)


def _prodesp_usuario_apenas_implantacao(user):
    """
    True se o usuário é somente analista IMPLANTAÇÃO (sem GP/SUPERVISORES/Agendamento/admin).
    Usado para bloquear dashboard de gestão.
    """
    if _prodesp_is_admin(user):
        return False
    from login.portal_access_config import DEPT_IMPLANTACAO, departamentos_do_usuario

    depts = departamentos_do_usuario(user)
    if depts & _PRODESP_PERFIS_MENU_GESTAO:
        return False
    return DEPT_IMPLANTACAO in depts


def _prodesp_pode_acessar_dashboard_gestao(user):
    """Dashboard PRODESP: GP, SUPERVISORES, Agendamento, admin; não perfil só IMPLANTAÇÃO."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return not _prodesp_usuario_apenas_implantacao(user)


def _prodesp_pode_operar_atendimentos_na_gestao(user):
    """SUPERVISORES/GP, Agendamento e admin podem criar/editar atendimentos na tela Gestão."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _prodesp_is_admin(user):
        return True
    return _prodesp_is_agendamento_ou_gp(user)


def _prodesp_pode_ver_menu_gestao(user):
    """Submenu GESTÃO (CSV, massa, dashboard quando permitido). Oculto para perfil só IMPLANTAÇÃO."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _prodesp_is_admin(user):
        return True
    return not _prodesp_usuario_apenas_implantacao(user)


def _prodesp_negar_api_menu_gestao():
    """403 JSON alinhado à página csv_manager (perfis exceto só IMPLANTAÇÃO)."""
    return jsonify(
        success=False,
        msg="Esta área não está disponível para o perfil Implantação.",
    ), 403


_csv_agendamento_upload_ultimo_por_usuario: dict[int, float] = {}


def _prodesp_csv_agendamento_rate_limit_segundos() -> int:
    raw = (os.getenv("PRODESP_CSV_UPLOAD_MIN_INTERVAL_SEC") or "120").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 120


def _prodesp_csv_agendamento_rate_limited(user) -> tuple[bool, int]:
    """Limita uploads consecutivos por usuário (reduz spam de e-mail). Retorna (bloqueado, retry_after)."""
    intervalo = _prodesp_csv_agendamento_rate_limit_segundos()
    if intervalo <= 0:
        return False, 0
    uid = getattr(user, "id_user", None)
    if uid is None:
        return False, 0
    agora = datetime.now().timestamp()
    ultimo = _csv_agendamento_upload_ultimo_por_usuario.get(uid, 0.0)
    decorrido = agora - ultimo
    if decorrido < intervalo:
        return True, max(1, int(intervalo - decorrido))
    return False, 0


def _prodesp_csv_agendamento_registrar_upload(user) -> None:
    uid = getattr(user, "id_user", None)
    if uid is not None:
        _csv_agendamento_upload_ultimo_por_usuario[uid] = datetime.now().timestamp()


@prodesp_bp.app_context_processor
def _prodesp_inject_template_access():
    """Flags para base_prodesp.html (menu GESTÃO e link Dashboard)."""
    from prodesp.prodesp.caderno.caderno_template_map import CADERNO_STATUS_OPCOES, CADERNO_TESTES_ANALISTA

    caderno_ctx = {
        "prodesp_caderno_status_opcoes": list(CADERNO_STATUS_OPCOES),
        "prodesp_caderno_testes_analista": list(CADERNO_TESTES_ANALISTA),
    }
    if not getattr(current_user, "is_authenticated", False):
        return {
            "prodesp_pode_menu_gestao": False,
            "prodesp_pode_dashboard_gestao": False,
            "prodesp_contratadas_permitidas": CONTRATADAS_PERMITIDAS,
            **caderno_ctx,
        }
    return {
        "prodesp_pode_menu_gestao": _prodesp_pode_ver_menu_gestao(current_user),
        "prodesp_pode_dashboard_gestao": _prodesp_pode_acessar_dashboard_gestao(current_user),
        "prodesp_contratadas_permitidas": CONTRATADAS_PERMITIDAS,
        **caderno_ctx,
    }


def _prodesp_bloquear_create_duplicado_em_atendimento(cur, conn, id_unidade, novo_status, today_date):
    """
    Trava a unidade e impede segundo INSERT «Em Atendimento» no mesmo dia (corrida entre analistas).
    Retorna (bloqueado, resposta_json, http_status) ou (False, None, None).
    """
    if (novo_status or "").strip() != "Em Atendimento":
        return False, None, None

    # create_atendimento já executou SQL nesta conexão (autocommit=False → transação implícita).
    # Não chamar start_transaction() de novo (ProgrammingError: Transaction already in progress).
    cur.execute("SELECT id_unidades FROM unidades WHERE id_unidades = %s FOR UPDATE", (id_unidade,))
    cur.execute(
        """
        SELECT a.id_atendimentos, a.status_atendimentos, a.substatus_atendimentos,
               a.analista_atuante_atendimentos, a.data_atendimentos
        FROM atendimentos a
        WHERE a.id_unidades_atendimentos = %s
          AND a.status_atendimentos = 'Em Atendimento'
          AND DATE(a.data_atendimentos) = %s
        ORDER BY a.horario_inicio_atendimentos DESC, a.id_atendimentos DESC
        LIMIT 1
        FOR UPDATE
        """,
        (id_unidade, today_date),
    )
    ativo_hoje = cur.fetchone()
    permitido, msg_dup, att_redirect = avaliar_create_atendimento_duplicado(
        novo_status=novo_status,
        atendimento_existente=ativo_hoje,
        hoje=today_date,
    )
    if not permitido:
        conn.rollback()
        return True, jsonify(
            message=msg_dup,
            success=False,
            action_type="redirect_edit",
            atendimento_id=att_redirect,
        ), 409
    return False, None, None


def _prodesp_valor_sql_nulo(val):
    """None, string vazia ou NaN/NaT (pandas) — equivalente a NULL SQL."""
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(val, str) and not val.strip():
        return True
    return False


def _prodesp_sem_id_atendimento(val):
    return _prodesp_valor_sql_nulo(val)


def _prodesp_parse_sql_date_value(val):
    """Converte valor_novo_historico (data_agendamento) em date ou None."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    s = s[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        p = parse_date_string(s, current_app.logger, None)
        return p.date() if p else None


def _prodesp_asof_para_atendimento(data_atendimento_raw, horario_finalizacao_raw=None):
    """
    Limite as-of por linha de atendimento: momento do fim do atendimento (ou início se não houver fim).

    Evita que dois atendimentos no mesmo dia compartilhem agenda cadastrada depois do primeiro
    (ex.: visita parcial 15:43 sem agenda; agenda 14:00 inserida às 16:20 só na linha 16:20+).
    """
    dt_att = None
    if data_atendimento_raw is not None and str(data_atendimento_raw).strip() != "":
        if isinstance(data_atendimento_raw, datetime):
            dt_att = data_atendimento_raw
        elif isinstance(data_atendimento_raw, date):
            dt_att = datetime.combine(data_atendimento_raw, time.min)
        else:
            p = parse_date_string(str(data_atendimento_raw), current_app.logger, None)
            dt_att = p if p else None

    if dt_att is None:
        return datetime.combine(date.today(), time(23, 59, 59))

    hf = horario_finalizacao_raw
    if hf is not None and str(hf).strip() not in ("", "None"):
        if isinstance(hf, datetime):
            return hf
        if isinstance(hf, timedelta):
            secs = int(hf.total_seconds()) % 86400
            hf_time = (datetime.min + timedelta(seconds=secs)).time()
            return datetime.combine(dt_att.date(), hf_time)
        if isinstance(hf, time):
            return datetime.combine(dt_att.date(), hf)
        hf_s = str(hf).strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                t = datetime.strptime(hf_s[: len(fmt)], fmt).time()
                return datetime.combine(dt_att.date(), t)
            except ValueError:
                continue

    return dt_att


def _prodesp_fetch_historico_agenda_unidades(cursor, unit_ids):
    """Carrega linhas de historico de agenda (data/hora) para os ids de unidade."""
    if not unit_ids:
        return {}
    placeholders = ",".join(["%s"] * len(unit_ids))
    cursor.execute(
        f"""
        SELECT id_registro_afetado_historico, campo_alterado_historico,
               valor_novo_historico, valor_antigo_historico,
               data_alteracao_historico, id_log_historico
        FROM historico
        WHERE tabela_afetada_historico = 'unidades'
          AND campo_alterado_historico IN ('data_agendamento_unidades', 'hora_agendamento_unidades')
          AND id_registro_afetado_historico IN ({placeholders})
        ORDER BY id_registro_afetado_historico, data_alteracao_historico ASC, id_log_historico ASC
        """,
        tuple(unit_ids),
    )
    by_uid = defaultdict(list)
    for h in cursor.fetchall():
        by_uid[h["id_registro_afetado_historico"]].append(h)
    return by_uid


def _prodesp_historico_ultimo_antes_de(hist_rows, campo, as_of_dt):
    """Última linha do campo com data_alteracao_historico <= as_of_dt."""
    best = None
    best_key = None
    for h in hist_rows:
        if h.get("campo_alterado_historico") != campo:
            continue
        ts = h.get("data_alteracao_historico")
        if ts is None:
            continue
        if isinstance(ts, date) and not isinstance(ts, datetime):
            ts_cmp = datetime.combine(ts, time.min)
        else:
            ts_cmp = ts
        if ts_cmp > as_of_dt:
            continue
        k = (ts_cmp, h.get("id_log_historico") or 0)
        if best_key is None or k > best_key:
            best_key = k
            best = h
    return best


def _prodesp_historico_primeiro_depois_de(hist_rows, campo, as_of_dt):
    """Primeira linha do campo com data_alteracao_historico estritamente após as_of_dt."""
    best = None
    best_key = None
    for h in hist_rows:
        if h.get("campo_alterado_historico") != campo:
            continue
        ts = h.get("data_alteracao_historico")
        if ts is None:
            continue
        if isinstance(ts, date) and not isinstance(ts, datetime):
            ts_cmp = datetime.combine(ts, time.min)
        else:
            ts_cmp = ts
        if ts_cmp <= as_of_dt:
            continue
        k = (ts_cmp, h.get("id_log_historico") or 0)
        if best_key is None or k < best_key:
            best_key = k
            best = h
    return best


def _prodesp_fetch_atendimentos_por_unidade(cursor, unit_ids):
    """Atendimentos por unidade (para detectar visita posterior no mesmo dia)."""
    if not unit_ids:
        return {}
    placeholders = ",".join(["%s"] * len(unit_ids))
    cursor.execute(
        f"""
        SELECT id_atendimentos, id_unidades_atendimentos, data_atendimentos
        FROM atendimentos
        WHERE id_unidades_atendimentos IN ({placeholders})
        """,
        tuple(unit_ids),
    )
    by_uid = defaultdict(list)
    for row in cursor.fetchall():
        by_uid[row["id_unidades_atendimentos"]].append(row)
    return by_uid


def _prodesp_tem_visita_posterior_mesmo_dia(atendimentos_unidade, id_atendimento_atual, as_of_dt, d_att):
    """True se existe outro atendimento da unidade no mesmo dia civil após o as-of da linha."""
    if d_att is None or as_of_dt is None:
        return False
    try:
        id_atual = int(id_atendimento_atual) if id_atendimento_atual is not None else None
    except (TypeError, ValueError):
        id_atual = None
    for a in atendimentos_unidade:
        aid = a.get("id_atendimentos")
        if id_atual is not None and aid == id_atual:
            continue
        dt = a.get("data_atendimentos")
        if dt is None:
            continue
        if isinstance(dt, datetime):
            d_visita = dt.date()
            dt_cmp = dt
        elif isinstance(dt, date):
            d_visita = dt
            dt_cmp = datetime.combine(dt, time.min)
        else:
            parsed = parse_date_string(str(dt), current_app.logger, None)
            if not parsed:
                continue
            d_visita = parsed.date()
            dt_cmp = parsed
        if d_visita != d_att:
            continue
        if dt_cmp > as_of_dt:
            return True
    return False


def _prodesp_resolver_agenda_insert_tardio(hlist, as_of_dt, d_att, campo):
    """
    Primeiro log após as-of com valor_antigo vazio (INSERT inicial) e valor_novo no mesmo dia da visita.
    """
    h_apos = _prodesp_historico_primeiro_depois_de(hlist, campo, as_of_dt)
    if not h_apos:
        return None
    if (h_apos.get("valor_antigo_historico") or "").strip():
        return None
    vn = (h_apos.get("valor_novo_historico") or "").strip()
    if not vn:
        return None
    if campo == "data_agendamento_unidades":
        cand = _prodesp_parse_sql_date_value(vn)
        if cand is None or d_att is None or cand != d_att:
            return None
        return cand
    return vn


def _prodesp_enriquecer_agendamento_historico_asof(cursor, rows, asof_fallback_day=None):
    """
    Ajusta data_agendamento / hora_agendamento por linha de atendimento (as-of histórico).
    Linhas sem id_atendimentos (só agenda na fila GP) usam apenas o snapshot atual em
    `unidades`, alinhado à linha fictícia da view.

    Fallback DATA: último valor_novo até o fim do atendimento (finalização ou início) →
    primeiro valor_antigo não vazio em log posterior → INSERT tardio no mesmo dia (sem visita
    posterior) → snapshot unidades se aplicável.
    As-of por atendimento (não fim do dia civil) evita copiar agenda criada entre dois
    atendimentos no mesmo dia para a visita anterior.

    Exibição: para linhas com data de atendimento, data_agendamento / hora_agendamento
    só são preenchidos quando o dia do atendimento coincide com o dia da agenda
    efetiva (agendamento visível só na visita do dia combinado).
    """
    if not rows:
        return

    id_set = set()
    for r in rows:
        uid = r.get("id_unidades") if r.get("id_unidades") is not None else r.get("id_unidade")
        if _prodesp_valor_sql_nulo(uid):
            continue
        if _prodesp_sem_id_atendimento(r.get("id_atendimentos")):
            continue
        try:
            id_set.add(int(uid))
        except (TypeError, ValueError):
            pass

    if not id_set:
        hist_by_uid = {}
        atend_by_uid = {}
    else:
        unit_ids = list(id_set)
        hist_by_uid = _prodesp_fetch_historico_agenda_unidades(cursor, unit_ids)
        atend_by_uid = _prodesp_fetch_atendimentos_por_unidade(cursor, unit_ids)

    for r in rows:
        uid = r.get("id_unidades") if r.get("id_unidades") is not None else r.get("id_unidade")
        if _prodesp_valor_sql_nulo(uid):
            continue
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            continue

        if _prodesp_sem_id_atendimento(r.get("id_atendimentos")):
            # Fila GP: linha fictícia só com agenda (sem id em atendimentos) — usa snapshot da unidade.
            cur_d = r.get("data_agendamento")
            cur_t = r.get("hora_agendamento")
            u_d = None
            if cur_d is not None:
                if isinstance(cur_d, datetime):
                    u_d = cur_d.date()
                elif isinstance(cur_d, date):
                    u_d = cur_d
                elif isinstance(cur_d, str) and str(cur_d).strip():
                    u_d = _prodesp_parse_sql_date_value(cur_d)
            r["data_agendamento"] = u_d
            r["data_agendamento_timeline"] = u_d
            r["hora_agendamento"] = _prodesp_normalizar_hora_agendamento(cur_t)
            r["data_evento"] = u_d
            continue

        data_att = r.get("data_atendimentos")
        if _prodesp_valor_sql_nulo(data_att):
            data_att = None
            r["data_atendimentos"] = None
        elif data_att is None:
            data_att = r.get("data_atendimento")
            if _prodesp_valor_sql_nulo(data_att):
                data_att = None
        hf_att = r.get("horario_finalizacao_atendimentos") or r.get("horario_finalizacao")
        as_of = _prodesp_asof_para_atendimento(data_att, hf_att)
        d_att = _prodesp_data_atendimento_registro(
            {
                "data_atendimentos": data_att,
                "id_atendimentos": r.get("id_atendimentos") or r.get("id_atendimento"),
            }
        )

        hlist = hist_by_uid.get(uid, [])
        h_d = _prodesp_historico_ultimo_antes_de(hlist, "data_agendamento_unidades", as_of)
        h_h = _prodesp_historico_ultimo_antes_de(hlist, "hora_agendamento_unidades", as_of)

        cur_d = r.get("data_agendamento")
        cur_t = r.get("hora_agendamento")

        u_d = None
        if cur_d is not None:
            if isinstance(cur_d, datetime):
                u_d = cur_d.date()
            elif isinstance(cur_d, date):
                u_d = cur_d
            elif isinstance(cur_d, str) and str(cur_d).strip():
                u_d = _prodesp_parse_sql_date_value(cur_d)

        unidade_sem_historico_agenda = not any(
            (h.get("campo_alterado_historico") or "")
            in ("data_agendamento_unidades", "hora_agendamento_unidades")
            for h in hlist
        )
        pode_usar_snapshot_unidade = (
            unidade_sem_historico_agenda
            and (d_att is None or u_d is None or u_d <= d_att)
        )

        new_d = None
        if h_d and h_d.get("valor_novo_historico"):
            new_d = _prodesp_parse_sql_date_value(h_d["valor_novo_historico"])
        if new_d is None:
            h_d_apos = _prodesp_historico_primeiro_depois_de(hlist, "data_agendamento_unidades", as_of)
            va = (h_d_apos or {}).get("valor_antigo_historico")
            if va and str(va).strip():
                new_d = _prodesp_parse_sql_date_value(va)
        if new_d is None and pode_usar_snapshot_unidade and u_d is not None:
            new_d = u_d
        if new_d is None and d_att is not None:
            id_att = r.get("id_atendimentos") or r.get("id_atendimento")
            if not _prodesp_tem_visita_posterior_mesmo_dia(
                atend_by_uid.get(uid, []), id_att, as_of, d_att
            ):
                cand_d = _prodesp_resolver_agenda_insert_tardio(
                    hlist, as_of, d_att, "data_agendamento_unidades"
                )
                if cand_d is not None:
                    new_d = cand_d

        new_t = None
        if h_h and h_h.get("valor_novo_historico"):
            new_t = str(h_h["valor_novo_historico"]).strip()
        if not new_t:
            h_h_apos = _prodesp_historico_primeiro_depois_de(hlist, "hora_agendamento_unidades", as_of)
            va_h = (h_h_apos or {}).get("valor_antigo_historico")
            if va_h and str(va_h).strip():
                new_t = str(va_h).strip()
        if not new_t and pode_usar_snapshot_unidade and cur_t is not None:
            new_t = _prodesp_normalizar_hora_agendamento(cur_t)
        if not new_t and new_d is not None and d_att is not None:
            id_att = r.get("id_atendimentos") or r.get("id_atendimento")
            if not _prodesp_tem_visita_posterior_mesmo_dia(
                atend_by_uid.get(uid, []), id_att, as_of, d_att
            ):
                cand_t = _prodesp_resolver_agenda_insert_tardio(
                    hlist, as_of, d_att, "hora_agendamento_unidades"
                )
                if cand_t is not None:
                    new_t = str(cand_t).strip()

        agenda_timeline = new_d
        if agenda_timeline is None and pode_usar_snapshot_unidade and u_d is not None:
            agenda_timeline = u_d

        if d_att is not None and (new_d is None or new_d != d_att):
            new_d = None
            new_t = None

        r["data_agendamento"] = new_d
        r["data_agendamento_timeline"] = agenda_timeline
        r["hora_agendamento"] = _prodesp_normalizar_hora_agendamento(new_t)

        if r.get("data_atendimentos") is not None:
            r["data_evento"] = r.get("data_atendimentos")
        else:
            r["data_evento"] = new_d


def _prodesp_data_atendimento_registro(atendimento_row):
    dt_a = atendimento_row.get("data_atendimentos")
    if isinstance(dt_a, datetime):
        return dt_a.date()
    if isinstance(dt_a, date):
        return dt_a
    parsed = parse_date_string(
        str(dt_a) if dt_a else "",
        current_app.logger,
        atendimento_row.get("id_atendimentos"),
    )
    return parsed.date() if parsed else None


def _prodesp_substatus_edicao_agendamento_gp():
    """Substatus em que Agendamento/SUPERVISORES/GP podem abrir edição."""
    return SUBSTATUS_EDICAO_AGENDAMENTO_GP


def _prodesp_user_edicao_map(user):
    from login.portal_access_config import departamentos_do_usuario

    return {
        "admin_user": getattr(user, "admin_user", 0),
        "departamentos": sorted(departamentos_do_usuario(user)),
        "nome_user": getattr(user, "nome_user", "") or "",
    }


def _prodesp_anexar_flags_edicao(user, row_api: dict) -> None:
    """Define pode_editar / edicao_msg no dict da API (mutação in-place)."""
    ok, msg, _ = _prodesp_validar_edicao_atendimento(
        user, row_api_para_validacao_edicao(row_api)
    )
    row_api["pode_editar"] = ok
    row_api["edicao_msg"] = msg if not ok else ""


def _prodesp_anexar_flags_edicao_dashboard(user, row: dict) -> None:
    """Flags de edição para linhas do dashboard (chaves _atendimentos do SELECT)."""
    api_row = {
        "status_atendimento": row.get("status_atendimentos") or "",
        "substatus_atendimento": row.get("substatus_atendimentos") or "",
        "data_atendimento": row.get("data_atendimento") or row.get("data_atendimentos"),
        "analista_atuante": row.get("analista_atuante_atendimentos") or "",
        "analista_configuracao": row.get("analista_configuracao_atendimentos") or "",
        "analista_mpls_atendimentos": row.get("analista_mpls_atendimentos") or "",
        "analista_caderno_teste": row.get("analista_caderno_teste_atendimentos") or "",
    }
    _prodesp_anexar_flags_edicao(user, api_row)
    row["pode_editar"] = api_row.get("pode_editar", False)
    row["edicao_msg"] = api_row.get("edicao_msg") or ""


def _prodesp_static_js_v(filename):
    """Cache-bust de assets JS do módulo (mtime do arquivo)."""
    try:
        path = os.path.join(os.path.dirname(__file__), "static", "js", filename)
        return str(int(os.path.getmtime(path)))
    except OSError:
        return "0"


def _prodesp_atendimentos_modais_template_context(user):
    """Contexto compartilhado entre Atendimentos e Gestão (modais edit/create)."""
    tz_sp = pytz.timezone("America/Sao_Paulo")
    try:
        from prodesp.prodesp.blueprint.blueprint_catalog import list_hint_acronimos

        hint = ", ".join(list_hint_acronimos(limit=12)) or "DETRAN, PROCON, PRO-SANGUE…"
    except Exception:
        hint = "DETRAN, PROCON, PRO-SANGUE…"
    return {
        "admin_user": int(getattr(user, "admin_user", 0) or 0),
        "prodesp_analistas_implantacao": _prodesp_analistas_implantacao_nomes(user),
        "grupos_filas_backend": _PRODESP_GRUPOS_FILAS_BACKEND,
        "prodesp_form_field_limits": form_field_limits_for_template(),
        "prodesp_mv_opcionais_fields": mv_opcionais_template_fields(),
        "prodesp_lan_extra_fields": lan_extra_template_fields(),
        "prodesp_mv_field_limits": blueprint_mv_opcionais_form_field_limits(),
        "prodesp_serial_model_rules": SERIAL_MODEL_FRAGMENTS_ORDERED,
        "hoje": datetime.now(tz_sp).date(),
        "usuario_logado": getattr(user, "nome_user", "") or "",
        "prodesp_js_v_motivos": _prodesp_static_js_v("prodesp_motivos_fora_padrao.js"),
        "prodesp_js_v_atendimentos": _prodesp_static_js_v("script_atendimentos_prodesp.js"),
        "prodesp_js_v_gestao": _prodesp_static_js_v("script_gestao_atendimentos_prodesp.js"),
        "blueprint_acronimo_hint": hint,
        **_prodesp_dt_sync_template_context(),
    }


def _prodesp_dt_sync_template_context():
    """Intervalo/fase global de refresh DataTable (fila + gestão)."""
    try:
        interval = max(15, int((os.getenv("PRODESP_DT_SYNC_INTERVAL_SEC") or "90").strip()))
    except (TypeError, ValueError):
        interval = 90
    use_revision = (os.getenv("PRODESP_DT_SYNC_USE_REVISION") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    from prodesp.prodesp.atendimentos_list_query import list_delta_enabled

    return {
        "prodesp_dt_sync_interval_sec": interval,
        "prodesp_dt_sync_use_revision": use_revision,
        "prodesp_js_v_dt_sync": _prodesp_static_js_v("prodesp_dt_sync.js"),
        "prodesp_list_delta": list_delta_enabled(),
    }


def _prodesp_validar_edicao_atendimento(user, atendimento_row, tz_sp=None):
    """
    Regras de edição do modal de atendimentos (perfil, data, dono da etapa).
    Admin: sem restrição. AG/GP: colaborativo só em Triagem; demais etapas exigem dono.
  """
    if not atendimento_row:
        return False, "Atendimento não encontrado.", 404

    if tz_sp is None:
        tz_sp = pytz.timezone("America/Sao_Paulo")
    elif isinstance(tz_sp, datetime):
        tz_sp = tz_sp.tzinfo if tz_sp.tzinfo is not None else pytz.timezone("America/Sao_Paulo")
    hoje = datetime.now(tz_sp).date()
    return _validar_edicao_atendimento_rules(
        _prodesp_user_edicao_map(user),
        atendimento_row,
        hoje,
    )


def _prodesp_validar_edicao_observacao_atendimento(user, atendimento_row, tz_sp=None):
    """Observações: relaxa bloqueio AG/GP em atendimentos finalizados no dia (pós-Quebra)."""
    if not atendimento_row:
        return False, "Atendimento não encontrado.", 404

    if tz_sp is None:
        tz_sp = pytz.timezone("America/Sao_Paulo")
    elif isinstance(tz_sp, datetime):
        tz_sp = tz_sp.tzinfo if tz_sp.tzinfo is not None else pytz.timezone("America/Sao_Paulo")
    hoje = datetime.now(tz_sp).date()
    return _validar_edicao_observacao_atendimento_rules(
        _prodesp_user_edicao_map(user),
        atendimento_row,
        hoje,
    )


def _prodesp_require_admin_api():
    if int(getattr(current_user, "admin_user", 0) or 0) != 1:
        return jsonify(success=False, message="Apenas administradores."), 403
    return None


def _prodesp_parse_admin_datetime(val):
    """Parse string de datetime-local ou ISO para datetime naive (MySQL)."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    s = s.replace("Z", "").replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError as e:
        raise ValueError("data/hora inválida") from e


def _prodesp_serialize_status_log_rows(rows):
    out = []
    for row in rows or []:
        r = dict(row)
        dt = r.get("alterado_em_log")
        if isinstance(dt, datetime):
            r["alterado_em_log"] = dt.isoformat(sep=" ", timespec="seconds")
        out.append(r)
    return out


def _prodesp_serialize_historico_rows(rows):
    tz_sp = pytz.timezone("America/Sao_Paulo")
    out = []
    for row in rows or []:
        r = dict(row)
        dt = r.get("data_alteracao_historico")
        if isinstance(dt, datetime) and dt.tzinfo is None:
            r["data_alteracao_historico"] = tz_sp.localize(dt).isoformat()
        elif isinstance(dt, datetime):
            r["data_alteracao_historico"] = dt.isoformat()
        out.append(r)
    return out


_PRODESP_HISTORICO_CAMPOS_RELACIONADOS = frozenset(
    {"Equipamento", "Link", "Observação", "Observacao"}
)
_PRODESP_HISTORICO_CAMPOS_OBSERVACAO = frozenset({"Observação", "Observacao"})


def _prodesp_filter_historico_observacao(rows):
    return [
        h
        for h in (rows or [])
        if (h.get("campo_alterado_historico") or "").strip() in _PRODESP_HISTORICO_CAMPOS_OBSERVACAO
    ]


def _prodesp_merge_historico_desc(*lists):
    merged = []
    for lst in lists:
        merged.extend(lst or [])

    def _sort_key(h):
        dt = h.get("data_alteracao_historico") or ""
        hid = h.get("id_log_historico") or 0
        return (str(dt), int(hid) if str(hid).isdigit() else 0)

    merged.sort(key=_sort_key, reverse=True)
    return merged


def _prodesp_fetch_historico_registro(cursor, tabela, registro_id, order_desc=True):
    if registro_id is None:
        return []
    ordem = "DESC" if order_desc else "ASC"
    cursor.execute(
        f"""
        SELECT id_log_historico, usuario_re_historico, usuario_nome_historico,
               tabela_afetada_historico, id_registro_afetado_historico,
               campo_alterado_historico, valor_antigo_historico, valor_novo_historico,
               operacao_historico, data_alteracao_historico
        FROM historico
        WHERE tabela_afetada_historico = %s AND id_registro_afetado_historico = %s
        ORDER BY data_alteracao_historico {ordem}, id_log_historico {ordem}
        """,
        (tabela, registro_id),
    )
    return _prodesp_serialize_historico_rows(cursor.fetchall())


def _prodesp_fetch_historico_ids_in(cursor, tabela, ids, order_desc=True):
    ids = [int(x) for x in (ids or []) if x is not None]
    if not ids:
        return []
    ordem = "DESC" if order_desc else "ASC"
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(
        f"""
        SELECT id_log_historico, usuario_re_historico, usuario_nome_historico,
               tabela_afetada_historico, id_registro_afetado_historico,
               campo_alterado_historico, valor_antigo_historico, valor_novo_historico,
               operacao_historico, data_alteracao_historico
        FROM historico
        WHERE tabela_afetada_historico = %s
          AND id_registro_afetado_historico IN ({placeholders})
        ORDER BY data_alteracao_historico {ordem}, id_log_historico {ordem}
        """,
        (tabela, *ids),
    )
    return _prodesp_serialize_historico_rows(cursor.fetchall())


def _prodesp_serialize_observacoes_admin(rows):
    out = []
    for row in rows or []:
        r = dict(row)
        ts = r.get("timestamp")
        if isinstance(ts, (datetime, date)):
            r["timestamp"] = ts.strftime("%d/%m/%Y %H:%M:%S")
            r["timestamp_iso"] = ts.isoformat(sep=" ", timespec="seconds")
        else:
            r["timestamp_iso"] = ts
        r["escopo"] = (
            "atendimento"
            if r.get("id_atendimentos_observacoes")
            else "unidade"
        )
        out.append(r)
    return out


def _prodesp_atendimento_id_unidade(cursor, id_atendimento):
    cursor.execute(
        "SELECT id_unidades_atendimentos FROM atendimentos WHERE id_atendimentos = %s",
        (id_atendimento,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return row.get("id_unidades_atendimentos")


def _prodesp_admin_auditoria_payload(cursor, id_atendimento):
    id_unidade = _prodesp_atendimento_id_unidade(cursor, id_atendimento)
    if id_unidade is None:
        return None

    cursor.execute(
        """
        SELECT id_log_atendimentos_status, id_atendimentos_log, tipo_campo_log,
               valor_anterior_log, valor_novo_log, alterado_em_log
        FROM atendimentos_status_log
        WHERE id_atendimentos_log = %s
        ORDER BY alterado_em_log ASC, id_log_atendimentos_status ASC
        """,
        (id_atendimento,),
    )
    status_log = _prodesp_serialize_status_log_rows(cursor.fetchall())

    historico_atendimento = _prodesp_fetch_historico_registro(
        cursor, "atendimentos", id_atendimento
    )
    historico_unidade = _prodesp_fetch_historico_registro(
        cursor, "unidades", id_unidade
    )

    cursor.execute(
        """
        SELECT id_equipamentos AS id, modelo_equipamentos AS modelo,
               serial_equipamentos AS serial, versao_equipamentos AS versao,
               descricao_equipamentos AS descricao, id_unidades_equipamentos AS id_unidade
        FROM equipamentos WHERE id_unidades_equipamentos = %s
        ORDER BY id_equipamentos
        """,
        (id_unidade,),
    )
    equipamentos = cursor.fetchall()
    eq_ids = [e["id"] for e in equipamentos]

    cursor.execute(
        """
        SELECT id_link AS id, id_vgr_links, designador_links, tipo_links,
               operadora_links, vlan_links, ip_wan_links, redundante_critico_links,
               ip_gateway_links,
               ip_mascara_links, velocidade_links, pppoe_user_links, pppoe_pass_links,
               id_unidades_links AS id_unidade
        FROM links WHERE id_unidades_links = %s
        ORDER BY id_link
        """,
        (id_unidade,),
    )
    links = decrypt_sensitive_rows_inplace(cursor.fetchall())
    link_ids = [l["id"] for l in links]

    historico_equipamentos = _prodesp_fetch_historico_ids_in(
        cursor, "equipamentos", eq_ids
    )
    historico_links = _prodesp_fetch_historico_ids_in(cursor, "links", link_ids)

    cursor.execute(
        """
        SELECT id_observacoes AS id, observacoes AS texto,
               timestamp_observacoes AS timestamp,
               id_atendimentos_observacoes, id_unidades_observacoes
        FROM observacoes
        WHERE id_atendimentos_observacoes = %s
           OR (id_unidades_observacoes = %s AND id_atendimentos_observacoes IS NULL)
        ORDER BY timestamp_observacoes DESC, id_observacoes DESC
        """,
        (id_atendimento, id_unidade),
    )
    observacoes = _prodesp_serialize_observacoes_admin(cursor.fetchall())

    historico_observacao = _prodesp_merge_historico_desc(
        _prodesp_filter_historico_observacao(historico_atendimento),
        _prodesp_filter_historico_observacao(historico_unidade),
    )
    eventos_relacionados = [
        h
        for h in historico_atendimento
        if (h.get("campo_alterado_historico") or "") in _PRODESP_HISTORICO_CAMPOS_RELACIONADOS
    ]

    return {
        "id_unidade": id_unidade,
        "status_log": status_log,
        "historico": historico_atendimento,
        "historico_atendimento": historico_atendimento,
        "historico_unidade": historico_unidade,
        "historico_observacao": historico_observacao,
        "historico_equipamentos": historico_equipamentos,
        "historico_links": historico_links,
        "eventos_relacionados": eventos_relacionados,
        "equipamentos": equipamentos,
        "links": links,
        "observacoes": observacoes,
    }


def normalizar_ids_lista(valor):
    if not valor:
        return []
    if isinstance(valor, (list, tuple, set)):
        ids = []
        for item in valor:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        # Remove duplicados preservando a ordem
        return list(dict.fromkeys(ids))
    return []

def salvar_motivos_fora_padrao(cursor, id_atendimento, motivos_ids):
    motivos_novos = normalizar_ids_lista(motivos_ids)
    cursor.execute(
        "SELECT id_motivo FROM atendimentos_fora_padrao WHERE id_atendimento = %s",
        (id_atendimento,)
    )
    motivos_atuais = []
    for row in cursor.fetchall():
        if isinstance(row, dict):
            motivo_id = row.get('id_motivo')
        else:
            motivo_id = row[0] if row else None
        try:
            if motivo_id is not None:
                motivos_atuais.append(int(motivo_id))
        except (TypeError, ValueError):
            continue

    set_atuais = set(motivos_atuais)
    set_novos = set(motivos_novos)

    motivos_para_inserir = sorted(set_novos - set_atuais)
    motivos_para_deletar = sorted(set_atuais - set_novos)

    if motivos_para_deletar:
        cursor.executemany(
            "DELETE FROM atendimentos_fora_padrao WHERE id_atendimento = %s AND id_motivo = %s",
            [(id_atendimento, motivo_id) for motivo_id in motivos_para_deletar]
        )

    if motivos_para_inserir:
        cursor.executemany(
            "INSERT INTO atendimentos_fora_padrao (id_atendimento, id_motivo) VALUES (%s, %s)",
            [(id_atendimento, motivo_id) for motivo_id in motivos_para_inserir]
        )

def _prodesp_hoje_sp_date():
    return datetime.now(pytz.timezone("America/Sao_Paulo")).date()


def _prodesp_dia_civil_atendimento(dt_val, logger=None, record_id=None):
    """Extrai date de datetime/date/str; None se inválido."""
    if dt_val is None or dt_val == "":
        return None
    if isinstance(dt_val, date) and not isinstance(dt_val, datetime):
        return dt_val
    if isinstance(dt_val, datetime):
        return dt_val.date()
    parsed = parse_date_string(dt_val, logger or current_app.logger, record_id)
    if isinstance(parsed, datetime):
        return parsed.date()
    if isinstance(parsed, date):
        return parsed
    return None


def _prodesp_dia_atendimento_para_cronometro(dt_val, status, logger=None, record_id=None):
    """
    Dia usado no cronômetro. Atendimento ativo com data futura no banco
    (ex.: agendamento copiado por engano) usa hoje em America/Sao_Paulo.
    """
    dia = _prodesp_dia_civil_atendimento(dt_val, logger, record_id)
    if dia is None:
        return None
    status_norm = (status or "").strip()
    if (
        status_norm not in FINAL_STATUSES_ATENDIMENTO
        and status_norm != "Agendado"
        and dia > _prodesp_hoje_sp_date()
    ):
        return _prodesp_hoje_sp_date()
    return dia


def _prodesp_normalizar_data_atendimento_lista(row: dict) -> None:
    """Exibição na fila: atendimento ativo não mostra data futura (mantém raw)."""
    if not row.get("id_atendimento"):
        return
    status = (row.get("status_atendimento") or "").strip()
    if status in FINAL_STATUSES_ATENDIMENTO or status == "Agendado":
        return
    hoje = _prodesp_hoje_sp_date()
    raw = row.get("data_atendimento") or row.get("data_atendimentos")
    dia = _prodesp_dia_civil_atendimento(raw, record_id=row.get("id_atendimento"))
    if dia is None or dia <= hoje:
        return
    if row.get("data_atendimento_raw") in (None, ""):
        row["data_atendimento_raw"] = raw
    if isinstance(raw, (datetime, date)):
        row["data_atendimento"] = hoje
    else:
        row["data_atendimento"] = hoje.isoformat()


def parse_date_string(date_str, logger, record_id=None):
    if isinstance(date_str, (datetime, date)):
        return date_str
    if not isinstance(date_str, str) or not date_str.strip():
        return None
    date_str = date_str.strip()
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        pass
    formats_to_try = [
        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
        '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M',
        '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y',
    ]
    for fmt in formats_to_try:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    logger.warning(f" prodesp - Não foi possível analisar a data: '{date_str}' para ID {record_id}.")
    return None


def _prodesp_sql_expr_ultimo_substatus_log(id_atendimentos_expr, substatus_expr):
    """
    Última entrada no substatus atual (cronômetro Tempo Etapa).
    Usa status_log + historico (fallback quando a trigger antiga omitiu reentradas).

    Preferir _prodesp_sql_cte_ultimo_substatus_log_agg + JOIN em listas grandes (evita subquery por linha).
    """
    return f"""(
        SELECT MAX(ts) FROM (
            SELECT s.alterado_em_log AS ts
            FROM atendimentos_status_log s
            WHERE s.id_atendimentos_log = {id_atendimentos_expr}
              AND s.tipo_campo_log = 'substatus'
              AND TRIM(s.valor_novo_log) = TRIM({substatus_expr})
            UNION ALL
            SELECT h.data_alteracao_historico AS ts
            FROM historico h
            WHERE h.id_registro_afetado_historico = {id_atendimentos_expr}
              AND h.tabela_afetada_historico = 'atendimentos'
              AND h.campo_alterado_historico = 'substatus_atendimentos'
              AND TRIM(h.valor_novo_historico) = TRIM({substatus_expr})
        ) _ult_sub
    )"""


def _prodesp_sql_cte_ultimo_substatus_log_agg() -> str:
    """
    Agrega MAX(ts) por (id_atendimento, substatus) uma vez — JOIN na lista em vez de subquery correlacionada.
    Fonte única: ``atendimentos_list_query.sql_cte_ultimo_substatus_log_agg`` (DRY Sprint 1).
    """
    from prodesp.prodesp.atendimentos_list_query import sql_cte_ultimo_substatus_log_agg

    return sql_cte_ultimo_substatus_log_agg()


def _prodesp_list_cache_user_key(user) -> str:
    """Chave estável para cache da resposta JSON (perfil + analista afeta pode_editar)."""
    from login.portal_access_config import departamentos_do_usuario

    uid = getattr(user, "id_user", None) or getattr(user, "id", None) or 0
    admin = int(getattr(user, "admin_user", 0) or 0)
    depts = "|".join(sorted(departamentos_do_usuario(user) or []))
    nome = (getattr(user, "nome_user", None) or "").strip()
    return f"{uid}:{admin}:{depts}:{nome}"


def _prodesp_list_server_side_ui() -> bool:
    from prodesp.prodesp.atendimentos_list_query import list_server_side_enabled

    return list_server_side_enabled()


def inicio_ultima_entrada_substatus(rows_chrono, substatus_nome):
    """
    Retorna o instante da última entrada no substatus (não acumula passagens anteriores).
    Usado no cronômetro do dashboard quando o atendimento retorna à mesma etapa.
    """
    nome = (substatus_nome or "").strip()
    if not nome or not rows_chrono:
        return None
    ultimo = None
    for row in rows_chrono:
        if (row.get("valor_novo_log") or "").strip() == nome:
            ultimo = row.get("alterado_em_log")
    return ultimo


def _prodesp_coerce_dt_sp(dt, tz_sp):
    """Normaliza datetime do MySQL para America/Sao_Paulo (evita naive/aware misturados)."""
    if dt is None:
        return None
    if hasattr(dt, "to_pydatetime"):
        dt = dt.to_pydatetime()
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return tz_sp.localize(dt)
    return dt


def duracao_acumulada_substatus_segundos(rows_chrono, substatus_nome, tz_sp):
    """
    Soma os intervalos em que o atendimento permaneceu em um substatus,
    usando a linha do tempo de `atendimentos_status_log` (tipo substatus).
    Cada intervalo vai da alteração para `substatus_nome` até a próxima alteração
    qualquer; se for o último evento, fecha em datetime.now(tz_sp).
    """
    total = 0
    nome = (substatus_nome or "").strip()
    if not nome or not rows_chrono:
        return 0
    now_sp = datetime.now(tz_sp)
    for i, row in enumerate(rows_chrono):
        val = (row.get("valor_novo_log") or "").strip()
        if val != nome:
            continue
        start = row.get("alterado_em_log")
        if not start:
            continue
        if hasattr(start, "to_pydatetime"):
            start = start.to_pydatetime()
        if isinstance(start, datetime) and start.tzinfo is None:
            start = tz_sp.localize(start)
        end = rows_chrono[i + 1]["alterado_em_log"] if i + 1 < len(rows_chrono) else None
        if end:
            if hasattr(end, "to_pydatetime"):
                end = end.to_pydatetime()
            if isinstance(end, datetime) and end.tzinfo is None:
                end = tz_sp.localize(end)
            total += max(0, int((end - start).total_seconds()))
        else:
            total += max(0, int((now_sp - start).total_seconds()))
    return total


def converter_timedelta_para_time(td_obj):
    if not isinstance(td_obj, timedelta):
        return None
    total_seconds = int(td_obj.total_seconds())
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return time(int(hours), int(minutes), int(seconds))


def _prodesp_tempo_valor_para_segundos(val):
    """Converte TIME/timedelta/str (ex.: tempo_total_geral da view) em segundos."""
    if val is None:
        return None
    if isinstance(val, timedelta):
        return max(0, int(val.total_seconds()))
    t = _prodesp_time_from_value(val)
    if t is not None:
        return t.hour * 3600 + t.minute * 60 + t.second
    return None


def _prodesp_formatar_segundos_hhmmss(segundos):
    segundos = max(0, int(segundos))
    hs, rem = divmod(segundos, 3600)
    ms, ss = divmod(rem, 60)
    return f"{int(hs):02d}:{int(ms):02d}:{int(ss):02d}"


_PRODESP_KPI_TEMPOS_EXECUTIVO_NOMES = frozenset(
    {"felipe dos santos paixao"}
)

PRODESP_ETAPAS_TEMPO_ESPERA = (
    {
        "key": "aguardando_cliente",
        "field": "tempo_aguardando_cliente",
        "label": "Aguardando Cliente",
        "analista": None,
    },
    {
        "key": "aguardando_config_remota",
        "field": "tempo_aguardando_config_remota",
        "label": "Aguardando Configuração Remota",
        "analista": None,
    },
    {
        "key": "aguardando_mpls",
        "field": "tempo_aguardando_mpls",
        "label": "Aguardando MPLS",
        "analista": None,
    },
    {
        "key": "aguardando_caderno",
        "field": "tempo_aguardando_caderno",
        "label": "Aguardando Caderno de Teste",
        "analista": None,
    },
)

PRODESP_ETAPAS_TEMPO_PRODUTIVO = (
    {
        "key": "aguarda_gestao",
        "field": "tempo_aguarda_gestao",
        "label": "Aguarda Gestão",
        "analista": "analista_atuante_atendimentos",
    },
    {
        "key": "com_suporte",
        "field": "tempo_com_suporte",
        "label": "Com Suporte",
        "analista": None,
    },
    {
        "key": "config_remota",
        "field": "tempo_config_remota",
        "label": "Configuração Remota",
        "analista": "analista_configuracao_atendimentos",
    },
    {
        "key": "config_mpls",
        "field": "tempo_config_mpls",
        "label": "Configuração MPLS",
        "analista": "analista_mpls_atendimentos",
    },
    {
        "key": "caderno_teste",
        "field": "tempo_caderno_teste",
        "label": "Caderno de Teste",
        "analista": "analista_caderno_teste_atendimentos",
    },
)


def _prodesp_normalize_nome_comparacao(nome):
    s = (nome or "").strip().lower()
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _prodesp_pode_ver_kpis_tempo_executivo(user):
    """KPIs executivos de tempo: admin ou usuários autorizados explicitamente."""
    if _prodesp_is_admin(user):
        return True
    nome = _prodesp_normalize_nome_comparacao(getattr(user, "nome_user", ""))
    return nome in _PRODESP_KPI_TEMPOS_EXECUTIVO_NOMES


def _prodesp_media_segundos_lista(segundos_list):
    if not segundos_list:
        return "00:00:00"
    return _prodesp_formatar_segundos_hhmmss(int(sum(segundos_list) / len(segundos_list)))


def _prodesp_etapa_tempo_stat(rows, field, analista_field=None):
    """Média, ocorrências (>0) e maior ofensor para um campo da view de tempos."""
    valores = []
    max_seg = -1
    max_row = None
    for row in rows:
        seg = _prodesp_tempo_valor_para_segundos(row.get(field))
        if seg is None or seg <= 0:
            continue
        valores.append(seg)
        if seg > max_seg:
            max_seg = seg
            max_row = row

    maior_ofensor = None
    if max_row is not None:
        acronimo = (max_row.get("acronimo") or "").strip()
        id_intragov_raw = max_row.get("id_intragov")
        id_intragov = (
            str(id_intragov_raw).strip()
            if id_intragov_raw is not None and str(id_intragov_raw).strip()
            else None
        )
        analista = None
        if analista_field:
            analista = (max_row.get(analista_field) or "").strip() or None
        maior_ofensor = {
            "id_atendimento": max_row.get("id_atendimentos"),
            "id_vgr": (max_row.get("id_vgr") or "").strip(),
            "acronimo": acronimo,
            "id_intragov": id_intragov,
            "analista": analista,
            "tempo": _prodesp_formatar_segundos_hhmmss(max_seg),
        }

    return {
        "tempo_medio": _prodesp_media_segundos_lista(valores),
        "ocorrencias": len(valores),
        "maior_ofensor": maior_ofensor,
    }


_PRODESP_SQL_TEMPOS_ETAPA_BASE = """
    SELECT
        v.id_atendimentos,
        v.id_unidade,
        v.tempo_total_geral,
        v.tempo_total_atendimento,
        v.tempo_aguardando_cliente,
        v.tempo_triagem,
        {colunas_gestao_suporte}
        v.tempo_aguardando_config_remota,
        v.tempo_config_remota,
        v.tempo_aguardando_mpls,
        v.tempo_config_mpls,
        v.tempo_aguardando_caderno,
        v.tempo_caderno_teste,
        v.analista_atuante_atendimentos,
        v.analista_configuracao_atendimentos,
        v.analista_mpls_atendimentos,
        v.analista_caderno_teste_atendimentos,
        a.contratada_atendimentos,
        u.id_vgr_unidades AS id_vgr,
        u.id_intragov_unidades AS id_intragov,
        u.acronimo_unidades AS acronimo
    FROM {tempo_src} v
    INNER JOIN atendimentos a ON a.id_atendimentos = v.id_atendimentos
    INNER JOIN unidades u ON u.id_unidades = COALESCE(v.id_unidade, a.id_unidades_atendimentos)
    WHERE a.data_atendimentos >= %s AND a.data_atendimentos < %s
"""


def _prodesp_sql_tempos_etapa_base() -> str:
    from prodesp.prodesp.tempo_snapshot import tempo_source_table

    return _PRODESP_SQL_TEMPOS_ETAPA_BASE.replace("{tempo_src}", tempo_source_table())


_PRODESP_SQL_TEMPOS_ETAPA_COLS_NOVO = (
    "v.tempo_aguarda_gestao,\n        v.tempo_com_suporte,\n        "
)
_PRODESP_SQL_TEMPOS_ETAPA_COLS_LEGADO = (
    "v.tempo_triagem AS tempo_aguarda_gestao,\n"
    "        CAST('00:00:00' AS TIME) AS tempo_com_suporte,\n        "
)


def _prodesp_carregar_tempos_etapa_view(cursor, start_date, end_date):
    """Linhas de tempos no período (view ou snapshot conforme flag)."""
    params = _prodesp_sql_date_range(start_date, end_date)
    sql_base = _prodesp_sql_tempos_etapa_base()
    for cols, modo in (
        (_PRODESP_SQL_TEMPOS_ETAPA_COLS_NOVO, "atualizada"),
        (_PRODESP_SQL_TEMPOS_ETAPA_COLS_LEGADO, "legada"),
    ):
        try:
            cursor.execute(
                sql_base.format(colunas_gestao_suporte=cols),
                params,
            )
            if modo == "legada":
                current_app.logger.info(
                    "prodesp - tempos sem colunas "
                    "tempo_aguarda_gestao/tempo_com_suporte; KPIs usam fallback "
                    "(aplique prodesp/sql/vw_tempo_atendimento_detalhado.sql)."
                )
            return cursor.fetchall()
        except Error as exc:
            errno = getattr(exc, "errno", None)
            if modo == "atualizada" and errno == 1054:
                continue
            current_app.logger.warning(
                "prodesp - fonte de tempos indisponível para KPIs de etapa",
                exc_info=True,
            )
            return []
    return []


def _prodesp_serializar_linhas_tempos_etapa(rows):
    """Serializa linhas da view de tempos para filtro por contratada no dashboard (JS)."""
    out = []
    for row in rows:
        item = {}
        for key, value in row.items():
            if value is None:
                item[key] = None
            elif isinstance(value, timedelta):
                item[key] = str(value)
            elif isinstance(value, (datetime, date)):
                item[key] = value.isoformat()
            elif hasattr(value, "__str__") and not isinstance(value, (int, float, str, bool)):
                item[key] = str(value)
            else:
                item[key] = value
        out.append(item)
    return out


def _prodesp_build_tempos_etapa_kpis_dashboard(cursor, start_date, end_date):
    rows = _prodesp_carregar_tempos_etapa_view(cursor, start_date, end_date)

    geral_secs = []
    atend_secs = []
    espera_diff_secs = []
    for row in rows:
        g = _prodesp_tempo_valor_para_segundos(row.get("tempo_total_geral"))
        a = _prodesp_tempo_valor_para_segundos(row.get("tempo_total_atendimento"))
        if g is not None:
            geral_secs.append(g)
        if a is not None:
            atend_secs.append(a)
        if g is not None and a is not None:
            espera_diff_secs.append(max(0, g - a))

    def _map_etapas(definicoes):
        return [
            {
                "key": d["key"],
                "label": d["label"],
                **_prodesp_etapa_tempo_stat(rows, d["field"], d.get("analista")),
            }
            for d in definicoes
        ]

    return {
        "resumo_ciclo": {
            "total_atendimentos": len(rows),
            "tempo_total_geral_medio": _prodesp_media_segundos_lista(geral_secs),
            "tempo_total_atendimento_medio": _prodesp_media_segundos_lista(atend_secs),
            "diferenca_espera_media": _prodesp_media_segundos_lista(espera_diff_secs),
            "legenda": {
                "geral": "Ciclo completo (inclui filas de espera entre etapas).",
                "atendimento": "Tempo em etapas produtivas (sem substatus Aguardando).",
                "espera": "Diferença média Geral − Atendimento por atendimento.",
            },
        },
        "espera": _map_etapas(PRODESP_ETAPAS_TEMPO_ESPERA),
        "produtivo": _map_etapas(PRODESP_ETAPAS_TEMPO_PRODUTIVO),
        "linhas": _prodesp_serializar_linhas_tempos_etapa(rows),
    }


def _prodesp_time_from_value(val):
    """Converte TIME/timedelta/str do MySQL ou frontend em datetime.time."""
    if val is None:
        return None
    if isinstance(val, time):
        return val
    if isinstance(val, timedelta):
        return converter_timedelta_para_time(val)
    s = str(val).strip()
    if not s:
        return None
    for fmt in ('%H:%M:%S', '%H:%M', '%H:%M:%S.%f'):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    parts = s.split(':')
    if len(parts) >= 2:
        try:
            h = int(parts[0])
            m = int(parts[1])
            sec = int(parts[2]) if len(parts) > 2 else 0
            return time(h, m, sec)
        except (ValueError, TypeError):
            return None
    return None


def normalize_hora_agendamento_db(val):
    """Formato canônico para gravar no banco (HH:MM:SS) ou None."""
    t = _prodesp_time_from_value(val)
    return t.strftime('%H:%M:%S') if t else None


def _prodesp_normalizar_hora_agendamento(val):
    """Normaliza TIME/timedelta/pd.Timedelta/str para HH:MM:SS (relatório e enrich)."""
    return normalize_hora_agendamento_db(val)


def format_hora_agendamento_input(val):
    """Formato para input HTML type=time (HH:MM)."""
    t = _prodesp_time_from_value(val)
    return t.strftime('%H:%M') if t else None


def horas_agendamento_equivalent(a, b):
    ta = _prodesp_time_from_value(a)
    tb = _prodesp_time_from_value(b)
    if ta is None and tb is None:
        return True
    if ta is None or tb is None:
        return False
    return ta == tb


def _coordenada_para_decimal(val):
    """Converte latitude/longitude (Decimal, str, float) para comparação numérica."""
    if val is None or val == "":
        return None
    try:
        from decimal import Decimal
        return Decimal(str(val).strip().replace(",", "."))
    except Exception:
        return None


def coordenadas_equivalentes(a, b) -> bool:
    """Evita UPDATE/histórico quando só muda formatação (ex.: 8 vs 7 casas decimais)."""
    da = _coordenada_para_decimal(a)
    db = _coordenada_para_decimal(b)
    if da is None and db is None:
        return True
    if da is None or db is None:
        return False
    return da == db


def _prodesp_format_row_hora_agendamento(row, key='hora_agendamento'):
    if key not in row:
        return
    val = row.get(key)
    if val is None:
        return
    formatted = format_hora_agendamento_input(val)
    row[key] = formatted if formatted else None


def _prodesp_ticket_noc_valor(unidade_row, unidade_updates=None):
    if unidade_updates and 'ticket_noc_unidades' in unidade_updates:
        return unidade_updates.get('ticket_noc_unidades')
    return (unidade_row or {}).get('ticket_noc_unidades')


def _prodesp_mensagem_ticket_noc_concluido(unidade_row, unidade_updates=None):
    """Ticket NOC obrigatório e no padrão quando status e substatus forem Concluído."""
    from prodesp.prodesp.ticket_noc_validation import validate_ticket_noc_format

    return validate_ticket_noc_format(
        _prodesp_ticket_noc_valor(unidade_row, unidade_updates),
        obrigatorio=True,
    )


def _prodesp_erros_conclusao_equipamento(
    cursor,
    *,
    id_unidade,
    hostname_unidade,
    logs_atendimentos="",
    equipamentos_override=None,
):
    """
    P0/P1: serial Fortinet válido + cruzamento com coleta FGT (se houver).
    Retorna lista de mensagens (vazia = ok).
    """
    from prodesp.prodesp.conclusao_equipamento_rules import validate_conclusao_equipamento

    equipamentos = list(equipamentos_override or [])
    if not equipamentos and id_unidade:
        cursor.execute(
            """
            SELECT serial_equipamentos AS serial, versao_equipamentos AS versao,
                   modelo_equipamentos AS modelo
            FROM equipamentos
            WHERE id_unidades_equipamentos = %s
              AND IFNULL(deleted_equipamentos, 0) = 0
            ORDER BY id_equipamentos
            """,
            (id_unidade,),
        )
        equipamentos = cursor.fetchall() or []

    return validate_conclusao_equipamento(
        hostname_unidade=hostname_unidade,
        equipamentos=equipamentos,
        logs_atendimentos=logs_atendimentos,
        exigir_cruzamento_log=True,
    )


def _prodesp_erros_conclusao_links(
    cursor,
    *,
    id_unidade,
    logs_atendimentos="",
    links_override=None,
):
    """
    Cruzamento de links MPLS/STATIC com coleta FGT (physical/show/ARP).
    Sem coleta de interface → não bloqueia.
    """
    from prodesp.prodesp.conclusao_links_rules import validate_conclusao_links

    links = list(links_override or [])
    if not links and id_unidade and cursor is not None:
        cursor.execute(
            """
            SELECT id_link, designador_links, tipo_links, operadora_links,
                   id_vgr_links, ip_wan_links, ip_gateway_links, ip_mascara_links,
                   velocidade_links
            FROM links
            WHERE id_unidades_links = %s
            ORDER BY id_link
            """,
            (id_unidade,),
        )
        links = cursor.fetchall() or []

    return validate_conclusao_links(
        links=links,
        logs_atendimentos=logs_atendimentos,
        exigir_cruzamento_log=True,
    )


def _prodesp_erros_conclusao(
    cursor,
    *,
    id_unidade,
    hostname_unidade,
    logs_atendimentos="",
    equipamentos_override=None,
    links_override=None,
):
    """Equipamento + links na conclusão. Retorna lista de mensagens."""
    errs = _prodesp_erros_conclusao_equipamento(
        cursor,
        id_unidade=id_unidade,
        hostname_unidade=hostname_unidade,
        logs_atendimentos=logs_atendimentos,
        equipamentos_override=equipamentos_override,
    )
    errs.extend(
        _prodesp_erros_conclusao_links(
            cursor,
            id_unidade=id_unidade,
            logs_atendimentos=logs_atendimentos,
            links_override=links_override,
        )
    )
    return errs


def _prodesp_status_substatus_efetivos(old_atendimento, atendimento_updates):
    """Status/substatus após o POST (updates) ou os persistidos."""
    att = old_atendimento or {}
    upd = atendimento_updates or {}
    status = upd.get("status_atendimentos", att.get("status_atendimentos"))
    sub = upd.get("substatus_atendimentos", att.get("substatus_atendimentos"))
    return str(status or "").strip(), str(sub or "").strip()


def _prodesp_deve_gerar_horario_finalizacao(old_atendimento, new_status, final_statuses):
    """True se o status novo é final e ainda não há horário de finalização."""
    if new_status not in final_statuses:
        return False
    return not (old_atendimento or {}).get("horario_finalizacao_atendimentos")


def _prodesp_hostname_logs_efetivos(
    old_unidade, unidade_updates, old_atendimento, atendimento_updates
):
    """Hostname/logs efetivos do POST (updates) ou persistidos — mesmo critério do UPDATE."""
    uni_upd = unidade_updates or {}
    att_upd = atendimento_updates or {}
    hostname = (
        uni_upd.get("hostname_unidades")
        if "hostname_unidades" in uni_upd
        else (old_unidade or {}).get("hostname_unidades")
    )
    logs = (
        att_upd.get("logs_atendimentos")
        if "logs_atendimentos" in att_upd
        else (old_atendimento or {}).get("logs_atendimentos")
    )
    return hostname, logs or ""


def _prodesp_gate_conclusao_concluido(
    cursor,
    *,
    status_efetivo,
    substatus_efetivo,
    old_unidade,
    unidade_updates,
    old_atendimento,
    atendimento_updates,
    id_unidade,
):
    """
    Ticket NOC + cruzamento FGT quando Status e Substatus são «Concluído».
    Deve rodar ANTES de gerar horario_finalizacao e ANTES do UPDATE.
    Retorna (mensagem, errors_list); mensagem None = ok.
    """
    if str(status_efetivo or "").strip() != "Concluído":
        return None, []
    if str(substatus_efetivo or "").strip() != "Concluído":
        return None, []
    ticket_msg = _prodesp_mensagem_ticket_noc_concluido(old_unidade, unidade_updates)
    if ticket_msg:
        return ticket_msg, []
    hostname_eff, logs_eff = _prodesp_hostname_logs_efetivos(
        old_unidade, unidade_updates, old_atendimento, atendimento_updates
    )
    eq_errs = _prodesp_erros_conclusao(
        cursor,
        id_unidade=id_unidade,
        hostname_unidade=hostname_eff,
        logs_atendimentos=logs_eff,
    )
    if eq_errs:
        return eq_errs[0], eq_errs
    return None, []


def _prodesp_reject_update(conn, entity_id, message, http=400, extra=None):
    """Rollback + log WARNING + JSON de erro (evita transação aberta no pool)."""
    if conn is not None:
        try:
            conn.rollback()
        except Exception:
            pass
    payload = {"success": False, "message": message}
    if extra:
        payload.update(extra)
    try:
        current_app.logger.warning(
            "prodesp - update atendimento id=%s rejeitado http=%s: %s",
            entity_id,
            http,
            message,
        )
    except Exception:
        pass
    return jsonify(payload), http


def _prodesp_listar_observacoes_unidade_agendado(cursor, id_unidade):
    """Observações da unidade sem atendimento vinculado (pré-atendimento / agendado)."""
    cursor.execute(
        """SELECT id_observacoes AS id, observacoes AS texto, timestamp_observacoes AS timestamp
           FROM observacoes
           WHERE id_unidades_observacoes = %s AND id_atendimentos_observacoes IS NULL
           ORDER BY timestamp_observacoes""",
        (id_unidade,),
    )
    observacoes = cursor.fetchall()
    for obs in observacoes:
        if isinstance(obs.get('timestamp'), (datetime, date)):
            obs['timestamp'] = obs['timestamp'].strftime('%d/%m/%Y %H:%M:%S')
    return observacoes


def _prodesp_listar_observacoes_atendimento_e_unidade(cursor, id_atendimento, id_unidade):
    """Observações do atendimento + unidade ainda sem vínculo (visão completa no modal)."""
    cursor.execute(
        """
        SELECT id_observacoes AS id, observacoes AS texto,
               timestamp_observacoes AS timestamp,
               id_atendimentos_observacoes
        FROM observacoes
        WHERE id_atendimentos_observacoes = %s
           OR (id_unidades_observacoes = %s AND id_atendimentos_observacoes IS NULL)
        ORDER BY timestamp_observacoes ASC, id_observacoes ASC
        """,
        (id_atendimento, id_unidade),
    )
    observacoes = cursor.fetchall()
    for obs in observacoes:
        if isinstance(obs.get('timestamp'), (datetime, date)):
            obs['timestamp'] = obs['timestamp'].strftime('%d/%m/%Y %H:%M:%S')
    return observacoes


def _prodesp_vincular_observacoes_unidade_ao_atendimento(cursor, conn, id_unidade, id_atendimento):
    """Associa observações pré-atendimento da unidade ao novo atendimento."""
    cursor.execute(
        """
        SELECT id_observacoes, observacoes
        FROM observacoes
        WHERE id_unidades_observacoes = %s AND id_atendimentos_observacoes IS NULL
        """,
        (id_unidade,),
    )
    rows = cursor.fetchall()
    if not rows:
        return 0
    cursor.execute(
        """
        UPDATE observacoes
        SET id_atendimentos_observacoes = %s
        WHERE id_unidades_observacoes = %s AND id_atendimentos_observacoes IS NULL
        """,
        (id_atendimento, id_unidade),
    )
    for row in rows:
        registrar_log(
            conn,
            'atendimentos',
            id_atendimento,
            'Observação',
            None,
            row.get('observacoes'),
            'INSERT',
        )
    return len(rows)


def _prodesp_slot_agendamento_para_js(atendimento, tz_sp):
    """Data/hora agendadas (unidade) como ISO para cronômetro de atraso no dashboard."""
    dt_ag = parse_date_string(
        atendimento.get('data_agendamento'),
        current_app.logger,
        atendimento.get('id_atendimento'),
    )
    if not dt_ag:
        return None
    if isinstance(dt_ag, datetime):
        dia_ag = dt_ag.date()
    elif isinstance(dt_ag, date):
        dia_ag = dt_ag
    else:
        return None
    hora_obj = _prodesp_time_from_value(atendimento.get('hora_agendamento'))
    if not hora_obj:
        return None
    dt_slot = datetime.combine(dia_ag, hora_obj)
    return tz_sp.localize(dt_slot).isoformat()


def _prodesp_datetime_para_js_iso(dt_val, tz_sp, logger=None, record_id=None):
    """Normaliza datetime/str do MySQL para ISO com timezone (cronômetro JS)."""
    if dt_val is None or dt_val == "":
        return None
    if isinstance(dt_val, str):
        dt_val = parse_date_string(dt_val, logger or current_app.logger, record_id)
    if not isinstance(dt_val, datetime):
        return None
    if dt_val.tzinfo is None:
        dt_val = tz_sp.localize(dt_val)
    return dt_val.isoformat()


def _prodesp_aplicar_campos_tempo_api(row: dict) -> None:
    """Enriquece linha da API (atendimentos_list / dashboard) com campos de cronômetro."""
    adaptado = {
        "id_atendimento": row.get("id_atendimento") or row.get("id_atendimentos"),
        "status_atendimentos": row.get("status_atendimentos") or row.get("status_atendimento"),
        "substatus_atendimentos": row.get("substatus_atendimentos") or row.get("substatus_atendimento"),
        "data_atendimento": row.get("data_atendimento") or row.get("data_atendimentos"),
        "horario_inicio": row.get("horario_inicio") or row.get("horario_inicio_atendimentos"),
        "horario_finalizacao": row.get("horario_finalizacao") or row.get("horario_finalizacao_atendimentos"),
        "tempo_total_geral": row.get("tempo_total_geral"),
        "data_agendamento": row.get("data_agendamento"),
        "hora_agendamento": row.get("hora_agendamento"),
        "ultimo_substatus_log": row.get("ultimo_substatus_log"),
    }
    processar_atendimentos_para_dashboard([adaptado])
    tz_sp = pytz.timezone("America/Sao_Paulo")
    status_row = (adaptado.get("status_atendimentos") or "").strip()
    if (
        status_row not in ({"Agendado"} | FINAL_STATUSES_ATENDIMENTO)
        and adaptado.get("modo_duracao") == "em_andamento"
        and adaptado.get("ultimo_substatus_log")
    ):
        iso_log = _prodesp_datetime_para_js_iso(
            adaptado["ultimo_substatus_log"],
            tz_sp,
            record_id=adaptado.get("id_atendimento"),
        )
        if iso_log:
            adaptado["data_para_js"] = iso_log
    row["data_para_js"] = adaptado.get("data_para_js")
    row["data_inicio_total_js"] = adaptado.get("data_inicio_total_js")
    row["modo_duracao"] = adaptado.get("modo_duracao")
    row["tempo_total_calculado"] = adaptado.get("tempo_total_calculado")
    row["tempo_em_segundos"] = adaptado.get("tempo_em_segundos")


def processar_atendimentos_para_dashboard(atendimentos_list):
    tz_sp = pytz.timezone('America/Sao_Paulo')
    for atendimento in atendimentos_list:
        atendimento['data_para_js'] = None
        atendimento['data_inicio_total_js'] = None
        atendimento['tempo_total_calculado'] = "---"
        atendimento['tempo_em_segundos'] = None
        atendimento['modo_duracao'] = None
        atendimento_id = atendimento.get('id_atendimento')
        status = (
            atendimento.get('status_atendimentos')
            or atendimento.get('status_atendimento')
            or ''
        ).strip()

        # Só agendamento: atraso em tempo real vs data + hora agendadas
        if status == 'Agendado' or not atendimento_id:
            slot_iso = _prodesp_slot_agendamento_para_js(atendimento, tz_sp)
            if slot_iso:
                atendimento['data_para_js'] = slot_iso
                atendimento['modo_duracao'] = 'atraso_agendado'
            else:
                atendimento['modo_duracao'] = 'pendente'
            continue

        dt_atendimento = parse_date_string(atendimento.get('data_atendimento'), current_app.logger, atendimento_id)
        atendimento['data_atendimentos'] = dt_atendimento
        if not dt_atendimento:
            atendimento['tempo_total_calculado'] = "N/A (Data Base Inválida)"
            continue
        if isinstance(dt_atendimento, datetime):
            dia_att = _prodesp_dia_atendimento_para_cronometro(
                dt_atendimento, status, record_id=atendimento_id
            )
        elif isinstance(dt_atendimento, date):
            dia_att = _prodesp_dia_atendimento_para_cronometro(
                dt_atendimento, status, record_id=atendimento_id
            )
        else:
            atendimento['tempo_total_calculado'] = "N/A (Data Base Inválida)"
            continue
        if not dia_att:
            atendimento['tempo_total_calculado'] = "N/A (Data Base Inválida)"
            continue

        if status in FINAL_STATUSES_ATENDIMENTO:
            seg_view = _prodesp_tempo_valor_para_segundos(atendimento.get('tempo_total_geral'))
            if seg_view is not None:
                atendimento['tempo_em_segundos'] = seg_view
                atendimento['tempo_total_calculado'] = _prodesp_formatar_segundos_hhmmss(seg_view)
                atendimento['modo_duracao'] = 'finalizado'
                continue

            time_inicio_obj = _prodesp_time_from_value(atendimento.get('horario_inicio'))
            time_final_obj = _prodesp_time_from_value(atendimento.get('horario_finalizacao'))
            if time_inicio_obj and time_final_obj:
                dt_inicio_completo = datetime.combine(dia_att, time_inicio_obj)
                dt_final_completo = datetime.combine(dia_att, time_final_obj)
                if dt_final_completo < dt_inicio_completo:
                    dt_final_completo += timedelta(days=1)
                segundos_liquidos = max(
                    0, int((dt_final_completo - dt_inicio_completo).total_seconds())
                )
                dt_inicio_aware = tz_sp.localize(dt_inicio_completo)
                atendimento['data_inicio_total_js'] = dt_inicio_aware.isoformat()
                atendimento['data_para_js'] = dt_inicio_aware.isoformat()
                atendimento['tempo_em_segundos'] = segundos_liquidos
                atendimento['tempo_total_calculado'] = _prodesp_formatar_segundos_hhmmss(segundos_liquidos)
                atendimento['modo_duracao'] = 'finalizado'
                continue

            # Encerrado sem horários completos: não expor início para cronômetro ao vivo.
            atendimento['modo_duracao'] = 'finalizado'
            atendimento['data_inicio_total_js'] = None
            atendimento['data_para_js'] = None
            continue

        time_inicio_obj = _prodesp_time_from_value(atendimento.get('horario_inicio'))
        if not time_inicio_obj:
            continue

        dt_inicio_completo = datetime.combine(dia_att, time_inicio_obj)
        dt_inicio_aware = tz_sp.localize(dt_inicio_completo)
        atendimento['data_inicio_total_js'] = dt_inicio_aware.isoformat()
        atendimento['data_para_js'] = dt_inicio_aware.isoformat()
        atendimento['modo_duracao'] = 'em_andamento'


def gerar_csv_prodesp(dados):
    """
    Gera um arquivo CSV com os dados da unidade e seus links.
    :param dados: Dicionário contendo dados da unidade e links achatados (ex: designador_1, designador_2).
    :return: Caminho completo do arquivo gerado.
    """
    try:
        id_vgr = dados.get('id_vgr_unidades', 'sem_id')
        hostname = dados.get('hostname_unidades', 'sem_hostname')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        nome_arquivo = f"prodesp_{id_vgr}_{hostname}_{timestamp}.csv"
        caminho_completo = os.path.join(CSV_DIR, nome_arquivo)

        # Definição das colunas do CSV (Cabeçalho)
        # Inclui dados da unidade e dados para até 2 links
        fieldnames = [
            'id_vgr', 'nome', 'acronimo', 'hostname', 'ip_lan_01', 'mv_ip_lan_sec',
            'loopback_vivo', 'loopback_cliente', 'id_intragov',
            # Link 1
            'link1_designador', 'link1_tipo', 'link1_operadora', 'link1_vlan', 
            'link1_ip_wan', 'link1_gateway', 'link1_mascara', 'link1_velocidade', 
            'link1_pppoe_user', 'link1_pppoe_pass',
            # Link 2
            'link2_designador', 'link2_tipo', 'link2_operadora', 'link2_vlan', 
            'link2_ip_wan', 'link2_gateway', 'link2_mascara', 'link2_velocidade', 
            'link2_pppoe_user', 'link2_pppoe_pass'
        ]

        # Mapeamento dos dados recebidos para as colunas do CSV
        row = {
            'id_vgr': dados.get('id_vgr_unidades'),
            'nome': dados.get('nome_unidades'),
            'acronimo': dados.get('acronimo_unidades'),
            'hostname': dados.get('hostname_unidades'),
            'ip_lan_01': dados.get('ip_lan_01_unidades'),
            'mv_ip_lan_sec': dados.get('mv_ip_lan_sec_unidades'),
            'loopback_vivo': dados.get('loopback_vivo_unidades'),
            'loopback_cliente': dados.get('loopback_cliente_unidades'),
            'id_intragov': dados.get('id_intragov_unidades'),
            
            # Link 1
            'link1_designador': dados.get('designador_1'), 'link1_tipo': dados.get('tipo_1'),
            'link1_operadora': dados.get('operadora_1'), 'link1_vlan': dados.get('vlan_1'),
            'link1_ip_wan': dados.get('ip_wan_1'), 'link1_gateway': dados.get('ip_gateway_1'),
            'link1_mascara': dados.get('ip_mascara_1'), 'link1_velocidade': dados.get('velocidade_1'),
            'link1_pppoe_user': dados.get('pppoe_user_1'), 'link1_pppoe_pass': dados.get('pppoe_pass_1'),

            # Link 2
            'link2_designador': dados.get('designador_2'), 'link2_tipo': dados.get('tipo_2'),
            'link2_operadora': dados.get('operadora_2'), 'link2_vlan': dados.get('vlan_2'),
            'link2_ip_wan': dados.get('ip_wan_2'), 'link2_gateway': dados.get('ip_gateway_2'),
            'link2_mascara': dados.get('ip_mascara_2'), 'link2_velocidade': dados.get('velocidade_2'),
            'link2_pppoe_user': dados.get('pppoe_user_2'), 'link2_pppoe_pass': dados.get('pppoe_pass_2'),
        }

        with open(caminho_completo, mode='w', newline='', encoding='utf-8-sig') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            writer.writerow(row)
            
        logging.info(f"Arquivo CSV gerado com sucesso: {caminho_completo}")
        return caminho_completo

    except Exception as e:
        logging.error(f"Erro ao gerar CSV prodesp: {e}")
        raise e

# =================================================================================
# ROTAS DA APLICAÇÃO
# =================================================================================

@prodesp_bp.route('/supervisao')
@login_required
def supervisao():
    return render_template('supervisao_prodesp.html', hoje=date.today())

_PRODESP_GRUPOS_FILAS_BACKEND = {
    "Aguarda Gestão": {
        "label": "Aguarda Gestão",
        "substatuses": [SUBSTATUS_AGUARDA_GESTAO, SUBSTATUS_LEGACY_TRIAGEM],
        "icon": "fas fa-filter",
        "hide_group_card": True,
    },
    "Aguardando Cliente": {
        "label": "Aguardando Cliente",
        "substatuses": ["Aguardando Cliente"],
        "icon": "fas fa-user-clock",
        "hide_group_card": True,
    },
    "Aguarda Contratada": {
        "label": "Aguarda Contratada",
        "substatuses": [SUBSTATUS_AGUARDA_CONTRATADA],
        "icon": "fas fa-building",
        "hide_group_card": True,
    },
    "Aguarda Licença": {
        "label": "Aguarda Licença",
        "substatuses": [SUBSTATUS_AGUARDA_LICENCA],
        "icon": "fas fa-id-card",
        "hide_group_card": True,
    },
    "Com Suporte": {
        "label": "Com Suporte",
        "substatuses": [SUBSTATUS_COM_SUPORTE],
        "icon": "fas fa-life-ring",
        "hide_group_card": True,
    },
    "Config. Remota": {
        "label": "Config. Remota",
        "substatuses": ["Aguardando Config. Remota", "Em Configuração Remota"],
        "icon": "fas fa-laptop-code",
        "hide_group_card": True,
    },
    "MPLS": {
        "label": "MPLS",
        "substatuses": ["Aguardando Config. MPLS", "Em Configuração do MPLS"],
        "icon": "fas fa-network-wired",
        "hide_group_card": True,
    },
    "Caderno de Teste": {
        "label": "Caderno",
        "substatuses": ["Aguardando Caderno de Teste", "Em Caderno de Teste"],
        "icon": "fas fa-clipboard-list",
        "hide_group_card": True,
    },
}

_PRODESP_ALL_SUBSTATUS_DETAILS = {
    SUBSTATUS_AGUARDA_GESTAO: {"icon": "fas fa-filter"},
    SUBSTATUS_LEGACY_TRIAGEM: {"icon": "fas fa-filter"},
    SUBSTATUS_COM_SUPORTE: {"icon": "fas fa-life-ring"},
    "Aguardando Cliente": {"icon": "fas fa-user-clock"},
    SUBSTATUS_AGUARDA_CONTRATADA: {"icon": "fas fa-building"},
    SUBSTATUS_AGUARDA_LICENCA: {"icon": "fas fa-id-card"},
    "Aguardando Config. Remota": {"icon": "fas fa-hourglass-half"},
    "Em Configuração Remota": {"icon": "fas fa-laptop-code"},
    "Aguardando Config. MPLS": {"icon": "fas fa-hourglass-half"},
    "Em Configuração do MPLS": {"icon": "fas fa-network-wired"},
    "Aguardando Caderno de Teste": {"icon": "fas fa-hourglass-half"},
    "Em Caderno de Teste": {"icon": "fas fa-clipboard-list"},
}


def _prodesp_build_grouped_cards_from_stats(substatus_stats):
    filas_substatuses = set()
    for group in _PRODESP_GRUPOS_FILAS_BACKEND.values():
        filas_substatuses.update(group["substatuses"])
    total_geral = sum(substatus_stats.get(s, 0) for s in filas_substatuses)
    grouped_cards_data = {}
    for group_name, group_info in _PRODESP_GRUPOS_FILAS_BACKEND.items():
        group_total_count = 0
        group_substatus_cards = []
        for substatus_key in group_info["substatuses"]:
            count = substatus_stats.get(substatus_key, 0)
            group_total_count += count
            substatus_detail = _PRODESP_ALL_SUBSTATUS_DETAILS.get(
                substatus_key, {"icon": "fas fa-question-circle text-muted"}
            )
            group_substatus_cards.append(
                {
                    "key": substatus_key,
                    "label": substatus_key,
                    "icon": substatus_detail["icon"],
                    "count": count,
                }
            )
        grouped_cards_data[group_name] = {
            "label": group_info["label"],
            "icon": group_info["icon"],
            "total_count": group_total_count,
            "substatus_cards": group_substatus_cards,
            "hide_group_card": group_info.get("hide_group_card", False),
        }
    return grouped_cards_data, total_geral


def _prodesp_analistas_implantacao_nomes(user):
    """Nomes de analistas IMPLANTAÇÃO ativos (somente para UI admin na fila)."""
    if not _prodesp_is_admin(user):
        return []
    from login.models import User

    nomes = set()
    for u in User.all(departamento="IMPLANTAÇÃO", apenas_ativos=True):
        nome = (getattr(u, "nome_user", "") or "").strip()
        if nome:
            nomes.add(nome)
    return sorted(nomes)


@prodesp_bp.route('/atendimentos')
@login_required
def atendimentos():
    """SSR leve: KPIs e tabela vêm de /api/atendimentos_list (evita query duplicada)."""
    grouped_cards_data, total_geral = _prodesp_build_grouped_cards_from_stats({})
    return render_template(
        "atendimentos_prodesp.html",
        atendimentos=[],
        total_geral=total_geral,
        grouped_cards_data=grouped_cards_data,
        kpi_agendados=0,
        prodesp_list_server_side=_prodesp_list_server_side_ui(),
        **_prodesp_atendimentos_modais_template_context(current_user),
    )

def _prodesp_atendimentos_list_from_rows(todos, user, resumo=None):
    """Monta JSON da lista a partir das linhas da view (filtro por perfil no caller)."""
    from prodesp.prodesp.atendimentos_list_query import slim_list_row

    ver_todos_na_tabela = _prodesp_is_admin(user)
    tabela_data = []
    for c in todos:
        if ver_todos_na_tabela:
            tabela_data.append(c)
            continue
        status_val = str(c.get('status_atendimento') or '').strip().lower()
        if status_val not in ['concluido', 'concluído']:
            tabela_data.append(c)

    if resumo is None:
        substatus_stats = defaultdict(int)
        for c in todos:
            sub = c.get('substatus_atendimento')
            if sub and sub.strip():
                substatus_stats[sub] += 1

        filas_substatuses = [
            SUBSTATUS_AGUARDA_GESTAO,
            SUBSTATUS_LEGACY_TRIAGEM,
            SUBSTATUS_COM_SUPORTE,
            'Aguardando Cliente',
            SUBSTATUS_AGUARDA_CONTRATADA,
            SUBSTATUS_AGUARDA_LICENCA,
            'Aguardando Config. Remota', 'Em Configuração Remota',
            'Aguardando Config. MPLS', 'Em Configuração do MPLS',
            'Aguardando Caderno de Teste', 'Em Caderno de Teste'
        ]
        total_geral_fila = sum(substatus_stats.get(s, 0) for s in filas_substatuses)

        kpi_agendados_vw = sum(
            1 for x in todos
            if (x.get('status_atendimento') or '').strip() == 'Agendado'
        )
        resumo = {
            'total_geral': total_geral_fila,
            'agendados': kpi_agendados_vw,
            'substatus_counts': dict(substatus_stats),
        }

    # Serialização segura
    for c in tabela_data:
        if not (c.get('status_atendimento') or '').strip():
            if c.get('id_atendimento') in (None, ''):
                c['status_atendimento'] = 'Agendado'
            elif (c.get('substatus_atendimento') or '').strip() == 'Sem atendimento iniciado':
                c['status_atendimento'] = 'Agendado'
        if c.get("data_atendimento") is not None and c.get("data_atendimento") != "":
            c["data_atendimento_raw"] = c["data_atendimento"]
        _prodesp_normalizar_data_atendimento_lista(c)
        sub_disp = (c.get("substatus_atendimento") or "").strip()
        if sub_disp:
            c["substatus_atendimento"] = normalizar_substatus_fluxo(sub_disp)
        _prodesp_aplicar_campos_tempo_api(c)
        _prodesp_anexar_flags_edicao(user, c)
        for key, value in list(c.items()):
            if value is None:
                c[key] = ""  # Essencial para o DataTable ColumnControl não crashar
            elif isinstance(value, (datetime, date)):
                c[key] = value.isoformat()
            elif isinstance(value, timedelta):
                c[key] = str(value)
            elif isinstance(value, str):
                c[key] = value  # Mantém espaços e quebras de linha originais
            elif hasattr(value, '__str__') and not isinstance(value, (int, float, str, bool)):
                c[key] = str(value)
        slim_list_row(c)

    return {
        'atendimentos': tabela_data,
        'resumo': resumo,
    }


def _prodesp_carregar_resumo_lista(cursor):
    """KPIs da fila (dataset completo, leve)."""
    from prodesp.prodesp.atendimentos_list_query import (
        build_resumo_agendados_query,
        build_resumo_query,
        resumo_from_substatus_rows,
    )

    cursor.execute(build_resumo_query())
    sub_rows = cursor.fetchall()
    cursor.execute(build_resumo_agendados_query())
    ag_row = cursor.fetchone() or {}
    return resumo_from_substatus_rows(sub_rows, agendados=int(ag_row.get('cnt') or 0))


def _prodesp_processar_linha_lista_api(row, user):
    """Normaliza uma linha da lista (tempo, flags, serialização)."""
    from prodesp.prodesp.atendimentos_list_query import slim_list_row

    if not (row.get('status_atendimento') or '').strip():
        if row.get('id_atendimento') in (None, ''):
            row['status_atendimento'] = 'Agendado'
        elif (row.get('substatus_atendimento') or '').strip() == 'Sem atendimento iniciado':
            row['status_atendimento'] = 'Agendado'
    if row.get("data_atendimento") is not None and row.get("data_atendimento") != "":
        row["data_atendimento_raw"] = row["data_atendimento"]
    _prodesp_normalizar_data_atendimento_lista(row)
    sub_disp = (row.get("substatus_atendimento") or "").strip()
    if sub_disp:
        row["substatus_atendimento"] = normalizar_substatus_fluxo(sub_disp)
    _prodesp_aplicar_campos_tempo_api(row)
    _prodesp_anexar_flags_edicao(user, row)
    for key, value in list(row.items()):
        if value is None:
            row[key] = ""
        elif isinstance(value, (datetime, date)):
            row[key] = value.isoformat()
        elif isinstance(value, timedelta):
            row[key] = str(value)
        elif isinstance(value, str):
            row[key] = value
        elif hasattr(value, '__str__') and not isinstance(value, (int, float, str, bool)):
            row[key] = str(value)
    slim_list_row(row)
    return row


@prodesp_bp.route('/api/atendimentos_list')
@login_required
@with_server_ms
def api_atendimentos_list():
    from prodesp.prodesp.atendimentos_list_cache import (
        get as list_cache_get,
        get_processed as list_cache_get_processed,
        get_resumo as list_cache_get_resumo,
        set as list_cache_set,
        set_processed as list_cache_set_processed,
        set_resumo as list_cache_set_resumo,
    )
    from prodesp.prodesp.atendimentos_list_query import (
        build_count_query,
        build_full_list_query,
        build_paginated_query,
        effective_scope,
        list_server_side_enabled,
        parse_dt_request_args,
    )

    is_admin = _prodesp_is_admin(current_user)
    dt_args = parse_dt_request_args(request.args)
    scope = effective_scope(dt_args.get("scope"), is_admin=is_admin)

    resumo = list_cache_get_resumo()
    if resumo is None:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            resumo = _prodesp_carregar_resumo_lista(cursor)
            list_cache_set_resumo(resumo)
        finally:
            cursor.close()
            conn.close()

    server_side = list_server_side_enabled() and dt_args["draw"] > 0
    if server_side:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            count_sql, count_params = build_count_query(
                scope,
                global_search=dt_args["global_search"],
                col_searches=dt_args["col_searches"],
                card_filter=dt_args["card_filter"] or None,
            )
            cursor.execute(count_sql, count_params)
            counts = cursor.fetchone() or {}
            page_sql, page_params = build_paginated_query(
                scope,
                start=dt_args["start"],
                length=dt_args["length"],
                order_col=dt_args["order_col"],
                order_dir=dt_args["order_dir"],
                global_search=dt_args["global_search"],
                col_searches=dt_args["col_searches"],
                card_filter=dt_args["card_filter"] or None,
            )
            cursor.execute(page_sql, page_params)
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        tabela_data = []
        for row in rows:
            item = dict(row)
            if not is_admin:
                st = str(item.get("status_atendimento") or "").strip().lower()
                if st in ("concluido", "concluído"):
                    continue
            tabela_data.append(_prodesp_processar_linha_lista_api(item, current_user))

        from prodesp.prodesp.data_revision import attach_to_payload

        return jsonify(attach_to_payload({
            "draw": dt_args["draw"],
            "recordsTotal": int(counts.get("records_total") or 0),
            "recordsFiltered": int(counts.get("records_filtered") or 0),
            "data": tabela_data,
            "atendimentos": tabela_data,
            "resumo": resumo,
            "scope": scope,
        }))

    user_key = f"{_prodesp_list_cache_user_key(current_user)}:{scope}"
    processed = list_cache_get_processed(user_key)
    if processed is not None:
        from prodesp.prodesp.data_revision import attach_to_payload

        return jsonify(attach_to_payload(processed))

    cache_key = f"todos_{scope}"
    cached = list_cache_get()
    todos = None
    if cached and cached.get(cache_key) is not None:
        todos = cached[cache_key]
    else:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            query, params = build_full_list_query(scope)
            cursor.execute(query, params)
            todos = cursor.fetchall()
            payload_cache = dict(cached) if cached else {}
            payload_cache[cache_key] = todos
            list_cache_set(payload_cache)
        finally:
            cursor.close()
            conn.close()

    payload = _prodesp_atendimentos_list_from_rows(todos, current_user, resumo=resumo)
    payload["scope"] = scope
    list_cache_set_processed(user_key, payload)
    from prodesp.prodesp.data_revision import attach_to_payload

    return jsonify(attach_to_payload(payload))


@prodesp_bp.route('/api/data_revision', methods=['GET'])
@login_required
def api_data_revision():
    """Poll leve: revisão global incrementada após mutações (fila + gestão)."""
    from prodesp.prodesp.data_revision import revision_payload

    return jsonify(revision_payload())


@prodesp_bp.route('/api/atendimentos_list_delta', methods=['GET'])
@login_required
@with_server_ms
def api_atendimentos_list_delta():
    """Delta da fila: linhas slim + resumo KPI desde ``since_revision``.

    Feature flag ``PRODESP_ATENDIMENTOS_LIST_DELTA`` (padrão off). Com flag off
    responde ``fallback_full`` para o cliente usar ajax.reload.

    Fase 2: ``updated`` (em scope), ``removed_ids`` (saiu do scope / sumiu),
    ``resumo`` KPI; cliente faz add/patch/remove sem full reload.
    """
    from prodesp.prodesp.atendimentos_list_cache import (
        get_resumo as list_cache_get_resumo,
        set_resumo as list_cache_set_resumo,
    )
    from prodesp.prodesp.atendimentos_list_query import (
        build_rows_by_ids_query,
        effective_scope,
        list_delta_enabled,
        row_in_scope,
    )
    from prodesp.prodesp.data_revision import attach_to_payload, dirty_ids_since

    is_admin = _prodesp_is_admin(current_user)
    scope = effective_scope(request.args.get("scope"), is_admin=is_admin)

    def _empty_delta(**extra):
        payload = {
            "unchanged": False,
            "fallback_full": False,
            "updated": [],
            "removed_ids": [],
            "added": [],
            "resumo": None,
            "scope": scope,
        }
        payload.update(extra)
        return jsonify(attach_to_payload(payload))

    if not list_delta_enabled():
        return _empty_delta(fallback_full=True)

    try:
        since = int(request.args.get("since_revision") or -1)
    except (TypeError, ValueError):
        since = -1

    info = dirty_ids_since(since)
    if info.get("unchanged"):
        return _empty_delta(unchanged=True)

    if info.get("fallback_full"):
        return _empty_delta(fallback_full=True)

    dirty_ids = list(info.get("ids") or [])
    if not dirty_ids:
        return _empty_delta(unchanged=True)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query, params = build_rows_by_ids_query(dirty_ids)
        cursor.execute(query, params)
        rows = cursor.fetchall() or []

        resumo = list_cache_get_resumo()
        if resumo is None:
            resumo = _prodesp_carregar_resumo_lista(cursor)
            list_cache_set_resumo(resumo)
    finally:
        cursor.close()
        conn.close()

    updated = []
    for row in rows:
        item = dict(row)
        if not row_in_scope(item, scope):
            continue
        if not is_admin:
            st = str(item.get("status_atendimento") or "").strip().lower()
            if st in ("concluido", "concluído"):
                continue
        updated.append(_prodesp_processar_linha_lista_api(item, current_user))

    updated_ids = set()
    for r in updated:
        try:
            updated_ids.add(int(r.get("id_atendimento")))
        except (TypeError, ValueError):
            pass
    removed_ids = [i for i in dirty_ids if i not in updated_ids]

    return jsonify(attach_to_payload({
        "unchanged": False,
        "fallback_full": False,
        "updated": updated,
        "removed_ids": removed_ids,
        "added": [],
        "resumo": resumo,
        "scope": scope,
    }))


@prodesp_bp.route('/dashboard_atendimentos')
@login_required
def dashboard_atendimentos():
    if not _prodesp_pode_acessar_dashboard_gestao(current_user):
        portal_flash(
            "O dashboard de gestão não está disponível para o perfil Implantação. "
            "Utilize a tela de Atendimentos.",
            "warning",
            scope="prodesp",
        )
        return redirect(url_for("prodesp.atendimentos"))
    return render_template('dashboard_atendimentos_prodesp.html',
                           start_date=datetime.now().date(),
                           end_date=datetime.now().date(),
                           atendimentos_Concluídos=0,
                           atendimentos_quebra=0,
                           atendimentos_em_atendimento=0,
                           atendimentos_concluído_parcial=0, 
                           media_tempo_atendimento="00:00:00",
                           perc_Concluídos="0%",
                           usuario_logado_admin=current_user.admin_user,
                           show_tempos_etapa_kpis=_prodesp_pode_ver_kpis_tempo_executivo(current_user),
                           gestao_operar_atendimentos=_prodesp_pode_operar_atendimentos_na_gestao(current_user),
                           **_prodesp_atendimentos_modais_template_context(current_user))

@prodesp_bp.route('/criar_csv')
@login_required
def criar_csv_prodesp_page():
    """
    Renderiza a página inicial para criação de CSV do cliente prodesp.
    """
    return render_template('prodesp_criar_csv.html', unidade={})

@prodesp_bp.route('/buscar_unidade_csv', methods=['POST'])
@login_required
def buscar_unidade_csv_prodesp():
    """
    Busca os dados de uma unidade pelo id_vgr e os exibe no formulário de CSV.
    """
    id_vgr = request.form.get('id_vgr')
    if not id_vgr:
        portal_flash("Por favor, digite um ID VGR para buscar.", 'warning', scope="prodesp")
        return redirect(url_for('prodesp.criar_csv_prodesp_page'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Busca dados da unidade
        cursor.execute(sql_select_unidades_by_id_vgr(), (id_vgr,))
        unidade_data = cursor.fetchone()

        if unidade_data:
            decrypt_sensitive_row_inplace(unidade_data)
            # Busca links associados
            cursor.execute(
                sql_select_links_by_unidade(order=True),
                (unidade_data['id_unidades'],),
            )
            links_data = decrypt_sensitive_rows_inplace(cursor.fetchall())
            
            # "Achata" os dados dos links no dicionário da unidade para preencher o form
            for i, link in enumerate(links_data, 1):
                for key, value in link.items():
                    # remove prefixo '..._links'
                    clean_key = key.replace('_links', '')
                    unidade_data[f'{clean_key}_{i}'] = value

            portal_flash(f"Dados da unidade {id_vgr} carregados com sucesso!", 'success', scope="prodesp")
            return render_template('prodesp_criar_csv.html', unidade=unidade_data)
        else:
            portal_flash(f"Nenhuma unidade encontrada com o ID VGR: {id_vgr}.", 'warning', scope="prodesp")
            # Retorna para a página com o ID VGR preenchido para o usuário criar uma nova
            return render_template('prodesp_criar_csv.html', unidade={'id_vgr_unidades': id_vgr})
    except Exception as e:
        current_app.logger.error(f"prodesp - Erro ao buscar unidade {id_vgr} para CSV: {e}")
        portal_flash("Erro ao buscar dados da unidade. Tente novamente ou contate o suporte.", 'danger', scope="prodesp")
        return redirect(url_for('prodesp.criar_csv_prodesp_page'))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@prodesp_bp.route('/gerar_csv_prodesp', methods=['POST'])
@login_required
def gerar_csv_prodesp_action():
    """
    Salva as alterações no banco de dados para unidades e links, 
    registra no histórico e gera o arquivo CSV.
    """
    id_vgr = request.form.get('id_vgr')
    if not id_vgr:
        portal_flash("ID VGR não fornecido.", 'danger', scope="prodesp")
        return redirect(url_for('prodesp.criar_csv_prodesp_page'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Verificar se a unidade existe. Se não, criar.
        cursor.execute(sql_select_unidades_by_id_vgr(), (id_vgr,))
        old_unidade_data = cursor.fetchone()
        id_unidade = None

        unidade_updates = {}
        # Campos da tabela 'unidades' que podem ser editados no formulário
        unidade_editable_fields = [
            'hostname_unidades', 'ip_lan_unidades', 'loopback_vivo_unidades', 
            'loopback_cliente_unidades', 'id_intragov_unidades'
        ]
        
        for field in unidade_editable_fields:
            form_key = field.replace('_unidades', '')
            new_value = request.form.get(form_key, '').strip()
            unidade_updates[field] = new_value if new_value else None

        if old_unidade_data:
            id_unidade = old_unidade_data['id_unidades']
            # Filtrar apenas os campos que realmente mudaram
            changed_fields = {k: v for k, v in unidade_updates.items() if str(v or '') != str(old_unidade_data.get(k) or '')}
            
            if changed_fields:
                set_clauses = [f"`{col}` = %s" for col in changed_fields.keys()]
                sql_update = f"UPDATE unidades SET {', '.join(set_clauses)} WHERE id_unidades = %s"
                params = list(changed_fields.values()) + [id_unidade]
                cursor.execute(sql_update, params)
                
                for col, novo in changed_fields.items():
                    registrar_log(conn, 'unidades', id_unidade, col, old_unidade_data.get(col), novo, 'UPDATE')
                
                portal_flash("Dados da unidade atualizados no banco de dados!", 'success', scope="prodesp")
        else:
            # Criar nova unidade se não existir
            unidade_updates['id_vgr_unidades'] = id_vgr
            # Adicionar outros campos do form que vão para a tabela unidades
            unidade_updates['nome_unidades'] = request.form.get('nome', '').strip()
            unidade_updates['acronimo_unidades'] = request.form.get('acronimo', '').strip()
            
            cols = ', '.join([f"`{k}`" for k in unidade_updates.keys()])
            placeholders = ', '.join(['%s'] * len(unidade_updates))
            sql_insert = f"INSERT INTO unidades ({cols}) VALUES ({placeholders})"
            cursor.execute(sql_insert, list(unidade_updates.values()))
            id_unidade = cursor.lastrowid
            registrar_log(conn, 'unidades', id_unidade, 'unidade', None, f'Unidade criada para VGR {id_vgr}', 'INSERT')
            portal_flash("Nova unidade cadastrada com sucesso!", 'success', scope="prodesp")

        # 2. Processar links (UPSERT)
        for i in range(1, 3):
            designador = request.form.get(f'designador_{i}', '').strip()
            if not designador:
                continue

            link_data = {
                'id_unidades_links': id_unidade, 'id_vgr_links': id_vgr, 'designador_links': designador,
                'tipo_links': request.form.get(f'tipo_{i}', '').strip(), 'operadora_links': request.form.get(f'operadora_{i}', '').strip(),
                'vlan_links': request.form.get(f'vlan_{i}', '').strip(), 'ip_wan_links': request.form.get(f'ip_wan_{i}', '').strip(),
                'ip_gateway_links': request.form.get(f'ip_gateway_{i}', '').strip(), 'ip_mascara_links': request.form.get(f'ip_mascara_{i}', '').strip(),
                'velocidade_links': request.form.get(f'velocidade_{i}', '').strip(), 'pppoe_user_links': request.form.get(f'pppoe_user_{i}', '').strip(),
                'pppoe_pass_links': request.form.get(f'pppoe_pass_{i}', '').strip(),
            }
            encrypt_link_pppoe_db_dict(link_data)
            link_data = {k: (v if v else None) for k, v in link_data.items()}

            sql_upsert_link = """
                INSERT INTO links (id_unidades_links, id_vgr_links, designador_links, tipo_links, operadora_links, vlan_links, ip_wan_links, ip_gateway_links, ip_mascara_links, velocidade_links, pppoe_user_links, pppoe_pass_links)
                VALUES (%(id_unidades_links)s, %(id_vgr_links)s, %(designador_links)s, %(tipo_links)s, %(operadora_links)s, %(vlan_links)s, %(ip_wan_links)s, %(ip_gateway_links)s, %(ip_mascara_links)s, %(velocidade_links)s, %(pppoe_user_links)s, %(pppoe_pass_links)s)
                ON DUPLICATE KEY UPDATE
                    tipo_links = VALUES(tipo_links), operadora_links = VALUES(operadora_links), vlan_links = VALUES(vlan_links),
                    ip_wan_links = VALUES(ip_wan_links), ip_gateway_links = VALUES(ip_gateway_links), ip_mascara_links = VALUES(ip_mascara_links),
                    velocidade_links = VALUES(velocidade_links), pppoe_user_links = VALUES(pppoe_user_links), pppoe_pass_links = VALUES(pppoe_pass_links);
            """
            cursor.execute(sql_upsert_link, link_data)
            registrar_log(conn, 'links', cursor.lastrowid, 'link_upsert', None, f'Link {designador} salvo para VGR {id_vgr}', 'UPDATE')

        conn.commit()

        # 3. Preparar dados para a geração do CSV
        cursor.execute(sql_select_unidades_by_id(), (id_unidade,))
        current_unidade_data = cursor.fetchone()
        decrypt_sensitive_row_inplace(current_unidade_data)
        cursor.execute(sql_select_links_by_unidade(order=True), (id_unidade,))
        current_links_data = decrypt_sensitive_rows_inplace(cursor.fetchall())
        
        for i, link in enumerate(current_links_data, 1):
            for key, value in link.items():
                clean_key = key.replace('_links', '')
                current_unidade_data[f'{clean_key}_{i}'] = value

        # 4. Gerar o arquivo CSV
        nome_arquivo_completo = gerar_csv_prodesp(current_unidade_data)

        # 5. Registrar a criação do CSV no histórico e gerar link de download
        filename_only = os.path.basename(nome_arquivo_completo)
        registrar_log(conn, 'unidades', id_unidade, 'csv_gerado', None, filename_only, 'INSERT')
        conn.commit()
        portal_flash(f"Arquivo CSV '{filename_only}' gerado com sucesso!", 'success', scope="prodesp")
        download_link = url_for('prodesp.download_prodesp_file', filename=filename_only)

        return render_template('prodesp_criar_csv.html', download_link=download_link, unidade=current_unidade_data)

    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"prodesp - Erro ao gerar CSV ou atualizar unidade {id_vgr}: {e}", exc_info=True)
        portal_flash("Ocorreu um erro ao processar a solicitação. Tente novamente ou contate o suporte.", 'danger', scope="prodesp")
        return redirect(url_for('prodesp.criar_csv_prodesp_page'))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@prodesp_bp.route('/download/prodesp/<filename>')
@login_required
def download_prodesp_file(filename):
    """
    Permite o download de arquivos CSV gerados para prodesp.
    """
    if not filename or os.path.basename(filename) != filename:
        portal_flash("Arquivo inválido.", "danger", scope="prodesp")
        return redirect(url_for('prodesp.criar_csv_prodesp_page'))
    current_app.logger.info(f"prodesp - Requisição de download para: {filename!r}")
    full_path = safe_join(CSV_DIR, filename)
    current_app.logger.info(f"prodesp - Procurando em: {full_path!r}")
    if full_path is None or not os.path.isfile(full_path):
        current_app.logger.error(f"prodesp - Arquivo não encontrado no disco: {full_path}")
        portal_flash("Arquivo não encontrado.", 'danger', scope="prodesp")
        return redirect(url_for('prodesp.criar_csv_prodesp_page'))
    return send_from_directory(CSV_DIR, filename, as_attachment=True, mimetype="text/csv")

@prodesp_bp.route('/csv_manager')
@login_required
def csv_manager():
    if not _prodesp_pode_ver_menu_gestao(current_user):
        portal_flash("Esta área não está disponível para o perfil Implantação.", "warning", scope="prodesp")
        return redirect(url_for("prodesp.atendimentos"))
    return render_template(
        'csv_prodesp.html',
        prodesp_contratadas_permitidas=CONTRATADAS_PERMITIDAS,
    )

def _prodesp_carregar_dados_dashboard_periodo(start_date, end_date, conn=None):
    """
    Mesma base de dados do dashboard de gestão (atendimentos + somente agendados),
    com enriquecimento de agenda e tempos. Retorna (atendimentos_data, scheduled_data, cursor, conn).
    O caller deve fechar cursor/conn quando passar conn=None.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    from prodesp.prodesp.dashboard_select import (
        UNIDADE_DASHBOARD_SELECT,
        atendimento_null_base,
        sql_atendimento_cols,
    )

    att_null_base = atendimento_null_base()

    range_start, range_end_excl = _prodesp_sql_date_range(start_date, end_date)
    from prodesp.prodesp.substatus_materializado import COLUMN as _SUB_DESDE_COL
    from prodesp.prodesp.substatus_materializado import read_enabled as _sub_desde_read
    from prodesp.prodesp.tempo_snapshot import tempo_source_table as _tempo_src

    _tempo_join = _tempo_src()
    _a_cols = sql_atendimento_cols("a")
    _u_cols = UNIDADE_DASHBOARD_SELECT

    if _sub_desde_read():
        query_atendimentos_no_periodo = f"""
    SELECT
        {_a_cols},
        {_u_cols},
        COALESCE(a.data_atendimentos, u.data_agendamento_unidades) AS data_evento,
        a.`{_SUB_DESDE_COL}` AS ultimo_substatus_log,
        v.tempo_total_geral AS tempo_total_geral
    FROM unidades u
    INNER JOIN atendimentos a ON a.id_unidades_atendimentos = u.id_unidades
    LEFT JOIN {_tempo_join} v ON v.id_atendimentos = a.id_atendimentos
    WHERE a.data_atendimentos >= %s AND a.data_atendimentos < %s
    """
    else:
        cte_agg = _prodesp_sql_cte_ultimo_substatus_log_agg()
        query_atendimentos_no_periodo = f"""
    WITH {cte_agg}
    SELECT
        {_a_cols},
        {_u_cols},
        COALESCE(a.data_atendimentos, u.data_agendamento_unidades) AS data_evento,
        usa.ultimo_ts AS ultimo_substatus_log,
        v.tempo_total_geral AS tempo_total_geral
    FROM unidades u
    INNER JOIN atendimentos a ON a.id_unidades_atendimentos = u.id_unidades
    LEFT JOIN {_tempo_join} v ON v.id_atendimentos = a.id_atendimentos
    LEFT JOIN ult_sub_log_agg usa ON usa.id_atend = a.id_atendimentos
        AND usa.sub_nome = TRIM(a.substatus_atendimentos)
    WHERE a.data_atendimentos >= %s AND a.data_atendimentos < %s
    """

    query_somente_agendado = f"""
    SELECT
        {_u_cols},
        u.data_agendamento_unidades AS data_evento,
        CAST(NULL AS DATETIME) AS ultimo_substatus_log
    FROM unidades u
    WHERE u.data_agendamento_unidades IS NOT NULL
      AND u.data_agendamento_unidades >= %s AND u.data_agendamento_unidades < %s
      AND NOT EXISTS (
          SELECT 1
          FROM atendimentos a2
          WHERE a2.id_unidades_atendimentos = u.id_unidades
            AND a2.data_atendimentos >= u.data_agendamento_unidades
      )
    """

    cursor.execute(query_atendimentos_no_periodo, (range_start, range_end_excl))
    rows_com_atendimento = cursor.fetchall()
    cursor.execute(query_somente_agendado, (range_start, range_end_excl))
    rows_so_agenda = cursor.fetchall()

    atendimentos_data = list(rows_com_atendimento)
    for r in rows_so_agenda:
        atendimentos_data.append({**att_null_base, **r})

    try:
        end_d = end_date if isinstance(end_date, date) else datetime.strptime(str(end_date)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        end_d = date.today()
    _prodesp_enriquecer_agendamento_historico_asof(cursor, atendimentos_data, end_d)
    for row in atendimentos_data:
        decrypt_sensitive_row_inplace(row)
    for row in atendimentos_data:
        if row.get("id_atendimentos") is None:
            row["status_atendimentos"] = "Agendado"
            row["substatus_atendimentos"] = "Sem atendimento iniciado"
            _prodesp_aplicar_planejado_em_row_agendado(row)
        row["id_atendimento"] = row.get("id_atendimentos")
        row["data_atendimento"] = row.get("data_atendimentos")
        row["horario_inicio"] = row.get("horario_inicio_atendimentos")
        row["horario_finalizacao"] = row.get("horario_finalizacao_atendimentos")
    processar_atendimentos_para_dashboard(atendimentos_data)

    tz_sp = pytz.timezone("America/Sao_Paulo")
    _status_final_dashboard = frozenset({"Agendado"}) | FINAL_STATUSES_ATENDIMENTO
    for row in atendimentos_data:
        status_row = (row.get("status_atendimentos") or "").strip()
        if status_row in _status_final_dashboard:
            continue
        if row.get("modo_duracao") != "em_andamento":
            continue
        iso_log = _prodesp_datetime_para_js_iso(
            row.get("ultimo_substatus_log"),
            tz_sp,
            record_id=row.get("id_atendimento") or row.get("id_atendimentos"),
        )
        if iso_log:
            row["data_para_js"] = iso_log

    scheduled_units_by_day = defaultdict(set)
    try:
        start_clip = (
            start_date
            if isinstance(start_date, date)
            else datetime.strptime(str(start_date)[:10], "%Y-%m-%d").date()
        ).isoformat()
        end_clip = (
            end_date
            if isinstance(end_date, date)
            else datetime.strptime(str(end_date)[:10], "%Y-%m-%d").date()
        ).isoformat()
    except (TypeError, ValueError):
        start_clip, end_clip = str(start_date)[:10], str(end_date)[:10]

    for row in atendimentos_data:
        id_u = row.get("id_unidades")
        if id_u is None:
            continue
        dag = row.get("data_agendamento_timeline") or row.get("data_agendamento")
        if dag is None:
            continue
        if isinstance(dag, datetime):
            d_str = dag.date().isoformat()
        elif isinstance(dag, date):
            d_str = dag.isoformat()
        else:
            d_str = str(dag)[:10]
        # Não expõe dias de agenda fora do filtro (evita barras cinzas em 30/07
        # quando o período selecionado é só a data de realização).
        if d_str < start_clip or d_str > end_clip:
            continue
        scheduled_units_by_day[d_str].add(id_u)
    scheduled_data = {d: len(ids) for d, ids in scheduled_units_by_day.items()}

    return atendimentos_data, scheduled_data, cursor, conn, own_conn


def _prodesp_sql_date_range(start_date, end_date):
    """Intervalo sargável: col >= start 00:00 e col < end+1 dia."""
    start_s = str(start_date)[:10]
    try:
        end_d = end_date if isinstance(end_date, date) else datetime.strptime(str(end_date)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        end_d = date.today()
    end_excl = (end_d + timedelta(days=1)).isoformat()
    return start_s, end_excl


def _prodesp_dashboard_cache_bust():
    """Invalida cache do dashboard após mutação (outros usuários veem dados novos na próxima carga)."""
    try:
        from prodesp.prodesp.dashboard_cache import bust

        bust()
    except Exception:
        pass


def _prodesp_mutations_cache_bust(*atendimento_ids):
    """Invalida caches PRODESP após mutação (dashboard + lista atendimentos).

    IDs opcionais alimentam o dirty log do delta. Se omitidos, tenta extrair
    ``id_atendimento`` da rota/JSON; sem ID → bump opaco (delta faz full reload).
    """
    _prodesp_dashboard_cache_bust()
    try:
        from prodesp.prodesp.atendimentos_list_cache import bust as list_bust

        list_bust()
    except Exception:
        pass
    ids = []
    for raw in atendimento_ids:
        if raw is None or raw == "":
            continue
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    try:
        from flask import has_request_context, request

        if has_request_context():
            va = request.view_args or {}
            for key in ("id_atendimento", "id_atendimentos"):
                if va.get(key) is not None:
                    try:
                        ids.append(int(va[key]))
                    except (TypeError, ValueError):
                        pass
            if request.is_json:
                body = request.get_json(silent=True) or {}
                for key in ("id_atendimento", "id_atendimentos", "attendanceId"):
                    if body.get(key) is not None:
                        try:
                            ids.append(int(body[key]))
                        except (TypeError, ValueError):
                            pass
    except Exception:
        pass
    # dedupe
    seen = set()
    clean = []
    for n in ids:
        if n <= 0 or n in seen:
            continue
        seen.add(n)
        clean.append(n)
    try:
        from prodesp.prodesp.data_revision import bump

        if clean:
            bump(atendimento_ids=clean)
        else:
            bump()
    except Exception:
        pass


def _prodesp_tempo_snapshot_refresh(cursor, id_atendimento) -> None:
    """Dual-write P0-02: atualiza snapshot de tempos (no-op se flag OFF)."""
    try:
        from prodesp.prodesp.tempo_snapshot import refresh_one, write_enabled

        if write_enabled():
            refresh_one(cursor, id_atendimento)
    except Exception:
        pass


def _prodesp_sanitize_dashboard_rows(atendimentos_data):
    for atendimento in atendimentos_data:
        for key, value in list(atendimento.items()):
            if value is None:
                if key in ['tempo_em_segundos', 'id_atendimento', 'id_unidade', 'id_unidades']:
                    continue
                atendimento[key] = ""
            elif key == 'hora_agendamento':
                _prodesp_format_row_hora_agendamento(atendimento, key)
            elif isinstance(value, timedelta):
                atendimento[key] = str(value)
            elif isinstance(value, (datetime, date)):
                atendimento[key] = value.isoformat()
            elif hasattr(value, '__str__') and not isinstance(value, (int, float, str, bool)):
                atendimento[key] = str(value)


def _prodesp_dashboard_tempos_etapa(start_date, end_date, user, cursor=None):
    """KPIs de tempo por etapa — só para quem tem permissão; dados podem vir do cache compartilhado."""
    if not _prodesp_pode_ver_kpis_tempo_executivo(user):
        return None
    own_conn = False
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        own_conn = True
    try:
        return _prodesp_build_tempos_etapa_kpis_dashboard(cursor, start_date, end_date)
    finally:
        if own_conn:
            cursor.close()
            conn.close()


def _prodesp_tempos_etapa_from_cache_or_compute(cached_tempos, start_date, end_date, user, cursor=None):
    """Entrega tempos do blob compartilhado; se ausente, computa (usuário autorizado)."""
    if not _prodesp_pode_ver_kpis_tempo_executivo(user):
        return None
    if cached_tempos is not None:
        return cached_tempos
    return _prodesp_dashboard_tempos_etapa(start_date, end_date, user, cursor=cursor)


def _prodesp_build_dashboard_payload(start_date, end_date, user):
    from prodesp.prodesp.dashboard_cache import get as cache_get, set as cache_set

    cached = cache_get(start_date, end_date)
    tz_sp = pytz.timezone("America/Sao_Paulo")
    if cached is not None:
        atendimentos_cached = [dict(r) for r in (cached.get("atendimentos") or [])]
        for row in atendimentos_cached:
            _prodesp_anexar_flags_edicao_dashboard(user, row)
        return {
            "atendimentos": atendimentos_cached,
            "scheduled": cached["scheduled"],
            "motivos_fora_padrao": cached["motivos_fora_padrao"],
            "tempos_etapa": _prodesp_tempos_etapa_from_cache_or_compute(
                cached.get("tempos_etapa"), start_date, end_date, user
            ),
            "server_time": datetime.now(tz_sp).isoformat(),
            "cache_meta": cached.get("cache_meta"),
        }

    atendimentos_data, scheduled_data, cursor, conn, own_conn = _prodesp_carregar_dados_dashboard_periodo(
        start_date, end_date
    )
    query_motivos_fora_padrao = """
        SELECT
            m.categoria,
            m.descricao,
            COUNT(*) AS total
        FROM atendimentos_fora_padrao af
        JOIN motivos_fora_padrao m ON af.id_motivo = m.id
        JOIN atendimentos a ON af.id_atendimento = a.id_atendimentos
        WHERE a.data_atendimentos >= %s AND a.data_atendimentos < %s
        GROUP BY m.categoria, m.descricao
        ORDER BY total DESC, m.categoria, m.descricao
    """
    motivos_start, motivos_end_excl = _prodesp_sql_date_range(start_date, end_date)
    cursor.execute(query_motivos_fora_padrao, (motivos_start, motivos_end_excl))
    motivos_fora_padrao = cursor.fetchall()
    _prodesp_sanitize_dashboard_rows(atendimentos_data)
    for row in atendimentos_data:
        _prodesp_anexar_flags_edicao_dashboard(user, row)
    # Sempre calcula e guarda no blob compartilhado (filtrado na entrega por permissão).
    tempos_etapa = _prodesp_build_tempos_etapa_kpis_dashboard(cursor, start_date, end_date)
    cursor.close()
    if own_conn:
        conn.close()

    core = {
        "atendimentos": atendimentos_data,
        "scheduled": scheduled_data,
        "motivos_fora_padrao": motivos_fora_padrao,
        "tempos_etapa": tempos_etapa,
    }
    cache_set(start_date, end_date, core)
    return {
        **core,
        "tempos_etapa": tempos_etapa if _prodesp_pode_ver_kpis_tempo_executivo(user) else None,
        "server_time": datetime.now(tz_sp).isoformat(),
        "cache_meta": {"from_cache": False, "ttl_sec": 0, "age_sec": 0},
    }


@prodesp_bp.route('/api/dashboard_data', methods=['GET'])
@login_required
@with_server_ms
def api_dashboard_data():
    if not _prodesp_pode_acessar_dashboard_gestao(current_user):
        return jsonify(message="Acesso negado ao dashboard de gestão.", success=False), 403
    start_date = request.args.get('start_date', datetime.now().date().isoformat())
    end_date = request.args.get('end_date', datetime.now().date().isoformat())
    from prodesp.prodesp.data_revision import attach_to_payload

    payload = _prodesp_build_dashboard_payload(start_date, end_date, current_user)
    return jsonify(
        attach_to_payload(
            {
                "atendimentos": payload["atendimentos"],
                "scheduled": payload["scheduled"],
                "motivos_fora_padrao": payload["motivos_fora_padrao"],
                "tempos_etapa": payload.get("tempos_etapa"),
                "server_time": payload["server_time"],
                "cache_meta": payload.get("cache_meta"),
            }
        )
    )


def _prodesp_build_dashboard_kpis_payload(start_date, end_date, user):
    """
    KPIs/cards sem repetir a query pesada quando o cache do período já está quente.
    Cache miss: uma carga completa (popula cache para dashboard_data + próximos kpis).
    """
    from dataclasses import asdict

    from prodesp.prodesp.dashboard_cache import get as cache_get
    from prodesp.prodesp.gestao.gestao_relatorio_email import calcular_kpis_gestao

    tz_sp = pytz.timezone("America/Sao_Paulo")
    cached = cache_get(start_date, end_date)
    if cached is not None:
        rows = cached.get("atendimentos") or []
        return {
            "total": len(rows),
            "resumo": asdict(calcular_kpis_gestao(rows)),
            "scheduled": cached.get("scheduled") or {},
            "motivos_fora_padrao": cached.get("motivos_fora_padrao") or [],
            "tempos_etapa": _prodesp_tempos_etapa_from_cache_or_compute(
                cached.get("tempos_etapa"), start_date, end_date, user
            ),
            "server_time": datetime.now(tz_sp).isoformat(),
            "cache_meta": cached.get("cache_meta"),
        }

    payload = _prodesp_build_dashboard_payload(start_date, end_date, user)
    rows = payload.get("atendimentos") or []
    return {
        "total": len(rows),
        "resumo": asdict(calcular_kpis_gestao(rows)),
        "scheduled": payload.get("scheduled") or {},
        "motivos_fora_padrao": payload.get("motivos_fora_padrao") or [],
        "tempos_etapa": payload.get("tempos_etapa"),
        "server_time": payload["server_time"],
        "cache_meta": payload.get("cache_meta"),
    }


@prodesp_bp.route('/api/dashboard_kpis', methods=['GET'])
@login_required
@with_server_ms
def api_dashboard_kpis():
    """Resumo leve (cards/KPIs) — em cache hit não reexecuta query de atendimentos."""
    if not _prodesp_pode_acessar_dashboard_gestao(current_user):
        return jsonify(message="Acesso negado ao dashboard de gestão.", success=False), 403
    start_date = request.args.get('start_date', datetime.now().date().isoformat())
    end_date = request.args.get('end_date', datetime.now().date().isoformat())
    payload = _prodesp_build_dashboard_kpis_payload(start_date, end_date, current_user)
    return jsonify(
        total=payload["total"],
        resumo=payload["resumo"],
        scheduled=payload["scheduled"],
        motivos_fora_padrao=payload["motivos_fora_padrao"],
        tempos_etapa=payload.get("tempos_etapa"),
        server_time=payload["server_time"],
        cache_meta=payload.get("cache_meta"),
    )

@prodesp_bp.route('/api/motivos_fora_padrao', methods=['GET'])
@login_required
def api_motivos_fora_padrao():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id, categoria, descricao
            FROM motivos_fora_padrao
            ORDER BY categoria, descricao
            """
        )
        return jsonify(cursor.fetchall())
    finally:
        cursor.close()
        conn.close()

@prodesp_bp.route('/api/atendimento/<int:id_atendimento>/motivos', methods=['GET'])
@login_required
def api_atendimento_motivos_fora_padrao(id_atendimento):
    denied = _prodesp_resposta_leitura_concluido(id_atendimento, current_user)
    if denied:
        return denied
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id_motivo FROM atendimentos_fora_padrao WHERE id_atendimento = %s ORDER BY id_motivo",
            (id_atendimento,)
        )
        return jsonify([row[0] for row in cursor.fetchall()])
    finally:
        cursor.close()
        conn.close()

@prodesp_bp.route("/atendimentos/<int:id_atendimento>")
@login_required
def detalhes_atendimento(id_atendimento):
    denied = _prodesp_resposta_leitura_concluido(id_atendimento, current_user)
    if denied:
        return denied
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT
              a.id_atendimentos, 
              a.data_atendimentos AS data_atendimento_raw, 
              a.id_unidades_atendimentos,
              a.status_atendimentos AS status_atendimento, 
              a.substatus_atendimentos AS substatus_atendimento,
              a.analista_atuante_atendimentos AS analista_atuante,
              a.analista_configuracao_atendimentos AS analista_configuracao,
              a.analista_mpls_atendimentos AS analista_mpls_atendimentos,
              a.analista_caderno_teste_atendimentos AS analista_caderno_teste,
              a.contratada_atendimentos AS contratada, 
              a.field_atendimentos AS field_responsavel,
              a.contato_field_atendimentos AS contato_field, 
              a.logs_atendimentos AS logs_atendimento,
              u.id_vgr_unidades AS id_vgr,
              u.acronimo_unidades AS acronimo, 
              u.nome_unidades AS nome,
              u.hostname_unidades AS hostname,
              u.id_intragov_unidades AS id_intragov,
            u.ip_lan_01_unidades AS ip_lan_01,
            u.mv_ip_lan_sec_unidades AS mv_ip_lan_sec,
            u.ip_lan_transito_unidades AS ip_lan_transito,
              u.data_agendamento_unidades AS data_agendamento,
              u.hora_agendamento_unidades AS hora_agendamento,
              u.endereco_unidades AS endereco,
              u.numero_unidades AS numero,
              u.complemento_unidades AS complemento,
              u.bairro_unidades AS bairro, 
              u.municipio_unidades AS municipio,
              u.estado_unidades AS estado, 
              u.cep_unidades AS cep,
              u.latitude_unidades AS latitude, 
              u.longitude_unidades AS longitude,
              u.telefone_contato_unidades AS telefone_contato,
              u.loopback_vivo_unidades AS loopback_vivo, 
              u.loopback_cliente_unidades AS loopback_cliente,
              u.loopback_on_bgp_unidades AS loopback_on_bgp,
              u.ticket_noc_unidades AS ticket_noc,
              """ + unidades_mv_opcionais_sql_select("u") + ",\n" + unidades_lan_extra_sql_select("u") + """
            FROM atendimentos a
            JOIN unidades u ON a.id_unidades_atendimentos = u.id_unidades
            WHERE a.id_atendimentos = %s LIMIT 1
        """
        cursor.execute(query, (id_atendimento,))
        row = cursor.fetchone()
        if not row:
            return jsonify(error="Atendimento não encontrado"), 404

        for key, value in row.items():
            if value is None:
                continue
            if key == 'hora_agendamento':
                _prodesp_format_row_hora_agendamento(row, key)
            elif isinstance(value, timedelta):
                row[key] = str(value)
            elif hasattr(value, '__str__') and not isinstance(value, (int, float, str, bool)):
                row[key] = str(value) # Garante que Decimal (Latitude/Longitude) seja enviado sem perdas

        dt_obj = parse_date_string(row.get('data_atendimento_raw'), current_app.logger, id_atendimento)
        row['data_atendimento'] = dt_obj.strftime('%Y-%m-%d %H:%M:%S') if dt_obj else None

        sub_disp = (row.get('substatus_atendimento') or '').strip()
        if sub_disp:
            row['substatus_atendimento'] = normalizar_substatus_fluxo(sub_disp)

        if isinstance(row.get('data_agendamento'), (date, datetime)):
            row['data_agendamento'] = row['data_agendamento'].strftime('%Y-%m-%d')

        row['observacoes'] = _prodesp_listar_observacoes_atendimento_e_unidade(
            cursor, id_atendimento, row['id_unidades_atendimentos']
        )

        row['equipamentos'] = _prodesp_listar_equipamentos_unidade(
            cursor, row['id_unidades_atendimentos']
        )
        row['links'] = _prodesp_listar_links_unidade(cursor, row['id_unidades_atendimentos'])

        decrypt_sensitive_row_inplace(row)

        cursor.execute(
            """
            SELECT m.categoria, m.descricao
            FROM atendimentos_fora_padrao af
            JOIN motivos_fora_padrao m ON af.id_motivo = m.id
            WHERE af.id_atendimento = %s
            ORDER BY m.categoria, m.descricao
            """,
            (id_atendimento,)
        )
        row['motivos_fora_padrao'] = cursor.fetchall()

        _prodesp_anexar_flags_edicao(current_user, row)

        include_raw = (request.args.get("include") or "").strip().lower()
        include_parts = {p.strip() for p in include_raw.split(",") if p.strip()}
        if "historico" in include_parts:
            payload_hist = _prodesp_admin_auditoria_payload(cursor, id_atendimento)
            if payload_hist:
                row["historico_atendimento"] = payload_hist.get("historico_atendimento")
                row["historico_auditoria"] = {
                    "admin_user": current_user.admin_user,
                    "dados": payload_hist.get("historico_atendimento"),
                    **payload_hist,
                }
        if "marcos" in include_parts:
            try:
                row["marcos_atividade"] = _prodesp_build_marcos_atividade(cursor, id_atendimento)
            except Exception as marcos_err:
                current_app.logger.warning(
                    "prodesp - marcos_atividade id=%s: %s",
                    id_atendimento,
                    marcos_err,
                )
                row["marcos_atividade"] = []

        return jsonify(row)
    except Exception as e:
        return _prodesp_json_error(
            e,
            log=current_app.logger,
            action="detalhes atendimento",
            entity_id=id_atendimento,
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/atendimentos/<int:id_atendimento>/substatus_baseline")
@login_required
def substatus_baseline(id_atendimento):
    """
    Retorna o último substatus (em ordem cronológica) diferente dos substatus «aguarda externo».
    Usado para manter a progressão do fluxo quando o substatus atual é Aguardando Cliente / Aguarda Contratada / Aguarda Licença.
    """
    denied = _prodesp_resposta_leitura_concluido(id_atendimento, current_user)
    if denied:
        return denied
    externos = tuple(SUBSTATUS_AGUARDA_EXTERNO)
    placeholders = ", ".join(["%s"] * len(externos))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT valor_novo_log
            FROM atendimentos_status_log
            WHERE id_atendimentos_log = %s
              AND tipo_campo_log = 'substatus'
              AND valor_novo_log IS NOT NULL
              AND TRIM(valor_novo_log) <> ''
              AND TRIM(valor_novo_log) NOT IN ({placeholders})
            ORDER BY alterado_em_log DESC
            LIMIT 1
            """,
            (id_atendimento, *externos),
        )
        row = cursor.fetchone() or {}
        return jsonify(success=True, baseline=(row.get("valor_novo_log") or "").strip())
    except Exception as e:
        return _prodesp_json_error(
            e,
            log=current_app.logger,
            action="substatus baseline",
            entity_id=id_atendimento,
            baseline="",
        )
    finally:
        cursor.close()
        conn.close()

def _prodesp_marco_aguarda_gestao_merged(rows, log, tz_sp):
    """Marco único «Aguarda Gestão» — soma intervalos legados em «Triagem»."""
    gestao_nomes = (SUBSTATUS_AGUARDA_GESTAO, SUBSTATUS_LEGACY_TRIAGEM)
    duracao = None
    seg = sum(
        duracao_acumulada_substatus_segundos(rows, nome, tz_sp) for nome in gestao_nomes
    )
    if seg and seg > 0:
        duracao = float(seg)

    all_entries = []
    for nome in gestao_nomes:
        all_entries.extend(log.get(nome, []))

    inicio = fim = None
    if all_entries:
        inicio_raw = min(all_entries)
        inicio = _prodesp_coerce_dt_sp(inicio_raw, tz_sp)
        last_entry = max(all_entries)
        proximo = next(
            (r["alterado_em_log"] for r in rows if r["alterado_em_log"] > last_entry),
            None,
        )
        fim = _prodesp_coerce_dt_sp(proximo, tz_sp)

    return inicio, fim, duracao


def _prodesp_build_marcos_from_log_rows(rows, tz_sp=None):
    """Monta marcos da atividade a partir do log cronológico de substatus."""
    tz_sp = tz_sp or pytz.timezone("America/Sao_Paulo")
    marcos_fixos = [
        SUBSTATUS_AGUARDA_GESTAO,
        SUBSTATUS_COM_SUPORTE,
        "Aguardando Cliente",
        "Em Configuração Remota",
        "Em Configuração do MPLS",
        "Em Caderno de Teste",
        "Concluído",
    ]
    log = defaultdict(list)
    for row in rows:
        nome = (row.get("valor_novo_log") or "").strip()
        if nome:
            log[nome].append(row["alterado_em_log"])
    result = []
    for marco in marcos_fixos:
        inicio = None
        fim = None
        duracao = None
        if marco == "Aguardando Cliente":
            seg = duracao_acumulada_substatus_segundos(rows, marco, tz_sp)
            if seg and seg > 0:
                duracao = float(seg)
            if log.get("Aguardando Cliente"):
                inicio_raw = max(log["Aguardando Cliente"])
                inicio = _prodesp_coerce_dt_sp(inicio_raw, tz_sp)
                proximo = next(
                    (r["alterado_em_log"] for r in rows if r["alterado_em_log"] > inicio_raw),
                    None,
                )
                fim = _prodesp_coerce_dt_sp(proximo, tz_sp)
        elif marco == SUBSTATUS_AGUARDA_GESTAO:
            inicio, fim, duracao = _prodesp_marco_aguarda_gestao_merged(rows, log, tz_sp)
        elif marco in log and log[marco]:
            inicio = _prodesp_coerce_dt_sp(max(log[marco]), tz_sp)
            proximo_inicio = next(
                (r["alterado_em_log"] for r in rows if r["alterado_em_log"] > max(log[marco])),
                None,
            )
            fim = _prodesp_coerce_dt_sp(proximo_inicio, tz_sp)
            if inicio and fim:
                duracao = (fim - inicio).total_seconds()
        result.append(
            {
                "marco": marco,
                "inicio": inicio.isoformat() if inicio else None,
                "fim": fim.isoformat() if fim else None,
                "duracao": duracao,
            }
        )
    return result


def _prodesp_build_marcos_atividade(cursor, id_atendimento):
    tz_sp = pytz.timezone("America/Sao_Paulo")
    cursor.execute(
        """
        SELECT valor_novo_log AS valor_novo_log, alterado_em_log AS alterado_em_log
        FROM atendimentos_status_log
        WHERE id_atendimentos_log = %s
          AND tipo_campo_log = 'substatus'
        ORDER BY alterado_em_log ASC
        """,
        (id_atendimento,),
    )
    rows = cursor.fetchall()
    return _prodesp_build_marcos_from_log_rows(rows, tz_sp)


@prodesp_bp.route("/marcos_atividade/<int:id>")
@login_required
def marcos_atividade(id):
    denied = _prodesp_resposta_leitura_concluido(id, current_user)
    if denied:
        return denied
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        return jsonify(_prodesp_build_marcos_atividade(cursor, id))
    finally:
        cursor.close()
        conn.close()

@prodesp_bp.route("/historico_atendimentos/<int:id>")
@login_required
def historico_atendimento(id):
    denied = _prodesp_resposta_leitura_concluido(id, current_user)
    if denied:
        return denied
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        payload = _prodesp_admin_auditoria_payload(cursor, id)
        if payload is None:
            return jsonify({"error": "Atendimento não encontrado"}), 404

        historico_data = payload["historico_atendimento"]
        return jsonify(
            {
                "admin_user": current_user.admin_user,
                "dados": historico_data,
                **payload,
            }
        )
    except Error as e:
        current_app.logger.exception("prodesp - historico_atendimento id=%s", id)
        return jsonify({"error": "Não foi possível carregar o histórico."}), 500
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/historico_unidade/<int:id_unidade>")
@login_required
def historico_unidade(id_unidade):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        historico_unidade_rows = _prodesp_fetch_historico_registro(
            cursor, "unidades", id_unidade
        )
        cursor.execute(
            """
            SELECT id_equipamentos FROM equipamentos
            WHERE id_unidades_equipamentos = %s
            """,
            (id_unidade,),
        )
        eq_ids = [r["id_equipamentos"] for r in cursor.fetchall()]
        cursor.execute(
            "SELECT id_link FROM links WHERE id_unidades_links = %s",
            (id_unidade,),
        )
        link_ids = [r["id_link"] for r in cursor.fetchall()]
        return jsonify(
            {
                "admin_user": current_user.admin_user,
                "historico_unidade": historico_unidade_rows,
                "historico_equipamentos": _prodesp_fetch_historico_ids_in(
                    cursor, "equipamentos", eq_ids
                ),
                "historico_links": _prodesp_fetch_historico_ids_in(
                    cursor, "links", link_ids
                ),
            }
        )
    except Error as e:
        return _prodesp_json_error(
            e, log=current_app.logger, action="historico unidade", entity_id=id_unidade
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/atendimento/<int:id_atendimento>/auditoria", methods=["GET"])
@login_required
def api_admin_atendimento_auditoria(id_atendimento):
    err = _prodesp_require_admin_api()
    if err:
        return err
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        payload = _prodesp_admin_auditoria_payload(cursor, id_atendimento)
        if payload is None:
            return jsonify(success=False, message="Atendimento não encontrado."), 404
        return jsonify(success=True, **payload)
    except Exception as e:
        return _prodesp_json_error(e, log=current_app.logger, action="auditoria admin")
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/atendimento/<int:id_atendimento>/status_log", methods=["POST"])
@login_required
def api_admin_status_log_create(id_atendimento):
    err = _prodesp_require_admin_api()
    if err:
        return err
    payload = request.get_json() or {}
    tipo = (payload.get("tipo_campo_log") or "").strip()
    if tipo not in ("status", "substatus"):
        return jsonify(success=False, message="tipo_campo_log deve ser status ou substatus."), 400
    try:
        alt = _prodesp_parse_admin_datetime(payload.get("alterado_em_log")) or datetime.now(
            pytz.timezone("America/Sao_Paulo")
        ).replace(tzinfo=None)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO atendimentos_status_log
            (id_atendimentos_log, tipo_campo_log, valor_anterior_log, valor_novo_log, alterado_em_log)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                id_atendimento,
                tipo,
                (payload.get("valor_anterior_log") or "")[:50] or None,
                (payload.get("valor_novo_log") or "")[:50] or None,
                alt,
            ),
        )
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, id=cursor.lastrowid), 201
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(e, log=current_app.logger, action="admin status_log create")
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route(
    "/api/admin/atendimento/<int:id_atendimento>/status_log/<int:log_id>",
    methods=["PUT", "DELETE"],
)
@login_required
def api_admin_status_log_item(id_atendimento, log_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id_atendimentos_log FROM atendimentos_status_log WHERE id_log_atendimentos_status = %s",
            (log_id,),
        )
        row = cursor.fetchone()
        if not row or int(row["id_atendimentos_log"]) != id_atendimento:
            return jsonify(success=False, message="Registro não encontrado."), 404

        if request.method == "DELETE":
            cur2 = conn.cursor()
            try:
                cur2.execute(
                    "DELETE FROM atendimentos_status_log WHERE id_log_atendimentos_status = %s",
                    (log_id,),
                )
                conn.commit()
                _prodesp_mutations_cache_bust()
            finally:
                cur2.close()
            return jsonify(success=True)

        payload = request.get_json() or {}
        updates = []
        params = []
        if "tipo_campo_log" in payload:
            t = (payload.get("tipo_campo_log") or "").strip()
            if t not in ("status", "substatus"):
                return jsonify(success=False, message="tipo_campo_log inválido."), 400
            updates.append("tipo_campo_log = %s")
            params.append(t)
        if "valor_anterior_log" in payload:
            updates.append("valor_anterior_log = %s")
            v = payload.get("valor_anterior_log")
            params.append((str(v)[:50] if v is not None else None) or None)
        if "valor_novo_log" in payload:
            updates.append("valor_novo_log = %s")
            v = payload.get("valor_novo_log")
            params.append((str(v)[:50] if v is not None else None) or None)
        if "alterado_em_log" in payload:
            try:
                alt = _prodesp_parse_admin_datetime(payload.get("alterado_em_log"))
            except ValueError as e:
                return jsonify(success=False, message=str(e)), 400
            if alt is None:
                return jsonify(success=False, message="alterado_em_log obrigatório."), 400
            updates.append("alterado_em_log = %s")
            params.append(alt)
        if not updates:
            return jsonify(success=False, message="Nenhum campo para atualizar."), 400
        params.append(log_id)
        cur2 = conn.cursor()
        try:
            cur2.execute(
                f"UPDATE atendimentos_status_log SET {', '.join(updates)} WHERE id_log_atendimentos_status = %s",
                params,
            )
            conn.commit()
            _prodesp_mutations_cache_bust()
        finally:
            cur2.close()
        return jsonify(success=True)
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin status_log item", entity_id=log_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/atendimento/<int:id_atendimento>/historico", methods=["POST"])
@login_required
def api_admin_historico_create(id_atendimento):
    err = _prodesp_require_admin_api()
    if err:
        return err
    payload = request.get_json() or {}
    re_u = (payload.get("usuario_re_historico") or "")[:8] or None
    nome_u = (payload.get("usuario_nome_historico") or "")[:100] or None
    campo = (payload.get("campo_alterado_historico") or "")[:255] or None
    op = (payload.get("operacao_historico") or "UPDATE").strip().upper()
    if op not in ("INSERT", "UPDATE", "DELETE"):
        return jsonify(success=False, message="operacao_historico inválida."), 400
    try:
        dth = _prodesp_parse_admin_datetime(payload.get("data_alteracao_historico")) or datetime.now(
            pytz.timezone("America/Sao_Paulo")
        ).replace(tzinfo=None)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO historico
            (usuario_re_historico, usuario_nome_historico, tabela_afetada_historico,
             id_registro_afetado_historico, campo_alterado_historico,
             valor_antigo_historico, valor_novo_historico, operacao_historico, data_alteracao_historico)
            VALUES (%s, %s, 'atendimentos', %s, %s, %s, %s, %s, %s)
            """,
            (
                re_u,
                nome_u,
                id_atendimento,
                campo,
                payload.get("valor_antigo_historico"),
                payload.get("valor_novo_historico"),
                op,
                dth,
            ),
        )
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, id=cursor.lastrowid), 201
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(e, log=current_app.logger, action="admin historico create")
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route(
    "/api/admin/atendimento/<int:id_atendimento>/historico/<int:hid>",
    methods=["PUT", "DELETE"],
)
@login_required
def api_admin_historico_item(id_atendimento, hid):
    err = _prodesp_require_admin_api()
    if err:
        return err
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id_log_historico, tabela_afetada_historico, id_registro_afetado_historico
            FROM historico WHERE id_log_historico = %s
            """,
            (hid,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Registro não encontrado."), 404
        if row["tabela_afetada_historico"] != "atendimentos" or int(
            row["id_registro_afetado_historico"]
        ) != id_atendimento:
            return jsonify(success=False, message="Registro não pertence a este atendimento."), 403

        if request.method == "DELETE":
            cur2 = conn.cursor()
            try:
                cur2.execute("DELETE FROM historico WHERE id_log_historico = %s", (hid,))
                conn.commit()
                _prodesp_mutations_cache_bust()
            finally:
                cur2.close()
            return jsonify(success=True)

        payload = request.get_json() or {}
        updates = []
        params = []
        flds = {
            "usuario_re_historico": ("usuario_re_historico", 8),
            "usuario_nome_historico": ("usuario_nome_historico", 100),
            "campo_alterado_historico": ("campo_alterado_historico", 255),
            "valor_antigo_historico": ("valor_antigo_historico", None),
            "valor_novo_historico": ("valor_novo_historico", None),
            "operacao_historico": ("operacao_historico", None),
            "data_alteracao_historico": ("data_alteracao_historico", None),
        }
        for key, (col, mx) in flds.items():
            if key not in payload:
                continue
            if key == "data_alteracao_historico":
                try:
                    v = _prodesp_parse_admin_datetime(payload.get(key))
                except ValueError as e:
                    return jsonify(success=False, message=str(e)), 400
                if v is None:
                    return jsonify(success=False, message="data_alteracao_historico inválida."), 400
                updates.append(f"{col} = %s")
                params.append(v)
                continue
            if key == "operacao_historico":
                op = (payload.get(key) or "").strip().upper()
                if op not in ("INSERT", "UPDATE", "DELETE"):
                    return jsonify(success=False, message="operacao_historico inválida."), 400
                updates.append(f"{col} = %s")
                params.append(op)
                continue
            val = payload.get(key)
            if mx and val is not None:
                val = str(val)[:mx]
            updates.append(f"{col} = %s")
            params.append(val)
        if not updates:
            return jsonify(success=False, message="Nenhum campo para atualizar."), 400
        params.append(hid)
        cur2 = conn.cursor()
        try:
            cur2.execute(
                f"UPDATE historico SET {', '.join(updates)} WHERE id_log_historico = %s",
                params,
            )
            conn.commit()
            _prodesp_mutations_cache_bust()
        finally:
            cur2.close()
        return jsonify(success=True)
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin historico item", entity_id=hid
        )
    finally:
        cursor.close()
        conn.close()


def _prodesp_admin_historico_apply_put(payload, updates, params):
    flds = {
        "usuario_re_historico": ("usuario_re_historico", 8),
        "usuario_nome_historico": ("usuario_nome_historico", 100),
        "campo_alterado_historico": ("campo_alterado_historico", 255),
        "valor_antigo_historico": ("valor_antigo_historico", None),
        "valor_novo_historico": ("valor_novo_historico", None),
        "operacao_historico": ("operacao_historico", None),
        "data_alteracao_historico": ("data_alteracao_historico", None),
    }
    for key, (col, mx) in flds.items():
        if key not in payload:
            continue
        if key == "data_alteracao_historico":
            try:
                v = _prodesp_parse_admin_datetime(payload.get(key))
            except ValueError as e:
                return None, jsonify(success=False, message=str(e)), 400
            if v is None:
                return None, jsonify(success=False, message="data_alteracao_historico inválida."), 400
            updates.append(f"{col} = %s")
            params.append(v)
            continue
        if key == "operacao_historico":
            op = (payload.get(key) or "").strip().upper()
            if op not in ("INSERT", "UPDATE", "DELETE"):
                return None, jsonify(success=False, message="operacao_historico inválida."), 400
            updates.append(f"{col} = %s")
            params.append(op)
            continue
        val = payload.get(key)
        if mx and val is not None:
            val = str(val)[:mx]
        updates.append(f"{col} = %s")
        params.append(val)
    return True, None, None


@prodesp_bp.route("/api/admin/unidade/<int:id_unidade>/historico", methods=["POST"])
@login_required
def api_admin_unidade_historico_create(id_unidade):
    err = _prodesp_require_admin_api()
    if err:
        return err
    payload = request.get_json() or {}
    re_u = (payload.get("usuario_re_historico") or "")[:8] or None
    nome_u = (payload.get("usuario_nome_historico") or "")[:100] or None
    campo = (payload.get("campo_alterado_historico") or "")[:255] or None
    op = (payload.get("operacao_historico") or "UPDATE").strip().upper()
    if op not in ("INSERT", "UPDATE", "DELETE"):
        return jsonify(success=False, message="operacao_historico inválida."), 400
    try:
        dth = _prodesp_parse_admin_datetime(payload.get("data_alteracao_historico")) or datetime.now(
            pytz.timezone("America/Sao_Paulo")
        ).replace(tzinfo=None)
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO historico
            (usuario_re_historico, usuario_nome_historico, tabela_afetada_historico,
             id_registro_afetado_historico, campo_alterado_historico,
             valor_antigo_historico, valor_novo_historico, operacao_historico, data_alteracao_historico)
            VALUES (%s, %s, 'unidades', %s, %s, %s, %s, %s, %s)
            """,
            (
                re_u,
                nome_u,
                id_unidade,
                campo,
                payload.get("valor_antigo_historico"),
                payload.get("valor_novo_historico"),
                op,
                dth,
            ),
        )
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, id=cursor.lastrowid), 201
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin historico unidade create"
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route(
    "/api/admin/atendimento/<int:id_atendimento>/historico_unidade/<int:hid>",
    methods=["PUT", "DELETE"],
)
@login_required
def api_admin_historico_unidade_item(id_atendimento, hid):
    err = _prodesp_require_admin_api()
    if err:
        return err
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        id_unidade = _prodesp_atendimento_id_unidade(cursor, id_atendimento)
        if id_unidade is None:
            return jsonify(success=False, message="Atendimento não encontrado."), 404

        cursor.execute(
            """
            SELECT id_log_historico, tabela_afetada_historico, id_registro_afetado_historico
            FROM historico WHERE id_log_historico = %s
            """,
            (hid,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Registro não encontrado."), 404
        if row["tabela_afetada_historico"] != "unidades" or int(
            row["id_registro_afetado_historico"]
        ) != int(id_unidade):
            return jsonify(success=False, message="Registro não pertence à unidade deste atendimento."), 403

        if request.method == "DELETE":
            cur2 = conn.cursor()
            try:
                cur2.execute("DELETE FROM historico WHERE id_log_historico = %s", (hid,))
                conn.commit()
                _prodesp_mutations_cache_bust()
            finally:
                cur2.close()
            return jsonify(success=True)

        payload = request.get_json() or {}
        updates, params = [], []
        ok, resp, code = _prodesp_admin_historico_apply_put(payload, updates, params)
        if not ok:
            return resp, code
        if not updates:
            return jsonify(success=False, message="Nenhum campo para atualizar."), 400
        params.append(hid)
        cur2 = conn.cursor()
        try:
            cur2.execute(
                f"UPDATE historico SET {', '.join(updates)} WHERE id_log_historico = %s",
                params,
            )
            conn.commit()
            _prodesp_mutations_cache_bust()
        finally:
            cur2.close()
        return jsonify(success=True)
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e,
            log=current_app.logger,
            action="admin historico unidade item",
            entity_id=hid,
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route(
    "/api/admin/atendimento/<int:id_atendimento>/observacoes/<int:obs_id>",
    methods=["PUT", "DELETE"],
)
@login_required
def api_admin_observacao_item(id_atendimento, obs_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        id_unidade = _prodesp_atendimento_id_unidade(cursor, id_atendimento)
        if id_unidade is None:
            return jsonify(success=False, message="Atendimento não encontrado."), 404

        cursor.execute(
            """
            SELECT id_observacoes, id_unidades_observacoes, id_atendimentos_observacoes, observacoes
            FROM observacoes WHERE id_observacoes = %s
            """,
            (obs_id,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Observação não encontrada."), 404
        if int(row["id_unidades_observacoes"]) != int(id_unidade):
            return jsonify(success=False, message="Observação não pertence a esta unidade/atendimento."), 403
        id_att = row.get("id_atendimentos_observacoes")
        if id_att is not None and int(id_att) != int(id_atendimento):
            return jsonify(success=False, message="Observação não pertence a este atendimento."), 403

        if request.method == "DELETE":
            texto = row.get("observacoes")
            cur2 = conn.cursor()
            try:
                cur2.execute("DELETE FROM observacoes WHERE id_observacoes = %s", (obs_id,))
                if id_att:
                    registrar_log(
                        conn,
                        "atendimentos",
                        id_atendimento,
                        "Observação",
                        texto,
                        None,
                        "DELETE",
                    )
                else:
                    registrar_log(
                        conn,
                        "unidades",
                        id_unidade,
                        "Observação",
                        texto,
                        None,
                        "DELETE",
                    )
                conn.commit()
                _prodesp_mutations_cache_bust()
            finally:
                cur2.close()
            return jsonify(success=True)

        payload = request.get_json() or {}
        if payload.get("desassociar_atendimento"):
            cur2 = conn.cursor()
            try:
                cur2.execute(
                    """
                    UPDATE observacoes
                    SET id_atendimentos_observacoes = NULL
                    WHERE id_observacoes = %s AND id_atendimentos_observacoes = %s
                    """,
                    (obs_id, id_atendimento),
                )
                conn.commit()
                _prodesp_mutations_cache_bust()
            finally:
                cur2.close()
            return jsonify(success=True, message="Observação desassociada do atendimento (permanece na unidade).")

        updates, params = [], []
        if "texto" in payload or "observacoes" in payload:
            texto = payload.get("texto", payload.get("observacoes"))
            obs_err = validate_observacao_text(texto)
            if obs_err:
                return jsonify(success=False, message=obs_err), 400
            updates.append("observacoes = %s")
            params.append(texto)
        if "timestamp" in payload or "timestamp_observacoes" in payload:
            raw_ts = payload.get("timestamp", payload.get("timestamp_observacoes"))
            try:
                ts = _prodesp_parse_admin_datetime(raw_ts)
            except ValueError as e:
                return jsonify(success=False, message=str(e)), 400
            if ts is None:
                return jsonify(success=False, message="timestamp inválido."), 400
            updates.append("timestamp_observacoes = %s")
            params.append(ts)
        if not updates:
            return jsonify(success=False, message="Nenhum campo para atualizar."), 400
        params.append(obs_id)
        cur2 = conn.cursor()
        try:
            cur2.execute(
                f"UPDATE observacoes SET {', '.join(updates)} WHERE id_observacoes = %s",
                params,
            )
            conn.commit()
            _prodesp_mutations_cache_bust()
        finally:
            cur2.close()
        return jsonify(success=True)
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin observacao item", entity_id=obs_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route(
    "/api/admin/atendimento/<int:id_atendimento>/equipamentos/<int:eq_id>",
    methods=["PUT", "DELETE"],
)
@login_required
def api_admin_equipamento_item(id_atendimento, eq_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        id_unidade = _prodesp_atendimento_id_unidade(cursor, id_atendimento)
        if id_unidade is None:
            return jsonify(success=False, message="Atendimento não encontrado."), 404

        cursor.execute(
            """
            SELECT id_equipamentos, modelo_equipamentos, serial_equipamentos,
                   versao_equipamentos, descricao_equipamentos, id_unidades_equipamentos
            FROM equipamentos WHERE id_equipamentos = %s
            """,
            (eq_id,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Equipamento não encontrado."), 404
        if int(row["id_unidades_equipamentos"]) != int(id_unidade):
            return jsonify(success=False, message="Equipamento não pertence à unidade deste atendimento."), 403

        payload = request.get_json() or {}

        if request.method == "DELETE" or payload.get("desassociar"):
            info = f"{row.get('modelo_equipamentos')} - {row.get('serial_equipamentos')}"
            cur2 = conn.cursor()
            try:
                if payload.get("desassociar"):
                    try:
                        cur2.execute(
                            "UPDATE equipamentos SET id_unidades_equipamentos = NULL WHERE id_equipamentos = %s",
                            (eq_id,),
                        )
                    except Error:
                        conn.rollback()
                        return jsonify(
                            success=False,
                            message="Não foi possível desassociar (use Excluir para remover o registro).",
                        ), 400
                    registrar_log(
                        conn,
                        "atendimentos",
                        id_atendimento,
                        "Equipamento",
                        info,
                        "Desassociado da unidade",
                        "UPDATE",
                    )
                else:
                    cur2.execute("DELETE FROM equipamentos WHERE id_equipamentos = %s", (eq_id,))
                    registrar_log(
                        conn,
                        "atendimentos",
                        id_atendimento,
                        "Equipamento",
                        info,
                        None,
                        "DELETE",
                    )
                conn.commit()
                _prodesp_mutations_cache_bust()
            finally:
                cur2.close()
            return jsonify(success=True)

        eq_payload = {
            "modelo": payload.get("modelo", row.get("modelo_equipamentos")),
            "serial": payload.get("serial", row.get("serial_equipamentos")),
            "versao": payload.get("versao", row.get("versao_equipamentos")),
            "descricao": payload.get("descricao", row.get("descricao_equipamentos")),
        }
        len_err = validate_equipamento_fields(eq_payload)
        if len_err:
            return jsonify(success=False, message=len_err), 400

        cur2 = conn.cursor()
        try:
            cur2.execute(
                """
                UPDATE equipamentos SET
                    modelo_equipamentos = %s, serial_equipamentos = %s,
                    versao_equipamentos = %s, descricao_equipamentos = %s
                WHERE id_equipamentos = %s
                """,
                (
                    eq_payload["modelo"].strip(),
                    eq_payload["serial"].strip().upper(),
                    eq_payload.get("versao", "").strip(),
                    eq_payload.get("descricao", "").strip(),
                    eq_id,
                ),
            )
            registrar_log(
                conn,
                "atendimentos",
                id_atendimento,
                "Equipamento",
                None,
                f"Equipamento {eq_payload['serial']} atualizado (admin)",
                "UPDATE",
            )
            conn.commit()
            _prodesp_mutations_cache_bust()
        finally:
            cur2.close()
        return jsonify(success=True)
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin equipamento item", entity_id=eq_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route(
    "/api/admin/atendimento/<int:id_atendimento>/links/<int:link_id>",
    methods=["PUT", "DELETE"],
)
@login_required
def api_admin_link_item(id_atendimento, link_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        id_unidade = _prodesp_atendimento_id_unidade(cursor, id_atendimento)
        if id_unidade is None:
            return jsonify(success=False, message="Atendimento não encontrado."), 404

        cursor.execute(
            """
            SELECT id_link, designador_links, tipo_links, operadora_links, vlan_links,
                   ip_wan_links, ip_gateway_links, ip_mascara_links, velocidade_links,
                   pppoe_user_links, pppoe_pass_links, id_vgr_links, id_unidades_links
            FROM links WHERE id_link = %s
            """,
            (link_id,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Link não encontrado."), 404
        decrypt_sensitive_row_inplace(row)
        if int(row["id_unidades_links"]) != int(id_unidade):
            return jsonify(success=False, message="Link não pertence à unidade deste atendimento."), 403

        payload = request.get_json() or {}

        if request.method == "DELETE" or payload.get("desassociar"):
            info = f"{row.get('tipo_links')} - {row.get('designador_links')}"
            cur2 = conn.cursor()
            try:
                if payload.get("desassociar"):
                    try:
                        cur2.execute(
                            "UPDATE links SET id_unidades_links = NULL WHERE id_link = %s",
                            (link_id,),
                        )
                    except Error:
                        conn.rollback()
                        return jsonify(
                            success=False,
                            message="Não foi possível desassociar (use Excluir para remover o registro).",
                        ), 400
                    registrar_log(
                        conn,
                        "atendimentos",
                        id_atendimento,
                        "Link",
                        info,
                        "Desassociado da unidade",
                        "UPDATE",
                    )
                else:
                    cur2.execute("DELETE FROM links WHERE id_link = %s", (link_id,))
                    registrar_log(
                        conn,
                        "atendimentos",
                        id_atendimento,
                        "Link",
                        info,
                        None,
                        "DELETE",
                    )
                conn.commit()
                _prodesp_mutations_cache_bust()
            finally:
                cur2.close()
            return jsonify(success=True)

        lnk_payload = normalize_link_api_payload({
            "designador": payload.get("designador", row.get("designador_links")),
            "tipo": payload.get("tipo", row.get("tipo_links")),
            "operadora": payload.get("operadora", row.get("operadora_links")),
            "vlan": payload.get("vlan", row.get("vlan_links")),
            "ip_wan": payload.get("ip_wan", row.get("ip_wan_links")),
            "redundante_critico": payload.get("redundante_critico", row.get("redundante_critico_links")),
            "ip_gateway": payload.get("ip_gateway", row.get("ip_gateway_links")),
            "ip_mascara": payload.get("ip_mascara", row.get("ip_mascara_links")),
            "velocidade": payload.get("velocidade", row.get("velocidade_links")),
            "pppoe_user": payload.get("pppoe_user", row.get("pppoe_user_links")),
            "pppoe_pass": payload.get("pppoe_pass", row.get("pppoe_pass_links")),
            "id_vgr": payload.get("id_vgr", row.get("id_vgr_links")),
        }, row)
        len_err = validate_link_fields(lnk_payload)
        if len_err:
            return jsonify(success=False, message=len_err), 400
        uniq_errs = find_link_uniqueness_errors(
            cursor,
            lnk_payload,
            exclude_link_id=link_id,
            id_unidade=row.get("id_unidades_links"),
        )
        if uniq_errs:
            return jsonify(success=False, message=uniq_errs[0]), 400

        cur2 = conn.cursor()
        try:
            cur2.execute(
                """
                UPDATE links SET
                    id_vgr_links = %s, designador_links = %s, tipo_links = %s,
                    operadora_links = %s, vlan_links = %s, ip_wan_links = %s,
                    redundante_critico_links = %s,
                    ip_gateway_links = %s, ip_mascara_links = %s, velocidade_links = %s,
                    pppoe_user_links = %s, pppoe_pass_links = %s
                WHERE id_link = %s
                """,
                (
                    lnk_payload.get("id_vgr"),
                    lnk_payload["designador"].strip(),
                    lnk_payload.get("tipo"),
                    lnk_payload.get("operadora"),
                    lnk_payload.get("vlan"),
                    lnk_payload.get("ip_wan"),
                    lnk_payload.get("redundante_critico_links", 0),
                    lnk_payload.get("ip_gateway"),
                    lnk_payload.get("ip_mascara"),
                    lnk_payload.get("velocidade"),
                    encrypt_sensitive_db_column("pppoe_user_links", lnk_payload.get("pppoe_user")),
                    encrypt_sensitive_db_column("pppoe_pass_links", lnk_payload.get("pppoe_pass")),
                    link_id,
                ),
            )
            registrar_log(
                conn,
                "atendimentos",
                id_atendimento,
                "Link",
                None,
                f"Link {lnk_payload['designador']} atualizado (admin)",
                "UPDATE",
            )
            conn.commit()
            _prodesp_mutations_cache_bust()
        finally:
            cur2.close()
        return jsonify(success=True)
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin link item", entity_id=link_id
        )
    finally:
        cursor.close()
        conn.close()


def _prodesp_require_admin_page():
    if int(getattr(current_user, "admin_user", 0) or 0) != 1:
        portal_flash(
            "Acesso restrito a administradores.",
            "danger",
            scope="prodesp",
        )
        return redirect(url_for("prodesp.atendimentos"))
    return None


@prodesp_bp.route("/admin/equipamentos")
@login_required
def admin_equipamentos_page():
    denied = _prodesp_require_admin_page()
    if denied:
        return denied
    return render_template(
        "admin_equipamentos_prodesp.html",
        admin_user=int(getattr(current_user, "admin_user", 0) or 0),
        prodesp_serial_model_rules=SERIAL_MODEL_FRAGMENTS_ORDERED,
    )


@prodesp_bp.route("/admin/links")
@login_required
def admin_links_page():
    denied = _prodesp_require_admin_page()
    if denied:
        return denied
    return render_template(
        "admin_links_prodesp.html",
        admin_user=int(getattr(current_user, "admin_user", 0) or 0),
        prodesp_serial_model_rules=SERIAL_MODEL_FRAGMENTS_ORDERED,
    )


def _prodesp_admin_user_label():
    for attr in ("re_user", "re", "email_user", "email", "nome_user", "name"):
        v = getattr(current_user, attr, None)
        if v:
            return str(v)[:120]
    return str(getattr(current_user, "id", "") or "admin")[:120]


@prodesp_bp.route("/admin/blueprint_secretarias")
@login_required
def admin_blueprint_secretarias_page():
    denied = _prodesp_require_admin_page()
    if denied:
        return denied
    catalog_ok = True
    try:
        from prodesp.prodesp.blueprint import blueprint_secretaria_repo as bsr

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            catalog_ok = bsr.table_exists(cur)
        finally:
            cur.close()
            conn.close()
    except Exception:
        catalog_ok = False
    return render_template(
        "admin_blueprint_secretarias_prodesp.html",
        admin_user=int(getattr(current_user, "admin_user", 0) or 0),
        catalog_table_ok=catalog_ok,
    )


@prodesp_bp.route("/api/admin/blueprint_secretarias", methods=["GET", "POST"])
@login_required
def api_admin_blueprint_secretarias():
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp.blueprint import blueprint_secretaria_repo as bsr

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if not bsr.table_exists(cursor):
            return (
                jsonify(
                    success=False,
                    message=(
                        "Tabela de catálogo ausente. Aplique "
                        "prodesp/sql/021_blueprint_secretaria_catalog.sql."
                    ),
                ),
                503,
            )
        if request.method == "GET":
            return jsonify(bsr.list_for_datatable(cursor))
        payload = request.get_json() or {}
        new_id, msg = bsr.create_secretaria(
            cursor,
            payload,
            updated_by=_prodesp_admin_user_label(),
            conn=conn,
        )
        if msg:
            conn.rollback()
            return jsonify(success=False, message=msg), 400
        conn.commit()
        return jsonify(success=True, id=new_id, message="Secretaria criada.")
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin blueprint secretarias"
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route(
    "/api/admin/blueprint_secretarias/<int:sec_id>", methods=["GET", "PUT", "DELETE"]
)
@login_required
def api_admin_blueprint_secretaria_item(sec_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp.blueprint import blueprint_secretaria_repo as bsr
    from prodesp.prodesp.blueprint.blueprint_catalog import rule_to_public_dict

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if not bsr.table_exists(cursor):
            return (
                jsonify(
                    success=False,
                    message=(
                        "Tabela de catálogo ausente. Aplique "
                        "prodesp/sql/021_blueprint_secretaria_catalog.sql."
                    ),
                ),
                503,
            )
        if request.method == "GET":
            rule = bsr.get_rule_by_id(cursor, sec_id)
            if not rule:
                return jsonify(success=False, message="Secretaria não encontrada."), 404
            return jsonify(success=True, data=rule_to_public_dict(rule))
        if request.method == "PUT":
            payload = request.get_json() or {}
            ok, msg = bsr.update_secretaria(
                cursor,
                sec_id,
                payload,
                updated_by=_prodesp_admin_user_label(),
                conn=conn,
            )
            if not ok:
                conn.rollback()
                return jsonify(success=False, message=msg or "Falha ao atualizar."), 400
            conn.commit()
            return jsonify(success=True, message="Secretaria atualizada.")
        payload = request.get_json(silent=True) or {}
        hard = str(payload.get("hard") or request.args.get("hard") or "").lower() in (
            "1",
            "true",
            "yes",
        )
        if hard:
            ok, msg = bsr.delete_hard(cursor, sec_id, conn=conn)
        else:
            ok, msg = bsr.soft_deactivate(
                cursor,
                sec_id,
                updated_by=_prodesp_admin_user_label(),
                conn=conn,
            )
        if not ok:
            conn.rollback()
            return jsonify(success=False, message=msg or "Falha ao remover."), 400
        conn.commit()
        return jsonify(
            success=True,
            message="Secretaria excluída." if hard else "Secretaria inativada.",
        )
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e,
            log=current_app.logger,
            action="admin blueprint secretaria item",
            entity_id=sec_id,
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route(
    "/api/admin/blueprint_secretarias/<int:sec_id>/historico", methods=["GET"]
)
@login_required
def api_admin_blueprint_secretaria_historico(sec_id):
    """Trilha de auditoria do catálogo (somente leitura)."""
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp.blueprint import blueprint_secretaria_repo as bsr

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if not bsr.table_exists(cursor):
            return (
                jsonify(
                    success=False,
                    message=(
                        "Tabela de catálogo ausente. Aplique "
                        "prodesp/sql/021_blueprint_secretaria_catalog.sql."
                    ),
                ),
                503,
            )
        rule = bsr.get_rule_by_id(cursor, sec_id)
        acronimo = rule.acronimo if rule else None
        rows = _prodesp_fetch_historico_registro(
            cursor, "prodesp_blueprint_secretaria", int(sec_id)
        )
        return jsonify(
            success=True,
            data=rows,
            id=int(sec_id),
            acronimo=acronimo,
            found=bool(rule),
        )
    except Exception as e:
        return _prodesp_json_error(
            e,
            log=current_app.logger,
            action="admin blueprint secretaria historico",
            entity_id=sec_id,
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/unidades/search")
@login_required
def api_admin_unidades_search():
    """Typeahead de unidades (admin): id_vgr, acrônimo, hostname, nome."""
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    q = (request.args.get("q") or "").strip()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        rows = inv.search_unidades(cursor, q, limit=request.args.get("limit") or 20)
        return jsonify(success=True, data=rows)
    except Exception as e:
        return _prodesp_json_error(e, log=current_app.logger, action="admin unidades search")
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/unidades/contexto")
@login_required
def api_admin_unidades_contexto():
    """Preview de unidade + atendimentos + ativos (admin), por id_vgr exato."""
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    id_vgr = (request.args.get("id_vgr") or "").strip()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        payload, msg = inv.contexto_unidade_by_vgr(cursor, id_vgr)
        if msg:
            return jsonify(success=False, message=msg), 404
        return jsonify(payload)
    except Exception as e:
        return _prodesp_json_error(e, log=current_app.logger, action="admin unidades contexto")
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/equipamentos", methods=["GET", "POST"])
@login_required
def api_admin_equipamentos():
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == "GET":
            return jsonify(inv.list_equipamentos_datatable(cursor, request.args))
        payload = request.get_json() or {}
        new_id, changes, msg = inv.create_equipamento(cursor, payload)
        if msg:
            conn.rollback()
            return jsonify(success=False, message=msg), 400
        inv.registrar_field_changes(conn, "equipamentos", new_id, changes, operacao="INSERT")
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, id=new_id, message="Equipamento criado.")
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(e, log=current_app.logger, action="admin equipamentos")
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/equipamentos/<int:eq_id>/contexto")
@login_required
def api_admin_equipamento_contexto(eq_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        payload, msg = inv.contexto_equipamento(cursor, eq_id)
        if msg:
            return jsonify(success=False, message=msg), 404
        return jsonify(payload)
    except Exception as e:
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin equipamento contexto", entity_id=eq_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/equipamentos/<int:eq_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_admin_equipamento(eq_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == "GET":
            cursor.execute(
                """
                SELECT e.id_equipamentos AS id, e.id_unidades_equipamentos AS id_unidade,
                       e.modelo_equipamentos AS modelo, e.serial_equipamentos AS serial,
                       e.mac_equipamentos AS mac, e.licenca_equipamentos AS licenca,
                       e.versao_equipamentos AS versao, e.descricao_equipamentos AS descricao,
                       u.id_vgr_unidades AS id_vgr, u.hostname_unidades AS hostname
                FROM equipamentos e
                LEFT JOIN unidades u ON u.id_unidades = e.id_unidades_equipamentos
                WHERE e.id_equipamentos = %s
                """,
                (eq_id,),
            )
            row = cursor.fetchone()
            if not row:
                return jsonify(success=False, message="Equipamento não encontrado."), 404
            data = {k: ("" if v is None else v) for k, v in dict(row).items()}
            return jsonify(success=True, data=data)

        if request.method == "DELETE":
            changes, msg = inv.delete_equipamento(cursor, eq_id)
            if msg:
                conn.rollback()
                return jsonify(success=False, message=msg), 404
            inv.registrar_field_changes(
                conn, "equipamentos", eq_id, changes, operacao="DELETE"
            )
            conn.commit()
            _prodesp_mutations_cache_bust()
            return jsonify(success=True, message="Equipamento excluído.")

        payload = request.get_json() or {}
        changes, msg = inv.update_equipamento(cursor, eq_id, payload)
        if msg:
            conn.rollback()
            code = 404 if "não encontrado" in msg.lower() else 400
            return jsonify(success=False, message=msg), code
        inv.registrar_field_changes(
            conn, "equipamentos", eq_id, changes, operacao="UPDATE"
        )
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, message="Equipamento atualizado.")
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin equipamento", entity_id=eq_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/equipamentos/<int:eq_id>/transferir", methods=["POST"])
@login_required
def api_admin_equipamento_transferir(eq_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        changes, msg = inv.transfer_equipamento(cursor, eq_id, request.get_json() or {})
        if msg:
            conn.rollback()
            if inv.is_unidade_conflito_msg(msg):
                code = 409
            elif "não encontrado" in msg.lower():
                code = 404
            else:
                code = 400
            return jsonify(success=False, message=msg), code
        inv.registrar_field_changes(
            conn, "equipamentos", eq_id, changes, operacao="UPDATE"
        )
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, message="Equipamento transferido.")
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin equipamento transferir", entity_id=eq_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/equipamentos/<int:eq_id>/desassociar", methods=["POST"])
@login_required
def api_admin_equipamento_desassociar(eq_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        changes, msg = inv.desassociar_equipamento(cursor, eq_id, request.get_json() or {})
        if msg:
            conn.rollback()
            code = 409 if inv.is_unidade_conflito_msg(msg) else 404
            return jsonify(success=False, message=msg), code
        inv.registrar_field_changes(
            conn, "equipamentos", eq_id, changes, operacao="UPDATE"
        )
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, message="Equipamento desassociado.")
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin equipamento desassociar", entity_id=eq_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/ultimo_atendimento_map", methods=["GET"])
@login_required
def api_admin_ultimo_atendimento_map():
    """Enrich da página visível (máx. 100 unidades) — admin inventário."""
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        return jsonify(inv.ultimo_atendimento_map_payload(cursor, request.args.get("ids")))
    except Exception as e:
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin ultimo atendimento map"
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/links", methods=["GET", "POST"])
@login_required
def api_admin_links():
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == "GET":
            return jsonify(inv.list_links_datatable(cursor, request.args))
        payload = request.get_json() or {}
        new_id, changes, msg = inv.create_link(cursor, payload)
        if msg:
            conn.rollback()
            return jsonify(success=False, message=msg), 400
        inv.registrar_field_changes(conn, "links", new_id, changes, operacao="INSERT")
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, id=new_id, message="Link criado.")
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(e, log=current_app.logger, action="admin links")
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/links/<int:link_id>/contexto")
@login_required
def api_admin_link_contexto(link_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        payload, msg = inv.contexto_link(cursor, link_id)
        if msg:
            return jsonify(success=False, message=msg), 404
        return jsonify(payload)
    except Exception as e:
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin link contexto", entity_id=link_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/links/<int:link_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_admin_link(link_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv
    from prodesp.prodesp.sensitive_fields_crypto import decrypt_sensitive_row_inplace

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == "GET":
            cursor.execute(
                """
                SELECT l.id_link AS id, l.id_unidades_links AS id_unidade,
                       l.tipo_links AS tipo, l.operadora_links AS operadora,
                       l.designador_links AS designador, l.id_vgr_links AS id_vgr_link,
                       l.ip_wan_links AS ip_wan, l.ip_gateway_links AS ip_gateway,
                       l.ip_mascara_links AS ip_mascara, l.vlan_links AS vlan,
                       l.velocidade_links AS velocidade,
                       l.redundante_critico_links AS redundante_critico,
                       l.pppoe_user_links, l.pppoe_pass_links,
                       u.id_vgr_unidades AS id_vgr, u.hostname_unidades AS hostname
                FROM links l
                LEFT JOIN unidades u ON u.id_unidades = l.id_unidades_links
                WHERE l.id_link = %s
                """,
                (link_id,),
            )
            row = cursor.fetchone()
            if not row:
                return jsonify(success=False, message="Link não encontrado."), 404
            data = dict(row)
            try:
                decrypt_sensitive_row_inplace(data)
            except Exception:
                current_app.logger.warning(
                    "admin link decrypt falhou id=%s", link_id, exc_info=True
                )
            pass_set = bool(data.get("pppoe_pass_links"))
            data["pppoe_user"] = data.get("pppoe_user_links") or ""
            data["pppoe_pass"] = ""
            data["pppoe_pass_set"] = pass_set
            data.pop("pppoe_user_links", None)
            data.pop("pppoe_pass_links", None)
            data = {k: ("" if v is None else v) for k, v in data.items()}
            return jsonify(success=True, data=data)

        if request.method == "DELETE":
            changes, msg = inv.delete_link(cursor, link_id)
            if msg:
                conn.rollback()
                return jsonify(success=False, message=msg), 404
            inv.registrar_field_changes(
                conn, "links", link_id, changes, operacao="DELETE"
            )
            conn.commit()
            _prodesp_mutations_cache_bust()
            return jsonify(success=True, message="Link excluído.")

        payload = request.get_json() or {}
        changes, msg = inv.update_link(cursor, link_id, payload)
        if msg:
            conn.rollback()
            code = 404 if "não encontrado" in msg.lower() else 400
            return jsonify(success=False, message=msg), code
        inv.registrar_field_changes(conn, "links", link_id, changes, operacao="UPDATE")
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, message="Link atualizado.")
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin link", entity_id=link_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/links/<int:link_id>/transferir", methods=["POST"])
@login_required
def api_admin_link_transferir(link_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        changes, msg = inv.transfer_link(cursor, link_id, request.get_json() or {})
        if msg:
            conn.rollback()
            if inv.is_unidade_conflito_msg(msg):
                code = 409
            elif "não encontrado" in msg.lower():
                code = 404
            else:
                code = 400
            return jsonify(success=False, message=msg), code
        inv.registrar_field_changes(conn, "links", link_id, changes, operacao="UPDATE")
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, message="Link transferido.")
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin link transferir", entity_id=link_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/links/<int:link_id>/desassociar", methods=["POST"])
@login_required
def api_admin_link_desassociar(link_id):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp import admin_inventory as inv

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        changes, msg = inv.desassociar_link(cursor, link_id, request.get_json() or {})
        if msg:
            conn.rollback()
            code = 409 if inv.is_unidade_conflito_msg(msg) else 404
            return jsonify(success=False, message=msg), code
        inv.registrar_field_changes(conn, "links", link_id, changes, operacao="UPDATE")
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(success=True, message="Link desassociado.")
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="admin link desassociar", entity_id=link_id
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/admin/atendimento/<int:id_atendimento>", methods=["DELETE"])
@login_required
def api_admin_atendimento_delete(id_atendimento):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp.admin_atendimento_ops import (
        AdminAtendimentoOpsError,
        admin_excluir_atendimento,
    )

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        result = admin_excluir_atendimento(conn, cursor, id_atendimento)
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(
            success=True,
            message="Atendimento excluído com sucesso.",
            **result,
        )
    except AdminAtendimentoOpsError as e:
        conn.rollback()
        return jsonify(success=False, message=e.message), e.status
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e,
            log=current_app.logger,
            action="admin excluir atendimento",
            entity_id=id_atendimento,
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route(
    "/api/admin/unidade/vgr/<path:id_vgr>/agendamento",
    methods=["DELETE"],
)
@login_required
def api_admin_unidade_agendamento_delete_vgr(id_vgr):
    err = _prodesp_require_admin_api()
    if err:
        return err
    from prodesp.prodesp.admin_atendimento_ops import (
        AdminAtendimentoOpsError,
        admin_remover_agendamento,
    )

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        result = admin_remover_agendamento(conn, cursor, id_vgr=id_vgr)
        conn.commit()
        _prodesp_mutations_cache_bust()
        return jsonify(
            success=True,
            message="Agendamento removido com sucesso.",
            **result,
        )
    except AdminAtendimentoOpsError as e:
        conn.rollback()
        return jsonify(success=False, message=e.message), e.status
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e,
            log=current_app.logger,
            action="admin remover agendamento",
            entity_id=id_vgr,
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/status_log/<int:id>")
@login_required
def status_log(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT status, changed_at FROM incidente_status_log WHERE incidente_id = %s ORDER BY changed_at ASC", (id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)

@prodesp_bp.route('/atendimentos/update', methods=['POST'])
@login_required
def update_atendimento():
    data = request.get_json() or {}
    id_ = data.get('id')
    updates = data.get('updates') or []
    restart_timer = data.get('restart_timer', False)
    motivos_fora_padrao = data.get('motivos_fora_padrao', None)

    if not id_ or (not isinstance(updates, list) and not restart_timer):
        return jsonify(message="Dados inválidos", success=False), 400

    tz_sp = pytz.timezone('America/Sao_Paulo')
    now_sp = datetime.now(tz_sp)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        allowed = {
            'data_atuacao': ('atendimentos', 'data_atendimentos'),
            'status': ('atendimentos', 'status_atendimentos'), 
            'substatus': ('atendimentos', 'substatus_atendimentos'),
            'analista_atuante': ('atendimentos', 'analista_atuante_atendimentos'),
            'analista_configuracao': ('atendimentos', 'analista_configuracao_atendimentos'),
            'analista_mpls_atendimentos': ('atendimentos', 'analista_mpls_atendimentos'),
            'analista_caderno_teste': ('atendimentos', 'analista_caderno_teste_atendimentos'),
            'contratada': ('atendimentos', 'contratada_atendimentos'), 
            'field': ('atendimentos', 'field_atendimentos'),
            'contato_field': ('atendimentos', 'contato_field_atendimentos'), 
            'logs': ('atendimentos', 'logs_atendimentos'),
            'nome': ('unidades', 'nome_unidades'),
            'acronimo': ('unidades', 'acronimo_unidades'),
            'data_agendamento': ('unidades', 'data_agendamento_unidades'),
            'hora_agendamento': ('unidades', 'hora_agendamento_unidades'),
            'hostname': ('unidades', 'hostname_unidades'),
            'endereco': ('unidades', 'endereco_unidades'),
            'numero': ('unidades', 'numero_unidades'),
            'bairro': ('unidades', 'bairro_unidades'),
            'municipio': ('unidades', 'municipio_unidades'),
            'estado': ('unidades', 'estado_unidades'),
            'complemento': ('unidades', 'complemento_unidades'),
            'cep': ('unidades', 'cep_unidades'),
            'latitude': ('unidades', 'latitude_unidades'),
            'longitude': ('unidades', 'longitude_unidades'),
            'telefone_contato': ('unidades', 'telefone_contato_unidades'),
            'ip_lan_01': ('unidades', 'ip_lan_01_unidades'),
            'ip_lan_transito': ('unidades', 'ip_lan_transito_unidades'),
            'id_intragov': ('unidades', 'id_intragov_unidades'),
            'loopback_vivo': ('unidades', 'loopback_vivo_unidades'),
            'loopback_cliente': ('unidades', 'loopback_cliente_unidades'),
            'loopback_on_bgp': ('unidades', 'loopback_on_bgp_unidades'),
            'ticket_noc': ('unidades', 'ticket_noc_unidades'),
        }
        allowed.update(
            (js, ("unidades", db)) for js, db in unidades_mv_opcionais_js_to_db().items()
        )
        allowed.update(
            (js, ("unidades", db)) for js, db in unidades_lan_extra_js_to_db().items()
        )

        conn.start_transaction()
        cursor.execute(
            sql_select_atendimento_by_id(include_logs=True, for_update=True),
            (id_,),
        )
        old_atendimento = cursor.fetchone()
        if not old_atendimento:
            return _prodesp_reject_update(conn, id_, "Atendimento não encontrado.", http=404)

        id_unidade = old_atendimento.get('id_unidades_atendimentos')
        cursor.execute(sql_select_unidades_by_id(), (id_unidade,))
        old_unidade = cursor.fetchone() or {}

        atendimento_updates, unidade_updates = {}, {}

        if restart_timer:
            now = datetime.now(tz_sp)
            atendimento_updates['horario_inicio_atendimentos'] = now.time()
            atendimento_updates['horario_finalizacao_atendimentos'] = None
            atendimento_updates['status_atendimentos'] = 'Em Atendimento'
            atendimento_updates['analista_atuante_atendimentos'] = current_user.nome_user
        else:
            for u in updates:
                js_field, novo = u.get('coluna'), u.get('valor')
                if js_field not in allowed:
                    continue
                len_err = validate_update_field(js_field, novo)
                if len_err:
                    return _prodesp_reject_update(conn, id_, len_err)
                table, db_col = allowed[js_field]

                # Tratamento para campos numéricos/data que não aceitam string vazia
                if db_col in ['latitude_unidades', 'longitude_unidades', 'data_agendamento_unidades', 'hora_agendamento_unidades']:
                    if novo == '':
                        novo = None

                # Estado (UF): validar 2 letras — não truncar silenciosamente
                if db_col == 'estado_unidades' and novo:
                    uf_err = validate_estado_unidade(novo)
                    if uf_err:
                        return _prodesp_reject_update(conn, id_, uf_err)
                    novo = normalize_estado_unidade(novo)

                if db_col == 'substatus_atendimentos' and novo is not None:
                    s_sub = str(novo).strip()
                    if s_sub:
                        novo = normalizar_substatus_fluxo(s_sub)

                if db_col == 'logs_atendimentos' and novo is not None:
                    from prodesp.prodesp.caderno.fgt_ssh_collector import sanitize_logs_atendimento_for_db

                    novo = sanitize_logs_atendimento_for_db(str(novo))

                if table == 'atendimentos':
                    old_stored = old_atendimento.get(db_col)
                    if is_sensitive_db_column(db_col):
                        if sensitive_values_equal_for_db(db_col, novo, old_stored):
                            continue
                        atendimento_updates[db_col] = encrypt_sensitive_db_column(db_col, novo)
                    elif str(novo) != str(old_stored):
                        atendimento_updates[db_col] = novo
                elif table == 'unidades':
                    old_val = old_unidade.get(db_col)
                    if db_col == 'hora_agendamento_unidades':
                        novo = normalize_hora_agendamento_db(novo)
                        if horas_agendamento_equivalent(novo, old_val):
                            continue
                    elif db_col in ('latitude_unidades', 'longitude_unidades'):
                        if coordenadas_equivalentes(novo, old_val):
                            continue
                        coord_label = "Latitude" if db_col == "latitude_unidades" else "Longitude"
                        coord_err = validate_coordinate_for_db(novo, field_label=coord_label)
                        if coord_err:
                            return _prodesp_reject_update(conn, id_, coord_err)
                        novo = normalize_coordinate_for_db(novo)
                        if coordenadas_equivalentes(novo, old_val):
                            continue
                        unidade_updates[db_col] = novo
                        continue
                    elif db_col in UNIDADES_MV_OPCIONAIS_DB_COLUMNS or db_col in UNIDADES_LAN_EXTRA_DB_COLUMNS:
                        if novo is not None and str(novo).strip() != '':
                            if db_col in UNIDADES_CIDR_DB_COLUMNS:
                                novo = sanitize_ip_cidr_field(novo)
                            else:
                                novo = sanitize_plain_ipv4_field(novo)
                        if (novo is None or str(novo).strip() == '') and old_val not in (None, ''):
                            continue
                        if str(novo) == str(old_val):
                            continue
                        unidade_updates[db_col] = novo
                    elif db_col in UNIDADES_CIDR_DB_COLUMNS:
                        if novo is not None and str(novo).strip() != '':
                            novo = sanitize_ip_cidr_field(novo)
                        if (novo is None or str(novo).strip() == '') and old_val not in (None, ''):
                            continue
                        if str(novo) == str(old_val):
                            continue
                        unidade_updates[db_col] = novo
                    elif is_sensitive_db_column(db_col):
                        if sensitive_values_equal_for_db(db_col, novo, old_val):
                            continue
                        unidade_updates[db_col] = encrypt_sensitive_db_column(db_col, novo)
                    elif str(novo) == str(old_val):
                        continue
                    else:
                        unidade_updates[db_col] = novo

        lb_cols = (
            "loopback_vivo_unidades",
            "loopback_cliente_unidades",
            "loopback_on_bgp_unidades",
        )
        if any(c in unidade_updates for c in lb_cols):
            merged_lb = {
                c: unidade_updates.get(c, old_unidade.get(c))
                for c in lb_cols
            }
            lb_errs = find_loopback_uniqueness_errors(
                cursor,
                merged_lb,
                exclude_unidade_id=id_unidade,
            )
            if lb_errs:
                return _prodesp_reject_update(conn, id_, lb_errs[0])

        has_work = bool(atendimento_updates or unidade_updates or restart_timer or motivos_fora_padrao is not None)
        if has_work:
            permitido, msg_ed, http_ed = _prodesp_validar_edicao_atendimento(
                current_user, old_atendimento, tz_sp=tz_sp
            )
            if not permitido:
                return _prodesp_reject_update(conn, id_, msg_ed, http=http_ed)

        old_substatus_val = (old_atendimento.get('substatus_atendimentos') or '').strip()
        is_admin_editor = _prodesp_is_admin(current_user)
        is_ag_gp_editor = _prodesp_is_agendamento_ou_gp(current_user)
        privilegio_sem_concorrencia = is_admin_editor or (
            is_ag_gp_editor and is_substatus_gestao(old_substatus_val)
        )

        new_substatus_val = atendimento_updates.get('substatus_atendimentos')
        em_atendimento = (
            atendimento_updates.get('status_atendimentos', old_atendimento.get('status_atendimentos'))
            == 'Em Atendimento'
        )
        substatus_mudou = (
            'substatus_atendimentos' in atendimento_updates
            and new_substatus_val is not None
            and new_substatus_val != old_substatus_val
        )
        from prodesp.prodesp.substatus_materializado import apply_stamp_on_updates

        apply_stamp_on_updates(
            atendimento_updates,
            substatus_mudou=substatus_mudou,
            restart_timer=bool(restart_timer),
            now=datetime.now(tz_sp),
        )
        transicao_obs_explicit = data.get('transicao_observacoes') or data.get('new_observacoes')

        retorno_de_fila = (
            substatus_mudou
            and is_retorno_de_fila(old_substatus_val, new_substatus_val or "")
        )

        if em_atendimento and (restart_timer or update_envolve_substatus_ou_analista(updates)):
            conflict_msg = check_atendimento_substatus_update(
                old_atendimento,
                updates,
                current_user.nome_user,
                is_admin=is_admin_editor,
                is_agendamento_gp=is_ag_gp_editor,
            )
            if conflict_msg:
                return _prodesp_reject_update(
                    conn, id_, conflict_msg, http=409, extra={"action_type": "substatus_conflict"}
                )

        if substatus_mudou:
            field_msg = check_dados_field_triagem_para_fila_aguardando(
                old_atendimento,
                old_substatus_val,
                new_substatus_val or "",
                updates,
            )
            if field_msg:
                return _prodesp_reject_update(conn, id_, field_msg)

            if em_atendimento:
                for col, val in colunas_analista_liberar_substatus_transicao(
                    old_substatus_val,
                    new_substatus_val or "",
                ).items():
                    atendimento_updates[col] = val

            mpls_msg = check_analista_mpls_em_config_mpls(
                old_atendimento,
                old_substatus_val,
                new_substatus_val or "",
                updates,
            )
            if mpls_msg:
                return _prodesp_reject_update(conn, id_, mpls_msg)

            transicao_obs = observacoes_payload_para_validacao_transicao(
                cursor,
                id_,
                transicao_obs_explicit,
            )
            obs_msg = check_observacao_substatus_transicao(
                old_substatus_val,
                new_substatus_val or "",
                transicao_obs,
            )
            if obs_msg:
                return _prodesp_reject_update(conn, id_, obs_msg)

        new_status_val = atendimento_updates.get(
            "status_atendimentos", old_atendimento.get("status_atendimentos")
        )
        if substatus_mudou or "status_atendimentos" in atendimento_updates:
            hostname_msg = check_hostname_obrigatorio_transicao(
                old_unidade,
                old_substatus_val,
                (new_substatus_val or old_substatus_val or ""),
                unidade_updates,
                old_atendimento.get("status_atendimentos"),
                new_status_val,
                substatus_mudou=substatus_mudou,
            )
            if hostname_msg:
                return _prodesp_reject_update(conn, id_, hostname_msg)

        if (
            substatus_mudou
            and em_atendimento
            and deve_registrar_analista_agendamento_gestao(
                old_substatus_val,
                new_substatus_val or "",
                is_agendamento_gp=is_ag_gp_editor,
            )
        ):
            atendimento_updates['analista_atuante_atendimentos'] = current_user.nome_user

        if em_atendimento and substatus_mudou and not retorno_de_fila and not privilegio_sem_concorrencia:
            col_nova = analista_coluna_para_substatus(new_substatus_val or "")
            if col_nova:
                atendimento_updates[col_nova] = current_user.nome_user

        # Determinar se a atualização vem do modal de gestão ANTES de adicionar campos automáticos
        campos_modal_gestao = {
            'data_atendimentos', 'status_atendimentos', 
            'substatus_atendimentos', 'contratada_atendimentos'
        }
        is_update_from_gestao_modal = set(atendimento_updates.keys()).issubset(campos_modal_gestao)

        if 'status_atendimentos' in atendimento_updates:
            new_status = atendimento_updates['status_atendimentos']

            if new_status in FINAL_STATUSES_ATENDIMENTO:
                # Determinar quais campos obrigatórios validar baseado no contexto da atualização
                if is_update_from_gestao_modal:
                    # Para atualizações do modal de gestão, validar apenas campos presentes no modal
                    obrigatorios_final = {'contratada_atendimentos': "Contratada", 'substatus_atendimentos': "Substatus"}
                else:
                    # Para outras atualizações, validar todos os campos obrigatórios 
                    obrigatorios_final = {
                        'contratada_atendimentos': "Contratada",
                        'field_atendimentos': "Field",
                        'contato_field_atendimentos': "Contato Field",
                        'substatus_atendimentos': "Substatus"
                    }

                campos_vazios = []
                for campo, nome_campo in obrigatorios_final.items():
                    valor_novo = atendimento_updates.get(campo)
                    valor_antigo = old_atendimento.get(campo)
                    # Se o campo não está preenchido nem no novo nem no antigo, é campo vazio
                    if (valor_novo is None or valor_novo == '') and (valor_antigo is None or valor_antigo == ''):
                        campos_vazios.append(nome_campo)
                if campos_vazios:
                    return _prodesp_reject_update(
                        conn,
                        id_,
                        (
                            f"Para status '{new_status}', os campos obrigatórios não preenchidos são: "
                            f"{', '.join(campos_vazios)}. Atualização abortada."
                        ),
                    )

        status_efetivo, substatus_efetivo = _prodesp_status_substatus_efetivos(
            old_atendimento, atendimento_updates
        )
        gate_msg, gate_errs = _prodesp_gate_conclusao_concluido(
            cursor,
            status_efetivo=status_efetivo,
            substatus_efetivo=substatus_efetivo,
            old_unidade=old_unidade,
            unidade_updates=unidade_updates,
            old_atendimento=old_atendimento,
            atendimento_updates=atendimento_updates,
            id_unidade=id_unidade,
        )
        if gate_msg:
            extra = {"errors": gate_errs} if gate_errs else None
            return _prodesp_reject_update(conn, id_, gate_msg, extra=extra)

        if 'status_atendimentos' in atendimento_updates:
            new_status = atendimento_updates['status_atendimentos']
            final_statuses = list(FINAL_STATUSES_ATENDIMENTO)
            now_time = now_sp.time()

            if new_status == 'Em Atendimento' and not old_atendimento.get('horario_inicio_atendimentos'):
                atendimento_updates['horario_inicio_atendimentos'] = now_time
                current_app.logger.info(f"prodesp - LOG HORARIO: Gerando 'horario_inicio' para Atendimento ID {id_}: {now_time}")

            elif _prodesp_deve_gerar_horario_finalizacao(old_atendimento, new_status, final_statuses):
                atendimento_updates['horario_finalizacao_atendimentos'] = now_time
                current_app.logger.info(f"prodesp - LOG HORARIO: Gerando 'horario_finalizacao' para Atendimento ID {id_}: {now_time}")

        if atendimento_updates:
            if "data_atendimentos" in atendimento_updates:
                st_eff = (
                    atendimento_updates.get("status_atendimentos")
                    or old_atendimento.get("status_atendimentos")
                    or ""
                ).strip()
                if st_eff == "Em Atendimento":
                    dia_novo = _prodesp_dia_civil_atendimento(
                        atendimento_updates.get("data_atendimentos"),
                        record_id=id_,
                    )
                    if dia_novo and dia_novo > _prodesp_hoje_sp_date():
                        return _prodesp_reject_update(
                            conn,
                            id_,
                            "Data de atendimento não pode ser futura para status Em Atendimento.",
                        )

            set_clauses_list = []
            params = []
            for col, val in atendimento_updates.items():
                if val is None:
                    set_clauses_list.append(f"`{col}` = NULL")
                else:
                    set_clauses_list.append(f"`{col}` = %s")
                    params.append(val)

            if set_clauses_list:
                set_clauses = ', '.join(set_clauses_list)
                sql_query = f"UPDATE atendimentos SET {set_clauses} WHERE id_atendimentos = %s"
                params.append(id_)
                cursor.execute(sql_query, params)

                for col, novo in atendimento_updates.items(): 
                    registrar_log(conn, 'atendimentos', id_, col, old_atendimento.get(col), novo, 'UPDATE')

        if unidade_updates:
            set_clauses = ', '.join([f"`{col}` = %s" for col in unidade_updates])
            cursor.execute(f"UPDATE unidades SET {set_clauses} WHERE id_unidades = %s", (*unidade_updates.values(), id_unidade))
            for col, novo in unidade_updates.items():
                registrar_log(conn, 'unidades', id_unidade, col, old_unidade.get(col), novo, 'UPDATE')

        if motivos_fora_padrao is not None:
            salvar_motivos_fora_padrao(cursor, id_, motivos_fora_padrao)

        if (
            str(status_efetivo or '').strip() == STATUS_QUEBRA_TBRA
            and str(substatus_efetivo or '').strip() not in SUBSTATUS_QUEBRA_TBRA_VALUES
        ):
            return _prodesp_reject_update(
                conn,
                id_,
                f"Para status «{STATUS_QUEBRA_TBRA}», selecione substatus Quebra SCI ou Quebra Técnica.",
            )

        if (
            str(status_efetivo or '').strip() == 'Quebra'
            and not is_substatus_quebra_normal(substatus_efetivo)
        ):
            return _prodesp_reject_update(conn, id_, mensagem_substatus_obrigatorio_quebra())

        if (
            str(status_efetivo or '').strip() == 'Quebra'
            and str(substatus_efetivo or '').strip().startswith('Quebra')
        ):
            motivos_quebra = motivos_fora_padrao
            if motivos_quebra is None:
                cursor.execute(
                    "SELECT id_motivo FROM atendimentos_fora_padrao WHERE id_atendimento = %s",
                    (id_,),
                )
                motivos_quebra = [row[0] for row in cursor.fetchall()]
            if not motivos_quebra:
                return _prodesp_reject_update(
                    conn,
                    id_,
                    "Para status Quebra, selecione ao menos um motivo em Fora do padrão.",
                )

        observacoes_atomicas: list[dict] = []
        if substatus_mudou:
            observacoes_atomicas.extend(
                observacoes_transicao_explicitas_no_request(transicao_obs_explicit)
            )

        status_efetivo_str = str(status_efetivo or "").strip()
        quebra_obs_item = observacao_quebra_encerramento_explicita(
            data.get("observacao_quebra_encerramento")
        )
        if quebra_obs_item and status_efetivo_str in ("Quebra", STATUS_QUEBRA_TBRA):
            quebra_msg = check_observacao_quebra_encerramento(
                substatus_efetivo,
                quebra_obs_item,
            )
            if quebra_msg:
                return _prodesp_reject_update(conn, id_, quebra_msg)
            observacoes_atomicas.append(quebra_obs_item)

        observacoes_transicao_persistidas = 0
        for obs_item in observacoes_atomicas:
            len_err = validate_observacao_text(obs_item.get("observacao_prodesp"))
            if len_err:
                return _prodesp_reject_update(conn, id_, len_err)
            timestamp = parse_date_string(
                obs_item.get("data_observacao"),
                current_app.logger,
                id_,
            )
            cursor.execute(
                """
                INSERT INTO observacoes
                    (id_unidades_observacoes, observacoes, timestamp_observacoes, id_atendimentos_observacoes)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    id_unidade,
                    obs_item["observacao_prodesp"],
                    timestamp,
                    id_,
                ),
            )
            registrar_log(
                conn,
                "atendimentos",
                id_,
                "Observação",
                None,
                obs_item["observacao_prodesp"],
                "INSERT",
            )
            observacoes_transicao_persistidas += 1

        _prodesp_tempo_snapshot_refresh(cursor, id_)
        conn.commit()
        _prodesp_hook_certificado_auto_export(
            id_,
            acronimo=unidade_updates.get("acronimo_unidades") or old_unidade.get("acronimo_unidades"),
            old_status=old_atendimento.get("status_atendimentos"),
            old_substatus=old_atendimento.get("substatus_atendimentos"),
            new_status=status_efetivo,
            new_substatus=substatus_efetivo,
        )
        _prodesp_mutations_cache_bust()
        resp_payload = {
            "message": "Dados atualizados com sucesso.",
            "success": True,
        }
        if observacoes_transicao_persistidas:
            resp_payload["observacoes_transicao_persistidas"] = observacoes_transicao_persistidas
            resp_payload["observacoes"] = _prodesp_listar_observacoes_atendimento_e_unidade(
                cursor, id_, id_unidade
            )
        return jsonify(resp_payload), 200
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(e, log=current_app.logger, action="Erro ao atualizar atendimento", entity_id=id_)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@prodesp_bp.route("/api/enriquecer-endereco", methods=["POST"])
@login_required
def api_enriquecer_endereco():
    """Completa número (do logradouro), bairro, CEP e coordenadas via APIs públicas."""
    data = request.get_json(silent=True) or {}
    try:
        result = enriquecer_endereco_unidade(data)
        return jsonify(result), 200
    except Exception as e:
        return _prodesp_json_error(e, log=logging, action="enriquecer endereço", updates={})


@prodesp_bp.route('/unidades/<string:id_vgr>')
@login_required
def get_unidade_por_id_vgr(id_vgr):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id_unidades AS id_unidade, id_vgr_unidades AS id_vgr, nome_unidades AS nome, acronimo_unidades AS acronimo, "
                       "hostname_unidades AS hostname, endereco_unidades AS endereco, numero_unidades AS numero, "
                       "complemento_unidades AS complemento, bairro_unidades AS bairro, municipio_unidades AS municipio, "
                       "estado_unidades AS estado, cep_unidades AS cep, latitude_unidades AS latitude, "
                       "longitude_unidades AS longitude, telefone_contato_unidades AS telefone_contato, "
                       "ip_lan_01_unidades AS ip_lan_01, mv_ip_lan_sec_unidades AS mv_ip_lan_sec, "
                       "ip_lan_transito_unidades AS ip_lan_transito, "
                       "id_intragov_unidades AS id_intragov, "
                       "data_agendamento_unidades AS data_agendamento, hora_agendamento_unidades AS hora_agendamento, "
                       "contratada_planejada_unidades AS contratada_planejada, "
                       "field_planejada_unidades AS field_planejada, "
                       "contato_field_planejada_unidades AS contato_field_planejada, "
                       "loopback_vivo_unidades AS loopback_vivo, loopback_cliente_unidades AS loopback_cliente, "
                       "loopback_on_bgp_unidades AS loopback_on_bgp, "
                       "ticket_noc_unidades AS ticket_noc, "
                       + ", ".join(
                           f"{db} AS {js}"
                           for js, db in unidades_mv_opcionais_js_to_db().items()
                       )
                       + (", " if unidades_lan_extra_js_to_db() else "")
                       + ", ".join(
                           f"{db} AS {js}"
                           for js, db in unidades_lan_extra_js_to_db().items()
                       )
                       + " "
                       "FROM unidades WHERE id_vgr_unidades = %s LIMIT 1", (id_vgr,))
        unidade = cursor.fetchone()
        if not unidade:
            return jsonify(success=False, message="ID VGR inválido ou unidade não encontrada"), 404

        for key, value in unidade.items():
            if key == 'hora_agendamento':
                _prodesp_format_row_hora_agendamento(unidade, key)
            elif isinstance(value, timedelta):
                unidade[key] = str(value)
            elif isinstance(value, (date, datetime)):
                unidade[key] = value.isoformat()

        # Busca equipamentos associados à unidade (mesmo sem histórico de atendimento)
        cursor.execute("SELECT id_equipamentos AS id, modelo_equipamentos AS modelo, serial_equipamentos AS serial, versao_equipamentos AS versao, descricao_equipamentos AS descricao FROM equipamentos WHERE id_unidades_equipamentos = %s", (unidade['id_unidade'],))
        unidade['equipamentos'] = cursor.fetchall()

        # Busca links associados à unidade (mesmo sem histórico de atendimento)
        cursor.execute("SELECT id_link AS id, id_vgr_links, designador_links, tipo_links, operadora_links, vlan_links, ip_wan_links, redundante_critico_links, ip_gateway_links, ip_mascara_links, velocidade_links, pppoe_user_links, pppoe_pass_links FROM links WHERE id_unidades_links = %s", (unidade['id_unidade'],))
        unidade['links'] = decrypt_sensitive_rows_inplace(cursor.fetchall())

        decrypt_sensitive_row_inplace(unidade)

        unidade['observacoes'] = _prodesp_listar_observacoes_unidade_agendado(cursor, unidade['id_unidade'])

        return jsonify(success=True, unidade=unidade)
    finally:
        cursor.close()
        conn.close()

@prodesp_bp.route('/atendimentos/verificar_id_vgr/<string:id_vgr>')
@login_required
def verificar_atendimento_existente_id_vgr(id_vgr):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        brazil_tz = pytz.timezone('America/Sao_Paulo')
        today_date = datetime.now(brazil_tz).date()
        cursor.execute(
            "SELECT a.id_atendimentos, a.data_atendimentos, a.status_atendimentos, a.substatus_atendimentos, a.analista_atuante_atendimentos, a.id_unidades_atendimentos "
            "FROM atendimentos a JOIN unidades u ON a.id_unidades_atendimentos = u.id_unidades WHERE TRIM(u.id_vgr_unidades) = %s ORDER BY a.data_atendimentos DESC, a.horario_inicio_atendimentos DESC LIMIT 1", (id_vgr.strip(),))
        latest_attendance = cursor.fetchone()
        if not latest_attendance:
            return jsonify(aviso=False, allow_creation=True)

        status = latest_attendance['status_atendimentos'].strip()
        substatus = (latest_attendance.get('substatus_atendimentos') or '').strip()
        atendimento_id = latest_attendance['id_atendimentos']
        analyst_name = latest_attendance['analista_atuante_atendimentos']
        id_unidade = latest_attendance['id_unidades_atendimentos']
        attendance_date = parse_date_string(latest_attendance['data_atendimentos'], current_app.logger, atendimento_id)
        attendance_date = attendance_date.date() if attendance_date else None

        # Regra de Negócio: Redirecionar para edição se for um atendimento ativo/pausado DE HOJE
        redirect_statuses = ["Em Atendimento"]
        if status in redirect_statuses and attendance_date == today_date:
            return jsonify(
                aviso=True,
                mensagem=f"Existe um atendimento em andamento ou recente (ID: {atendimento_id}, Status: {status}) para o ID VGR {id_vgr}. Redirecionando para edição.",
                action_type="redirect_edit",
                atendimento_id=atendimento_id,
                allow_creation=False
            )

        # Regra de Negócio: Bloquear se Status E Substatus forem 'Concluído'
        if status.lower() in ['concluído', 'concluido'] and substatus.lower() in ['concluído', 'concluido']:
            return jsonify(
                aviso=True,
                mensagem=f"Já existe um atendimento finalizado (Status: {status}, Substatus: {substatus}) para o ID VGR {id_vgr}. Não é possível criar um novo.",
                action_type="block_creation",
                atendimento_id=atendimento_id,
                allow_creation=False
            )

        status_msg = f"{status} - {substatus}" if substatus else status
        data_fmt = attendance_date.strftime('%d/%m/%Y') if attendance_date else "Data Inválida"
        
        try:
            cursor.execute(
                "SELECT observacoes AS observacao_prodesp, timestamp_observacoes AS data_observacao FROM observacoes WHERE id_atendimentos_observacoes = %s ORDER BY timestamp_observacoes ASC",
                (atendimento_id,))
            previous_observacoes = cursor.fetchall()
            for obs in previous_observacoes:
                if isinstance(obs.get('data_observacao'), (datetime, date)):
                    obs['data_observacao'] = obs['data_observacao'].strftime('%d/%m/%Y %H:%M:%S')
        except Exception:
            previous_observacoes = []

        cursor.execute(
            "SELECT id_equipamentos AS id_equipamento, modelo_equipamentos AS modelo, serial_equipamentos AS serial, versao_equipamentos AS versao, descricao_equipamentos AS descricao FROM equipamentos WHERE id_unidades_equipamentos = %s",
            (id_unidade,))
        previous_equipamentos = cursor.fetchall()

        cursor.execute(
            "SELECT id_link AS id_link, id_vgr_links AS id_vgr, designador_links AS designador, tipo_links AS tipo, operadora_links AS operadora, vlan_links AS vlan, ip_wan_links AS ip_wan, redundante_critico_links AS redundante_critico, ip_gateway_links AS ip_gateway, ip_mascara_links AS ip_mascara, velocidade_links AS velocidade, pppoe_user_links AS pppoe_user, pppoe_pass_links AS pppoe_pass FROM links WHERE id_unidades_links = %s",
            (id_unidade,))
        previous_links = decrypt_sensitive_rows_inplace(cursor.fetchall())

        return jsonify(
            aviso=True,
            mensagem=f"Existe um atendimento anterior. Data: {data_fmt} (Status: {status_msg}) para o ID VGR {id_vgr}. Um novo atendimento será criado.",
            action_type="warn_and_continue",
            atendimento_id=atendimento_id,
            allow_creation=True,
            previous_observacoes=previous_observacoes,
            previous_equipamentos=previous_equipamentos,
            previous_links=previous_links
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route('/atendimentos/create', methods=['POST'])
@login_required
def create_atendimento():
    data = request.get_json() or {}

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)

    required_fields = {'status': "Status", 'id_vgr': "ID VGR", 'analista_atuante': "Analista Atuante"}
    for key, name in required_fields.items():
        if not data.get(key):
            return jsonify(message=f"Campo '{name}' é obrigatório.", success=False), 400

    # Validação adicional para status final
    final_statuses = list(FINAL_STATUSES_ATENDIMENTO)
    if data.get('status') in final_statuses:
        obrigatorios_final = {
            'contratada': "Contratada",
            'field': "Field",
            'contato_field': "Contato Field",
            'substatus': "Substatus"
        }
        campos_vazios = [nome for campo, nome in obrigatorios_final.items() if not data.get(campo)]
        if (
            str(data.get('status') or '').strip() == 'Concluído'
            and str(data.get('substatus') or '').strip() == 'Concluído'
        ):
            from prodesp.prodesp.ticket_noc_validation import validate_ticket_noc_format

            ticket_noc_err = validate_ticket_noc_format(data.get('ticket_noc'), obrigatorio=True)
            if ticket_noc_err:
                return jsonify(message=ticket_noc_err, success=False), 400
            eq_errs = _prodesp_erros_conclusao(
                None,
                id_unidade=None,
                hostname_unidade=data.get('hostname') or data.get('hostname_unidades'),
                logs_atendimentos=data.get('logs') or "",
                equipamentos_override=data.get('new_equipamentos') or [],
                links_override=data.get('new_links') or [],
            )
            if eq_errs:
                return jsonify(message=eq_errs[0], success=False, errors=eq_errs), 400
        if (
            str(data.get('status') or '').strip() == STATUS_QUEBRA_TBRA
            and str(data.get('substatus') or '').strip() not in SUBSTATUS_QUEBRA_TBRA_VALUES
        ):
            return jsonify(
                message=f"Para status «{STATUS_QUEBRA_TBRA}», selecione substatus Quebra SCI ou Quebra Técnica.",
                success=False,
            ), 400
        if (
            str(data.get('status') or '').strip() == 'Quebra'
            and str(data.get('substatus') or '').strip().startswith('Quebra')
            and not (data.get('motivos_fora_padrao') or [])
        ):
            return jsonify(
                message="Para status Quebra, selecione ao menos um motivo em Fora do padrão.",
                success=False,
            ), 400
        if campos_vazios:
            return jsonify(message=f"Para status '{data.get('status')}', os campos obrigatórios não preenchidos são: {', '.join(campos_vazios)}.", success=False), 400

    create_err = validate_create_payload(data)
    if create_err:
        return jsonify(message=create_err, success=False), 400

    field_create_msg = check_dados_field_create_em_atendimento(data)
    if field_create_msg:
        return jsonify(message=field_create_msg, success=False), 400

    if str(data.get("status") or "").strip() == "Em Atendimento":
        contratada_canonica, err_contratada = _prodesp_validar_contratada_planejada(
            data.get("contratada")
        )
        if err_contratada:
            return jsonify(message=err_contratada, success=False), 400
        data["contratada"] = contratada_canonica
        data["contato_field"] = _prodesp_normalizar_contato_field_planejado(
            data.get("contato_field")
        ) or ""
        data["field"] = (str(data.get("field") or "")).strip()

    try:
        id_unidade = data.get('id_unidade')
        id_vgr = str(data.get('id_vgr', '')).strip()

        # Mapeamento de campos do frontend para colunas do banco (unidades)
        unit_fields_map = {
            'nome': 'nome_unidades',
            'endereco': 'endereco_unidades',
            'numero': 'numero_unidades',
            'bairro': 'bairro_unidades',
            'municipio': 'municipio_unidades',
            'estado': 'estado_unidades',
            'complemento': 'complemento_unidades',
            'cep': 'cep_unidades',
            'latitude': 'latitude_unidades',
            'longitude': 'longitude_unidades',
            'telefone_contato': 'telefone_contato_unidades',
            'hostname': 'hostname_unidades',
            'acronimo': 'acronimo_unidades',
            'data_agendamento': 'data_agendamento_unidades',
            'hora_agendamento': 'hora_agendamento_unidades',
            'ip_lan_01': 'ip_lan_01_unidades',
            'ip_lan_transito': 'ip_lan_transito_unidades',
            'id_intragov': 'id_intragov_unidades',
            'loopback_vivo': 'loopback_vivo_unidades',
            'loopback_cliente': 'loopback_cliente_unidades',
            'loopback_on_bgp': 'loopback_on_bgp_unidades',
            'ticket_noc': 'ticket_noc_unidades',
            # Planejamento Dados Field (pré-atendimento / confirmação ao iniciar)
            'contratada': 'contratada_planejada_unidades',
            'field': 'field_planejada_unidades',
            'contato_field': 'contato_field_planejada_unidades',
        }
        unit_fields_map.update(unidades_mv_opcionais_js_to_db())
        unit_fields_map.update(unidades_lan_extra_js_to_db())

        if id_unidade:
            # Validação de integridade: Verifica se a unidade existe e se o ID VGR corresponde
            cur.execute("SELECT id_vgr_unidades FROM unidades WHERE id_unidades = %s", (id_unidade,))
            unidade_check = cur.fetchone()
            if not unidade_check:
                return jsonify(message="Unidade informada não encontrada no banco de dados.", success=False), 400
            if str(unidade_check['id_vgr_unidades']) != str(id_vgr):
                return jsonify(message=f"Inconsistência: O ID VGR informado ({id_vgr}) não corresponde à unidade selecionada.", success=False), 400
        else:
            # Se não veio id_unidade, verifica se existe pelo id_vgr ou cria nova
            cur.execute("SELECT id_unidades FROM unidades WHERE TRIM(id_vgr_unidades) = %s", (id_vgr,))
            existing_unit = cur.fetchone()
            if existing_unit:
                id_unidade = existing_unit['id_unidades']
            else:
                # Prepara dados para inserção garantindo campos obrigatórios para evitar erro 1364
                insert_data_unit = {'id_vgr_unidades': id_vgr}
                nullable_fields = ['latitude_unidades', 'longitude_unidades', 'data_agendamento_unidades', 'hora_agendamento_unidades']
                
                for json_key, db_col in unit_fields_map.items():
                    val = data.get(json_key)
                    # Tratamento para campos que devem ser NULL se vazios (datas, numeros)
                    if (val is None or val == '') and db_col in nullable_fields:
                        val = None
                    elif db_col in ('latitude_unidades', 'longitude_unidades'):
                        if val not in (None, ''):
                            coord_label = "Latitude" if db_col == "latitude_unidades" else "Longitude"
                            coord_err = validate_coordinate_for_db(val, field_label=coord_label)
                            if coord_err:
                                return jsonify(message=coord_err, success=False), 400
                            val = normalize_coordinate_for_db(val)
                    elif db_col == 'hora_agendamento_unidades':
                        val = normalize_hora_agendamento_db(val)
                    elif db_col == 'estado_unidades' and val:
                        val = normalize_estado_unidade(val) or ''
                    elif (db_col in UNIDADES_MV_OPCIONAIS_DB_COLUMNS or db_col in UNIDADES_LAN_EXTRA_DB_COLUMNS) and val not in (None, ''):
                        if db_col in UNIDADES_CIDR_DB_COLUMNS:
                            val = sanitize_ip_cidr_field(val)
                        else:
                            val = sanitize_plain_ipv4_field(val)
                    elif db_col in UNIDADES_CIDR_DB_COLUMNS and val not in (None, ''):
                        val = sanitize_ip_cidr_field(val)
                    elif val is None:
                        # Define string vazia para campos de texto para evitar erro de "doesn't have a default value"
                        val = ''
                    if is_sensitive_db_column(db_col) and val not in (None, ''):
                        val = encrypt_sensitive_db_column(db_col, val)
                    
                    insert_data_unit[db_col] = val

                cols = ', '.join([f"`{k}`" for k in insert_data_unit.keys()])
                placeholders = ', '.join(['%s'] * len(insert_data_unit))
                sql_insert = f"INSERT INTO unidades ({cols}) VALUES ({placeholders})"
                cur.execute(sql_insert, list(insert_data_unit.values()))
                id_unidade = cur.lastrowid
            data['id_unidade'] = id_unidade # Atualiza para uso posterior

        tz_sp = pytz.timezone('America/Sao_Paulo')
        now = datetime.now(tz_sp)
        today_date = now.date()

        bloqueado, resp_dup, http_dup = _prodesp_bloquear_create_duplicado_em_atendimento(
            cur, conn, id_unidade, data.get('status'), today_date
        )
        if bloqueado:
            return resp_dup, http_dup

        cur.execute(
            """
            SELECT contratada_planejada_unidades, field_planejada_unidades, contato_field_planejada_unidades
            FROM unidades WHERE id_unidades = %s
            """,
            (id_unidade,),
        )
        planejado = cur.fetchone() or {}
        decrypt_sensitive_row_inplace(planejado)

        def _valor_dados_field_create(js_key, col_planejada):
            val = (data.get(js_key) or "").strip()
            if val:
                if js_key == "contato_field":
                    return _prodesp_normalizar_contato_field_planejado(val) or ""
                return val
            bruto = (planejado.get(col_planejada) or "").strip()
            if js_key == "contato_field":
                return _prodesp_normalizar_contato_field_planejado(bruto) or ""
            return bruto

        status_create = (data.get('status') or '').strip()
        sub_create_raw = (data.get('substatus') or '').strip()
        if status_create == 'Em Atendimento' and _prodesp_is_agendamento_ou_gp(current_user):
            msg_ag_create = validar_substatus_create_ag_gp(
                sub_create_raw or SUBSTATUS_INICIAL_FILA
            )
            if msg_ag_create:
                return jsonify(message=msg_ag_create, success=False), 403

        now_time_str = now.strftime("%H:%M:%S")
        if status_create == 'Em Atendimento':
            horario_inicio = now_time_str
            horario_final = None
        elif status_create in FINAL_STATUSES_ATENDIMENTO:
            horario_inicio = now_time_str
            horario_final = now_time_str
        else:
            horario_inicio = None
            horario_final = None

        from prodesp.prodesp.caderno.fgt_ssh_collector import sanitize_logs_atendimento_for_db

        insert_data = {
            'status_atendimentos': data.get('status'),
            'substatus_atendimentos': normalizar_substatus_fluxo(sub_create_raw) or SUBSTATUS_INICIAL_FILA,
            'analista_atuante_atendimentos': data.get('analista_atuante'),
            'analista_configuracao_atendimentos': data.get('analista_configuracao'),
            'analista_mpls_atendimentos': data.get('analista_mpls_atendimentos'),
            'analista_caderno_teste_atendimentos': data.get('analista_caderno_teste'),
            'contratada_atendimentos': _valor_dados_field_create('contratada', 'contratada_planejada_unidades'),
            'field_atendimentos': _valor_dados_field_create('field', 'field_planejada_unidades'),
            'contato_field_atendimentos': _valor_dados_field_create('contato_field', 'contato_field_planejada_unidades'),
            'logs_atendimentos': sanitize_logs_atendimento_for_db(data.get('logs') or ''),
            'id_unidades_atendimentos': id_unidade,
            'data_atendimentos': now.strftime("%Y-%m-%d %H:%M:%S"),
            'horario_inicio_atendimentos': horario_inicio,
            'horario_finalizacao_atendimentos': horario_final,
        }
        from prodesp.prodesp.substatus_materializado import apply_stamp_on_create

        apply_stamp_on_create(insert_data, now=now)
        insert_data['contato_field_atendimentos'] = encrypt_sensitive_db_column(
            'contato_field_atendimentos',
            insert_data['contato_field_atendimentos'],
        )

        columns = '`, `'.join(insert_data.keys())
        placeholders = ', '.join(['%s'] * len(insert_data))
        sql = f"INSERT INTO atendimentos (`{columns}`) VALUES ({placeholders})"
        
        current_app.logger.info(f"prodesp - LOG HORARIO: Criando atendimento ID VGR {data.get('id_vgr')} com 'horario_inicio': {insert_data['horario_inicio_atendimentos']}")
        cur.execute(sql, list(insert_data.values()))
        new_id = cur.lastrowid

        # Atualiza campos da unidade se fornecidos
        unidade_updates = {}
        
        nullable_unit_fields = [
            'latitude_unidades', 'longitude_unidades',
            'data_agendamento_unidades', 'hora_agendamento_unidades',
        ]
        for json_key, db_col in unit_fields_map.items():
            if json_key not in data:
                continue
            val = data.get(json_key)
            if val == '' and db_col in nullable_unit_fields:
                continue
            if db_col == 'hora_agendamento_unidades':
                val = normalize_hora_agendamento_db(val)
                if val is None:
                    continue
            elif db_col in ('latitude_unidades', 'longitude_unidades'):
                if val in (None, ''):
                    continue
                coord_label = "Latitude" if db_col == "latitude_unidades" else "Longitude"
                coord_err = validate_coordinate_for_db(val, field_label=coord_label)
                if coord_err:
                    conn.rollback()
                    return jsonify(message=coord_err, success=False), 400
                val = normalize_coordinate_for_db(val)
            elif (db_col in UNIDADES_MV_OPCIONAIS_DB_COLUMNS or db_col in UNIDADES_LAN_EXTRA_DB_COLUMNS) and val not in (None, ''):
                if db_col in UNIDADES_CIDR_DB_COLUMNS:
                    val = sanitize_ip_cidr_field(val)
                else:
                    val = sanitize_plain_ipv4_field(val)
            elif db_col in UNIDADES_CIDR_DB_COLUMNS and val not in (None, ''):
                val = sanitize_ip_cidr_field(val)
            elif val == '' and db_col in nullable_unit_fields:
                val = None
            if is_sensitive_db_column(db_col) and val not in (None, ''):
                val = encrypt_sensitive_db_column(db_col, val)
            unidade_updates[db_col] = val

        if unidade_updates:
            lb_cols = (
                "loopback_vivo_unidades",
                "loopback_cliente_unidades",
                "loopback_on_bgp_unidades",
            )
            if any(c in unidade_updates for c in lb_cols):
                cur.execute(
                    """
                    SELECT loopback_vivo_unidades, loopback_cliente_unidades, loopback_on_bgp_unidades
                    FROM unidades WHERE id_unidades = %s
                    """,
                    (id_unidade,),
                )
                old_lb = cur.fetchone() or {}
                merged_lb = {
                    c: unidade_updates.get(c, old_lb.get(c))
                    for c in lb_cols
                }
                lb_errs = find_loopback_uniqueness_errors(
                    cur,
                    merged_lb,
                    exclude_unidade_id=id_unidade,
                )
                if lb_errs:
                    conn.rollback()
                    return jsonify(message=lb_errs[0], success=False), 400
            set_clauses = ', '.join([f"`{col}` = %s" for col in unidade_updates])
            cur.execute(f"UPDATE unidades SET {set_clauses} WHERE id_unidades = %s", (*unidade_updates.values(), id_unidade))

        _prodesp_vincular_observacoes_unidade_ao_atendimento(cur, conn, id_unidade, new_id)

        for obs in data.get('new_observacoes', []):
            texto = (obs.get('observacao_prodesp') or '').strip()
            if not texto:
                continue
            len_err = validate_observacao_text(texto)
            if len_err:
                conn.rollback()
                return jsonify(message=len_err, success=False), 400
            cur.execute(
                """
                SELECT 1 FROM observacoes
                WHERE id_atendimentos_observacoes = %s AND observacoes = %s
                LIMIT 1
                """,
                (new_id, texto),
            )
            if cur.fetchone():
                continue
            timestamp = parse_date_string(obs.get('data_observacao'), current_app.logger, new_id)
            cur.execute(
                "INSERT INTO observacoes (id_unidades_observacoes, observacoes, timestamp_observacoes, id_atendimentos_observacoes) VALUES (%s, %s, %s, %s)",
                (id_unidade, texto, timestamp, new_id),
            )
            registrar_log(conn, 'atendimentos', new_id, 'Observação', None, texto, 'INSERT')
        from .prodesp.blueprint.prodesp_routes import (
            buscar_colisao_serial_equipamento,
            mensagem_serial_duplicado,
        )

        for eq in data.get('new_equipamentos', []):
            serial = (eq.get('serial') or '').strip().upper()
            descricao = eq.get('descricao')
            modelo = (eq.get('modelo') or '').strip()
            if serial and not modelo:
                modelo = infer_modelo_equipamento_from_serial(serial)
            versao = eq.get('versao')
            len_err = validate_equipamento_fields(
                {"serial": serial, "versao": versao, "modelo": modelo, "descricao": descricao}
            )
            if len_err:
                return jsonify(message=len_err, success=False), 400

            if serial:
                # Não mover entre unidades (antes: ON DUPLICATE KEY UPDATE mudava id_unidade).
                vgr_colisao = buscar_colisao_serial_equipamento(
                    cur, serial, None, exclude_unidade_id=id_unidade
                )
                if vgr_colisao:
                    return jsonify(
                        message=mensagem_serial_duplicado(serial, vgr_colisao),
                        success=False,
                    ), 400
                same_id = _prodesp_find_equipamento_same_unit(cur, id_unidade, serial)
                if same_id:
                    cur.execute(
                        """
                        UPDATE equipamentos SET
                          modelo_equipamentos = %s,
                          versao_equipamentos = %s,
                          descricao_equipamentos = %s
                        WHERE id_equipamentos = %s
                        """,
                        (modelo, versao, descricao, same_id),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO equipamentos (
                          modelo_equipamentos, serial_equipamentos, versao_equipamentos,
                          descricao_equipamentos, id_unidades_equipamentos
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        (modelo, serial, versao, descricao, id_unidade),
                    )
            else:
                cur.execute(
                    """
                    INSERT INTO equipamentos (
                      modelo_equipamentos, serial_equipamentos, versao_equipamentos,
                      descricao_equipamentos, id_unidades_equipamentos
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (modelo, serial, versao, descricao, id_unidade),
                )

        for lnk in data.get('new_links', []):
            lnk = normalize_link_api_payload(lnk)
            len_err = validate_link_fields(lnk)
            if len_err:
                return jsonify(success=False, message=len_err), 400
            uniq_errs = find_link_uniqueness_errors(
                cur,
                lnk,
                exclude_link_id=lnk.get("id"),
                id_unidade=id_unidade,
            )
            if uniq_errs:
                return jsonify(success=False, message=uniq_errs[0]), 400
            designador = lnk.get('designador', '').strip()
            id_vgr_link = lnk.get('id_vgr') if lnk.get('id_vgr') else data.get('id_vgr')
            
            sql_link_upsert = """
                INSERT INTO links (id_unidades_links, id_vgr_links, designador_links, tipo_links, operadora_links, vlan_links, ip_wan_links, ip_gateway_links, ip_mascara_links, velocidade_links, pppoe_user_links, pppoe_pass_links)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    id_unidades_links = VALUES(id_unidades_links),
                    id_vgr_links = VALUES(id_vgr_links),
                    tipo_links = VALUES(tipo_links),
                    operadora_links = VALUES(operadora_links),
                    vlan_links = VALUES(vlan_links),
                    ip_wan_links = VALUES(ip_wan_links),
                    ip_gateway_links = VALUES(ip_gateway_links),
                    ip_mascara_links = VALUES(ip_mascara_links),
                    velocidade_links = VALUES(velocidade_links),
                    pppoe_user_links = VALUES(pppoe_user_links),
                    pppoe_pass_links = VALUES(pppoe_pass_links)
            """
            cur.execute(
                sql_link_upsert,
                (
                    id_unidade, id_vgr_link, lnk.get('designador'), lnk.get('tipo'), lnk.get('operadora'),
                    lnk.get('vlan'), lnk.get('ip_wan'), lnk.get('ip_gateway'), lnk.get('ip_mascara'),
                    lnk.get('velocidade'),
                    encrypt_sensitive_db_column('pppoe_user_links', lnk.get('pppoe_user')),
                    encrypt_sensitive_db_column('pppoe_pass_links', lnk.get('pppoe_pass')),
                ),
            )

        salvar_motivos_fora_padrao(cur, new_id, data.get('motivos_fora_padrao', []))

        registrar_log(conn, 'atendimentos', new_id, None, None, f"Atendimento criado ({new_id})", 'INSERT')
        _prodesp_tempo_snapshot_refresh(cur, new_id)
        conn.commit()
        acr_novo = (data.get("acronimo") or "").strip()
        if not acr_novo and id_unidade:
            cur.execute(
                "SELECT acronimo_unidades FROM unidades WHERE id_unidades = %s",
                (id_unidade,),
            )
            row_acr = cur.fetchone() or {}
            acr_novo = (row_acr.get("acronimo_unidades") or "").strip()
        _prodesp_hook_certificado_auto_export(
            new_id,
            acronimo=acr_novo,
            old_status="",
            old_substatus="",
            new_status=data.get("status"),
            new_substatus=data.get("substatus"),
        )
        _prodesp_mutations_cache_bust()
        return jsonify(message="Atendimento criado!", success=True, id=new_id, id_unidade=id_unidade), 200
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(e, log=current_app.logger, action="Erro ao criar atendimento", entity_id=None)
    finally:
        cur.close()
        conn.close()


@prodesp_bp.route('/api/quebra_massa', methods=['POST'])
@login_required
def api_quebra_massa():
    """Quebra em lote para unidades agendadas (sem motivos fora do padrão)."""
    if not _prodesp_pode_operar_atendimentos_na_gestao(current_user):
        return jsonify(message="Sem permissão para quebra em massa.", success=False), 403

    data = request.get_json() or {}
    raw_ids = data.get('ids_vgr') or []
    if not isinstance(raw_ids, list):
        return jsonify(message="Lista de VGRs inválida.", success=False), 400
    ids_vgr = _prodesp_quebra_massa_dedupe_ids_vgr(raw_ids)
    status = (data.get('status') or '').strip()
    substatus = (data.get('substatus') or '').strip()
    observacao = (data.get('observacao') or '').strip()

    if not ids_vgr:
        return jsonify(message="Selecione ao menos uma unidade agendada.", success=False), 400
    if len(ids_vgr) > 200:
        return jsonify(message="Máximo de 200 unidades por lote.", success=False), 400

    if status not in ('Quebra', STATUS_QUEBRA_TBRA):
        return jsonify(message="Tipo de quebra inválido.", success=False), 400
    if status == 'Quebra' and not substatus.startswith('Quebra'):
        return jsonify(message="Substatus de Quebra inválido.", success=False), 400
    if status == STATUS_QUEBRA_TBRA and substatus not in SUBSTATUS_QUEBRA_TBRA_VALUES:
        return jsonify(
            message=f"Para «{STATUS_QUEBRA_TBRA}», selecione substatus Quebra SCI ou Quebra Técnica.",
            success=False,
        ), 400

    obs_err = validate_observacao_text(observacao)
    if obs_err or len(observacao) < 10:
        return jsonify(message="Observação obrigatória (mín. 10 caracteres).", success=False), 400

    tz_sp = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(tz_sp)
    analista = (getattr(current_user, 'nome_user', None) or '').strip()
    texto_obs = f"[{substatus}] {observacao}"

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True, buffered=True)
    criados = []
    erros = []
    try:
        for id_vgr in ids_vgr:
            try:
                criado, err = _prodesp_quebra_massa_processar_unidade(
                    cur,
                    conn,
                    id_vgr=id_vgr,
                    status=status,
                    substatus=substatus,
                    texto_obs=texto_obs,
                    analista=analista,
                )
            except Exception as unit_exc:
                err_msg, _ = message_from_mysql_exception(unit_exc)
                erros.append(f"VGR {id_vgr}: {err_msg}")
                continue
            if criado:
                criados.append(criado)
            elif err:
                erros.append(err)

        if not criados:
            return jsonify(
                message="Nenhum atendimento criado.",
                success=False,
                erros=erros,
            ), 400

        _prodesp_mutations_cache_bust()
        return jsonify(
            message=f"{len(criados)} atendimento(s) de quebra criado(s).",
            success=True,
            criados=criados,
            erros=erros,
        ), 200
    except Exception as e:
        try:
            conn.rollback()
        except Error:
            pass
        return _prodesp_json_error(e, log=current_app.logger, action="Erro na quebra em massa", entity_id=None, erros=erros)
    finally:
        cur.close()
        conn.close()


@prodesp_bp.route('/observacoes-update', methods=['POST'])
@login_required
def observacoes_update():
    payload = request.get_json() or {}
    atendimento, obs_novas, obs_deletar = payload.get('id_atendimento'), payload.get('new_observacoes', []), payload.get('deleted_observacoes', [])
    if not atendimento:
        return jsonify(message="Dados inválidos.", success=False), 400
    if not obs_novas and not obs_deletar:
        return jsonify(message="Nada a salvar.", success=True)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            sql_select_atendimento_by_id(include_logs=False),
            (atendimento,),
        )
        row_at = cursor.fetchone()
        if not row_at:
            return jsonify(message="Atendimento não encontrado.", success=False), 404
        permitido, msg_ed, http_ed = _prodesp_validar_edicao_observacao_atendimento(current_user, row_at)
        if not permitido:
            return jsonify(message=msg_ed, success=False), http_ed

        id_unidade_obs = row_at.get("id_unidades_atendimentos")

        if obs_deletar:
            for oid in obs_deletar:
                cursor.execute("SELECT observacoes FROM observacoes WHERE id_observacoes = %s", (oid,))
                row = cursor.fetchone()
                if row:
                    registrar_log(
                        conn,
                        'atendimentos',
                        atendimento,
                        'Observação',
                        row.get('observacoes'),
                        None,
                        'DELETE',
                    )
            cursor.executemany("DELETE FROM observacoes WHERE id_observacoes = %s", [(oid,) for oid in obs_deletar])
        
        for o in obs_novas:
            len_err = validate_observacao_text(o.get('observacao_prodesp'))
            if len_err:
                return jsonify(message=len_err, success=False), 400
            timestamp = parse_date_string(o.get('data_observacao'), current_app.logger, atendimento)
            cursor.execute("INSERT INTO observacoes (id_unidades_observacoes, observacoes, timestamp_observacoes, id_atendimentos_observacoes) VALUES (%s, %s, %s, %s)",
                           (id_unidade_obs, o['observacao_prodesp'], timestamp, atendimento))
            registrar_log(conn, 'atendimentos', atendimento, 'Observação', None, o['observacao_prodesp'], 'INSERT')
            
        conn.commit()
        observacoes = _prodesp_listar_observacoes_atendimento_e_unidade(
            cursor, atendimento, id_unidade_obs
        )
        _prodesp_mutations_cache_bust()
        return jsonify(message="Observações salvas!", success=True, observacoes=observacoes)
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(e, log=current_app.logger, action="Erro ao salvar observações", entity_id=atendimento)
    finally:
        cursor.close(); conn.close()


@prodesp_bp.route('/unidades-observacoes-update', methods=['POST'])
@login_required
def unidades_observacoes_update():
    """Persiste observações da unidade sem criar/vincular atendimento (id_atendimentos NULL)."""
    payload = request.get_json() or {}
    id_unidade = payload.get('id_unidade')
    obs_novas = payload.get('new_observacoes', [])
    obs_deletar = payload.get('deleted_observacoes', [])
    if not id_unidade:
        return jsonify(message="Dados inválidos.", success=False), 400
    if not obs_novas and not obs_deletar:
        return jsonify(message="Nada a salvar.", success=True, observacoes=[])

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id_unidades FROM unidades WHERE id_unidades = %s", (id_unidade,))
        if not cursor.fetchone():
            return jsonify(message="Unidade não encontrada.", success=False), 404

        if obs_deletar:
            for oid in obs_deletar:
                cursor.execute(
                    """SELECT observacoes FROM observacoes
                       WHERE id_observacoes = %s AND id_unidades_observacoes = %s
                         AND id_atendimentos_observacoes IS NULL""",
                    (oid, id_unidade),
                )
                row = cursor.fetchone()
                if row:
                    registrar_log(
                        conn,
                        'unidades',
                        id_unidade,
                        'Observação',
                        row.get('observacoes'),
                        None,
                        'DELETE',
                    )
            cursor.executemany(
                """DELETE FROM observacoes
                   WHERE id_observacoes = %s AND id_unidades_observacoes = %s
                     AND id_atendimentos_observacoes IS NULL""",
                [(oid, id_unidade) for oid in obs_deletar],
            )

        for o in obs_novas:
            obs_err = validate_observacao_text(o.get('observacao_prodesp'))
            if obs_err:
                return jsonify(message=obs_err, success=False), 400
            timestamp = parse_date_string(o.get('data_observacao'), current_app.logger, id_unidade)
            cursor.execute(
                """INSERT INTO observacoes
                   (id_unidades_observacoes, observacoes, timestamp_observacoes, id_atendimentos_observacoes)
                   VALUES (%s, %s, %s, NULL)""",
                (id_unidade, o['observacao_prodesp'], timestamp),
            )
            registrar_log(
                conn,
                'unidades',
                id_unidade,
                'Observação',
                None,
                o['observacao_prodesp'],
                'INSERT',
            )

        conn.commit()
        observacoes = _prodesp_listar_observacoes_unidade_agendado(cursor, id_unidade)
        _prodesp_mutations_cache_bust()
        return jsonify(message="Observações salvas!", success=True, observacoes=observacoes)
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(
            e, log=current_app.logger, action="salvar observações unidade", entity_id=id_unidade
        )
    finally:
        cursor.close()
        conn.close()


def _prodesp_listar_equipamentos_unidade(cursor, id_unidade):
    cursor.execute(
        """
        SELECT id_equipamentos AS id, modelo_equipamentos AS modelo,
               serial_equipamentos AS serial, versao_equipamentos AS versao,
               descricao_equipamentos AS descricao
        FROM equipamentos
        WHERE id_unidades_equipamentos = %s
        ORDER BY id_equipamentos
        """,
        (id_unidade,),
    )
    return cursor.fetchall()


def _prodesp_listar_links_unidade(cursor, id_unidade):
    cursor.execute(
        """
        SELECT id_link AS id, id_vgr_links, designador_links, tipo_links,
               operadora_links, vlan_links, ip_wan_links, redundante_critico_links,
               ip_gateway_links,
               ip_mascara_links, velocidade_links, pppoe_user_links, pppoe_pass_links
        FROM links
        WHERE id_unidades_links = %s
        ORDER BY id_link
        """,
        (id_unidade,),
    )
    return decrypt_sensitive_rows_inplace(cursor.fetchall())


def _prodesp_find_equipamento_same_unit(cursor, id_unidade, serial, exclude_id=None):
    """Retorna id_equipamentos se o serial já existir na mesma unidade."""
    if not serial:
        return None
    cursor.execute(
        """
        SELECT id_equipamentos FROM equipamentos
        WHERE id_unidades_equipamentos = %s AND serial_equipamentos = %s
          AND id_equipamentos != %s
        """,
        (id_unidade, serial, exclude_id if exclude_id else -1),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return row["id_equipamentos"] if isinstance(row, dict) else row[0]


def _prodesp_find_link_same_unit(cursor, id_unidade, designador, id_vgr_link, exclude_id=None):
    """Retorna id_link se designador ou id_vgr já existir na mesma unidade."""
    ex = exclude_id if exclude_id else -1
    if designador:
        cursor.execute(
            """
            SELECT id_link FROM links
            WHERE id_unidades_links = %s AND designador_links = %s
              AND id_link != %s
            """,
            (id_unidade, designador, ex),
        )
        row = cursor.fetchone()
        if row:
            return row[0]
    id_vgr_s = str(id_vgr_link).strip() if id_vgr_link else ""
    if id_vgr_s:
        cursor.execute(
            """
            SELECT id_link FROM links
            WHERE id_unidades_links = %s AND TRIM(COALESCE(id_vgr_links, '')) = %s
              AND id_link != %s
            """,
            (id_unidade, id_vgr_s, ex),
        )
        row = cursor.fetchone()
        if row:
            return row[0]
    return None


@prodesp_bp.route('/equipamentos-update', methods=['POST'])
@login_required
def equipamentos_update():
    payload = request.get_json() or {}
    id_atendimento = payload.get('id_atendimento')
    id_unidade, eq_novos, eq_deletar = payload.get('id_unidade_equipamentos'), payload.get('new_equipamentos', []), payload.get('deleted_equipamentos', [])
    if not id_unidade:
        return jsonify(message="Dados inválidos.", success=False), 400
    if not eq_novos and not eq_deletar:
        return jsonify(message="Nada a salvar.", success=True)

    conn = get_db_connection()
    cursor = conn.cursor()
    cur_list = None
    try:
        if id_atendimento:
            cur_perm = conn.cursor(dictionary=True)
            cur_perm.execute(
                sql_select_atendimento_by_id(include_logs=False),
                (id_atendimento,),
            )
            row_at = cur_perm.fetchone()
            cur_perm.close()
            if not row_at:
                return jsonify(message="Atendimento não encontrado.", success=False), 404
            permitido, msg_ed, http_ed = _prodesp_validar_edicao_atendimento(current_user, row_at)
            if not permitido:
                return jsonify(message=msg_ed, success=False), http_ed

        # Recupera o ID VGR para validação correta de duplicidade entre sites
        cursor.execute("SELECT id_vgr_unidades FROM unidades WHERE id_unidades = %s", (id_unidade,))
        res_vgr = cursor.fetchone()
        id_vgr_val = str(res_vgr[0]).strip() if res_vgr and res_vgr[0] else None

        if eq_deletar: 
            for eid in eq_deletar:
                cursor.execute("SELECT modelo_equipamentos, serial_equipamentos FROM equipamentos WHERE id_equipamentos = %s", (eid,))
                row = cursor.fetchone()
                if row and id_atendimento:
                    info = f"{row[0]} - {row[1]}"
                    registrar_log(conn, 'atendimentos', id_atendimento, 'Equipamento', info, None, 'DELETE')
            cursor.executemany("DELETE FROM equipamentos WHERE id_equipamentos = %s", [(eid,) for eid in eq_deletar])

        for e in eq_novos:
            eq_id = e.get('id') # Get the ID if it's an existing item
            len_err = validate_equipamento_fields(e)
            if len_err:
                return jsonify(message=len_err, success=False), 400
            serial = (e.get('serial') or '').strip().upper()
            versao = (e.get('versao') or '').strip()
            modelo = (e.get('modelo') or '').strip()
            if serial and not modelo:
                modelo = infer_modelo_equipamento_from_serial(serial)
            descricao = e.get('descricao', '').strip()
            info = f"{modelo} - {serial}"

            if serial:
                # Bloqueia serial em outra unidade (mesma mensagem do Blueprint); na mesma unidade faz UPDATE.
                from .prodesp.blueprint.prodesp_routes import (
                    buscar_colisao_serial_equipamento,
                    mensagem_serial_duplicado,
                )

                vgr_colisao = buscar_colisao_serial_equipamento(
                    cursor,
                    serial,
                    eq_id if eq_id else None,
                    exclude_unidade_id=id_unidade,
                )
                if vgr_colisao:
                    return jsonify(
                        message=mensagem_serial_duplicado(serial, vgr_colisao),
                        success=False,
                    ), 400

            if not eq_id and serial:
                eq_id = _prodesp_find_equipamento_same_unit(cursor, id_unidade, serial)

            if eq_id: # This is an update operation
                from prodesp.prodesp.admin_inventory import (
                    apply_partial_update,
                    registrar_field_changes,
                )

                cur_old = conn.cursor(dictionary=True)
                try:
                    cur_old.execute(
                        """
                        SELECT id_equipamentos, id_unidades_equipamentos, modelo_equipamentos,
                               serial_equipamentos, versao_equipamentos, descricao_equipamentos
                        FROM equipamentos WHERE id_equipamentos = %s
                        """,
                        (eq_id,),
                    )
                    old_eq = cur_old.fetchone() or {}
                finally:
                    cur_old.close()
                new_eq_map = {
                    "modelo_equipamentos": modelo,
                    "serial_equipamentos": serial,
                    "versao_equipamentos": versao,
                    "descricao_equipamentos": descricao,
                    "id_unidades_equipamentos": id_unidade,
                }
                eq_changes = apply_partial_update(
                    cursor,
                    table="equipamentos",
                    pk_column="id_equipamentos",
                    pk_value=int(eq_id),
                    old_map=old_eq,
                    new_map=new_eq_map,
                )
                if eq_changes:
                    registrar_field_changes(
                        conn, "equipamentos", int(eq_id), eq_changes, operacao="UPDATE"
                    )
            else: # This is an insert operation
                # If serial is empty for a new insert, it might be an issue depending on DB schema.
                # Assuming serial is required for new inserts based on previous logic.
                if not serial:
                    return jsonify(message="Erro: Serial é obrigatório para novos equipamentos.", success=False), 400
                
                sql_insert = """
                    INSERT INTO equipamentos (modelo_equipamentos, serial_equipamentos, versao_equipamentos, descricao_equipamentos, id_unidades_equipamentos) 
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(sql_insert, (modelo, serial, versao, descricao, id_unidade))
                if id_atendimento:
                    registrar_log(conn, 'atendimentos', id_atendimento, 'Equipamento', None, f"Adicionado: {modelo} - {serial}", 'INSERT')
                new_eq_id = cursor.lastrowid
                if new_eq_id:
                    from prodesp.prodesp.admin_inventory import (
                        collect_field_changes,
                        registrar_field_changes,
                    )

                    ins_map = {
                        "modelo_equipamentos": modelo,
                        "serial_equipamentos": serial,
                        "versao_equipamentos": versao,
                        "descricao_equipamentos": descricao,
                        "id_unidades_equipamentos": id_unidade,
                    }
                    registrar_field_changes(
                        conn,
                        "equipamentos",
                        int(new_eq_id),
                        collect_field_changes({}, ins_map),
                        operacao="INSERT",
                    )

        conn.commit()
        cur_list = conn.cursor(dictionary=True)
        equipamentos = _prodesp_listar_equipamentos_unidade(cur_list, id_unidade)
        _prodesp_mutations_cache_bust()
        return jsonify(
            message="Equipamentos salvos!",
            success=True,
            equipamentos=equipamentos,
        )
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(e, log=current_app.logger, action="Erro ao salvar equipamentos", entity_id=id_atendimento)
    finally:
        if cur_list is not None:
            cur_list.close()
        cursor.close()
        conn.close()

@prodesp_bp.route('/api/check-uniqueness', methods=['POST'])
@login_required
def api_check_uniqueness():
    """
    Pré-validação de duplicidade (links e/ou loopbacks) antes de salvar/gerar Blueprint.
    Não altera dados — só informa conflitos.
    """
    payload = request.get_json() or {}
    id_unidade = payload.get("id_unidade")
    links = payload.get("links") or []
    loopbacks = payload.get("loopbacks") or {}

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        errors: list[str] = []
        if links:
            from .prodesp.link_uniqueness_rules import find_batch_link_uniqueness_errors

            errors.extend(
                find_batch_link_uniqueness_errors(
                    cursor,
                    links,
                    id_unidade=id_unidade,
                )
            )
        if loopbacks:
            errors.extend(
                find_loopback_uniqueness_errors(
                    cursor,
                    loopbacks,
                    exclude_unidade_id=id_unidade,
                )
            )
        if errors:
            return jsonify(success=False, ok=False, errors=errors, message=errors[0]), 200
        return jsonify(success=True, ok=True, errors=[], message=""), 200
    except Exception as e:
        return _prodesp_json_error(e, log=current_app.logger, action="Erro ao validar unicidade")
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route('/links-update', methods=['POST'])
@login_required
def links_update():
    payload = request.get_json() or {}
    id_atendimento = payload.get('id_atendimento')
    id_unidade, lnk_novos, lnk_deletar = payload.get('id_unidade_links'), payload.get('new_links', []), payload.get('deleted_links', [])
    if not id_unidade:
        return jsonify(message="Dados inválidos.", success=False), 400
    if not lnk_novos and not lnk_deletar:
        return jsonify(message="Nada a salvar.", success=True)

    conn = get_db_connection()
    cursor = conn.cursor()
    cur_list = None
    try:
        if id_atendimento:
            cur_perm = conn.cursor(dictionary=True)
            cur_perm.execute(
                sql_select_atendimento_by_id(include_logs=False),
                (id_atendimento,),
            )
            row_at = cur_perm.fetchone()
            cur_perm.close()
            if not row_at:
                return jsonify(message="Atendimento não encontrado.", success=False), 404
            permitido, msg_ed, http_ed = _prodesp_validar_edicao_atendimento(current_user, row_at)
            if not permitido:
                return jsonify(message=msg_ed, success=False), http_ed

        # Recupera o ID VGR para validação correta de duplicidade entre sites
        cursor.execute("SELECT id_vgr_unidades FROM unidades WHERE id_unidades = %s", (id_unidade,))
        res_vgr = cursor.fetchone()
        id_vgr_val = str(res_vgr[0]).strip() if res_vgr and res_vgr[0] else None

        if lnk_deletar: 
            for lid in lnk_deletar:
                cursor.execute("SELECT tipo_links, designador_links FROM links WHERE id_link = %s", (lid,))
                row = cursor.fetchone()
                if row and id_atendimento:
                    info = f"{row[0]} - {row[1]}"
                    registrar_log(conn, 'atendimentos', id_atendimento, 'Link', info, None, 'DELETE')
            cursor.executemany("DELETE FROM links WHERE id_link = %s", [(lid,) for lid in lnk_deletar])

        for l in lnk_novos:
            link_id = l.get('id') # Get the ID if it's an existing item
            existing_link = None
            if link_id:
                cur_existing = conn.cursor(dictionary=True)
                cur_existing.execute(
                    sql_select_link_by_id_and_unidade(),
                    (link_id, id_unidade),
                )
                existing_link = cur_existing.fetchone()
                cur_existing.close()
            l = normalize_link_api_payload(l, existing_link)
            len_err = validate_link_fields(l)
            if len_err:
                return jsonify(message=len_err, success=False), 400
            designador = l.get('designador', '').strip()
            id_vgr_link = l.get('id_vgr') if l.get('id_vgr') else id_vgr_val

            if not link_id:
                same_unit_link = _prodesp_find_link_same_unit(
                    cursor, id_unidade, designador, id_vgr_link
                )
                if same_unit_link:
                    link_id = same_unit_link

            cur_uniq = conn.cursor(dictionary=True)
            try:
                uniq_errs = find_link_uniqueness_errors(
                    cur_uniq,
                    l,
                    exclude_link_id=link_id,
                    id_unidade=id_unidade,
                )
            finally:
                cur_uniq.close()
            if uniq_errs:
                return jsonify(message=uniq_errs[0], success=False), 400

            if link_id: # This is an update operation
                from prodesp.prodesp.admin_inventory import (
                    _LINK_ENCRYPT_COLS,
                    apply_partial_update,
                    registrar_field_changes,
                )
                from prodesp.prodesp.sensitive_fields_crypto import decrypt_sensitive_row_inplace

                old_link = existing_link
                if not old_link or int(old_link.get("id_link") or 0) != int(link_id):
                    cur_old = conn.cursor(dictionary=True)
                    try:
                        cur_old.execute(
                            """
                            SELECT id_link, designador_links, tipo_links, operadora_links, vlan_links,
                                   ip_wan_links, ip_gateway_links, ip_mascara_links, velocidade_links,
                                   pppoe_user_links, pppoe_pass_links, id_vgr_links, id_unidades_links,
                                   redundante_critico_links
                            FROM links WHERE id_link = %s
                            """,
                            (link_id,),
                        )
                        old_link = cur_old.fetchone() or {}
                    finally:
                        cur_old.close()
                else:
                    old_link = dict(old_link)
                decrypt_sensitive_row_inplace(old_link)

                new_link_map = {
                    "id_unidades_links": id_unidade,
                    "id_vgr_links": id_vgr_link,
                    "designador_links": designador,
                    "tipo_links": l.get("tipo"),
                    "operadora_links": l.get("operadora"),
                    "vlan_links": l.get("vlan"),
                    "ip_wan_links": l.get("ip_wan"),
                    "redundante_critico_links": l.get("redundante_critico_links", 0),
                    "ip_gateway_links": l.get("ip_gateway"),
                    "ip_mascara_links": l.get("ip_mascara"),
                    "velocidade_links": l.get("velocidade"),
                    "pppoe_user_links": l.get("pppoe_user"),
                    "pppoe_pass_links": l.get("pppoe_pass"),
                }
                link_changes = apply_partial_update(
                    cursor,
                    table="links",
                    pk_column="id_link",
                    pk_value=int(link_id),
                    old_map=old_link,
                    new_map=new_link_map,
                    encrypt_cols=_LINK_ENCRYPT_COLS,
                )
                if link_changes:
                    registrar_field_changes(
                        conn, "links", int(link_id), link_changes, operacao="UPDATE"
                    )
            else: # This is an insert operation
                if not designador:
                    return jsonify(message="Erro: Designador é obrigatório para novos links.", success=False), 400
                
                sql_insert = """
                    INSERT INTO links (id_unidades_links, id_vgr_links, designador_links, tipo_links, operadora_links, vlan_links, ip_wan_links, redundante_critico_links, ip_gateway_links, ip_mascara_links, velocidade_links, pppoe_user_links, pppoe_pass_links)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(
                    sql_insert,
                    (
                        id_unidade, id_vgr_link, designador, l.get('tipo'), l.get('operadora'),
                        l.get('vlan'), l.get('ip_wan'),
                        l.get('redundante_critico_links', 0),
                        l.get('ip_gateway'), l.get('ip_mascara'),
                        l.get('velocidade'),
                        encrypt_sensitive_db_column('pppoe_user_links', l.get('pppoe_user')),
                        encrypt_sensitive_db_column('pppoe_pass_links', l.get('pppoe_pass')),
                    ),
                )
                if id_atendimento:
                    registrar_log(conn, 'atendimentos', id_atendimento, 'Link', None, f"Adicionado: {l.get('tipo')} - {designador}", 'INSERT')
                new_link_id = cursor.lastrowid
                if new_link_id:
                    from prodesp.prodesp.admin_inventory import (
                        collect_field_changes,
                        registrar_field_changes,
                    )

                    ins_map = {
                        "id_unidades_links": id_unidade,
                        "id_vgr_links": id_vgr_link,
                        "designador_links": designador,
                        "tipo_links": l.get("tipo"),
                        "operadora_links": l.get("operadora"),
                        "vlan_links": l.get("vlan"),
                        "ip_wan_links": l.get("ip_wan"),
                        "redundante_critico_links": l.get("redundante_critico_links", 0),
                        "ip_gateway_links": l.get("ip_gateway"),
                        "ip_mascara_links": l.get("ip_mascara"),
                        "velocidade_links": l.get("velocidade"),
                        "pppoe_user_links": l.get("pppoe_user"),
                        "pppoe_pass_links": l.get("pppoe_pass"),
                    }
                    registrar_field_changes(
                        conn,
                        "links",
                        int(new_link_id),
                        collect_field_changes({}, ins_map),
                        operacao="INSERT",
                    )

        conn.commit()
        cur_list = conn.cursor(dictionary=True)
        links = _prodesp_listar_links_unidade(cur_list, id_unidade)
        _prodesp_mutations_cache_bust()
        return jsonify(
            message="Links salvos!",
            success=True,
            links=links,
        )
    except Exception as e:
        conn.rollback()
        return _prodesp_json_error(e, log=current_app.logger, action="Erro ao salvar links", entity_id=id_atendimento)
    finally:
        if cur_list is not None:
            cur_list.close()
        cursor.close()
        conn.close()


def _prodesp_format_obs_timestamp_br(val) -> str:
    """Formata timestamp de observação para DD/MM/AAAA HH:MM (relatório)."""
    if val is None or val == "":
        return ""
    if isinstance(val, datetime):
        dt = val
    elif isinstance(val, date):
        dt = datetime.combine(val, datetime.min.time())
    else:
        s = str(val).strip()
        if not s:
            return ""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                dt = datetime.strptime(s[:19], fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            return s
    return dt.strftime("%d/%m/%Y %H:%M")


def _prodesp_format_relatorio_observacoes_cell(cell) -> str:
    """GROUP_CONCAT com timestamp bruto → linhas 'DD/MM/AAAA HH:MM: texto'."""
    if cell is None:
        return ""
    try:
        import pandas as pd

        if isinstance(cell, float) and pd.isna(cell):
            return ""
    except Exception:
        pass
    text = str(cell).strip()
    if not text:
        return ""
    linhas = []
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        if ": " in line:
            ts_raw, _, obs = line.partition(": ")
            ts_fmt = _prodesp_format_obs_timestamp_br(ts_raw.strip())
            linhas.append(f"{ts_fmt}: {obs}" if obs else ts_fmt)
        else:
            linhas.append(line)
    return "\n".join(linhas)


def _prodesp_dataframe_from_sql(conn, query, params=None):
    """
    SELECT → DataFrame via cursor mysql.connector (sem pd.read_sql).
    Evita UserWarning do pandas sobre DBAPI2 não suportado oficialmente.
    """
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        if not cursor.description:
            return pd.DataFrame()
        columns = [col[0] for col in cursor.description]
        return pd.DataFrame(rows, columns=columns)
    finally:
        cursor.close()


def _prodesp_concat_relatorio_atendimentos(df_atendimentos, df_agendados):
    """Une atendimentos + somente agendados alinhando colunas/dtypes (evita FutureWarning do pandas)."""
    if df_atendimentos.empty:
        return df_agendados.copy()
    if df_agendados.empty:
        return df_atendimentos.copy()
    cols = df_atendimentos.columns.union(df_agendados.columns)
    left = df_atendimentos.reindex(columns=cols).copy()
    right = df_agendados.reindex(columns=cols).copy()
    for col in cols:
        if left[col].dtype != right[col].dtype or left[col].isna().all() or right[col].isna().all():
            left[col] = left[col].astype(object)
            right[col] = right[col].astype(object)
    return pd.concat([left, right], ignore_index=True)


from prodesp.prodesp.gestao.relatorio_tempos import (
    COL_TEMPO_ATENDIMENTO,
    COL_TEMPO_VITA,
    ETAPAS_RELATORIO_TEMPO,
    carregar_logs_substatus_map,
    carregar_motivos_map,
    metricas_atendimento_logs,
    metricas_map_por_atendimento,
)

_PRODESP_ETAPAS_RELATORIO_ANALITICO = ETAPAS_RELATORIO_TEMPO


def _prodesp_segundos_para_hms_relatorio(segundos):
    segundos = max(0, int(segundos))
    h, rem = divmod(segundos, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _prodesp_format_hora_relatorio(dt, tz_sp):
    """Início de etapa no analítico: somente hora (sem data)."""
    if not dt:
        return ""
    if hasattr(dt, "to_pydatetime"):
        dt = dt.to_pydatetime()
    if isinstance(dt, datetime) and dt.tzinfo is None:
        dt = tz_sp.localize(dt)
    elif isinstance(dt, datetime):
        dt = dt.astimezone(tz_sp)
    return dt.strftime("%H:%M:%S")


def _prodesp_inicio_primeira_etapa_log(logs_chrono, substatus_names, tz_sp):
    """Primeiro instante em que o atendimento entrou em qualquer substatus da etapa."""
    nomes = frozenset((s or "").strip() for s in substatus_names if (s or "").strip())
    if not nomes or not logs_chrono:
        return ""
    primeiro = None
    for row in logs_chrono:
        val = (row.get("valor_novo_log") or "").strip()
        if val not in nomes:
            continue
        ts = row.get("alterado_em_log")
        if not ts:
            continue
        if primeiro is None or ts < primeiro:
            primeiro = ts
    return _prodesp_format_hora_relatorio(primeiro, tz_sp) if primeiro else ""


def _prodesp_tempo_acumulado_etapa_log(logs_chrono, substatus_names, tz_sp):
    total = 0
    for nome in substatus_names:
        total += duracao_acumulada_substatus_segundos(logs_chrono, nome, tz_sp)
    return _prodesp_segundos_para_hms_relatorio(total)


def _prodesp_metricas_etapas_relatorio(df_logs, tz_sp):
    """Colunas Início/Tempo por etapa + totais a partir do log de substatus."""
    if df_logs is None or df_logs.empty:
        return pd.DataFrame()
    linhas = []
    for attendance_id, group in df_logs.groupby("id_atendimentos_log"):
        logs = group.sort_values("alterado_em_log").to_dict("records")
        row = {"id_atendimentos": attendance_id}
        row.update(metricas_atendimento_logs(logs, tz_sp))
        linhas.append(row)
    return pd.DataFrame(linhas)


def _prodesp_reordenar_colunas_relatorio_atendimentos(df):
    """Dados operacionais primeiro; tempos (total + por etapa) no final do analítico."""
    etapa_cols = []
    for label, _ in _PRODESP_ETAPAS_RELATORIO_ANALITICO:
        etapa_cols.extend([f"Início {label}", f"Tempo {label}"])

    cols_tempos_final = [COL_TEMPO_VITA, COL_TEMPO_ATENDIMENTO, *etapa_cols]

    ordem = [
        "ID VGR",
        "Data Agendamento",
        "Hora Agendamento",
        "Data Atendimento",
        "Status",
        "Substatus",
        "Motivo",
        "Contratada",
        "Observações",
        "Tck NOC",
        "Analista Gestão",
        "Analista Configuração",
        "Analista Configuração MPLS",
        "Analista Caderno de Teste",
        "Horário Início",
        "Horário Finalização",
        "Nome Unidade",
        "Hostname",
        "Endereço",
        "Número",
        "Complemento",
        "Bairro",
        "Município",
        "UF",
        "CEP",
        "Latitude",
        "Longitude",
        "Telefone Contato",
        "IP LAN 1",
        "IP LAN 2",
        "IP LAN Trânsito",
        "ID Intragov",
        "Loopback Vivo",
        "Loopback Cliente",
        "Equipamentos",
        "Links",
        *cols_tempos_final,
    ]
    existentes = [c for c in ordem if c in df.columns]
    restantes = [c for c in df.columns if c not in existentes and c != "id_atendimentos"]
    return df[existentes + restantes]


def _prodesp_format_data_agendamento_relatorio(val):
    """Data de agenda no relatório (DD/MM/AAAA), alinhado ao DataTable do dashboard."""
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, date):
        return val.strftime("%d/%m/%Y")
    parsed = pd.to_datetime(val, errors="coerce")
    if parsed is pd.NaT or pd.isna(parsed):
        return ""
    return parsed.strftime("%d/%m/%Y")


def _prodesp_sql_relatorio_fragmentos_unidade(u_alias="u"):
    """Colunas de unidade compartilhadas entre atendimentos e agendados no relatório."""
    u = u_alias
    return f"""
                CASE
                    WHEN NULLIF(TRIM({u}.acronimo_unidades), '') IS NOT NULL
                    THEN CONCAT(TRIM({u}.acronimo_unidades), ' — ', IFNULL({u}.nome_unidades, ''))
                    ELSE IFNULL({u}.nome_unidades, '')
                END AS 'Nome Unidade',
                {u}.ticket_noc_unidades AS 'Tck NOC',
                {u}.hostname_unidades AS 'Hostname',
                {u}.endereco_unidades AS 'Endereço',
                {u}.numero_unidades AS 'Número',
                {u}.complemento_unidades AS 'Complemento',
                {u}.bairro_unidades AS 'Bairro',
                {u}.municipio_unidades AS 'Município',
                {u}.estado_unidades AS 'UF',
                {u}.cep_unidades AS 'CEP',
                {u}.latitude_unidades AS 'Latitude',
                {u}.longitude_unidades AS 'Longitude',
                {u}.telefone_contato_unidades AS 'Telefone Contato',
                {u}.ip_lan_01_unidades AS 'IP LAN 1',
                {u}.mv_ip_lan_sec_unidades AS 'IP LAN SEC',
                {u}.ip_lan_transito_unidades AS 'IP LAN Trânsito',
                {u}.id_intragov_unidades AS 'ID Intragov',
                {u}.loopback_vivo_unidades AS 'Loopback Vivo',
                {u}.loopback_cliente_unidades AS 'Loopback Cliente',
                (
                    SELECT GROUP_CONCAT(
                        CONCAT(
                            'Modelo: ', IFNULL(e.modelo_equipamentos, ''),
                            ' | Serial: ', IFNULL(e.serial_equipamentos, ''),
                            ' | Versão: ', IFNULL(e.versao_equipamentos, ''),
                            ' | Desc: ', IFNULL(e.descricao_equipamentos, '')
                        ) SEPARATOR '\\n'
                    )
                    FROM equipamentos e
                    WHERE e.id_unidades_equipamentos = {u}.id_unidades
                ) AS 'Equipamentos',
                (
                    SELECT GROUP_CONCAT(
                        CONCAT(
                            'Des: ', IFNULL(l.designador_links, ''),
                            ' | Tipo: ', IFNULL(l.tipo_links, ''),
                            ' | Op: ', IFNULL(l.operadora_links, ''),
                            ' | VLAN: ', IFNULL(l.vlan_links, ''),
                            ' | Vel: ', IFNULL(l.velocidade_links, ''),
                            ' | IP: ', IFNULL(l.ip_wan_links, ''),
                            ' | Gateway: ', IFNULL(l.ip_gateway_links, ''),
                            ' | Mascara: ', IFNULL(l.ip_mascara_links, ''),
                            ' | User: ', IFNULL(l.pppoe_user_links, ''),
                            ' | Pass: ', IFNULL(l.pppoe_pass_links, '')
                        ) SEPARATOR '\\n'
                    )
                    FROM links l
                    WHERE l.id_unidades_links = {u}.id_unidades
                ) AS 'Links'
    """


def _prodesp_relatorio_aplicar_agenda_datatable(cursor, df, end_date_str):
    """
    Expõe Data/Hora Agendamento como no DataTable do dashboard (histórico as-of).
    Formata Data Atendimento (DD/MM/AAAA) após enriquecimento.
    """
    if df is None or df.empty:
        out = pd.DataFrame() if df is None else df.copy()
        if not out.empty:
            out["Data Agendamento"] = ""
            out["Hora Agendamento"] = ""
        return out

    records = df.to_dict("records")
    for r in records:
        if _prodesp_sem_id_atendimento(r.get("id_atendimentos")):
            r["id_atendimentos"] = None
        r["data_agendamento"] = r.pop("_data_agendamento_raw", None)
        r["hora_agendamento"] = _prodesp_normalizar_hora_agendamento(
            r.pop("_hora_agendamento_raw", None)
        )
        r["data_atendimentos"] = r.pop("_data_atendimento_raw", None)
        if _prodesp_valor_sql_nulo(r.get("data_atendimentos")):
            r["data_atendimentos"] = None

    try:
        end_d = datetime.strptime(str(end_date_str)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        end_d = date.today()

    _prodesp_enriquecer_agendamento_historico_asof(cursor, records, end_d)

    for r in records:
        r["Data Agendamento"] = _prodesp_format_data_agendamento_relatorio(r.get("data_agendamento"))
        fmt_row = {"hora_agendamento": r.get("hora_agendamento")}
        _prodesp_format_row_hora_agendamento(fmt_row, "hora_agendamento")
        r["Hora Agendamento"] = fmt_row.get("hora_agendamento") or ""
        raw_att = r.get("data_atendimentos")
        r["Data Atendimento"] = (
            _prodesp_format_data_agendamento_relatorio(raw_att) if raw_att else ""
        )

    out = pd.DataFrame(records)
    drop_cols = [
        "id_unidades",
        "_data_agendamento_raw",
        "_hora_agendamento_raw",
        "_data_atendimento_raw",
        "data_agendamento",
        "hora_agendamento",
        "data_agendamento_timeline",
        "data_evento",
        "data_atendimentos",
    ]
    out.drop(columns=[c for c in drop_cols if c in out.columns], inplace=True)
    return out


def _prodesp_label_periodo_relatorio(start_s, end_s):
    """Rótulo DD/MM/AAAA para título do XLSX (entrada YYYY-MM-DD ou similar)."""
    def _fmt(s):
        if not s:
            return s or ""
        raw = str(s).strip()[:10]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return raw

    return f"{_fmt(start_s)} a {_fmt(end_s)}"


def _prodesp_aplicar_layout_planilha_relatorio(ws, start_date_str, end_date_str):
    """Formata aba do relatório PRODESP (cabeçalho, bordas, larguras, filtros)."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    max_row = ws.max_row
    max_col = ws.max_column
    if max_col < 1 or max_row < 2:
        return

    header_row = 2
    data_start = 3
    last_col_letter = get_column_letter(max_col)

    thin = Side(style="thin", color="D0D5DD")
    border_all = Border(left=thin, right=thin, top=thin, bottom=thin)
    fill_title = PatternFill("solid", fgColor="1F4E79")
    fill_header = PatternFill("solid", fgColor="2E75B6")
    fill_zebra = PatternFill("solid", fgColor="F4F7FB")
    font_title = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
    font_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    font_body = Font(name="Calibri", size=10, color="1A1A1A")
    align_title = Alignment(horizontal="center", vertical="center")
    align_header = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_top_wrap = Alignment(vertical="top", wrap_text=True)
    align_center = Alignment(horizontal="center", vertical="center")
    align_top = Alignment(vertical="top")

    periodo = _prodesp_label_periodo_relatorio(start_date_str, end_date_str)
    titulo = f"PRODESP — Relatório de Atividades  |  Período: {periodo}"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
    c_title = ws.cell(row=1, column=1, value=titulo)
    c_title.font = font_title
    c_title.fill = fill_title
    c_title.alignment = align_title
    ws.row_dimensions[1].height = 28

    wrap_headers = frozenset({
        "Observações", "Equipamentos", "Links", "Endereço", "Complemento",
        "Nome Unidade", "Hostname",
    })
    center_headers = frozenset({
        "ID VGR", "Data Agendamento", "Hora Agendamento",
        "Data Atendimento", "Status", "Substatus", "Contratada", "UF", "CEP",
        "Início da Atividade", "Horário Início", "Horário Finalização", "Tempo Total Atendimento",
    })
    width_by_header = {
        "ID VGR": 11,
        "Data Agendamento": 13,
        "Hora Agendamento": 10,
        "Data Atendimento": 13,
        "Status": 14,
        "Substatus": 22,
        "Contratada": 14,
        "Início da Atividade": 12,
        "Cidade": 18,
        "Observações": 52,
        "Tck NOC": 16,
        "Analista Gestão": 18,
        "Analista Configuração": 20,
        "Analista Configuração MPLS": 22,
        "Analista Caderno de Teste": 22,
        "Horário Início": 12,
        "Horário Finalização": 14,
        "Tempo Total Atendimento": 16,
        "Nome Unidade": 28,
        "Hostname": 18,
        "Endereço": 36,
        "Número": 8,
        "Complemento": 16,
        "Bairro": 16,
        "Município": 18,
        "UF": 6,
        "CEP": 11,
        "Equipamentos": 44,
        "Links": 44,
    }

    headers = []
    for col in range(1, max_col + 1):
        val = ws.cell(row=header_row, column=col).value
        headers.append(str(val) if val is not None else "")

    for col_idx, name in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.font = font_header
        cell.fill = fill_header
        cell.border = border_all
        cell.alignment = align_header
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = width_by_header.get(name, 14)

    ws.row_dimensions[header_row].height = 32
    ws.freeze_panes = f"A{data_start}"
    ws.auto_filter.ref = f"A{header_row}:{last_col_letter}{max_row}"

    for row_idx in range(data_start, max_row + 1):
        is_zebra = (row_idx - data_start) % 2 == 1
        row_fill = fill_zebra if is_zebra else None
        max_lines = 1
        for col_idx, name in enumerate(headers, start=1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = font_body
            cell.border = border_all
            if row_fill:
                cell.fill = row_fill
            if name in wrap_headers:
                cell.alignment = align_top_wrap
                val = cell.value
                if val and isinstance(val, str):
                    max_lines = max(max_lines, val.count("\n") + 1)
            elif (
                name in center_headers
                or (name and name.startswith("Tempo "))
                or (name and name.startswith("Início "))
            ):
                cell.alignment = align_center
            else:
                cell.alignment = align_top
        ws.row_dimensions[row_idx].height = min(15 * max_lines, 120)

    ws.sheet_view.showGridLines = False
    ws.print_title_rows = f"1:{header_row}"


@prodesp_bp.route('/download_report', methods=['GET'])
@login_required
def download_report():
    """
    Gera e faz o download de um relatório de atividades (XLSX ou CSV)
    com múltiplas abas para o período de datas selecionado, ou relatório de MACs.
    """
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    file_format = request.args.get('format')

    if not all([start_date_str, end_date_str, file_format]):
        portal_flash("Parâmetros inválidos para gerar o relatório.", "danger", scope="prodesp")
        return redirect(url_for('prodesp.dashboard_atendimentos'))

    if file_format not in ['xlsx', 'csv']:
        portal_flash("Formato de arquivo inválido.", "danger", scope="prodesp")
        return redirect(url_for('prodesp.dashboard_atendimentos'))

    if not _prodesp_pode_acessar_dashboard_gestao(current_user):
        portal_flash(
            "O relatório de gestão não está disponível para o perfil Implantação.",
            "warning",
            scope="prodesp",
        )
        return redirect(url_for("prodesp.atendimentos"))

    report_conn = None

    try:
        # Conexão direta: relatório alterna SQL longo com pandas/Excel (minutos de gap).
        # No pool isso devolve conexão stale ou segura slot ocioso até wait_timeout.
        report_conn = get_db_connection_long_running()
        try:
            report_conn.ping(reconnect=True, attempts=2, delay=1)
        except Exception:
            pass
        cols_unidade = _prodesp_sql_relatorio_fragmentos_unidade("u")

        from prodesp.prodesp.gestao.relatorio_observacoes import (
            carregar_observacoes_map,
            carregar_substatus_historico_map,
            date_range_exclusive,
            observacoes_linha_relatorio,
        )
        from prodesp.prodesp.gestao.relatorio_tempos import carregar_motivos_map

        rep_start, rep_end_excl = _prodesp_sql_date_range(start_date_str, end_date_str)
        obs_start, obs_end_ex = date_range_exclusive(start_date_str, end_date_str)

        # Query 1: Atendimentos e Unidades (Principal) — observações em lote após SELECT
        query_atendimentos = f"""
            SELECT 
                a.id_atendimentos,
                u.id_unidades,
                u.id_vgr_unidades AS 'ID VGR',
                u.data_agendamento_unidades AS _data_agendamento_raw,
                u.hora_agendamento_unidades AS _hora_agendamento_raw,
                a.data_atendimentos AS _data_atendimento_raw,
                a.status_atendimentos AS 'Status',
                a.substatus_atendimentos AS 'Substatus',
                a.contratada_atendimentos AS 'Contratada',
                a.analista_atuante_atendimentos AS 'Analista Gestão',
                a.analista_configuracao_atendimentos AS 'Analista Configuração',
                a.analista_mpls_atendimentos AS 'Analista Configuração MPLS',
                a.analista_caderno_teste_atendimentos AS 'Analista Caderno de Teste',
                CAST(a.horario_inicio_atendimentos AS CHAR) AS 'Horário Início',
                CAST(a.horario_finalizacao_atendimentos AS CHAR) AS 'Horário Finalização',
                {cols_unidade}
            FROM atendimentos a
            JOIN unidades u ON a.id_unidades_atendimentos = u.id_unidades
            WHERE a.data_atendimentos >= %s AND a.data_atendimentos < %s
            ORDER BY a.data_atendimentos DESC
        """

        query_agendados = f"""
            SELECT
                NULL AS id_atendimentos,
                u.id_unidades,
                u.id_vgr_unidades AS 'ID VGR',
                u.data_agendamento_unidades AS _data_agendamento_raw,
                u.hora_agendamento_unidades AS _hora_agendamento_raw,
                NULL AS _data_atendimento_raw,
                'Agendado' AS 'Status',
                'Sem atendimento iniciado' AS 'Substatus',
                u.contratada_planejada_unidades AS 'Contratada',
                NULL AS 'Analista Gestão',
                NULL AS 'Analista Configuração',
                NULL AS 'Analista Configuração MPLS',
                NULL AS 'Analista Caderno de Teste',
                NULL AS 'Horário Início',
                NULL AS 'Horário Finalização',
                {cols_unidade}
            FROM unidades u
            WHERE u.data_agendamento_unidades IS NOT NULL
              AND u.data_agendamento_unidades >= %s AND u.data_agendamento_unidades < %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM atendimentos a2
                  WHERE a2.id_unidades_atendimentos = u.id_unidades
                    AND a2.data_atendimentos >= u.data_agendamento_unidades
              )
            ORDER BY u.data_agendamento_unidades DESC, u.hora_agendamento_unidades DESC
        """

        dataframes = {}
        df_atendimentos = _prodesp_dataframe_from_sql(
            report_conn,
            query_atendimentos,
            (rep_start, rep_end_excl),
        )
        df_agendados = _prodesp_dataframe_from_sql(
            report_conn,
            query_agendados,
            (rep_start, rep_end_excl),
        )
        dataframes["Atendimentos"] = _prodesp_concat_relatorio_atendimentos(
            df_atendimentos, df_agendados
        )

        cursor_obs = report_conn.cursor(dictionary=True)
        try:
            por_att, por_u = carregar_observacoes_map(cursor_obs, obs_start, obs_end_ex)
            ids_att = [
                int(x)
                for x in dataframes["Atendimentos"].get("id_atendimentos", []).dropna().unique()
            ]
            por_sub = carregar_substatus_historico_map(cursor_obs, ids_att)
            motivos_map = carregar_motivos_map(cursor_obs, ids_att)
        finally:
            cursor_obs.close()
        if not dataframes["Atendimentos"].empty:
            dataframes["Atendimentos"]["Observações"] = dataframes["Atendimentos"].apply(
                lambda r: observacoes_linha_relatorio(r, por_att, por_u, por_sub),
                axis=1,
            )
            dataframes["Atendimentos"]["Motivo"] = dataframes["Atendimentos"].apply(
                lambda r: motivos_map.get(int(r["id_atendimentos"]), "")
                if pd.notna(r.get("id_atendimentos"))
                else "",
                axis=1,
            )

        cursor_agenda = report_conn.cursor(dictionary=True)
        try:
            dataframes["Atendimentos"] = _prodesp_relatorio_aplicar_agenda_datatable(
                cursor_agenda, dataframes["Atendimentos"], end_date_str
            )
        finally:
            cursor_agenda.close()

        if 'Observações' in dataframes['Atendimentos'].columns:
            dataframes['Atendimentos']['Observações'] = dataframes['Atendimentos']['Observações'].apply(
                _prodesp_format_relatorio_observacoes_cell
            )
        if 'Telefone Contato' in dataframes['Atendimentos'].columns:
            dataframes['Atendimentos']['Telefone Contato'] = dataframes['Atendimentos']['Telefone Contato'].apply(
                decrypt_export_telefone_cell
            )
        if 'Links' in dataframes['Atendimentos'].columns:
            dataframes['Atendimentos']['Links'] = dataframes['Atendimentos']['Links'].apply(
                decrypt_export_links_cell
            )

        # --- Métricas de tempo por etapa (log de substatus + fim do atendimento) ---
        tz_report = pytz.timezone('America/Sao_Paulo')
        ids_metricas = [
            int(x)
            for x in dataframes["Atendimentos"].get("id_atendimentos", []).dropna().unique()
        ]
        cursor_met = report_conn.cursor(dictionary=True)
        try:
            from prodesp.prodesp.gestao.relatorio_tempos import carregar_logs_status_map

            logs_map = carregar_logs_substatus_map(cursor_met, ids_metricas)
            status_map = carregar_logs_status_map(cursor_met, ids_metricas)
        finally:
            cursor_met.close()

        metas_por_att = {}
        for _, r in dataframes["Atendimentos"].iterrows():
            id_att = r.get("id_atendimentos")
            if pd.isna(id_att):
                continue
            metas_por_att[int(id_att)] = {
                "data_atendimentos": r.get("_data_atendimento_raw"),
                "horario_finalizacao_atendimentos": r.get("Horário Finalização"),
                "status_atendimentos": r.get("Status"),
            }
        metricas_map = metricas_map_por_atendimento(
            logs_map,
            tz_report,
            status_logs_por_att=status_map,
            metas_por_att=metas_por_att,
        )
        if metricas_map:
            df_metricas = pd.DataFrame(
                [{"id_atendimentos": k, **v} for k, v in metricas_map.items()]
            )
            dataframes["Atendimentos"] = pd.merge(
                dataframes["Atendimentos"],
                df_metricas,
                on="id_atendimentos",
                how="left",
            )
        for label, _ in _PRODESP_ETAPAS_RELATORIO_ANALITICO:
            col_inicio = f"Início {label}"
            col_tempo = f"Tempo {label}"
            if col_inicio not in dataframes['Atendimentos'].columns:
                dataframes['Atendimentos'][col_inicio] = ""
            else:
                dataframes['Atendimentos'][col_inicio] = (
                    dataframes['Atendimentos'][col_inicio].fillna("")
                )
            if col_tempo not in dataframes['Atendimentos'].columns:
                dataframes['Atendimentos'][col_tempo] = "00:00:00"
            else:
                dataframes['Atendimentos'][col_tempo] = (
                    dataframes['Atendimentos'][col_tempo].fillna("00:00:00")
                )
        for col_total in (COL_TEMPO_VITA, COL_TEMPO_ATENDIMENTO):
            if col_total not in dataframes['Atendimentos'].columns:
                dataframes['Atendimentos'][col_total] = "00:00:00"
            else:
                dataframes['Atendimentos'][col_total] = (
                    dataframes['Atendimentos'][col_total].fillna("00:00:00")
                )

        if 'id_atendimentos' in dataframes['Atendimentos'].columns:
            dataframes['Atendimentos'].drop(columns=['id_atendimentos'], inplace=True)

        dataframes['Atendimentos'] = _prodesp_reordenar_colunas_relatorio_atendimentos(
            dataframes['Atendimentos']
        )

        # Auditoria (falha no log não bloqueia o download)
        try:
            registrar_log(
                report_conn,
                "relatorio_download",
                0,
                None,
                None,
                f"Download Relatório Completo {start_date_str} a {end_date_str} ({file_format})",
                "UPDATE",
            )
            report_conn.commit()
        except Exception as log_exc:
            current_app.logger.warning(
                "prodesp - log download relatório não gravado: %s", log_exc
            )
            try:
                report_conn.rollback()
            except Exception:
                pass

        # Gerar o arquivo
        output = io.BytesIO()
        filename = f"relatorio_prodesp_{start_date_str.replace('/', '-')}_a_{end_date_str.replace('/', '-')}.{file_format}"
        mimetype = ''

        if file_format == 'xlsx':
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                for nome_aba, df in dataframes.items():
                    df.to_excel(writer, sheet_name=nome_aba, index=False, startrow=1)
                    _prodesp_aplicar_layout_planilha_relatorio(
                        writer.sheets[nome_aba],
                        start_date_str,
                        end_date_str,
                    )
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif file_format == 'csv':
            dataframes['Atendimentos'].to_csv(output, index=False, encoding='utf-8-sig', sep=';')
            mimetype = 'text/csv'

        output.seek(0)

        # 3. Enviar o arquivo para o usuário
        return send_file(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        current_app.logger.error(f"prodesp - ERRO AO GERAR RELATÓRIO: {e}", exc_info=True)
        portal_flash("ERRO: Não foi possível gerar o relatório. Tente novamente ou contate o suporte.", "danger", scope="prodesp")
        return redirect(url_for('prodesp.dashboard_atendimentos'))

    finally:
        if report_conn and report_conn.is_connected():
            report_conn.close()

# =================================================================================
# ROTAS CSV MANAGER (PRODESP)
# =================================================================================

@prodesp_bp.route('/api/csv/gerar')
@login_required
def export_csv():
    if not _prodesp_pode_ver_menu_gestao(current_user):
        return _prodesp_negar_api_menu_gestao()
    # Gera um modelo CSV com as colunas esperadas
    df = pd.DataFrame(columns=['id_vgr', 'data_agendamento', 'hora_agendamento', 'contratada', 'field', 'contato_field'])
    
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, sep=';')
    buffer.seek(0)
    
    return Response(
        buffer.getvalue(),
        mimetype='text/csv',
        headers=Headers([('Content-Disposition', 'attachment; filename=modelo_prodesp.csv')])
    )

@prodesp_bp.route('/api/csv/register', methods=['POST'])
@login_required
def import_csv():
    if not _prodesp_pode_ver_menu_gestao(current_user):
        return _prodesp_negar_api_menu_gestao()
    bloqueado, retry_after = _prodesp_csv_agendamento_rate_limited(current_user)
    if bloqueado:
        return jsonify(
            success=False,
            msg=f"Aguarde {retry_after}s antes de enviar outro CSV de agendamento.",
        ), 429
    json_data = request.json or {}
    keys = json_data.get('keys', [])
    body = json_data.get('body', [])
    rejeitadas_previa_csv = parse_rejeitadas_previa_payload(json_data.get('rejeitadas_previa'))
    
    if not body:
        return jsonify({'msg': 'Nenhum dado encontrado no arquivo.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        tz_sp = pytz.timezone('America/Sao_Paulo')
        hoje_sp = datetime.now(tz_sp).date()

        import_result = processar_importacao_agendamento_csv(
            conn,
            cursor,
            body,
            hoje_sp,
            user_re=getattr(current_user, 're_user', '') or '',
            user_nome=getattr(current_user, 'nome_user', '') or '',
            normalize_hora_fn=normalize_hora_agendamento_db,
            horas_equivalent_fn=horas_agendamento_equivalent,
            format_hora_input_fn=format_hora_agendamento_input,
            time_from_value_fn=_prodesp_time_from_value,
            mensagem_bloqueio_concluido_fn=_prodesp_mensagem_bloqueio_agenda_unidade_concluida,
        )
        updated_count = import_result.updated_count
        errors = import_result.errors
        sucessos_csv = import_result.sucessos
        repetidos_csv = import_result.repetidos
        erros_csv = import_result.erros
        
        conn.commit()
        _prodesp_mutations_cache_bust()
        _prodesp_csv_agendamento_registrar_upload(current_user)

        relatorio_email = AgendamentoCsvRelatorio(
            sucessos=sucessos_csv,
            repetidos=repetidos_csv,
            erros=erros_csv,
            rejeitadas_previa=rejeitadas_previa_csv,
            usuario_upload=getattr(current_user, 'nome_user', '') or '',
            total_linhas_arquivo=len(body) + len(rejeitadas_previa_csv),
        )

        app_obj = current_app._get_current_object()

        def _enviar_email_agendamento_csv():
            with app_obj.app_context():
                try:
                    send_agendamento_csv_report(relatorio_email)
                except Exception:
                    app_obj.logger.warning(
                        "prodesp - falha ao enviar e-mail do CSV de agendamento (background)",
                        exc_info=True,
                    )

        threading.Thread(
            target=_enviar_email_agendamento_csv,
            name="prodesp-csv-agendamento-email",
            daemon=True,
        ).start()

        msg = build_resumo_from_relatorio(relatorio_email)
        payload = {
            'msg': msg,
            'success': len(erros_csv) == 0,
            'resumo': {
                'sucesso': len(sucessos_csv),
                'repetidos': len(repetidos_csv),
                'erros': len(erros_csv),
                'rejeitadas_previa': len(rejeitadas_previa_csv),
                'atualizados': updated_count,
            },
            'erros_export': [
                _prodesp_csv_linha_export_dict(e)
                for e in erros_csv
            ],
            'rejeitadas_previa_export': [
                _prodesp_csv_linha_export_dict(e)
                for e in rejeitadas_previa_csv
            ],
        }
        if erros_csv or rejeitadas_previa_csv:
            return jsonify(payload), 207 if erros_csv else 200

        return jsonify(payload), 200

    except Exception as e:
        conn.rollback()
        current_app.logger.exception("prodesp - erro crítico processamento agendamentos")
        return jsonify({'msg': 'Erro crítico no processamento. Tente novamente ou contate o suporte.'}), 500
    finally:
        cursor.close()
        conn.close()

@prodesp_bp.route('/dados_em_massa_import')
@login_required
def dados_em_massa_import_page():
    """Renderiza a página para importação em massa via CSV."""
    if not _prodesp_pode_ver_menu_gestao(current_user):
        portal_flash("Esta área não está disponível para o perfil Implantação.", "warning", scope="prodesp")
        return redirect(url_for("prodesp.atendimentos"))
    return render_template('prodesp_dados_em_massa_csv.html')

@prodesp_bp.route('/api/dadosemmassa_csv/template')
@login_required
def export_dados_em_massa_csv_template():
    """Gera o modelo de CSV para importação em massa com os campos solicitados."""
    columns = [
        'id_vgr_unidades', 'id_intragov_unidades', 'nome_unidades', 'endereco_unidades',
        'numero_unidades', 'bairro_unidades', 'municipio_unidades', 'estado_unidades',
        'complemento_unidades', 'cep_unidades', 'latitude_unidades', 'longitude_unidades',
        'ip_lan_unidades', 'loopback_vivo_unidades', 'loopback_cliente_unidades', 'loopback_on_bgp_unidades',
        'designador_links', 'tipo_links', 'operadora_links', 'ip_wan_links', 'ip_gateway_links', 'ip_mascara_links', 'vlan_links', 'velocidade_links',
        'serial_equipamentos', 'modelo_equipamentos'
    ]
    df = pd.DataFrame(columns=columns)
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, sep=';')
    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype='text/csv',
        headers=Headers([('Content-Disposition', 'attachment; filename=modelo_importacao_prodesp.csv')])
    )

@prodesp_bp.route('/api/dadosemmassa_csv/register', methods=['POST'])
@login_required
def dados_em_massa_register_csv():
    """Processa a inserção/atualização em massa de Unidades, Links e Equipamentos."""
    json_data = request.json or {}
    body = json_data.get('body', [])
    if not body:
        return jsonify({'msg': 'Nenhum dado encontrado.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    processed_count = 0
    errors = []
    
    try:
        for row in body:
            vgr = str(row.get('id_vgr_unidades', '')).strip()
            if not vgr: continue
            try:
                # 1. Upsert Unidade
                unit_fields = {
                    'id_vgr_unidades': vgr, 'id_intragov_unidades': row.get('id_intragov_unidades'),
                    'nome_unidades': row.get('nome_unidades'), 'endereco_unidades': row.get('endereco_unidades'),
                    'numero_unidades': row.get('numero_unidades'), 'bairro_unidades': row.get('bairro_unidades'),
                    'municipio_unidades': row.get('municipio_unidades'), 'estado_unidades': row.get('estado_unidades'),
                    'complemento_unidades': row.get('complemento_unidades'), 'cep_unidades': row.get('cep_unidades'),
                    'latitude_unidades': row.get('latitude_unidades') or None, 'longitude_unidades': row.get('longitude_unidades') or None,
                    'ip_lan_01_unidades': row.get('ip_lan_01_unidades'), 'mv_ip_lan_sec_unidades': row.get('mv_ip_lan_sec_unidades'),
                    'loopback_vivo_unidades': row.get('loopback_vivo_unidades'),
                    'loopback_cliente_unidades': row.get('loopback_cliente_unidades'), 'loopback_on_bgp_unidades': row.get('loopback_on_bgp_unidades')
                }
                cols = ", ".join([f"`{k}`" for k in unit_fields.keys()])
                placeholders = ", ".join(["%s"] * len(unit_fields)) # type: ignore
                updates = ", ".join([f"`{k}` = IF(VALUES(`{k}`) IS NULL OR VALUES(`{k}`) = '', `{k}`, VALUES(`{k}`))" for k in unit_fields.keys() if k != 'id_vgr_unidades']) # type: ignore
                sql_unit = f"INSERT INTO unidades ({cols}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}"
                cursor.execute(sql_unit, list(unit_fields.values()))
                
                cursor.execute("SELECT id_unidades FROM unidades WHERE id_vgr_unidades = %s", (vgr,))
                res_unit = cursor.fetchone()
                if not res_unit:
                    errors.append(f"VGR {vgr}: Erro ao recuperar ID após salvamento.")
                    continue
                id_unidade = res_unit['id_unidades']
                
                # 2. Upsert Link
                designador = str(row.get('designador_links', '')).strip()
                if designador:
                    link_fields = {
                        'id_unidades_links': id_unidade, 'id_vgr_links': vgr, 'designador_links': designador,
                        'tipo_links': row.get('tipo_links'), 'operadora_links': row.get('operadora_links'),
                        'ip_wan_links': row.get('ip_wan_links'), 'ip_gateway_links': row.get('ip_gateway_links'),
                        'ip_mascara_links': row.get('ip_mascara_links'), 'vlan_links': row.get('vlan_links'),
                        'velocidade_links': row.get('velocidade_links')
                    } # type: ignore
                    l_cols, l_place = ", ".join([f"`{k}`" for k in link_fields.keys()]), ", ".join(["%s"] * len(link_fields)) # type: ignore
                    l_upd = ", ".join([f"`{k}` = IF(VALUES(`{k}`) IS NULL OR VALUES(`{k}`) = '', `{k}`, VALUES(`{k}`))" for k in link_fields.keys() if k not in ['id_unidades_links', 'designador_links']]) # type: ignore
                    cursor.execute(f"INSERT INTO links ({l_cols}) VALUES ({l_place}) ON DUPLICATE KEY UPDATE {l_upd}", list(link_fields.values()))

                # 3. Upsert Equipamento
                serial = str(row.get('serial_equipamentos', '')).strip()
                if serial:
                    eq_fields = {'id_unidades_equipamentos': id_unidade, 'serial_equipamentos': serial, 'modelo_equipamentos': row.get('modelo_equipamentos')}
                    e_cols, e_place = ", ".join([f"`{k}`" for k in eq_fields.keys()]), ", ".join(["%s"] * len(eq_fields))
                    e_upd = ", ".join([f"`{k}` = IF(VALUES(`{k}`) IS NULL OR VALUES(`{k}`) = '', `{k}`, VALUES(`{k}`))" for k in eq_fields.keys() if k != 'serial_equipamentos']) # type: ignore
                    cursor.execute(f"INSERT INTO equipamentos ({e_cols}) VALUES ({e_place}) ON DUPLICATE KEY UPDATE {e_upd}", list(eq_fields.values())) # type: ignore

                processed_count += 1
            except Exception as e:
                current_app.logger.warning("prodesp - erro massa unidades VGR %s: %s", vgr, e)
                errors.append(f"VGR {vgr}: Erro ao processar o registro.")
        conn.commit()
        _prodesp_mutations_cache_bust()
        status_code = 207 if errors else 200
        return jsonify({'msg': f'Processado: {processed_count} registros.', 'errors': errors}), status_code
    except Exception as e:
        conn.rollback()
        current_app.logger.exception("prodesp - erro crítico massa unidades")
        return jsonify({'msg': 'Erro crítico no processamento. Tente novamente ou contate o suporte.'}), 500
    finally:
        cursor.close(); conn.close()

# ─────────────────────────────────────────────
# CADERNO DE TESTE FGT (coleta SSH + geração .xlsm)
# ─────────────────────────────────────────────


def _caderno_atendimento_indisponivel(row, user):
    """Admin ignora status concluído; demais perfis não acessam atendimento encerrado."""
    if _prodesp_is_admin(user):
        return None
    if _prodesp_status_concluido(row.get("status_atendimentos")):
        return jsonify(success=False, message="Atendimento não disponível."), 404
    return None


@prodesp_bp.route("/api/atendimentos/<int:id_atendimento>/caderno/coletar-logs", methods=["POST"])
@login_required
def api_caderno_coletar_logs(id_atendimento):
    from .prodesp.caderno.caderno_teste_service import executar_coleta, pode_acionar_caderno

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id_atendimentos, substatus_atendimentos,
                   analista_caderno_teste_atendimentos, status_atendimentos
            FROM atendimentos WHERE id_atendimentos = %s
            """,
            (id_atendimento,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Atendimento não encontrado."), 404
        bloqueio = _caderno_atendimento_indisponivel(row, current_user)
        if bloqueio:
            return bloqueio

        ok_perm, msg_perm = pode_acionar_caderno(
            current_user, row, is_admin=_prodesp_is_admin(current_user)
        )
        if not ok_perm:
            return jsonify(success=False, message=msg_perm), 403

        result = executar_coleta(cursor, conn, id_atendimento)
        return jsonify(success=result.get("ok", False), **{k: v for k, v in result.items() if k != "ok"}), (
            200 if result.get("ok") else 400
        )
    except Exception as exc:
        return _prodesp_json_error(
            exc, log=current_app.logger, action="coleta caderno", entity_id=id_atendimento
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/atendimentos/<int:id_atendimento>/certificados/exportar", methods=["POST"])
@login_required
def api_certificados_exportar(id_atendimento):
    from .prodesp.caderno.certificado_export_service import (
        exportar_certificados_atendimento,
        pode_exportar_certificado,
    )

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id_atendimentos, substatus_atendimentos, status_atendimentos
            FROM atendimentos WHERE id_atendimentos = %s
            """,
            (id_atendimento,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Atendimento não encontrado."), 404
        bloqueio = _caderno_atendimento_indisponivel(row, current_user)
        if bloqueio:
            return bloqueio

        ok_perm, msg_perm = pode_exportar_certificado(
            current_user, is_admin=_prodesp_is_admin(current_user)
        )
        if not ok_perm:
            return jsonify(success=False, message=msg_perm), 403

        result = exportar_certificados_atendimento(cursor, conn, id_atendimento)
        return jsonify(success=result.get("ok", False), **{k: v for k, v in result.items() if k != "ok"}), (
            200 if result.get("ok") else 400
        )
    except Exception as exc:
        return _prodesp_json_error(
            exc, log=current_app.logger, action="exportação certificado", entity_id=id_atendimento
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/atendimentos/<int:id_atendimento>/caderno/gerar", methods=["POST"])
@login_required
def api_caderno_gerar(id_atendimento):
    from .prodesp.caderno.caderno_teste_service import executar_geracao, pode_acionar_caderno, validar_questionario_obrigatorio

    data = request.get_json(silent=True) or {}
    status_testes = data.get("status_testes")
    if status_testes is not None and not isinstance(status_testes, dict):
        return jsonify(success=False, message="Status de testes inválido."), 400
    questionario = {
        "dhcp_server": (data.get("dhcp_server") or "").strip(),
        "dhcp_relay": (data.get("dhcp_relay") or "").strip(),
        "vlan": (data.get("vlan") or "").strip(),
        "multi_ip_lan": (data.get("multi_ip_lan") or "").strip(),
        "voip_tipo": (data.get("voip_tipo") or "").strip(),
        "voip_nome": (data.get("voip_nome") or "").strip(),
        "voip_telefone": (data.get("voip_telefone") or "").strip(),
        "executor_cliente": (data.get("executor_cliente") or "").strip(),
        "status_testes": status_testes if isinstance(status_testes, dict) else {},
    }
    ok_q, msg_q = validar_questionario_obrigatorio(questionario)
    if not ok_q:
        return jsonify(success=False, message=msg_q), 400
    voip_tipo = (data.get("voip_tipo") or "").strip().upper()
    if voip_tipo in ("CPE", "FGT"):
        if not (data.get("voip_nome") or "").strip():
            return jsonify(success=False, message="VOIP — Nome do colaborador é obrigatório quando VOIP é CPE ou FGT."), 400
        if not (data.get("voip_telefone") or "").strip():
            return jsonify(success=False, message="VOIP — Telefone fixo é obrigatório quando VOIP é CPE ou FGT."), 400
    portal_bbl_ok_raw = (data.get("portal_banda_larga_ok") or "SIM").strip().upper()
    portal_banda_larga_ok = portal_bbl_ok_raw != "NÃO"

    imagem_esaq = (data.get("imagem_esaq") or "").strip()
    imagem_erro_bbl = (data.get("imagem_erro_bbl") or "").strip()
    imagem_speedtest = (data.get("imagem_speedtest") or "").strip()

    if portal_banda_larga_ok:
        if not imagem_esaq:
            return jsonify(success=False, message="Imagem ESAQ obrigatória."), 400
        if len(imagem_esaq) > 8_000_000:
            return jsonify(success=False, message="Imagem ESAQ excede o tamanho permitido."), 400
    else:
        if not imagem_erro_bbl or not imagem_speedtest:
            return (
                jsonify(
                    success=False,
                    message=(
                        "Com Portal Banda Larga indisponível, informe a evidência de erro "
                        "e a evidência de velocidade no Speedtest."
                    ),
                ),
                400,
            )
        for label, img in (
            ("erro Brasil Banda Larga", imagem_erro_bbl),
            ("Speedtest", imagem_speedtest),
        ):
            if len(img) > 8_000_000:
                return jsonify(
                    success=False,
                    message=f"Imagem de {label} excede o tamanho permitido.",
                ), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    db_released = False
    try:
        cursor.execute(
            """
            SELECT id_atendimentos, substatus_atendimentos,
                   analista_caderno_teste_atendimentos, status_atendimentos
            FROM atendimentos WHERE id_atendimentos = %s
            """,
            (id_atendimento,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Atendimento não encontrado."), 404
        bloqueio = _caderno_atendimento_indisponivel(row, current_user)
        if bloqueio:
            return bloqueio

        ok_perm, msg_perm = pode_acionar_caderno(
            current_user, row, is_admin=_prodesp_is_admin(current_user)
        )
        if not ok_perm:
            return jsonify(success=False, message=msg_perm), 403

        executor_vivo = (
            (row.get("analista_caderno_teste_atendimentos") or "").strip()
            or (getattr(current_user, "nome_user", None) or "").strip()
        )
        result = executar_geracao(
            cursor,
            conn,
            id_atendimento,
            questionario=questionario,
            imagem_esaq_b64=imagem_esaq,
            portal_banda_larga_ok=portal_banda_larga_ok,
            imagem_erro_bbl_b64=imagem_erro_bbl,
            imagem_speedtest_b64=imagem_speedtest,
            executor_vivo=executor_vivo,
            conn_factory=get_db_connection,
            release_db_before_generate=True,
        )
        db_released = bool(result.get("db_released"))
        if result.get("ok") and result.get("filename"):
            result["download_url"] = url_for(
                "prodesp.api_caderno_download",
                id_atendimento=id_atendimento,
                file=result["filename"],
            )
        return jsonify(success=result.get("ok", False), **{k: v for k, v in result.items() if k not in ("ok", "db_released")}), (
            200 if result.get("ok") else 400
        )
    except Exception as exc:
        return _prodesp_json_error(
            exc, log=current_app.logger, action="gerar caderno", entity_id=id_atendimento
        )
    finally:
        if not db_released:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass


@prodesp_bp.route("/api/atendimentos/<int:id_atendimento>/caderno/carimbo-texto", methods=["GET"])
@login_required
def api_caderno_carimbo_texto(id_atendimento):
    from .prodesp.caderno.caderno_teste_service import obter_texto_carimbo_para_atendimento, pode_acionar_caderno

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id_atendimentos, substatus_atendimentos,
                   analista_caderno_teste_atendimentos, status_atendimentos
            FROM atendimentos WHERE id_atendimentos = %s
            """,
            (id_atendimento,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Atendimento não encontrado."), 404
        bloqueio = _caderno_atendimento_indisponivel(row, current_user)
        if bloqueio:
            return bloqueio

        ok_perm, msg_perm = pode_acionar_caderno(
            current_user, row, is_admin=_prodesp_is_admin(current_user)
        )
        if not ok_perm:
            return jsonify(success=False, message=msg_perm), 403

        result = obter_texto_carimbo_para_atendimento(cursor, id_atendimento)
        return jsonify(success=result.get("ok", False), **{k: v for k, v in result.items() if k != "ok"}), (
            200 if result.get("ok") else 400
        )
    except Exception as exc:
        return _prodesp_json_error(
            exc, log=current_app.logger, action="carimbo texto", entity_id=id_atendimento
        )
    finally:
        cursor.close()
        conn.close()


@prodesp_bp.route("/api/atendimentos/<int:id_atendimento>/caderno/download")
@login_required
def api_caderno_download(id_atendimento):
    from .prodesp.caderno.caderno_teste_service import (
        caminhos_download_caderno,
        carregar_contexto_atendimento,
        ler_bytes_arquivo_caderno,
        mimetype_caderno,
        pode_acionar_caderno,
    )

    filename = (request.args.get("file") or "").strip()
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return jsonify(success=False, message="Arquivo inválido."), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id_atendimentos, substatus_atendimentos,
                   analista_caderno_teste_atendimentos, status_atendimentos
            FROM atendimentos WHERE id_atendimentos = %s
            """,
            (id_atendimento,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify(success=False, message="Atendimento não encontrado."), 404

        ok_perm, msg_perm = pode_acionar_caderno(
            current_user, row, is_admin=_prodesp_is_admin(current_user)
        )
        if not ok_perm:
            return jsonify(success=False, message=msg_perm), 403

        ctx = carregar_contexto_atendimento(cursor, id_atendimento)
        id_vgr = str((ctx or {}).get("unidade", {}).get("id_vgr_unidades") or "")
        if id_vgr and id_vgr not in filename:
            return jsonify(success=False, message="Arquivo não autorizado."), 403

        acronimo = str((ctx or {}).get("unidade", {}).get("acronimo_unidades") or "")
        log = get_logger("PRODESP")
        candidates = caminhos_download_caderno(filename, acronimo)
        local_path = candidates[0] if candidates else ""
        last_err: Exception | None = None
        found_any = False
        for candidate in candidates:
            if not os.path.isfile(candidate):
                log.debug("Download caderno: ausente em %s", candidate)
                continue
            found_any = True
            try:
                payload = ler_bytes_arquivo_caderno(candidate)
                if local_path and candidate != local_path:
                    log.info("Download caderno %s via cópia alternativa", filename)
                return send_file(
                    io.BytesIO(payload),
                    mimetype=mimetype_caderno(filename),
                    as_attachment=True,
                    download_name=filename,
                )
            except (PermissionError, OSError) as exc:
                last_err = exc
                log.warning("Download caderno bloqueado em %s: %s", candidate, type(exc).__name__)
                continue

        if not found_any:
            log.warning(
                "Download caderno %s não encontrado. Caminhos verificados: %s",
                filename,
                "; ".join(candidates),
            )
            return jsonify(
                success=False,
                message=(
                    "Caderno não encontrado no servidor. "
                    "Gere o caderno novamente; se o erro persistir, verifique se a geração concluiu sem erro."
                ),
            ), 404

        if last_err:
            log.warning("Download caderno %s indisponível (lock): %s", filename, last_err)
        return jsonify(
            success=False,
            message="Arquivo temporariamente indisponível para download. Tente novamente em alguns segundos.",
        ), 503
    finally:
        cursor.close()
        conn.close()


# Importa as rotas para que sejam registradas no blueprint
from .prodesp.blueprint import prodesp_routes
