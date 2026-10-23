"""
Notificação por e-mail após importação do CSV de agendamentos PRODESP (Microsoft Graph).
"""
from __future__ import annotations

import base64
import html
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import msal
import pytz
import requests

logger = logging.getLogger(__name__)

LOGO_VITA_CID = "logo_vita_email"

DEFAULT_RECIPIENTS = [
    "fabiana.cruz@telefonica.com",
    "vitoria.nnascimento@telefonica.com",
    "celso.previato@telefonica.com",
    "CAQ.vita.br@telefonica.com",
]


@dataclass
class AgendamentoCsvLinha:
    id_vgr: str
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


def _env_bool(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "sim", "on")


def _recipients_from_env() -> list[str]:
    raw = (os.getenv("PRODESP_AGENDAMENTO_CSV_EMAIL_TO") or "").strip()
    if raw:
        return [e.strip() for e in raw.replace(",", ";").split(";") if e.strip()]
    return list(DEFAULT_RECIPIENTS)


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
    return h


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
    if formatter:
        text = formatter(val)
    else:
        text = str(val).strip() if val else "—"
    return html.escape(text)


def _tabela_linhas_html(
    linhas: list[AgendamentoCsvLinha],
    *,
    incluir_motivo: bool = False,
) -> str:
    headers = [
        "ID VGR",
        "Data Agend.",
        "Hora",
        "Contratada",
        "Field",
    ]
    if incluir_motivo:
        headers.append("Motivo")

    head_cells = "".join(f"<th style='{_TH_STYLE}'>{html.escape(h)}</th>" for h in headers)
    body_rows = []
    for idx, linha in enumerate(linhas):
        td_style = _TD_ALT_STYLE if idx % 2 else _TD_STYLE
        cells = [
            _cel(linha, "id_vgr"),
            _cel(linha, "data_agendamento", _format_data_br),
            _cel(linha, "hora_agendamento", _format_hora_br),
            _cel(linha, "contratada"),
            _cel(linha, "field"),
        ]
        if incluir_motivo:
            cells.append(_cel(linha, "detalhe"))
        row_html = "".join(f"<td style='{td_style}'>{c}</td>" for c in cells)
        body_rows.append(f"<tr>{row_html}</tr>")

    return (
        f"<table style='{_TABLE_STYLE}' cellpadding='0' cellspacing='0'>"
        f"<thead><tr>{head_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def _secao_tabela_html(titulo: str, linhas: list[AgendamentoCsvLinha], vazio: str, *, incluir_motivo: bool = False) -> str:
    if not linhas:
        return (
            f"<h3 style='margin: 20px 0 6px 0; font-size: 15px; color: #6b2d8a;'>{html.escape(titulo)}</h3>"
            f"<p style='color: #666; margin: 0 0 12px 0;'>{html.escape(vazio)}</p>"
        )
    return (
        f"<h3 style='margin: 20px 0 6px 0; font-size: 15px; color: #6b2d8a;'>"
        f"{html.escape(titulo)} <span style='color:#888;font-weight:normal;'>({len(linhas)})</span></h3>"
        f"{_tabela_linhas_html(linhas, incluir_motivo=incluir_motivo)}"
    )


def _logo_vita_path() -> Optional[Path]:
    """
    Logo da assinatura PRODESP — prodesp/static/img/logo_vita_email.png.
    Usa PRODESP_DIR (raiz do módulo) para não quebrar se o .py mudar de subpasta.
    """
    try:
        from prodesp.config_paths import PRODESP_DIR

        base = Path(PRODESP_DIR)
    except ImportError:
        # fallback: blueprint/ → prodesp/prodesp/ → prodesp/
        base = Path(__file__).resolve().parents[2]
    logo_path = base / "static" / "img" / "logo_vita_email.png"
    return logo_path if logo_path.is_file() else None


def _logo_vita_img_tag() -> str:
    """Referência cid: — Outlook/Graph não exibem data URI inline no corpo HTML."""
    if not _logo_vita_path():
        return "<span style='font-weight:bold;color:#6b2d8a;font-size:18px;'>Vita</span>"
    return (
        f'<img src="cid:{LOGO_VITA_CID}" alt="Vita" width="120" '
        'style="display:block;border:0;max-width:120px;height:auto;">'
    )


def _logo_vita_inline_attachment() -> Optional[dict[str, Any]]:
    logo_path = _logo_vita_path()
    if not logo_path:
        return None
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": logo_path.name,
        "contentType": "image/png",
        "contentBytes": base64.b64encode(logo_path.read_bytes()).decode("ascii"),
        "isInline": True,
        "contentId": LOGO_VITA_CID,
    }


def build_email_assinatura_vita_html() -> str:
    """Assinatura padrão CAQ/Vita (logo cid + endereço) — reutilizada nos e-mails PRODESP."""
    return f"""
  <p style="margin-top: 24px;">Permaneço à disposição para quaisquer esclarecimentos adicionais.</p>
  <p>Atenciosamente,</p>
  <table cellpadding="0" cellspacing="0" style="margin-top: 8px; font-family: Calibri, Arial, sans-serif;">
    <tr>
      <td style="padding-right: 16px; vertical-align: top;">
        {_logo_vita_img_tag()}
      </td>
      <td style="vertical-align: top; font-size: 13px; color: #444; line-height: 1.45;">
        <strong style="color: #222; font-size: 14px;">CAQ - AIOPS</strong><br>
        Av. Dr. Chucri Zaidan, 860 - 2º andar – Lado A - Morumbi<br>
        CEP: 04583-110 | São Paulo – SP<br>
        <a href="mailto:caqimplantacao@vitait.com" style="color: #6b2d8a;">caqimplantacao@vitait.com</a><br>
        <a href="https://www.vitait.com" style="color: #6b2d8a;">www.vitait.com</a>
      </td>
    </tr>
  </table>
""".strip()


def build_resumo_agendamento_csv(
    *,
    sucessos: int,
    repetidos: int,
    erros: int,
    rejeitadas_previa: int = 0,
) -> str:
    """Texto único de resumo (portal + e-mail)."""
    texto = (
        f"Resumo: {sucessos} unidade(s) agendada(s) com sucesso · "
        f"{repetidos} unidade(s) já agendada(s) · "
        f"{erros} unidade(s) não agendada(s)"
    )
    if rejeitadas_previa:
        texto += (
            f" · {rejeitadas_previa} rejeitada(s) na pré-validação "
            f"(não enviadas ao processamento)"
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
    n_ok = len(relatorio.sucessos)
    n_rep = len(relatorio.repetidos)
    n_err = len(relatorio.erros)
    n_prev = len(relatorio.rejeitadas_previa)
    partes = [
        f"{n_ok} agendada(s) com sucesso",
        f"{n_rep} já agendada(s)",
        f"{n_err} não agendada(s)",
    ]
    if n_prev:
        partes.append(f"{n_prev} rejeitada(s) na prévia")
    return f"[PRODESP] Agendamento Portal — " + " | ".join(partes)


def build_email_html(relatorio: AgendamentoCsvRelatorio) -> str:
    tz_sp = pytz.timezone("America/Sao_Paulo")
    agora = datetime.now(tz_sp).strftime("%d/%m/%Y %H:%M")
    usuario = html.escape(relatorio.usuario_upload or "Portal PRODESP")

    corpo = f"""
<div style="font-family: Calibri, Arial, sans-serif; font-size: 14px; color: #333;">
  <p>Olá,</p>
  <p>Segue o resumo do upload do <strong>CSV de Agendamento PRODESP</strong> realizado em
     <strong>{agora}</strong> por <strong>{usuario}</strong>.</p>
  <p style="margin: 16px 0; padding: 12px; background: #f4f0f8; border-left: 4px solid #6b2d8a;">
    <strong>{html.escape(build_resumo_from_relatorio(relatorio))}</strong>
  </p>
  {_secao_tabela_html("Unidades agendadas com sucesso", relatorio.sucessos, "Nenhuma unidade agendada neste upload.")}
  {_secao_tabela_html(
      "Unidades já agendadas",
      relatorio.repetidos,
      "Nenhuma unidade com agendamento repetido.",
      incluir_motivo=True,
  )}
  {_secao_tabela_html(
      "Unidades não agendadas",
      relatorio.erros,
      "Nenhuma falha registrada.",
      incluir_motivo=True,
  )}
  {_secao_tabela_html(
      "Rejeitadas na pré-validação (não enviadas)",
      relatorio.rejeitadas_previa,
      "Nenhuma linha ficou rejeitada na pré-visualização do portal.",
      incluir_motivo=True,
  )}
  {build_email_assinatura_vita_html()}
</div>
"""
    return corpo.strip()


def _graph_access_token() -> Optional[str]:
    client_id = (os.getenv("MS_GRAPH_CLIENT_ID") or os.getenv("CLIENT_ID") or "").strip()
    client_secret = (os.getenv("MS_GRAPH_CLIENT_SECRET") or os.getenv("CLIENT_SECRET") or "").strip()
    tenant_id = (os.getenv("MS_GRAPH_TENANT_ID") or os.getenv("TENANT_ID") or "").strip()
    if not all([client_id, client_secret, tenant_id]):
        logger.warning("prodesp - e-mail agendamento CSV: credenciais Graph ausentes no .env")
        return None

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if not result or "access_token" not in result:
        err = (result or {}).get("error_description") or (result or {}).get("error") or "token indisponível"
        logger.warning("prodesp - e-mail agendamento CSV: falha ao obter token Graph: %s", err)
        return None
    return result["access_token"]


def send_graph_html_email(
    *,
    subject: str,
    html_body: str,
    recipients: list[str],
    cc_recipients: Optional[list[str]] = None,
    log_label: str = "e-mail Graph",
    extra_attachments: Optional[list[dict[str, Any]]] = None,
    include_logo: bool = True,
) -> bool:
    """Envia HTML via Microsoft Graph (sendMail). Falha silenciosa com log."""
    token = _graph_access_token()
    if not token:
        return False

    from_email = (
        os.getenv("PRODESP_AGENDAMENTO_EMAIL_FROM")
        or os.getenv("EMAIL_FROM")
        or "caqimplantacao@vitait.com"
    ).strip()
    if not recipients:
        logger.warning("prodesp - %s: nenhum destinatário configurado", log_label)
        return False

    message: dict[str, Any] = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": html_body},
        "toRecipients": [
            {"emailAddress": {"address": addr}} for addr in recipients
        ],
    }
    if cc_recipients:
        message["ccRecipients"] = [
            {"emailAddress": {"address": addr}} for addr in cc_recipients
        ]
    attachments: list[dict[str, Any]] = []
    if include_logo:
        logo_att = _logo_vita_inline_attachment()
        if logo_att:
            attachments.append(logo_att)
    if extra_attachments:
        attachments.extend(extra_attachments)
    if attachments:
        message["attachments"] = attachments

    payload = {"message": message, "saveToSentItems": True}
    url = f"https://graph.microsoft.com/v1.0/users/{from_email}/sendMail"
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        if resp.status_code in (200, 202):
            logger.info(
                "prodesp - %s enviado para %s (%s)",
                log_label,
                ", ".join(recipients),
                subject,
            )
            return True
        req_id = resp.headers.get("request-id") or resp.headers.get("client-request-id") or ""
        logger.warning(
            "prodesp - %s falhou HTTP %s (Graph sendMail)%s",
            log_label,
            resp.status_code,
            f" request-id={req_id}" if req_id else "",
        )
    except requests.RequestException as exc:
        logger.warning("prodesp - %s erro de rede: %s", log_label, exc)
    return False


def send_agendamento_csv_report(relatorio: AgendamentoCsvRelatorio) -> bool:
    """Envia relatório por e-mail. Falha silenciosa (log) — não interrompe o upload."""
    if not _env_bool("PRODESP_AGENDAMENTO_CSV_EMAIL_ENABLED", default=True):
        logger.info("prodesp - e-mail agendamento CSV desabilitado (PRODESP_AGENDAMENTO_CSV_EMAIL_ENABLED)")
        return False

    recipients = _recipients_from_env()
    return send_graph_html_email(
        subject=build_subject(relatorio),
        html_body=build_email_html(relatorio),
        recipients=recipients,
        log_label="e-mail agendamento CSV",
    )


def linha_from_row(row: dict[str, Any]) -> AgendamentoCsvLinha:
    return AgendamentoCsvLinha(
        id_vgr=str(row.get("id_vgr") or "").strip(),
        data_agendamento=row.get("data_agendamento"),
        hora_agendamento=row.get("hora_agendamento"),
        contratada=(row.get("contratada") or "").strip() or None,
        field=(row.get("field") or "").strip() or None,
        contato_field=(row.get("contato_field") or "").strip() or None,
    )


def erro_linha(linha: AgendamentoCsvLinha, motivo: str) -> AgendamentoCsvLinha:
    copia = AgendamentoCsvLinha(
        id_vgr=linha.id_vgr,
        data_agendamento=linha.data_agendamento,
        hora_agendamento=linha.hora_agendamento,
        contratada=linha.contratada,
        field=linha.field,
        contato_field=linha.contato_field,
        detalhe=motivo,
    )
    return copia


def parse_rejeitadas_previa_payload(
    rows: Any,
    *,
    max_items: int = 500,
) -> list[AgendamentoCsvLinha]:
    """Linhas rejeitadas no portal antes do envio — só para relatório por e-mail."""
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
            row.get("motivo")
            or "Rejeitada na pré-validação (não enviada ao processamento)."
        ).strip()
        if len(motivo) > 500:
            motivo = motivo[:497] + "..."
        out.append(erro_linha(linha, motivo))
    return out
