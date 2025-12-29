"""
Rating models (difficulty and quality) for database operations.
"""

from datetime import datetime
from bson import ObjectId
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable


# ============================================================================
# Rating Difficulty
# ============================================================================

def is_already_rated_difficulty(username, crackme_hexid):
    """Check if user already rated difficulty for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('rating_difficulty')
    count = collection.count_documents({
        'author': username,
        'crackmehexid': crackme_hexid
    })
    return count > 0


def rating_difficulty_by_crackme(crackme_hexid):
    """Get all difficulty ratings for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('rating_difficulty')
    return list(collection.find({'crackmehexid': crackme_hexid}))


def rating_difficulty_set_rating(username, crackme_hexid, rating):
    """Update a difficulty rating."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('rating_difficulty')
    collection.update_one(
        {'crackmehexid': crackme_hexid, 'author': username},
        {'$set': {'rating': rating}}
    )


def rating_difficulty_create(username, crackme_hexid, rating):
    """Create a new difficulty rating."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('rating_difficulty')
    obj_id = ObjectId()

    rating_doc = {
        '_id': obj_id,
        'rating': rating,
        'author': username,
        'crackmehexid': crackme_hexid,
        'created_at': datetime.utcnow(),
        'visible': True,
        'deleted': False
    }

    collection.insert_one(rating_doc)
    return rating_doc


def rating_difficulty_delete_by_crackme(crackme_hexid):
    """Delete all difficulty ratings for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('rating_difficulty')
    collection.delete_many({'crackmehexid': crackme_hexid})


# ============================================================================
# Rating Quality
# ============================================================================

def is_already_rated_quality(username, crackme_hexid):
    """Check if user already rated quality for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('rating_quality')
    count = collection.count_documents({
        'author': username,
        'crackmehexid': crackme_hexid
    })
    return count > 0


def rating_quality_by_crackme(crackme_hexid):
    """Get all quality ratings for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('rating_quality')
    return list(collection.find({'crackmehexid': crackme_hexid}))


def rating_quality_set_rating(username, crackme_hexid, rating):
    """Update a quality rating."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('rating_quality')
    collection.update_one(
        {'crackmehexid': crackme_hexid, 'author': username},
        {'$set': {'rating': rating}}
    )


def rating_quality_create(username, crackme_hexid, rating):
    """Create a new quality rating."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('rating_quality')
    obj_id = ObjectId()

    rating_doc = {
        '_id': obj_id,
        'rating': rating,
        'author': username,
        'crackmehexid': crackme_hexid,
        'created_at': datetime.utcnow(),
        'visible': True,
        'deleted': False
    }

    collection.insert_one(rating_doc)
    return rating_doc
