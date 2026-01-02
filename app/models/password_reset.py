"""
Password reset token model for database operations.
"""

import secrets
from datetime import datetime, timedelta
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable

# Token expiration time in hours
TOKEN_EXPIRY_HOURS = 1


def create_reset_token(email: str) -> str:
    """Create a password reset token for a user.

    Args:
        email: User's email address

    Returns:
        The generated token string

    Raises:
        ErrUnavailable: If database unavailable
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('password_reset_tokens')

    # Delete any existing tokens for this email
    collection.delete_many({'email': email.lower()})

    # Generate a secure random token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)

    token_doc = {
        'email': email.lower(),
        'token': token,
        'created_at': datetime.utcnow(),
        'expires_at': expires_at
    }

    collection.insert_one(token_doc)
    return token


def get_reset_token(token: str) -> dict:
    """Get a password reset token document.

    Args:
        token: The reset token string

    Returns:
        Token document dict

    Raises:
        ErrNoResult: If token not found or expired
        ErrUnavailable: If database unavailable
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('password_reset_tokens')

    # Find token and check it hasn't expired
    result = collection.find_one({
        'token': token,
        'expires_at': {'$gt': datetime.utcnow()}
    })

    if result is None:
        raise ErrNoResult("Token not found or expired")

    return result


def delete_reset_token(token: str):
    """Delete a password reset token.

    Args:
        token: The reset token string

    Raises:
        ErrUnavailable: If database unavailable
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('password_reset_tokens')
    collection.delete_one({'token': token})


def cleanup_expired_tokens():
    """Remove all expired tokens from the database.

    Raises:
        ErrUnavailable: If database unavailable
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('password_reset_tokens')
    collection.delete_many({'expires_at': {'$lt': datetime.utcnow()}})
