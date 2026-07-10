"""Integration tests for models using the configured disposable database."""

import pytest

from app.models.errors import ErrNoResult
from app.models.user import user_by_mail, user_by_name


def test_user_lookup_is_case_insensitive(app, alice):
    assert user_by_name('ALICE')['email'] == 'alice@example.test'
    assert user_by_mail('ALICE@EXAMPLE.TEST')['name'] == 'alice'


def test_missing_user_raises(app):
    with pytest.raises(ErrNoResult):
        user_by_name('missing')


def test_crackme_lookup_and_counts(app, sample_crackme):
    from app.models.crackme import (
        count_crackmes,
        count_crackmes_by_user,
        crackme_by_hexid,
    )

    found = crackme_by_hexid(sample_crackme['hexid'])
    assert found['name'] == 'Test Crackme'
    assert count_crackmes() == 1
    assert count_crackmes_by_user('alice') == 1


def test_missing_crackme_raises(app):
    from bson import ObjectId
    from app.models.crackme import crackme_by_hexid

    with pytest.raises(ErrNoResult):
        crackme_by_hexid(str(ObjectId()))


def test_comments_are_ordered_and_hidden_comments_excluded(app, db, sample_crackme):
    from datetime import datetime, timedelta, timezone
    from app.models.comment import comments_by_crackme

    now = datetime.now(timezone.utc)
    db.comment.insert_many([
        {'author': 'bob', 'crackmehexid': sample_crackme['hexid'],
         'info': 'second', 'visible': True, 'created_at': now},
        {'author': 'alice', 'crackmehexid': sample_crackme['hexid'],
         'info': 'first', 'visible': True, 'created_at': now - timedelta(minutes=1)},
        {'author': 'alice', 'crackmehexid': sample_crackme['hexid'],
         'info': 'hidden', 'visible': False, 'created_at': now},
    ])

    assert [item['info'] for item in comments_by_crackme(sample_crackme['hexid'])] == [
        'first', 'second'
    ]


def test_solution_exists_for_only_the_submitting_user(app, db, sample_crackme):
    from app.models.solution import solution_exists

    db.solution.insert_one({
        'author': 'alice',
        'crackmeid': sample_crackme['_id'],
        'visible': True,
    })

    assert solution_exists('alice', sample_crackme['_id']) is True
    assert solution_exists('bob', sample_crackme['_id']) is False
