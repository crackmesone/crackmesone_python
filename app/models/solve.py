"""Solve model - records of users who submitted a crackme's correct flag.

A solve is the unit the point system is built on: one record per (user,
crackme) pair, carrying the points awarded at the moment it was earned.

Solves are keyed by the user's immutable hexid rather than their username.
Usernames are display data that can change; a score that silently zeroed out
when someone renamed themselves would be worse than no score at all.
"""

from datetime import datetime, timezone

from bson import ObjectId

from app.models.errors import ErrUnavailable
from app.services.database import get_collection, check_connection


def solve_by_user_and_crackme(user_hexid, crackme_hexid):
    """Return the user's solve of a crackme, or None if they haven't solved it."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    return get_collection('solve').find_one({
        'user_hexid': user_hexid,
        'crackme_hexid': crackme_hexid,
    })


def solve_create(user_hexid, crackme_hexid, points, difficulty):
    """Record a solve and return it.

    Args:
        user_hexid: The solver's immutable hexid.
        crackme_hexid: The solved crackme's hexid.
        points: Points awarded, snapshotted so a later change to the scoring
            formula doesn't retroactively re-price solves already earned.
        difficulty: The difficulty level those points were priced at.

    Returns:
        The inserted solve document, or the existing one if the user had
        already solved this crackme (double-submits are a no-op, never a
        second award).
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('solve')
    existing = collection.find_one({
        'user_hexid': user_hexid,
        'crackme_hexid': crackme_hexid,
    })
    if existing:
        return existing

    obj_id = ObjectId()
    solve = {
        '_id': obj_id,
        'hexid': str(obj_id),
        'user_hexid': user_hexid,
        'crackme_hexid': crackme_hexid,
        'created_at': datetime.now(timezone.utc),
        'points': int(points),
        'difficulty': int(difficulty),
    }
    collection.insert_one(solve)
    return solve


def solves_by_user(user_hexid):
    """Get a user's solves, newest first."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    solves = list(get_collection('solve').find({'user_hexid': user_hexid}))
    solves.sort(key=lambda s: s.get('created_at') or s['_id'].generation_time,
                reverse=True)
    return solves


def user_score(user_hexid):
    """Return a user's total score: the sum of the points on their solves.

    Summed from the solve records rather than kept as a counter on the user
    document, so the score can never drift out of step with the solves it is
    supposed to represent (a deleted crackme takes its points with it).
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    solves = get_collection('solve').find({'user_hexid': user_hexid},
                                          {'points': 1})
    return sum(solve.get('points', 0) for solve in solves)


def count_solves_by_crackme(crackme_hexid):
    """Count how many users have solved a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    return get_collection('solve').count_documents(
        {'crackme_hexid': crackme_hexid}
    )
