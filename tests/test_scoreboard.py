"""Scoreboard ranking, navigation, and pagination."""

from datetime import datetime, timedelta, timezone

from bson import ObjectId


def _user(db, name, *, visible=True, deleted=False):
    object_id = ObjectId()
    user = {
        '_id': object_id,
        'hexid': str(object_id),
        'name': name,
        'visible': visible,
        'deleted': deleted,
    }
    db.user.insert_one(user)
    return user


def _solve(db, user, points, index=0, created_at=None):
    object_id = ObjectId()
    db.solve.insert_one({
        '_id': object_id,
        'hexid': str(object_id),
        'user_hexid': user.get('hexid') or str(user['_id']),
        'crackme_hexid': f'crackme-{index}',
        'points': points,
        'created_at': created_at or datetime.now(timezone.utc),
    })


def test_scoreboard_orders_scores_and_excludes_zero_or_hidden_users(
        client, db):
    alice = _user(db, 'alice')
    bob = _user(db, 'bob')
    zero = _user(db, 'zero')
    hidden = _user(db, 'hidden', visible=False)
    deleted = _user(db, 'deleted', deleted=True)
    _solve(db, alice, 200)
    _solve(db, alice, 300, 1)
    _solve(db, bob, 400)
    _solve(db, zero, 0)
    _solve(db, hidden, 900)
    _solve(db, deleted, 800)

    html = client.get('/scoreboard').get_data(as_text=True)

    assert html.index('>alice</a>') < html.index('>bob</a>')
    assert '<td class="text-right">500</td>' in html
    assert '<td class="text-right">400</td>' in html
    assert '>zero</a>' not in html
    assert '>hidden</a>' not in html
    assert '>deleted</a>' not in html


def test_scoreboard_ties_rank_by_time_of_reaching_score(client, db):
    zed = _user(db, 'zed')
    amy = _user(db, 'Amy')
    lower = _user(db, 'lower')
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _solve(db, zed, 200, created_at=start)
    _solve(db, amy, 500, created_at=start + timedelta(minutes=1))
    _solve(db, zed, 300, 1, created_at=start + timedelta(minutes=2))
    _solve(db, lower, 400, created_at=start + timedelta(minutes=3))

    html = client.get('/scoreboard').get_data(as_text=True)

    assert html.index('>Amy</a>') < html.index('>zed</a>')
    assert '<td>1</td>' in html
    assert '<td>2</td>' in html
    assert '<td>3</td>' in html


def test_scoreboard_ties_with_legacy_solve_without_timestamp(client, db):
    legacy = _user(db, 'legacy')
    newer = _user(db, 'newer')
    legacy_id = ObjectId.from_datetime(datetime(2025, 1, 1, tzinfo=timezone.utc))
    db.solve.insert_one({
        '_id': legacy_id,
        'user_hexid': legacy['hexid'],
        'points': 100,
    })
    _solve(db, newer, 100, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))

    html = client.get('/scoreboard').get_data(as_text=True)
    assert html.index('>legacy</a>') < html.index('>newer</a>')


def test_scoreboard_uses_latest_legacy_solve_among_mixed_formats(client, db):
    mixed = _user(db, 'mixed')
    other = _user(db, 'other')
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _solve(db, mixed, 50, created_at=start)
    _solve(db, other, 100, created_at=start + timedelta(days=1))
    db.solve.insert_one({
        '_id': ObjectId.from_datetime(start + timedelta(days=2)),
        'user_hexid': mixed['hexid'],
        'points': 50,
    })

    html = client.get('/scoreboard').get_data(as_text=True)
    assert html.index('>other</a>') < html.index('>mixed</a>')


def test_zero_point_solve_does_not_change_time_score_was_reached(client, db):
    first = _user(db, 'first')
    second = _user(db, 'second')
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _solve(db, first, 500, created_at=start)
    _solve(db, second, 500, created_at=start + timedelta(days=1))
    _solve(db, first, 0, 1, created_at=start + timedelta(days=2))

    html = client.get('/scoreboard').get_data(as_text=True)
    assert html.index('>first</a>') < html.index('>second</a>')


def test_scoreboard_paginates_with_global_rank(client, db):
    for index in range(26):
        user = _user(db, f'player-{index:02d}')
        _solve(db, user, 1000 - index, index)

    first_page = client.get('/scoreboard').get_data(as_text=True)
    assert '>player-00</a>' in first_page
    assert '>player-24</a>' in first_page
    assert '>player-25</a>' not in first_page
    assert 'href="/scoreboard/2"' in first_page

    second_page = client.get('/scoreboard/2').get_data(as_text=True)
    assert '>player-00</a>' not in second_page
    assert '>player-25</a>' in second_page
    assert '<td>26</td>' in second_page
    assert 'href="/scoreboard"' in second_page
    assert client.get('/scoreboard/0').location == '/scoreboard'
    assert client.get('/scoreboard/99').location == '/scoreboard/2'


def test_scoreboard_is_linked_from_navigation_but_not_embedded_on_homepage(client):
    home = client.get('/').get_data(as_text=True)
    assert 'href="/scoreboard" class="btn btn-link">Scoreboard</a>' in home
    assert '<h2>Scoreboard</h2>' not in home
    assert client.get('/scoreboard').status_code == 200
