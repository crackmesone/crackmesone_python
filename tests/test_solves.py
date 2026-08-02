"""Flag submission, solve records and the points they award."""

import zipfile
from io import BytesIO

import pytest

from app.services.flag import (
    hash_flag, is_valid_flag_format, normalize_flag, verify_flag
)
from app.services.points import points_for_solve, solve_difficulty

FLAG = 'CM1{a_perfectly_good_flag}'


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
            'flag_hash': hash_flag(FLAG),
            'source_original_filename': 'source.zip',
            'official_difficulty': 3,
        }}
    )
    return db.crackme.find_one({'_id': sample_crackme['_id']})


# ---------------------------------------------------------------- flag format

@pytest.mark.parametrize('flag', [
    'CM1{ok}',
    'CM1{' + 'x' * 56 + '}',
])
def test_valid_flags_are_accepted(flag):
    assert is_valid_flag_format(flag)


@pytest.mark.parametrize('flag', [
    '',
    'ok',
    'CTF{ok}',
    'CM1{}',
    'CM1{nested{braces}}',
    'CM1{has space}',
    'CM1{' + 'x' * 57 + '}',        # longer than the body limit
    'prefix CM1{ok}',
    'CM1{\u00fcnicode}',            # ASCII only, so a flag's bytes stay bounded
    'CM1{tab\tinside}',
])
def test_invalid_flags_are_rejected(flag):
    assert not is_valid_flag_format(flag)


def test_surrounding_whitespace_is_not_a_wrong_answer():
    assert normalize_flag(f'  {FLAG}\n') == FLAG


def test_flag_is_stored_hashed_and_verifies():
    stored = hash_flag(FLAG)

    assert FLAG not in stored
    assert verify_flag(stored, FLAG)
    assert not verify_flag(stored, 'CM1{wrong}')
    assert not verify_flag(None, FLAG)


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
                       content_type='multipart/form-data')


def test_opting_into_auto_validation_stores_flag_hash_and_private_source(
        alice_client, db, alice, tmp_path, monkeypatch):
    response = _upload(alice_client, monkeypatch, tmp_path,
                       auto_validation='on', flag=FLAG,
                       source=(_zip_bytes(), 'source.zip'))

    assert response.status_code == 200
    crackme = db.crackme.find_one({'name': 'Flagged Challenge'})
    assert crackme['flag_hash'] != FLAG
    assert verify_flag(crackme['flag_hash'], FLAG)
    assert crackme['source_original_filename'] == 'source.zip'
    assert crackme['official_difficulty'] is None
    # The source archive lands outside static/, where nothing serves it.
    assert (tmp_path / 'source' / crackme['hexid']).exists()


def test_upload_without_opting_in_stores_no_flag(
        alice_client, db, alice, tmp_path, monkeypatch):
    response = _upload(alice_client, monkeypatch, tmp_path)

    assert response.status_code == 200
    assert db.crackme.find_one({'name': 'Flagged Challenge'})['flag_hash'] is None


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
                               data={'flag': 'CM1{nope}'},
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


def test_reviewer_can_test_a_flag_against_the_stored_hash(
        reviewer_client, db, flagged_crackme, monkeypatch):
    from review import routes

    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **kw: None)
    path = '/review/checkflag'

    match = reviewer_client.post(path, data={
        'uuid': flagged_crackme['hexid'], 'flag': FLAG,
        'csrf_token': 'test-csrf-token',
    })
    mismatch = reviewer_client.post(path, data={
        'uuid': flagged_crackme['hexid'], 'flag': 'CM1{wrong}',
        'csrf_token': 'test-csrf-token',
    })

    assert 'message=Match' in match.headers['Location']
    assert 'message=No+match' in mismatch.headers['Location']


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
    assert b'Check flag' in response.data
    assert b'Download source archive' in response.data
    assert b'Official difficulty' in response.data
    # The flag itself is only stored hashed, so nothing can print it here.
    assert FLAG.encode() not in response.data
    assert flagged_crackme['flag_hash'].encode() not in response.data


def test_review_page_says_so_when_a_crackme_is_not_auto_validated(
        reviewer_client, db, sample_crackme):
    response = reviewer_client.get(
        f"/review/viewcrackme?crackme_uuid={sample_crackme['hexid']}"
    )

    assert response.status_code == 200
    assert b'did not opt into auto-validation' in response.data
    assert b'Check flag' not in response.data
