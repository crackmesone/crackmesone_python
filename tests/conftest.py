"""Shared, isolated fixtures for application and model tests."""

import os

import mongomock
import pytest
from pymongo import MongoClient

from app.services.passhash import hash_string


def _test_config(mongo_client, database_name):
    return {
        'Database': {
            'URL': os.getenv('TEST_MONGODB_URL', 'mongodb://127.0.0.1:27017'),
            'Name': database_name,
            'Client': mongo_client,
        },
        'Recaptcha': {'Enabled': False, 'SiteKey': '', 'Secret': ''},
        'Session': {'SecretKey': 'test-secret-key', 'CookieName': 'test-session'},
        'RateLimiter': {'Enabled': False, 'StorageUri': 'memory://'},
        'Discord': {'Enabled': False},
        'Email': {'Enabled': False},
        'Reviewer': {'Enabled': True, 'PasswordSalt': 'test-reviewer-salt'},
        'Site': {'BaseURL': 'http://localhost'},
        'Writeup': {'ObfuscationSalt': 'test-obfuscation-salt'},
    }


@pytest.fixture(scope='session')
def mongo_client():
    """Use mongomock locally or a disposable real MongoDB when configured."""
    mongo_url = os.getenv('TEST_MONGODB_URL')
    client = MongoClient(mongo_url) if mongo_url else mongomock.MongoClient()
    if mongo_url:
        client.admin.command('ping')
    yield client
    client.drop_database('test_crackmesone')
    client.close()


@pytest.fixture(scope='session')
def app(mongo_client):
    from app import create_app

    application = create_app(config=_test_config(mongo_client, 'test_crackmesone'))
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield application


@pytest.fixture
def db(app):
    database = app.config['MONGO_DB']
    for collection_name in database.list_collection_names():
        database.drop_collection(collection_name)
    yield database
    for collection_name in database.list_collection_names():
        database.drop_collection(collection_name)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_external_service_config(app):
    """Prevent tests that change process-global service config leaking state."""
    from app.services.recaptcha import init_recaptcha
    from review import auth, routes

    init_recaptcha(app, app.config['APP_CONFIG']['Recaptcha'])
    auth.configure(routes.users)


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


@pytest.fixture
def alice(db):
    user = {
        'name': 'alice',
        'email': 'alice@example.test',
        'password': hash_string('alice-password'),
        'visible': True,
        'deleted': False,
        'unread_notifications': 0,
    }
    db.user.insert_one(user)
    return user


@pytest.fixture
def bob(db):
    user = {
        'name': 'bob',
        'email': 'bob@example.test',
        'password': hash_string('bob-password'),
        'visible': True,
        'deleted': False,
        'unread_notifications': 0,
    }
    db.user.insert_one(user)
    return user


def _authenticate(client, user):
    with client.session_transaction() as session:
        session['name'] = user['name']
        session['email'] = user['email']
    return client


@pytest.fixture
def alice_client(app, alice):
    return _authenticate(app.test_client(), alice)


@pytest.fixture
def bob_client(app, bob):
    return _authenticate(app.test_client(), bob)


@pytest.fixture
def reviewer_account():
    from review import routes

    routes.users['reviewer'] = {
        'password_hash': routes.hash_string(
            'reviewer-password' + 'test-reviewer-salt'
        ),
        'is_admin': False,
    }
    yield routes.users['reviewer']
    routes.users.pop('reviewer', None)


@pytest.fixture
def reviewer_client(app, reviewer_account):
    from review.routes import (
        REVIEWER_ADMIN_KEY,
        REVIEWER_CSRF_KEY,
        REVIEWER_SESSION_KEY,
    )

    client = app.test_client()
    with client.session_transaction() as session:
        session[REVIEWER_SESSION_KEY] = 'reviewer'
        session[REVIEWER_ADMIN_KEY] = False
        session[REVIEWER_CSRF_KEY] = 'test-csrf-token'
    return client


@pytest.fixture
def sample_crackme(db, alice):
    from bson import ObjectId
    from datetime import datetime, timezone

    object_id = ObjectId()
    crackme = {
        '_id': object_id,
        'hexid': str(object_id),
        'name': 'Test Crackme',
        'author': alice['name'],
        'info': 'A test crackme',
        'lang': 'C/C++',
        'arch': 'x86-64',
        'platform': 'Linux',
        'difficulty': 3.0,
        'quality': 4.0,
        'visible': True,
        'deleted': False,
        'nbsolutions': 0,
        'nbcomments': 0,
        'nbdownloads': 0,
        'size': 100,
        'created_at': datetime.now(timezone.utc),
    }
    db.crackme.insert_one(crackme)
    return crackme
