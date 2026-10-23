"""Monta e envia os relatórios SUPERVISORES (e-mail Graph + Teams opcional)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

import pytz

from core.reports.data_loaders import (
    carregar_analistas_disponiveis,
    carregar_fila_atual,
    carregar_fila_final,
    carregar_kpis_resumo_supervisao_dia,
    carregar_picos_do_dia,
    carregar_rows_fust,
    carregar_rows_prodesp,
)
from core.reports.email_html import (
    build_analistas_teams_card,
    build_analistas_teams_text,
    build_fila_email_html,
    build_fila_teams_card,
    build_fila_teams_text,
    build_macro_email_html,
    build_macro_teams_card,
    build_macro_teams_text,
    fatiar_analistas_teams,
)
from core.reports.env_config import (
    graph_mail_ok,
    teams_channel_email,
    teams_fila_channel_email,
    teams_fila_webhook_urls,
    teams_fust_webhook_url,
    teams_webhook_url,
)
from core.reports.fila_sem_analista import (
    aplicar_proximo_aviso,
    carregar_contagem_avisos,
    chave_fila,
    registrar_envio_avisos,
    salvar_contagem_avisos,
)
from core.reports.kpi_macro import (
    KpiMacro,
    agregar_top5_por_projeto,
    calcular_kpis_fust,
    calcular_kpis_prodesp,
    listar_atendimentos_ativos,
)
from core.reports.report_settings import (
    ENVIADO,
    ReportConfig,
    ResultadoEnvio,
    carregar_config,
    fingerprint,
    igual_ao_ultimo,
    omitido,
    registrar_envio,
)
from core.reports.teams_notify import send_macro_teams_email, send_teams_webhook

logger = logging.getLogger(__name__)
TZ_SP = pytz.timezone("America/Sao_Paulo")

TipoRelatorio = Literal["periodico", "final"]


def _enviar_email(
    subject: str,
    html_body: str,
    recipients: list[str],
    log_label: str,
    cc: list[str] | None = None,
) -> bool:
    if not recipients:
        logger.warning("supervisores - %s sem destinatários", log_label)
        return False
    if not graph_mail_ok():
        logger.warning("supervisores - %s: MS_GRAPH_* ausente", log_label)
        return False
    from prodesp.prodesp.blueprint.agendamento_csv_notifier import send_graph_html_email

    return send_graph_html_email(
        subject=subject,
        html_body=html_body,
        recipients=recipients,
        cc_recipients=cc or None,
        log_label=log_label,
        extra_attachments=None,
        include_logo=True,
    )


def _periodo_label(start_date: str, end_date: str) -> str:
    if start_date == end_date:
        return datetime.strptime(start_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    return (
        f"{datetime.strptime(start_date, '%Y-%m-%d').strftime('%d/%m/%Y')} a "
        f"{datetime.strptime(end_date, '%Y-%m-%d').strftime('%d/%m/%Y')}"
    )


def _dia_encerrado(*kpis: KpiMacro) -> bool:
    """Houve atividade e nenhum atendimento segue em aberto."""
    com_dados = [k for k in kpis if k is not None]
    if not com_dados:
        return False
    return sum(k.com_atividade for k in com_dados) > 0 and all(k.em_atendimento == 0 for k in com_dados)


def _carregar_kpis_macro(start_date: str, end_date: str) -> tuple[KpiMacro, KpiMacro]:
    hoje = datetime.now(TZ_SP).date().isoformat()
    rows_p = carregar_rows_prodesp(start_date, end_date)
    rows_f = carregar_rows_fust(start_date, end_date)
    resumos = carregar_kpis_resumo_supervisao_dia(hoje)
    kpi_p = calcular_kpis_prodesp(rows_p, resumo_kpi=resumos.get("PRODESP"))
    kpi_f = calcular_kpis_fust(rows_f, resumo_kpi=resumos.get("FUST"))
    return kpi_p, kpi_f


def _condicionais_macro(
    cfg: ReportConfig,
    tipo: TipoRelatorio,
    kpis: dict[str, KpiMacro],
) -> tuple[dict[str, KpiMacro], ResultadoEnvio | None]:
    """Aplica 'sem dados' / 'dia encerrado' / 'Final só com atividade'. Retorna (projetos, omissão)."""
    if tipo == "periodico" and cfg.skip_sem_dados:
        kpis = {nome: k for nome, k in kpis.items() if not k.vazio}
        if not kpis:
            return kpis, omitido("sem_dados")
    if tipo == "periodico" and cfg.parar_dia_encerrado and _dia_encerrado(*kpis.values()):
        return kpis, omitido("encerrado")
    if tipo == "final" and cfg.final_so_com_atividade:
        if sum(k.com_atividade for k in kpis.values()) <= 0:
            return kpis, omitido("sem_atividade")
    return kpis, None


def enviar_macro(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    tipo: TipoRelatorio = "periodico",
) -> ResultadoEnvio:
    cfg = carregar_config("MACRO")
    if not (cfg.email_ativo or cfg.teams_ativo):
        return omitido("desabilitado")
    hoje = datetime.now(TZ_SP).date().isoformat()
    start_date = (start_date or hoje)[:10]
    end_date = (end_date or hoje)[:10]
    kpi_p, kpi_f = _carregar_kpis_macro(start_date, end_date)
    kpis, omissao = _condicionais_macro(cfg, tipo, {"PRODESP": kpi_p, "FUST": kpi_f})
    if omissao is not None:
        logger.info("supervisores - macro %s omitido: %s", tipo, omissao.motivo)
        return omissao
    kpi_p_env = kpis.get("PRODESP")
    kpi_f_env = kpis.get("FUST")
    fp = fingerprint(kpi_p_env, kpi_f_env)
    if tipo == "periodico" and cfg.skip_igual and igual_ao_ultimo("MACRO", hoje, fp):
        logger.info("supervisores - macro omitido: dados iguais ao último envio")
        return omitido("igual")

    periodo = _periodo_label(start_date, end_date)
    gerado = datetime.now(TZ_SP).strftime("%d/%m/%Y %H:%M")
    prefixo = "[SUPERVISORES] Report Final — " if tipo == "final" else "[SUPERVISORES] "
    nomes = " + ".join(n for n in ("FUST", "PRODESP") if n in kpis)
    totais = " / ".join(f"{n[0]} {kpis[n].total}" for n in ("PRODESP", "FUST") if n in kpis)
    subject = f"{prefixo}{nomes} — {periodo} — {totais}"
    html_body = build_macro_email_html(
        periodo_label=periodo,
        gerado_em=gerado,
        kpi_prodesp=kpi_p_env,
        kpi_fust=kpi_f_env,
        tipo=tipo,
    )
    ok_mail = False
    if cfg.email_ativo:
        ok_mail = _enviar_email(
            subject, html_body, cfg.emails_to, "relatório SUPERVISORES macro", cc=cfg.emails_cc
        )
    ok_teams = False
    if cfg.teams_ativo:
        if teams_webhook_url():
            ok_teams = send_teams_webhook(
                title=subject,
                text=build_macro_teams_text(
                    periodo_label=periodo, kpi_prodesp=kpi_p_env, kpi_fust=kpi_f_env
                ),
                card=build_macro_teams_card(
                    title=subject,
                    periodo_label=periodo,
                    gerado_em=gerado,
                    kpi_prodesp=kpi_p_env,
                    kpi_fust=kpi_f_env,
                    tipo=tipo,
                ),
            )
        if teams_channel_email():
            ok_teams = send_macro_teams_email(subject, html_body) or ok_teams
    if ok_mail or ok_teams:
        registrar_envio("MACRO", hoje, fp)
        return ENVIADO
    return omitido("falha")


def enviar_fust(*, tipo: TipoRelatorio = "periodico") -> ResultadoEnvio:
    """Cartão FUST-only no webhook dedicado (agenda própria em Personalização dos reports)."""
    cfg = carregar_config("FUST")
    if not cfg.teams_ativo:
        return omitido("desabilitado")
    hook_fust = teams_fust_webhook_url().strip()
    if not hook_fust:
        return omitido("desabilitado")
    hoje = datetime.now(TZ_SP).date().isoformat()
    rows_f = carregar_rows_fust(hoje, hoje)
    resumos = carregar_kpis_resumo_supervisao_dia(hoje)
    kpi_f = calcular_kpis_fust(rows_f, resumo_kpi=resumos.get("FUST"))
    kpis, omissao = _condicionais_macro(cfg, tipo, {"FUST": kpi_f})
    if omissao is not None:
        logger.info("supervisores - FUST-only %s omitido: %s", tipo, omissao.motivo)
        return omissao
    fp = fingerprint(kpi_f)
    if tipo == "periodico" and cfg.skip_igual and igual_ao_ultimo("FUST", hoje, fp):
        logger.info("supervisores - FUST-only omitido: dados iguais ao último envio")
        return omitido("igual")
    periodo = _periodo_label(hoje, hoje)
    gerado = datetime.now(TZ_SP).strftime("%d/%m/%Y %H:%M")
    prefixo = "[SUPERVISORES-FUST] Report Final — " if tipo == "final" else "[SUPERVISORES-FUST] "
    subject = f"{prefixo}FUST — {periodo} · Total {kpi_f.total}"
    faixa = (
        "Report FUST Final — encerramento operacional do dia."
        if tipo == "final"
        else "Visão FUST — dados da equipe FUST, sem PRODESP."
    )
    ok = send_teams_webhook(
        title=subject,
        text=build_macro_teams_text(periodo_label=periodo, kpi_fust=kpi_f),
        webhook_url=hook_fust,
        card=build_macro_teams_card(
            title=subject,
            periodo_label=periodo,
            gerado_em=gerado,
            kpi_fust=kpi_f,
            tipo=tipo,
            faixa_custom=faixa,
        ),
    )
    if ok:
        registrar_envio("FUST", hoje, fp)
        return ENVIADO
    return omitido("falha")


def enviar_fila(
    *,
    tipo: TipoRelatorio = "periodico",
    itens: list | None = None,
) -> ResultadoEnvio:
    cfg = carregar_config("FILA")
    email_on = cfg.email_ativo
    teams_on = cfg.teams_ativo
    if not email_on and not teams_on:
        return omitido("desabilitado")
    minutos = cfg.fila_limiar_min
    hoje = datetime.now(TZ_SP).date().isoformat()
    if itens is None:
        if tipo == "final":
            itens = carregar_fila_final(hoje, minutos_min=minutos)
        else:
            itens = carregar_fila_atual(minutos_min=minutos)

    rows_fust = None
    rows_prodesp = None
    top_fust = None
    top_prodesp = None
    top_geral = None
    ativos = None
    if tipo == "final":
        rows_fust = carregar_rows_fust(hoje, hoje)
        rows_prodesp = carregar_rows_prodesp(hoje, hoje)
        top_fust, top_prodesp, top_geral = agregar_top5_por_projeto(
            rows_fust, rows_prodesp, top=5
        )
        ativos = listar_atendimentos_ativos(
            rows_fust=rows_fust,
            rows_prodesp=rows_prodesp,
            agora=datetime.now(TZ_SP),
        )

    analistas = carregar_analistas_disponiveis()
    picos = None
    if tipo == "final":
        disp_ids = [getattr(a, "id_user", a.nome) for a in analistas] or [a.nome for a in analistas]
        picos = carregar_picos_do_dia(
            hoje,
            rows_fust=rows_fust,
            rows_prodesp=rows_prodesp,
            analistas_disponiveis_ids=disp_ids,
        )

    if tipo == "final":
        titulo = "[SUPERVISORES] Fila remota — quem atendeu"
        if not itens and not (picos and picos.tem_dado):
            logger.info("supervisores - fila final omitida: sem trechos e sem picos")
            return omitido("sem_dados")
    else:
        titulo = "[SUPERVISORES] Fila remota sem analista"
        if not itens:
            logger.info("supervisores - fila %s omitida: nenhum atendimento no critério", tipo)
            return omitido("sem_dados")
        fp_fila = fingerprint(sorted(f"{p}|{i}" for p, i in map(chave_fila, itens)))
        if cfg.skip_igual and igual_ao_ultimo("FILA", hoje, fp_fila):
            logger.info("supervisores - fila omitida: mesmas unidades do último envio")
            return omitido("igual")
        if any(int(getattr(item, "avisos", 0) or 0) <= 0 for item in itens):
            aplicar_proximo_aviso(itens, carregar_contagem_avisos())
    gerado = datetime.now(TZ_SP).strftime("%d/%m/%Y %H:%M")
    html_body = build_fila_email_html(
        gerado_em=gerado,
        itens=itens or [],
        minutos_min=minutos,
        tipo=tipo,
        analistas=analistas,
        picos=picos,
        top_fust=top_fust,
        top_prodesp=top_prodesp,
        top_geral=top_geral,
        ativos=ativos,
    )
    n_unidades = len(itens or [])
    subject = f"{titulo} — {n_unidades} unidade(s) — {gerado}"
    ok_mail = False
    if email_on:
        ok_mail = _enviar_email(
            subject, html_body, cfg.emails_to, "relatório SUPERVISORES fila", cc=cfg.emails_cc
        )
    ok_teams = False
    if teams_on:
        hooks = teams_fila_webhook_urls()
        if hooks:
            card_fila = build_fila_teams_card(
                title=subject,
                gerado_em=gerado,
                itens=itens or [],
                minutos_min=minutos,
                tipo=tipo,
                picos=picos,
                top_fust=top_fust,
                top_prodesp=top_prodesp,
                top_geral=top_geral,
                ativos=ativos,
            )
            cards_ana: list[tuple[str, str, dict, bool]] = []
            if tipo != "final":
                fatias = fatiar_analistas_teams(analistas)
                n_pag = len(fatias)
                for i, fatia in enumerate(fatias):
                    pagina = i + 1
                    sufixo = f" ({pagina}/{n_pag})" if n_pag > 1 else ""
                    subj_ana = (
                        f"[SUPERVISORES] Analistas disponíveis — {len(analistas)} — {gerado}{sufixo}"
                    )
                    cards_ana.append(
                        (
                            subj_ana,
                            build_analistas_teams_text(fatia),
                            build_analistas_teams_card(
                                title=subj_ana,
                                gerado_em=gerado,
                                analistas=fatia,
                                total=len(analistas),
                                pagina=pagina,
                                paginas=n_pag,
                            ),
                            i == 0,
                        )
                    )
            for hook in hooks:
                ok_fila = send_teams_webhook(
                    title=subject,
                    text=build_fila_teams_text(
                        itens=itens or [],
                        picos=picos,
                        tipo=tipo,
                        top_fust=top_fust,
                        top_prodesp=top_prodesp,
                        top_geral=top_geral,
                        ativos=ativos,
                    ),
                    webhook_url=hook,
                    card=card_fila,
                    mention_geral=False,
                )
                ok_teams = ok_teams or ok_fila
                if tipo != "final":
                    for subj_ana, texto_ana, card_ana, mention in cards_ana:
                        ok_ana = send_teams_webhook(
                            title=subj_ana,
                            text=texto_ana,
                            webhook_url=hook,
                            card=card_ana,
                            mention_geral=mention,
                        )
                        ok_teams = ok_teams or ok_ana
        dest_canal = teams_fila_channel_email()
        if dest_canal:
            from prodesp.prodesp.blueprint.agendamento_csv_notifier import send_graph_html_email

            ok_teams = (
                send_graph_html_email(
                    subject=subject,
                    html_body=html_body,
                    recipients=[dest_canal],
                    log_label="relatório SUPERVISORES fila Teams (e-mail do canal)",
                    extra_attachments=None,
                    include_logo=True,
                )
                or ok_teams
            )
    ok = ok_mail or ok_teams
    if ok and tipo != "final" and itens:
        contagem = carregar_contagem_avisos()
        registrar_envio_avisos(contagem, itens)
        salvar_contagem_avisos(contagem)
        registrar_envio("FILA", hoje, fp_fila)
    return ENVIADO if ok else omitido("falha")
