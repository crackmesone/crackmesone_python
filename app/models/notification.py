"""
Notification model for database operations.
"""

from datetime import datetime
from bson import ObjectId
from pymongo import DESCENDING
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable


def notifications_by_user(username):
    """Get all notifications for a user."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('notifications')
    return list(collection.find({'user': username})
                .sort('time', DESCENDING))


def notifications_set_seen(notifications):
    """Mark notifications as seen."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('notifications')

    for notif in notifications:
        if notif.get('seen'):
            continue

        collection.update_one(
            {'hexid': notif['hexid']},
            {'$set': {'seen': True}}
        )


def notifications_has_unseen(username):
    """Check if user has unseen notifications."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('notifications')
    count = collection.count_documents({'user': username, 'seen': False})
    return count > 0


def notification_add(username, text):
    """Add a notification for a user."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('notifications')
    obj_id = ObjectId()

    notif = {
        '_id': obj_id,
        'hexid': str(obj_id),
        'user': username,
        'text': text,
        'time': datetime.utcnow(),
        'seen': False
    }

    collection.insert_one(notif)
    return notif


def notification_remove(username, hexid):
    """Remove a notification."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('notifications')
    collection.delete_one({'user': username, 'hexid': hexid})
