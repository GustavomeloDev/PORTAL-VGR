"""Envio ao Teams com o que já existe no Graph (caqimplantacao).

Forma prática (sem permissão extra no Azure):
  1) Fluxo Power Automate / Incoming Webhook → SUPERVISORES_MACRO_TEAMS_WEBHOOK_URL
  2) E-mail do canal Teams → SUPERVISORES_MACRO_TEAMS_EMAIL (usa Mail.Send já liberado)

ChannelMessage.Send no app Graph exigiria GMUD de permissão; não é necessário.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from core.reports.env_config import teams_channel_email, teams_webhook_url

logger = logging.getLogger(__name__)

_POWER_AUTOMATE_HOST_MARKERS = (
    "powerplatform.com",
    "logic.azure.com",
    "azurewebsites.net",
)
_POWER_AUTOMATE_PATH_MARKERS = (
    "/powerautomate/",
    "/workflows/",
    "/triggers/manual/",
)


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "")[:80]
    except Exception:
        return ""


def is_power_automate_webhook(url: str) -> bool:
    """URL de fluxo Power Automate (não o conector Incoming Webhook legado)."""
    raw = (url or "").strip().lower()
    if not raw:
        return False
    host = _host_of(raw)
    if any(m in host for m in _POWER_AUTOMATE_HOST_MARKERS):
        return True
    return any(m in raw for m in _POWER_AUTOMATE_PATH_MARKERS)


def _adaptive_card(title: str, text: str) -> dict[str, Any]:
    """Cartão exigido pelo PostCardToConversation (type deve ser AdaptiveCard)."""
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.2",
        "body": [
            {
                "type": "TextBlock",
                "text": title,
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": text or title,
                "wrap": True,
            },
        ],
    }


def build_teams_webhook_payload(
    title: str,
    text: str,
    webhook_url: str,
    card: Optional[dict[str, Any]] = None,
    *,
    mention_geral: bool = False,
) -> dict[str, Any]:
    title_safe = (title or "")[:180]
    body = text or ""
    extra = {}
    if mention_geral:
        extra["mentionChannel"] = True
        extra["mentionText"] = "@geral"
    if is_power_automate_webhook(webhook_url):
        # Modelo "Enviar alertas de webhook para um canal":
        # - Attachments null → Post_card_1 usa string(Body) → Body.tipo = AdaptiveCard
        # - Attachments preenchido → For each usa item()['content'] → AdaptiveCard
        inner = card if isinstance(card, dict) and card.get("type") == "AdaptiveCard" else _adaptive_card(
            title_safe, body
        )
        # Cartão grande (fila + analistas) não pode ir duplicado: o fluxo usa
        # attachments[].content no For each. A raiz fica um AdaptiveCard curto
        # (Body.tipo = AdaptiveCard) para o ramo "Attachments is null".
        raiz = _adaptive_card(title_safe, (body or title_safe)[:400])
        return {
            **raiz,
            **extra,
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": inner,
                }
            ],
        }
    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": "6b2d8a",
        "summary": title_safe,
        "title": title_safe,
        "text": body,
    }
    payload.update(extra)
    return payload


def send_teams_webhook(
    title: str,
    text: str,
    webhook_url: Optional[str] = None,
    *,
    card: Optional[dict[str, Any]] = None,
    mention_geral: bool = False,
) -> bool:
    url = (webhook_url if webhook_url is not None else teams_webhook_url()).strip()
    if not url:
        logger.debug("supervisores - Teams webhook não configurado")
        return False
    if not url.startswith("https://"):
        logger.warning("supervisores - Teams webhook inválido (exige https)")
        return False
    payload = build_teams_webhook_payload(
        title, text, url, card=card, mention_geral=mention_geral
    )
    try:
        nbytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if nbytes > 24000:
            logger.warning(
                "supervisores - Teams payload grande (%s bytes) host=%s",
                nbytes,
                _host_of(url),
            )
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code in (200, 201, 202):
            logger.info(
                "supervisores - Teams webhook enviado (%s) host=%s bytes=%s",
                title[:80],
                _host_of(url),
                nbytes,
            )
            return True
        snippet = (resp.text or "").replace("\n", " ")[:180]
        logger.warning(
            "supervisores - Teams webhook HTTP %s host=%s body=%s",
            resp.status_code,
            _host_of(url),
            snippet,
        )
    except requests.RequestException as exc:
        logger.warning("supervisores - Teams webhook erro de rede")
        logger.debug("supervisores - Teams webhook detalhe: %s", type(exc).__name__)
    return False


def send_macro_teams_email(subject: str, html_body: str) -> bool:
    """Usa Mail.Send da caixa caqimplantacao para o e-mail do canal Teams."""
    dest = teams_channel_email()
    if not dest:
        return False
    from prodesp.prodesp.blueprint.agendamento_csv_notifier import send_graph_html_email

    return send_graph_html_email(
        subject=subject,
        html_body=html_body,
        recipients=[dest],
        log_label="relatório SUPERVISORES Teams (e-mail do canal)",
        extra_attachments=None,
        include_logo=True,
    )
