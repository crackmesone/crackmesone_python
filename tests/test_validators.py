"""Unit tests for application input-validation helpers."""

import pytest
from werkzeug.datastructures import MultiDict

from app.services.view import (
    authorized_chars_only,
    is_valid_hexid,
    validate_required,
)


@pytest.mark.parametrize('value', [
    'alice',
    'Alice_123',
    'user-name',
    'user+tag@example.test',
])
def test_authorized_chars_accepts_supported_names_and_emails(value):
    assert authorized_chars_only(value) is True


@pytest.mark.parametrize('value', [
    'user name',
    'user<script>',
    'user/example',
    'snowman☃',
])
def test_authorized_chars_rejects_unsupported_characters(value):
    assert authorized_chars_only(value) is False


@pytest.mark.parametrize('value', [
    '507f1f77bcf86cd799439011',
    'ABCDEF77BCF86CD799439011',
])
def test_valid_hexids(value):
    assert is_valid_hexid(value) is True


@pytest.mark.parametrize('value', [
    '',
    '507f1f77bcf86cd79943901',
    '507f1f77bcf86cd7994390110',
    '507f1f77bcf86cd79943901z',
])
def test_invalid_hexids(value):
    assert is_valid_hexid(value) is False


def test_required_fields_reports_the_first_missing_field():
    form = MultiDict({'name': 'alice', 'email': ''})
    assert validate_required(form, ['name', 'email', 'password']) == (False, 'email')


def test_required_fields_accepts_complete_form():
    form = MultiDict({'name': 'alice', 'email': 'alice@example.test'})
    assert validate_required(form, ['name', 'email']) == (True, None)
