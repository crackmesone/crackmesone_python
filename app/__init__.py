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
from app.services.email import configure as configure_email
from app.services.view import register_filters


def create_app(config_path=None, config=None):
    """Create and configure the Flask application.

    ``config`` allows tests and other callers to supply configuration without
    creating or modifying the production JSON file.  Production continues to
    load ``config_path`` when no configuration mapping is supplied.
    """
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')
    app.url_map.strict_slashes = False

    if config is None:
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

    # Initialize email service if configured
    email_config = config.get('Email', {})
    if email_config.get('Enabled', False):
        configure_email(email_config)

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

    # Re-resolve the logged-in user from their immutable id on every request.
    # Usernames are mutable (they can be changed in account settings), so the
    # name stored in the signed cookie can go stale on other devices. Keying off
    # the id lets us refresh the cookie's name in place — otherwise a stale
    # session could post content under a username that no longer exists, or lose
    # ownership of its own (now-renamed) content. If the account is gone, the
    # auth keys are cleared so the request is treated as anonymous.
    @app.before_request
    def refresh_session_identity():
        from bson import ObjectId
        from bson.errors import InvalidId
        from flask import request, session, g
        from app.models.user import user_by_name
        from app.services.database import get_collection
        from app.models.errors import ErrNoResult

        g.current_user = None
        if request.endpoint == 'static' or not session.get('name'):
            return

        try:
            user = None
            hexid = session.get('hexid')
            if hexid:
                # Resolve by the primary key (indexed point-read), not the
                # unindexed hexid field, so this stays the cheapest query there is.
                try:
                    user = get_collection('user').find_one({'_id': ObjectId(hexid)})
                except InvalidId:
                    user = None
            else:
                # Legacy session issued before ids were stored; resolve by name
                # once and backfill the id so future requests are id-based.
                try:
                    user = user_by_name(session['name'])
                except ErrNoResult:
                    user = None

            if user is None:
                # Account deleted (or the old name was freed and re-registered by
                # someone else): drop our stale auth rather than impersonate.
                session.pop('name', None)
                session.pop('email', None)
                session.pop('hexid', None)
            else:
                session['name'] = user['name']
                session['email'] = user.get('email', session.get('email'))
                session['hexid'] = user.get('hexid') or str(user['_id'])
                g.current_user = user
        except Exception as e:
            # A transient DB error shouldn't break the request; leave the
            # session untouched and let downstream handlers cope.
            print(f"Session identity refresh error: {e}")

    # Register template context processors
    @app.context_processor
    def inject_globals():
        from flask import session, g
        from app.services.crackme_fields import (
            DIFFICULTY_CHOICES, LANG_CHOICES, ARCH_CHOICES, PLATFORM_CHOICES)

        username = session.get('name', '')
        # Reuse the user loaded in refresh_session_identity so this doesn't add a
        # second per-request query.
        current_user = getattr(g, 'current_user', None)
        unread_notifs = current_user.get('unread_notifications', 0) if current_user else 0

        return {
            'BaseURI': '/',
            'AuthLevel': 'auth' if username else 'anon',
            'usersess': username,
            'unread_notifications': unread_notifs,
            'RECAPTCHA_SITEKEY': config['Recaptcha'].get('SiteKey', '') if config['Recaptcha'].get('Enabled') else '',
            'DIFFICULTY_CHOICES': DIFFICULTY_CHOICES,
            'LANG_CHOICES': LANG_CHOICES,
            'ARCH_CHOICES': ARCH_CHOICES,
            'PLATFORM_CHOICES': PLATFORM_CHOICES,
        }

    # Register template filters
    register_filters(app)

    return app
