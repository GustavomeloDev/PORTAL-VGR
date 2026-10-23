import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Mock modules to avoid import errors
sys.modules['msal'] = MagicMock()

# Import the service
# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if project_root not in sys.path:
    sys.path.append(project_root)

from core.integrations.email import EmailService

class TestEmailServiceRecipients(unittest.TestCase):
    def setUp(self):
        # Patch environment variables before creating service instance
        self.env_patcher = patch.dict(os.environ, {
            "MICROSOFT_CLIENT_ID": "fake_id",
            "MICROSOFT_CLIENT_SECRET": "fake_secret",
            "MICROSOFT_TENANT_ID": "fake_tenant",
            "MICROSOFT_EMAIL_FROM": "sender@example.com",
            "MICROSOFT_EMAIL_TO": "default@example.com"
        })
        self.env_patcher.start()
        
        self.service = EmailService()
        # Mock auth service internals to avoid real validation calls that might fail if env vars not picked up or logic changes
        self.service.auth_service.validate_env = MagicMock(return_value=(True, None))
        self.service.auth_service.get_token = MagicMock(return_value=("fake_token", None))
        
        # Mock template service
        self.service.template_service.format_body = MagicMock(return_value=("body", "Text"))
        self.service.template_service.get_logo_attachment = MagicMock(return_value=None)

    def tearDown(self):
        self.env_patcher.stop()

    @patch('requests.post')
    def test_send_email_returns_recipients(self, mock_post):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response
        
        # Test with explicit recipients
        recipients = ["test@example.com", "other@example.com"]
        result = self.service.send_email("Subject", "Body", recipients)
        
        self.assertTrue(result['success'])
        self.assertIn('recipients', result)
        self.assertEqual(result['recipients'], recipients)
        
    @patch('requests.post')
    def test_send_email_uses_default_recipients(self, mock_post):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response
        
        # Test with no recipients (should use default)
        result = self.service.send_email("Subject", "Body", None)
        
        self.assertTrue(result['success'])
        self.assertIn('recipients', result)
        self.assertEqual(result['recipients'], ["default@example.com"])

if __name__ == '__main__':
    unittest.main()
