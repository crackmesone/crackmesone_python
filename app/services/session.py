"""
Session service for Flask session management.
"""

from flask import session as flask_session


def init_session(app, config):
    """Initialize session configuration."""
    app.config['SESSION_COOKIE_NAME'] = config.get('CookieName', 'crackmesone')
    app.config['SECRET_KEY'] = config.get('SecretKey', 'change-me-in-production')
    # Session options can be extended here


def get_session():
    """Get the current session."""
    return flask_session


def clear_session():
    """Clear all session values."""
    flask_session.clear()


def get_username():
    """Get the current logged-in username."""
    return flask_session.get('name')


def is_authenticated():
    """Check if user is authenticated."""
    return flask_session.get('name') is not None
