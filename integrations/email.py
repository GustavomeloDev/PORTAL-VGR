"""core.integrations.email

Fornece autenticação via Microsoft Graph (MSAL) e envio de e-mails HTML com
assinatura corporativa Vita e logo embutido como anexo CID.

Classes:
    GraphAuthService      — Obtém access token para o Microsoft Graph API.
    EmailTemplateService  — Monta o corpo HTML com assinatura e logo.
    EmailService          — Envia e-mails via POST /sendMail do Graph API.

Variáveis de ambiente necessárias:
    MICROSOFT_CLIENT_ID      — Client ID do app Azure AD.
    MICROSOFT_CLIENT_SECRET  — Client secret do app Azure AD.
    MICROSOFT_TENANT_ID      — Tenant ID do Azure AD.
    MICROSOFT_EMAIL_FROM     — Endereço remetente (caixa de saída no Graph).
    MICROSOFT_EMAIL_TO       — Destinatário(s) padrão (separados por vírgula ou ponto-e-vírgula).
    EMAIL_SIGNATURE_ENABLED  — Habilita assinatura corporativa (\"true\"/\"false\", padrão: true).
"""
import os
from core.logger import get_logger
import requests
import base64

# Configuração básica de logging
logging = get_logger("CORE")


class GraphAuthService:
    """Autentica no Azure AD via MSAL e fornece access token para o Microsoft Graph."""

    def __init__(self):
        self.client_id = os.getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        self.tenant_id = os.getenv("MICROSOFT_TENANT_ID")
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}" if self.tenant_id else None
        self.scope = ["https://graph.microsoft.com/.default"]

    def validate_env(self):
        """Verifica se as variáveis de ambiente de autenticação estão definidas.

        Returns:
            tuple[bool, str | None]: (True, None) se válido;
                (False, mensagem_de_erro) caso contrário.
        """
        missing = []
        if not self.client_id:
            missing.append("MICROSOFT_CLIENT_ID")
        if not self.client_secret:
            missing.append("MICROSOFT_CLIENT_SECRET")
        if not self.tenant_id:
            missing.append("MICROSOFT_TENANT_ID")
        if missing:
            return False, f"Variáveis ausentes: {', '.join(missing)}"
        return True, None

    def get_token(self):
        """Obtém access token para o Microsoft Graph API via client credentials.

        Returns:
            tuple[str | None, str | None]: (access_token, None) em sucesso;
                (None, mensagem_de_erro) em falha.
        """
        try:
            if not self.client_id or not self.client_secret or not self.tenant_id:
                 return None, "Configurações de autenticação incompletas."
            
            try:
                import msal
            except ImportError:
                return None, "Dependência 'msal' não encontrada."

            app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=self.authority,
                client_credential=self.client_secret,
            )
            token = app.acquire_token_for_client(scopes=self.scope)
            if not token or "access_token" not in token:
                return None, "Falha ao obter token de acesso do Microsoft Graph."
            return token["access_token"], None
        except Exception as e:
            return None, f"Erro ao autenticar: {str(e)}"


class EmailTemplateService:
    """Monta o corpo do e-mail HTML com assinatura corporativa e logo embutido (CID)."""

    def __init__(self):
        self.signature_enabled = (os.getenv("EMAIL_SIGNATURE_ENABLED", "true").lower() == "true")
        self.signature_html = (
            '<div style="margin-top:12px;">'
            '<table role="presentation" style="border:none; border-collapse:collapse;">'
            '<tr>'
            '<td colspan="2" style="font-family:Arial, sans-serif; font-size:12px; padding:0 0 8px 0; color:#000000;">Este é um e-mail automático.</td>'
            '</tr>'
            '<tr>'
            '<td style="vertical-align:middle; padding-right:16px; width:180px;">'
            '<img src="cid:logo" alt="Vita" style="width:160px; height:auto;">'
            '</td>'
            '<td style="vertical-align:middle; font-family:Arial, sans-serif; font-size:12px; color:#000000;">'
            '<div style="line-height:1.6;">'
            '<div style="margin-bottom:6px;">Atenciosamente,</div>'
            '<div><b>Central de Agendamentos Implantação - Vivo Vita</b></div>'
            '<div>Av. Dr. Chucri Zaidan, 860, 2º andar – Lado A</div>'
            '<div>CEP: 04583-110 | São Paulo - SP</div>'
            '<div><a href="https://www.vitait.com" style="color:#0066cc; text-decoration:underline;">www.vitait.com</a></div>'
            '</div>'
            '</td>'
            '</tr>'
            '</table>'
            '</div>'
        )

    def format_body(self, body, content_type="Text"):
        """Combina o corpo com a assinatura HTML corporativa.

        Args:
            body (str): Conteúdo do e-mail.
            content_type (str): \"HTML\" ou \"Text\". Se \"Text\", converte para HTML
                automaticamente ao adicionar a assinatura.

        Returns:
            tuple[str, str]: (corpo_final, content_type_final)
        """
        ct = (content_type or "Text").upper()
        if not self.signature_enabled:
            return (body or ""), ct
        if ct == "HTML":
            return (body or "") + self.signature_html, "HTML"
        return "<div>" + (body or "") + "</div>" + self.signature_html, "HTML"

    def get_logo_attachment(self):
        """Gera o dicionário de anexo inline (CID) com o logo Vita.

        Procura por `vita_colorido.png` e, como fallback, `vita_logo.png` em
        `login/static/img/`.

        Returns:
            dict | None: Dicionário no formato Graph API `fileAttachment`, ou
                None se o arquivo não for encontrado.
        """
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            p1 = os.path.join(base_dir, "login", "static", "img", "vita_colorido.png")
            p2 = os.path.join(base_dir, "login", "static", "img", "vita_logo.png")
            path = p1 if os.path.exists(p1) else p2 if os.path.exists(p2) else None
            
            if not path:
                return None
            
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            
            return {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": os.path.basename(path),
                "contentType": "image/png",
                "isInline": True,
                "contentId": "logo",
                "contentBytes": b64,
            }
        except Exception:
            return None


class EmailService:
    """Envia e-mails via Microsoft Graph API (POST /sendMail).

    Combina autenticação (GraphAuthService) com montagem do template (EmailTemplateService)
    para fornecer um método de envio simples e sem estado.
    """

    def __init__(self):
        self.auth_service = GraphAuthService()
        self.template_service = EmailTemplateService()
        self.email_from = os.getenv("MICROSOFT_EMAIL_FROM")
        self.default_to = os.getenv("MICROSOFT_EMAIL_TO")

    def _validate_sender(self, sender=None):
        if not self.email_from and not sender:
            return False, "Remetente (MICROSOFT_EMAIL_FROM) não configurado."
        return True, None

    def _format_recipients(self, recipients):
        result = []
        for r in recipients or []:
            if isinstance(r, str) and r.strip():
                result.append({"emailAddress": {"address": r.strip()}})
        return result
    
    def _parse_default_to(self):
        if not self.default_to:
            return []
        raw = self.default_to.replace(";", ",")
        addrs = [a.strip() for a in raw.split(",") if a.strip()]
        return addrs

    def send_email(self, subject, body, recipients, content_type="Text", sender=None, attachments=None):
        """Envia um e-mail via Microsoft Graph API.

        Args:
            subject (str): Assunto do e-mail.
            body (str): Corpo do e-mail (texto ou HTML).
            recipients (list[str]): Lista de endereços de e-mail dos destinatários.
            content_type (str): \"Text\" ou \"HTML\" (padrão: \"Text\").
            sender (str | None): Endereço remetente; se None, usa MICROSOFT_EMAIL_FROM.
            attachments (list | None): Lista de dicionários de anexo no formato Graph API.

        Returns:
            dict: {\"success\": bool, \"message\": str, ...}  
                  Em sucesso inclui \"recipients\" (lista de endereços confirmados).
        """
        # 1. Validações
        ok, err = self.auth_service.validate_env()
        if not ok:
            logging.error(f"Env inválido para envio de e-mail: {err}")
            return {"success": False, "message": err}
        
        ok, err = self._validate_sender(sender)
        if not ok:
            return {"success": False, "message": err}

        # 2. Auth
        access_token, auth_err = self.auth_service.get_token()
        if not access_token:
            logging.error(f"Autenticação Graph falhou: {auth_err}")
            return {"success": False, "message": auth_err}

        # 3. Destinatários
        to_list = self._format_recipients(recipients)
        if not to_list:
            to_list = self._format_recipients(self._parse_default_to())
        if not to_list:
            return {"success": False, "message": "Destinatários inválidos ou ausentes."}

        # 4. Corpo e Anexos
        final_body, final_content_type = self.template_service.format_body(body, content_type)
        
        atts = []
        if attachments and isinstance(attachments, list):
            atts.extend(attachments)
        
        logo = self.template_service.get_logo_attachment()
        if logo:
            atts.append(logo)

        # 5. Payload e Envio
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "message": {
                "subject": subject or "",
                "body": {"contentType": final_content_type, "content": final_body},
                "toRecipients": to_list,
            }
        }
        
        if atts:
            payload["message"]["attachments"] = atts

        try:
            email_from = sender or self.email_from
            url = f"https://graph.microsoft.com/v1.0/users/{email_from}/sendMail"
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            
            if resp.status_code == 202:
                logging.info("E-mail enviado com sucesso via Microsoft Graph.")
                sent_to = [r["emailAddress"]["address"] for r in to_list]
                return {"success": True, "message": "E-mail enviado com sucesso.", "recipients": sent_to}
            
            msg = None
            try:
                msg = resp.json()
            except Exception:
                msg = resp.text
            
            logging.error(f"Falha ao enviar e-mail: {resp.status_code} - {msg}")
            return {
                "success": False,
                "message": "Falha ao enviar e-mail.",
                "status_code": resp.status_code,
                "response": msg,
            }
        except requests.RequestException as e:
            logging.error(f"Erro de rede ao enviar e-mail: {e}")
            return {"success": False, "message": f"Erro de rede: {str(e)}"}
