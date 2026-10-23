"""HTML dos relatórios SUPERVISORES (sem anexo, sem bloco por contratada)."""
from __future__ import annotations

import html
from typing import Sequence

from core.reports.analistas_disponiveis import AnalistaDisponivel, ordenar_analistas_destaque
from core.reports.env_config import env_int
from core.reports.fila_sem_analista import FilaEsperaItem
from core.reports.kpi_macro import (
    AtendimentoAtivoSupervisao,
    KpiMacro,
    TopAnalista,
    spec_cards_fust,
    spec_cards_prodesp,
)
from core.reports.picos_hora import PicoHora, PicosDia, PicosProjeto

_KPI_PER_ROW = 4
_KPI_CARD_HEIGHT = 76
_MSO_VAL = "font-size:24px;font-weight:700;color:#222222;line-height:1.1;"
_MSO_LBL = "font-size:12px;color:#444444;text-transform:uppercase;letter-spacing:.3px;"
_MSO_HINT = "font-size:11px;color:#666666;margin-top:2px;height:16px;overflow:hidden;"
_MODERN_VAL = "font-size:28px;font-weight:700;color:#222222;line-height:1.1;margin:6px 0 4px 0;"
_MODERN_LBL = "font-size:13px;color:#444444;text-transform:uppercase;letter-spacing:.4px;"
_MODERN_HINT = "font-size:12px;color:#666666;margin-top:4px;"
_MSO_BORDER = "border-top:1px solid #e5e5e5;border-right:1px solid #e5e5e5;border-bottom:1px solid #e5e5e5;"


def _assinatura() -> str:
    try:
        from prodesp.prodesp.blueprint.agendamento_csv_notifier import (
            build_email_assinatura_vita_html,
        )

        return build_email_assinatura_vita_html()
    except Exception:
        return "<p style='margin-top:24px;color:#888;font-size:12px;'>Portal Implantação — VITA</p>"


def _card_cell(label: str, valor: str, hint: str, accent: str) -> str:
    hint_text = html.escape(hint) if hint else "&nbsp;"
    h = _KPI_CARD_HEIGHT
    return (
        f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' height='{h}' "
        f"style='border-collapse:collapse;width:100%;height:{h}px;'>"
        "<tr>"
        f"<td width='4' bgcolor='{accent}' valign='top' height='{h}' "
        f"style='padding:0;background-color:{accent};width:4px;height:{h}px;'></td>"
        f"<td valign='top' height='{h}' style='padding:7px 10px 5px 10px;{_MSO_BORDER}"
        f"background:#ffffff;font-family:Calibri,Arial,sans-serif;height:{h}px;'>"
        f"<div style='{_MSO_LBL}'>{html.escape(label)}</div>"
        f"<div style='{_MSO_VAL}'>{html.escape(str(valor))}</div>"
        f"<div style='{_MSO_HINT}'>{hint_text}</div>"
        "</td></tr></table>"
    )


def _grid_table(cards: list[tuple[str, str, str, str]]) -> str:
    h = _KPI_CARD_HEIGHT
    rows_html: list[str] = []
    for i in range(0, len(cards), _KPI_PER_ROW):
        chunk = cards[i : i + _KPI_PER_ROW]
        cells = []
        for label, valor, hint, accent in chunk:
            cells.append(
                f"<td width='25%' valign='top' height='{h}' style='padding:0 6px 8px 0;width:25%;'>"
                f"{_card_cell(label, valor, hint, accent)}</td>"
            )
        while len(cells) < _KPI_PER_ROW:
            cells.append(f"<td width='25%' valign='top' height='{h}' style='padding:0 6px 8px 0;'>&nbsp;</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    return (
        "<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' "
        "style='border-collapse:collapse;table-layout:fixed;width:100%;'>"
        + "".join(rows_html)
        + "</table>"
    )


def _grid_modern(cards: list[tuple[str, str, str, str]]) -> str:
    parts = []
    for label, valor, hint, accent in cards:
        hint_html = f"<div style='{_MODERN_HINT}'>{html.escape(hint)}</div>" if hint else ""
        style = (
            "display:inline-block;vertical-align:top;width:132px;margin:0 8px 12px 0;"
            "padding:12px 14px;border-radius:8px;background:#ffffff;border:1px solid #e5e5e5;"
            f"border-left:4px solid {accent};font-family:Calibri,Arial,sans-serif;"
        )
        parts.append(
            f"<div style='{style}'>"
            f"<div style='{_MODERN_LBL}'>{html.escape(label)}</div>"
            f"<div style='{_MODERN_VAL}'>{html.escape(str(valor))}</div>"
            f"{hint_html}</div>"
        )
    return "<div style='font-size:0;line-height:0;max-width:980px;'>" + "".join(parts) + "</div>"


def _grid_dual(cards: list[tuple[str, str, str, str]]) -> str:
    return (
        "<!--[if mso]>"
        f"{_grid_table(cards)}"
        "<![endif]-->"
        "<!--[if !mso]><!-->"
        f"{_grid_modern(cards)}"
        "<!--<![endif]-->"
    )


def _bloco(titulo: str, cards: list[tuple[str, str, str, str]], subtitulo: str = "") -> str:
    sub = (
        f"<p style='margin:0 0 10px 0;color:#666666;font-size:12px;"
        f"font-family:Calibri,Arial,sans-serif;'>{html.escape(subtitulo)}</p>"
        if subtitulo
        else ""
    )
    return (
        f"<h3 style='margin:24px 0 8px 0;font-size:15px;color:#6b2d8a;"
        f"font-family:Calibri,Arial,sans-serif;'>{html.escape(titulo)}</h3>"
        f"{sub}{_grid_dual(cards)}"
    )


def build_macro_email_html(
    *,
    periodo_label: str,
    gerado_em: str,
    kpi_prodesp: KpiMacro | None,
    kpi_fust: KpiMacro | None,
    tipo: str = "periodico",
) -> str:
    projetos = [nome for nome, kpi in (("FUST", kpi_fust), ("PRODESP", kpi_prodesp)) if kpi is not None]
    projetos_html = " e ".join(f"<strong>{p}</strong>" for p in projetos) or "<strong>—</strong>"
    blocos = ""
    if kpi_prodesp is not None:
        blocos += _bloco("PRODESP", spec_cards_prodesp(kpi_prodesp), f"{kpi_prodesp.total} no período")
    if kpi_fust is not None:
        blocos += _bloco("FUST", spec_cards_fust(kpi_fust), f"{kpi_fust.total} no período")
    if tipo == "final":
        faixa = (
            "<p style='margin:0 0 12px 0;padding:10px 14px;background:#198754;color:#ffffff;"
            "font-weight:700;border-radius:4px;'>Report Final — encerramento operacional do dia.</p>"
        )
        titulo = "relatório operacional SUPERVISORES (Report Final)"
    else:
        faixa = ""
        titulo = "relatório operacional SUPERVISORES"
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:980px;border-collapse:collapse;">
  <tr><td style="font-family:Calibri,Arial,sans-serif;font-size:14px;color:#333333;line-height:1.45;">
  <p style="margin:0 0 12px 0;">Olá,</p>
  {faixa}
  <p style="margin:0 0 16px 0;">Segue o <strong>{html.escape(titulo)}</strong> de
  {projetos_html} referente a
  <strong>{html.escape(periodo_label)}</strong>, gerado em <strong>{html.escape(gerado_em)}</strong>.
  Visão consolidada, sem quebra por empresa contratada.</p>
  {blocos}
  {_assinatura()}
  </td></tr>
</table>
""".strip()


def _bloco_analistas_html(analistas: Sequence[AnalistaDisponivel] | None) -> str:
    if analistas is None:
        return ""
    if not analistas:
        corpo = (
            "<tr><td colspan='4' style='padding:10px;color:#666;'>"
            "Nenhum analista disponível no momento (após blacklist).</td></tr>"
        )
    else:
        linhas = []
        for a in analistas:
            linhas.append(
                "<tr>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.nome)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.status_label)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.plataforma_label)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>"
                f"{int(a.finalizados)}</td>"
                "</tr>"
            )
        corpo = "".join(linhas)
    return (
        "<h3 style='margin:22px 0 8px 0;font-size:15px;color:#6b2d8a;"
        "font-family:Calibri,Arial,sans-serif;'>Analistas disponíveis</h3>"
        "<p style='margin:0 0 10px 0;color:#666;font-size:12px;'>"
        "Sem atendimento em andamento no portal agora. Nomes em férias/consultoria entram na blacklist."
        "</p>"
        "<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' "
        "style='border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='background:#f4f1f7;text-align:left;'>"
        "<th style='padding:8px;'>Analista</th>"
        "<th style='padding:8px;'>Status</th>"
        "<th style='padding:8px;'>Na plataforma</th>"
        "<th style='padding:8px;'>Finalizado</th>"
        "</tr></thead>"
        f"<tbody>{corpo}</tbody></table>"
    )


def _linhas_pico_html(titulo: str, picos: Sequence[PicoHora], tipo: str) -> str:
    if not picos:
        return (
            f"<p style='margin:4px 0;color:#666;font-size:13px;'>{html.escape(titulo)}: "
            "sem pico registrado no dia.</p>"
        )
    partes = []
    for i, pico in enumerate(picos, start=1):
        if tipo == "espera":
            linha = pico.linha(f"{i}º maior pico de aguardando analista", mostrar_equipe=True)
            # Ajuste: troca sufixo default "atendimento" para "aguardando analista" para manter texto original
            linha_ajustada = linha.replace(
                "maior pico de aguardando analista atendimento simultâneo",
                "maior pico de aguardando analista atendimento simultâneo aguardando analista",
            ).replace(
                "maior pico de aguardando analista atendimentos simultâneos",
                "maior pico de aguardando analista atendimentos simultâneos aguardando analista",
            )
            partes.append(html.escape(linha_ajustada))
        else:
            linha = pico.linha(f"{i}º maior pico de atendimento", mostrar_equipe=True)
            partes.append(html.escape(linha))
    return (
        "<p style='margin:4px 0 2px 0;font-size:13px;color:#333;'>"
        + "<br>".join(partes)
        + "</p>"
    )


def _top5_tabela_html(titulo_projeto: str, top: Sequence[TopAnalista]) -> str:
    escopo_geral = titulo_projeto.strip().upper() == "GERAL"
    cab = (
        "<h3 style='margin:22px 0 8px 0;font-size:15px;color:#6b2d8a;"
        f"font-family:Calibri,Arial,sans-serif;'>TOP 5 analistas — {html.escape(titulo_projeto)}</h3>"
    )
    if escopo_geral:
        n_cols = 7
        head = (
            "<thead><tr style='background:#f4f1f7;text-align:left;'>"
            "<th style='padding:8px;'>Analista</th>"
            "<th style='padding:8px;'>Concluído</th>"
            "<th style='padding:8px;'>Quebra</th>"
            "<th style='padding:8px;'>Parcial</th>"
            "<th style='padding:8px;'>FUST</th>"
            "<th style='padding:8px;'>PRODESP</th>"
            "<th style='padding:8px;'>Total dia</th>"
            "</tr></thead>"
        )
    else:
        n_cols = 5
        head = (
            "<thead><tr style='background:#f4f1f7;text-align:left;'>"
            "<th style='padding:8px;'>Analista</th>"
            "<th style='padding:8px;'>Concluído</th>"
            "<th style='padding:8px;'>Quebra</th>"
            "<th style='padding:8px;'>Parcial</th>"
            "<th style='padding:8px;'>Total dia</th>"
            "</tr></thead>"
        )
    linhas = []
    if not top:
        linhas.append(
            f"<tr><td colspan='{n_cols}' style='padding:10px;color:#666;'>Nenhum analista no período.</td></tr>"
        )
    for a in top:
        total = int(getattr(a, "total", 0))
        if escopo_geral:
            linha = (
                "<tr>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.nome)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>{int(a.concluidos)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>{int(a.quebra)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>{int(a.parcial)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>{int(a.fust)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>{int(a.prodesp)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;font-weight:700;'>{total}</td>"
                "</tr>"
            )
        else:
            linha = (
                "<tr>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.nome)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>{int(a.concluidos)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>{int(a.quebra)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>{int(a.parcial)}</td>"
                f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;font-weight:700;'>{total}</td>"
                "</tr>"
            )
        linhas.append(linha)
    corpo = "".join(linhas)
    return (
        cab
        + "<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' "
        "style='border-collapse:collapse;font-size:13px;'>"
        + head
        + f"<tbody>{corpo}</tbody></table>"
    )


def _ativos_tabela_html(ativos: Sequence[AtendimentoAtivoSupervisao]) -> str:
    cab = (
        "<h3 style='margin:24px 0 8px 0;font-size:15px;color:#6b2d8a;"
        "font-family:Calibri,Arial,sans-serif;'>Atendimentos ainda ativos</h3>"
    )
    head = (
        "<thead><tr style='background:#f4f1f7;text-align:left;'>"
        "<th style='padding:8px;'>Projeto</th>"
        "<th style='padding:8px;'>INEP / ID VGR</th>"
        "<th style='padding:8px;'>Unidade</th>"
        "<th style='padding:8px;'>Status</th>"
        "<th style='padding:8px;'>Substatus</th>"
        "<th style='padding:8px;'>Tempo atuação</th>"
        "<th style='padding:8px;'>Analista</th>"
        "</tr></thead>"
    )
    linhas = []
    if not ativos:
        linhas.append(
            "<tr><td colspan='7' style='padding:10px;color:#666;'>Nenhum atendimento ativo neste momento.</td></tr>"
        )
    for a in ativos[:120]:
        linhas.append(
            "<tr>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.projeto)}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.chave or '—')}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.unidade or '—')}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.status or '—')}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.substatus or '—')}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>{html.escape(a.tempo_atuacao_label or '—')}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(a.analista or '—')}</td>"
            "</tr>"
        )
    corpo = "".join(linhas)
    return (
        cab
        + "<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' "
        "style='border-collapse:collapse;font-size:13px;'>"
        + head
        + f"<tbody>{corpo}</tbody></table>"
    )


def _bloco_picos_html(picos: PicosDia) -> str:
    if not picos or not picos.tem_dado:
        return ""
    titulo = (
        "<h2 style='margin:24px 0 4px 0;font-size:16px;color:#6b2d8a;"
        "font-family:Calibri,Arial,sans-serif;'>Picos de atuação (top 3 por hora)</h2>"
        "<p style='margin:0 0 10px 0;font-size:12px;color:#666;'>"
        "Máximo de atendimentos simultâneos em etapa produtiva (Em Configuração / Caderno) "
        "e máximo aguardando analista (filas Aguardando Config./MPLS/Caderno). "
        "Útil para dimensionar a escala do dia seguinte.</p>"
    )
    blocos = []
    for bloco in (picos.fust, picos.prodesp, picos.geral):
        if not bloco or not bloco.tem_dado:
            continue
        header = (
            f"<h3 style='margin:14px 0 6px 0;font-size:14px;color:#6b2d8a;"
            f"font-family:Calibri,Arial,sans-serif;'>{html.escape(bloco.projeto)}</h3>"
        )
        body = _linhas_pico_html(bloco.projeto, bloco.atendimento, "atendimento")
        body += _linhas_pico_html(bloco.projeto, bloco.espera, "espera")
        blocos.append(header + body)
    return titulo + "".join(blocos)


def build_fila_email_html(
    *,
    gerado_em: str,
    itens: Sequence[FilaEsperaItem],
    minutos_min: int,
    tipo: str = "periodico",
    analistas: Sequence[AnalistaDisponivel] | None = None,
    picos: PicosDia | None = None,
    top_fust: Sequence[TopAnalista] | None = None,
    top_prodesp: Sequence[TopAnalista] | None = None,
    top_geral: Sequence[TopAnalista] | None = None,
    ativos: Sequence[AtendimentoAtivoSupervisao] | None = None,
) -> str:
    if tipo == "final":
        intro = (
            f"Atendimentos que ficaram <strong>{int(minutos_min)} min ou mais</strong> em "
            "<strong>Aguardando Config. Remota</strong> sem analista e depois foram assumidos. "
            "Coluna <em>Acionamentos</em> = quantas vezes este atendimento entrou na fila remota até ser assumido; "
            "<em>Analista</em> = quem atendeu; <em>Espera</em> = tempo parado na fila."
        )
        titulo = "Fila remota — report final (quem atendeu)"
    else:
        intro = (
            f"Atendimentos em <strong>Aguardando Config. Remota</strong> sem analista alocado "
            f"há <strong>{int(minutos_min)} min ou mais</strong>. "
            "Lista completa da fila neste momento: quem foi assumido sai; quem acaba de cruzar o limiar entra. "
            "Coluna <em>Avisos</em> = quantas vezes esta unidade já foi reportada até ser atendida."
        )
        titulo = "Fila remota sem analista"
    mostrar_avisos = tipo != "final"
    mostrar_acionamentos = tipo == "final"
    linhas = []
    for it in itens:
        col_avisos = (
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>"
            f"{html.escape(it.avisos_label)}</td>"
            if mostrar_avisos
            else ""
        )
        col_acionamentos = (
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>"
            f"{html.escape(it.acionamentos_label if hasattr(it, 'acionamentos_label') else '—')}</td>"
            if mostrar_acionamentos
            else ""
        )
        linhas.append(
            "<tr>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(it.projeto)}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(it.chave)}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(it.unidade)}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(it.municipio)}/{html.escape(it.uf)}</td>"
            + col_acionamentos
            + f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;'>{html.escape(it.espera_label)}</td>"
            + col_avisos
            + f"<td style='padding:6px 8px;border-bottom:1px solid #eee;'>{html.escape(it.analista or '—')}</td>"
            "</tr>"
        )
    th_acionamentos = "<th style='padding:8px;'>Acionamentos</th>" if mostrar_acionamentos else ""
    th_avisos = "<th style='padding:8px;'>Avisos</th>" if mostrar_avisos else ""
    n_cols = 7 + (1 if mostrar_acionamentos else 0) if mostrar_avisos else 6 + (1 if mostrar_acionamentos else 0)
    corpo = (
        "".join(linhas)
        if linhas
        else f"<tr><td colspan='{n_cols}' style='padding:10px;color:#666;'>Nenhum atendimento no critério.</td></tr>"
    )
    bloco_analistas = ""
    if tipo != "final":
        bloco_analistas = _bloco_analistas_html(analistas)
    bloco_top5 = ""
    bloco_ativos = ""
    if tipo == "final":
        bloco_top5 = (
            _top5_tabela_html("FUST", list(top_fust or []))
            + _top5_tabela_html("PRODESP", list(top_prodesp or []))
            + _top5_tabela_html("GERAL", list(top_geral or []))
        )
        bloco_ativos = _ativos_tabela_html(list(ativos or []))
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:980px;border-collapse:collapse;">
  <tr><td style="font-family:Calibri,Arial,sans-serif;font-size:14px;color:#333333;line-height:1.45;">
  <p>Olá,</p>
  <h2 style="margin:0 0 8px 0;font-size:16px;color:#6b2d8a;">{html.escape(titulo)}</h2>
  <p style="margin:0 0 14px 0;">{intro} Gerado em <strong>{html.escape(gerado_em)}</strong>.</p>
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;font-size:13px;">
    <thead>
      <tr style="background:#f4f1f7;text-align:left;">
        <th style="padding:8px;">Projeto</th>
        <th style="padding:8px;">INEP / ID VGR</th>
        <th style="padding:8px;">Unidade</th>
        <th style="padding:8px;">Cidade/UF</th>
        {th_acionamentos}
        <th style="padding:8px;">Espera</th>
        {th_avisos}
        <th style="padding:8px;">Analista</th>
      </tr>
    </thead>
    <tbody>{corpo}</tbody>
  </table>
  {bloco_analistas}
  {_bloco_picos_html(picos) if tipo == "final" else ""}
  {bloco_top5}
  {bloco_ativos}
  {_assinatura()}
  </td></tr>
</table>
""".strip()


def build_macro_teams_text(
    *,
    periodo_label: str,
    kpi_prodesp: KpiMacro | None = None,
    kpi_fust: KpiMacro | None = None,
) -> str:
    """Markdown curto para Incoming Webhook legado / resumo.

    Aceita kpi_prodesp=None ou kpi_fust=None para emitir visão unitária (só FUST / só PRODESP).
    Usado no envio de relatório FUST-only para webhooks dedicados.
    """

    def linha(kpi: KpiMacro | None) -> str | None:
        if kpi is None:
            return None
        return (
            f"Total **{kpi.total}** · Agendados **{kpi.agendados}** · "
            f"Em atend. **{kpi.em_atendimento}** · Fila remota **{kpi.aguardando_remota}** · "
            f"Concluídos **{kpi.concluidos}** ({kpi.pct_concluidos}%)"
        )

    linhas: list[str] = []
    if kpi_prodesp is not None:
        linhas.append(f"**PRODESP** — {linha(kpi_prodesp)}")
    if kpi_fust is not None:
        linhas.append(f"**FUST** — {linha(kpi_fust)}")
    bloco_kpis = "\n\n".join(linhas) if linhas else ""
    return f"**Período:** {periodo_label}\n\n{bloco_kpis}".strip()


def build_macro_teams_card(
    *,
    title: str,
    periodo_label: str,
    gerado_em: str,
    kpi_prodesp: KpiMacro | None = None,
    kpi_fust: KpiMacro | None = None,
    tipo: str = "periodico",
    faixa_custom: str | None = None,
) -> dict:
    """Adaptive Card 1.2: 2 colunas (chat estreito + canal). Sem width em px.

    Suporta visão consolidada (PRODESP+FUST) ou visão unitária (só 1 dos 2 ou separado).
    Parâmetro `faixa_custom` permite trocar o texto da faixa de cabeçalho em cards dedicados.
    """
    is_final = tipo == "final"
    if faixa_custom is not None:
        faixa = faixa_custom
    elif is_final:
        faixa = "Report Final — encerramento operacional do dia."
    else:
        if kpi_prodesp is not None and kpi_fust is not None:
            faixa = "Visão consolidada, sem quebra por empresa contratada."
        elif kpi_fust is not None and kpi_prodesp is None:
            faixa = "Visão FUST — dados da equipe FUST."
        elif kpi_prodesp is not None and kpi_fust is None:
            faixa = "Visão PRODESP — dados da equipe PRODESP."
        else:
            faixa = "Sem dados no período."
    body: list[dict] = [
        {
            "type": "Container",
            "style": "good" if is_final else "accent",
            "items": [
                {
                    "type": "TextBlock",
                    "text": str(title)[:180],
                    "weight": "Bolder",
                    "size": "Medium",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": f"Período **{periodo_label}** · gerado em {gerado_em}",
                    "wrap": True,
                    "size": "Small",
                    "spacing": "None",
                },
                {
                    "type": "TextBlock",
                    "text": faixa,
                    "wrap": True,
                    "size": "Small",
                    "spacing": "Small",
                },
            ],
        },
    ]
    if kpi_prodesp is not None:
        body.append(_teams_section_title(f"PRODESP · {kpi_prodesp.total} no período"))
        body.extend(_teams_kpi_grid(spec_cards_prodesp(kpi_prodesp)))
    if kpi_fust is not None:
        body.append(_teams_section_title(f"FUST · {kpi_fust.total} no período"))
        body.extend(_teams_kpi_grid(spec_cards_fust(kpi_fust)))
    body.append(
        {
            "type": "TextBlock",
            "text": "Portal Implantação — SUPERVISORES",
            "size": "Small",
            "isSubtle": True,
            "spacing": "Medium",
        }
    )
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.2",
        "msteams": {"width": "Full"},
        "body": body,
    }


_TEAMS_COLOR = {
    "#6b2d8a": "Accent",
    "#5a2e7c": "Accent",
    "#198754": "Good",
    "#dc3545": "Attention",
    "#b02a37": "Attention",
    "#fd7e14": "Warning",
    "#e67e22": "Warning",
    "#0d6efd": "Accent",
    "#0dcaf0": "Accent",
    "#6c757d": "Default",
}


def _teams_color(accent: str) -> str:
    return _TEAMS_COLOR.get((accent or "").strip().lower(), "Default")


def _teams_bar_style(accent: str) -> str:
    """Faixa esquerda: estilo do host Teams (o mais perto da borda colorida do e-mail)."""
    return {
        "Good": "good",
        "Attention": "attention",
        "Warning": "warning",
        "Accent": "accent",
        "Default": "emphasis",
    }.get(_teams_color(accent), "emphasis")


def _teams_kpi_column(label: str, valor: str, hint: str, accent: str) -> dict:
    """Card compacto (chat + canal): sem coluna em px — o chat ignora 8px e esmaga o layout."""
    color = _teams_color(accent)
    bar_color = color if color != "Default" else "Accent"
    items = [
        {
            "type": "TextBlock",
            "text": str(label),
            "size": "Medium",
            "weight": "Bolder",
            "wrap": True,
            "maxLines": 2,
        },
        {
            "type": "TextBlock",
            "text": str(valor),
            "size": "ExtraLarge",
            "weight": "Bolder",
            "color": bar_color,
            "spacing": "None",
        },
    ]
    if hint:
        items.append(
            {
                "type": "TextBlock",
                "text": str(hint),
                "size": "Default",
                "isSubtle": False,
                "wrap": True,
                "maxLines": 2,
                "spacing": "Small",
            }
        )
    return {
        "type": "Column",
        "width": "stretch",
        "items": [
            {
                "type": "Container",
                "style": _teams_bar_style(accent),
                "items": items,
            }
        ],
    }


def _teams_kpi_grid(cards: list[tuple[str, str, str, str]], per_row: int = 2) -> list[dict]:
    rows: list[dict] = []
    blank = {
        "type": "Column",
        "width": "stretch",
        "items": [{"type": "TextBlock", "text": " "}],
    }
    for i in range(0, len(cards), per_row):
        chunk = cards[i : i + per_row]
        cols = [_teams_kpi_column(*c) for c in chunk]
        while len(cols) < per_row:
            cols.append(blank)
        rows.append({"type": "ColumnSet", "columns": cols, "spacing": "Small"})
    return rows


def _teams_section_title(text: str) -> dict:
    return {
        "type": "Container",
        "style": "accent",
        "spacing": "Medium",
        "items": [
            {
                "type": "TextBlock",
                "text": text,
                "weight": "Bolder",
                "wrap": True,
            }
        ],
    }


def build_macro_teams_card(
    *,
    title: str,
    periodo_label: str,
    gerado_em: str,
    kpi_prodesp: KpiMacro | None = None,
    kpi_fust: KpiMacro | None = None,
    tipo: str = "periodico",
    faixa_custom: str | None = None,
) -> dict:
    """Adaptive Card 1.2: 2 colunas (chat estreito + canal). Sem width em px.

    Suporta visão consolidada (PRODESP+FUST) ou visão unitária (só 1 dos 2 ou separado).
    Parâmetro `faixa_custom` permite trocar o texto da faixa de cabeçalho em cards dedicados.
    """
    is_final = tipo == "final"
    if faixa_custom is not None:
        faixa = faixa_custom
    elif is_final:
        faixa = "Report Final — encerramento operacional do dia."
    else:
        if kpi_prodesp is not None and kpi_fust is not None:
            faixa = "Visão consolidada, sem quebra por empresa contratada."
        elif kpi_fust is not None and kpi_prodesp is None:
            faixa = "Visão FUST — dados da equipe FUST."
        elif kpi_prodesp is not None and kpi_fust is None:
            faixa = "Visão PRODESP — dados da equipe PRODESP."
        else:
            faixa = "Sem dados no período."
    body: list[dict] = [
        {
            "type": "Container",
            "style": "good" if is_final else "accent",
            "items": [
                {
                    "type": "TextBlock",
                    "text": str(title)[:180],
                    "weight": "Bolder",
                    "size": "Medium",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": f"Período **{periodo_label}** · gerado em {gerado_em}",
                    "wrap": True,
                    "size": "Small",
                    "spacing": "None",
                },
                {
                    "type": "TextBlock",
                    "text": faixa,
                    "wrap": True,
                    "size": "Small",
                    "spacing": "Small",
                },
            ],
        },
    ]
    if kpi_prodesp is not None:
        body.append(_teams_section_title(f"PRODESP · {kpi_prodesp.total} no período"))
        body.extend(_teams_kpi_grid(spec_cards_prodesp(kpi_prodesp)))
    if kpi_fust is not None:
        body.append(_teams_section_title(f"FUST · {kpi_fust.total} no período"))
        body.extend(_teams_kpi_grid(spec_cards_fust(kpi_fust)))
    body.append(
        {
            "type": "TextBlock",
            "text": "Portal Implantação — SUPERVISORES",
            "size": "Small",
            "isSubtle": True,
            "spacing": "Medium",
        }
    )
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.2",
        "msteams": {"width": "Full"},
        "body": body,
    }


def _build_macro_teams_card_legacy(
    *,
    title: str,
    periodo_label: str,
    gerado_em: str,
    kpi_prodesp: KpiMacro,
    kpi_fust: KpiMacro,
    tipo: str = "periodico",
) -> dict:
    """Alias LEGADO preservado para não quebrar referências circulares / hotreload."""
    return build_macro_teams_card(
        title=title,
        periodo_label=periodo_label,
        gerado_em=gerado_em,
        kpi_prodesp=kpi_prodesp,
        kpi_fust=kpi_fust,
        tipo=tipo,
    )





def _teams_columnset(cells: Sequence[str], *, header: bool = False) -> dict:
    cols = []
    for val in cells:
        cols.append(
            {
                "type": "Column",
                "width": "stretch",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": str(val) if val not in (None, "") else "—",
                        "wrap": True,
                        "weight": "Bolder" if header else "Default",
                        "size": "Small",
                        "spacing": "None",
                    }
                ],
            }
        )
    return {"type": "ColumnSet", "columns": cols, "spacing": "Small" if header else "None"}


def _teams_tabela(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[dict]:
    blocos: list[dict] = [
        {
            "type": "Container",
            "style": "emphasis",
            "items": [_teams_columnset(headers, header=True)],
        }
    ]
    if not rows:
        blocos.append(
            {
                "type": "TextBlock",
                "text": "Nenhum item no critério.",
                "wrap": True,
                "size": "Small",
                "isSubtle": True,
            }
        )
        return blocos
    for row in rows:
        blocos.append(_teams_columnset(row, header=False))
    return blocos


def _fila_linhas_tabela(itens: Sequence[FilaEsperaItem], *, tipo: str) -> tuple[list[str], list[list[str]]]:
    mostrar_avisos = tipo != "final"
    mostrar_acionamentos = tipo == "final"
    headers = ["Projeto / ID", "Unidade"]
    if mostrar_acionamentos:
        headers.append("Aciona")
    headers.append("Espera")
    if mostrar_avisos:
        headers.append("Avisos")
    rows: list[list[str]] = []
    for it in itens:
        projeto_id = f"{it.projeto} {it.chave}".strip()
        unidade = f"{it.unidade}\n{it.municipio}/{it.uf}".strip()
        row = [projeto_id, unidade]
        if mostrar_acionamentos:
            row.append(getattr(it, "acionamentos_label", "—"))
        row.append(it.espera_label)
        if mostrar_avisos:
            row.append(it.avisos_label)
        rows.append(row)
    return headers, rows


def _analistas_linhas_tabela(
    analistas: Sequence[AnalistaDisponivel],
) -> tuple[list[str], list[list[str]]]:
    headers = ["Analista", "Status", "Plataforma", "Finalizado"]
    rows = [
        [a.nome, a.status_label, a.plataforma_label, str(int(a.finalizados))]
        for a in analistas
    ]
    return headers, rows


def _fila_linha_item(it: FilaEsperaItem, *, tipo: str = "periodico") -> str:
    analista = it.analista or "—"
    avisos = f" · aviso **{it.avisos_label}**" if tipo != "final" and it.avisos else ""
    aciona = f" · aciona **{getattr(it, 'acionamentos_label', '—')}**" if tipo == "final" else ""
    return (
        f"**{it.projeto}** `{it.chave}` · {it.unidade} · {it.municipio}/{it.uf} · "
        f"espera **{it.espera_label}**{aciona}{avisos} · {analista}"
    )


def _fila_linhas_pico(bloco: PicosProjeto) -> str:
    partes = [f"**{bloco.projeto}**"]
    if bloco.atendimento:
        for i, pico in enumerate(bloco.atendimento, start=1):
            partes.append(pico.linha(f"{i}º pico de atendimento:", mostrar_equipe=True))
    else:
        partes.append("Atendimento: sem pico no dia")
    if bloco.espera:
        for i, pico in enumerate(bloco.espera, start=1):
            partes.append(pico.linha(f"{i}º pico de aguardando analista:", mostrar_equipe=True))
    else:
        partes.append("Aguardando analista: sem pico no dia")
    return "\n".join(partes)


def build_fila_teams_text(
    *,
    itens: Sequence[FilaEsperaItem],
    picos: PicosDia | None = None,
    tipo: str = "periodico",
    analistas: Sequence[AnalistaDisponivel] | None = None,
    top_fust: Sequence[TopAnalista] | None = None,
    top_prodesp: Sequence[TopAnalista] | None = None,
    top_geral: Sequence[TopAnalista] | None = None,
    ativos: Sequence[AtendimentoAtivoSupervisao] | None = None,
) -> str:
    del analistas
    linhas = [_fila_linha_item(it, tipo=tipo) for it in itens[:20]]
    if len(itens) > 20:
        linhas.append(f"... +{len(itens) - 20} unidade(s)")
    if tipo == "final" and picos and picos.tem_dado:
        for proj in (picos.fust, picos.prodesp, picos.geral):
            if proj and proj.tem_dado:
                linhas.append(_fila_linhas_pico(proj))
    if tipo == "final":
        for titulo, top_r in (
            ("FUST", top_fust),
            ("PRODESP", top_prodesp),
            ("GERAL", top_geral),
        ):
            if not top_r:
                continue
            escopo_geral = titulo == "GERAL"
            top_lines = [f"**TOP {min(len(top_r),3)} {titulo} — mais atendimentos do dia**"]
            for a in top_r[:3]:
                if escopo_geral:
                    proj = []
                    if a.fust:
                        proj.append(f"{a.fust} FUST")
                    if a.prodesp:
                        proj.append(f"{a.prodesp} PRODESP")
                    proj_str = " + ".join(proj) if proj else "-"
                    top_lines.append(
                        f"{a.nome} · Conc {a.concluidos} · Quebra {a.quebra} · Parc {a.parcial} · {proj_str} · Total {a.total}"
                    )
                else:
                    top_lines.append(
                        f"{a.nome} · Conc {a.concluidos} · Quebra {a.quebra} · Parc {a.parcial} · Total {a.total}"
                    )
            linhas.append("\n".join(top_lines))
    if tipo == "final" and ativos:
        atv_lines = [f"**Atendimentos ainda ativos — {len(ativos)}**"]
        for at in ativos[:10]:
            atv_lines.append(
                f"{at.projeto} · {at.chave} · {at.unidade[:35]} · {at.status}/{at.substatus} · {at.tempo_atuacao_label} · {at.analista}"
            )
        if len(ativos) > 10:
            atv_lines.append(f"... +{len(ativos) - 10} no e-mail")
        linhas.append("\n".join(atv_lines))
    return "\n\n".join(linhas) if linhas else "Nenhum atendimento no critério."


def build_analistas_teams_text(analistas: Sequence[AnalistaDisponivel] | None = None) -> str:
    lista = ordenar_analistas_destaque(list(analistas or []))
    if not lista:
        return "Nenhum analista disponível no momento (após blacklist)."
    linhas = ["Analistas disponíveis"]
    for a in lista[:40]:
        linhas.append(
            f"{a.nome} · {a.status_label} · {a.plataforma_label} · finalizado {int(a.finalizados)}"
        )
    if len(lista) > 40:
        linhas.append(f"... +{len(lista) - 40} analista(s)")
    return "\n".join(linhas)


def _teams_cabecalho(title: str, intro: str, gerado_em: str, *, estilo: str) -> dict:
    return {
        "type": "Container",
        "style": estilo,
        "items": [
            {
                "type": "TextBlock",
                "text": str(title)[:180],
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": f"{intro} Gerado em {gerado_em}",
                "wrap": True,
                "size": "Small",
                "spacing": "None",
            },
        ],
    }


def _teams_rodape() -> dict:
    return {
        "type": "TextBlock",
        "text": "Portal Implantação — SUPERVISORES fila",
        "size": "Small",
        "isSubtle": True,
        "spacing": "Medium",
    }


def build_fila_teams_card(
    *,
    title: str,
    gerado_em: str,
    itens: Sequence[FilaEsperaItem],
    minutos_min: int,
    tipo: str = "periodico",
    analistas: Sequence[AnalistaDisponivel] | None = None,
    picos: PicosDia | None = None,
    top_fust: Sequence[TopAnalista] | None = None,
    top_prodesp: Sequence[TopAnalista] | None = None,
    top_geral: Sequence[TopAnalista] | None = None,
    ativos: Sequence[AtendimentoAtivoSupervisao] | None = None,
) -> dict:
    del analistas
    max_itens = max(5, env_int("SUPERVISORES_FILA_TEAMS_MAX_ITENS", 15))
    is_final = tipo == "final"
    intro = (
        f"Report final — quem atendeu após ≥{int(minutos_min)} min na fila remota."
        if is_final
        else f"Fila atual ≥{int(minutos_min)} min. Quem foi assumido sai; novo atraso entra. Avisos = vezes reportada."
    )
    body: list[dict] = [
        _teams_cabecalho(title, intro, gerado_em, estilo="attention" if not is_final else "good"),
        _teams_section_title(f"Fila — {len(itens)} unidade(s)"),
    ]
    if itens:
        headers, rows = _fila_linhas_tabela(itens[:max_itens], tipo=tipo)
        body.extend(_teams_tabela(headers, rows))
        if len(itens) > max_itens:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"... +{len(itens) - max_itens} unidade(s) no e-mail",
                    "size": "Small",
                    "isSubtle": True,
                }
            )
    else:
        body.append(
            {
                "type": "TextBlock",
                "text": "Nenhum atendimento no critério.",
                "wrap": True,
                "size": "Small",
            }
        )
    if is_final and picos and picos.tem_dado:
        body.append(_teams_section_title("Picos de atuação (top 3)"))
        for bloco in (picos.fust, picos.prodesp, picos.geral):
            if bloco and bloco.tem_dado:
                body.append(
                    {
                        "type": "TextBlock",
                        "text": _fila_linhas_pico(bloco),
                        "wrap": True,
                        "size": "Small",
                        "spacing": "Small",
                    }
                )
    if is_final:
        for titulo, top_r in (("FUST", top_fust), ("PRODESP", top_prodesp)):
            if not top_r:
                continue
            n = min(3, len(top_r))
            body.append(_teams_section_title(f"TOP {n} {titulo}"))
            top_rows: list[list[str]] = []
            for a in top_r[:3]:
                top_rows.append([
                    (a.nome or "")[:24],
                    str(a.concluidos),
                    str(a.quebra),
                    str(a.parcial),
                    str(a.total),
                ])
            body.extend(
                _teams_tabela(
                    ["Analista", "Conc", "Quebra", "Parc", "Total"],
                    top_rows,
                )
            )
    if is_final and top_geral:
        n = min(5, len(top_geral))
        body.append(_teams_section_title(f"TOP {n} GERAL"))
        top_rows_geral: list[list[str]] = []
        for a in top_geral[:5]:
            projetos: list[str] = []
            if a.fust:
                projetos.append(f"{a.fust} FUST")
            if a.prodesp:
                projetos.append(f"{a.prodesp} PRODESP")
            proj_str = " + ".join(projetos) if projetos else "-"
            top_rows_geral.append([
                (a.nome or "")[:22],
                str(a.concluidos),
                str(a.quebra),
                str(a.parcial),
                proj_str,
                str(a.total),
            ])
        body.extend(
            _teams_tabela(
                ["Analista", "Conc", "Quebra", "Parc", "Projetos", "Total"],
                top_rows_geral,
            )
        )
    if is_final and ativos:
        max_ativos = max(3, env_int("SUPERVISORES_FILA_TEAMS_MAX_ATIVOS", 8))
        body.append(_teams_section_title(f"Atendimentos ativos — {len(ativos)}"))
        atv_rows: list[list[str]] = []
        for at in ativos[:max_ativos]:
            atv_rows.append([
                at.projeto[:3],
                at.chave[:12] if at.chave else "-",
                at.unidade[:20] if at.unidade else "-",
                at.tempo_atuacao_label,
                (at.analista or "")[:18],
            ])
        body.extend(_teams_tabela(["Prj", "INEP/ID", "Unidade", "Tempo", "Analista"], atv_rows))
        if len(ativos) > max_ativos:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"... +{len(ativos) - max_ativos} no e-mail",
                    "size": "Small",
                    "isSubtle": True,
                }
            )
    body.append(_teams_rodape())
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.2",
        "msteams": {"width": "Full"},
        "body": body,
    }


def fatiar_analistas_teams(
    analistas: Sequence[AnalistaDisponivel] | None,
) -> list[list[AnalistaDisponivel]]:
    """Quebra a lista em páginas. Se MAX_ANALISTAS > 0 usa esse teto; senão empacota até ~22KB."""
    lista = ordenar_analistas_destaque(list(analistas or []))
    if not lista:
        return []
    teto = env_int("SUPERVISORES_FILA_TEAMS_MAX_ANALISTAS", 0)
    if teto > 0:
        return [lista[i : i + teto] for i in range(0, len(lista), teto)]
    limite = max(8000, env_int("SUPERVISORES_FILA_TEAMS_MAX_BYTES", 22000))
    fatias: list[list[AnalistaDisponivel]] = []
    atual: list[AnalistaDisponivel] = []
    total = len(lista)
    for analista in lista:
        candidato = atual + [analista]
        nbytes = _bytes_payload_analistas(
            candidato, total=total, pagina=max(1, len(fatias) + 1)
        )
        if atual and nbytes > limite:
            fatias.append(atual)
            atual = [analista]
        else:
            atual = candidato
    if atual:
        fatias.append(atual)
    return fatias


def _bytes_payload_analistas(
    fatia: Sequence[AnalistaDisponivel],
    *,
    total: int,
    pagina: int,
) -> int:
    import json

    from core.reports.teams_notify import build_teams_webhook_payload

    card = build_analistas_teams_card(
        title="[SUPERVISORES] Analistas disponíveis",
        gerado_em="00/00/0000 00:00",
        analistas=fatia,
        total=total,
        pagina=pagina,
        paginas=99,
    )
    payload = build_teams_webhook_payload(
        "[SUPERVISORES] Analistas disponíveis",
        build_analistas_teams_text(fatia),
        "https://example.environment.api.powerplatform.com/powerautomate/x",
        card=card,
        mention_geral=(pagina == 1),
    )
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def build_analistas_teams_card(
    *,
    title: str,
    gerado_em: str,
    analistas: Sequence[AnalistaDisponivel] | None = None,
    total: int | None = None,
    pagina: int = 1,
    paginas: int = 1,
) -> dict:
    lista = list(analistas or [])
    n_total = int(total if total is not None else len(lista))
    n_pag = max(1, int(paginas or 1))
    n_pagina = max(1, int(pagina or 1))
    if n_pag > 1:
        secao = f"analistas disponíveis ({n_total}) — {n_pagina}/{n_pag}"
        if n_pagina == 1:
            secao = f"@geral — {secao}"
    else:
        secao = f"@geral — analistas disponíveis ({n_total})"
    intro = (
        "Sem atendimento em andamento no portal agora. "
        "Nomes em férias/consultoria entram na blacklist."
    )
    body: list[dict] = [
        _teams_cabecalho(title, intro, gerado_em, estilo="accent"),
        _teams_section_title(secao),
    ]
    headers_a, rows_a = _analistas_linhas_tabela(lista)
    body.extend(_teams_tabela(headers_a, rows_a))
    body.append(_teams_rodape())
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.2",
        "msteams": {"width": "Full"},
        "body": body,
    }
