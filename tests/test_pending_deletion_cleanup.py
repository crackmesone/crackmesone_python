"""Regressions for files left in the review queue after account deletion."""

from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
import pytest


@pytest.fixture
def submission_root(monkeypatch, tmp_path):
    from review import routes

    monkeypatch.setattr(routes, 'CRACKMESONE_DIR', str(tmp_path))
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)
    for directory in (
        'tmp/crackme', 'tmp/solution', 'static/crackme', 'static/solution',
        'private/crackme_source',
    ):
        (tmp_path / directory).mkdir(parents=True)
    return tmp_path


def _crackme(db, author, root, visible=False):
    oid = ObjectId()
    doc = {
        '_id': oid, 'hexid': str(oid), 'name': f'Submission {oid}',
        'author': author, 'created_at': datetime.now(timezone.utc),
        'visible': visible, 'deleted': False,
    }
    db.crackme.insert_one(doc)
    path = root / (f'static/crackme/{oid}.zip' if visible
                   else f'tmp/crackme/{oid}')
    path.write_bytes(b'submission')
    (root / 'private/crackme_source' / str(oid)).write_bytes(b'source')
    return doc


def test_deleting_flood_account_cleans_queue_and_preserves_other_users(
        app, db, alice, bob, submission_root, monkeypatch):
    from review import routes

    root = submission_root
    owned = [_crackme(db, 'alice', root) for _ in range(48)]
    approved = _crackme(db, 'alice', root, visible=True)
    other = _crackme(db, 'bob', root)
    monkeypatch.setitem(routes.users, 'cleanup-admin', {'is_admin': True})
    client = app.test_client()
    with client.session_transaction() as session:
        session[routes.REVIEWER_SESSION_KEY] = 'cleanup-admin'
        session[routes.REVIEWER_ADMIN_KEY] = True
        session[routes.REVIEWER_CSRF_KEY] = 'cleanup-csrf'

    assert routes.count_pending_items('crackme') == 49
    response = client.post('/review/deleteuser', data={
        'action': 'confirm_delete', 'confirmed_email': alice['email'],
        'csrf_token': 'cleanup-csrf',
    })

    assert response.status_code == 200
    assert b'User account deletion successful!' in response.data
    assert db.user.find_one({'name': 'alice'}) is None
    assert db.user.find_one({'name': 'bob'}) is not None
    assert db.crackme.count_documents({'author': 'alice'}) == 0
    assert routes.count_pending_items('crackme') == 1
    queue, error = routes.get_pending_crackmes()
    assert error is None
    assert [item['crackme_uuid'] for item in queue] == [other['hexid']]
    assert b'uuid not found in db' not in client.get('/review/reviewcrackme').data
    for doc in owned + [approved]:
        assert not (root / 'tmp/crackme' / doc['hexid']).exists()
        assert not (root / 'private/crackme_source' / doc['hexid']).exists()
    assert not (root / 'static/crackme' / f"{approved['hexid']}.zip").exists()
    assert (root / 'tmp/crackme' / other['hexid']).read_bytes() == b'submission'
    assert (root / 'private/crackme_source' / other['hexid']).exists()


@pytest.mark.parametrize('visible,attachment', [(False, True), (False, False), (True, True)])
def test_account_deletion_removes_solutions_without_corrupting_public_count(
        db, alice, bob, sample_crackme, submission_root, visible, attachment):
    from review import routes

    oid = ObjectId()
    db.solution.insert_one({
        '_id': oid, 'hexid': str(oid), 'author': 'bob',
        'crackmeid': sample_crackme['_id'], 'visible': visible,
        'has_attachment': attachment,
    })
    db.crackme.update_one({'_id': sample_crackme['_id']},
                         {'$set': {'nbsolutions': 2}})
    pending = submission_root / 'tmp/solution' / str(oid)
    archive = submission_root / 'static/solution' / f'{oid}.zip'
    if attachment:
        (archive if visible else pending).write_bytes(b'solution')

    assert 'deletion successful' in routes.delete_user_account(bob['email'])
    assert db.solution.find_one({'_id': oid}) is None
    assert not pending.exists()
    assert not archive.exists()
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['nbsolutions'] == (
        1 if visible else 2
    )


def test_crackme_cascade_removes_another_authors_pending_solution(
        db, alice, bob, submission_root):
    from review import routes

    crackme = _crackme(db, 'alice', submission_root)
    oid = ObjectId()
    db.solution.insert_one({
        '_id': oid, 'hexid': str(oid), 'author': 'bob',
        'crackmeid': crackme['_id'], 'visible': False,
    })
    pending = submission_root / 'tmp/solution' / str(oid)
    pending.write_bytes(b'solution')

    assert 'deletion successful' in routes.delete_user_account(alice['email'])
    assert not pending.exists()
    assert db.solution.find_one({'_id': oid}) is None
    assert db.user.find_one({'name': 'bob'}) is not None


@pytest.mark.parametrize('blocked', ['crackme', 'solution', 'source'])
def test_file_deletion_failure_preserves_account_and_related_documents(
        db, alice, bob, submission_root, monkeypatch, blocked):
    from review import routes

    crackme = _crackme(db, 'alice', submission_root)
    oid = ObjectId()
    db.solution.insert_one({
        '_id': oid, 'hexid': str(oid), 'author': 'bob',
        'crackmeid': crackme['_id'], 'visible': False,
    })
    solution_path = submission_root / 'tmp/solution' / str(oid)
    solution_path.write_bytes(b'solution')
    blocked_path = {
        'crackme': submission_root / 'tmp/crackme' / crackme['hexid'],
        'solution': solution_path,
        'source': submission_root / 'private/crackme_source' / crackme['hexid'],
    }[blocked]
    remove = routes.os.remove

    def refuse_file(path):
        if Path(path) == blocked_path:
            raise PermissionError('test file is not writable')
        return remove(path)

    monkeypatch.setattr(routes.os, 'remove', refuse_file)
    result = routes.delete_user_account(alice['email'])

    assert result.startswith('Error during deletion:')
    assert 'test file is not writable' in result
    assert db.user.find_one({'name': 'alice'}) is not None
    assert db.crackme.find_one({'_id': crackme['_id']}) is not None
    assert db.solution.find_one({'_id': oid}) is not None
    assert blocked_path.exists()
