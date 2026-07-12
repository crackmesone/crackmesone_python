"""Password-reset tests with email and Discord kept behind mocks."""

from datetime import datetime, timedelta
from unittest.mock import patch

from app.models.password_reset import create_reset_token
from app.services.passhash import match_string


def test_forgot_password_sends_configured_reset_link(client, db, alice):
    with patch('app.controllers.password_reset.email_is_configured', return_value=True), \
         patch('app.controllers.password_reset.send_email', return_value=True) as send, \
         patch('app.controllers.password_reset.notify_password_reset_request'):
        response = client.post(
            '/forgot-password', data={'email': 'alice@example.test'}
        )

    assert response.status_code == 200
    assert b'email' in response.data.lower()
    token = db.password_reset_tokens.find_one({'email': 'alice@example.test'})['token']
    recipient, subject, body = send.call_args.args
    assert recipient == 'alice@example.test'
    assert 'Password Reset' in subject
    assert f'http://localhost/reset-password/{token}' in body


def test_forgot_password_does_not_reveal_unknown_email(client, db):
    with patch('app.controllers.password_reset.email_is_configured', return_value=True), \
         patch('app.controllers.password_reset.send_email') as send:
        response = client.post(
            '/forgot-password', data={'email': 'missing@example.test'}
        )

    assert response.status_code == 200
    assert b'email' in response.data.lower()
    send.assert_not_called()


def test_valid_reset_token_changes_password_and_is_single_use(client, db, alice):
    token = create_reset_token('alice@example.test')
    with patch('app.controllers.password_reset.notify_password_reset_complete'):
        response = client.post(f'/reset-password/{token}', data={
            'new_password': 'replacement-password',
            'new_password_verify': 'replacement-password',
        })

    assert response.status_code == 302
    assert response.location == '/login'
    assert match_string(
        db.user.find_one({'name': 'alice'})['password'], 'replacement-password'
    ) is True
    assert db.password_reset_tokens.find_one({'token': token}) is None
    assert client.get(f'/reset-password/{token}').status_code == 302


def test_expired_reset_token_is_rejected(client, db, alice):
    db.password_reset_tokens.insert_one({
        'email': 'alice@example.test',
        'token': 'expired-token',
        'expires_at': datetime.utcnow() - timedelta(minutes=1),
    })

    response = client.get('/reset-password/expired-token')

    assert response.status_code == 302
    assert response.location == '/forgot-password'


def test_reset_password_validates_confirmation(client, db, alice):
    token = create_reset_token('alice@example.test')
    response = client.post(f'/reset-password/{token}', data={
        'new_password': 'replacement-password',
        'new_password_verify': 'different-password',
    })

    assert response.status_code == 200
    assert b'Passwords do not match' in response.data
    assert db.password_reset_tokens.find_one({'token': token}) is not None
