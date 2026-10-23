"""
Orquestração da exportação de certificados FortiGate (manual ou automação Concluído/Concluído).
Reutiliza carregar_contexto_atendimento e conexão SSH da coleta de logs.
"""
from __future__ import annotations

import base64
import html
import io
import os
import zipfile
from typing import Any, Optional

from prodesp.prodesp.caderno.caderno_teste_service import carregar_contexto_atendimento
from prodesp.prodesp.caderno.fgt_cert_exporter import CertExportResult, exportar_certificados_fgt
from prodesp.prodesp.historico import registrar_log


def pode_exportar_certificado(user, *, is_admin: bool) -> tuple[bool, str]:
    """Fase 1: apenas administradores."""
    if is_admin:
        return True, ""
    return False, "Exportação de certificado disponível apenas para administradores."


def _split_emails(raw: str) -> list[str]:
    return [e.strip() for e in (raw or "").replace(",", ";").split(";") if e.strip()]


def _parse_email_map_por_acronimo(raw: str) -> dict[str, list[str]]:
    """
    Formato (mesmo padrão de PRODESP_CERTIFICADO_NETWORK_DIRS):
      ACR=email1,email2;OUTRO=email3
    ';' separa acrônimos; ',' separa e-mails dentro do mesmo acrônimo.
    """
    result: dict[str, list[str]] = {}
    for chunk in (raw or "").split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _, emails = chunk.partition("=")
        acr = key.strip().upper()
        lst = [e.strip() for e in emails.split(",") if e.strip()]
        if acr and lst:
            result[acr] = lst
    return result


def _recipients_from_env(acronimo: str = "") -> list[str]:
    """
    Destinatários do certificado, por prioridade:
    1. PRODESP_CERTIFICADO_EMAIL_TO_ACRONIMOS (mapa por acrônimo, ex. POUPATEMPO=a@x;DER=b@y)
    2. PRODESP_CERTIFICADO_EMAIL_TO (lista global — comportamento anterior)
    3. PRODESP_GESTAO_RELATORIO_EMAIL_TO (fallback legado)
    """
    acr = (acronimo or "").strip().upper()
    if acr:
        mapped = _parse_email_map_por_acronimo(
            os.environ.get("PRODESP_CERTIFICADO_EMAIL_TO_ACRONIMOS") or ""
        )
        if acr in mapped:
            return mapped[acr]
    raw = (os.environ.get("PRODESP_CERTIFICADO_EMAIL_TO") or "").strip()
    if raw:
        return _split_emails(raw)
    raw2 = (os.environ.get("PRODESP_GESTAO_RELATORIO_EMAIL_TO") or "").strip()
    if raw2:
        return _split_emails(raw2)
    return []


def _cc_recipients_from_env(to_list: list[str]) -> list[str]:
    """Cópia fixa (PRODESP_CERTIFICADO_EMAIL_CC); remove quem já está no Para."""
    raw = (os.environ.get("PRODESP_CERTIFICADO_EMAIL_CC") or "").strip()
    to_lower = {e.lower() for e in to_list}
    return [e for e in _split_emails(raw) if e.lower() not in to_lower]


def _certificado_email_attach_mode() -> str:
    """
    zip = anexo .zip (teste para contornar bloqueio de .cer externo no Outlook).
    cer = anexo .cer direto (comportamento anterior).
    """
    raw = (os.environ.get("PRODESP_CERTIFICADO_EMAIL_ATTACH") or "zip").strip().lower()
    return raw if raw in ("zip", "cer") else "zip"


def _format_ip_lan_unidade(unidade: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, label in (
        ("ip_lan_01_unidades", "LAN 01"),
        ("mv_ip_lan_sec_unidades", "LAN SEC"),
        ("ip_lan_transito_unidades", "Trânsito"),
    ):
        val = (unidade.get(key) or "").strip()
        if val:
            parts.append(f"{label}: {val}")
    return " · ".join(parts) if parts else "—"


def _esc(val: object) -> str:
    return html.escape(str(val or "").strip() or "—")


def _linha_tabela_email(label: str, valor: object) -> str:
    return (
        f"<tr>"
        f"<td style='padding:8px 12px;border:1px solid #e0e0e0;background:#f8f9fa;"
        f"font-weight:600;width:38%;'>{html.escape(label)}</td>"
        f"<td style='padding:8px 12px;border:1px solid #e0e0e0;'>{_esc(valor)}</td>"
        f"</tr>"
    )


def build_certificado_email_subject(result: CertExportResult, unidade: dict[str, Any]) -> str:
    acr = (result.acronimo or unidade.get("acronimo_unidades") or "PRODESP").strip()
    host = (result.hostname or unidade.get("hostname_unidades") or "FortiGate").strip()
    id_vgr = (unidade.get("id_vgr_unidades") or "").strip()
    vgr_part = f" | VGR {id_vgr}" if id_vgr else ""
    return f"[PRODESP] Certificado FortiGate — {acr} | {host}{vgr_part}"


def build_certificado_email_html(result: CertExportResult, unidade: dict[str, Any]) -> str:
    from prodesp.prodesp.blueprint.agendamento_csv_notifier import build_email_assinatura_vita_html

    certs_ok = [it for it in result.items if it.ok]
    cert_lines = ""
    for it in certs_ok:
        metodo = f' <span style="color:#666;">({_esc(it.metodo)})</span>' if it.metodo else ""
        cert_lines += (
            f"<li><strong>{_esc(it.cert_name)}</strong> — {_esc(it.filename)}{metodo}</li>"
        )
    if not cert_lines:
        cert_lines = "<li>Nenhum certificado exportado.</li>"

    attach_mode = _certificado_email_attach_mode()
    attach_hint = (
        "O certificado segue compactado em <strong>.zip</strong> para facilitar o download "
        "em ambientes com política de segurança para anexos externos."
        if attach_mode == "zip"
        else "O certificado segue anexado no formato <strong>.cer</strong>."
    )

    return f"""
<div style="font-family:Calibri,Arial,sans-serif;font-size:14px;color:#333;max-width:720px;">
  <p>Olá,</p>
  <p>Segue a exportação do certificado FortiGate realizada pelo <strong>Portal PRODESP</strong>.</p>
  <p style="margin:16px 0;padding:12px 14px;background:#f4f0f8;border-left:4px solid #6b2d8a;">
    <strong>Certificado local FortiGate — {_esc(result.acronimo)}</strong><br>
    <span style="font-size:13px;color:#555;">{attach_hint}</span>
  </p>
  <table cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%;margin:12px 0 20px 0;">
    {_linha_tabela_email("Secretaria (acrônimo)", result.acronimo)}
    {_linha_tabela_email("Unidade", unidade.get("nome_unidades"))}
    {_linha_tabela_email("Hostname FortiGate", result.hostname)}
    {_linha_tabela_email("ID VGR", unidade.get("id_vgr_unidades"))}
    {_linha_tabela_email("ID Intragov", unidade.get("id_intragov_unidades"))}
    {_linha_tabela_email("IP LAN", _format_ip_lan_unidade(unidade))}
    {_linha_tabela_email("Loopback Vivo", result.loopback_ip)}
    {_linha_tabela_email("Tempo de exportação", f"{result.elapsed_seconds}s" if result.elapsed_seconds else "—")}
  </table>
  <p style="margin:0 0 6px 0;font-weight:600;">Arquivo(s) exportado(s):</p>
  <ul style="margin:0 0 16px 18px;padding:0;">{cert_lines}</ul>
  {build_email_assinatura_vita_html()}
</div>
""".strip()


def _content_type_certificado(path: str) -> str:
    ext = os.path.splitext(path or "")[1].lower()
    if ext == ".p12":
        return "application/x-pkcs12"
    if ext in (".cer", ".crt"):
        return "application/pkix-cert"
    return "application/octet-stream"


def _graph_file_attachment(path: str, filename: str, *, content_type: str = "") -> Optional[dict]:
    if not path or not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        raw = handle.read()
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": filename,
        "contentType": content_type or _content_type_certificado(path),
        "contentBytes": base64.b64encode(raw).decode("ascii"),
    }


def _graph_zip_attachment(path: str, inner_name: str, zip_name: str) -> Optional[dict]:
    if not path or not os.path.isfile(path):
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(path, arcname=inner_name or os.path.basename(path))
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": zip_name,
        "contentType": "application/zip",
        "contentBytes": base64.b64encode(buf.getvalue()).decode("ascii"),
    }


def _preparar_anexos_certificado(items: list) -> list[dict]:
    mode = _certificado_email_attach_mode()
    attachments: list[dict] = []
    for it in items:
        if not it.ok or not it.path_interno:
            continue
        inner = it.filename or os.path.basename(it.path_interno)
        if mode == "cer":
            att = _graph_file_attachment(it.path_interno, inner)
        else:
            stem, _ = os.path.splitext(inner)
            att = _graph_zip_attachment(it.path_interno, inner, f"{stem}.zip")
        if att:
            attachments.append(att)
    return attachments


def _enviar_email_certificados(
    result: CertExportResult,
    *,
    unidade: Optional[dict[str, Any]] = None,
) -> tuple[bool, str]:
    unidade = unidade or {}
    acronimo = (result.acronimo or unidade.get("acronimo_unidades") or "").strip()
    recipients = _recipients_from_env(acronimo)
    if not recipients:
        return False, "Destinatários de e-mail não configurados (PRODESP_CERTIFICADO_EMAIL_TO)."
    cc_recipients = _cc_recipients_from_env(recipients)

    attachments = _preparar_anexos_certificado(result.items)
    if not attachments:
        return False, "Nenhum arquivo de certificado para anexar ao e-mail."

    subject = build_certificado_email_subject(result, unidade)
    body_html = build_certificado_email_html(result, unidade)

    try:
        from prodesp.prodesp.blueprint.agendamento_csv_notifier import send_graph_html_email

        ok = send_graph_html_email(
            subject=subject,
            html_body=body_html,
            recipients=recipients,
            cc_recipients=cc_recipients,
            log_label="e-mail certificado FGT",
            extra_attachments=attachments,
            include_logo=True,
        )
        if ok:
            return True, ""
        return False, "Falha no envio de e-mail via Graph PRODESP (MS_GRAPH_* / PRODESP_AGENDAMENTO_EMAIL_FROM)."
    except Exception as exc:
        return False, str(exc) or type(exc).__name__


def _registrar_historico_exportacao(conn, id_atendimento: int, texto: str, *, automatico: bool = False) -> None:
    if automatico:
        prefixo = "Exportação automática (Status Concluído / Substatus Concluído)."
        texto = f"{prefixo}\n\n{texto}" if texto else prefixo
    registrar_log(
        conn,
        "atendimentos",
        id_atendimento,
        "Exportação de Certificado",
        "",
        texto,
        "INSERT",
    )


def exportar_certificados_atendimento(
    cursor,
    conn,
    id_atendimento: int,
    *,
    registrar_auditoria: bool = True,
    enviar_email: bool = True,
    automatico: bool = False,
    progress_cb=None,
) -> dict[str, Any]:
    """
    Função principal — UI manual (admin) ou automação ao Concluído/Concluído.
    """
    ctx = carregar_contexto_atendimento(cursor, id_atendimento)
    if not ctx:
        return {"ok": False, "message": "Atendimento não encontrado."}

    unidade = ctx.get("unidade") or {}
    loopback = (unidade.get("loopback_vivo_unidades") or "").strip()
    if not loopback:
        msg = "Loopback Vivo não cadastrado — necessário para conexão SSH."
        if registrar_auditoria:
            tmp = CertExportResult(ok=False)
            _registrar_historico_exportacao(
                conn, id_atendimento, tmp.historico_falha(msg), automatico=automatico
            )
            conn.commit()
        return {"ok": False, "message": msg}

    result = exportar_certificados_fgt(
        loopback,
        acronimo=(unidade.get("acronimo_unidades") or ""),
        hostname=(unidade.get("hostname_unidades") or ""),
        progress_cb=progress_cb,
    )

    email_ok = True
    email_msg = ""
    if result.ok and enviar_email:
        email_ok, email_msg = _enviar_email_certificados(result, unidade=unidade)
        if not email_ok:
            result.errors.append(f"E-mail: {email_msg}")

    if registrar_auditoria:
        if result.ok:
            hist = result.historico_sucesso()
            if not email_ok:
                hist += f"\n\nE-mail: não enviado — {email_msg}"
        else:
            motivo = "; ".join(result.errors) or "Falha desconhecida."
            hist = result.historico_falha(motivo)
        _registrar_historico_exportacao(conn, id_atendimento, hist, automatico=automatico)
        conn.commit()

    payload: dict[str, Any] = {
        "ok": result.ok,
        "message": "Exportação concluída." if result.ok else _mensagem_resposta_falha(result),
        "automatico": automatico,
        "hostname": result.hostname,
        "acronimo": result.acronimo,
        "loopback_ip": result.loopback_ip,
        "tftp_ip": result.tftp_ip,
        "elapsed_seconds": result.elapsed_seconds,
        "certificados": [
            {
                "nome": it.cert_name,
                "ok": it.ok,
                "arquivo": it.filename,
                "path_interno": it.path_interno,
                "path_externo": it.path_externo,
                "erro": it.error,
            }
            for it in result.items
        ],
        "errors": result.errors,
        "email_enviado": email_ok if enviar_email and result.ok else None,
    }
    return payload


def _mensagem_resposta_falha(result: CertExportResult) -> str:
    if result.errors:
        return result.errors[0]
    failed = [it for it in result.items if not it.ok and it.error]
    if failed:
        return failed[0].error
    return "Falha na exportação."
