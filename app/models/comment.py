"""
Comment model for database operations.
"""

from datetime import datetime
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable


def count_comments_by_user(username):
    """Count comments by a specific user."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('comment')
    return collection.count_documents({'author': username})


def count_comments_by_crackme(crackme_hexid):
    """Count comments for a specific crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('comment')
    return collection.count_documents({
        'crackmehexid': crackme_hexid,
        'visible': True
    })


def comments_by_user(username):
    """Get all comments by a user."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('comment')
    return list(collection.find({'author': username, 'visible': True})
                .sort('created_at', DESCENDING))


def comments_by_crackme(crackme_hexid):
    """Get all comments for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('comment')
    return list(collection.find({
        'crackmehexid': crackme_hexid,
        'visible': True
    }).sort('created_at', ASCENDING))


def comment_create(content, username, crackme_hexid):
    """Create a new comment.

    Args:
        content: Comment text
        username: Author username
        crackme_hexid: Hex ID of the crackme
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    # Get the crackme to store its name
    from app.models.crackme import crackme_by_hexid
    crackme = crackme_by_hexid(crackme_hexid)

    collection = get_collection('comment')
    obj_id = ObjectId()

    comment = {
        '_id': obj_id,
        'info': content,  # 'info' field matches Go model's bson tag
        'author': username,
        'crackmehexid': crackme_hexid,
        'crackmename': crackme['name'],
        'created_at': datetime.utcnow(),
        'visible': True,
        'deleted': False
    }

    collection.insert_one(comment)
    return comment
