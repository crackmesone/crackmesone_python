"""
Comment model for database operations.
"""

from datetime import datetime
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, ReturnDocument
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


def comment_create(content, username, crackme_hexid, spoiler=False):
    """Create a new comment.

    Args:
        content: Comment text
        username: Author username
        crackme_hexid: Hex ID of the crackme
        spoiler: Whether the comment contains spoilers (default: False)
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
        'deleted': False,
        'spoiler': spoiler
    }

    collection.insert_one(comment)
    return comment


def comment_by_id(comment_id):
    """Get a comment by its ID.

    Args:
        comment_id: The comment's ObjectId (string or ObjectId)

    Returns:
        Comment document

    Raises:
        ErrNoResult: If comment not found
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('comment')

    if isinstance(comment_id, str):
        comment_id = ObjectId(comment_id)

    comment = collection.find_one({'_id': comment_id})
    if not comment:
        raise ErrNoResult("Comment not found")

    return comment


def get_thread_participants(crackme_hexid):
    """Get all unique usernames who have commented on a crackme.

    Args:
        crackme_hexid: Hex ID of the crackme

    Returns:
        Set of usernames who have commented on the crackme
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('comment')
    comments = collection.find(
        {'crackmehexid': crackme_hexid, 'visible': True},
        {'author': 1}
    )

    return set(comment['author'] for comment in comments)


def comment_set_spoiler(comment_id, is_spoiler):
    """Set the spoiler status of a comment.

    Args:
        comment_id: The comment's ObjectId (string or ObjectId)
        is_spoiler: Boolean indicating if comment is a spoiler

    Returns:
        Updated comment document

    Raises:
        ErrNoResult: If comment not found
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('comment')

    if isinstance(comment_id, str):
        comment_id = ObjectId(comment_id)

    result = collection.find_one_and_update(
        {'_id': comment_id},
        {'$set': {'spoiler': is_spoiler}},
        return_document=ReturnDocument.AFTER
    )

    if not result:
        raise ErrNoResult("Comment not found")

    return result
