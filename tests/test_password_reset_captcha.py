"""
Tests for forgot-password reCAPTCHA handling.
"""

from flask import Flask
from unittest.mock import patch

from app.models.errors import ErrNoResult
from app.controllers.password_reset import forgot_password_post


class TestPasswordResetCaptcha:
    """Focused tests for forgot-password captcha flow."""

    def setup_method(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-secret'

    def test_forgot_password_rejects_invalid_recaptcha(self):
        """Forgot-password should reject invalid reCAPTCHA."""
        with self.app.test_request_context('/forgot-password', method='POST', data={'email': 'test@example.com'}):
            with patch('app.controllers.password_reset.quota_exceeded', return_value=False):
                with patch('app.controllers.password_reset.verify_recaptcha', return_value=False):
                    with patch('app.controllers.password_reset.email_is_configured') as email_configured:
                        with patch('app.controllers.password_reset.render_template', return_value='password_reset/forgot.html'):
                            response = forgot_password_post()
                            assert response == 'password_reset/forgot.html'
                            email_configured.assert_not_called()

    def test_forgot_password_accepts_valid_recaptcha(self):
        """Forgot-password should continue flow when reCAPTCHA is valid."""
        with self.app.test_request_context('/forgot-password', method='POST', data={'email': 'test@example.com'}):
            with patch('app.controllers.password_reset.quota_exceeded', return_value=False):
                with patch('app.controllers.password_reset.verify_recaptcha', return_value=True):
                    with patch('app.controllers.password_reset.email_is_configured', return_value=True):
                        with patch('app.controllers.password_reset.email_quota_exceeded', return_value=False):
                            with patch('app.controllers.password_reset.user_by_mail', side_effect=ErrNoResult('not found')):
                                with patch('app.controllers.password_reset.render_template', return_value='password_reset/email_sent.html'):
                                    response = forgot_password_post()
                                    assert response == 'password_reset/email_sent.html'
