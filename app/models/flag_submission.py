"""Persistent audit records for user flag-submission attempts."""

from datetime import datetime, timezone

from bson import ObjectId

from app.models.errors import ErrUnavailable
from app.services.database import get_collection, check_connection


def flag_submission_create(
        user_hexid, username, crackme_hexid, submitted_flag, result):
    """Persist one flag-validation attempt and return the inserted document."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    obj_id = ObjectId()
    submission = {
        '_id': obj_id,
        'hexid': str(obj_id),
        'user_hexid': user_hexid,
        'username': username,
        'crackme_hexid': crackme_hexid,
        'submitted_flag': submitted_flag,
        'result': result,
        'created_at': datetime.now(timezone.utc),
    }
    get_collection('flag_submission').insert_one(submission)
    return submission


def flag_submissions_by_crackme(crackme_hexid, limit=100):
    """Return the newest audit entries for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    return list(
        get_collection('flag_submission')
        .find({'crackme_hexid': crackme_hexid})
        .sort('created_at', -1)
        .limit(limit)
    )


def count_flag_submissions_by_crackme(crackme_hexid):
    """Return the number of attempted flag submissions for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    return get_collection('flag_submission').count_documents({
        'crackme_hexid': crackme_hexid,
    })
