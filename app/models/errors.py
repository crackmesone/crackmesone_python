"""
Custom exceptions for database operations.
"""


class ErrNoResult(Exception):
    """Raised when no result is found in the database."""
    pass


class ErrUnavailable(Exception):
    """Raised when database is unavailable."""
    pass


class ErrUnauthorized(Exception):
    """Raised when user doesn't have permission."""
    pass


class ErrCode(Exception):
    """Raised for internal code errors."""
    pass


def standardize_error(error):
    """Convert database errors to standard errors."""
    if error is None:
        return None
    error_str = str(error).lower()
    if 'no documents' in error_str or 'not found' in error_str:
        return ErrNoResult("Result not found.")
    return error
