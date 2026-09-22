"""Latest activity overview and paginated category listings."""

from datetime import datetime, timedelta, timezone

from bson import ObjectId


def _crackme(index, created_at):
    object_id = ObjectId()
    return {
        '_id': object_id,
        'hexid': str(object_id),
        'name': f'Crackme {index:02d}',
        'author': 'alice',
        'lang': 'C/C++',
        'arch': 'x86-64',
        'difficulty': 3.0,
        'quality': 4.0,
        'platform': 'Linux',
        'visible': True,
        'created_at': created_at,
    }


def test_latest_overview_shows_first_twenty_of_each_category(client, db, alice, bob):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    crackmes = [_crackme(index, start + timedelta(minutes=index)) for index in range(21)]
    db.crackme.insert_many(crackmes)

    solutions = []
    solves = []
    for index, crackme in enumerate(crackmes):
        solution_id = ObjectId()
        solve_id = ObjectId()
        solutions.append({
            '_id': solution_id,
            'hexid': str(solution_id),
            'crackmeid': crackme['_id'],
            'crackmehexid': crackme['hexid'],
            'crackmename': crackme['name'],
            'author': 'bob',
            'info': f'Writeup {index:02d}',
            'visible': True,
            'created_at': start + timedelta(minutes=index),
        })
        solves.append({
            '_id': solve_id,
            'hexid': str(solve_id),
            'user_hexid': str(bob['_id']),
            'crackme_hexid': crackme['hexid'],
            'difficulty': 3.0,
            'points': 300,
            'created_at': start + timedelta(minutes=index),
        })
    db.solution.insert_many(solutions)
    db.solve.insert_many(solves)

    html = client.get('/latest').get_data(as_text=True)

    assert 'Crackme 20' in html
    assert 'Writeup 20' in html
    assert 'Crackme 00' not in html
    assert 'Writeup 00' not in html
    assert html.count('>bob</a>') == 40
    assert 'href="/lasts/1" class="btn active">Show more crackmes' in html
    assert ('href="/latest/solutions/1" class="btn active">Show more solutions'
            in html)
    assert 'href="/latest/solves/1" class="btn active">Show more solves' in html
    assert html.count('<div class="pagination-controls">') == 3
    assert html.count('class="btn active">Show more') == 3
    assert html.count('href="/rss"') == 3
    assert html.count('src="/static/img/rss.svg"') == 3


def test_latest_category_pages_and_navigation_load(client):
    for path in ('/latest/solutions/1', '/latest/solves/1', '/lasts/1'):
        response = client.get(path)
        assert response.status_code == 200
        assert 'href="/rss"' in response.get_data(as_text=True)

    menu = client.get('/latest').get_data(as_text=True)
    assert 'href="/latest" class="btn btn-link">Latest</a>' in menu
    assert '>Latest Crackmes</a>' not in menu


def test_latest_category_redirects(client):
    assert client.get('/latest/solutions').location == '/latest/solutions/1'
    assert client.get('/latest/solves').location == '/latest/solves/1'
