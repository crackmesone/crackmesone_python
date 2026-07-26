"""Route integration tests using Flask's test client (no browser required)."""

from app.services.passhash import match_string


def test_public_pages_load(client):
    for path in ('/', '/faq', '/upload/crackmerules', '/upload/writeuprules',
                 '/login', '/register', '/search', '/lasts/1'):
        assert client.get(path).status_code == 200, path


def test_unknown_route_is_404(client):
    assert client.get('/not-a-real-route').status_code == 404


def test_anonymous_user_is_redirected_from_protected_pages(client):
    for path in ('/upload/crackme', '/notifications', '/change-password'):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response.location == '/', path


def test_authenticated_user_can_open_protected_pages(alice_client):
    assert alice_client.get('/upload/crackme').status_code == 200
    assert alice_client.get('/notifications').status_code == 200
    assert alice_client.get('/change-password').status_code == 200


def test_login_with_valid_synthetic_user(client, alice):
    response = client.post('/login', data={
        'name': 'alice',
        'password': 'alice-password',
    })

    assert response.status_code == 302
    assert response.location == '/'
    with client.session_transaction() as session:
        assert session['name'] == 'alice'
        assert session['email'] == 'alice@example.test'


def test_login_with_wrong_password_does_not_authenticate(client, alice):
    response = client.post('/login', data={
        'name': 'alice',
        'password': 'wrong-password',
    })

    assert response.status_code == 200
    assert b'Password is incorrect' in response.data
    with client.session_transaction() as session:
        assert 'name' not in session
        assert session['login_attempt'] == 1


def test_registration_creates_a_user(client, db):
    response = client.post('/register', data={
        'name': 'charlie',
        'email': 'CHARLIE@example.test',
        'password': 'charlie-password',
    })

    assert response.status_code == 302
    assert response.location == '/login'
    user = db.user.find_one({'name': 'charlie'})
    assert user['email'] == 'charlie@example.test'
    assert match_string(user['password'], 'charlie-password') is True


def test_logout_clears_only_main_auth(alice_client):
    with alice_client.session_transaction() as session:
        session['unrelated'] = 'preserved'

    response = alice_client.get('/logout')
    assert response.status_code == 302
    assert response.location == '/'
    with alice_client.session_transaction() as session:
        assert 'name' not in session
        assert 'email' not in session
        assert session['unrelated'] == 'preserved'


def test_missing_crackme_is_404(client):
    from bson import ObjectId
    assert client.get(f'/crackme/{ObjectId()}').status_code == 404


def test_existing_user_profile_loads(client, alice):
    assert client.get('/user/alice').status_code == 200


def test_missing_user_profile_is_404(client):
    assert client.get('/user/missing').status_code == 404


def test_spoiler_comment_is_hidden_on_user_profile(client, db, alice):
    from bson import ObjectId
    from datetime import datetime, timezone

    secret = 'the flag is 1234'
    db.comment.insert_one({
        '_id': ObjectId(),
        'info': secret,
        'author': 'alice',
        'crackmehexid': 'deadbeef',
        'crackmename': 'Test Crackme',
        'created_at': datetime.now(timezone.utc),
        'visible': True,
        'deleted': False,
        'spoiler': True,
    })

    html = client.get('/user/alice').get_data(as_text=True)
    # The spoiler content is present but wrapped so it is hidden by default.
    assert '[Click to reveal]' in html
    assert 'spoiler-content-' in html
    assert 'revealSpoiler(' in html


def test_non_spoiler_comment_is_shown_on_user_profile(client, db, alice):
    from bson import ObjectId
    from datetime import datetime, timezone

    db.comment.insert_one({
        '_id': ObjectId(),
        'info': 'just a normal comment',
        'author': 'alice',
        'crackmehexid': 'deadbeef',
        'crackmename': 'Test Crackme',
        'created_at': datetime.now(timezone.utc),
        'visible': True,
        'deleted': False,
        'spoiler': False,
    })

    html = client.get('/user/alice').get_data(as_text=True)
    assert 'just a normal comment' in html
    assert '[Click to reveal]' not in html
