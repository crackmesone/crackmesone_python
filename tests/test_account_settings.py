"""Tests for renaming users/crackmes and changing emails.

Covers both the cascade model helpers and the account-settings / crackme-edit
controllers, including the "user renames while a writeup is pending review"
scenario.
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.models.errors import ErrNoResult
from app.models.user import user_rename, user_change_email, user_by_name


def _seed_alice_content(db, author='alice'):
    """Insert one document of every kind that references a username."""
    cid = ObjectId()
    hexid = str(cid)
    db.crackme.insert_one({
        '_id': cid, 'hexid': hexid, 'name': 'C1', 'author': author,
        'visible': True, 'deleted': False,
    })
    db.comment.insert_one({
        'author': author, 'crackmehexid': hexid, 'crackmename': 'C1',
        'info': 'nice', 'visible': True, 'created_at': datetime.now(timezone.utc),
    })
    db.solution.insert_one({
        '_id': ObjectId(), 'hexid': str(ObjectId()), 'author': author,
        'crackmeid': cid, 'crackmehexid': hexid, 'crackmename': 'C1',
        'visible': False, 'deleted': False, 'info': 'sol',
    })
    db.rating_difficulty.insert_one({'author': author, 'crackmehexid': hexid, 'rating': 3})
    db.rating_quality.insert_one({'author': author, 'crackmehexid': hexid, 'rating': 4})
    db.notifications.insert_one({'user': author, 'text': 'hi', 'seen': False})
    db.label_request.insert_one({
        'requester': author, 'crackme_hexid': hexid, 'crackme_name': 'C1',
        'status': 'pending',
    })
    db.account_deletion_request.insert_one({
        'requester': author, 'email': 'alice@example.test', 'status': 'pending',
    })
    return hexid


# --------------------------------------------------------------------------- #
# Model: username rename cascade
# --------------------------------------------------------------------------- #

def test_user_rename_cascades_every_reference(app, db, alice):
    _seed_alice_content(db, 'alice')

    user_rename('alice', 'alice_renamed')

    # The user document itself is renamed...
    assert user_by_name('alice_renamed')['email'] == 'alice@example.test'
    with pytest.raises(ErrNoResult):
        user_by_name('alice')

    # ...and no reference to the old name survives anywhere.
    assert db.crackme.count_documents({'author': 'alice'}) == 0
    assert db.comment.count_documents({'author': 'alice'}) == 0
    assert db.solution.count_documents({'author': 'alice'}) == 0
    assert db.rating_difficulty.count_documents({'author': 'alice'}) == 0
    assert db.rating_quality.count_documents({'author': 'alice'}) == 0
    assert db.notifications.count_documents({'user': 'alice'}) == 0
    assert db.label_request.count_documents({'requester': 'alice'}) == 0
    assert db.account_deletion_request.count_documents({'requester': 'alice'}) == 0

    # Every reference now points at the new name.
    assert db.crackme.count_documents({'author': 'alice_renamed'}) == 1
    assert db.comment.count_documents({'author': 'alice_renamed'}) == 1
    assert db.solution.count_documents({'author': 'alice_renamed'}) == 1
    assert db.rating_difficulty.count_documents({'author': 'alice_renamed'}) == 1
    assert db.rating_quality.count_documents({'author': 'alice_renamed'}) == 1
    assert db.notifications.count_documents({'user': 'alice_renamed'}) == 1
    assert db.label_request.count_documents({'requester': 'alice_renamed'}) == 1
    assert db.account_deletion_request.count_documents({'requester': 'alice_renamed'}) == 1


def test_user_rename_missing_user_raises(app, db):
    with pytest.raises(ErrNoResult):
        user_rename('nobody', 'somebody')


def test_user_rename_failure_leaves_user_on_old_name(app, db, alice, monkeypatch):
    """A mid-cascade failure must not rename the user doc (no session lockout)."""
    import app.models.user as user_model
    _seed_alice_content(db, 'alice')
    real_get = user_model.get_collection

    def boom(name):
        if name == 'solution':          # fail partway through the cascade
            raise RuntimeError('db blip')
        return real_get(name)

    monkeypatch.setattr(user_model, 'get_collection', boom)

    with pytest.raises(RuntimeError):
        user_rename('alice', 'alice_new')

    monkeypatch.undo()
    # The user document still resolves under the old name, so the session stays
    # valid and the rename can simply be retried.
    assert user_by_name('alice')['email'] == 'alice@example.test'
    with pytest.raises(ErrNoResult):
        user_by_name('alice_new')


def test_user_rename_leaves_other_users_untouched(app, db, alice, bob):
    db.crackme.insert_one({
        '_id': ObjectId(), 'hexid': str(ObjectId()), 'name': 'B', 'author': 'bob',
        'visible': True, 'deleted': False,
    })
    user_rename('alice', 'alice2')
    assert db.crackme.count_documents({'author': 'bob'}) == 1


# --------------------------------------------------------------------------- #
# Model: email change
# --------------------------------------------------------------------------- #

def test_user_change_email_updates_copies_and_drops_tokens(app, db, alice):
    db.account_deletion_request.insert_one({
        'requester': 'alice', 'email': 'alice@example.test', 'status': 'pending',
    })
    db.password_reset_tokens.insert_one({
        'email': 'alice@example.test', 'token': 'tok',
    })

    old = user_change_email('alice', 'NewAlice@Example.test')

    assert old == 'alice@example.test'
    assert user_by_name('alice')['email'] == 'newalice@example.test'
    # Denormalized copy on the pending deletion request is refreshed...
    assert db.account_deletion_request.find_one(
        {'requester': 'alice'})['email'] == 'newalice@example.test'
    # ...and stale reset tokens for the old address are gone.
    assert db.password_reset_tokens.count_documents({'email': 'alice@example.test'}) == 0


# --------------------------------------------------------------------------- #
# Model: crackme rename cascade
# --------------------------------------------------------------------------- #

def test_crackme_rename_cascades_denormalized_name(app, db, sample_crackme):
    from app.models.crackme import crackme_update

    hexid = sample_crackme['hexid']
    db.comment.insert_one({
        'author': 'bob', 'crackmehexid': hexid, 'crackmename': 'Test Crackme',
        'info': 'c', 'visible': True, 'created_at': datetime.now(timezone.utc),
    })
    db.solution.insert_one({
        '_id': ObjectId(), 'hexid': str(ObjectId()), 'author': 'bob',
        'crackmeid': sample_crackme['_id'], 'crackmehexid': hexid,
        'crackmename': 'Test Crackme', 'visible': True, 'deleted': False,
    })
    db.label_request.insert_one({
        'requester': 'bob', 'crackme_hexid': hexid, 'crackme_name': 'Test Crackme',
        'status': 'pending',
    })

    changes = crackme_update(hexid, {'name': 'Renamed Crackme'})

    assert changes['name']['new'] == 'Renamed Crackme'
    assert db.crackme.find_one({'hexid': hexid})['name'] == 'Renamed Crackme'
    assert db.comment.find_one({'crackmehexid': hexid})['crackmename'] == 'Renamed Crackme'
    assert db.solution.find_one({'crackmehexid': hexid})['crackmename'] == 'Renamed Crackme'
    assert db.label_request.find_one({'crackme_hexid': hexid})['crackme_name'] == 'Renamed Crackme'


# --------------------------------------------------------------------------- #
# Controller: username change
# --------------------------------------------------------------------------- #

def test_change_username_endpoint_renames_and_cascades(app, db, alice, alice_client):
    hexid = _seed_alice_content(db, 'alice')

    resp = alice_client.post('/settings/username', data={
        'name': 'alice_new', 'current_password': 'alice-password',
    })
    assert resp.status_code == 302

    assert user_by_name('alice_new')['email'] == 'alice@example.test'
    assert db.crackme.find_one({'hexid': hexid})['author'] == 'alice_new'
    # Session was updated to the new name.
    with alice_client.session_transaction() as sess:
        assert sess['name'] == 'alice_new'


def test_change_username_rejects_name_taken_by_other(app, db, alice, bob, alice_client):
    resp = alice_client.post('/settings/username', data={
        'name': 'bob', 'current_password': 'alice-password',
    })
    assert resp.status_code == 302
    # alice keeps her name; bob is untouched.
    assert user_by_name('alice')['email'] == 'alice@example.test'
    assert user_by_name('bob')['email'] == 'bob@example.test'


def test_change_username_rejects_wrong_password(app, db, alice, alice_client):
    resp = alice_client.post('/settings/username', data={
        'name': 'alice_new', 'current_password': 'wrong',
    })
    assert resp.status_code == 302
    with pytest.raises(ErrNoResult):
        user_by_name('alice_new')


def test_pending_writeup_survives_username_change(app, db, alice, alice_client):
    """A writeup submitted before a rename must remain owned and still pending."""
    cid = ObjectId()
    sol_id = ObjectId()
    db.crackme.insert_one({
        '_id': cid, 'hexid': str(cid), 'name': 'C', 'author': 'someoneelse',
        'visible': True, 'deleted': False,
    })
    db.solution.insert_one({
        '_id': sol_id, 'hexid': str(sol_id), 'author': 'alice', 'crackmeid': cid,
        'crackmehexid': str(cid), 'crackmename': 'C', 'visible': False,
        'deleted': False, 'info': 'wip',
    })

    alice_client.post('/settings/username', data={
        'name': 'alice2', 'current_password': 'alice-password',
    })

    sol = db.solution.find_one({'_id': sol_id})
    assert sol['author'] == 'alice2'          # ownership preserved
    assert sol['visible'] is False            # still in the review queue


# --------------------------------------------------------------------------- #
# Controller: email change
# --------------------------------------------------------------------------- #

def test_change_email_endpoint(app, db, alice, alice_client):
    resp = alice_client.post('/settings/email', data={
        'email': 'alice2@example.test', 'current_password': 'alice-password',
    })
    assert resp.status_code == 302
    assert user_by_name('alice')['email'] == 'alice2@example.test'
    with alice_client.session_transaction() as sess:
        assert sess['email'] == 'alice2@example.test'


def test_change_email_rejects_taken(app, db, alice, bob, alice_client):
    resp = alice_client.post('/settings/email', data={
        'email': 'bob@example.test', 'current_password': 'alice-password',
    })
    assert resp.status_code == 302
    assert user_by_name('alice')['email'] == 'alice@example.test'


# --------------------------------------------------------------------------- #
# Controller: crackme rename via edit form
# --------------------------------------------------------------------------- #

def test_edit_crackme_renames_via_form(app, db, alice, alice_client, sample_crackme):
    hexid = sample_crackme['hexid']
    db.solution.insert_one({
        '_id': ObjectId(), 'hexid': str(ObjectId()), 'author': 'bob',
        'crackmeid': sample_crackme['_id'], 'crackmehexid': hexid,
        'crackmename': 'Test Crackme', 'visible': True, 'deleted': False,
    })

    resp = alice_client.post(f'/crackme/{hexid}/edit', data={
        'name': 'Brand New Name', 'info': 'updated', 'lang': 'C/C++',
        'arch': 'x86-64', 'platform': 'Linux',
    })
    assert resp.status_code == 302
    assert db.crackme.find_one({'hexid': hexid})['name'] == 'Brand New Name'
    assert db.solution.find_one({'crackmehexid': hexid})['crackmename'] == 'Brand New Name'


def test_edit_crackme_rejects_empty_name(app, db, alice, alice_client, sample_crackme):
    hexid = sample_crackme['hexid']
    resp = alice_client.post(f'/crackme/{hexid}/edit', data={
        'name': '  ', 'info': 'x', 'lang': 'C/C++', 'arch': 'x86-64',
        'platform': 'Linux',
    })
    assert resp.status_code == 302
    assert db.crackme.find_one({'hexid': hexid})['name'] == 'Test Crackme'
