"""
Relatório (portal + e-mail) da importação do CSV de agendamento VGR.

Espelha ``prodesp/prodesp/blueprint/agendamento_csv_notifier.py``, com a coluna
extra ``tipo_servico``. O envio usa ``core.integrations.email.EmailService``
(Microsoft Graph, assinatura corporativa padrão do portal), sem depender do
pacote PRODESP.

Variáveis de ambiente:
  VGR_AGENDAMENTO_CSV_EMAIL_ENABLED  — liga/desliga (default: on)
  VGR_AGENDAMENTO_CSV_EMAIL_TO       — destinatários (`,` ou `;`);
                                       vazio → MICROSOFT_EMAIL_TO do core
"""
from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from vgr.vgr.operacao.agendamento_csv_validacao import motivo_agendamento_csv_corrigivel

logger = logging.getLogger("VGR.agendamento_csv")


@dataclass
class AgendamentoCsvLinha:
    id_vgr: str
    tipo_servico: Optional[str] = None
    data_agendamento: Optional[str] = None
    hora_agendamento: Optional[str] = None
    contratada: Optional[str] = None
    field: Optional[str] = None
    contato_field: Optional[str] = None
    detalhe: str = ""


@dataclass
class AgendamentoCsvRelatorio:
    sucessos: list[AgendamentoCsvLinha] = field(default_factory=list)
    repetidos: list[AgendamentoCsvLinha] = field(default_factory=list)
    erros: list[AgendamentoCsvLinha] = field(default_factory=list)
    rejeitadas_previa: list[AgendamentoCsvLinha] = field(default_factory=list)
    usuario_upload: str = ""
    total_linhas_arquivo: int = 0


# ---------------------------------------------------------------------------
# Linhas (payload ↔ dataclass ↔ export)
# ---------------------------------------------------------------------------


def _txt(row: dict[str, Any], key: str) -> Optional[str]:
    val = row.get(key)
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def linha_from_row(row: dict[str, Any]) -> AgendamentoCsvLinha:
    return AgendamentoCsvLinha(
        id_vgr=str(row.get("id_vgr") or "").strip(),
        tipo_servico=_txt(row, "tipo_servico"),
        data_agendamento=_txt(row, "data_agendamento"),
        hora_agendamento=_txt(row, "hora_agendamento"),
        contratada=_txt(row, "contratada"),
        field=_txt(row, "field"),
        contato_field=_txt(row, "contato_field"),
    )


def erro_linha(linha: AgendamentoCsvLinha, motivo: str) -> AgendamentoCsvLinha:
    return AgendamentoCsvLinha(
        id_vgr=linha.id_vgr,
        tipo_servico=linha.tipo_servico,
        data_agendamento=linha.data_agendamento,
        hora_agendamento=linha.hora_agendamento,
        contratada=linha.contratada,
        field=linha.field,
        contato_field=linha.contato_field,
        detalhe=motivo,
    )


def _format_data_br(data_iso: Optional[str]) -> str:
    if not data_iso:
        return "—"
    try:
        return datetime.strptime(str(data_iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(data_iso)


def _format_hora_br(hora: Optional[str]) -> str:
    if not hora:
        return "—"
    h = str(hora).strip()
    if len(h) >= 5 and h[2] == ":":
        return h[:5]
    if len(h) >= 4 and h[1] == ":":
        return "0" + h[:4]
    return h


def linha_export_dict(linha: AgendamentoCsvLinha) -> dict[str, Any]:
    """Formato devolvido ao front (Baixar não aplicadas / Corrigir no portal)."""
    data_br = _format_data_br(linha.data_agendamento) if linha.data_agendamento else ""
    return {
        "id_vgr": linha.id_vgr or "",
        "tipo_servico": linha.tipo_servico or "",
        "data_agendamento": data_br if data_br != "—" else "",
        "hora_agendamento": _format_hora_br(linha.hora_agendamento)
        if linha.hora_agendamento
        else "",
        "contratada": linha.contratada or "",
        "field": linha.field or "",
        "contato_field": linha.contato_field or "",
        "motivo": linha.detalhe or "",
        "corrigivel": motivo_agendamento_csv_corrigivel(linha.detalhe),
    }


def parse_rejeitadas_previa_payload(
    rows: Any,
    *,
    max_items: int = 500,
) -> list[AgendamentoCsvLinha]:
    """Linhas rejeitadas no portal antes do envio — só para relatório."""
    if not isinstance(rows, list):
        return []
    out: list[AgendamentoCsvLinha] = []
    for row in rows[:max_items]:
        if not isinstance(row, dict):
            continue
        linha = linha_from_row(row)
        if not linha.id_vgr:
            continue
        motivo = str(
            row.get("motivo") or "Rejeitada na pré-validação (não enviada ao processamento)."
        ).strip()
        if len(motivo) > 500:
            motivo = motivo[:497] + "..."
        out.append(erro_linha(linha, motivo))
    return out


# ---------------------------------------------------------------------------
# Resumo / e-mail
# ---------------------------------------------------------------------------


def build_resumo_agendamento_csv(
    *,
    sucessos: int,
    repetidos: int,
    erros: int,
    rejeitadas_previa: int = 0,
) -> str:
    texto = (
        f"Resumo: {sucessos} unidade(s) agendada(s) com sucesso · "
        f"{repetidos} unidade(s) já agendada(s) · "
        f"{erros} unidade(s) não agendada(s)"
    )
    if rejeitadas_previa:
        texto += (
            f" · {rejeitadas_previa} rejeitada(s) na pré-validação "
            "(não enviadas ao processamento)"
        )
    return texto


def build_resumo_from_relatorio(relatorio: AgendamentoCsvRelatorio) -> str:
    return build_resumo_agendamento_csv(
        sucessos=len(relatorio.sucessos),
        repetidos=len(relatorio.repetidos),
        erros=len(relatorio.erros),
        rejeitadas_previa=len(relatorio.rejeitadas_previa),
    )


def build_subject(relatorio: AgendamentoCsvRelatorio) -> str:
    partes = [
        f"{len(relatorio.sucessos)} agendada(s) com sucesso",
        f"{len(relatorio.repetidos)} já agendada(s)",
        f"{len(relatorio.erros)} não agendada(s)",
    ]
    if relatorio.rejeitadas_previa:
        partes.append(f"{len(relatorio.rejeitadas_previa)} rejeitada(s) na prévia")
    return "[VGR] Agendamento Portal — " + " | ".join(partes)


_TABLE_STYLE = (
    "border-collapse: collapse; width: 100%; margin: 8px 0 20px 0; "
    "font-size: 13px; font-family: Calibri, Arial, sans-serif;"
)
_TH_STYLE = (
    "background: #6b2d8a; color: #fff; padding: 10px 12px; text-align: left; "
    "font-weight: 600; border: 1px solid #5a2572;"
)
_TD_STYLE = "padding: 8px 12px; border: 1px solid #e2e2e2; color: #333; vertical-align: top;"
_TD_ALT_STYLE = _TD_STYLE + " background: #faf8fc;"


def _cel(linha: AgendamentoCsvLinha, attr: str, formatter=None) -> str:
    val = getattr(linha, attr, None)
    text = formatter(val) if formatter else (str(val).strip() if val else "—")
    return html.escape(text)


def _tabela_linhas_html(linhas: list[AgendamentoCsvLinha], *, incluir_motivo: bool) -> str:
    headers = ["ID VGR", "Serviço", "Data Agend.", "Hora", "Contratada", "Field"]
    if incluir_motivo:
        headers.append("Motivo")
    head = "".join(f"<th style='{_TH_STYLE}'>{html.escape(h)}</th>" for h in headers)
    body = []
    for idx, linha in enumerate(linhas):
        td = _TD_ALT_STYLE if idx % 2 else _TD_STYLE
        cells = [
            _cel(linha, "id_vgr"),
            _cel(linha, "tipo_servico"),
            _cel(linha, "data_agendamento", _format_data_br),
            _cel(linha, "hora_agendamento", _format_hora_br),
            _cel(linha, "contratada"),
            _cel(linha, "field"),
        ]
        if incluir_motivo:
            cells.append(_cel(linha, "detalhe"))
        body.append("<tr>" + "".join(f"<td style='{td}'>{c}</td>" for c in cells) + "</tr>")
    return (
        f"<table style='{_TABLE_STYLE}' cellpadding='0' cellspacing='0'>"
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _secao_tabela_html(
    titulo: str,
    linhas: list[AgendamentoCsvLinha],
    vazio: str,
    *,
    incluir_motivo: bool = False,
) -> str:
    h3 = "margin: 20px 0 6px 0; font-size: 15px; color: #6b2d8a;"
    if not linhas:
        return (
            f"<h3 style='{h3}'>{html.escape(titulo)}</h3>"
            f"<p style='color: #666; margin: 0 0 12px 0;'>{html.escape(vazio)}</p>"
        )
    return (
        f"<h3 style='{h3}'>{html.escape(titulo)} "
        f"<span style='color:#888;font-weight:normal;'>({len(linhas)})</span></h3>"
        f"{_tabela_linhas_html(linhas, incluir_motivo=incluir_motivo)}"
    )


def build_email_html(relatorio: AgendamentoCsvRelatorio, *, agora: datetime | None = None) -> str:
    if agora is None:
        try:
            import pytz

            agora = datetime.now(pytz.timezone("America/Sao_Paulo"))
        except Exception:
            agora = datetime.now()
    usuario = html.escape(relatorio.usuario_upload or "Portal VGR")
    resumo = html.escape(build_resumo_from_relatorio(relatorio))
    return f"""
<div style="font-family: Calibri, Arial, sans-serif; font-size: 14px; color: #333;">
  <p>Olá,</p>
  <p>Segue o resumo do upload do <strong>CSV de Agendamento VGR</strong> realizado em
     <strong>{agora.strftime('%d/%m/%Y %H:%M')}</strong> por <strong>{usuario}</strong>.</p>
  <p style="margin: 16px 0; padding: 12px; background: #f4f0f8; border-left: 4px solid #6b2d8a;">
    <strong>{resumo}</strong>
  </p>
  {_secao_tabela_html("Unidades agendadas com sucesso", relatorio.sucessos,
                      "Nenhuma unidade agendada neste upload.", incluir_motivo=True)}
  {_secao_tabela_html("Unidades já agendadas", relatorio.repetidos,
                      "Nenhuma unidade com agendamento repetido.", incluir_motivo=True)}
  {_secao_tabela_html("Unidades não agendadas", relatorio.erros,
                      "Nenhuma falha registrada.", incluir_motivo=True)}
  {_secao_tabela_html("Rejeitadas na pré-validação (não enviadas)", relatorio.rejeitadas_previa,
                      "Nenhuma linha ficou rejeitada na pré-visualização do portal.",
                      incluir_motivo=True)}
</div>
""".strip()


def _env_bool(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "sim", "on")


def _recipients_from_env() -> list[str]:
    raw = (os.getenv("VGR_AGENDAMENTO_CSV_EMAIL_TO") or "").strip()
    if not raw:
        return []  # EmailService cai em MICROSOFT_EMAIL_TO
    return [e.strip() for e in raw.replace(",", ";").split(";") if e.strip()]


def send_agendamento_csv_report(relatorio: AgendamentoCsvRelatorio) -> bool:
    """Envia o relatório. Falha silenciosa (log) — nunca desfaz o upload."""
    if not _env_bool("VGR_AGENDAMENTO_CSV_EMAIL_ENABLED", default=True):
        logger.info("vgr - e-mail CSV agendamento desabilitado (VGR_AGENDAMENTO_CSV_EMAIL_ENABLED)")
        return False
    try:
        from core.integrations.email import EmailService

        res = EmailService().send_email(
            subject=build_subject(relatorio),
            body=build_email_html(relatorio),
            recipients=_recipients_from_env(),
            content_type="HTML",
        )
    except Exception:
        logger.warning("vgr - falha ao enviar e-mail do CSV de agendamento", exc_info=True)
        return False
    if not res.get("success"):
        logger.warning("vgr - e-mail CSV agendamento não enviado: %s", res.get("message"))
        return False
    return True
