"""Blueprint Flask do módulo VGR (`/vgr`) — multi_cliente_db."""
from __future__ import annotations

import logging
import os
import threading
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from core.portal_flash import portal_flash
from core.security.csrf import (
    csrf_token_from_request,
    ensure_csrf_token,
    validate_csrf_token,
)
from vgr.credentials.db_connection import get_vgr_db_connection
from vgr.vgr.acl import (
    ACAO_ADMIN_MODULO,
    ACAO_AGENDAR,
    ACAO_ATENDIMENTO,
    ACAO_CADASTROS,
    ACAO_SUPERVISAO,
    eh_admin,
    exige_acao,
    flags_acl,
)
from vgr.vgr.cadastros import repo_inventario as repo
from vgr.vgr.cadastros import repo_field as repo_f
from vgr.vgr.cadastros.validators import (
    apply_matriz_endereco_from_cliente,
    link_avisos,
    normalize_id_vgr_equipamento,
    parse_cliente_payload,
    parse_contratada_payload,
    parse_equipamento_payload,
    parse_field_payload,
    parse_link_payload,
    parse_unidade_payload,
)
from vgr.vgr.operacao import repo_atendimento as repo_at
from vgr.vgr.operacao import repo_agendamento as repo_ag
from vgr.vgr.operacao.agendamento_csv_import_service import (
    processar_importacao_agendamento_csv,
)
from vgr.vgr.operacao.agendamento_csv_notifier import (
    AgendamentoCsvRelatorio,
    build_resumo_from_relatorio,
    linha_export_dict,
    parse_rejeitadas_previa_payload,
    send_agendamento_csv_report,
)
from vgr.vgr.operacao.agendamento_csv_validacao import (
    CONTRATADAS_CSV_PERMITIDAS,
    TIPOS_SERVICO_CSV,
)
from vgr.vgr.operacao.catalogo_atendimento import catalogo_payload
from vgr.vgr.operacao.catalogo_agendamento import (
    SUGESTAO_POR_STATUS_ATENDIMENTO,
    catalogo_payload as catalogo_agendamento_payload,
)
from vgr.vgr.operacao.catalogo_atendimento import is_status_final
from vgr.vgr.operacao.validators_atendimento import (
    VGR_AGUARDA_EXTERNO,
    is_transicao_gestao_para_fila_config,
    parse_atendimento_payload,
)
from vgr.vgr.operacao.validators_agendamento import parse_agendamento_payload
from vgr.vgr.gestao import repo_gestao
from vgr.vgr.gestao.gestao_kpis import linhas_tabela, parse_periodo, resumo_periodo_payload
from vgr.vgr.gestao.relatorio_atividades import gerar_csv, gerar_xlsx, nome_arquivo

log = logging.getLogger("VGR")

vgr_bp = Blueprint(
    "vgr",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/vgr",
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat(timespec="seconds")
    # mysql.connector devolve TIME como timedelta
    if isinstance(value, timedelta):
        total = int(value.total_seconds())
        if total < 0:
            total = 0
        hh, rem = divmod(total, 3600)
        mm, ss = divmod(rem, 60)
        return f"{hh:02d}:{mm:02d}:{ss:02d}"
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _dt_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    data = _json_safe(rows)
    n = len(data)
    return {
        "success": True,
        "data": data,
        "recordsTotal": n,
        "recordsFiltered": n,
    }


def _api_error(message: str, status: int = 500):
    return jsonify(success=False, message=message), status


def _actor() -> tuple[str | None, str | None]:
    re_u = getattr(current_user, "re_user", None) or None
    nome = getattr(current_user, "nome_user", None) or getattr(
        current_user, "nome", None
    )
    return (str(re_u)[:16] if re_u else None, str(nome)[:120] if nome else None)


@vgr_bp.before_request
def _vgr_enforce_projeto_acesso():
    """SEC-004: exige acesso ao projeto VGR (card ou admin/supervisão)."""
    from login.portal_project_access import PROJETO_VGR, usuario_tem_acesso_modulo

    if request.endpoint and str(request.endpoint).endswith(".static"):
        return None
    if request.path.startswith(f"{vgr_bp.url_prefix or ''}/static"):
        return None
    if not current_user.is_authenticated:
        return None
    if usuario_tem_acesso_modulo(current_user, PROJETO_VGR):
        return None
    msg = "Acesso negado ao módulo VGR."
    if request.is_json or (
        request.accept_mimetypes.best_match(["application/json", "text/html"])
        == "application/json"
    ):
        return jsonify(success=False, message=msg), 403
    portal_flash(msg, "warning", scope="login")
    return redirect(url_for("login.pos_login"))


@vgr_bp.before_request
def _vgr_csrf_mutations():
    """CSRF em POST/PUT/PATCH/DELETE do módulo (APIs e forms)."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    if request.endpoint and str(request.endpoint).endswith(".static"):
        return None
    if request.path.startswith(f"{vgr_bp.url_prefix or ''}/static"):
        return None
    ensure_csrf_token()
    if validate_csrf_token(csrf_token_from_request()):
        return None
    return (
        jsonify(
            success=False,
            message="Token CSRF inválido ou ausente. Recarregue a página.",
        ),
        403,
    )


@vgr_bp.context_processor
def _vgr_inject_acl():
    """Flags D6 para esconder itens de menu; enforcement real é server-side."""
    if not current_user.is_authenticated:
        return {"vgr_acl": flags_acl(None)}
    return {"vgr_acl": flags_acl(current_user)}


# ---------------------------------------------------------------------------
# Páginas shell
# ---------------------------------------------------------------------------


@vgr_bp.route("/")
@login_required
def homepage():
    return redirect(url_for("vgr.clientes_page"))


@vgr_bp.route("/clientes")
@login_required
def clientes_page():
    return render_template("clientes.html")


@vgr_bp.route("/clientes/<int:id_cliente>")
@login_required
def cliente_detalhe_page(id_cliente: int):
    try:
        cliente = repo.get_cliente(id_cliente)
    except Exception:
        log.exception("Falha ao carregar cliente id=%s", id_cliente)
        portal_flash("Erro ao carregar cliente.", "danger", scope="vgr")
        return redirect(url_for("vgr.clientes_page"))
    if not cliente:
        portal_flash("Cliente não encontrado.", "warning", scope="vgr")
        return redirect(url_for("vgr.clientes_page"))
    return render_template("cliente_detalhe.html", cliente=_json_safe(cliente))


@vgr_bp.route("/unidades")
@login_required
def unidades_page():
    return render_template("unidades.html")


@vgr_bp.route("/fields")
@login_required
def fields_page():
    return render_template("fields.html")


@vgr_bp.route("/unidades/<int:id_unidade>")
@login_required
def unidade_detalhe_page(id_unidade: int):
    try:
        unidade = repo.get_unidade(id_unidade)
    except Exception:
        log.exception("Falha ao carregar unidade id=%s", id_unidade)
        portal_flash("Erro ao carregar unidade.", "danger", scope="vgr")
        return redirect(url_for("vgr.unidades_page"))
    if not unidade:
        portal_flash("Unidade não encontrada.", "warning", scope="vgr")
        return redirect(url_for("vgr.unidades_page"))
    sdwan_ativos = 0
    try:
        sdwan_ativos = repo.count_equipamentos_sdwan(id_unidade)
    except Exception:
        log.exception("count_equipamentos_sdwan id=%s", id_unidade)
    return render_template(
        "unidade_detalhe.html",
        unidade=_json_safe(unidade),
        sdwan_ativos=sdwan_ativos,
    )


@vgr_bp.route("/atendimentos")
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def atendimentos_page():
    re_u, nome = _actor()
    return render_template(
        "atendimentos.html",
        modo="operacao",
        vgr_actor={"re": re_u, "nome": nome},
    )

# ---------------------------------------------------------------------------
# Gestão de atendimentos (padrão dashboard PRODESP): período + KPIs + relatório
# ---------------------------------------------------------------------------

VGR_GESTAO_REFRESH_SEC = 90


def _vgr_hoje_sp() -> date:
    """Data de hoje no fuso de São Paulo (mesma referência do filtro da UI)."""
    try:
        import pytz

        return datetime.now(pytz.timezone("America/Sao_Paulo")).date()
    except Exception:
        return date.today()


@vgr_bp.route("/gestao/atendimentos")
@login_required
@exige_acao(ACAO_SUPERVISAO)
def gestao_atendimentos_page():
    hoje = _vgr_hoje_sp()
    re_u, nome = _actor()
    return render_template(
        "gestao_atendimentos.html",
        modo="gestao",
        vgr_actor={"re": re_u, "nome": nome},
        start_date=hoje,
        end_date=hoje,
        vgr_gestao_refresh_sec=VGR_GESTAO_REFRESH_SEC,
    )


@vgr_bp.route("/api/gestao/atendimentos", methods=["GET"])
@login_required
@exige_acao(ACAO_SUPERVISAO)
def api_gestao_atendimentos():
    """Linhas do período (DataTable) + KPIs no mesmo payload — cards e tabela
    sempre do mesmo conjunto (padrão /prodesp/api/dashboard_data)."""
    try:
        start, end = parse_periodo(
            request.args.get("start_date"),
            request.args.get("end_date"),
            hoje=_vgr_hoje_sp(),
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    try:
        rows = repo_gestao.list_linhas_periodo(start, end)
        payload = _dt_payload(linhas_tabela(rows, start, end))
        resumo = resumo_periodo_payload(rows, start, end)
        resumo["server_time"] = datetime.now().isoformat(timespec="seconds")
        payload["resumo"] = _json_safe(resumo)
        return jsonify(payload)
    except Exception:
        log.exception("api_gestao_atendimentos %s a %s", start, end)
        return _api_error("Falha ao carregar atendimentos do período.")


@vgr_bp.route("/gestao/atendimentos/relatorio", methods=["GET"])
@login_required
@exige_acao(ACAO_SUPERVISAO)
def gestao_atendimentos_relatorio():
    """Relatório de Atividades do período (XLSX com abas ou CSV `;` UTF-8 BOM)."""
    file_format = (request.args.get("format") or "").strip().lower()
    if file_format not in ("xlsx", "csv"):
        portal_flash("Formato de arquivo inválido.", "danger", scope="vgr")
        return redirect(url_for("vgr.gestao_atendimentos_page"))
    try:
        start, end = parse_periodo(
            request.args.get("start_date"),
            request.args.get("end_date"),
            hoje=_vgr_hoje_sp(),
        )
    except ValueError as exc:
        portal_flash(str(exc), "danger", scope="vgr")
        return redirect(url_for("vgr.gestao_atendimentos_page"))

    try:
        rows = repo_gestao.list_linhas_periodo(start, end)
        if file_format == "csv":
            conteudo = gerar_csv(rows, start, end)
            mimetype = "text/csv; charset=utf-8"
        else:
            conteudo = gerar_xlsx(
                rows,
                repo_gestao.list_transicoes_periodo(start, end),
                resumo_periodo_payload(rows, start, end),
                start,
                end,
            )
            mimetype = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    except Exception:
        log.exception("gestao_atendimentos_relatorio %s a %s (%s)", start, end, file_format)
        portal_flash("Falha ao gerar o relatório. Tente novamente.", "danger", scope="vgr")
        return redirect(url_for("vgr.gestao_atendimentos_page"))

    re_u, nome = _actor()
    log.info(
        "vgr - download relatório atividades %s a %s (%s) por %s",
        start,
        end,
        file_format,
        nome or re_u,
    )
    return Response(
        conteudo,
        mimetype=mimetype,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{nome_arquivo(start, end, file_format)}"'
            ),
            "Cache-Control": "no-store",
        },
    )
    

@vgr_bp.route("/agendamentos")
@login_required
@exige_acao(ACAO_AGENDAR)
def agendamentos_page():
    return render_template("agendamentos.html", modo="operacao")


@vgr_bp.route("/gestao/agendamentos")
@login_required
@exige_acao(ACAO_SUPERVISAO)
def gestao_agendamentos_page():
    return render_template("agendamentos.html", modo="gestao")


@vgr_bp.route("/supervisao")
@login_required
@exige_acao(ACAO_SUPERVISAO)
def supervisao_page():
    return render_template("supervisao.html")


@vgr_bp.route("/admin")
@login_required
@exige_acao(ACAO_ADMIN_MODULO)
def admin_page():
    return render_template("shell.html", titulo="Admin do módulo", nav="admin")


# ---------------------------------------------------------------------------
# APIs DataTables (client-side — padrão PortalDt / admin PRODESP)
# ---------------------------------------------------------------------------


@vgr_bp.route("/api/clientes", methods=["GET"])
@login_required
def api_clientes():
    try:
        return jsonify(_dt_payload(repo.list_clientes()))
    except Exception:
        log.exception("api_clientes")
        return _api_error("Falha ao listar clientes.")


@vgr_bp.route("/api/clientes", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_clientes_create():
    raw = request.get_json(silent=True) or {}
    try:
        data = parse_cliente_payload(raw, partial=False)
        data.setdefault("ativo", 1)
        cnpj = data.get("cnpj_cliente")
        if cnpj and repo.find_cliente_id_by_cnpj(cnpj):
            return _api_error("Já existe cliente com este CNPJ.", 409)
        new_id = repo.create_cliente(data)
        row = repo.get_cliente(new_id)
        return jsonify(success=True, message="Cliente criado.", data=_json_safe(row)), 201
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_clientes_create")
        return _api_error("Falha ao criar cliente.")


@vgr_bp.route("/api/clientes/opcoes", methods=["GET"])
@login_required
def api_clientes_opcoes():
    try:
        return jsonify(success=True, data=_json_safe(repo.list_clientes_opcoes(apenas_ativos=True)))
    except Exception:
        log.exception("api_clientes_opcoes")
        return _api_error("Falha ao listar opções de clientes.")


@vgr_bp.route("/api/clientes/<int:id_cliente>", methods=["GET"])
@login_required
def api_cliente_get(id_cliente: int):
    try:
        row = repo.get_cliente(id_cliente)
        if not row:
            return _api_error("Cliente não encontrado.", 404)
        return jsonify(success=True, data=_json_safe(row))
    except Exception:
        log.exception("api_cliente_get id=%s", id_cliente)
        return _api_error("Falha ao carregar cliente.")


@vgr_bp.route("/api/clientes/<int:id_cliente>", methods=["PUT"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_cliente_update(id_cliente: int):
    raw = request.get_json(silent=True) or {}
    try:
        if not repo.get_cliente(id_cliente):
            return _api_error("Cliente não encontrado.", 404)
        data = parse_cliente_payload(raw, partial=False)
        cnpj = data.get("cnpj_cliente")
        if cnpj:
            other = repo.find_cliente_id_by_cnpj(cnpj, exclude_id=id_cliente)
            if other:
                return _api_error("Já existe cliente com este CNPJ.", 409)
        if not repo.update_cliente(id_cliente, data):
            return _api_error("Nenhuma alteração aplicada.", 400)
        row = repo.get_cliente(id_cliente)
        return jsonify(success=True, message="Cliente atualizado.", data=_json_safe(row))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_cliente_update id=%s", id_cliente)
        return _api_error("Falha ao atualizar cliente.")


@vgr_bp.route("/api/clientes/<int:id_cliente>/desativar", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_cliente_desativar(id_cliente: int):
    try:
        if not repo.get_cliente(id_cliente):
            return _api_error("Cliente não encontrado.", 404)
        repo.set_cliente_ativo(id_cliente, 0)
        return jsonify(success=True, message="Cliente desativado.")
    except Exception:
        log.exception("api_cliente_desativar id=%s", id_cliente)
        return _api_error("Falha ao desativar cliente.")


@vgr_bp.route("/api/clientes/<int:id_cliente>/reativar", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_cliente_reativar(id_cliente: int):
    try:
        if not repo.get_cliente(id_cliente):
            return _api_error("Cliente não encontrado.", 404)
        repo.set_cliente_ativo(id_cliente, 1)
        return jsonify(success=True, message="Cliente reativado.")
    except Exception:
        log.exception("api_cliente_reativar id=%s", id_cliente)
        return _api_error("Falha ao reativar cliente.")


@vgr_bp.route("/api/unidades", methods=["GET"])
@login_required
def api_unidades():
    try:
        return jsonify(_dt_payload(repo.list_unidades()))
    except Exception:
        log.exception("api_unidades")
        return _api_error("Falha ao listar unidades.")


@vgr_bp.route("/api/unidades", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_unidades_create():
    raw = request.get_json(silent=True) or {}
    try:
        data = parse_unidade_payload(raw, partial=False)
        data.setdefault("ativo", 1)
        cliente = repo.get_cliente(data["id_cliente"])
        if not cliente:
            return _api_error("Cliente não encontrado.", 404)
        data = apply_matriz_endereco_from_cliente(data, cliente)
        new_id = repo.create_unidade(data)
        row = repo.get_unidade(new_id)
        return jsonify(success=True, message="Unidade criada.", data=_json_safe(row)), 201
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_unidades_create")
        return _api_error("Falha ao criar unidade.")

@vgr_bp.route("/api/enriquecer-endereco", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_enriquecer_endereco():
    """
    Completar endereço (core.utils.endereco_enriquecimento): só SUGERE
    bairro/CEP/cidade/UF/lat-long; nada é gravado aqui (save da unidade grava).
    CSRF validado no before_request do blueprint.
    """
    data = request.get_json(silent=True) or {}
    try:
        from core.utils.endereco_enriquecimento import enriquecer_endereco_portal

        return jsonify(enriquecer_endereco_portal(data))
    except Exception:
        log.exception("api_enriquecer_endereco")
        return (
            jsonify(success=False, message="Falha ao completar endereço.", updates={}),
            500,
        )


@vgr_bp.route("/api/unidades/by-id-vgr/<path:id_vgr>", methods=["GET"])
@login_required
def api_unidade_by_id_vgr(id_vgr: str):
    """Resolve a unidade pelo ID VGR gravado em equipamentos.id_vgr (prioriza equipamentos ativos)."""
    try:
        vgr_id = normalize_id_vgr_equipamento(id_vgr) or ""
    except ValueError as exc:
        return _api_error(str(exc), 400)
    if not vgr_id:
        return _api_error("Informe o ID VGR.", 400)
    try:
        # Busca estrita em equipamentos, priorizando ativos via repositório
        id_unidade = repo.find_unidade_id_by_equipamento_id_vgr(vgr_id)
        
        if not id_unidade:
            return _api_error(
                "Nenhuma unidade encontrada para o ID VGR informado (busca em equipamentos).", 404
            )
            
        row = repo.get_unidade(id_unidade)
        if not row:
            return _api_error("Unidade não encontrada.", 404)
            
        return jsonify(success=True, data=_json_safe(row))
    except Exception:
        log.exception("api_unidade_by_id_vgr id_vgr=%s", vgr_id)
        return _api_error("Falha ao buscar unidade pelo ID VGR.")

@vgr_bp.route("/api/unidades/<int:id_unidade>", methods=["GET"])
@login_required
def api_unidade_get(id_unidade: int):
    try:
        row = repo.get_unidade(id_unidade)
        if not row:
            return _api_error("Unidade não encontrada.", 404)
        return jsonify(success=True, data=_json_safe(row))
    except Exception:
        log.exception("api_unidade_get id=%s", id_unidade)
        return _api_error("Falha ao carregar unidade.")


@vgr_bp.route("/api/unidades/<int:id_unidade>", methods=["PUT"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_unidade_update(id_unidade: int):
    raw = request.get_json(silent=True) or {}
    try:
        if not repo.get_unidade(id_unidade):
            return _api_error("Unidade não encontrada.", 404)
        data = parse_unidade_payload(raw, partial=False)
        cliente = repo.get_cliente(data["id_cliente"])
        if not cliente:
            return _api_error("Cliente não encontrado.", 404)
        data = apply_matriz_endereco_from_cliente(data, cliente)
        if not repo.update_unidade(id_unidade, data):
            return _api_error("Nenhuma alteração aplicada.", 400)
        row = repo.get_unidade(id_unidade)
        return jsonify(success=True, message="Unidade atualizada.", data=_json_safe(row))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_unidade_update id=%s", id_unidade)
        return _api_error("Falha ao atualizar unidade.")


@vgr_bp.route("/api/unidades/<int:id_unidade>/desativar", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_unidade_desativar(id_unidade: int):
    try:
        if not repo.get_unidade(id_unidade):
            return _api_error("Unidade não encontrada.", 404)
        repo.set_unidade_ativo(id_unidade, 0)
        return jsonify(success=True, message="Unidade desativada.")
    except Exception:
        log.exception("api_unidade_desativar id=%s", id_unidade)
        return _api_error("Falha ao desativar unidade.")


@vgr_bp.route("/api/unidades/<int:id_unidade>/reativar", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_unidade_reativar(id_unidade: int):
    try:
        if not repo.get_unidade(id_unidade):
            return _api_error("Unidade não encontrada.", 404)
        repo.set_unidade_ativo(id_unidade, 1)
        return jsonify(success=True, message="Unidade reativada.")
    except Exception:
        log.exception("api_unidade_reativar id=%s", id_unidade)
        return _api_error("Falha ao reativar unidade.")


@vgr_bp.route("/api/clientes/<int:id_cliente>/unidades", methods=["GET"])
@login_required
def api_cliente_unidades(id_cliente: int):
    try:
        if not repo.get_cliente(id_cliente):
            return _api_error("Cliente não encontrado.", 404)
        return jsonify(_dt_payload(repo.list_unidades(id_cliente=id_cliente)))
    except Exception:
        log.exception("api_cliente_unidades id=%s", id_cliente)
        return _api_error("Falha ao listar unidades do cliente.")


@vgr_bp.route("/api/clientes/<int:id_cliente>/agendamentos", methods=["GET"])
@login_required
def api_cliente_agendamentos(id_cliente: int):
    try:
        if not repo.get_cliente(id_cliente):
            return _api_error("Cliente não encontrado.", 404)
        return jsonify(_dt_payload(repo.list_agendamentos_by_cliente(id_cliente)))
    except Exception:
        log.exception("api_cliente_agendamentos id=%s", id_cliente)
        return _api_error("Falha ao listar agendamentos do cliente.")


@vgr_bp.route("/api/clientes/<int:id_cliente>/atendimentos", methods=["GET"])
@login_required
def api_cliente_atendimentos(id_cliente: int):
    try:
        if not repo.get_cliente(id_cliente):
            return _api_error("Cliente não encontrado.", 404)
        return jsonify(_dt_payload(repo.list_atendimentos_by_cliente(id_cliente)))
    except Exception:
        log.exception("api_cliente_atendimentos id=%s", id_cliente)
        return _api_error("Falha ao listar atendimentos do cliente.")


@vgr_bp.route("/api/unidades/<int:id_unidade>/agendamentos", methods=["GET"])
@login_required
def api_unidade_agendamentos(id_unidade: int):
    try:
        if not repo.get_unidade(id_unidade):
            return _api_error("Unidade não encontrada.", 404)
        return jsonify(_dt_payload(repo.list_agendamentos_by_unidade(id_unidade)))
    except Exception:
        log.exception("api_unidade_agendamentos id=%s", id_unidade)
        return _api_error("Falha ao listar agendamentos da unidade.")


@vgr_bp.route("/api/unidades/<int:id_unidade>/atendimentos", methods=["GET"])
@login_required
def api_unidade_atendimentos(id_unidade: int):
    try:
        if not repo.get_unidade(id_unidade):
            return _api_error("Unidade não encontrada.", 404)
        return jsonify(_dt_payload(repo.list_atendimentos_by_unidade(id_unidade)))
    except Exception:
        log.exception("api_unidade_atendimentos id=%s", id_unidade)
        return _api_error("Falha ao listar atendimentos da unidade.")


@vgr_bp.route("/api/unidades/<int:id_unidade>/equipamentos", methods=["GET"])
@login_required
def api_unidade_equipamentos(id_unidade: int):
    try:
        if not repo.get_unidade(id_unidade):
            return _api_error("Unidade não encontrada.", 404)
        return jsonify(_dt_payload(repo.list_equipamentos_by_unidade(id_unidade)))
    except Exception:
        log.exception("api_unidade_equipamentos id=%s", id_unidade)
        return _api_error("Falha ao listar equipamentos da unidade.")


@vgr_bp.route("/api/unidades/<int:id_unidade>/equipamentos", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_unidade_equipamentos_create(id_unidade: int):
    raw = request.get_json(silent=True) or {}
    raw = dict(raw)
    raw["id_unidade"] = id_unidade
    try:
        if not repo.get_unidade(id_unidade):
            return _api_error("Unidade não encontrada.", 404)
        data = parse_equipamento_payload(raw, partial=False)
        data.setdefault("ativo", 1)
        data["id_vgr"] = normalize_id_vgr_equipamento(raw.get("id_vgr"))
        if data.get("serial") and repo.find_equipamento_id_by_serial(data["serial"]):
            return _api_error("Já existe equipamento com este serial.", 409)
        if data.get("fortcloud_key"):
            data["_set_fortcloud"] = True
        new_id = repo.create_equipamento(data)
        row = repo.get_equipamento(new_id)
        return (
            jsonify(
                success=True,
                message="Equipamento criado.",
                data=_json_safe(row),
            ),
            201,
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_unidade_equipamentos_create id=%s", id_unidade)
        return _api_error("Falha ao criar equipamento.")


@vgr_bp.route("/api/equipamentos/<int:id_equipamento>", methods=["GET"])
@login_required
def api_equipamento_get(id_equipamento: int):
    try:
        row = repo.get_equipamento(id_equipamento)
        if not row:
            return _api_error("Equipamento não encontrado.", 404)
        return jsonify(success=True, data=_json_safe(row))
    except Exception:
        log.exception("api_equipamento_get id=%s", id_equipamento)
        return _api_error("Falha ao carregar equipamento.")


@vgr_bp.route("/api/equipamentos/<int:id_equipamento>", methods=["PUT"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_equipamento_update(id_equipamento: int):
    raw = request.get_json(silent=True) or {}
    try:
        existing = repo.get_equipamento(id_equipamento)
        if not existing:
            return _api_error("Equipamento não encontrado.", 404)
        raw = dict(raw)
        raw.setdefault("id_unidade", existing["id_unidade"])
        data = parse_equipamento_payload(raw, partial=False)
        if "id_vgr" in raw:
            data["id_vgr"] = normalize_id_vgr_equipamento(raw.get("id_vgr"))
        else:
            data["id_vgr"] = existing.get("id_vgr")
        if int(data["id_unidade"]) != int(existing["id_unidade"]):
            if not repo.get_unidade(data["id_unidade"]):
                return _api_error("Unidade não encontrada.", 404)
        if data.get("serial"):
            other = repo.find_equipamento_id_by_serial(
                data["serial"],
                exclude_id=id_equipamento,
            )
            if other:
                return _api_error("Já existe equipamento com este serial.", 409)
        if not repo.update_equipamento(id_equipamento, data):
            return _api_error("Nenhuma alteração aplicada.", 400)
        row = repo.get_equipamento(id_equipamento)
        return jsonify(
            success=True,
            message="Equipamento atualizado.",
            data=_json_safe(row),
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_equipamento_update id=%s", id_equipamento)
        return _api_error("Falha ao atualizar equipamento.")


@vgr_bp.route("/api/equipamentos/<int:id_equipamento>/desativar", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_equipamento_desativar(id_equipamento: int):
    try:
        if not repo.get_equipamento(id_equipamento):
            return _api_error("Equipamento não encontrado.", 404)
        repo.set_equipamento_ativo(id_equipamento, 0)
        return jsonify(success=True, message="Equipamento desativado.")
    except Exception:
        log.exception("api_equipamento_desativar id=%s", id_equipamento)
        return _api_error("Falha ao desativar equipamento.")


@vgr_bp.route("/api/equipamentos/<int:id_equipamento>/reativar", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_equipamento_reativar(id_equipamento: int):
    try:
        if not repo.get_equipamento(id_equipamento):
            return _api_error("Equipamento não encontrado.", 404)
        repo.set_equipamento_ativo(id_equipamento, 1)
        return jsonify(success=True, message="Equipamento reativado.")
    except Exception:
        log.exception("api_equipamento_reativar id=%s", id_equipamento)
        return _api_error("Falha ao reativar equipamento.")


@vgr_bp.route("/api/unidades/<int:id_unidade>/links", methods=["GET"])
@login_required
def api_unidade_links(id_unidade: int):
    try:
        if not repo.get_unidade(id_unidade):
            return _api_error("Unidade não encontrada.", 404)
        return jsonify(_dt_payload(repo.list_links_by_unidade(id_unidade)))
    except Exception:
        log.exception("api_unidade_links id=%s", id_unidade)
        return _api_error("Falha ao listar links da unidade.")


def _link_uniqueness_error(data: dict, *, exclude_id: int | None = None) -> str | None:
    """Controles de unicidade de link (IP host, id_vgr_link, designador+operadora)."""
    from core.utils.network import canonicalize_ipv4

    ip = canonicalize_ipv4(data.get("ip_address"))
    if ip:
        other = repo.find_link_id_by_ip_host(ip, exclude_id=exclude_id)
        if other:
            return f"Já existe link com este IP (id_link={other})."
    id_vgr_link = data.get("id_vgr_link")
    if id_vgr_link:
        other = repo.find_link_id_by_id_vgr_link(id_vgr_link, exclude_id=exclude_id)
        if other:
            return f"Já existe link com este ID VGR (id_link={other})."
    designador = data.get("designador")
    if designador:
        other = repo.find_link_id_by_designador_operadora(
            designador, data.get("operadora"), exclude_id=exclude_id
        )
        if other:
            return (
                f"Já existe link com este designador na mesma operadora "
                f"(id_link={other})."
            )
    return None


@vgr_bp.route("/api/unidades/<int:id_unidade>/links", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_unidade_links_create(id_unidade: int):
    raw = request.get_json(silent=True) or {}
    raw = dict(raw)
    raw["id_unidade"] = id_unidade
    try:
        if not repo.get_unidade(id_unidade):
            return _api_error("Unidade não encontrada.", 404)
        data = parse_link_payload(raw, partial=False)
        id_eq = data.get("id_equipamento")
        if data.get("tipo_link") == "WAN":
            eq = repo.get_equipamento(id_eq) if id_eq else None
            if not eq or int(eq["id_unidade"]) != int(id_unidade):
                return _api_error("Equipamento inválido para esta unidade.", 400)
        elif id_eq is not None:
            data["id_equipamento"] = None
        conflict = _link_uniqueness_error(data)
        if conflict:
            return _api_error(conflict, 409)
        new_id = repo.create_link(data)
        row = repo.get_link(new_id)
        return (
            jsonify(
                success=True,
                message="Link criado.",
                data=_json_safe(row),
                avisos=link_avisos(data),
            ),
            201,
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_unidade_links_create id=%s", id_unidade)
        return _api_error("Falha ao criar link.")


@vgr_bp.route("/api/links/check-uniqueness", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_links_check_uniqueness():
    """Pré-check UX (padrão PRODESP) — não muta dados."""
    raw = request.get_json(silent=True) or {}
    try:
        exclude_id = raw.get("exclude_id") or raw.get("id_link")
        exclude = int(exclude_id) if exclude_id not in (None, "") else None
        # Valida formato sem exigir modo completo (partial-friendly).
        data = parse_link_payload(
            {
                "id_unidade": raw.get("id_unidade") or 1,
                "id_equipamento": raw.get("id_equipamento") or 1,
                "tipo_link": raw.get("tipo_link") or "WAN",
                "modo_conexao": raw.get("modo_conexao"),
                "ip_address": raw.get("ip_address"),
                "mascara": raw.get("mascara"),
                "gateway": raw.get("gateway"),
                "subrede": raw.get("subrede"),
                "range_start": raw.get("range_start"),
                "range_end": raw.get("range_end"),
                "vlan": raw.get("vlan"),
                "id_vgr_link": raw.get("id_vgr_link"),
                "designador": raw.get("designador"),
                "operadora": raw.get("operadora"),
                "operadora_outros": raw.get("operadora_outros"),
                "velocidade": raw.get("velocidade"),
            },
            partial=True,
        )
        conflict = _link_uniqueness_error(data, exclude_id=exclude)
        if conflict:
            return jsonify(success=False, unique=False, message=conflict), 409
        return jsonify(success=True, unique=True, message="OK", avisos=link_avisos(data))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_links_check_uniqueness")
        return _api_error("Falha ao verificar unicidade.")


@vgr_bp.route("/api/links/<int:id_link>", methods=["GET"])
@login_required
def api_link_get(id_link: int):
    try:
        row = repo.get_link(id_link)
        if not row:
            return _api_error("Link não encontrado.", 404)
        return jsonify(success=True, data=_json_safe(row))
    except Exception:
        log.exception("api_link_get id=%s", id_link)
        return _api_error("Falha ao carregar link.")


@vgr_bp.route("/api/links/<int:id_link>", methods=["PUT"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_link_update(id_link: int):
    raw = request.get_json(silent=True) or {}
    try:
        existing = repo.get_link(id_link)
        if not existing:
            return _api_error("Link não encontrado.", 404)
        raw = dict(raw)
        raw.setdefault("id_unidade", existing["id_unidade"])
        # Campos que nem toda tela envia (ex.: edição inline do atendimento):
        # sem isto o UPDATE gravava NULL e apagava ordem/subrede/ranges.
        for keep in ("ordem", "subrede", "range_start", "range_end"):
            raw.setdefault(keep, existing.get(keep))
        # PPPoE já gravado (cifrado) satisfaz a obrigatoriedade sem reenviar.
        raw["has_pppoe_user"] = existing.get("has_pppoe_user")
        raw["has_pppoe_pass"] = existing.get("has_pppoe_pass")
        data = parse_link_payload(raw, partial=False)
        id_eq = data.get("id_equipamento")
        if data.get("tipo_link") == "WAN":
            eq = repo.get_equipamento(id_eq) if id_eq else None
            if not eq or int(eq["id_unidade"]) != int(data["id_unidade"]):
                return _api_error("Equipamento inválido para esta unidade.", 400)
        else:
            data["id_equipamento"] = None
        conflict = _link_uniqueness_error(data, exclude_id=id_link)
        if conflict:
            return _api_error(conflict, 409)
        if not repo.update_link(id_link, data):
            return _api_error("Nenhuma alteração aplicada.", 400)
        row = repo.get_link(id_link)
        return jsonify(
            success=True,
            message="Link atualizado.",
            data=_json_safe(row),
            avisos=link_avisos(data),
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_link_update id=%s", id_link)
        return _api_error("Falha ao atualizar link.")


@vgr_bp.route("/api/links/<int:id_link>/desativar", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_link_desativar(id_link: int):
    try:
        if not repo.get_link(id_link):
            return _api_error("Link não encontrado.", 404)
        repo.set_link_ativo(id_link, 0)
        return jsonify(success=True, message="Link desativado.")
    except Exception:
        log.exception("api_link_desativar id=%s", id_link)
        return _api_error("Falha ao desativar link.")


@vgr_bp.route("/api/links/<int:id_link>/reativar", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_link_reativar(id_link: int):
    try:
        if not repo.get_link(id_link):
            return _api_error("Link não encontrado.", 404)
        repo.set_link_ativo(id_link, 1)
        return jsonify(success=True, message="Link reativado.")
    except Exception:
        log.exception("api_link_reativar id=%s", id_link)
        return _api_error("Falha ao reativar link.")


# ---------------------------------------------------------------------------
# Field (P10) + contratadas
# ---------------------------------------------------------------------------


@vgr_bp.route("/api/fields", methods=["GET"])
@login_required
def api_fields():
    try:
        return jsonify(_dt_payload(repo_f.list_fields()))
    except Exception:
        log.exception("api_fields")
        return _api_error("Falha ao listar Fields.")


@vgr_bp.route("/api/fields/typeahead", methods=["GET"])
@login_required
def api_fields_typeahead():
    q = (request.args.get("q") or "").strip()
    try:
        rows = repo_f.typeahead_fields(q)
        return jsonify(success=True, data=_json_safe(rows))
    except Exception:
        log.exception("api_fields_typeahead")
        return _api_error("Falha na busca de Fields.")


@vgr_bp.route("/api/fields", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_fields_create():
    raw = request.get_json(silent=True) or {}
    try:
        data = parse_field_payload(raw, partial=False)
        data.setdefault("ativo", 1)
        ids = data.get("id_contratadas") or []
        if ids and not repo_f.contratadas_existem(ids):
            return _api_error("Contratada inválida ou inativa.", 400)
        re_u, nome = _actor()
        new_id = repo_f.create_field(data, usuario_re=re_u, usuario_nome=nome)
        row = repo_f.get_field(new_id)
        return jsonify(success=True, message="Field criado.", data=_json_safe(row)), 201
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_fields_create")
        return _api_error("Falha ao criar Field.")


@vgr_bp.route("/api/fields/<int:id_field>", methods=["GET"])
@login_required
def api_field_get(id_field: int):
    try:
        row = repo_f.get_field(id_field)
        if not row:
            return _api_error("Field não encontrado.", 404)
        return jsonify(success=True, data=_json_safe(row))
    except Exception:
        log.exception("api_field_get id=%s", id_field)
        return _api_error("Falha ao carregar Field.")


@vgr_bp.route("/api/fields/<int:id_field>", methods=["PUT"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_field_update(id_field: int):
    raw = request.get_json(silent=True) or {}
    try:
        if not repo_f.get_field(id_field, decrypt_pii=False):
            return _api_error("Field não encontrado.", 404)
        data = parse_field_payload(raw, partial=False)
        ids = data.get("id_contratadas") or []
        if ids and not repo_f.contratadas_existem(ids):
            return _api_error("Contratada inválida ou inativa.", 400)
        re_u, nome = _actor()
        if not repo_f.update_field(id_field, data, usuario_re=re_u, usuario_nome=nome):
            return _api_error("Nenhuma alteração aplicada.", 400)
        row = repo_f.get_field(id_field)
        return jsonify(success=True, message="Field atualizado.", data=_json_safe(row))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_field_update id=%s", id_field)
        return _api_error("Falha ao atualizar Field.")


@vgr_bp.route("/api/fields/<int:id_field>/desativar", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_field_desativar(id_field: int):
    try:
        if not repo_f.get_field(id_field, decrypt_pii=False):
            return _api_error("Field não encontrado.", 404)
        repo_f.set_field_ativo(id_field, 0)
        return jsonify(success=True, message="Field desativado.")
    except Exception:
        log.exception("api_field_desativar id=%s", id_field)
        return _api_error("Falha ao desativar Field.")


@vgr_bp.route("/api/fields/<int:id_field>/reativar", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_field_reativar(id_field: int):
    try:
        if not repo_f.get_field(id_field, decrypt_pii=False):
            return _api_error("Field não encontrado.", 404)
        repo_f.set_field_ativo(id_field, 1)
        return jsonify(success=True, message="Field reativado.")
    except Exception:
        log.exception("api_field_reativar id=%s", id_field)
        return _api_error("Falha ao reativar Field.")


@vgr_bp.route("/api/contratadas", methods=["GET"])
@login_required
def api_contratadas():
    try:
        return jsonify(
            success=True,
            data=_json_safe(repo_f.list_contratadas(apenas_ativos=True)),
        )
    except Exception:
        log.exception("api_contratadas")
        return _api_error("Falha ao listar contratadas.")


@vgr_bp.route("/api/contratadas", methods=["POST"])
@login_required
@exige_acao(ACAO_CADASTROS)
def api_contratadas_create():
    raw = request.get_json(silent=True) or {}
    try:
        data = parse_contratada_payload(raw)
        new_id = repo_f.create_contratada(data)
        row = repo_f.get_contratada(new_id)
        return (
            jsonify(success=True, message="Contratada criada.", data=_json_safe(row)),
            201,
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_contratadas_create")
        return _api_error("Falha ao criar contratada.")


# ---------------------------------------------------------------------------
# Atendimentos (Fase 3 — P4/P6/P13)
# ---------------------------------------------------------------------------


def _validar_vinculo_agenda(
    data: dict[str, Any], *, exclude_atendimento_id: int | None = None
) -> None:
    id_ag = data.get("id_agendamento")
    if not id_ag:
        return
    ag = repo_at.get_agendamento_resumo(int(id_ag))
    if not ag or not int(ag.get("ativo") or 0):
        raise ValueError("Agendamento não encontrado ou inativo.")
    if int(ag["id_unidade"]) != int(data["id_unidade"]):
        raise ValueError("Agendamento não pertence à unidade informada.")
    other = repo_at.find_atendimento_id_by_agendamento(
        int(id_ag), exclude_id=exclude_atendimento_id
    )
    if other:
        raise ValueError("Já existe atendimento vinculado a este agendamento (1→1).")
    
VGR_OBS_TRANSICAO_MIN = 10


def _gate_bloqueios_vgr(
    data: dict[str, Any],
    existing: dict[str, Any] | None,
    raw: dict[str, Any],
) -> str | None:
    """Bloqueios de finalização/transição (espelho PRODESP). Mensagem ou None."""
    from core.utils.ticket_noc import validate_ticket_noc_format

    status = (
        data.get("status_atendimento")
        or (existing or {}).get("status_atendimento")
        or ""
    ).strip()
    sub = (
        data.get("substatus_atendimento")
        or (existing or {}).get("substatus_atendimento")
        or ""
    ).strip()
    old_status = ((existing or {}).get("status_atendimento") or "").strip()
    old_sub = ((existing or {}).get("substatus_atendimento") or "").strip()
    id_unidade = int(data.get("id_unidade") or (existing or {}).get("id_unidade") or 0)

    # 1) Status final: substatus + analista atuante
    if is_status_final(status):
        if not sub:
            return "Para status final, selecione o substatus."
        analista = (
            data.get("analista_atuante")
            or (existing or {}).get("analista_atuante")
            or ""
        ).strip()
        if not analista:
            return "Para finalizar, preencha o analista atuante."

    # 2) Concluído/Concluído: Ticket NOC + inventário mínimo (hostname, ID VGR, WAN)
    if status == "Concluído" and sub == "Concluído":
        tkt = raw["tkt_noc"] if "tkt_noc" in raw else (existing or {}).get("tkt_noc")
        err_tkt = validate_ticket_noc_format(tkt, obrigatorio=True)
        if err_tkt:
            return err_tkt
        eqs = [
            e
            for e in repo.list_equipamentos_by_unidade(id_unidade)
            if int(e.get("ativo") or 0) == 1
        ]
        if not eqs:
            return "Para concluir, cadastre ao menos um equipamento ativo na unidade."
        if not any((e.get("hostname") or "").strip() for e in eqs):
            return "Para concluir, preencha o hostname do equipamento ativo."
        if not any((e.get("id_vgr") or "").strip() for e in eqs):
            return "Para concluir, preencha o ID VGR do equipamento ativo."
        wans = [
            l
            for l in repo.list_links_by_unidade(id_unidade)
            if int(l.get("ativo") or 0) == 1 and (l.get("tipo_link") or "").strip() == "WAN"
        ]
        if not wans:
            return "Para concluir, cadastre ao menos um link WAN ativo na unidade."

    # 3) Observação de transição: Quebra (motivo) e entrada em Aguarda Cliente/Contratada
    obs_transicao = (raw.get("observacao_transicao") or "").strip()
    entrando_quebra = status == "Quebra" and old_status != "Quebra"
    entrando_espera = sub in VGR_AGUARDA_EXTERNO and old_sub != sub
    if entrando_quebra or entrando_espera:
        if len(obs_transicao) < VGR_OBS_TRANSICAO_MIN:
            alvo = (
                "o motivo da quebra"
                if entrando_quebra
                else f"a observação de «{sub}»"
            )
            return f"Informe {alvo} (mín. {VGR_OBS_TRANSICAO_MIN} caracteres)."
    elif obs_transicao and len(obs_transicao) < VGR_OBS_TRANSICAO_MIN:
        return f"Observação de transição deve ter mín. {VGR_OBS_TRANSICAO_MIN} caracteres."

    # 4) Gestão → fila de configuração: Dados Field persistidos (ou no payload, no create)
    if is_transicao_gestao_para_fila_config(old_sub, sub):
        if existing:
            fields = repo_at.list_fields_do_atendimento(int(existing["id_atendimento"]))
            ok_field = any(
                (f.get("snap_nome") or "").strip()
                and (f.get("snap_contratada_nome") or "").strip()
                for f in fields
            )
            if not ok_field:
                return (
                    "Para enviar da Gestão para a fila Aguardando, "
                    "preencha e salve os Dados Field."
                )
        else:
            snaps = raw.get("field_snaps") or {}
            if not (snaps.get("snap_nome") or "").strip() or not (
                snaps.get("snap_contratada_nome") or ""
            ).strip():
                return (
                    "Para enviar da Gestão para a fila Aguardando, "
                    "informe os Dados Field."
                )
    return None    


@vgr_bp.route("/api/atendimentos/catalogo", methods=["GET"])
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimentos_catalogo():
    return jsonify(success=True, data=catalogo_payload())


def _vgr_lista_operacao_com_concluidos() -> list[dict[str, Any]]:
    """
    Fila operacional (padrão PRODESP): lista operacional + Concluídos ativos.
    Dedup por id_atendimento; linhas sintéticas de agenda (sem id) preservadas.
    """
    base = list(repo_at.list_atendimentos_operacao() or [])
    ids_vistos: set[int] = set()
    for r in base:
        rid = r.get("id_atendimento")
        if rid not in (None, ""):
            ids_vistos.add(int(rid))

    for r in repo_at.list_atendimentos(apenas_ativos=True) or []:
        if (r.get("status_atendimento") or "").strip() != "Concluído":
            continue
        rid = r.get("id_atendimento")
        if rid in (None, "") or int(rid) in ids_vistos:
            continue
        ids_vistos.add(int(rid))
        base.append(r)
    return base


@vgr_bp.route("/api/atendimentos", methods=["GET"])
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimentos():
    try:
        # Gestão (supervisão): histórico completo, sem filtro de fila.
        if request.args.get("modo") == "gestao":
            if not flags_acl(current_user).get("pode_supervisao"):
                return _api_error("Sem permissão para visão de gestão.", 403)
            return jsonify(_dt_payload(repo_at.list_atendimentos(apenas_ativos=False)))
        # Fila operacional: ativos + Concluídos; a ordenação de prioridade
        # é calculada no client (_sort_lista), igual à fila PRODESP.
        return jsonify(_dt_payload(_vgr_lista_operacao_com_concluidos()))
    except Exception:
        log.exception("api_atendimentos")
        return _api_error("Falha ao listar atendimentos.")


@vgr_bp.route("/api/atendimentos", methods=["POST"])
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimentos_create():
    raw = request.get_json(silent=True) or {}
    try:
        data = parse_atendimento_payload(raw, partial=False)
        data.setdefault("ativo", 1)
        if not repo.get_unidade(data["id_unidade"]):
            return _api_error("Unidade não encontrada.", 404)
        _validar_vinculo_agenda(data)
        err_gate = _gate_bloqueios_vgr(data, None, raw)
        if err_gate:
            return _api_error(err_gate, 400)
        re_u, nome = _actor()
        if not data.get("analista_atuante"):
            data["analista_atuante"] = nome or re_u
        new_id = repo_at.create_atendimento(data, usuario_re=re_u, usuario_nome=nome)
        # Field informado no create (walk-in / transição direta)
        snaps = raw.get("field_snaps") or {}
        snap_nome = (snaps.get("snap_nome") or "").strip() or None
        if snap_nome:
            snap_tel = (snaps.get("snap_telefone") or "").strip() or None
            snap_cont = (snaps.get("snap_contratada_nome") or "").strip() or None
            id_field = repo_f.find_field_id_by_nome(snap_nome)
            if not id_field:
                data_f = parse_field_payload(
                    {"nome": snap_nome, "telefone": snap_tel}, partial=False
                )
                data_f.setdefault("ativo", 1)
                id_field = repo_f.create_field(
                    data_f, usuario_re=re_u, usuario_nome=nome
                )
            repo_at.create_atendimento_field_direct(
                new_id,
                id_field,
                snap_nome=snap_nome,
                snap_telefone=snap_tel,
                snap_contratada_nome=snap_cont,
            )
        # FIX (UnboundLocalError): busca o row ANTES de qualquer uso.
        row = repo_at.get_atendimento(new_id)
        if row and "tkt_noc" in raw:
            _aplicar_tkt_noc_atendimento(row, raw.get("tkt_noc"))
        obs_t = (raw.get("observacao_transicao") or "").strip()
        if obs_t:
            repo_at.append_observacao(
                new_id, obs_t, usuario_re=re_u, usuario_nome=nome
            )
        # Refetch pós-TKT/observação para devolver o estado final ao front
        row = repo_at.get_atendimento(new_id)
        return (
            jsonify(success=True, message="Atendimento criado.", data=_json_safe(row)),
            201,
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_atendimentos_create")
        return _api_error("Falha ao criar atendimento.")


@vgr_bp.route("/api/atendimentos/<int:id_atendimento>", methods=["GET"])
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimento_get(id_atendimento: int):
    try:
        row = repo_at.get_atendimento(id_atendimento)
        if not row:
            return _api_error("Atendimento não encontrado.", 404)
        return jsonify(success=True, data=_json_safe(row))
    except Exception:
        log.exception("api_atendimento_get id=%s", id_atendimento)
        return _api_error("Falha ao carregar atendimento.")


@vgr_bp.route("/api/atendimentos/<int:id_atendimento>", methods=["PUT"])
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimento_update(id_atendimento: int):
    raw = request.get_json(silent=True) or {}
    try:
        existing = repo_at.get_atendimento(id_atendimento)
        if not existing:
            return _api_error("Atendimento não encontrado.", 404)
        raw = dict(raw)
        raw.setdefault("id_unidade", existing["id_unidade"])
        data = parse_atendimento_payload(raw, partial=False)
        if int(data["id_unidade"]) != int(existing["id_unidade"]):
            if not repo.get_unidade(data["id_unidade"]):
                return _api_error("Unidade não encontrada.", 404)
        id_ag = data.get("id_agendamento", existing.get("id_agendamento"))
        if id_ag and int(id_ag or 0) != int(existing.get("id_agendamento") or 0):
            check = dict(data)
            check["id_agendamento"] = id_ag
            _validar_vinculo_agenda(check, exclude_atendimento_id=id_atendimento)
        elif id_ag:
            check = dict(data)
            check["id_agendamento"] = id_ag
            _validar_vinculo_agenda(check, exclude_atendimento_id=id_atendimento)
        err_gate = _gate_bloqueios_vgr(data, existing, raw)
        if err_gate:
            return _api_error(err_gate, 400)
        re_u, nome = _actor()
        # P0: não exige checkbox — server inicia ao sair de gestão / status final!
        if "atendimento_iniciado" not in raw:
            data.pop("atendimento_iniciado", None)
        if not data.get("analista_atuante"):
            data["analista_atuante"] = existing.get("analista_atuante") or nome or re_u
        repo_at.update_atendimento(
            id_atendimento,
            data,
            usuario_re=re_u,
            usuario_nome=nome,
            allow_troca_analista=eh_admin(current_user),
        )
        if "tkt_noc" in raw:
            _aplicar_tkt_noc_atendimento(existing, raw.get("tkt_noc"))
        obs_t = (raw.get("observacao_transicao") or "").strip()
        if obs_t:
            repo_at.append_observacao(
                id_atendimento, obs_t, usuario_re=re_u, usuario_nome=nome
            )
        row = repo_at.get_atendimento(id_atendimento)
        return jsonify(
            success=True, message="Atendimento atualizado.", data=_json_safe(row)
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_atendimento_update id=%s", id_atendimento)
        return _api_error("Falha ao atualizar atendimento.")


def _aplicar_tkt_noc_atendimento(atend: dict, tkt_raw) -> None:
    """Grava Ticket NOC em equipamentos.tkt_noc (não há coluna no atendimento)."""
    from core.utils.ticket_noc import (
        normalizar_ticket_noc,
        validate_ticket_noc_format,
    )

    id_eq = atend.get("id_equipamento_tkt")
    if not id_eq:
        if tkt_raw is None or str(tkt_raw).strip() == "":
            return
        raise ValueError(
            "Cadastre um equipamento na unidade antes de gravar o Ticket NOC."
        )
    eq = repo.get_equipamento(int(id_eq))
    if not eq or int(eq["id_unidade"]) != int(atend["id_unidade"]):
        raise ValueError("Equipamento do Ticket NOC inválido para a unidade.")
    if tkt_raw is None or str(tkt_raw).strip() == "":
        repo.update_equipamento_tkt_noc(int(id_eq), None)
        return
    err = validate_ticket_noc_format(tkt_raw)
    if err:
        raise ValueError(err)
    repo.update_equipamento_tkt_noc(int(id_eq), normalizar_ticket_noc(tkt_raw)[:64])


@vgr_bp.route(
    "/api/atendimentos/<int:id_atendimento>/observacoes", methods=["POST"]
)
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimento_observacao_append(id_atendimento: int):
    raw = request.get_json(silent=True) or {}
    try:
        if not repo_at.get_atendimento(id_atendimento):
            return _api_error("Atendimento não encontrado.", 404)
        re_u, nome = _actor()
        texto = raw.get("texto") or raw.get("observacao") or ""
        novo = repo_at.append_observacao(
            id_atendimento, texto, usuario_re=re_u, usuario_nome=nome
        )
        return jsonify(
            success=True,
            message="Observação adicionada.",
            data={
                "observacoes": novo,
                "observacoes_log": repo_at.parse_observacoes_log(novo),
            },
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_atendimento_observacao_append id=%s", id_atendimento)
        return _api_error("Falha ao adicionar observação.")


@vgr_bp.route(
    "/api/atendimentos/<int:id_atendimento>/fields", methods=["POST"]
)
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimento_field_create(id_atendimento: int):
    """Cadastra Field direto no atendimento (walk-in / sem vínculo prévio)."""
    raw = request.get_json(silent=True) or {}
    try:
        atend = repo_at.get_atendimento(id_atendimento)
        if not atend:
            return _api_error("Atendimento não encontrado.", 404)

        repo_at.ensure_fields_from_agendamento(id_atendimento)
        if repo_at.list_fields_do_atendimento(id_atendimento):
            return _api_error(
                "Já existe Field vinculado a este atendimento; use a edição.", 409
            )

        nome = (raw.get("snap_nome") or raw.get("nome") or "").strip() or None
        tel = (raw.get("snap_telefone") or raw.get("telefone") or "").strip() or None
        contratada = (
            raw.get("snap_contratada_nome") or raw.get("contratada") or ""
        ).strip() or None
        if not nome:
            return _api_error("Nome do Field é obrigatório.", 400)
        nome = nome[:128]
        if tel:
            tel = tel[:64]
        if contratada:
            contratada = contratada[:255]

        id_field = repo_f.find_field_id_by_nome(nome)
        if not id_field:
            data = parse_field_payload({"nome": nome, "telefone": tel}, partial=False)
            data.setdefault("ativo", 1)
            re_u, nome_u = _actor()
            id_field = repo_f.create_field(data, usuario_re=re_u, usuario_nome=nome_u)

        repo_at.create_atendimento_field_direct(
            id_atendimento,
            id_field,
            snap_nome=nome,
            snap_telefone=tel,
            snap_contratada_nome=contratada,
        )
        row = repo_at.get_atendimento(id_atendimento)
        return (
            jsonify(
                success=True,
                message="Field cadastrado no atendimento.",
                data=_json_safe(row),
            ),
            201,
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_atendimento_field_create id=%s", id_atendimento)
        return _api_error("Falha ao cadastrar Field no atendimento.")


@vgr_bp.route(
    "/api/atendimentos/<int:id_atendimento>/fields/<int:id_field>", methods=["PUT"]
)
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimento_field_update(id_atendimento: int, id_field: int):
    raw = request.get_json(silent=True) or {}
    try:
        atend = repo_at.get_atendimento(id_atendimento)
        if not atend:
            return _api_error("Atendimento não encontrado.", 404)
        repo_at.ensure_fields_from_agendamento(id_atendimento)
        nome = (raw.get("snap_nome") or raw.get("nome") or "").strip() or None
        tel = (raw.get("snap_telefone") or raw.get("telefone") or "").strip() or None
        contratada = (
            raw.get("snap_contratada_nome") or raw.get("contratada") or ""
        ).strip() or None
        if nome is not None:
            nome = nome[:128]
        if tel is not None:
            tel = tel[:64]
        if contratada is not None:
            contratada = contratada[:255]
        ok = repo_at.update_atendimento_field_snap(
            id_atendimento,
            id_field,
            snap_nome=nome,
            snap_telefone=tel,
            snap_contratada_nome=contratada,
        )
        if not ok:
            return _api_error(
                "Field não vinculado a este atendimento (associe no agendamento).",
                404,
            )
        row = repo_at.get_atendimento(id_atendimento)
        return jsonify(
            success=True,
            message="Dados Field atualizados.",
            data=_json_safe(row),
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception(
            "api_atendimento_field_update id=%s field=%s", id_atendimento, id_field
        )
        return _api_error("Falha ao atualizar Field do atendimento.")


@vgr_bp.route("/api/atendimentos/<int:id_atendimento>/desativar", methods=["POST"])
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimento_desativar(id_atendimento: int):
    try:
        if not repo_at.get_atendimento(id_atendimento):
            return _api_error("Atendimento não encontrado.", 404)
        repo_at.set_atendimento_ativo(id_atendimento, 0)
        return jsonify(success=True, message="Atendimento desativado.")
    except Exception:
        log.exception("api_atendimento_desativar id=%s", id_atendimento)
        return _api_error("Falha ao desativar atendimento.")


@vgr_bp.route("/api/atendimentos/<int:id_atendimento>/reativar", methods=["POST"])
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimento_reativar(id_atendimento: int):
    try:
        if not repo_at.get_atendimento(id_atendimento):
            return _api_error("Atendimento não encontrado.", 404)
        repo_at.set_atendimento_ativo(id_atendimento, 1)
        return jsonify(success=True, message="Atendimento reativado.")
    except Exception:
        log.exception("api_atendimento_reativar id=%s", id_atendimento)
        return _api_error("Falha ao reativar atendimento.")


@vgr_bp.route("/api/atendimentos/<int:id_atendimento>/sugestao-agenda", methods=["GET"])
@login_required
@exige_acao(ACAO_ATENDIMENTO)
def api_atendimento_sugestao_agenda(id_atendimento: int):
    """P11-B: sugere status de agenda a partir de final de atendimento."""
    try:
        row = repo_at.get_atendimento(id_atendimento)
        if not row:
            return _api_error("Atendimento não encontrado.", 404)
        st = row.get("status_atendimento")
        if not is_status_final(st):
            return jsonify(
                success=True,
                data={
                    "sugerir": False,
                    "message": "Sugestão só após status final do atendimento.",
                },
            )
        id_ag = row.get("id_agendamento")
        if not id_ag:
            return jsonify(
                success=True,
                data={
                    "sugerir": False,
                    "message": "Atendimento walk-in sem agendamento vinculado.",
                },
            )
        sugerido = SUGESTAO_POR_STATUS_ATENDIMENTO.get(st)
        return jsonify(
            success=True,
            data={
                "sugerir": bool(sugerido),
                "id_agendamento": id_ag,
                "status_atendimento": st,
                "status_agendamento_sugerido": sugerido,
                "message": "Confirme a sugestão na agenda (perfil AGENDAMENTO/GP/Admin).",
            },
        )
    except Exception:
        log.exception("api_atendimento_sugestao_agenda id=%s", id_atendimento)
        return _api_error("Falha ao obter sugestão de agenda.")


# ---------------------------------------------------------------------------
# Agendamentos (Fase 4)
# ---------------------------------------------------------------------------


@vgr_bp.route("/api/agendamentos/catalogo", methods=["GET"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamentos_catalogo():
    return jsonify(success=True, data=catalogo_agendamento_payload())


@vgr_bp.route("/api/agendamentos", methods=["GET"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamentos():
    try:
        apenas_ativos = (request.args.get("apenas_ativos") or "").lower() in (
            "1",
            "true",
            "yes",
        )
        if request.args.get("modo") == "gestao":
            if not flags_acl(current_user).get("pode_supervisao"):
                return _api_error("Sem permissão para visão de gestão.", 403)
            apenas_ativos = False
        return jsonify(
            _dt_payload(repo_ag.list_agendamentos(apenas_ativos=apenas_ativos))
        )
    except Exception:
        log.exception("api_agendamentos")
        return _api_error("Falha ao listar agendamentos.")


@vgr_bp.route("/api/agendamentos", methods=["POST"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamentos_create():
    raw = request.get_json(silent=True) or {}
    try:
        data = parse_agendamento_payload(raw, partial=False)
        data.setdefault("ativo", 1)
        if not repo.get_unidade(data["id_unidade"]):
            return _api_error("Unidade não encontrada.", 404)
        re_u, nome = _actor()
        new_id = repo_ag.create_agendamento(data, usuario_re=re_u, usuario_nome=nome)
        row = repo_ag.get_agendamento(new_id)
        return (
            jsonify(success=True, message="Agendamento criado.", data=_json_safe(row)),
            201,
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_agendamentos_create")
        return _api_error("Falha ao criar agendamento.")


@vgr_bp.route("/api/agendamentos/<int:id_agendamento>", methods=["GET"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamento_get(id_agendamento: int):
    try:
        row = repo_ag.get_agendamento(id_agendamento)
        if not row:
            return _api_error("Agendamento não encontrado.", 404)
        return jsonify(success=True, data=_json_safe(row))
    except Exception:
        log.exception("api_agendamento_get id=%s", id_agendamento)
        return _api_error("Falha ao carregar agendamento.")


@vgr_bp.route("/api/agendamentos/<int:id_agendamento>", methods=["PUT"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamento_update(id_agendamento: int):
    raw = request.get_json(silent=True) or {}
    try:
        existing = repo_ag.get_agendamento(id_agendamento)
        if not existing:
            return _api_error("Agendamento não encontrado.", 404)
        raw = dict(raw)
        raw.setdefault("id_unidade", existing["id_unidade"])
        data = parse_agendamento_payload(raw, partial=False)
        if not repo.get_unidade(data["id_unidade"]):
            return _api_error("Unidade não encontrada.", 404)
        re_u, nome = _actor()
        repo_ag.update_agendamento(
            id_agendamento, data, usuario_re=re_u, usuario_nome=nome
        )
        row = repo_ag.get_agendamento(id_agendamento)
        return jsonify(
            success=True, message="Agendamento atualizado.", data=_json_safe(row)
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_agendamento_update id=%s", id_agendamento)
        return _api_error("Falha ao atualizar agendamento.")


@vgr_bp.route("/api/agendamentos/<int:id_agendamento>/desativar", methods=["POST"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamento_desativar(id_agendamento: int):
    try:
        if not repo_ag.get_agendamento(id_agendamento):
            return _api_error("Agendamento não encontrado.", 404)
        repo_ag.set_agendamento_ativo(id_agendamento, 0)
        return jsonify(success=True, message="Agendamento desativado.")
    except Exception:
        log.exception("api_agendamento_desativar id=%s", id_agendamento)
        return _api_error("Falha ao desativar agendamento.")


@vgr_bp.route("/api/agendamentos/<int:id_agendamento>/reativar", methods=["POST"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamento_reativar(id_agendamento: int):
    try:
        if not repo_ag.get_agendamento(id_agendamento):
            return _api_error("Agendamento não encontrado.", 404)
        repo_ag.set_agendamento_ativo(id_agendamento, 1)
        return jsonify(success=True, message="Agendamento reativado.")
    except Exception:
        log.exception("api_agendamento_reativar id=%s", id_agendamento)
        return _api_error("Falha ao reativar agendamento.")


@vgr_bp.route("/api/agendamentos/<int:id_agendamento>/confirmar-agendado", methods=["POST"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamento_confirmar_agendado(id_agendamento: int):
    raw = request.get_json(silent=True) or {}
    try:
        confirmar = bool(raw.get("confirmar"))
        re_u, nome = _actor()
        result = repo_ag.confirmar_agendado(
            id_agendamento,
            confirmar=confirmar,
            usuario_re=re_u,
            usuario_nome=nome,
        )
        msg = "Agendado publicado."
        if result.get("created_atendimento"):
            msg += f" Atendimento #{result.get('id_atendimento')} criado."
        return jsonify(success=True, message=msg, data=_json_safe(result))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_agendamento_confirmar_agendado id=%s", id_agendamento)
        return _api_error("Falha ao confirmar Agendado.")


@vgr_bp.route("/api/agendamentos/<int:id_agendamento>/improdutivo", methods=["POST"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamento_improdutivo(id_agendamento: int):
    raw = request.get_json(silent=True) or {}
    try:
        re_u, nome = _actor()
        result = repo_ag.marcar_improdutivo(
            id_agendamento,
            usuario_re=re_u,
            usuario_nome=nome,
            observacao=(raw.get("observacao") or None),
        )
        return jsonify(
            success=True,
            message=result.get("message") or "Marcado como Improdutiva.",
            data=_json_safe(result),
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_agendamento_improdutivo id=%s", id_agendamento)
        return _api_error("Falha ao marcar Improdutiva.")


@vgr_bp.route("/api/agendamentos/<int:id_agendamento>/aplicar-sugestao", methods=["POST"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamento_aplicar_sugestao(id_agendamento: int):
    raw = request.get_json(silent=True) or {}
    try:
        status_novo = (raw.get("status_agendamento") or "").strip()
        if not status_novo:
            return _api_error("status_agendamento é obrigatório.", 400)
        if not raw.get("confirmar"):
            return _api_error("Confirmação obrigatória (P11-B).", 400)
        re_u, nome = _actor()
        result = repo_ag.aplicar_status_sugerido(
            id_agendamento,
            status_novo,
            usuario_re=re_u,
            usuario_nome=nome,
        )
        return jsonify(
            success=True,
            message="Sugestão aplicada na agenda.",
            data=_json_safe(result),
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception:
        log.exception("api_agendamento_aplicar_sugestao id=%s", id_agendamento)
        return _api_error("Falha ao aplicar sugestão.")
    
VGR_CSV_AGENDAMENTO_COLUNAS = [
    "id_vgr",
    "tipo_servico",
    "data_agendamento",
    "hora_agendamento",
    "contratada",
    "field",
    "contato_field",
]

_vgr_csv_ag_ultimo_upload: dict[Any, float] = {}


def _vgr_csv_ag_intervalo_seg() -> int:
    raw = (os.getenv("VGR_CSV_UPLOAD_MIN_INTERVAL_SEC") or "120").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 120


def _vgr_csv_ag_user_key() -> Any:
    return getattr(current_user, "id_user", None) or getattr(current_user, "re_user", None)


def _vgr_csv_ag_rate_limited() -> tuple[bool, int]:
    """Limita uploads consecutivos por usuário (evita spam de e-mail)."""
    intervalo = _vgr_csv_ag_intervalo_seg()
    uid = _vgr_csv_ag_user_key()
    if intervalo <= 0 or uid is None:
        return False, 0
    decorrido = datetime.now().timestamp() - _vgr_csv_ag_ultimo_upload.get(uid, 0.0)
    if decorrido < intervalo:
        return True, max(1, int(intervalo - decorrido))
    return False, 0


def _vgr_csv_ag_registrar_upload() -> None:
    uid = _vgr_csv_ag_user_key()
    if uid is not None:
        _vgr_csv_ag_ultimo_upload[uid] = datetime.now().timestamp()


def _vgr_csv_json(payload: dict[str, Any], status: int = 200):
    """Mantém `message` (padrão VGR) e `msg` (contrato do painel CSV PRODESP)."""
    msg = payload.get("message") or payload.get("msg") or ""
    payload["message"] = msg
    payload["msg"] = msg
    return jsonify(payload), status


@vgr_bp.route("/atendimentos/csv-agendamento")
@login_required
@exige_acao(ACAO_AGENDAR)
def csv_agendamento_page():
    # Regra fixa do CSV (agendamento_csv_validacao.CONTRATADAS_CSV_PERMITIDAS):
    # a mesma lista alimenta o texto de ajuda, a pré-validação do navegador e o
    # processamento no servidor. Contratada ausente no cadastro é criada no upload.
    return render_template(
        "csv_agendamento.html",
        vgr_csv_contratadas_permitidas=list(CONTRATADAS_CSV_PERMITIDAS),
        vgr_csv_tipos_servico=list(TIPOS_SERVICO_CSV),
        vgr_csv_colunas=VGR_CSV_AGENDAMENTO_COLUNAS,
    )

@vgr_bp.route("/api/agendamentos/csv/modelo", methods=["GET"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamentos_csv_modelo():
    # BOM: o Excel PT-BR abre acentos corretamente; separador `;` (igual PRODESP).
    conteudo = "﻿" + ";".join(VGR_CSV_AGENDAMENTO_COLUNAS) + "\r\n"
    return Response(
        conteudo,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=modelo_agendamento_vgr.csv"},
    )


@vgr_bp.route("/api/agendamentos/csv/register", methods=["POST"])
@login_required
@exige_acao(ACAO_AGENDAR)
def api_agendamentos_csv_register():
    bloqueado, retry_after = _vgr_csv_ag_rate_limited()
    if bloqueado:
        return _vgr_csv_json(
            {
                "success": False,
                "message": f"Aguarde {retry_after}s antes de enviar outro CSV de agendamento.",
            },
            429,
        )

    raw = request.get_json(silent=True) or {}
    body = raw.get("body")
    if not isinstance(body, list) or not body:
        return _vgr_csv_json(
            {"success": False, "message": "Nenhum dado encontrado no arquivo."}, 400
        )
    if len(body) > 5000:
        return _vgr_csv_json(
            {"success": False, "message": "Arquivo muito grande (máx. 5000 linhas por envio)."},
            400,
        )
    rejeitadas_previa = parse_rejeitadas_previa_payload(raw.get("rejeitadas_previa"))
    re_u, nome = _actor()

    try:
        import pytz

        hoje_sp = datetime.now(pytz.timezone("America/Sao_Paulo")).date()
    except Exception:
        hoje_sp = date.today()

    conn = None
    cur = None
    try:
        conn = get_vgr_db_connection()
        cur = conn.cursor(dictionary=True)
        # Contratadas: o serviço resolve CONTRATADAS_CSV_PERMITIDAS no banco
        # (e cadastra a ausente) na mesma transação — não pré-carregar aqui.
        resultado = processar_importacao_agendamento_csv(
            cur,
            body,
            hoje_sp,
            user_re=re_u,
            user_nome=nome,
        )
        conn.commit()
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        log.exception("api_agendamentos_csv_register")
        return _vgr_csv_json(
            {
                "success": False,
                "message": "Erro crítico no processamento. Tente novamente ou contate o suporte.",
            },
            500,
        )
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

    _vgr_csv_ag_registrar_upload()

    relatorio = AgendamentoCsvRelatorio(
        sucessos=resultado.sucessos,
        repetidos=resultado.repetidos,
        erros=resultado.erros,
        rejeitadas_previa=rejeitadas_previa,
        usuario_upload=nome or re_u or "",
        total_linhas_arquivo=len(body) + len(rejeitadas_previa),
    )

    # E-mail em background: falha de envio não desfaz o upload (já commitado).
    app_obj = current_app._get_current_object()

    def _enviar_email():
        with app_obj.app_context():
            try:
                send_agendamento_csv_report(relatorio)
            except Exception:
                log.warning("vgr - falha ao enviar e-mail do CSV de agendamento", exc_info=True)

    threading.Thread(target=_enviar_email, name="vgr-csv-agendamento-email", daemon=True).start()

    payload = {
        "success": len(resultado.erros) == 0,
        "message": build_resumo_from_relatorio(relatorio),
        "resumo": {
            "sucesso": len(resultado.sucessos),
            "repetidos": len(resultado.repetidos),
            "erros": len(resultado.erros),
            "rejeitadas_previa": len(rejeitadas_previa),
            "agendados": resultado.agendados_count,
            "atendimentos_criados": resultado.atendimentos_criados,
            "agendas_criadas": resultado.created_count,
            "atualizados": resultado.updated_count,
        },
        "erros_export": [linha_export_dict(e) for e in resultado.erros],
        "rejeitadas_previa_export": [linha_export_dict(e) for e in rejeitadas_previa],
    }
    return _vgr_csv_json(payload, 207 if resultado.erros else 200)