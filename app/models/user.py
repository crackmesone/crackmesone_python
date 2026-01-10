"""
User model for database operations.
"""

import re
from datetime import datetime
from bson import ObjectId
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable


def count_users():
    """Return the total number of users."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('user')
    return collection.count_documents({})


def user_by_name(name):
    """Get user by username (case-insensitive).

    Args:
        name: Username to search for

    Returns:
        User document dict

    Raises:
        ErrNoResult: If user not found
        ErrUnavailable: If database unavailable
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('user')
    # Case-insensitive regex search
    pattern = re.compile(f'^{re.escape(name)}$', re.IGNORECASE)
    result = collection.find_one({'name': pattern})

    if result is None:
        raise ErrNoResult("User not found")

    return result


def user_by_mail(email):
    """Get user by email (case-insensitive).

    Args:
        email: Email to search for

    Returns:
        User document dict

    Raises:
        ErrNoResult: If user not found
        ErrUnavailable: If database unavailable
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('user')
    pattern = re.compile(f'^{re.escape(email)}$', re.IGNORECASE)
    result = collection.find_one({'email': pattern})

    if result is None:
        raise ErrNoResult("User not found")

    return result


def user_by_hexid(hexid):
    """Get user by hex ID.

    Args:
        hexid: The hex ID of the user

    Returns:
        User document dict

    Raises:
        ErrNoResult: If user not found
        ErrUnavailable: If database unavailable
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('user')
    result = collection.find_one({'hexid': hexid})

    if result is None:
        raise ErrNoResult("User not found")

    return result


def all_users_visible():
    """Get all visible users.

    Returns:
        List of user documents
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('user')
    return list(collection.find({'visible': True}))


def user_create(name, email, password):
    """Create a new user.

    Args:
        name: Username
        email: User email
        password: Hashed password

    Raises:
        ErrUnavailable: If database unavailable
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('user')
    obj_id = ObjectId()

    user = {
        '_id': obj_id,
        'hexid': str(obj_id),
        'name': name,
        'email': email,
        'password': password,
        'visible': True,
        'deleted': False
    }

    collection.insert_one(user)


def update_user_password(username, hashed_password):
    """Update user password.

    Args:
        username: The username
        hashed_password: The new hashed password

    Raises:
        ValueError: If username or password is empty
        ErrNoResult: If no user found
    """
    if not username:
        raise ValueError("username cannot be empty")
    if not hashed_password:
        raise ValueError("hashed password cannot be empty")

    collection = get_collection('user')

    result = collection.update_one(
        {'name': username},
        {'$set': {'password': hashed_password}}
    )

    if result.matched_count == 0:
        raise ErrNoResult("No user found with the provided username")


def user_get_unread_notifications(username):
    """Get the count of unread notifications for a user.

    Args:
        username: The username (exact match)

    Returns:
        Number of unread notifications (0 if user not found or field missing)
    """
    if not check_connection():
        return 0

    try:
        collection = get_collection('user')
        user = collection.find_one({'name': username}, {'unread_notifications': 1})
        if user:
            return user.get('unread_notifications', 0)
        return 0
    except Exception:
        return 0


def user_increment_unread_notifications(username):
    """Increment the unread notification count for a user.

    Args:
        username: The username (exact match)
    """
    if not check_connection():
        return

    collection = get_collection('user')
    collection.update_one(
        {'name': username},
        {'$inc': {'unread_notifications': 1}}
    )


def user_decrement_unread_notifications(username, count=1):
    """Decrement the unread notification count for a user.

    Args:
        username: The username (exact match)
        count: Number to decrement by (default 1)
    """
    if not check_connection():
        return

    collection = get_collection('user')

    # First get current count to avoid going negative
    user = collection.find_one({'name': username}, {'unread_notifications': 1})
    if user:
        current = user.get('unread_notifications', 0)
        new_count = max(0, current - count)
        collection.update_one(
            {'name': username},
            {'$set': {'unread_notifications': new_count}}
        )
