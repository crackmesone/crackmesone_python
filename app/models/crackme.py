"""
Crackme model for database operations.
"""

import re
from datetime import datetime
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable


def count_crackmes():
    """Return the total number of approved crackmes."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    return collection.count_documents({'visible': True})


def count_crackmes_by_user(username):
    """Count crackmes by a specific user."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    return collection.count_documents({'author': username, 'visible': True})


def get_all_crackmes():
    """Get all crackmes."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    return list(collection.find({}))


def crackme_set_float(hexid, field, value):
    """Set a float field on a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    collection.update_one(
        {'hexid': hexid},
        {'$set': {field: float(value)}}
    )


def crackme_update_difficulty(crackme_hexid):
    """Recalculate and update difficulty rating."""
    from app.models.rating import rating_difficulty_by_crackme

    difficulties = rating_difficulty_by_crackme(crackme_hexid)
    if difficulties:
        avg = sum(d['rating'] for d in difficulties) / len(difficulties)
    else:
        avg = 0.0

    crackme_set_float(crackme_hexid, 'difficulty', avg)


def crackme_update_quality(crackme_hexid):
    """Recalculate and update quality rating."""
    from app.models.rating import rating_quality_by_crackme

    qualities = rating_quality_by_crackme(crackme_hexid)
    if qualities:
        avg = sum(q['rating'] for q in qualities) / len(qualities)
    else:
        avg = 0.0

    crackme_set_float(crackme_hexid, 'quality', avg)


def crackme_increment_comments(crackme_hexid):
    """Increment comment count for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    collection.update_one(
        {'hexid': crackme_hexid},
        {'$inc': {'nbcomments': 1}}
    )


def crackme_decrement_comments(crackme_hexid):
    """Decrement comment count for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    collection.update_one(
        {'hexid': crackme_hexid},
        {'$inc': {'nbcomments': -1}}
    )


def crackme_increment_downloads(crackme_hexid):
    """Increment download count for a crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    collection.update_one(
        {'hexid': crackme_hexid},
        {'$inc': {'nbdownloads': 1}}
    )


SORT_FIELDS = {
    'date': 'created_at',
    'size': 'size',
    'downloads': 'nbdownloads',
    'solutions': 'nbsolutions',
    'comments': 'nbcomments',
    'quality': 'quality',
    'difficulty': 'difficulty',
}


def search_crackme(name='', author='', lang='', arch='', platform='',
                   labels=None,
                   difficulty_min=0, difficulty_max=6,
                   quality_min=0, quality_max=6,
                   downloads_min=0, downloads_max=None,
                   solutions_min=0, solutions_max=None,
                   comments_min=0, comments_max=None,
                   size_min=0, size_max=None,
                   sort_by='date', sort_order='desc',
                   page=1, per_page=50):
    """Search crackmes with filters, sorting, and pagination.

    Returns (results, has_more) where has_more indicates if there are more pages.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')

    query = {
        'visible': True,
        'difficulty': {'$gte': difficulty_min, '$lte': difficulty_max},
        'quality': {'$gte': quality_min, '$lte': quality_max}
    }

    if downloads_min > 0 or downloads_max is not None:
        downloads_query = {'$gte': downloads_min}
        if downloads_max is not None:
            downloads_query['$lte'] = downloads_max
        query['nbdownloads'] = downloads_query

    if solutions_min > 0 or solutions_max is not None:
        solutions_query = {'$gte': solutions_min}
        if solutions_max is not None:
            solutions_query['$lte'] = solutions_max
        query['nbsolutions'] = solutions_query

    if comments_min > 0 or comments_max is not None:
        comments_query = {'$gte': comments_min}
        if comments_max is not None:
            comments_query['$lte'] = comments_max
        query['nbcomments'] = comments_query

    if size_min > 0 or size_max is not None:
        size_query = {'$gte': size_min}
        if size_max is not None:
            size_query['$lte'] = size_max
        query['size'] = size_query

    if name:
        query['name'] = {'$regex': name, '$options': 'i'}
    if author:
        query['author'] = {'$regex': author, '$options': 'i'}
    # lang, arch, platform support multiple values (lists) with exact matching
    if lang:
        if isinstance(lang, list):
            query['lang'] = {'$in': lang}
        else:
            query['lang'] = lang
    if arch:
        if isinstance(arch, list):
            query['arch'] = {'$in': arch}
        else:
            query['arch'] = arch
    if platform:
        if isinstance(platform, list):
            query['platform'] = {'$in': platform}
        else:
            query['platform'] = platform
    # labels: a crackme must carry *all* selected labels ($all)
    if labels:
        if isinstance(labels, str):
            labels = [labels]
        if labels:
            query['labels'] = {'$all': labels}

    skip = (page - 1) * per_page
    # Determine sort field and direction
    sort_field = SORT_FIELDS.get(sort_by, 'created_at')
    sort_direction = ASCENDING if sort_order == 'asc' else DESCENDING
    # Fetch one extra to check if there are more results
    results = list(collection.find(query)
                   .sort(sort_field, sort_direction)
                   .skip(skip)
                   .limit(per_page + 1))

    has_more = len(results) > per_page
    if has_more:
        results = results[:per_page]

    return results, has_more


def last_crackmes(page=1):
    """Get latest crackmes with pagination.

    Returns (results, has_more) where has_more indicates if there are more pages.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    skip = (page - 1) * 50

    # Fetch one extra to check if there are more results
    results = list(collection.find({'visible': True})
                   .sort('created_at', DESCENDING)
                   .skip(skip)
                   .limit(51))

    has_more = len(results) > 50
    if has_more:
        results = results[:50]

    return results, has_more


def crackme_by_hexid(hexid):
    """Get crackme by hex ID."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    result = collection.find_one({'hexid': hexid, 'visible': True})

    if result is None:
        raise ErrNoResult("Crackme not found")

    return result


def crackmes_by_user(username):
    """Get all crackmes by a user."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    return list(collection.find({'author': username, 'visible': True})
                .sort('created_at', DESCENDING))


def crackme_by_user_and_name(username, name, visible=True):
    """Get crackme by user and name."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    result = collection.find_one({
        'name': name,
        'author': username,
        'visible': visible
    })

    if result is None:
        raise ErrNoResult("Crackme not found")

    return result


def crackme_create_prepare(name, info, username, lang, arch, platform, size, original_filename, labels=None):
    """Prepare a crackme object without inserting it."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    obj_id = ObjectId()

    return {
        '_id': obj_id,
        'hexid': str(obj_id),
        'name': name,
        'info': info,
        'lang': lang,
        'arch': arch,
        'author': username,
        'created_at': datetime.utcnow(),
        'visible': False,
        'deleted': False,
        'difficulty': 0.0,
        'quality': 0.0,
        'nbsolutions': 0,
        'nbcomments': 0,
        'nbdownloads': 0,
        'platform': platform,
        'size': size,
        'original_filename': original_filename,
        'labels': labels or []
    }


def crackme_insert(crackme):
    """Insert a prepared crackme into the database."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    collection.insert_one(crackme)


def crackme_delete_by_hexid(hexid):
    """Delete a crackme by hex ID."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    collection.delete_one({'hexid': hexid})


def random_crackmes(count=50):
    """Get multiple random visible crackmes."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    pipeline = [
        {'$match': {'visible': True}},
        {'$sample': {'size': count}}
    ]
    return list(collection.aggregate(pipeline))


def crackme_update(hexid, updates):
    """Update a crackme's fields.

    Args:
        hexid: The hex ID of the crackme
        updates: Dictionary of fields to update (name, info, lang, arch, platform)

    Returns:
        Dictionary with old values of changed fields, or None if crackme not found
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    # Only allow updating these fields (name is excluded to avoid database issues)
    allowed_fields = {'info', 'lang', 'arch', 'platform', 'labels'}
    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not filtered_updates:
        return {}

    collection = get_collection('crackme')

    # Get current values first
    crackme = collection.find_one({'hexid': hexid})
    if not crackme:
        return None

    # Track what changed
    changes = {}
    for field, new_value in filtered_updates.items():
        old_value = crackme.get(field)
        if old_value != new_value:
            changes[field] = {'old': old_value, 'new': new_value}

    if changes:
        collection.update_one(
            {'hexid': hexid},
            {'$set': filtered_updates}
        )

    return changes


def crackme_set_labels(hexid, labels):
    """Overwrite the obfuscation labels on a crackme.

    Args:
        hexid: The hex ID of the crackme
        labels: The full (already validated) list of labels to store

    Returns:
        The previous list of labels, or None if the crackme was not found.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    crackme = collection.find_one({'hexid': hexid}, {'labels': 1})
    if not crackme:
        return None

    old_labels = crackme.get('labels', [])
    collection.update_one({'hexid': hexid}, {'$set': {'labels': list(labels)}})
    return old_labels


def crackme_by_hexid_any(hexid):
    """Get crackme by hex ID regardless of visibility status.

    Used for admin/editing purposes.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    result = collection.find_one({'hexid': hexid})

    if result is None:
        raise ErrNoResult("Crackme not found")

    return result
