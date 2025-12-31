"""
Crackme model for database operations.
"""

import re
from datetime import datetime
from bson import ObjectId
from pymongo import DESCENDING
from app.services.database import get_collection, check_connection
from app.models.errors import ErrNoResult, ErrUnavailable


def count_crackmes():
    """Return the total number of crackmes.

    Uses estimated count for performance.
    """
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    return collection.estimated_document_count()


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


def search_crackme(name='', author='', lang='', arch='', platform='',
                   difficulty_min=0, difficulty_max=6,
                   quality_min=0, quality_max=6):
    """Search crackmes with filters."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')

    query = {
        'visible': True,
        'difficulty': {'$gte': difficulty_min, '$lte': difficulty_max},
        'quality': {'$gte': quality_min, '$lte': quality_max}
    }

    if name:
        query['name'] = {'$regex': name, '$options': 'i'}
    if author:
        query['author'] = {'$regex': author, '$options': 'i'}
    if lang:
        query['lang'] = {'$regex': lang, '$options': 'i'}
    if arch:
        query['arch'] = {'$regex': arch, '$options': 'i'}
    if platform:
        query['platform'] = {'$regex': platform, '$options': 'i'}

    return list(collection.find(query).sort('created_at', DESCENDING).limit(150))


def last_crackmes(page=1):
    """Get latest crackmes with pagination."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    skip = (page - 1) * 50

    return list(collection.find({'visible': True})
                .sort('created_at', DESCENDING)
                .skip(skip)
                .limit(50))


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


def crackme_create(name, info, username, lang, arch, platform):
    """Create a new crackme."""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('crackme')
    obj_id = ObjectId()

    crackme = {
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
        'platform': platform
    }

    collection.insert_one(crackme)
    return crackme


def crackme_create_prepare(name, info, username, lang, arch, platform):
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
        'platform': platform
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
