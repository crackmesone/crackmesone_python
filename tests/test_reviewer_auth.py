"""Unit coverage for the isolated reviewer authentication domain."""

from review import auth


def test_reviewer_authentication_and_stale_sessions(app):
    accounts = {'reviewer': {'is_admin': False}, 'admin': {'is_admin': True}}
    auth.configure(accounts)

    with app.test_request_context('/'):
        assert auth.get_current_reviewer() is None
        auth.session[auth.REVIEWER_SESSION_KEY] = 'removed-user'
        assert auth.get_current_reviewer() is None
        auth.session[auth.REVIEWER_SESSION_KEY] = 'admin'
        assert auth.get_current_reviewer() == {
            'username': 'admin', 'is_admin': True
        }


def test_reviewer_csrf_token_is_stable_and_validated(app):
    with app.test_request_context(
        '/', method='POST', data={'csrf_token': 'known-token'}
    ):
        auth.session[auth.REVIEWER_CSRF_KEY] = 'known-token'
        assert auth.generate_csrf_token() == 'known-token'
        assert auth.validate_csrf_token() is None


def test_reviewer_csrf_token_is_generated(app):
    with app.test_request_context('/'):
        token = auth.generate_csrf_token()
        assert len(token) == 64
        assert auth.generate_csrf_token() == token


def test_clear_reviewer_session_preserves_main_site_session(app):
    with app.test_request_context('/'):
        auth.session.update({
            auth.REVIEWER_SESSION_KEY: 'reviewer',
            auth.REVIEWER_ADMIN_KEY: False,
            'name': 'alice',
        })
        auth.clear_reviewer_session()
        assert auth.REVIEWER_SESSION_KEY not in auth.session
        assert auth.REVIEWER_ADMIN_KEY not in auth.session
        assert auth.session['name'] == 'alice'
