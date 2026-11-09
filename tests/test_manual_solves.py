"""Tests for Issue #182: Manual 'Mark as Done' solve tracking.

Covers:
  - Model: toggle adds/removes from manual_solves, respects cap
  - Model: invalid hexids and non-existent crackmes are rejected
  - Model: official solves are never touched
  - Model: user_all_solved_hexids returns correct union
  - API:   unauthenticated requests are rejected (302 redirect)
  - API:   toggling an officially solved crackme is blocked (403)
  - API:   invalid/non-existent hexid returns 400
  - API:   valid toggle returns {ok, solved} JSON
  - Search: hide_solved excludes both official and manual at query level
  - Search: hide_solved=0 (or absent) shows all crackmes
  - Integration: flag solve does not appear in manual_solves
"""

import pytest
from bson import ObjectId
from datetime import datetime, timezone


# ─────────────────────────────────────────── helpers ──────────────────────────

def _hexid(user):
    return user.get('hexid') or str(user['_id'])


@pytest.fixture
def bob_hexid(bob):
    return _hexid(bob)


@pytest.fixture
def alice_crackme(db, alice):
    """A second visible crackme authored by alice, no flag."""
    oid = ObjectId()
    crackme = {
        '_id': oid,
        'hexid': str(oid),
        'name': 'Alice Hidden Gem',
        'author': alice['name'],
        'info': 'Another test crackme',
        'lang': 'Rust',
        'arch': 'x86-64',
        'platform': 'Linux',
        'difficulty': 2.0,
        'quality': 3.5,
        'visible': True,
        'deleted': False,
        'nbsolutions': 0,
        'nbcomments': 0,
        'nbdownloads': 0,
        'size': 50,
        'created_at': datetime.now(timezone.utc),
    }
    db.crackme.insert_one(crackme)
    return crackme


# ─────────────────────────────────────── model: toggle ────────────────────────

class TestUserToggleManualSolve:

    def test_toggle_on_adds_hexid_to_manual_solves(self, db, bob, sample_crackme):
        from app.models.user import user_toggle_manual_solve
        result = user_toggle_manual_solve(bob['name'], sample_crackme['hexid'])
        assert result is True
        user = db.user.find_one({'name': bob['name']})
        assert sample_crackme['hexid'] in user['manual_solves']

    def test_toggle_off_removes_hexid_from_manual_solves(self, db, bob, sample_crackme):
        from app.models.user import user_toggle_manual_solve
        user_toggle_manual_solve(bob['name'], sample_crackme['hexid'])
        result = user_toggle_manual_solve(bob['name'], sample_crackme['hexid'])
        assert result is False
        user = db.user.find_one({'name': bob['name']})
        assert sample_crackme['hexid'] not in (user.get('manual_solves') or [])

    def test_toggle_is_idempotent_via_addtoset(self, db, bob, sample_crackme):
        from app.models.user import user_toggle_manual_solve
        user_toggle_manual_solve(bob['name'], sample_crackme['hexid'])
        # Directly insert duplicate to simulate a race condition
        db.user.update_one(
            {'name': bob['name']},
            {'$push': {'manual_solves': sample_crackme['hexid']}}
        )
        # Toggle off: should remove all occurrences via $pull
        result = user_toggle_manual_solve(bob['name'], sample_crackme['hexid'])
        assert result is False
        user = db.user.find_one({'name': bob['name']})
        assert sample_crackme['hexid'] not in (user.get('manual_solves') or [])

    def test_toggle_does_not_touch_score_or_points(self, db, bob, sample_crackme):
        from app.models.user import user_toggle_manual_solve
        from app.models.solve import user_score
        score_before = user_score(_hexid(bob))
        user_toggle_manual_solve(bob['name'], sample_crackme['hexid'])
        assert user_score(_hexid(bob)) == score_before

    def test_toggle_does_not_add_to_solve_collection(self, db, bob, sample_crackme):
        from app.models.user import user_toggle_manual_solve
        user_toggle_manual_solve(bob['name'], sample_crackme['hexid'])
        assert db.solve.count_documents({'user_hexid': _hexid(bob)}) == 0

    def test_invalid_hexid_raises_value_error(self, db, bob):
        from app.models.user import user_toggle_manual_solve
        with pytest.raises(ValueError, match='24-character'):
            user_toggle_manual_solve(bob['name'], 'not-a-hexid')

    def test_short_hexid_raises_value_error(self, db, bob):
        from app.models.user import user_toggle_manual_solve
        with pytest.raises(ValueError):
            user_toggle_manual_solve(bob['name'], 'abc123')

    def test_nonexistent_crackme_raises_value_error(self, db, bob):
        from app.models.user import user_toggle_manual_solve
        fake_hexid = 'a' * 24
        with pytest.raises(ValueError, match='not found or not visible'):
            user_toggle_manual_solve(bob['name'], fake_hexid)

    def test_invisible_crackme_raises_value_error(self, db, bob, sample_crackme):
        from app.models.user import user_toggle_manual_solve
        db.crackme.update_one({'_id': sample_crackme['_id']}, {'$set': {'visible': False}})
        with pytest.raises(ValueError, match='not found or not visible'):
            user_toggle_manual_solve(bob['name'], sample_crackme['hexid'])

    def test_cap_of_5000_is_enforced(self, db, bob, sample_crackme):
        from app.models.user import user_toggle_manual_solve, _MANUAL_SOLVE_HARD_CAP
        # Inject exactly cap fake hexids directly into the user document
        fake_ids = [str(ObjectId()) for _ in range(_MANUAL_SOLVE_HARD_CAP)]
        db.user.update_one({'name': bob['name']}, {'$set': {'manual_solves': fake_ids}})
        with pytest.raises(ValueError, match='limit'):
            user_toggle_manual_solve(bob['name'], sample_crackme['hexid'])


# ─────────────────────────────────── model: all_solved_hexids ─────────────────

class TestUserAllSolvedHexids:

    def test_empty_for_fresh_user(self, db, bob):
        from app.models.user import user_all_solved_hexids
        result = user_all_solved_hexids(bob['name'])
        assert result['official'] == frozenset()
        assert result['manual']   == frozenset()
        assert result['all']      == frozenset()

    def test_manual_solve_appears_in_manual_and_all(self, db, bob, sample_crackme):
        from app.models.user import user_toggle_manual_solve, user_all_solved_hexids
        user_toggle_manual_solve(bob['name'], sample_crackme['hexid'])
        result = user_all_solved_hexids(bob['name'])
        assert sample_crackme['hexid'] in result['manual']
        assert sample_crackme['hexid'] in result['all']
        assert sample_crackme['hexid'] not in result['official']

    def test_official_solve_appears_in_official_and_all(self, db, bob, bob_hexid, sample_crackme):
        from app.models.user import user_all_solved_hexids
        db.solve.insert_one({
            'user_hexid': bob_hexid,
            'crackme_hexid': sample_crackme['hexid'],
            'points': 300, 'difficulty': 3.0,
            'created_at': datetime.now(timezone.utc),
        })
        result = user_all_solved_hexids(bob['name'])
        assert sample_crackme['hexid'] in result['official']
        assert sample_crackme['hexid'] in result['all']
        assert sample_crackme['hexid'] not in result['manual']

    def test_union_covers_both_sources(self, db, bob, bob_hexid, sample_crackme, alice_crackme):
        from app.models.user import user_toggle_manual_solve, user_all_solved_hexids
        user_toggle_manual_solve(bob['name'], alice_crackme['hexid'])
        db.solve.insert_one({
            'user_hexid': bob_hexid,
            'crackme_hexid': sample_crackme['hexid'],
            'points': 300, 'difficulty': 3.0,
            'created_at': datetime.now(timezone.utc),
        })
        result = user_all_solved_hexids(bob['name'])
        assert result['all'] == frozenset({
            sample_crackme['hexid'], alice_crackme['hexid']
        })

    def test_nonexistent_user_returns_empty_sets(self, db):
        from app.models.user import user_all_solved_hexids
        result = user_all_solved_hexids('nobody_at_all')
        assert result['all'] == frozenset()


# ─────────────────────────────────────────── API ──────────────────────────────

class TestToggleManualSolveEndpoint:

    def test_anonymous_request_redirects_to_root(self, client, db, sample_crackme):
        response = client.post(
            f"/crackme/{sample_crackme['hexid']}/toggle-manual-solve"
        )
        assert response.status_code == 302
        assert response.headers['Location'] == '/'

    def test_valid_toggle_on_returns_ok_and_solved_true(
            self, bob_client, db, sample_crackme):
        response = bob_client.post(
            f"/crackme/{sample_crackme['hexid']}/toggle-manual-solve"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['ok']     is True
        assert data['solved'] is True

    def test_valid_toggle_off_returns_ok_and_solved_false(
            self, bob_client, db, bob, sample_crackme):
        db.user.update_one(
            {'name': bob['name']},
            {'$set': {'manual_solves': [sample_crackme['hexid']]}}
        )
        response = bob_client.post(
            f"/crackme/{sample_crackme['hexid']}/toggle-manual-solve"
        )
        data = response.get_json()
        assert data['ok']     is True
        assert data['solved'] is False

    def test_invalid_hexid_returns_400(self, bob_client, db):
        response = bob_client.post('/crackme/not-a-hexid/toggle-manual-solve')
        assert response.status_code == 400
        assert response.get_json()['ok'] is False

    def test_nonexistent_crackme_returns_400(self, bob_client, db):
        fake_hexid = 'b' * 24
        response = bob_client.post(f'/crackme/{fake_hexid}/toggle-manual-solve')
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False

    def test_officially_solved_crackme_cannot_be_toggled_off(
            self, bob_client, db, bob, bob_hexid, sample_crackme):
        """Official flag solves are locked — the endpoint must enforce this."""
        db.solve.insert_one({
            'user_hexid': bob_hexid,
            'crackme_hexid': sample_crackme['hexid'],
            'points': 300, 'difficulty': 3.0,
            'created_at': datetime.now(timezone.utc),
        })
        response = bob_client.post(
            f"/crackme/{sample_crackme['hexid']}/toggle-manual-solve"
        )
        assert response.status_code == 403
        data = response.get_json()
        assert data['ok']     is False
        assert data['locked'] is True

    def test_toggle_persists_to_database(
            self, bob_client, db, bob, sample_crackme):
        bob_client.post(
            f"/crackme/{sample_crackme['hexid']}/toggle-manual-solve"
        )
        user = db.user.find_one({'name': bob['name']})
        assert sample_crackme['hexid'] in user['manual_solves']


# ─────────────────────────────── search: hide_solved ──────────────────────────

class TestSearchHideSolved:

    def test_hide_solved_excludes_manually_solved_crackmes(
            self, bob_client, db, bob, sample_crackme, alice_crackme):
        """hide_solved=1 must remove manually-solved crackmes from results."""
        db.user.update_one(
            {'name': bob['name']},
            {'$set': {'manual_solves': [sample_crackme['hexid']]}}
        )
        response = bob_client.get(
            '/search?hide_solved=1&difficulty-min=1&difficulty-max=6'
            '&quality-min=1&quality-max=6'
        )
        assert response.status_code == 200
        assert sample_crackme['name'].encode() not in response.data
        assert alice_crackme['name'].encode() in response.data

    def test_hide_solved_excludes_officially_solved_crackmes(
            self, bob_client, db, bob, bob_hexid, sample_crackme, alice_crackme):
        """hide_solved=1 must also remove flag-solved crackmes."""
        db.solve.insert_one({
            'user_hexid': bob_hexid,
            'crackme_hexid': sample_crackme['hexid'],
            'points': 300, 'difficulty': 3.0,
            'created_at': datetime.now(timezone.utc),
        })
        response = bob_client.get(
            '/search?hide_solved=1&difficulty-min=1&difficulty-max=6'
            '&quality-min=1&quality-max=6'
        )
        assert sample_crackme['name'].encode() not in response.data
        assert alice_crackme['name'].encode() in response.data

    def test_without_hide_solved_all_crackmes_appear(
            self, bob_client, db, bob, sample_crackme, alice_crackme):
        """Without hide_solved, solved crackmes still appear (just greyed out)."""
        db.user.update_one(
            {'name': bob['name']},
            {'$set': {'manual_solves': [sample_crackme['hexid']]}}
        )
        response = bob_client.get(
            '/search?difficulty-min=1&difficulty-max=6&quality-min=1&quality-max=6'
        )
        assert sample_crackme['name'].encode() in response.data
        assert alice_crackme['name'].encode() in response.data

    def test_hide_solved_does_nothing_for_guests(
            self, client, db, sample_crackme):
        """Unauthenticated users: hide_solved param is silently ignored."""
        response = client.get(
            '/search?hide_solved=1&difficulty-min=1&difficulty-max=6'
            '&quality-min=1&quality-max=6'
        )
        assert response.status_code == 200
        assert sample_crackme['name'].encode() in response.data

    def test_search_page_shows_done_column_only_when_logged_in(
            self, bob_client, client, db, sample_crackme):
        auth_response  = bob_client.get('/search?difficulty-min=1&difficulty-max=6&quality-min=1&quality-max=6')
        guest_response = client.get('/search?difficulty-min=1&difficulty-max=6&quality-min=1&quality-max=6')
        assert b'btn-mark-solved' in auth_response.data
        assert b'btn-mark-solved' not in guest_response.data

    def test_solved_row_has_crackme_row_solved_class(
            self, bob_client, db, bob, sample_crackme):
        db.user.update_one(
            {'name': bob['name']},
            {'$set': {'manual_solves': [sample_crackme['hexid']]}}
        )
        response = bob_client.get(
            '/search?difficulty-min=1&difficulty-max=6&quality-min=1&quality-max=6'
        )
        assert b'crackme-row-solved' in response.data

    def test_officially_solved_row_shows_locked_indicator(
            self, bob_client, db, bob, bob_hexid, sample_crackme):
        db.solve.insert_one({
            'user_hexid': bob_hexid,
            'crackme_hexid': sample_crackme['hexid'],
            'points': 300, 'difficulty': 3.0,
            'created_at': datetime.now(timezone.utc),
        })
        response = bob_client.get(
            '/search?difficulty-min=1&difficulty-max=6&quality-min=1&quality-max=6'
        )
        assert b'mark-solved-locked' in response.data
        assert b'btn-mark-solved' not in response.data  # no toggle for official

    def test_lasts_page_shows_done_column_and_solved_class(
            self, bob_client, db, bob, sample_crackme):
        db.user.update_one(
            {'name': bob['name']},
            {'$set': {'manual_solves': [sample_crackme['hexid']]}}
        )
        response = bob_client.get('/lasts/1')
        assert response.status_code == 200
        assert b'crackme-row-solved' in response.data
        assert b'btn-mark-solved' in response.data


    def test_random_route_shows_my_progress_and_done_column_when_logged_in(
            self, bob_client, client, db, sample_crackme):
        auth_response = bob_client.get('/random')
        assert auth_response.status_code == 200
        assert b'My Progress' in auth_response.data
        assert b'hide-solved-checkbox' in auth_response.data
        assert b'btn-mark-solved' in auth_response.data

        guest_response = client.get('/random')
        assert guest_response.status_code == 200
        assert b'My Progress' not in guest_response.data
        assert b'hide-solved-checkbox' not in guest_response.data
        assert b'btn-mark-solved' not in guest_response.data

    def test_random_route_hides_solved_crackmes_when_requested(
            self, bob_client, db, bob, sample_crackme, alice_crackme):
        db.user.update_one(
            {'name': bob['name']},
            {'$set': {'manual_solves': [sample_crackme['hexid']]}}
        )
        response = bob_client.get('/random?hide_solved=1')
        assert response.status_code == 200
        assert sample_crackme['name'].encode() not in response.data
        assert alice_crackme['name'].encode() in response.data

    def test_crackme_view_shows_mark_as_done_button_and_status(
            self, bob_client, db, sample_crackme):
        response = bob_client.get(f"/crackme/{sample_crackme['hexid']}")
        assert response.status_code == 200
        assert b'page-mark-solved-btn' in response.data
        assert b'Mark as done' in response.data
        assert b'Mark as done. Only visible to yourself' in response.data

    def test_crackme_view_shows_marked_done_when_solved(
            self, bob_client, db, bob, sample_crackme):
        db.user.update_one(
            {'name': bob['name']},
            {'$set': {'manual_solves': [sample_crackme['hexid']]}}
        )
        response = bob_client.get(f"/crackme/{sample_crackme['hexid']}")
        assert response.status_code == 200
        assert b'page-mark-solved-btn' in response.data
        assert b'Done' in response.data
        assert b'active' in response.data
        assert b'is-solved' in response.data
        assert b'Mark it as undone. Only visible to yourself' in response.data

    def test_crackme_view_shows_locked_when_officially_solved(
            self, bob_client, db, bob, bob_hexid, sample_crackme):
        db.solve.insert_one({
            'user_hexid': bob_hexid,
            'crackme_hexid': sample_crackme['hexid'],
            'points': 300, 'difficulty': 3.0,
            'created_at': datetime.now(timezone.utc),
        })
        response = bob_client.get(f"/crackme/{sample_crackme['hexid']}")
        assert response.status_code == 200
        assert b'mark-solved-locked' in response.data
        assert b'Solved' in response.data
        assert b'page-mark-solved-btn' not in response.data


# ??????????????????????????? official solve integration ???????????????????????

class TestOfficialFlagSolveAutoMarked:

    def test_submitting_official_flag_auto_marks_as_solved_across_site(
            self, bob_client, db, bob, sample_crackme, alice_crackme):
        flag = 'CMO{flag_auto_solved_123}'
        db.crackme.update_one(
            {'_id': sample_crackme['_id']},
            {'$set': {
                'flag': flag,
                'official_difficulty': 2.0,
            }}
        )
        hexid = sample_crackme['hexid']

        # 1. Before submitting flag: shows 'Mark as done'
        res_before = bob_client.get(f"/crackme/{hexid}")
        assert res_before.status_code == 200
        assert b'Mark as done' in res_before.data
        assert b'mark-solved-locked-badge' not in res_before.data

        # 2. Bob submits the correct flag
        submit_res = bob_client.post(
            f"/crackme/{hexid}/solve",
            data={'flag': flag},
            follow_redirects=True
        )
        assert submit_res.status_code == 200

        # 3. Viewing the crackme page now shows auto-marked 'Solved' locked badge
        res_after = bob_client.get(f"/crackme/{hexid}")
        assert res_after.status_code == 200
        assert b'mark-solved-locked-badge' in res_after.data
        assert b'Solved' in res_after.data
        assert b'page-mark-solved-btn' not in res_after.data

        # 4. Viewing /lasts/1 shows row solved with locked icon
        lasts_res = bob_client.get('/lasts/1')
        assert lasts_res.status_code == 200
        assert b'crackme-row-solved' in lasts_res.data
        assert b'mark-solved-locked' in lasts_res.data

        # 5. hide_solved=1 excludes it from search and random
        search_hidden = bob_client.get('/search?hide_solved=1')
        assert search_hidden.status_code == 200
        assert sample_crackme['name'].encode() not in search_hidden.data
        assert alice_crackme['name'].encode() in search_hidden.data

        random_hidden = bob_client.get('/random?hide_solved=1')
        assert random_hidden.status_code == 200
        assert sample_crackme['name'].encode() not in random_hidden.data
        assert alice_crackme['name'].encode() in random_hidden.data

        # 6. Attempting to manually toggle an official solve is rejected (403)
        toggle_res = bob_client.post(f"/crackme/{hexid}/toggle-manual-solve")
        assert toggle_res.status_code == 403

    def test_manual_solve_lifecycle_can_toggle_freely(
            self, bob_client, db, bob, alice_crackme):
        hexid = alice_crackme['hexid']

        # Initially unsolved
        res0 = bob_client.get(f"/crackme/{hexid}")
        assert b'Mark as done' in res0.data

        # Toggle ON
        res_on = bob_client.post(f"/crackme/{hexid}/toggle-manual-solve")
        assert res_on.status_code == 200
        assert res_on.get_json()['solved'] is True

        # Challenge view shows Done
        res1 = bob_client.get(f"/crackme/{hexid}")
        assert b'Done' in res1.data

        # Table shows row solved with checkbox toggle (not locked)
        lasts1 = bob_client.get('/lasts/1')
        assert b'crackme-row-solved' in lasts1.data
        assert b'btn-mark-solved' in lasts1.data

        # Hidden with hide_solved=1
        search1 = bob_client.get('/search?hide_solved=1')
        assert alice_crackme['name'].encode() not in search1.data

        # Toggle OFF
        res_off = bob_client.post(f"/crackme/{hexid}/toggle-manual-solve")
        assert res_off.status_code == 200
        assert res_off.get_json()['solved'] is False

        # Challenge view shows Mark as done again
        res2 = bob_client.get(f"/crackme/{hexid}")
        assert b'Mark as done' in res2.data

        # Shown in search with hide_solved=1
        search2 = bob_client.get('/search?hide_solved=1')
        assert alice_crackme['name'].encode() in search2.data
