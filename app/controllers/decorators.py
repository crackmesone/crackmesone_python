"""
Decorators for access control.
"""

from functools import wraps
from flask import redirect, url_for, session


def login_required(f):
    """Decorator to require user to be logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('name') is None:
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function


def anonymous_required(f):
    """Decorator to require user to NOT be logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('name') is not None:
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function
