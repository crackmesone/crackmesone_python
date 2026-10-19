"""
Decorators for access control.
"""

from functools import wraps
from flask import redirect, session
#from app.models.user import is_session_valid

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
        if session.get('name') is not None: #or is_session_valid(session.get('name'), session.get('sess_id')):
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function
