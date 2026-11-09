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


def users_by_hexids(hexids):
    """Return visible users keyed by immutable hexid."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    hexids = list(hexids)
    if not hexids:
        return {}
    return {
        user.get('hexid') or str(user['_id']): user
        for user in get_collection('user').find({
            '$or': [
                {'hexid': {'$in': hexids}},
                {'_id': {'$in': [ObjectId(value) for value in hexids
                                  if ObjectId.is_valid(value)]}},
            ],
            'visible': True,
        })
    }


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


# -- Manual solve tracking (Issue #182) ------------------------------------

_HEXID_RE = re.compile(r'^[a-f0-9]{24}$')
_MANUAL_SOLVE_HARD_CAP = 5_000


def user_toggle_manual_solve(username: str, crackme_hexid: str) -> bool:
    """Atomically toggle a manual solve mark for a user.

    Manual solves are strictly for personal progress tracking. They do NOT
    touch points, ratings, or any scoreboard field -- only the manual_solves
    array on the user document.

    Args:
        username:      The session username (session['name']).
        crackme_hexid: 24-char hex ID of the crackme to toggle.

    Returns:
        True  if crackme is now manually marked as done.
        False if crackme has been unmarked.

    Raises:
        ValueError:     Invalid hex ID format, or crackme doesn't exist /
                        isn't visible.
        ErrUnavailable: Database is not reachable.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    # --- Input validation ---
    if not username or not isinstance(username, str):
        raise ValueError("username must be a non-empty string")

    if not _HEXID_RE.match(crackme_hexid or ''):
        raise ValueError("crackme_hexid must be a 24-character hex string")

    # --- Crackme existence check (1 query, limit=1 is O(1) on the index) ---
    crackme_exists = get_collection('crackme').count_documents(
        {'hexid': crackme_hexid, 'visible': True}, limit=1
    )
    if not crackme_exists:
        raise ValueError(f"Crackme '{crackme_hexid}' not found or not visible")

    user_col = get_collection('user')

    # --- Determine current state: projection fetches only what we need ---
    user = user_col.find_one({'name': username}, {'manual_solves': 1})
    if user is None:
        raise ValueError(f"User '{username}' not found")

    current_solves = set(user.get('manual_solves') or [])
    already_solved = crackme_hexid in current_solves

    if already_solved:
        # Unmark: atomic pull
        user_col.update_one(
            {'name': username},
            {'$pull': {'manual_solves': crackme_hexid}}
        )
        return False
    else:
        # Guard: prevent document bloat beyond hard cap
        if len(current_solves) >= _MANUAL_SOLVE_HARD_CAP:
            raise ValueError(
                f"Manual solve limit of {_MANUAL_SOLVE_HARD_CAP} reached"
            )
        # Mark: atomic addToSet prevents duplicates under any race condition
        user_col.update_one(
            {'name': username},
            {'$addToSet': {'manual_solves': crackme_hexid}}
        )
        return True


def user_all_solved_hexids(username: str) -> dict:
    """Return all crackme hexids a user has completed, by source.

    Makes exactly TWO database reads:
    1. User document projection  -> manual_solves list
    2. Solve collection filter   -> official flag-validated solves

    Returns a dict::

        {
            "official": frozenset of hexids (flag-submitted, immutable),
            "manual":   frozenset of hexids (manually toggled),
            "all":      frozenset union (use this for grey-out + hide logic),
        }

    If the user doesn't exist or the database is unreachable, returns empty
    sets -- the caller must handle the graceful degradation itself.
    """
    if not check_connection():
        return {"official": frozenset(), "manual": frozenset(), "all": frozenset()}

    # 1. Manual solves -- single projection read on the user document
    user = get_collection('user').find_one(
        {'name': username}, {'hexid': 1, 'manual_solves': 1}
    )
    if not user:
        return {"official": frozenset(), "manual": frozenset(), "all": frozenset()}

    manual = frozenset(user.get('manual_solves') or [])

    # 2. Official flag solves -- keyed by user hexid (immutable, rename-safe)
    user_hexid = user.get('hexid') or str(user['_id'])
    solve_docs = get_collection('solve').find(
        {'user_hexid': user_hexid}, {'crackme_hexid': 1}
    )
    official = frozenset(doc['crackme_hexid'] for doc in solve_docs)

    return {
        "official": official,
        "manual":   manual,
        "all":      official | manual,
    }
