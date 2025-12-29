"""
crackmes.one - Flask Application
A platform for sharing and solving reverse engineering challenges.
"""

import json
import os
from flask import Flask
from flask_wtf.csrf import CSRFProtect

from app.services.database import init_db
from app.services.session import init_session
from app.services.recaptcha import init_recaptcha
from app.services.view import init_view


def create_app(config_path=None):
    """Create and configure the Flask application."""
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    # Load configuration
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                   'config', 'config.json')

    with open(config_path, 'r') as f:
        config = json.load(f)

    # Configure Flask app
    app.config['SECRET_KEY'] = config['Session']['SecretKey']
    app.config['SESSION_COOKIE_NAME'] = config['Session']['Name']
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = None  # No expiry

    # Store full config for access by services
    app.config['APP_CONFIG'] = config

    # Initialize CSRF protection
    csrf = CSRFProtect(app)

    # Initialize services
    init_db(app, config['Database'])
    init_session(app, config['Session'])
    init_recaptcha(app, config['Recaptcha'])
    init_view(app, config['View'])

    # Register blueprints
    from app.controllers import register_blueprints
    register_blueprints(app)

    # Register template context processors
    @app.context_processor
    def inject_globals():
        from flask import session
        return {
            'BaseURI': config['View']['BaseURI'],
            'AuthLevel': 'auth' if session.get('name') else 'anon',
            'usersess': session.get('name', ''),
            'RECAPTCHA_SITEKEY': config['Recaptcha'].get('SiteKey', '') if config['Recaptcha'].get('Enabled') else ''
        }

    # Register template filters
    from app.services.view import register_filters
    register_filters(app)

    return app
