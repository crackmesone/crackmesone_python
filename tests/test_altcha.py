"""Self-hosted ALTCHA v2 verification, real crypto, route and replay tests."""

import base64
from datetime import datetime, timedelta, timezone
import json
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor

import pytest
from altcha import Challenge, Payload, create_challenge, solve_challenge

from app.services import altcha


ALTCHA_CONFIG = {
    'Enabled': True,
    'HmacSecret': 'unit-test-signing-key-012345678901234567890123456789',
    'HmacKeySecret': 'unit-test-pow-key-012345678901234567890123456789',
    'Cost': 100,
    'MinCounter': 1,
    'MaxCounter': 3,
    'ExpiresMinutes': 20,
    'Protect': {'Crackme': True, 'Writeup': True,
                'Register': False, 'Comment': False},
}


def configure_altcha_for_test(app, **overrides):
    config = {**ALTCHA_CONFIG, **overrides}
    altcha.init_altcha(app, config)


def solved(client, scope='Crackme'):
    response = client.get('/altcha/challenge/' + scope)
    assert response.status_code == 200, response.get_json()
    assert response.headers['Cache-Control'] == 'no-store, max-age=0'
    challenge = Challenge.from_dict(response.get_json())
    solution = solve_challenge(challenge, timeout=10)
    assert solution is not None
    return Payload(challenge, solution).to_base64()


def post_request(app, token, scope):
    with app.test_request_context('/', method='POST', data={'altcha': token}):
        return altcha.verify(__import__('flask').request, scope)


def test_enabled_switches_and_invalid_scope(app):
    configure_altcha_for_test(app)
    assert altcha.is_enabled('Crackme')
    assert altcha.is_enabled('Writeup')
    assert not altcha.is_enabled('Register')
    assert not altcha.is_enabled('Comment')
    with pytest.raises(ValueError):
        altcha.is_enabled('Wrong')
    altcha.init_altcha(app, {'Enabled': False})
    with app.test_request_context('/', method='POST'):
        assert altcha.verify(__import__('flask').request, 'Crackme')


def test_challenge_endpoint_not_exposed_when_disabled(app, client):
    configure_altcha_for_test(app, Protect={'Crackme': False})
    assert client.get('/altcha/challenge/Crackme').status_code == 404
    assert client.get('/altcha/challenge/Evil').status_code == 404
    assert client.get('/altcha/challenge/Writeup').status_code == 200


@pytest.mark.parametrize('bad', [
    {'HmacSecret': ''},
    {'HmacKeySecret': 'weak'},
    {'Cost': 0},
    {'Cost': 10000000},
    {'MinCounter': 100, 'MaxCounter': 1},
    {'ExpiresMinutes': 0},
])
def test_invalid_config_fails_closed(app, client, bad):
    configure_altcha_for_test(app, **bad)
    response = client.get('/altcha/challenge/Crackme')
    assert response.status_code == 503


def test_ttl_index_created_when_altcha_is_enabled(app, db):
    configure_altcha_for_test(app)
    index = db.altcha_used.index_information()['expires_at_1']
    assert index['expireAfterSeconds'] == 0


def test_verifying_proof_does_not_create_index_per_request(app, client, db,
                                                          monkeypatch):
    configure_altcha_for_test(app)
    token = solved(client)

    class GuardedCollection:
        def insert_one(self, document):
            return db.altcha_used.insert_one(document)

        def create_index(self, *_args, **_kwargs):
            pytest.fail('Index creation must happen during init, not request')

    class GuardedDB:
        def __getitem__(self, name):
            assert name == 'altcha_used'
            return GuardedCollection()

    monkeypatch.setitem(app.config, 'MONGO_DB', GuardedDB())
    assert post_request(app, token, 'Crackme') is True
    assert post_request(app, token, 'Crackme') is False


def test_real_crypto_and_atomic_single_use(app, client, db):
    configure_altcha_for_test(app)
    token = solved(client)
    assert post_request(app, token, 'Crackme') is True
    assert post_request(app, token, 'Crackme') is False
    assert db.altcha_used.count_documents({}) == 1
    assert 'expires_at_1' in db.altcha_used.index_information()


def test_replay_with_different_json_format_is_rejected(app, client, db):
    configure_altcha_for_test(app)
    token = solved(client)
    assert post_request(app, token, 'Crackme') is True
    obj = json.loads(base64.b64decode(token))
    changed = base64.b64encode(json.dumps(obj, separators=(',', ':'), sort_keys=True).encode()).decode()
    assert post_request(app, changed, 'Crackme') is False
    assert db.altcha_used.count_documents({}) == 1


def test_real_crypto_cross_form_is_blocked(app, client):
    configure_altcha_for_test(app)
    token = solved(client, 'Crackme')
    assert post_request(app, token, 'Writeup') is False
    assert post_request(app, token, 'Crackme') is True


def test_missing_and_tampered_payloads_are_blocked(app, client):
    configure_altcha_for_test(app)
    assert post_request(app, '', 'Crackme') is False
    assert post_request(app, 'Z'*10000, 'Crackme') is False
    assert post_request(app, 'not-base64', 'Crackme') is False
    token = solved(client)
    obj = json.loads(base64.b64decode(token))
    obj['challenge']['parameters']['cost'] += 1
    tampered = base64.b64encode(json.dumps(obj).encode()).decode()
    assert post_request(app, tampered, 'Crackme') is False


def test_expired_challenge_is_rejected(app):
    configure_altcha_for_test(app)
    secret = altcha._secret('HmacSecret', 'Crackme')
    key_secret = altcha._secret('HmacKeySecret', 'Crackme')
    challenge = create_challenge(algorithm='PBKDF2/SHA-256', cost=100,
                                 counter=1, hmac_secret=secret,
                                 hmac_key_secret=key_secret,
                                 expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    result = solve_challenge(challenge, timeout=10)
    token = Payload(challenge, result).to_base64()
    assert post_request(app, token, 'Crackme') is False


def test_broken_db_rejects_submission(app, client, monkeypatch):
    configure_altcha_for_test(app)
    token = solved(client)
    class BrokenCollection:
        def insert_one(self, *_args, **_kwargs):
            raise __import__('pymongo').errors.PyMongoError('database offline')
    class BrokenDB:
        def __getitem__(self, name):
            return BrokenCollection()
    monkeypatch.setitem(app.config, 'MONGO_DB', BrokenDB())
    assert post_request(app, token, 'Crackme') is False


def test_concurrent_reuse_only_one_wins(app, client):
    configure_altcha_for_test(app)
    token = solved(client)
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: post_request(app, token, 'Crackme'), range(6)))
    assert results.count(True) == 1
    assert results.count(False) == 5


def _crackme_data(token=None):
    data = {'name': 'ALTCHA challenge', 'info': 'Analysis', 'lang': 'C/C++',
            'arch': 'x86-64', 'platform': 'Linux', 'difficulty': '3',
            'file': (BytesIO(b'ELF dummy'), 'test.bin')}
    if token is not None:
        data['altcha'] = token
    return data


def _writeup_data(token=None):
    data = {'info': 'Solution summary', 'content': 'a' * 250}
    if token is not None:
        data['altcha'] = token
    return data


@pytest.mark.parametrize('scope', ['Crackme', 'Writeup'])
@pytest.mark.parametrize('mode', ['missing', 'bad', 'valid'])
def test_direct_uploads_validate_altcha(app, alice_client, client, db,
                                        sample_crackme, monkeypatch, tmp_path,
                                        scope, mode):
    from app.controllers import crackme as cc, solution as sc
    monkeypatch.setattr(cc, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(sc, 'UPLOAD_FOLDER', str(tmp_path))
    configure_altcha_for_test(app)
    if scope == 'Crackme':
        path = '/upload/crackme'
        collection = db.crackme
        builder = _crackme_data
    else:
        path = '/upload/solution/' + sample_crackme['hexid']
        collection = db.solution
        builder = _writeup_data
    before = collection.count_documents({})
    token = None if mode == 'missing' else ('fake' if mode == 'bad' else solved(client, scope))
    response = alice_client.post(path, data=builder(token),
                                 content_type='multipart/form-data',
                                 headers={'X-Requested-With': 'XMLHttpRequest'})
    if mode == 'valid':
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.json['ok'] is True
        assert collection.count_documents({}) == before + 1
    else:
        assert response.status_code == 400
        assert response.json['error'] == 'ALTCHA invalid!'
        assert collection.count_documents({}) == before


def test_templates_only_protected_features_render_widget(app, alice_client, client, sample_crackme):
    configure_altcha_for_test(app)
    upload = alice_client.get('/upload/crackme').data
    writeup = alice_client.get('/upload/solution/' + sample_crackme['hexid']).data
    registration = client.get('/register').data
    comment = client.get('/crackme/' + sample_crackme['hexid']).data
    assert b'<altcha-widget' in upload and b'/altcha/challenge/Crackme' in upload
    assert b'<altcha-widget' in writeup and b'/altcha/challenge/Writeup' in writeup
    # Catch a broken CDN path even when the widget element renders in HTML.
    assert b'altcha@3.2.1/dist/main/altcha.min.js' in upload
    assert b'altcha@3.2.1/dist/main/altcha.min.js' in writeup
    assert b'<altcha-widget' not in registration
    assert b'<altcha-widget' not in comment
    for page in (upload, writeup, registration, comment):
        assert b'google.com/recaptcha' not in page


def test_legacy_google_field_never_bypasses_altcha(app, alice_client, db):
    configure_altcha_for_test(app)
    payload = _crackme_data()
    payload['g-recaptcha-response'] = 'old-valid-token'
    before = db.crackme.count_documents({})
    response = alice_client.post('/upload/crackme', data=payload,
                                 content_type='multipart/form-data',
                                 headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 400
    assert db.crackme.count_documents({}) == before
