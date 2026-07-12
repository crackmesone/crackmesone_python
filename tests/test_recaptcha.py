"""Unit tests for the reCAPTCHA external-service boundary."""

from unittest.mock import MagicMock, patch

from flask import request

from app.services.recaptcha import init_recaptcha, verify


def test_disabled_recaptcha_passes(app):
    init_recaptcha(app, {'Enabled': False})
    with app.test_request_context('/register', method='POST'):
        assert verify(request) is True


def test_enabled_recaptcha_rejects_missing_token(app):
    init_recaptcha(app, {'Enabled': True, 'Secret': 'test-secret'})
    with app.test_request_context('/register', method='POST'):
        assert verify(request) is False


def test_enabled_recaptcha_sends_token_and_accepts_success(app):
    init_recaptcha(app, {'Enabled': True, 'Secret': 'test-secret'})
    response = MagicMock()
    response.json.return_value = {'success': True}

    with app.test_request_context(
        '/register', method='POST',
        data={'g-recaptcha-response': 'valid-token'},
        environ_base={'REMOTE_ADDR': '127.0.0.1'},
    ):
        with patch('app.services.recaptcha.requests.post', return_value=response) as post:
            assert verify(request) is True

    post.assert_called_once_with(
        'https://www.google.com/recaptcha/api/siteverify',
        data={
            'secret': 'test-secret',
            'response': 'valid-token',
            'remoteip': '127.0.0.1',
        },
        timeout=10,
    )


def test_enabled_recaptcha_fails_closed_on_network_error(app):
    init_recaptcha(app, {'Enabled': True, 'Secret': 'test-secret'})
    with app.test_request_context(
        '/register', method='POST', data={'g-recaptcha-response': 'token'}
    ):
        with patch('app.services.recaptcha.requests.post', side_effect=TimeoutError):
            assert verify(request) is False
