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


# Collections (and the field on each) that store a username as a reference to a
# user. The username is denormalized onto all of these, so renaming a user must
# cascade to every one of them or the user would silently lose ownership of their
# crackmes, comments, solutions, ratings, notifications, and pending requests.
#
# Reviewer identities (e.g. ``label_request.reviewed_by`` and
# ``account_deletion_request.reviewed_by``) are deliberately NOT included:
# reviewers authenticate through review/users.json, a namespace separate from the
# user collection, so their names are never main-site usernames.
USERNAME_REFERENCES = (
    ('crackme', 'author'),
    ('comment', 'author'),
    ('solution', 'author'),
    ('rating_difficulty', 'author'),
    ('rating_quality', 'author'),
    ('notifications', 'user'),
    ('label_request', 'requester'),
    ('account_deletion_request', 'requester'),
)


def user_rename(old_name, new_name):
    """Rename a user and update every stored reference to their old username.

    Because the username is denormalized across many collections (see
    :data:`USERNAME_REFERENCES`), a rename must touch all of them so nothing
    orphans — including content still awaiting review (a pending crackme or
    writeup keeps working because the reviewer queue reads ``author`` from the
    database at review time).

    Callers must validate that ``new_name`` is available first (see the
    availability checks in the account-settings controller). ``old_name`` must
    be the user's exact stored name.

    Returns:
        The number of user documents renamed (1 on success).

    Raises:
        ErrNoResult: If no user matches ``old_name``.
        ErrUnavailable: If the database is unavailable.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    if old_name == new_name:
        return 0

    user_collection = get_collection('user')
    if user_collection.find_one({'name': old_name}, {'_id': 1}) is None:
        raise ErrNoResult("No user found with the provided username")

    # MongoDB has no cheap way to do this atomically without a replica-set
    # transaction, so ordering is the safety net: cascade the references FIRST
    # and flip the user document LAST. If a reference update fails partway, the
    # user document still carries the old name, so the caller's session keeps
    # resolving (no lockout) and re-running the rename converges. Renaming the
    # user document first would risk exactly that lockout.
    for collection_name, field in USERNAME_REFERENCES:
        get_collection(collection_name).update_many(
            {field: old_name},
            {'$set': {field: new_name}}
        )

    result = user_collection.update_one(
        {'name': old_name},
        {'$set': {'name': new_name}}
    )

    return result.modified_count


def user_change_email(username, new_email):
    """Change a user's email and refresh denormalized copies of it.

    The email also lives on any pending account-deletion request (kept there so
    the confirmation email survives the user document being deleted), and it
    keys password-reset tokens. Both are handled here: the deletion-request copy
    is updated, and any reset tokens for the old address are dropped since the
    user no longer controls it.

    Args:
        username: The account's exact stored username.
        new_email: The new email address (stored lower-cased, matching
            registration).

    Returns:
        The previous email address, or None if it was unset.

    Raises:
        ErrNoResult: If no user matches ``username``.
        ErrUnavailable: If the database is unavailable.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    new_email = new_email.lower()
    user_collection = get_collection('user')
    user = user_collection.find_one({'name': username}, {'email': 1})
    if not user:
        raise ErrNoResult("No user found with the provided username")

    old_email = user.get('email')
    if old_email == new_email:
        return old_email

    user_collection.update_one({'name': username}, {'$set': {'email': new_email}})

    # Keep the denormalized copy on any pending deletion request fresh.
    get_collection('account_deletion_request').update_many(
        {'requester': username},
        {'$set': {'email': new_email}}
    )

    # Reset tokens for the old address now point somewhere the user no longer
    # owns; discard them so they can't be used against the wrong mailbox.
    if old_email:
        get_collection('password_reset_tokens').delete_many(
            {'email': old_email.lower()}
        )

    return old_email


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
