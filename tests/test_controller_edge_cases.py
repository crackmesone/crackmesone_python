"""High-value validation and failure branches across public controllers."""

from io import BytesIO
from unittest.mock import patch

import pytest


def test_login_by_email_and_safe_referrer(client, alice):
    page = client.get('/login', headers={'Referer': 'http://localhost/crackme/abc'})
    assert page.status_code == 200
    response = client.post('/login', data={
        'name': 'alice@example.test', 'password': 'alice-password',
    })
    assert response.status_code == 302
    assert response.location == '/crackme/abc'


def test_login_does_not_redirect_to_external_referrer(client, alice):
    client.get('/login', headers={'Referer': 'https://evil.example/phish'})
    response = client.post('/login', data={
        'name': 'alice', 'password': 'alice-password',
    })
    assert response.location == '/'


def test_login_missing_and_invalid_name(client):
    missing = client.post('/login', data={'name': '', 'password': ''})
    invalid = client.post('/login', data={'name': '<script>', 'password': 'x'})
    assert b'Field missing: name' in missing.data
    assert b'Non authorized chars' in invalid.data


def test_login_database_failure_is_generic(client):
    with patch('app.controllers.login.user_by_mail', side_effect=RuntimeError):
        response = client.post('/login', data={'name': 'alice', 'password': 'x'})
    assert response.status_code == 200
    assert b'error' in response.data.lower()


def test_registration_rejects_duplicate_email_and_username(client, alice):
    duplicate_email = client.post('/register', data={
        'name': 'different', 'email': 'alice@example.test', 'password': 'password123',
    })
    duplicate_name = client.post('/register', data={
        'name': 'alice', 'email': 'different@example.test', 'password': 'password123',
    })
    assert b'Account already exists' in duplicate_email.data
    assert b'Account already exists' in duplicate_name.data


def test_registration_cross_field_conflicts(client, db):
    db.user.insert_one({
        'name': 'existing@example.test', 'email': 'existing-email@example.test',
        'password': 'hash',
    })
    username_is_email = client.post('/register', data={
        'name': 'existing-email@example.test', 'email': 'new@example.test',
        'password': 'password123',
    })
    email_is_username = client.post('/register', data={
        'name': 'new-user', 'email': 'existing@example.test',
        'password': 'password123',
    })
    assert b'username is not available' in username_is_email.data
    assert b'email is not available' in email_is_username.data


def test_registration_rejects_invalid_chars_and_recaptcha(client):
    invalid = client.post('/register', data={
        'name': 'bad name', 'email': 'valid@example.test', 'password': 'password123',
    })
    with patch('app.controllers.register.verify_recaptcha', return_value=False):
        captcha = client.post('/register', data={
            'name': 'valid', 'email': 'valid@example.test', 'password': 'password123',
        })
    assert b'Non allowed chars' in invalid.data
    assert b'reCAPTCHA invalid' in captcha.data


def test_registration_hash_and_create_failures(client):
    data = {'name': 'newuser', 'email': 'new@example.test', 'password': 'password123'}
    with patch('app.controllers.register.hash_string', side_effect=RuntimeError):
        hashing = client.post('/register', data=data)
    with patch('app.controllers.register.user_create', side_effect=RuntimeError):
        creation = client.post('/register', data=data)
    assert hashing.status_code == 302
    assert creation.status_code == 200


@pytest.mark.parametrize(('difficulty', 'message'), [
    ('0', b'Wrong difficulty'), ('7', b'Wrong difficulty'), ('bad', b'Wrong difficulty'),
])
def test_crackme_upload_rejects_invalid_difficulty(
        alice_client, alice, difficulty, message):
    response = alice_client.post('/upload/crackme', data={
        'name': 'Challenge', 'info': 'Info', 'lang': 'C', 'difficulty': difficulty,
        'platform': 'Linux', 'arch': 'x86',
        'file': (BytesIO(b'data'), 'challenge.bin'),
    }, content_type='multipart/form-data')
    assert message in response.data


@pytest.mark.parametrize(('validator', 'message'), [
    ('is_unsupported_archive', b'RAR and tar'),
    ('is_archive_password_protected', b'Password-protected'),
    ('is_single_file_archive', b'only one file'),
])
def test_crackme_upload_archive_rejections(
        alice_client, alice, validator, message):
    with patch(f'app.controllers.crackme.{validator}', return_value=True):
        response = alice_client.post('/upload/crackme', data={
            'name': 'Challenge', 'info': 'Info', 'lang': 'C', 'difficulty': '3',
            'platform': 'Linux', 'arch': 'x86',
            'file': (BytesIO(b'data'), 'challenge.bin'),
        }, content_type='multipart/form-data')
    assert message in response.data


def test_crackme_upload_rejects_oversized_file(alice_client, alice):
    with patch('app.controllers.crackme.MAX_FILE_SIZE', 2):
        response = alice_client.post('/upload/crackme', data={
            'name': 'Challenge', 'info': 'Info', 'lang': 'C', 'difficulty': '3',
            'platform': 'Linux', 'arch': 'x86',
            'file': (BytesIO(b'too large'), 'challenge.bin'),
        }, content_type='multipart/form-data')
    assert b'This file is too large' in response.data


def test_crackme_view_download_and_lasts(client, db, sample_crackme):
    page = client.get(f"/crackme/{sample_crackme['hexid']}")
    download = client.get(f"/download/crackme/{sample_crackme['hexid']}")
    lasts = client.get('/lasts')
    assert page.status_code == 200
    assert b'Test Crackme' in page.data
    assert download.location == f"/static/crackme/{sample_crackme['hexid']}.zip"
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['nbdownloads'] == 1
    assert lasts.location == '/lasts/1'


def test_comment_validation_sanitization_and_recaptcha(
        bob_client, db, sample_crackme, bob):
    missing = bob_client.post(f"/comment/{sample_crackme['hexid']}", data={})
    with patch('app.controllers.comment.verify_recaptcha', return_value=False):
        captcha = bob_client.post(
            f"/comment/{sample_crackme['hexid']}", data={'comment': 'hello'}
        )
    sanitized = bob_client.post(
        f"/comment/{sample_crackme['hexid']}",
        data={'comment': '<script>alert(1)</script><b>safe</b>'},
    )
    assert missing.status_code == captcha.status_code == sanitized.status_code == 302
    stored = db.comment.find_one({})['info']
    assert '<script>' not in stored
    assert '<b>safe</b>' in stored


def test_spoiler_token_is_single_use(bob_client, client, db, sample_crackme, bob):
    from app.controllers import comment as controller

    bob_client.post(f"/comment/{sample_crackme['hexid']}", data={'comment': 'spoiler'})
    comment = db.comment.find_one({'author': 'bob'})
    token = controller._spoiler_tokens[str(comment['_id'])]
    path = f"/comment/{comment['_id']}/spoiler-token/{token}"
    first = client.get(path)
    second = client.get(path)
    assert b'success' in first.data.lower()
    assert b'Invalid token' in second.data
    assert db.comment.find_one({'_id': comment['_id']})['spoiler'] is True


def test_password_reset_quota_and_unconfigured_email(client, db):
    with patch('app.controllers.password_reset.quota_exceeded', return_value=True):
        get_response = client.get('/forgot-password')
        post_response = client.post('/forgot-password', data={'email': 'a@example.test'})
    with patch('app.controllers.password_reset.email_is_configured', return_value=False):
        unavailable = client.post('/forgot-password', data={'email': 'a@example.test'})
    assert get_response.status_code == post_response.status_code == unavailable.status_code == 200
    assert b'unavailable' in unavailable.data.lower()


def test_password_reset_per_address_quota_hides_limit(client):
    with patch('app.controllers.password_reset.email_is_configured', return_value=True), \
         patch('app.controllers.password_reset.email_quota_exceeded', return_value=True), \
         patch('app.controllers.password_reset.user_by_mail') as lookup:
        response = client.post('/forgot-password', data={'email': 'a@example.test'})
    assert response.status_code == 200
    lookup.assert_not_called()


@pytest.mark.parametrize('payload', [
    {'new_password': '', 'new_password_verify': ''},
    {'new_password': 'short', 'new_password_verify': 'short'},
])
def test_password_reset_rejects_empty_and_short_passwords(client, alice, payload):
    from app.models.password_reset import create_reset_token
    token = create_reset_token('alice@example.test')
    response = client.post(f'/reset-password/{token}', data=payload)
    assert response.status_code == 200


@pytest.mark.parametrize(('validator', 'message'), [
    ('is_unsupported_archive', b'RAR and tar'),
    ('is_archive_password_protected', b'Password-protected'),
    ('is_single_file_archive', b'only one file'),
    ('is_pe_file', b'Executable files'),
])
def test_solution_attachment_rejections(
        alice_client, db, sample_crackme, validator, message):
    with patch(f'app.controllers.solution.{validator}', return_value=True):
        response = alice_client.post(
            f"/upload/solution/{sample_crackme['hexid']}",
            data={'info': 'Summary', 'file': (BytesIO(b'data'), 'file.bin')},
            content_type='multipart/form-data',
        )
    assert response.status_code == 302
    with alice_client.session_transaction() as session:
        assert message in session['_flashes'][-1][1].encode()
    assert db.solution.count_documents({}) == 0


def test_solution_rejects_long_summary_and_recaptcha(alice_client, db, sample_crackme):
    long_info = alice_client.post(
        f"/upload/solution/{sample_crackme['hexid']}",
        data={'info': 'x' * 201, 'content': 'a' * 200},
    )
    with patch('app.controllers.solution.verify_recaptcha', return_value=False):
        captcha = alice_client.post(
            f"/upload/solution/{sample_crackme['hexid']}",
            data={'info': 'Summary', 'content': 'a' * 200},
        )
    assert long_info.status_code == captcha.status_code == 302
    assert db.solution.count_documents({}) == 0
