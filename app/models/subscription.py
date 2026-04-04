"""
subscriptions model for database operations.
"""

import re
from app.services.database import get_collection, check_connection
from app.models.user import user_by_name
from app.models.errors import ErrNoResult

def get_users_subbed_to(name):
    """Return a list with all users subscribed to NAME"""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")
    
    collection = get_collection('subscriptions')
    user = user_by_name(name)['name']
    result = [x.get('name') for x in collection.find({'to': user})]

    if result is None:
        raise ErrNoResult("No Subscribers yet")

    return result

def get_user_subs(name):
    """Return the subscriptions list of NAME"""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")

    collection = get_collection('subscriptions')
    user = user_by_name(name)['name']
    result = [x.get('to') for x in collection.find({'name': user})]

    if result is None:
        raise ErrNoResult("No Subscribtions yet")

    return result

def user_subscribe_to(name, to_name):
    """Make NAME subscribe to TO_NAME"""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")
        
    if to_name in get_user_subs(name):
        return
        
    collection = get_collection('subscriptions')

    collection.insert_one({'name': name, 'to': to_name})

def user_unsubscribe_to(name, to_name):
    """Make USER unsubscribe to TO_NAME"""
    if not check_connection():
        raise ErrUnavailable("Database is unavailable")
        
    if not to_name in get_user_subs(name):
        return
        
    collection = get_collection('subscriptions')

    collection.delete_one({'name': name, 'to': to_name})