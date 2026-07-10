"""Tests for RSS output and graceful error paths."""

from unittest.mock import patch


def test_rss_feed_escapes_user_content(client, db, sample_crackme):
    db.crackme.update_one({'_id': sample_crackme['_id']}, {'$set': {
        'name': 'A & B <challenge>',
        'info': '<script>alert(1)</script>',
    }})
    db.rating_difficulty.insert_one({
        'crackmehexid': sample_crackme['hexid'], 'rating': 5,
    })

    response = client.get('/rss/crackme')

    assert response.status_code == 200
    assert response.mimetype == 'application/rss+xml'
    assert b'A &amp; B &lt;challenge&gt;' in response.data
    assert b'Very Hard' in response.data
    assert b'&lt;script&gt;alert(1)&lt;/script&gt;' in response.data
    assert b'http://localhost/crackme/' in response.data


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
