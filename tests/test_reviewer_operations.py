"""Operational reviewer coverage for crackmes, deletion, and user tools."""

from bson import ObjectId


def _review_dirs(monkeypatch, tmp_path):
    from review import routes

    pending = tmp_path / 'pending'
    approved = tmp_path / 'approved'
    pending.mkdir()
    approved.mkdir()
    monkeypatch.setattr(
        routes, 'get_tmp_dir', lambda item_type: str(pending / item_type)
    )
    monkeypatch.setattr(
        routes, 'get_static_dir', lambda item_type: str(approved / item_type)
    )
    (pending / 'crackme').mkdir()
    (pending / 'solution').mkdir()
    (approved / 'crackme').mkdir()
    (approved / 'solution').mkdir()
    return pending, approved


def test_reviewer_approves_pending_crackme(
        reviewer_client, db, sample_crackme, monkeypatch, tmp_path):
    from review import routes

    pending, _ = _review_dirs(monkeypatch, tmp_path)
    db.crackme.update_one(
        {'_id': sample_crackme['_id']}, {'$set': {'visible': False}}
    )
    (pending / 'crackme' / sample_crackme['hexid']).write_bytes(b'binary')
    monkeypatch.setattr(
        routes, 'create_password_protected_zip', lambda *args: (True, None)
    )
    monkeypatch.setattr(routes, 'notify_crackme_approved', lambda *args: None)
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *args, **kw: None)

    response = reviewer_client.post('/review/approvecrackme', data={
        'uuid': sample_crackme['hexid'], 'csrf_token': 'test-csrf-token',
    })

    assert response.status_code == 302
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['visible'] is True
    assert db.notifications.count_documents({'user': 'alice'}) == 1


def test_reviewer_rejects_pending_crackme_and_removes_ratings(
        reviewer_client, db, sample_crackme, monkeypatch, tmp_path):
    from review import routes

    pending, _ = _review_dirs(monkeypatch, tmp_path)
    db.crackme.update_one(
        {'_id': sample_crackme['_id']}, {'$set': {'visible': False}}
    )
    db.rating_difficulty.insert_one({'crackmehexid': sample_crackme['hexid']})
    db.rating_quality.insert_one({'crackmehexid': sample_crackme['hexid']})
    pending_file = pending / 'crackme' / sample_crackme['hexid']
    pending_file.write_bytes(b'binary')
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *args, **kw: None)

    response = reviewer_client.post('/review/rejectcrackme', data={
        'uuid': sample_crackme['hexid'],
        'reject_reason': 'Does not follow the rules',
        'csrf_token': 'test-csrf-token',
    })

    assert response.status_code == 302
    assert db.crackme.find_one({'_id': sample_crackme['_id']}) is None
    assert db.rating_difficulty.count_documents({}) == 0
    assert db.rating_quality.count_documents({}) == 0
    assert pending_file.exists() is False
    assert 'Does not follow the rules' in db.notifications.find_one({})['text']


def test_crackme_approval_rolls_back_when_archive_creation_fails(
        db, sample_crackme, monkeypatch, tmp_path):
    from review import routes

    pending, _ = _review_dirs(monkeypatch, tmp_path)
    db.crackme.update_one(
        {'_id': sample_crackme['_id']}, {'$set': {'visible': False}}
    )
    (pending / 'crackme' / sample_crackme['hexid']).write_bytes(b'binary')
    monkeypatch.setattr(
        routes, 'create_password_protected_zip',
        lambda *args: (False, 'compression failed'),
    )

    success, message = routes.approve_pending_crackme(sample_crackme['hexid'])

    assert success is False
    assert message == 'compression failed'
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['visible'] is False


def test_admin_cascade_deletes_crackme_related_data(
        db, sample_crackme, monkeypatch, tmp_path):
    from review import routes

    _, approved = _review_dirs(monkeypatch, tmp_path)
    solution_id = ObjectId()
    db.solution.insert_one({
        '_id': solution_id, 'hexid': str(solution_id),
        'crackmeid': sample_crackme['_id'],
    })
    db.comment.insert_one({'crackmehexid': sample_crackme['hexid']})
    db.rating_difficulty.insert_one({'crackmehexid': sample_crackme['hexid']})
    db.rating_quality.insert_one({'crackmehexid': sample_crackme['hexid']})
    (approved / 'crackme' / f"{sample_crackme['hexid']}.zip").write_bytes(b'zip')

    message = routes.delete_approved_crackme(sample_crackme['hexid'])

    assert '1 solutions' in message
    assert '1 comments' in message
    assert db.crackme.count_documents({}) == 0
    assert db.solution.count_documents({}) == 0
    assert db.comment.count_documents({}) == 0
    assert db.rating_difficulty.count_documents({}) == 0
    assert db.rating_quality.count_documents({}) == 0


def test_admin_deletes_approved_solution_and_decrements_count(
        db, sample_crackme, monkeypatch, tmp_path):
    from review import routes

    _, approved = _review_dirs(monkeypatch, tmp_path)
    solution_id = ObjectId()
    db.solution.insert_one({
        '_id': solution_id, 'hexid': str(solution_id),
        'crackmeid': sample_crackme['_id'],
    })
    db.crackme.update_one(
        {'_id': sample_crackme['_id']}, {'$set': {'nbsolutions': 1}}
    )
    archive = approved / 'solution' / f'{solution_id}.zip'
    archive.write_bytes(b'zip')

    assert routes.delete_approved_solution(str(solution_id)) == 'Solution deleted'
    assert db.solution.count_documents({}) == 0
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['nbsolutions'] == 0
    assert archive.exists() is False


def test_admin_user_lookup_and_password_reset_helpers(db, alice, monkeypatch):
    from review import routes

    monkeypatch.setattr(routes.random, 'choices', lambda *args, **kw: list('A' * 16))
    found = routes.find_user_by_email_or_name('ALICE@EXAMPLE.TEST')
    reset_message = routes.reset_user_password('alice@example.test')
    preview, error = routes.preview_user_deletion('alice@example.test')

    assert found['name'] == 'alice'
    assert 'Password reset successful' in reset_message
    assert 'New password: AAAAAAAAAAAAAAAA' in reset_message
    assert error is None
    assert preview['username'] == 'alice'
