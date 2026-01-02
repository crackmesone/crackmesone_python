"""
Rate limiting service using Flask-Limiter.

Rate Limits Documentation
=========================

The following rate limits are applied to protect against spam and abuse:

+-------------------------+----------------+-------------+----------------------------------+
| Route                   | Limit          | Limited By  | Purpose                          |
+-------------------------+----------------+-------------+----------------------------------+
| POST /register          | 10 per hour    | IP address  | Prevent mass account creation    |
| POST /login             | 20 per hour    | IP address  | Prevent brute-force attacks      |
| POST /change-password   | 5 per hour     | Username    | Prevent password guess attempts  |
| POST /upload/crackme    | 10 per day     | Username    | Prevent submission spam          |
| POST /upload/solution   | 20 per day     | Username    | Prevent submission spam          |
| POST /comment           | 30 per hour    | Username    | Prevent comment spam             |
+-------------------------+----------------+-------------+----------------------------------+

Configuration
=============

Rate limiting can be enabled/disabled via config.json:

    "RateLimiter": {
        "Enabled": true,
        "StorageUri": "memory://"
    }

Storage options:
- "memory://" - In-memory storage (default, suitable for single instance)
- "redis://localhost:6379" - Redis storage (recommended for production)
- "mongodb://localhost:27017" - MongoDB storage
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Global limiter instance and configuration
limiter = None
limiter_config = {}


def init_limiter(app, config):
    """Initialize rate limiter with configuration.

    Args:
        app: Flask application instance
        config: Rate limiter configuration dict with keys:
            - Enabled: bool - Whether rate limiting is enabled
            - StorageUri: str - Storage backend URI (default: memory://)
    """
    global limiter, limiter_config
    limiter_config = config

    if not is_enabled():
        # Create a no-op limiter that doesn't actually limit
        limiter = Limiter(
            key_func=get_remote_address,
            app=app,
            enabled=False,
            storage_uri="memory://",
        )
        return

    storage_uri = config.get('StorageUri', 'memory://')

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        storage_uri=storage_uri,
        strategy="fixed-window",
    )


def is_enabled():
    """Check if rate limiting is enabled."""
    return limiter_config.get('Enabled', False)


def get_limiter():
    """Get the limiter instance."""
    return limiter


def limit(*args, **kwargs):
    """Decorator for rate limiting routes.

    Usage:
        from app.services.limiter import limit

        # Limit by IP address (default)
        @app.route('/api/resource')
        @limit("5 per minute")
        def resource():
            ...

        # Limit by username (for logged-in routes)
        @app.route('/upload')
        @limit("10 per day", key_func=lambda: session.get('name'))
        def upload():
            ...

    When rate limiting is disabled, this decorator does nothing.
    """
    if limiter is None:
        # Return a no-op decorator if limiter not initialized
        def decorator(f):
            return f
        return decorator

    return limiter.limit(*args, **kwargs)


def shared_limit(*args, **kwargs):
    """Decorator for shared rate limits across multiple routes.

    Usage:
        from app.services.limiter import shared_limit

        submission_limit = shared_limit("10 per hour", scope="submissions")

        @app.route('/upload/crackme')
        @submission_limit
        def upload_crackme():
            ...

        @app.route('/upload/solution')
        @submission_limit
        def upload_solution():
            ...
    """
    if limiter is None:
        def decorator(f):
            return f
        return decorator

    return limiter.shared_limit(*args, **kwargs)


def exempt(f):
    """Decorator to exempt a route from rate limiting.

    Usage:
        from app.services.limiter import exempt

        @app.route('/health')
        @exempt
        def health_check():
            ...
    """
    if limiter is None:
        return f

    return limiter.exempt(f)
