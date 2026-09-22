"""Tests for RSS output and graceful error paths."""

from datetime import timedelta
from unittest.mock import patch
from xml.etree import ElementTree

from bson import ObjectId


def test_rss_feed_includes_crackmes_solutions_and_solves(
        client, db, sample_crackme, bob):
    db.crackme.update_one({'_id': sample_crackme['_id']}, {'$set': {
        'name': 'A & B <challenge>',
        'info': '<script>alert(1)</script>',
    }})
    db.rating_difficulty.insert_one({
        'crackmehexid': sample_crackme['hexid'], 'rating': 5,
    })
    solution_id = ObjectId()
    db.solution.insert_one({
        '_id': solution_id,
        'hexid': str(solution_id),
        'crackmehexid': sample_crackme['hexid'],
        'crackmename': 'A & B <challenge>',
        'author': 'bob',
        'info': 'A <careful> solution',
        'visible': True,
        'created_at': sample_crackme['created_at'] + timedelta(minutes=1),
    })
    solve_id = ObjectId()
    db.solve.insert_one({
        '_id': solve_id,
        'hexid': str(solve_id),
        'user_hexid': str(bob['_id']),
        'crackme_hexid': sample_crackme['hexid'],
        'difficulty': 5,
        'points': 500,
        'created_at': sample_crackme['created_at'] + timedelta(minutes=2),
    })

    response = client.get('/rss')

    assert response.status_code == 200
    assert response.mimetype == 'application/rss+xml'
    assert b'A &amp; B &lt;challenge&gt;' in response.data
    assert b'Very Hard' in response.data
    assert b'&lt;script&gt;alert(1)&lt;/script&gt;' in response.data
    assert b'A &lt;careful&gt; solution' in response.data
    assert b'New solve: bob solved A &amp; B &lt;challenge&gt;' in response.data
    assert b'<category>Crackme</category>' in response.data
    assert b'<category>Solution</category>' in response.data
    assert b'<category>Solve</category>' in response.data
    assert b'http://localhost/crackme/' in response.data
    assert b'http://localhost/solution/' in response.data
    assert len(ElementTree.fromstring(response.data).findall('./channel/item')) == 3


def test_old_crackme_rss_url_is_kept_as_an_alias(client):
    assert client.get('/rss/crackme').status_code == 200


def test_rss_database_failure_returns_500(client):
    with patch('app.controllers.rss.last_crackmes', side_effect=RuntimeError):
        response = client.get('/rss/crackme')

    assert response.status_code == 500
    assert response.data == b'Error generating RSS feed'


def test_index_degrades_to_zero_counts_on_database_error(client):
    with patch('app.controllers.index.count_users', side_effect=RuntimeError):
        response = client.get('/')

    assert response.status_code == 200


def test_static_and_well_known_missing_files_are_404(client):
    assert client.get('/static/does-not-exist.txt').status_code == 404
    assert client.get('/.well-known/does-not-exist.txt').status_code == 404
