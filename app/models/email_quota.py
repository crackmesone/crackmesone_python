"""
Email quota tracking - limits password reset emails per day.
"""

from datetime import datetime, timezone
from app.services.database import get_collection

COLLECTION_NAME = 'email_quota'
PER_EMAIL_COLLECTION = 'email_quota_per_address'
DAILY_LIMIT = 90
PER_EMAIL_DAILY_LIMIT = 3


def get_today_key():
    """Get today's date as a string key (UTC)."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def get_daily_count():
    """Get the number of emails sent today."""
    collection = get_collection(COLLECTION_NAME)
    today = get_today_key()

    doc = collection.find_one({'_id': today})
    if doc:
        return doc.get('count', 0)
    return 0


def increment_daily_count():
    """Increment today's email count. Returns the new count."""
    collection = get_collection(COLLECTION_NAME)
    today = get_today_key()

    result = collection.find_one_and_update(
        {'_id': today},
        {'$inc': {'count': 1}},
        upsert=True,
        return_document=True
    )
    return result.get('count', 1)


def can_send_email():
    """Check if we can send another email today."""
    return get_daily_count() < DAILY_LIMIT


def quota_exceeded():
    """Check if the daily quota has been exceeded."""
    return get_daily_count() >= DAILY_LIMIT


def get_email_daily_count(email: str) -> int:
    """Get the number of reset emails sent to a specific address today."""
    collection = get_collection(PER_EMAIL_COLLECTION)
    today = get_today_key()
    key = f"{today}:{email.lower()}"

    doc = collection.find_one({'_id': key})
    if doc:
        return doc.get('count', 0)
    return 0


def increment_email_daily_count(email: str) -> int:
    """Increment today's count for a specific email. Returns the new count."""
    collection = get_collection(PER_EMAIL_COLLECTION)
    today = get_today_key()
    key = f"{today}:{email.lower()}"

    result = collection.find_one_and_update(
        {'_id': key},
        {'$inc': {'count': 1}},
        upsert=True,
        return_document=True
    )
    return result.get('count', 1)


def email_quota_exceeded(email: str) -> bool:
    """Check if a specific email has exceeded its daily reset limit."""
    return get_email_daily_count(email) >= PER_EMAIL_DAILY_LIMIT
