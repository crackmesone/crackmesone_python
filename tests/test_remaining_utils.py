"""Remaining deterministic utility branches suitable for isolated testing."""

from datetime import datetime
from unittest.mock import MagicMock, patch


def test_limiter_decorator_helpers_with_and_without_instance(monkeypatch):
    from app.services import limiter as service

    monkeypatch.setattr(service, 'limiter', None)
    function = lambda: 'ok'
    assert service.limit('1/minute')(function)() == 'ok'
    assert service.shared_limit('1/minute', scope='x')(function)() == 'ok'
    assert service.exempt(function) is function

    fake = MagicMock()
    fake.limit.return_value = lambda fn: fn
    fake.shared_limit.return_value = lambda fn: fn
    fake.exempt.return_value = function
    monkeypatch.setattr(service, 'limiter', fake)
    assert service.limit('1/minute')(function)() == 'ok'
    assert service.shared_limit('1/minute', scope='x')(function)() == 'ok'
    assert service.exempt(function) is function


def test_recaptcha_configuration_accessors(app):
    from app.services import recaptcha

    recaptcha.init_recaptcha(app, {
        'Enabled': True, 'SiteKey': 'site-key', 'Secret': 'secret',
    })
    assert recaptcha.read_config()['Secret'] == 'secret'
    assert recaptcha.is_enabled() is True
    assert recaptcha.get_site_key() == 'site-key'
    recaptcha.init_recaptcha(app, {'Enabled': False})
    assert recaptcha.get_site_key() == ''


def test_crypto_default_salt_and_key_are_deterministic():
    from app.services.crypto import (
        DEFAULT_OBFUSCATION_SALT, get_obfuscation_key_base64,
        get_obfuscation_salt, obfuscate_writeup,
    )

    assert get_obfuscation_salt({}) == DEFAULT_OBFUSCATION_SALT
    key1 = get_obfuscation_key_base64('abc', 'salt')
    key2 = get_obfuscation_key_base64('abc', 'salt')
    assert key1 == key2
    assert obfuscate_writeup('hello', 'abc', 'salt') != b'hello'


def test_database_access_and_failed_health_check(app, monkeypatch):
    from app.services import database
    from pymongo.errors import ConnectionFailure

    assert database.get_db() is app.config['MONGO_DB']
    assert database.get_collection('user').name == 'user'
    failing = MagicMock()
    failing.admin.command.side_effect = ConnectionFailure('down')
    monkeypatch.setattr(database, 'mongo_client', failing)
    assert database.check_connection() is False
    monkeypatch.setattr(database, 'mongo_client', None)
    assert database.check_connection() is False


def test_remaining_template_filter_fallbacks(app):
    filters = app.jinja_env.filters
    globals_ = app.jinja_env.globals
    assert filters['PRETTYTIME'](None) == ''
    assert filters['PRETTYTIME'](object()) == ''
    assert filters['PRETTYTIMEFORMAT'](None, '%Y') == ''
    assert filters['PRETTYTIMEFORMAT'](object(), '%Y') == ''
    assert filters['TIMECOMPARE'](None, datetime.now()) is False
    assert filters['render_mentions']('') == ''
    assert globals_['TIMECOMPARE'](None, None, 2) is True
    assert globals_['TIMECOMPARE']('bad', 'values', 2) is True
    assert globals_['DIFFERENT_DATE'](None, None) is True
    assert globals_['DIFFERENT_DATE']('bad', 'values') is True


def test_archive_malformed_compressed_signatures_and_pe_offsets():
    from app.services.archive import is_archive_password_protected, is_pe_file, is_tar_file

    assert is_tar_file(b'\x1f\x8bnot-gzip') is False
    assert is_tar_file(b'BZhnot-bzip') is False
    assert is_tar_file(b'\xfd7zXZ\x00not-xz') is False
    header = bytearray(80)
    header[:2] = b'MZ'
    header[0x3C:0x40] = (9999).to_bytes(4, 'little')
    assert is_pe_file('file.bin', bytes(header)) is False
    assert is_archive_password_protected(b'not-a-zip') is False


def test_user_and_solution_error_routes(client):
    assert client.get('/user/missing').status_code == 404
    assert client.get('/solution/not-valid').status_code == 404
    assert client.get('/solution/not-valid/content').status_code == 404
    assert client.get('/upload/solution/not-valid').status_code == 302
