"""
Solution model for database operations.
"""

from datetime import datetime
from bson import ObjectId
from pymongo import DESCENDING
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable


def count_solutions():
    """Return the total number of solutions.

    Uses estimated count for performance.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('solution')
    return collection.estimated_document_count()


def count_solutions_by_user(username):
    """Count solutions by a specific user."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('solution')
    return collection.count_documents({'author': username, 'visible': True})


def count_solutions_by_crackme(crackme_hexid):
    """Count solutions for a specific crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('solution')
    try:
        obj_id = ObjectId(crackme_hexid)
        return collection.count_documents({'crackmeid': obj_id, 'visible': True})
    except Exception:
        return 0


def solution_by_hexid(hexid):
    """Get solution by hex ID."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('solution')
    result = collection.find_one({'hexid': hexid, 'visible': True})

    if result is None:
        raise ErrNoResult("Solution not found")

    return result


def solutions_by_user(username):
    """Get all solutions by a user."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('solution')
    return list(collection.find({'author': username, 'visible': True})
                .sort('created_at', DESCENDING))


def solutions_by_user_and_crackme(username, crackme_hexid):
    """Get solution by user and crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    # First get the crackme
    from app.models.crackme import crackme_by_hexid
    try:
        crackme = crackme_by_hexid(crackme_hexid)
    except ErrNoResult:
        raise ErrNoResult("Solution not found")

    collection = get_collection('solution')
    result = collection.find_one({
        'crackmeid': crackme['_id'],
        'author': username
    })

    if result is None:
        raise ErrNoResult("Solution not found")

    return result


def solutions_by_crackme(crackme_object_id):
    """Get all solutions for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('solution')
    return list(collection.find({
        'crackmeid': crackme_object_id,
        'visible': True
    }))


def solution_create(info, username, crackme_hexid):
    """Create a new solution."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    # Get the crackme
    from app.models.crackme import crackme_by_hexid
    crackme = crackme_by_hexid(crackme_hexid)

    collection = get_collection('solution')
    obj_id = ObjectId()

    solution = {
        '_id': obj_id,
        'hexid': str(obj_id),
        'info': info,
        'crackmeid': crackme['_id'],
        'created_at': datetime.utcnow(),
        'author': username,
        'visible': False,
        'deleted': False
    }

    collection.insert_one(solution)
    return solution
