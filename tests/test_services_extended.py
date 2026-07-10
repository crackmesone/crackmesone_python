"""Focused unit coverage for deterministic service boundaries and helpers."""

import io
import struct
import tarfile
import zipfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.services import archive, email


def _zip(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as zipped:
        for name, data in files.items():
            zipped.writestr(name, data)
    return output.getvalue()


def test_archive_counts_real_files_but_ignores_metadata():
    data = _zip({
        'one.bin': b'1',
        'two.txt': b'2',
        '__MACOSX/._one.bin': b'metadata',
        '.DS_Store': b'metadata',
    })

    assert archive.get_archive_file_count(data) == 2
    assert archive.is_single_file_archive(data) is False
    assert archive.get_archive_file_count(b'not a zip') is None


def test_single_file_zip_is_detected():
    assert archive.is_single_file_archive(_zip({'only.bin': b'data'})) is True


def test_rar_and_tar_are_rejected_but_plain_data_is_allowed():
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
        payload = b'content'
        info = tarfile.TarInfo('file.txt')
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))

    assert archive.is_unsupported_archive(b'Rar!payload') is True
    assert archive.is_unsupported_archive(tar_buffer.getvalue()) is True
    assert archive.is_unsupported_archive(b'plain binary') is False


def test_pe_detection_uses_extension_and_header_signature():
    header = bytearray(128)
    header[:2] = b'MZ'
    header[0x3C:0x40] = struct.pack('<I', 64)
    header[64:68] = b'PE\x00\x00'

    assert archive.is_pe_file('program.EXE', b'short') is True
    assert archive.is_pe_file('program.bin', bytes(header)) is True
    assert archive.is_pe_file('program.bin', b'MZ' + b'0' * 20) is False


def test_zip_encryption_flag_is_detected(monkeypatch):
    info = type('Info', (), {'flag_bits': 1})()
    fake_zip = type('FakeZip', (), {
        '__enter__': lambda self: self,
        '__exit__': lambda self, *args: None,
        'infolist': lambda self: [info],
    })()
    monkeypatch.setattr(archive.zipfile, 'ZipFile', lambda *a, **k: fake_zip)

    assert archive.is_archive_password_protected(b'data') is True


def test_email_configuration_and_plain_text_send(monkeypatch):
    send = monkeypatch.setattr(email.resend.Emails, 'send', lambda params: params)
    email.configure({'ApiKey': 'test-key', 'From': 'sender@example.test'})

    with patch.object(email.resend.Emails, 'send') as resend_send:
        assert email.send_email('user@example.test', 'Subject', 'Body') is True
        params = resend_send.call_args.args[0]
        assert params['from'] == 'sender@example.test'
        assert params['to'] == ['user@example.test']
        assert params['text'] == 'Body'


def test_html_email_and_email_failures():
    email.configure({'ApiKey': 'test-key'})
    with patch.object(email.resend.Emails, 'send') as send:
        assert email.send_html_email(
            'user@example.test', 'Subject', '<b>Body</b>', 'Body'
        ) is True
        assert send.call_args.args[0]['html'] == '<b>Body</b>'
        assert send.call_args.args[0]['text'] == 'Body'

    with patch.object(email.resend.Emails, 'send', side_effect=RuntimeError):
        assert email.send_email('user@example.test', 'Subject', 'Body') is False
        assert email.send_html_email('user@example.test', 'Subject', '<b>x</b>') is False

    email.configure({})
    assert email.send_email('user@example.test', 'Subject', 'Body') is False
    assert email.send_html_email('user@example.test', 'Subject', '<b>x</b>') is False


def test_template_filters_cover_dates_sizes_mentions_and_invalid_values(app):
    filters = app.jinja_env.filters
    globals_ = app.jinja_env.globals
    now = datetime(2026, 1, 2, 3, 4)

    assert filters['PRETTYTIME'](now) == '2026-01-02 03:04'
    assert filters['PRETTYTIME']('not-a-date') == 'not-a-date'
    assert filters['PRETTYTIMEFORMAT'](now, '%Y') == '2026'
    assert filters['FILESIZE'](0) == '-'
    assert filters['FILESIZE'](2048) == '2.00 KB'
    assert filters['FILESIZE'](2**21) == '2.00 MB'
    assert filters['FILESIZE'](2**31) == '2.00 GB'
    rendered = str(filters['render_mentions']('<script> @alice'))
    assert '&lt;script&gt;' in rendered
    assert '<a href="/user/alice">@alice</a>' in rendered
    assert globals_['TIMECOMPARE'](now, now + timedelta(seconds=10), 5) is True
    assert globals_['DIFFERENT_DATE'](now, now + timedelta(days=1)) is True


def test_session_helpers_preserve_unrelated_state(app):
    from app.services.session import clear_session, get_session, get_username, is_authenticated

    with app.test_request_context('/'):
        session = get_session()
        session.update(name='alice', email='alice@example.test', unrelated='keep')
        assert get_username() == 'alice'
        assert is_authenticated() is True
        clear_session()
        assert is_authenticated() is False
        assert session['unrelated'] == 'keep'


def test_repopulate_and_flash_helper(app):
    from flask import get_flashed_messages
    from app.services.view import add_flash, repopulate

    context = {}
    repopulate(['name', 'email'], {'name': 'alice'}, context)
    assert context == {'name': 'alice', 'email': ''}
    with app.test_request_context('/'):
        add_flash('Saved', 'success')
        assert get_flashed_messages(with_categories=True) == [('success', 'Saved')]
