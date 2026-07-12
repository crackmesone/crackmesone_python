"""Reviewer authentication, authorization, and CSRF helpers.

This module deliberately owns only reviewer-session security.  Main-site user
authentication remains separate.
"""

from functools import wraps
import hashlib
import os

from flask import abort, redirect, request, session, url_for


REVIEWER_SESSION_KEY = '_reviewer_user'
REVIEWER_ADMIN_KEY = '_reviewer_is_admin'
REVIEWER_CSRF_KEY = '_reviewer_csrf_token'

_users = {}


def configure(users):
    """Use the reviewer credential mapping loaded by the reviewer package."""
    global _users
    _users = users


def hash_string(input_string):
    """Return a SHA-256 hexadecimal password digest input."""
    return hashlib.sha256(input_string.encode('utf-8')).hexdigest()


def get_current_reviewer():
    """Return the authenticated reviewer, or ``None`` for a stale session."""
    username = session.get(REVIEWER_SESSION_KEY)
    if not username or username not in _users:
        return None
    return {
        'username': username,
        'is_admin': _users[username].get('is_admin', False),
    }


def clear_reviewer_session():
    """Remove reviewer authentication without touching main-site auth."""
    session.pop(REVIEWER_SESSION_KEY, None)
    session.pop(REVIEWER_ADMIN_KEY, None)


def token_required(view):
    """Require a current reviewer account."""
    @wraps(view)
    def decorated(*args, **kwargs):
        current_user = get_current_reviewer()
        if not current_user:
            clear_reviewer_session()
            return redirect(url_for('reviewer.login'))
        return view(current_user, *args, **kwargs)
    return decorated


def admin_required(view):
    """Require a current reviewer account with administrator privileges."""
    @wraps(view)
    def decorated(*args, **kwargs):
        current_user = get_current_reviewer()
        if not current_user:
            clear_reviewer_session()
            return redirect(url_for('reviewer.login'))
        if not current_user['is_admin']:
            abort(403)
        return view(current_user, *args, **kwargs)
    return decorated


def generate_csrf_token():
    """Generate or retrieve the reviewer-specific CSRF token."""
    if REVIEWER_CSRF_KEY not in session:
        session[REVIEWER_CSRF_KEY] = hashlib.sha256(os.urandom(32)).hexdigest()
    return session[REVIEWER_CSRF_KEY]


def validate_csrf_token():
    """Reject a missing or mismatched reviewer CSRF token."""
    token = request.form.get('csrf_token')
    expected = session.get(REVIEWER_CSRF_KEY)
    if not token or not expected or token != expected:
        abort(403, description='CSRF token validation failed')
