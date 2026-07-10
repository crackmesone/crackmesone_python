"""
Password hashing service using bcrypt.
"""

import bcrypt


def hash_string(password: str) -> str:
    """Hash a password string and return the hash."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def hash_bytes(password: bytes) -> bytes:
    """Hash password bytes and return the hash bytes."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password, salt)


def match_string(hashed: str, password: str) -> bool:
    """Check if the password matches the hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (AttributeError, ValueError, TypeError):
        return False


def match_bytes(hashed: bytes, password: bytes) -> bool:
    """Check if the password bytes match the hash bytes."""
    try:
        return bcrypt.checkpw(password, hashed)
    except (ValueError, TypeError):
        return False
