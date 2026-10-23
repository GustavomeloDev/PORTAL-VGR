"""core.integrations.microsoft_auth

Serviço de autenticação isolado para o Microsoft Graph API via MSAL.
Utilizado por módulos que precisam de um token de acesso sem envolver
template de e-mail.

Variáveis de ambiente necessárias:
    MICROSOFT_CLIENT_ID      — Client ID do app Azure AD.
    MICROSOFT_CLIENT_SECRET  — Client secret do app Azure AD.
    MICROSOFT_TENANT_ID      — Tenant ID do Azure AD.
"""
import os

try:
    import msal  # type: ignore
except ImportError:
    msal = None

class GraphAuthService:
    """Autentica no Azure AD via MSAL usando o fluxo client credentials.

    Não mantém cache de token — cada chamada gera um novo token junto ao Azure.
    """
    def __init__(self):
        """Lê as credenciais Azure das variáveis de ambiente."""
        self.client_id = os.getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
        self.tenant_id = os.getenv("MICROSOFT_TENANT_ID")
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}" if self.tenant_id else None
        self.scope = ["https://graph.microsoft.com/.default"]

    def validate_credentials(self):
        """Verifica se as três variáveis de autenticação estão definidas.

        Returns:
            tuple[bool, str | None]: (True, None) se completo;
                (False, mensagem_com_lista_de_ausentes) caso contrário.
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

    def get_access_token(self):
        """Obtém um access token válido para o Microsoft Graph API.

        Utiliza o fluxo *Client Credentials* (sem usuário interativo).

        Returns:
            tuple[str | None, str | None]:
                - (access_token, None) em caso de sucesso.
                - (None, mensagem_de_erro) em caso de falha.
        """
        if msal is None:
            return None, "Biblioteca 'msal' não está instalada no ambiente atual."

        try:
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
