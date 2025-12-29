"""
Unit tests for reCAPTCHA service.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.services.recaptcha import verify_recaptcha


class TestRecaptcha:
    """Tests for reCAPTCHA verification."""

    def test_verify_recaptcha_disabled(self):
        """Test that verification passes when reCAPTCHA is disabled."""
        config = {'Recaptcha': {'Enabled': False}}
        with patch('app.services.recaptcha.load_config', return_value=config):
            from app.services import recaptcha
            # Reload to pick up the mock
            result = verify_recaptcha('any-token')
            # When disabled, should return True
            assert result is True

    def test_verify_recaptcha_empty_token(self):
        """Test verification with empty token."""
        config = {'Recaptcha': {'Enabled': True, 'Secret': 'test-secret'}}
        with patch('app.services.recaptcha.load_config', return_value=config):
            with patch('app.services.recaptcha.RECAPTCHA_ENABLED', True):
                result = verify_recaptcha('')
                assert result is False

    def test_verify_recaptcha_success(self):
        """Test successful reCAPTCHA verification."""
        config = {'Recaptcha': {'Enabled': True, 'Secret': 'test-secret'}}
        mock_response = MagicMock()
        mock_response.json.return_value = {'success': True}

        with patch('app.services.recaptcha.load_config', return_value=config):
            with patch('app.services.recaptcha.RECAPTCHA_ENABLED', True):
                with patch('app.services.recaptcha.requests.post', return_value=mock_response):
                    result = verify_recaptcha('valid-token')
                    assert result is True

    def test_verify_recaptcha_failure(self):
        """Test failed reCAPTCHA verification."""
        config = {'Recaptcha': {'Enabled': True, 'Secret': 'test-secret'}}
        mock_response = MagicMock()
        mock_response.json.return_value = {'success': False}

        with patch('app.services.recaptcha.load_config', return_value=config):
            with patch('app.services.recaptcha.RECAPTCHA_ENABLED', True):
                with patch('app.services.recaptcha.requests.post', return_value=mock_response):
                    result = verify_recaptcha('invalid-token')
                    assert result is False
