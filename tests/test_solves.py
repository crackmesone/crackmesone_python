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


def test_fractional_official_difficulty_supports_author_selected_points():
    crackme = {'official_difficulty': 3.57, 'difficulty': 1.2}

    assert solve_difficulty(crackme) == 3.57
    assert points_for_solve(crackme) == 357


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
                       auto_validation='on', flag=FLAG, points='357',
                       source=(_zip_bytes(), 'source.zip'))

    assert response.status_code == 200
    assert b'has been submitted' in response.data or b'Flagged Challenge' in response.data
    crackme = db.crackme.find_one({'name': 'Flagged Challenge'})
    assert crackme['flag'] == FLAG
    assert crackme['source_original_filename'] == 'source.zip'
    assert crackme['official_difficulty'] == 3.57
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


def test_auto_validation_requires_the_verification_file_to_be_a_zip(
        alice_client, db, alice, tmp_path, monkeypatch):
    response = _upload(
        alice_client, monkeypatch, tmp_path,
        auto_validation='on', flag=FLAG,
        source=(BytesIO(b'# plain text writeup'), 'writeup.txt'),
    )

    assert b'must be a valid ZIP archive' in response.data
    assert db.crackme.count_documents({}) == 0


@pytest.mark.parametrize('points', ['99', '601', '250.5', 'many'])
def test_auto_validation_rejects_invalid_points(
        alice_client, db, alice, tmp_path, monkeypatch, points):
    response = _upload(
        alice_client, monkeypatch, tmp_path,
        auto_validation='on', flag=FLAG, points=points,
        source=(_zip_bytes(), 'source.zip'),
    )

    assert b'Points must be a whole number from 100 to 600' in response.data
    assert db.crackme.count_documents({}) == 0


def test_auto_validation_points_default_to_selected_difficulty(
        alice_client, db, alice, tmp_path, monkeypatch):
    response = _upload(
        alice_client, monkeypatch, tmp_path,
        difficulty='4', auto_validation='on', flag=FLAG,
        source=(_zip_bytes(), 'source.zip'),
    )

    assert response.status_code == 200
    assert db.crackme.find_one({'name': 'Flagged Challenge'})[
        'official_difficulty'
    ] == 4.0


# ---------------------------------------------------------------- solve flow

def test_correct_flag_records_a_solve_and_awards_points(
        bob_client, db, bob, flagged_crackme, monkeypatch):
    from app.controllers import crackme as crackme_controller
    solve_notifications = []
    monkeypatch.setattr(
        crackme_controller, 'notify_first_blood',
        lambda *args: solve_notifications.append(args),
    )
    response = bob_client.post(f"/crackme/{flagged_crackme['hexid']}/solve",
                               data={'flag': f'  {FLAG} '},
                               follow_redirects=True)

    assert response.status_code == 200
    solve = db.solve.find_one({'user_hexid': _hexid(bob)})
    assert solve['crackme_hexid'] == flagged_crackme['hexid']
    assert solve['points'] == 300
    assert solve['difficulty'] == 3
    assert db.notifications.count_documents({'user': 'bob'}) == 0
    submission = db.flag_submission.find_one({})
    assert submission['user_hexid'] == _hexid(bob)
    assert submission['username'] == 'bob'
    assert submission['crackme_hexid'] == flagged_crackme['hexid']
    assert submission['submitted_flag'] == FLAG
    assert submission['result'] == 'correct'
    assert solve_notifications == [(
        'bob', flagged_crackme['name'], flagged_crackme['hexid'], 300
    )]


def test_only_first_solver_gets_public_announcement(
        app, bob_client, db, bob, flagged_crackme, monkeypatch):
    from app.controllers import crackme as crackme_controller

    announcements = []
    monkeypatch.setattr(
        crackme_controller, 'notify_first_blood',
        lambda *args: announcements.append(args),
    )
    path = f"/crackme/{flagged_crackme['hexid']}/solve"
    bob_client.post(path, data={'flag': FLAG})

    db.user.insert_one({'name': 'charlie', 'email': 'charlie@example.test'})
    charlie_client = app.test_client()
    with charlie_client.session_transaction() as session:
        session['name'] = 'charlie'
        session['email'] = 'charlie@example.test'
    charlie_client.post(path, data={'flag': FLAG})
    bob_client.post(path, data={'flag': FLAG})

    assert db.solve.count_documents({'crackme_hexid': flagged_crackme['hexid']}) == 2
    assert len(announcements) == 1
    assert announcements[0][0] == 'bob'
    assert db.crackme.find_one({'hexid': flagged_crackme['hexid']})[
        'first_blood_notified'
    ] is True


def test_solve_snapshots_fractional_difficulty(
        bob_client, db, bob, flagged_crackme):
    db.crackme.update_one(
        {'_id': flagged_crackme['_id']},
        {'$set': {'official_difficulty': 3.57}},
    )

    bob_client.post(
        f"/crackme/{flagged_crackme['hexid']}/solve", data={'flag': FLAG}
    )

    solve = db.solve.find_one({'user_hexid': _hexid(bob)})
    assert solve['points'] == 357
    assert solve['difficulty'] == 3.57


def test_wrong_flag_records_nothing(
        bob_client, db, bob, flagged_crackme, monkeypatch):
    from app.controllers import crackme as crackme_controller
    solve_notifications = []
    monkeypatch.setattr(
        crackme_controller, 'notify_first_blood',
        lambda *args: solve_notifications.append(args),
    )
    response = bob_client.post(f"/crackme/{flagged_crackme['hexid']}/solve",
                               data={'flag': 'CMO{nope}'},
                               follow_redirects=True)

    assert b'Wrong flag' in response.data
    assert db.solve.count_documents({}) == 0
    submission = db.flag_submission.find_one({})
    assert submission['submitted_flag'] == 'CMO{nope}'
    assert submission['result'] == 'incorrect'
    assert solve_notifications == []


def test_resubmitting_a_correct_flag_does_not_award_twice(
        bob_client, db, bob, flagged_crackme):
    path = f"/crackme/{flagged_crackme['hexid']}/solve"
    bob_client.post(path, data={'flag': FLAG})
    again = bob_client.post(path, data={'flag': FLAG}, follow_redirects=True)

    assert b'already solved' in again.data
    assert db.solve.count_documents({'user_hexid': _hexid(bob)}) == 1
    assert [entry['result'] for entry in db.flag_submission.find({})] == [
        'correct', 'already_solved'
    ]


def test_author_cannot_solve_their_own_crackme(
        alice_client, db, alice, flagged_crackme):
    response = alice_client.post(f"/crackme/{flagged_crackme['hexid']}/solve",
                                 data={'flag': FLAG}, follow_redirects=True)

    assert b"your own crackme" in response.data
    assert db.solve.count_documents({}) == 0
    assert db.flag_submission.find_one({})['result'] == 'own_crackme'


def test_crackme_without_auto_validation_accepts_no_flags(
        bob_client, db, bob, sample_crackme):
    response = bob_client.post(f"/crackme/{sample_crackme['hexid']}/solve",
                               data={'flag': FLAG}, follow_redirects=True)

    assert b'does not accept flag submissions' in response.data
    assert db.solve.count_documents({}) == 0
    assert db.flag_submission.find_one({})['result'] == 'not_enabled'


def test_malformed_flag_submission_is_logged_with_the_submitted_value(
        bob_client, db, bob, flagged_crackme):
    response = bob_client.post(f"/crackme/{flagged_crackme['hexid']}/solve",
                               data={'flag': 'not a flag'},
                               follow_redirects=True)

    assert b'not a valid flag' in response.data
    submission = db.flag_submission.find_one({})
    assert submission['result'] == 'invalid_format'
    assert submission['user_hexid'] == _hexid(bob)
    assert submission['submitted_flag'] == 'not a flag'


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
    assert b'Solves:<br> 0' in before.data
    assert b'Attempts:<br> 0' in before.data
    assert b'Solves (0)' in before.data
    assert b'Points:<br> 300' in before.data
    assert b'Difficulty:<br>' not in before.data
    assert b'This crackme is auto-validated' not in before.data
    assert b'Comments (' not in before.data
    assert b'Writeups (' not in before.data
    assert b'Post a comment' not in before.data
    assert b'Submit a writeup' not in before.data
    assert b'<b>Labels</b>' not in before.data
    assert b'Request a label change' not in before.data
    assert b'id="rate-diff"' not in before.data
    assert b"openModal('rate-diff')" not in before.data
    assert b"openModal('rate-qual')" not in before.data

    bob_client.post(f'{path}/solve', data={'flag': 'CMO{wrong}'})
    bob_client.post(f'{path}/solve', data={'flag': FLAG})
    after = bob_client.get(path)

    assert b'Solved!' in after.data
    assert b'Submit flag' not in after.data
    assert b'Solves:<br> 1' in after.data
    assert b'Attempts:<br> 2' in after.data
    assert b'Solves (1)' in after.data
    assert b'>bob</a>' in after.data
    assert b"openModal('rate-qual')" in after.data


def test_auto_validated_crackme_rejects_comments_and_writeups_in_backend(
        bob_client, db, flagged_crackme):
    hexid = flagged_crackme['hexid']

    comment = bob_client.post(
        f'/comment/{hexid}', data={'comment': 'Backend bypass attempt'},
        follow_redirects=True
    )
    writeup_form = bob_client.get(
        f'/upload/solution/{hexid}', follow_redirects=True
    )
    writeup_post = bob_client.post(
        f'/upload/solution/{hexid}',
        data={'info': 'Bypass', 'content': 'A' * 300},
        follow_redirects=True
    )

    assert b'Comments are disabled for auto-validated crackmes' in comment.data
    assert b'Writeups are disabled for auto-validated crackmes' in writeup_form.data
    assert b'Writeups are disabled for auto-validated crackmes' in writeup_post.data
    assert db.comment.count_documents({}) == 0
    assert db.solution.count_documents({}) == 0


def test_auto_validated_crackme_rejects_difficulty_ratings_in_backend(
        bob_client, db, flagged_crackme):
    response = bob_client.post(
        f"/crackme/rate-diff/{flagged_crackme['hexid']}",
        data={'difficulty': '6'},
        follow_redirects=True
    )

    assert b'Difficulty ratings are disabled for auto-validated crackmes' in response.data
    assert db.rating_difficulty.count_documents({}) == 0


def test_auto_validated_crackme_allows_quality_rating_only_after_solve(
        bob_client, db, bob, flagged_crackme):
    path = f"/crackme/rate-qual/{flagged_crackme['hexid']}"

    before = bob_client.post(
        path, data={'quality': '6'}, follow_redirects=True
    )
    assert b'Solve this crackme before rating it' in before.data
    assert db.rating_quality.count_documents({}) == 0

    bob_client.post(
        f"/crackme/{flagged_crackme['hexid']}/solve", data={'flag': FLAG}
    )
    after = bob_client.post(
        path, data={'quality': '6'}, follow_redirects=True
    )

    assert b'Rated!' in after.data
    assert db.rating_quality.find_one({
        'author': 'bob', 'crackmehexid': flagged_crackme['hexid']
    })['rating'] == 6


def test_crackme_page_has_no_flag_section_without_auto_validation(
        bob_client, db, sample_crackme):
    response = bob_client.get(f"/crackme/{sample_crackme['hexid']}")

    assert b'Submit flag' not in response.data
    assert b'<b>Labels</b>' in response.data


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


def _approval_data(crackme, **overrides):
    data = {
        'uuid': crackme['hexid'],
        'csrf_token': 'test-csrf-token',
        'info': crackme['info'],
        'lang': crackme['lang'],
        'arch': crackme['arch'],
        'platform': crackme['platform'],
        'flag': crackme.get('flag') or '',
        'official_points': str(round(
            (crackme.get('official_difficulty') or 3) * 100
        )),
        'labels': crackme.get('labels', []),
    }
    data.update(overrides)
    return data


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

    response = reviewer_client.post(
        '/review/approvecrackme',
        data=_approval_data(
            flagged_crackme, official_points='357', info='Reviewer corrected',
            lang='Rust', arch='ARM', platform='Windows',
            flag='CMO{reviewer_corrected}',
        ),
    )

    assert response.status_code == 302
    stored = db.crackme.find_one({'_id': flagged_crackme['_id']})
    assert stored['visible'] is True
    assert stored['official_difficulty'] == 3.57
    assert stored['info'] == 'Reviewer corrected'
    assert stored['lang'] == 'Rust'
    assert stored['arch'] == 'ARM'
    assert stored['platform'] == 'Windows'
    assert stored['flag'] == 'CMO{reviewer_corrected}'


@pytest.mark.parametrize('points', ['99', '601', '250.5', 'many'])
def test_review_approval_rejects_invalid_points(
        reviewer_client, db, flagged_crackme, monkeypatch, tmp_path, points):
    from review import routes

    pending, _, _ = _review_dirs(monkeypatch, tmp_path)
    db.crackme.update_one({'_id': flagged_crackme['_id']},
                          {'$set': {'visible': False}})
    (pending / 'crackme' / flagged_crackme['hexid']).write_bytes(b'binary')
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)

    response = reviewer_client.post(
        '/review/approvecrackme',
        data=_approval_data(flagged_crackme, official_points=points),
        follow_redirects=True,
    )

    assert b'Points must be a whole number from 100 to 600' in response.data
    assert db.crackme.find_one({'_id': flagged_crackme['_id']})['visible'] is False


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
    db.flag_submission.insert_one({
        'user_hexid': _hexid(bob),
        'username': 'bob',
        'crackme_hexid': flagged_crackme['hexid'],
        'result': 'correct',
    })

    message = routes.delete_approved_crackme(flagged_crackme['hexid'])

    assert '1 solves' in message
    assert db.solve.count_documents({}) == 0
    assert db.flag_submission.count_documents({}) == 0
    assert archive.exists() is False


def test_deleting_a_user_removes_their_solves(db, bob, flagged_crackme, monkeypatch):
    from review import routes

    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)
    db.solve.insert_one({
        'user_hexid': _hexid(bob),
        'crackme_hexid': flagged_crackme['hexid'],
        'points': 300,
    })
    db.flag_submission.insert_one({
        'user_hexid': _hexid(bob),
        'username': 'bob',
        'crackme_hexid': flagged_crackme['hexid'],
        'result': 'incorrect',
    })

    preview, error = routes.preview_user_deletion(bob['email'])
    assert error is None
    assert preview['solves'] == 1
    assert preview['flag_submissions'] == 1

    routes.delete_user_account(bob['email'])

    assert db.solve.count_documents({}) == 0
    assert db.flag_submission.count_documents({}) == 0


def test_review_page_offers_the_flag_tools_for_an_opted_in_crackme(
        reviewer_client, db, flagged_crackme):
    db.flag_submission.insert_one({
        'username': 'bob',
        'crackme_hexid': flagged_crackme['hexid'],
        'submitted_flag': 'CMO{reviewed_attempt}',
        'result': 'incorrect',
    })
    response = reviewer_client.get(
        f"/review/viewcrackme?crackme_uuid={flagged_crackme['hexid']}"
    )

    assert response.status_code == 200
    assert b'Download private verification ZIP' in response.data
    assert b'name="official_points"' in response.data
    assert b'min="100" max="600" step="1"' in response.data
    # Reviewers need to see the flag to confirm the crackme is really solvable.
    assert FLAG.encode() in response.data
    assert b'Recent flag submissions' not in response.data
    assert b'CMO{reviewed_attempt}' not in response.data
    assert b'id="change-status"' in response.data
    assert b'id="discard-changes"' in response.data
    assert b'name="lang"' in response.data
    assert b'name="arch"' in response.data
    assert b'name="platform"' in response.data
    assert b'name="info"' in response.data


def test_review_page_says_so_when_a_crackme_is_not_auto_validated(
        reviewer_client, db, sample_crackme):
    response = reviewer_client.get(
        f"/review/viewcrackme?crackme_uuid={sample_crackme['hexid']}"
    )

    assert response.status_code == 200
    assert b'did not enable auto-validation' in response.data


def test_regular_reviewer_cannot_see_flag_validation_history(
        reviewer_client, db, flagged_crackme):
    db.flag_submission.insert_one({
        'username': 'bob',
        'crackme_hexid': flagged_crackme['hexid'],
        'submitted_flag': 'CMO{dashboard_attempt}',
        'result': 'incorrect',
    })

    response = reviewer_client.get('/review/dashboard')

    assert response.status_code == 200
    assert b'Review flag validations' not in response.data
    assert b'CMO{dashboard_attempt}' not in response.data
    assert reviewer_client.get('/review/flagvalidations').status_code == 403


def test_admin_opens_flag_validations_from_dashboard(
        admin_client, db, flagged_crackme):
    db.flag_submission.insert_one({
        'username': 'bob',
        'crackme_hexid': flagged_crackme['hexid'],
        'submitted_flag': 'CMO{admin_review_attempt}',
        'result': 'incorrect',
    })

    dashboard = admin_client.get('/review/dashboard')
    page = admin_client.get('/review/flagvalidations')

    assert dashboard.status_code == 200
    assert b'Review flag validations' in dashboard.data
    assert b'CMO{admin_review_attempt}' not in dashboard.data
    assert page.status_code == 200
    assert flagged_crackme['name'].encode() in page.data
    assert b'CMO{admin_review_attempt}' in page.data
    assert b'Incorrect' in page.data


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
        'official_points': str(round((crackme.get('official_difficulty') or 0) * 100) or ''),
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
                     official_points='600', notify_author='on')

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
    _edit(admin_client, flagged_crackme, flag='CMO{corrected}', official_points='600')
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
    bad_difficulty = _edit(admin_client, flagged_crackme, official_points='601')

    assert b'Invalid flag format' in bad_flag.data
    assert b'Points must be a whole number from 100 to 600' in bad_difficulty.data
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
    assert b'name="official_points"' in response.data
    assert b'min="100" max="600" step="1"' in response.data
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
    assert 'id="points" name="points" min="100" max="600" step="1"' in body
    # Labels sit at the end of the form, after the auto-validation block.
    assert body.index('Auto-validation') < body.index('Select all anti-analysis')


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
