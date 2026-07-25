"""
Tag change request model.

Any logged-in user can request that tags be added to or removed from a crackme.
Requests land in a pending queue that reviewers approve or reject; approving a
request applies the add/remove sets to the crackme's tags.
"""

from datetime import datetime
from bson import ObjectId
from pymongo import DESCENDING
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable

# Request lifecycle states.
STATUS_PENDING = 'pending'
STATUS_APPROVED = 'approved'
STATUS_REJECTED = 'rejected'


def tag_request_create(hexid, crackme_name, requester, add=None, remove=None, note=''):
    """Create a pending tag change request.

    Args:
        hexid: Hex ID of the target crackme
        crackme_name: Name of the crackme (denormalized for the review queue)
        requester: Username of the requesting user
        add: List of (already validated) tags to add
        remove: List of (already validated) tags to remove
        note: Optional free-text justification from the requester

    Returns:
        The inserted request document.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('tag_request')
    obj_id = ObjectId()

    request = {
        '_id': obj_id,
        'hexid': str(obj_id),
        'crackme_hexid': hexid,
        'crackme_name': crackme_name,
        'requester': requester,
        'add': list(add or []),
        'remove': list(remove or []),
        'note': note or '',
        'status': STATUS_PENDING,
        'created_at': datetime.utcnow(),
        'reviewed_by': None,
        'reviewed_at': None,
    }

    collection.insert_one(request)
    return request


def tag_requests_pending():
    """Return all pending tag change requests, newest first."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('tag_request')
    return list(collection.find({'status': STATUS_PENDING})
                .sort('created_at', DESCENDING))


def count_pending_tag_requests():
    """Count pending tag change requests."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('tag_request')
    return collection.count_documents({'status': STATUS_PENDING})


def tag_request_by_hexid(hexid):
    """Get a tag change request by its hex ID.

    Raises:
        ErrNoResult: If no request matches.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('tag_request')
    request = collection.find_one({'hexid': hexid})
    if not request:
        raise ErrNoResult("Tag request not found")
    return request


def tag_request_set_status(hexid, status, reviewer):
    """Mark a request approved/rejected and stamp the reviewer.

    Returns:
        The updated request document, or None if not found.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    from pymongo import ReturnDocument

    collection = get_collection('tag_request')
    return collection.find_one_and_update(
        {'hexid': hexid},
        {'$set': {
            'status': status,
            'reviewed_by': reviewer,
            'reviewed_at': datetime.utcnow(),
        }},
        return_document=ReturnDocument.AFTER
    )


def pending_tag_requests_by_user_and_crackme(requester, crackme_hexid):
    """Count a user's already-pending requests for one crackme (anti-spam)."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('tag_request')
    return collection.count_documents({
        'requester': requester,
        'crackme_hexid': crackme_hexid,
        'status': STATUS_PENDING,
    })
