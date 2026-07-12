"""Coverage for the remaining reviewer administration and archive workflows."""

import json
from datetime import datetime, timezone
from io import BytesIO

from bson import ObjectId


def _admin_client(app):
    from review import auth, routes

    routes.users['workflow-admin'] = {'password_hash': 'unused', 'is_admin': True}
    auth.configure(routes.users)
    client = app.test_client()
    with client.session_transaction() as session:
        session['_reviewer_user'] = 'workflow-admin'
        session['_reviewer_is_admin'] = True
        session['_reviewer_csrf_token'] = 'workflow-csrf'
    return client


def _cleanup_admin():
    from review import routes
    routes.users.pop('workflow-admin', None)


def test_reviewer_downloads_pending_attachment(
        reviewer_client, db, sample_crackme, monkeypatch, tmp_path):
    from review import routes

    pending = tmp_path / 'solution'
    pending.mkdir()
    file_path = pending / sample_crackme['hexid']
    file_path.write_bytes(b'pending attachment')
    db.solution.insert_one({
        'hexid': sample_crackme['hexid'], 'original_filename': 'analysis.txt'
    })
    monkeypatch.setattr(routes, 'get_tmp_dir', lambda kind: str(pending))

    response = reviewer_client.get(
        f"/review/downloadreview?type=solution&uuid={sample_crackme['hexid']}"
    )

    assert response.status_code == 200
    assert response.data == b'pending attachment'
    assert 'analysis.txt' in response.headers['Content-Disposition']
    assert reviewer_client.get('/review/downloadreview?type=bad&uuid=x').status_code == 404


def test_admin_edits_crackme_metadata_and_notifies_author(
        app, db, sample_crackme, monkeypatch):
    from review import routes

    client = _admin_client(app)
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **k: None)
    response = client.post('/review/editcrackme', data={
        'csrf_token': 'workflow-csrf',
        'crackme_uuid': sample_crackme['hexid'],
        'info': 'Reviewer-updated description',
        'lang': 'Rust', 'arch': 'ARM', 'platform': 'Linux',
        'notify_author': 'on',
    })

    assert response.status_code == 200
    updated = db.crackme.find_one({'_id': sample_crackme['_id']})
    assert updated['info'] == 'Reviewer-updated description'
    assert updated['lang'] == 'Rust'
    assert db.notifications.count_documents({'user': 'alice'}) == 1
    _cleanup_admin()


def test_admin_replaces_crackme_file(app, db, sample_crackme, monkeypatch, tmp_path):
    from review import routes

    client = _admin_client(app)
    monkeypatch.setattr(routes, 'CRACKMESONE_DIR', str(tmp_path))
    monkeypatch.setattr(routes, 'get_static_dir', lambda kind: str(tmp_path))
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **k: None)
    monkeypatch.setattr(
        routes, 'create_password_protected_zip', lambda *a: (True, None)
    )
    response = client.post('/review/editcrackme', data={
        'csrf_token': 'workflow-csrf', 'crackme_uuid': sample_crackme['hexid'],
        'info': sample_crackme['info'], 'lang': sample_crackme['lang'],
        'arch': sample_crackme['arch'], 'platform': sample_crackme['platform'],
        'file': (BytesIO(b'replacement'), 'replacement.bin'),
    }, content_type='multipart/form-data')

    assert response.status_code == 200
    assert b'updated successfully' in response.data
    _cleanup_admin()


def test_admin_lists_toggles_and_deletes_comments(
        app, db, sample_crackme, bob, monkeypatch):
    from review import routes

    client = _admin_client(app)
    comment_id = ObjectId()
    db.comment.insert_one({
        '_id': comment_id, 'author': 'bob', 'info': 'Moderate me',
        'crackmehexid': sample_crackme['hexid'], 'spoiler': False,
    })
    db.crackme.update_one({'_id': sample_crackme['_id']}, {'$set': {'nbcomments': 1}})
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **k: None)

    listing = client.get(f"/review/delcomment?crackme_uuid={sample_crackme['hexid']}")
    toggled = client.post('/review/delcomment', data={
        'csrf_token': 'workflow-csrf', 'crackme_uuid': sample_crackme['hexid'],
        'comment_uuid': str(comment_id), 'action': 'toggle_spoiler',
    })
    deleted = client.post('/review/delcomment', data={
        'csrf_token': 'workflow-csrf', 'crackme_uuid': sample_crackme['hexid'],
        'comment_uuid': str(comment_id), 'action': 'delete',
    })

    assert listing.status_code == toggled.status_code == deleted.status_code == 200
    assert b'Moderate me' in listing.data
    assert db.comment.find_one({'_id': comment_id}) is None
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['nbcomments'] == 0
    _cleanup_admin()


def test_full_user_lookup_and_delete_preview(app, db, alice, sample_crackme, monkeypatch):
    from review import routes

    client = _admin_client(app)
    db.comment.insert_one({
        'author': 'alice', 'info': 'A' * 120,
        'crackmehexid': sample_crackme['hexid'], 'created_at': datetime.now(timezone.utc),
    })
    db.rating_difficulty.insert_one({
        'author': 'alice', 'rating': 3, 'crackmehexid': sample_crackme['hexid'],
        'created_at': datetime.now(timezone.utc),
    })
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **k: None)
    lookup = client.post('/review/lookupuser', data={
        'csrf_token': 'workflow-csrf', 'search_query': 'alice', 'show_all': '1',
    })
    preview = client.post('/review/deleteuser', data={
        'csrf_token': 'workflow-csrf', 'action': 'preview',
        'user_email': 'alice@example.test', 'confirm_email': 'alice@example.test',
    })

    assert lookup.status_code == preview.status_code == 200
    assert b'alice@example.test' in lookup.data
    assert b'Test Crackme' in lookup.data
    assert b'alice' in preview.data
    _cleanup_admin()


def test_delete_user_account_removes_owned_data(db, alice, monkeypatch, tmp_path):
    from review import routes

    monkeypatch.setattr(routes, 'get_static_dir', lambda kind: str(tmp_path))
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **k: None)
    db.notifications.insert_one({'user': 'alice'})
    db.comment.insert_one({'author': 'alice', 'crackmehexid': 'other'})
    db.rating_difficulty.insert_one({'author': 'alice', 'crackmehexid': 'other'})
    db.rating_quality.insert_one({'author': 'alice', 'crackmehexid': 'other'})

    message = routes.delete_user_account('alice@example.test', 'workflow-admin')

    assert 'deletion successful' in message.lower()
    assert db.user.find_one({'name': 'alice'}) is None
    assert db.notifications.count_documents({'user': 'alice'}) == 0
    assert db.comment.count_documents({'author': 'alice'}) == 0


def test_admin_deletes_toggles_and_changes_reviewer(app, db, monkeypatch):
    from review import routes

    client = _admin_client(app)
    routes.users['target-reviewer'] = {'password_hash': 'old', 'is_admin': False}
    monkeypatch.setattr(routes, 'save_users', lambda: None)
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **k: None)

    toggle = client.post('/review/managereviewers', data={
        'csrf_token': 'workflow-csrf', 'action': 'toggle_admin',
        'username_to_toggle': 'target-reviewer',
    })
    change = client.post('/review/managereviewers', data={
        'csrf_token': 'workflow-csrf', 'action': 'change_password',
        'username_to_change': 'target-reviewer', 'change_password': 'new-secret',
    })
    delete = client.post('/review/managereviewers', data={
        'csrf_token': 'workflow-csrf', 'action': 'delete',
        'username_to_delete': 'target-reviewer',
    })

    assert toggle.status_code == change.status_code == delete.status_code == 200
    assert 'target-reviewer' not in routes.users
    _cleanup_admin()


def _archive_paths(monkeypatch, tmp_path):
    from review import routes

    archive_dir = tmp_path / 'archive'
    archive_dir.mkdir()
    monkeypatch.setattr(routes, 'ARCHIVE_DIR', str(archive_dir))
    monkeypatch.setattr(routes, 'ARCHIVE_STATUS_FILE', str(archive_dir / 'status.json'))
    monkeypatch.setattr(routes, 'CRACKMESONE_DIR', str(tmp_path))
    return archive_dir


def test_site_archive_helpers_and_path_validation(db, monkeypatch, tmp_path):
    from review import routes

    archive_dir = _archive_paths(monkeypatch, tmp_path)
    assert routes.get_archive_status() == {'status': 'idle'}
    routes.set_archive_status('running', step='Testing')
    assert routes.get_archive_status()['step'] == 'Testing'
    archive = archive_dir / 'crackmesone_20260101_000000.zip'
    archive.write_bytes(b'zip')
    assert routes.get_archive_list()[0]['filename'] == archive.name
    assert routes.delete_archive('../bad.zip')[0] is False
    assert routes.delete_archive(archive.name)[0] is True
    routes.clear_archive_status()
    assert routes.get_archive_status() == {'status': 'idle'}


def test_site_archive_background_success_and_failure(
        db, sample_crackme, monkeypatch, tmp_path):
    from review import routes

    archive_dir = _archive_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **k: None)
    routes.create_site_archive_background('workflow-admin')
    status = routes.get_archive_status()
    assert status['status'] == 'completed'
    assert (archive_dir / status['filename']).exists()

    monkeypatch.setattr('app.services.database.get_db', lambda: None)
    routes.create_site_archive_background('workflow-admin')
    assert routes.get_archive_status()['status'] == 'error'


def test_site_archive_routes_start_poll_download_and_delete(
        app, db, monkeypatch, tmp_path):
    from review import routes

    client = _admin_client(app)
    archive_dir = _archive_paths(monkeypatch, tmp_path)
    archive = archive_dir / 'crackmesone_test.zip'
    archive.write_bytes(b'archive')
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **k: None)

    class ImmediateThread:
        daemon = False
        def __init__(self, target, args):
            self.target, self.args = target, args
        def start(self):
            routes.set_archive_status('completed', filename='created.zip')

    monkeypatch.setattr(routes.threading, 'Thread', ImmediateThread)
    started = client.post('/review/sitearchive', data={
        'csrf_token': 'workflow-csrf', 'action': 'create',
    })
    status = client.get('/review/sitearchive/status')
    download = client.get('/review/downloadarchive/crackmesone_test.zip')
    deleted = client.post('/review/sitearchive', data={
        'csrf_token': 'workflow-csrf', 'action': 'delete',
        'filename': 'crackmesone_test.zip',
    })

    assert started.status_code == status.status_code == download.status_code == deleted.status_code == 200
    assert json.loads(status.data)['status'] == 'completed'
    assert download.data == b'archive'
    assert archive.exists() is False
    _cleanup_admin()
