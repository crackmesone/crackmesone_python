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
from app.services.limiter import init_limiter
from app.services.discord import init_discord
from app.services.view import register_filters


def create_app(config_path=None):
    """Create and configure the Flask application."""
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')
    app.url_map.strict_slashes = False

    # Load configuration
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                   'config', 'config.json')

    with open(config_path, 'r') as f:
        config = json.load(f)

    # Configure Flask app
    app.config['SECRET_KEY'] = config['Session']['SecretKey']
    app.config['SESSION_COOKIE_NAME'] = config['Session'].get('CookieName', 'crackmesone')
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
    init_limiter(app, config.get('RateLimiter', {}))
    init_discord(app, config.get('Discord'))

    # Register blueprints
    from app.controllers import register_blueprints
    register_blueprints(app)

    # Register reviewer blueprint (separate authentication system)
    reviewer_config = config.get('Reviewer', {})
    if reviewer_config.get('Enabled', False):
        from review.routes import reviewer_bp, init_reviewer
        from review.logger import init_logger as init_reviewer_logger
        app.config['REVIEWER_PASSWORD_SALT'] = reviewer_config.get('PasswordSalt', 'default_salt')
        init_reviewer(app)
        # Use private webhook for reviewer operation logs
        discord_config = config.get('Discord', {})
        private_webhook = discord_config.get('WebhookPrivate', '') if discord_config.get('Enabled', False) else None
        init_reviewer_logger(discord_webhook=private_webhook)
        app.register_blueprint(reviewer_bp)
        # Exempt reviewer routes from main CSRF (reviewer has its own CSRF)
        csrf.exempt(reviewer_bp)

    # Register template context processors
    @app.context_processor
    def inject_globals():
        from flask import session
        from app.models.user import user_get_unread_notifications

        username = session.get('name', '')
        unread_notifs = 0
        if username:
            unread_notifs = user_get_unread_notifications(username)

        return {
            'BaseURI': '/',
            'AuthLevel': 'auth' if username else 'anon',
            'usersess': username,
            'unread_notifications': unread_notifs,
            'RECAPTCHA_SITEKEY': config['Recaptcha'].get('SiteKey', '') if config['Recaptcha'].get('Enabled') else ''
        }

    # Register template filters
    register_filters(app)

    return app
