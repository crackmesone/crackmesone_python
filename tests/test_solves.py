"""Flag submission, solve records and the points they award."""

import zipfile
from io import BytesIO

import pytest

from app.services.flag import flags_match, is_valid_flag_format, normalize_flag
from app.services.points import points_for_solve, solve_difficulty

FLAG = 'CMO{a_perfectly_good_flag}'


def _hexid(user):
    """The immutable id solves are keyed by."""
    return user.get('hexid') or str(user['_id'])


def _zip_bytes():
    """A two-file zip, which is what the archive checks accept."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr('main.c', 'int main(void){return 0;}')
        archive.writestr('Makefile', 'all:\n\tcc main.c')
    buf.seek(0)
    return buf


@pytest.fixture
def flagged_crackme(db, sample_crackme):
    """Alice's crackme, opted into auto-validation at difficulty 3."""
    db.crackme.update_one(
        {'_id': sample_crackme['_id']},
        {'$set': {
            'flag': FLAG,
            'source_original_filename': 'source.zip',
            'official_difficulty': 3,
        }}
    )
    return db.crackme.find_one({'_id': sample_crackme['_id']})


# ---------------------------------------------------------------- flag format

@pytest.mark.parametrize('flag', [
    'CMO{ok}',
    'CMO{' + 'x' * 56 + '}',
])
def test_valid_flags_are_accepted(flag):
    assert is_valid_flag_format(flag)


@pytest.mark.parametrize('flag', [
    '',
    'ok',
    'CTF{ok}',
    'CMO{}',
    'CMO{nested{braces}}',
    'CMO{has space}',
    'CMO{' + 'x' * 57 + '}',        # longer than the body limit
    'prefix CMO{ok}',
    'CMO{\u00fcnicode}',            # ASCII only, so a flag's bytes stay bounded
    'CMO{tab\tinside}',
])
def test_invalid_flags_are_rejected(flag):
    assert not is_valid_flag_format(flag)


def test_surrounding_whitespace_is_not_a_wrong_answer():
    assert normalize_flag(f'  {FLAG}\n') == FLAG


def test_flags_match_only_the_exact_flag():
    assert flags_match(FLAG, FLAG)
    assert not flags_match(FLAG, 'CMO{wrong}')
    assert not flags_match(FLAG, FLAG.upper())
    assert not flags_match(None, FLAG)
    assert not flags_match(FLAG, '')


# -------------------------------------------------------------------- scoring

def test_official_difficulty_prices_a_solve():
    crackme = {'official_difficulty': 4, 'difficulty': 1.2}

    assert solve_difficulty(crackme) == 4
    assert points_for_solve(crackme) == 400


def test_scoring_falls_back_to_the_community_rating_when_unofficial():
    # Crackmes approved before reviewers assigned difficulties have none.
    assert points_for_solve({'difficulty': 2.6}) == 300
    assert points_for_solve({'official_difficulty': None, 'difficulty': 0}) == 100
    assert points_for_solve({'difficulty': 99}) == 600


# --------------------------------------------------------------------- upload

def _upload(client, monkeypatch, tmp_path, **extra):
    from app.controllers import crackme as crackme_controller

    monkeypatch.setattr(crackme_controller, 'UPLOAD_FOLDER', str(tmp_path / 'pending'))
    monkeypatch.setattr(crackme_controller, 'SOURCE_UPLOAD_FOLDER', str(tmp_path / 'source'))
    data = {
        'name': 'Flagged Challenge',
        'info': 'Find the flag.',
        'lang': 'C/C++',
        'difficulty': '3',
        'platform': 'Linux',
        'arch': 'x86-64',
        'file': (BytesIO(b'challenge-binary'), 'challenge.bin'),
    }
    data.update(extra)
    return client.post('/upload/crackme', data=data,
                       content_type='multipart/form-data',
                       follow_redirects=True)


def test_opting_into_auto_validation_stores_flag_hash_and_private_source(
        alice_client, db, alice, tmp_path, monkeypatch):
    response = _upload(alice_client, monkeypatch, tmp_path,
                       auto_validation='on', flag=FLAG,
                       source=(_zip_bytes(), 'source.zip'))

    assert response.status_code == 200
    assert b'has been submitted' in response.data or b'Flagged Challenge' in response.data
    crackme = db.crackme.find_one({'name': 'Flagged Challenge'})
    assert crackme['flag'] == FLAG
    assert crackme['source_original_filename'] == 'source.zip'
    assert crackme['official_difficulty'] is None
    # The source archive lands outside static/, where nothing serves it.
    assert (tmp_path / 'source' / crackme['hexid']).exists()


def test_upload_without_opting_in_stores_no_flag(
        alice_client, db, alice, tmp_path, monkeypatch):
    response = _upload(alice_client, monkeypatch, tmp_path)

    assert response.status_code == 200
    assert db.crackme.find_one({'name': 'Flagged Challenge'})['flag'] is None


def test_auto_validation_requires_a_well_formed_flag_and_a_source_archive(
        alice_client, db, alice, tmp_path, monkeypatch):
    bad_flag = _upload(alice_client, monkeypatch, tmp_path,
                       auto_validation='on', flag='not-a-flag',
                       source=(_zip_bytes(), 'source.zip'))
    no_source = _upload(alice_client, monkeypatch, tmp_path,
                        auto_validation='on', flag=FLAG)

    assert b'Invalid flag format' in bad_flag.data
    assert b'needs a source archive' in no_source.data
    assert db.crackme.count_documents({}) == 0


# ---------------------------------------------------------------- solve flow

def test_correct_flag_records_a_solve_and_awards_points(
        bob_client, db, bob, flagged_crackme):
    response = bob_client.post(f"/crackme/{flagged_crackme['hexid']}/solve",
                               data={'flag': f'  {FLAG} '},
                               follow_redirects=True)

    assert response.status_code == 200
    solve = db.solve.find_one({'user_hexid': _hexid(bob)})
    assert solve['crackme_hexid'] == flagged_crackme['hexid']
    assert solve['points'] == 300
    assert solve['difficulty'] == 3
    assert db.notifications.count_documents({'user': 'bob'}) == 1


def test_wrong_flag_records_nothing(bob_client, db, bob, flagged_crackme):
    response = bob_client.post(f"/crackme/{flagged_crackme['hexid']}/solve",
                               data={'flag': 'CMO{nope}'},
                               follow_redirects=True)

    assert b'Wrong flag' in response.data
    assert db.solve.count_documents({}) == 0


def test_resubmitting_a_correct_flag_does_not_award_twice(
        bob_client, db, bob, flagged_crackme):
    path = f"/crackme/{flagged_crackme['hexid']}/solve"
    bob_client.post(path, data={'flag': FLAG})
    again = bob_client.post(path, data={'flag': FLAG}, follow_redirects=True)

    assert b'already solved' in again.data
    assert db.solve.count_documents({'user_hexid': _hexid(bob)}) == 1


def test_author_cannot_solve_their_own_crackme(
        alice_client, db, alice, flagged_crackme):
    response = alice_client.post(f"/crackme/{flagged_crackme['hexid']}/solve",
                                 data={'flag': FLAG}, follow_redirects=True)

    assert b"your own crackme" in response.data
    assert db.solve.count_documents({}) == 0


def test_crackme_without_auto_validation_accepts_no_flags(
        bob_client, db, bob, sample_crackme):
    response = bob_client.post(f"/crackme/{sample_crackme['hexid']}/solve",
                               data={'flag': FLAG}, follow_redirects=True)

    assert b'does not accept flag submissions' in response.data
    assert db.solve.count_documents({}) == 0


def test_anonymous_visitors_cannot_submit_flags(client, db, flagged_crackme):
    response = client.post(f"/crackme/{flagged_crackme['hexid']}/solve",
                           data={'flag': FLAG})

    assert response.status_code == 302
    assert response.headers['Location'] == '/'
    assert db.solve.count_documents({}) == 0


# ------------------------------------------------------------------ rendering

def test_crackme_page_shows_the_flag_form_and_then_the_solved_state(
        bob_client, db, bob, flagged_crackme):
    path = f"/crackme/{flagged_crackme['hexid']}"

    before = bob_client.get(path)
    assert b'Submit flag' in before.data
    assert b'300 points' in before.data

    bob_client.post(f'{path}/solve', data={'flag': FLAG})
    after = bob_client.get(path)

    assert b'Solved!' in after.data
    assert b'Submit flag' not in after.data


def test_crackme_page_has_no_flag_section_without_auto_validation(
        bob_client, db, sample_crackme):
    response = bob_client.get(f"/crackme/{sample_crackme['hexid']}")

    assert b'Submit flag' not in response.data


def test_profile_shows_score_and_solved_crackmes(
        bob_client, client, db, bob, flagged_crackme):
    bob_client.post(f"/crackme/{flagged_crackme['hexid']}/solve", data={'flag': FLAG})

    profile = client.get('/user/bob')

    assert profile.status_code == 200
    assert b'Score:' in profile.data
    assert b'>Solves<' in profile.data
    assert flagged_crackme['name'].encode() in profile.data


def test_profile_of_a_user_without_solves_scores_zero(client, db, alice):
    profile = client.get('/user/alice')

    assert profile.status_code == 200
    assert b'No flags submitted yet.' in profile.data


# ------------------------------------------------------------ reviewer tools

def _review_dirs(monkeypatch, tmp_path):
    """Point the reviewer file helpers at throwaway directories."""
    from review import routes

    pending = tmp_path / 'pending'
    approved = tmp_path / 'approved'
    source = tmp_path / 'source'
    for path in (pending / 'crackme', pending / 'solution',
                 approved / 'crackme', approved / 'solution', source):
        path.mkdir(parents=True)

    monkeypatch.setattr(routes, 'get_tmp_dir', lambda item_type: str(pending / item_type))
    monkeypatch.setattr(routes, 'get_static_dir', lambda item_type: str(approved / item_type))
    monkeypatch.setattr(routes, 'get_source_dir', lambda: str(source))
    return pending, approved, source


def test_reviewer_downloads_the_private_source_archive(
        reviewer_client, db, flagged_crackme, monkeypatch, tmp_path):
    _, _, source = _review_dirs(monkeypatch, tmp_path)
    (source / flagged_crackme['hexid']).write_bytes(b'source-archive')

    response = reviewer_client.get(
        f"/review/downloadreview?type=source&uuid={flagged_crackme['hexid']}"
    )

    assert response.status_code == 200
    assert response.data == b'source-archive'
    assert 'source.zip' in response.headers['Content-Disposition']


def test_approval_records_the_official_difficulty(
        reviewer_client, db, flagged_crackme, monkeypatch, tmp_path):
    from review import routes

    pending, _, _ = _review_dirs(monkeypatch, tmp_path)
    db.crackme.update_one({'_id': flagged_crackme['_id']},
                          {'$set': {'visible': False, 'official_difficulty': None}})
    (pending / 'crackme' / flagged_crackme['hexid']).write_bytes(b'binary')
    monkeypatch.setattr(routes, 'create_password_protected_zip', lambda *a: (True, None))
    monkeypatch.setattr(routes, 'notify_crackme_approved', lambda *a: None)
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)

    response = reviewer_client.post('/review/approvecrackme', data={
        'uuid': flagged_crackme['hexid'], 'official_difficulty': '5',
        'csrf_token': 'test-csrf-token',
    })

    assert response.status_code == 302
    stored = db.crackme.find_one({'_id': flagged_crackme['_id']})
    assert stored['visible'] is True
    assert stored['official_difficulty'] == 5


def test_rejecting_a_crackme_removes_its_private_source(
        reviewer_client, db, flagged_crackme, monkeypatch, tmp_path):
    from review import routes

    pending, _, source = _review_dirs(monkeypatch, tmp_path)
    db.crackme.update_one({'_id': flagged_crackme['_id']}, {'$set': {'visible': False}})
    (pending / 'crackme' / flagged_crackme['hexid']).write_bytes(b'binary')
    archive = source / flagged_crackme['hexid']
    archive.write_bytes(b'source-archive')
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)

    reviewer_client.post('/review/rejectcrackme', data={
        'uuid': flagged_crackme['hexid'], 'reject_reason': 'nope',
        'csrf_token': 'test-csrf-token',
    })

    assert archive.exists() is False
    assert db.crackme.count_documents({}) == 0


def test_deleting_a_crackme_takes_its_solves_and_source_with_it(
        db, bob, flagged_crackme, monkeypatch, tmp_path):
    from review import routes

    _, approved, source = _review_dirs(monkeypatch, tmp_path)
    (approved / 'crackme' / f"{flagged_crackme['hexid']}.zip").write_bytes(b'zip')
    archive = source / flagged_crackme['hexid']
    archive.write_bytes(b'source-archive')
    db.solve.insert_one({
        'user_hexid': _hexid(bob),
        'crackme_hexid': flagged_crackme['hexid'],
        'points': 300,
    })

    message = routes.delete_approved_crackme(flagged_crackme['hexid'])

    assert '1 solves' in message
    assert db.solve.count_documents({}) == 0
    assert archive.exists() is False


def test_deleting_a_user_removes_their_solves(db, bob, flagged_crackme, monkeypatch):
    from review import routes

    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)
    db.solve.insert_one({
        'user_hexid': _hexid(bob),
        'crackme_hexid': flagged_crackme['hexid'],
        'points': 300,
    })

    preview, error = routes.preview_user_deletion(bob['email'])
    assert error is None
    assert preview['solves'] == 1

    routes.delete_user_account(bob['email'])

    assert db.solve.count_documents({}) == 0


def test_review_page_offers_the_flag_tools_for_an_opted_in_crackme(
        reviewer_client, db, flagged_crackme):
    response = reviewer_client.get(
        f"/review/viewcrackme?crackme_uuid={flagged_crackme['hexid']}"
    )

    assert response.status_code == 200
    assert b'Download source archive' in response.data
    assert b'Official difficulty' in response.data
    # Reviewers need to see the flag to confirm the crackme is really solvable.
    assert FLAG.encode() in response.data


def test_review_page_says_so_when_a_crackme_is_not_auto_validated(
        reviewer_client, db, sample_crackme):
    response = reviewer_client.get(
        f"/review/viewcrackme?crackme_uuid={sample_crackme['hexid']}"
    )

    assert response.status_code == 200
    assert b'did not opt into auto-validation' in response.data


def test_public_pages_never_render_the_flag(client, bob_client, db, flagged_crackme):
    # The flag is stored in cleartext for reviewers, so the public views must
    # keep rendering a fixed set of fields that doesn't include it.
    pages = [
        client.get(f"/crackme/{flagged_crackme['hexid']}"),
        bob_client.get(f"/crackme/{flagged_crackme['hexid']}"),
        client.get('/lasts/1'),
        client.get('/user/alice'),
        client.get('/search?name=Test'),
        client.get('/rss'),
    ]

    for page in pages:
        assert FLAG.encode() not in page.data


def _admin_client(app):
    from review import routes
    from review.routes import (
        REVIEWER_ADMIN_KEY, REVIEWER_CSRF_KEY, REVIEWER_SESSION_KEY
    )

    routes.users['admin'] = {'password_hash': 'x', 'is_admin': True}
    client = app.test_client()
    with client.session_transaction() as session:
        session[REVIEWER_SESSION_KEY] = 'admin'
        session[REVIEWER_ADMIN_KEY] = True
        session[REVIEWER_CSRF_KEY] = 'test-csrf-token'
    return client


@pytest.fixture
def admin_client(app):
    from review import routes

    client = _admin_client(app)
    yield client
    routes.users.pop('admin', None)


def _edit(client, crackme, **overrides):
    data = {
        'crackme_uuid': crackme['hexid'],
        'csrf_token': 'test-csrf-token',
        'info': crackme.get('info', ''),
        'lang': crackme.get('lang', ''),
        'arch': crackme.get('arch', ''),
        'platform': crackme.get('platform', ''),
        'flag': crackme.get('flag') or '',
        'official_difficulty': str(crackme.get('official_difficulty') or ''),
    }
    data.update(overrides)
    return client.post('/review/editcrackme', data=data,
                       content_type='multipart/form-data')


def test_admin_edits_every_crackme_field_including_flag_and_difficulty(
        admin_client, db, flagged_crackme, monkeypatch):
    from review import routes

    logged = []
    monkeypatch.setattr(routes, 'log_reviewer_operation',
                        lambda op, who, details, ok: logged.append(details))

    response = _edit(admin_client, flagged_crackme,
                     info='Rewritten description', lang='Rust', arch='ARM',
                     platform='Windows', flag='CMO{corrected}',
                     official_difficulty='6', notify_author='on')

    assert response.status_code == 200
    stored = db.crackme.find_one({'_id': flagged_crackme['_id']})
    assert stored['info'] == 'Rewritten description'
    assert stored['lang'] == 'Rust'
    assert stored['arch'] == 'ARM'
    assert stored['platform'] == 'Windows'
    assert stored['flag'] == 'CMO{corrected}'
    assert stored['official_difficulty'] == 6
    # The flag change is recorded, but neither the log nor the author's
    # notification quotes the flag itself.
    assert 'flag changed' in logged[0]['changes']
    assert 'CMO{corrected}' not in str(logged[0])
    assert 'CMO{corrected}' not in db.notifications.find_one({'user': 'alice'})['text']


def test_a_corrected_flag_is_the_one_that_now_scores(
        admin_client, bob_client, db, bob, flagged_crackme, monkeypatch):
    from review import routes

    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)
    _edit(admin_client, flagged_crackme, flag='CMO{corrected}', official_difficulty='6')
    path = f"/crackme/{flagged_crackme['hexid']}/solve"

    stale = bob_client.post(path, data={'flag': FLAG}, follow_redirects=True)
    corrected = bob_client.post(path, data={'flag': 'CMO{corrected}'},
                                follow_redirects=True)

    assert b'Wrong flag' in stale.data
    assert b'Correct!' in corrected.data
    assert db.solve.find_one({'user_hexid': _hexid(bob)})['points'] == 600


def test_admin_turns_auto_validation_off_without_erasing_earned_points(
        admin_client, db, bob, flagged_crackme, monkeypatch):
    from review import routes

    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)
    db.solve.insert_one({
        'user_hexid': _hexid(bob), 'crackme_hexid': flagged_crackme['hexid'],
        'points': 300, 'difficulty': 3,
    })

    _edit(admin_client, flagged_crackme, remove_flag='on')

    assert db.crackme.find_one({'_id': flagged_crackme['_id']})['flag'] is None
    assert db.solve.count_documents({}) == 1


def test_admin_edit_rejects_a_malformed_flag_or_difficulty(
        admin_client, db, flagged_crackme, monkeypatch):
    from review import routes

    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)

    bad_flag = _edit(admin_client, flagged_crackme, flag='nope')
    bad_difficulty = _edit(admin_client, flagged_crackme, official_difficulty='9')

    assert b'Invalid flag format' in bad_flag.data
    assert b'Invalid official difficulty' in bad_difficulty.data
    stored = db.crackme.find_one({'_id': flagged_crackme['_id']})
    assert stored['flag'] == FLAG
    assert stored['official_difficulty'] == 3


def test_admin_replaces_the_private_source_archive(
        admin_client, db, flagged_crackme, monkeypatch, tmp_path):
    from review import routes

    _, _, source = _review_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)

    _edit(admin_client, flagged_crackme,
          source_file=(_zip_bytes(), 'rebuilt-source.zip'))

    stored = db.crackme.find_one({'_id': flagged_crackme['_id']})
    assert stored['source_original_filename'] == 'rebuilt-source.zip'
    assert (source / flagged_crackme['hexid']).exists()


def test_admin_edit_page_shows_the_flag_and_difficulty_fields(
        admin_client, db, flagged_crackme):
    response = admin_client.get(
        f"/review/editcrackme?crackme_uuid={flagged_crackme['hexid']}"
    )

    assert response.status_code == 200
    assert FLAG.encode() in response.data
    assert b'Official difficulty' in response.data
    assert b'Private source archive' in response.data


def test_non_admin_reviewers_cannot_reach_the_editor(reviewer_client, flagged_crackme):
    response = reviewer_client.get(
        f"/review/editcrackme?crackme_uuid={flagged_crackme['hexid']}"
    )

    assert response.status_code == 403


# ------------------------------------------------- upload failure recovery

def test_a_rejected_upload_keeps_what_the_user_typed(
        alice_client, db, alice, tmp_path, monkeypatch):
    from app.controllers import crackme as crackme_controller

    monkeypatch.setattr(crackme_controller, 'UPLOAD_FOLDER', str(tmp_path / 'pending'))
    response = alice_client.post('/upload/crackme', data={
        'name': 'Half Filled Challenge',
        'info': 'A long description nobody wants to retype.',
        'lang': 'Rust',
        'difficulty': '5',
        'platform': 'Windows',
        'arch': 'ARM',
        'labels': ['Packer'],
        'auto_validation': 'on',
        'flag': 'CMO{typed_but_not_lost}',
        # ... and no file, so the submission is rejected.
    }, content_type='multipart/form-data')

    assert response.status_code == 200
    body = response.data.decode()
    assert 'Field missing: file' in body
    assert 'value="Half Filled Challenge"' in body
    assert 'A long description nobody wants to retype.' in body
    assert 'value="CMO{typed_but_not_lost}"' in body
    # Radios and label checkboxes come back ticked too.
    assert 'value="Rust" checked' in body
    assert 'value="5" checked' in body
    assert 'value="Windows" checked' in body
    assert 'value="ARM" checked' in body
    assert 'value="Packer" data-label-class="1" checked' in body


def test_background_submits_report_errors_as_json(
        alice_client, db, alice, tmp_path, monkeypatch):
    from app.controllers import crackme as crackme_controller

    monkeypatch.setattr(crackme_controller, 'UPLOAD_FOLDER', str(tmp_path / 'pending'))
    response = alice_client.post('/upload/crackme', data={
        'name': 'No File Challenge', 'info': 'info', 'lang': 'C/C++',
        'difficulty': '3', 'platform': 'Linux', 'arch': 'x86-64',
    }, content_type='multipart/form-data',
        headers={'X-Requested-With': 'XMLHttpRequest'})

    assert response.status_code == 400
    assert response.json == {'ok': False, 'error': 'Field missing: file'}


def test_background_submits_get_the_confirmation_url_on_success(
        alice_client, db, alice, tmp_path, monkeypatch):
    from app.controllers import crackme as crackme_controller

    monkeypatch.setattr(crackme_controller, 'UPLOAD_FOLDER', str(tmp_path / 'pending'))
    response = alice_client.post('/upload/crackme', data={
        'name': 'Ajax Challenge', 'info': 'info', 'lang': 'C/C++',
        'difficulty': '3', 'platform': 'Linux', 'arch': 'x86-64',
        'file': (BytesIO(b'binary'), 'challenge.bin'),
    }, content_type='multipart/form-data',
        headers={'X-Requested-With': 'XMLHttpRequest'})

    assert response.status_code == 200
    assert response.json == {'ok': True, 'redirect': '/upload/crackme/submitted'}
    assert db.crackme.find_one({'name': 'Ajax Challenge'}) is not None

    confirmation = alice_client.get('/upload/crackme/submitted')
    assert b'Ajax Challenge' in confirmation.data
    # One-shot: refreshing the confirmation doesn't re-announce the submission.
    assert alice_client.get('/upload/crackme/submitted').status_code == 302


def test_auto_validation_is_ticked_by_default_on_a_fresh_form(alice_client, alice):
    body = alice_client.get('/upload/crackme').data.decode()

    assert 'id="auto_validation" name="auto_validation" checked' in body
    # Labels sit at the end of the form, after the auto-validation block.
    assert body.index('Auto-validation') < body.index('Select the anti-analysis')


def test_unticking_auto_validation_survives_a_rejected_upload(
        alice_client, db, alice, tmp_path, monkeypatch):
    from app.controllers import crackme as crackme_controller

    monkeypatch.setattr(crackme_controller, 'UPLOAD_FOLDER', str(tmp_path / 'pending'))
    response = alice_client.post('/upload/crackme', data={
        'name': 'No Flag Here', 'info': 'info', 'lang': 'C/C++',
        'difficulty': '3', 'platform': 'Linux', 'arch': 'x86-64',
        # auto_validation deliberately absent: the user unticked it.
    }, content_type='multipart/form-data')

    body = response.data.decode()
    assert 'id="auto_validation" name="auto_validation" checked' not in body
