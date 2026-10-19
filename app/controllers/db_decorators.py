"""
Decorators for the database.
"""

from functools import wraps
from app.models.errors import ErrUnavailable
from app.services.database import check_connection

def check_db_con(f):
    """Decorator to check whether the database is available"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not check_connection():
            raise ErrUnavailable("Database is unavailable")

        return f(*args, **kwargs)

    return wrapper