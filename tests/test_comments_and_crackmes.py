"""Integration tests for comments and crackme ownership/upload workflows."""

from io import BytesIO


def test_comment_creation_updates_count_and_notifies_owner(
        bob_client, db, sample_crackme, bob):
    response = bob_client.post(
        f"/comment/{sample_crackme['hexid']}",
        data={'comment': 'Useful challenge, thanks!'},
    )

    assert response.status_code == 302
    comment = db.comment.find_one({'author': 'bob'})
    assert comment['info'] == 'Useful challenge, thanks!'
    assert comment['spoiler'] is False
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['nbcomments'] == 1
    assert db.notifications.count_documents({'user': 'alice'}) == 1


def test_comment_mentions_only_existing_thread_participants(
        alice_client, bob_client, db, sample_crackme, bob):
    alice_client.post(
        f"/comment/{sample_crackme['hexid']}", data={'comment': 'Initial note'}
    )
    db.notifications.delete_many({})

    bob_client.post(
        f"/comment/{sample_crackme['hexid']}",
        data={'comment': '@alice and @outsider please review'},
    )

    assert db.notifications.count_documents({'user': 'alice'}) == 1
    assert db.notifications.count_documents({'user': 'outsider'}) == 0


def test_crackme_author_can_toggle_any_comment_spoiler(
        alice_client, db, sample_crackme, bob):
    from app.models.comment import comment_create

    comment = comment_create('Potential spoiler', 'bob', sample_crackme['hexid'])
    path = f"/comment/{comment['_id']}/spoiler"

    assert alice_client.post(path).status_code == 302
    assert db.comment.find_one({'_id': comment['_id']})['spoiler'] is True
    assert alice_client.post(path).status_code == 302
    assert db.comment.find_one({'_id': comment['_id']})['spoiler'] is False


def test_comment_author_cannot_remove_own_spoiler(
        bob_client, db, sample_crackme, bob):
    from app.models.comment import comment_create

    comment = comment_create(
        'My spoiler', 'bob', sample_crackme['hexid'], spoiler=True
    )
    response = bob_client.post(f"/comment/{comment['_id']}/spoiler")

    assert response.status_code == 302
    assert db.comment.find_one({'_id': comment['_id']})['spoiler'] is True


def test_crackme_upload_creates_pending_record_file_and_ratings(
        alice_client, db, alice, tmp_path, monkeypatch):
    from app.controllers import crackme as crackme_controller

    monkeypatch.setattr(crackme_controller, 'UPLOAD_FOLDER', str(tmp_path))
    response = alice_client.post('/upload/crackme', data={
        'name': 'Uploaded Challenge',
        'info': 'Analyze this small challenge.',
        'lang': 'C/C++',
        'difficulty': '3',
        'platform': 'Linux',
        'arch': 'x86-64',
        'file': (BytesIO(b'not-an-archive-binary'), '../../challenge.bin'),
    }, content_type='multipart/form-data')

    assert response.status_code == 302
    assert response.headers['Location'] == '/upload/crackme/submitted'
    crackme = db.crackme.find_one({'name': 'Uploaded Challenge'})
    assert crackme['visible'] is False
    assert crackme['original_filename'] == 'challenge.bin'
    assert (tmp_path / crackme['hexid']).read_bytes() == b'not-an-archive-binary'
    assert db.rating_difficulty.find_one({'crackmehexid': crackme['hexid']})['rating'] == 3
    assert db.rating_quality.find_one({'crackmehexid': crackme['hexid']})['rating'] == 4


def test_crackme_upload_requires_all_metadata_and_file(alice_client, db, alice):
    missing_metadata = alice_client.post('/upload/crackme', data={'name': 'Incomplete'})
    missing_file = alice_client.post('/upload/crackme', data={
        'name': 'No File', 'info': 'Info', 'lang': 'C/C++', 'difficulty': '3',
        'platform': 'Linux', 'arch': 'x86-64',
    })

    assert missing_metadata.status_code == 200
    assert b'Field missing: info' in missing_metadata.data
    assert missing_file.status_code == 200
    assert b'Field missing: file' in missing_file.data
    assert db.crackme.count_documents({}) == 0


def test_owner_can_edit_crackme_but_other_user_cannot(
        alice_client, bob_client, db, sample_crackme, bob):
    path = f"/crackme/{sample_crackme['hexid']}/edit"

    denied = bob_client.post(path, data={
        'info': 'Unauthorized', 'lang': 'Python', 'arch': 'ARM',
        'platform': 'Windows',
    })
    allowed = alice_client.post(path, data={
        'info': 'Updated information', 'lang': 'Rust', 'arch': 'ARM',
        'platform': 'Linux',
    })

    assert denied.status_code == 302
    assert allowed.status_code == 302
    updated = db.crackme.find_one({'_id': sample_crackme['_id']})
    assert updated['info'] == 'Updated information'
    assert updated['lang'] == 'Rust'


def test_comment_author_can_delete_own_comment(
        bob_client, db, sample_crackme, bob):
    from app.models.comment import comment_create
    from app.models.crackme import crackme_increment_comments

    comment = comment_create('To be deleted', 'bob', sample_crackme['hexid'])
    crackme_increment_comments(sample_crackme['hexid'])

    assert db.crackme.find_one({'_id': sample_crackme['_id']})['nbcomments'] == 1

    response = bob_client.post(f"/comment/{comment['_id']}/delete")
    assert response.status_code == 302
    assert db.comment.find_one({'_id': comment['_id']}) is None
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['nbcomments'] == 0


def test_other_user_cannot_delete_comment(
        alice_client, db, sample_crackme, bob):
    from app.models.comment import comment_create
    from app.models.crackme import crackme_increment_comments

    comment = comment_create('Bob comment', 'bob', sample_crackme['hexid'])
    crackme_increment_comments(sample_crackme['hexid'])

    response = alice_client.post(f"/comment/{comment['_id']}/delete")
    assert response.status_code == 302
    assert db.comment.find_one({'_id': comment['_id']}) is not None
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['nbcomments'] == 1


def test_comment_author_can_edit_own_comment(
        bob_client, db, sample_crackme, bob):
    from app.models.comment import comment_create

    comment = comment_create('Original comment text', 'bob', sample_crackme['hexid'])

    response = bob_client.post(
        f"/comment/{comment['_id']}/edit",
        data={'comment': 'Updated comment text'}
    )
    assert response.status_code == 302
    updated = db.comment.find_one({'_id': comment['_id']})
    assert updated['info'] == 'Updated comment text'
    assert updated.get('edited') is True
    assert updated.get('updated_at') is not None


def test_other_user_cannot_edit_comment(
        alice_client, db, sample_crackme, bob):
    from app.models.comment import comment_create

    comment = comment_create('Bob original', 'bob', sample_crackme['hexid'])

    response = alice_client.post(
        f"/comment/{comment['_id']}/edit",
        data={'comment': 'Alice tampering'}
    )
    assert response.status_code == 302
    unchanged = db.comment.find_one({'_id': comment['_id']})
    assert unchanged['info'] == 'Bob original'


def test_comment_edit_empty_text_rejected(
        bob_client, db, sample_crackme, bob):
    from app.models.comment import comment_create

    comment = comment_create('Valid text', 'bob', sample_crackme['hexid'])

    response = bob_client.post(
        f"/comment/{comment['_id']}/edit",
        data={'comment': '   '}
    )
    assert response.status_code == 302
    unchanged = db.comment.find_one({'_id': comment['_id']})
    assert unchanged['info'] == 'Valid text'


def test_comment_edit_notifies_new_mentions(
        alice_client, bob_client, db, sample_crackme, bob):
    from app.models.comment import comment_create

    # Alice participates in thread
    comment_create('Alice here', 'alice', sample_crackme['hexid'])
    db.notifications.delete_many({})

    # Bob creates comment without mention
    comment = comment_create('Bob note', 'bob', sample_crackme['hexid'])

    # Bob edits comment to mention Alice
    response = bob_client.post(
        f"/comment/{comment['_id']}/edit",
        data={'comment': 'Bob note @alice check this'}
    )
    assert response.status_code == 302
    assert db.notifications.count_documents({'user': 'alice'}) == 1


def test_comment_delete_nonexistent_handled(bob_client):
    response = bob_client.post("/comment/507f1f77bcf86cd799439011/delete")
    assert response.status_code == 302

