"""
Session service for Flask session management.
"""

from flask import session as flask_session


SESSION_VERSION_KEY = 'session_version'


def init_session(app, config):
    """Initialize session configuration."""
    app.config['SESSION_COOKIE_NAME'] = config.get('CookieName', 'crackmesone')
    app.config['SECRET_KEY'] = config.get('SecretKey', 'change-me-in-production')

    @app.before_request
    def validate_session_version():
        """Drop auth cookies that predate a password change/reset."""
        username = flask_session.get('name')
        if not username:
            return

        from app.models.errors import ErrNoResult, ErrUnavailable
        from app.models.user import user_by_name

        try:
            user = user_by_name(username)
        except ErrNoResult:
            clear_session()
            return
        except ErrUnavailable:
            # don't log people out because Mongo hiccuped
            return

        expected = user.get('session_version', 0)
        if flask_session.get(SESSION_VERSION_KEY, 0) != expected:
            clear_session()


def get_session():
    """Get the current session."""
    return flask_session


def clear_session():
    """Clear main site auth session keys only."""
    flask_session.pop('name', None)
    flask_session.pop('email', None)
    flask_session.pop(SESSION_VERSION_KEY, None)
    flask_session.pop('login_attempt', None)


def get_username():
    """Get the current logged-in username."""
    return flask_session.get('name')


def is_authenticated():
    """Check if user is authenticated."""
    return flask_session.get('name') is not None
