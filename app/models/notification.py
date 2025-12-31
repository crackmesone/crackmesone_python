"""
Notification model for database operations.
"""

from datetime import datetime
from bson import ObjectId
from pymongo import DESCENDING
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable
from app.models.user import user_increment_unread_notifications, user_decrement_unread_notifications


def notifications_by_user(username):
    """Get all notifications for a user."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('notifications')
    return list(collection.find({'user': username})
                .sort('time', DESCENDING))


def notifications_set_seen(username, notifications):
    """Mark notifications as seen and update user's unread count."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('notifications')

    unseen_count = 0
    for notif in notifications:
        if notif.get('seen'):
            continue

        collection.update_one(
            {'hexid': notif['hexid']},
            {'$set': {'seen': True}}
        )
        unseen_count += 1

    # Decrement user's unread notification count
    if unseen_count > 0:
        user_decrement_unread_notifications(username, unseen_count)


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

    # Increment user's unread notification count
    user_increment_unread_notifications(username)

    return notif


def notification_mark_seen_single(username, hexid):
    """Mark a single notification as seen and update user's unread count.

    Returns:
        True if notification was marked as seen, False if already seen or not found
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('notifications')

    # Check if notification exists and is unseen
    notif = collection.find_one({'user': username, 'hexid': hexid})
    if not notif:
        return False

    if notif.get('seen'):
        return False  # Already seen

    # Mark as seen
    collection.update_one(
        {'user': username, 'hexid': hexid},
        {'$set': {'seen': True}}
    )

    # Decrement user's unread count
    user_decrement_unread_notifications(username, 1)

    return True


def notification_remove(username, hexid):
    """Remove a notification."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('notifications')
    collection.delete_one({'user': username, 'hexid': hexid})
