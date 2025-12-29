"""
Pytest configuration and fixtures for crackmes.one tests.
"""
import pytest
from unittest.mock import MagicMock, patch
import mongomock
from flask import Flask


@pytest.fixture
def app():
    """Create a test Flask application."""
    from app import create_app

    # Mock the config to use test settings
    test_config = {
        'Database': {
            'MongoDB': {
                'URL': 'mongodb://localhost:27017',
                'Database': 'test_crackmesone'
            }
        },
        'Recaptcha': {
            'Enabled': False,
            'SiteKey': 'test-site-key',
            'Secret': 'test-secret'
        },
        'Session': {
            'SecretKey': 'test-secret-key'
        },
        'Server': {
            'HTTPPort': 5000
        }
    }

    with patch('app.services.database.load_config', return_value=test_config):
        with patch('app.services.database.MongoClient') as mock_client:
            mock_client.return_value = mongomock.MongoClient()
            app = create_app()
            app.config['TESTING'] = True
            app.config['WTF_CSRF_ENABLED'] = False
            yield app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def mock_db():
    """Create a mock MongoDB database."""
    return mongomock.MongoClient().test_crackmesone


@pytest.fixture
def sample_user():
    """Sample user data for testing."""
    return {
        'name': 'testuser',
        'email': 'test@example.com',
        'password': 'password123',
        'level': 0,
        'nbcrackmes': 0,
        'nbsolutions': 0,
        'nbcomments': 0
    }


@pytest.fixture
def sample_crackme():
    """Sample crackme data for testing."""
    return {
        'name': 'Test Crackme',
        'author': 'testuser',
        'info': 'A test crackme for unit testing',
        'lang': 'C/C++',
        'arch': 'x86-64',
        'platform': 'Linux',
        'difficulty': 3.0,
        'quality': 4.0,
        'nbsolutions': 0,
        'nbcomments': 0
    }
