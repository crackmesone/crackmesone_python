"""
Solution model for database operations.
"""

from datetime import datetime, timezone
from bson import ObjectId
from pymongo import DESCENDING
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable


def count_solutions():
    """Return the total number of approved solutions."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('solution')
    return collection.count_documents({'visible': True})


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
    solutions = list(collection.find({'author': username, 'visible': True}))

    # Extract created_at from ObjectId if not present
    for sol in solutions:
        if 'created_at' not in sol:
            sol['created_at'] = sol['_id'].generation_time

    # Sort by created_at descending
    solutions.sort(key=lambda x: x.get('created_at') or x['_id'].generation_time, reverse=True)
    return solutions


def solution_exists(username, crackme_hexid):
    """Check if a user has already submitted a solution for a crackme.

    Raises:
        ErrNoResult: If the crackme doesn't exist
        ErrUnavailable: If the database is unavailable
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    crackme_collection = get_collection('crackme')
    crackme = crackme_collection.find_one({'hexid': crackme_hexid}, {'_id': 1})
    if not crackme:
        raise ErrNoResult("Crackme not found")

    collection = get_collection('solution')
    return collection.find_one(
        {'crackmeid': crackme['_id'], 'author': username},
        {'_id': 1}
    ) is not None


def solutions_by_crackme(crackme_object_id):
    """Get all solutions for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('solution')
    return list(collection.find({
        'crackmeid': crackme_object_id,
        'visible': True
    }))


def get_solution_authors(crackme_hexid):
    """Get all unique usernames who have submitted solutions for a crackme.

    Args:
        crackme_hexid: Hex ID of the crackme

    Returns:
        Set of usernames who have submitted solutions
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('solution')
    solutions = collection.find(
        {'crackmehexid': crackme_hexid, 'visible': True},
        {'author': 1}
    )

    return set(solution['author'] for solution in solutions)


def solution_create(info, username, crackme_hexid, original_filename=None, has_markdown=False):
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
        'crackmehexid': crackme['hexid'],
        'crackmename': crackme['name'],
        'created_at': datetime.now(timezone.utc),
        'author': username,
        'visible': False,
        'deleted': False,
        'original_filename': original_filename,
        'has_markdown': has_markdown
    }

    collection.insert_one(solution)
    return solution, crackme
