"""
Account deletion request model.

A logged-in user can request that their own account be deleted. Requests land
in a pending queue that reviewers approve or reject; approving a request runs the
full account deletion and emails the (now former) user. The requester's email is
denormalized onto the request so the confirmation email can still be sent after
the user document is gone.
"""

from datetime import datetime
from bson import ObjectId
from pymongo import DESCENDING, ReturnDocument
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable

# Request lifecycle states.
STATUS_PENDING = 'pending'
STATUS_APPROVED = 'approved'
STATUS_REJECTED = 'rejected'


def account_deletion_request_create(username, email, note=''):
    """Create a pending account deletion request.

    Args:
        username: Username of the requesting user
        email: The user's email (denormalized for the confirmation email)
        note: Optional free-text reason from the requester

    Returns:
        The inserted request document.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('account_deletion_request')
    obj_id = ObjectId()

    request = {
        '_id': obj_id,
        'hexid': str(obj_id),
        'requester': username,
        'email': email,
        'note': note or '',
        'status': STATUS_PENDING,
        'created_at': datetime.utcnow(),
        'reviewed_by': None,
        'reviewed_at': None,
    }

    collection.insert_one(request)
    return request


def account_deletion_requests_pending():
    """Return all pending account deletion requests, newest first."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('account_deletion_request')
    return list(collection.find({'status': STATUS_PENDING})
                .sort('created_at', DESCENDING))


def count_pending_account_deletion_requests():
    """Count pending account deletion requests."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('account_deletion_request')
    return collection.count_documents({'status': STATUS_PENDING})


def account_deletion_request_by_hexid(hexid):
    """Get an account deletion request by its hex ID.

    Raises:
        ErrNoResult: If no request matches.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('account_deletion_request')
    request = collection.find_one({'hexid': hexid})
    if not request:
        raise ErrNoResult("Account deletion request not found")
    return request


def account_deletion_request_set_status(hexid, status, reviewer):
    """Mark a request approved/rejected and stamp the reviewer.

    Returns:
        The updated request document, or None if not found.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('account_deletion_request')
    return collection.find_one_and_update(
        {'hexid': hexid},
        {'$set': {
            'status': status,
            'reviewed_by': reviewer,
            'reviewed_at': datetime.utcnow(),
        }},
        return_document=ReturnDocument.AFTER
    )


def pending_account_deletion_request_by_user(username):
    """Return a user's existing pending deletion request, if any (anti-dup)."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('account_deletion_request')
    return collection.find_one({
        'requester': username,
        'status': STATUS_PENDING,
    })
