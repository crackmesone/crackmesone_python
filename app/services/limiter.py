"""
Rate limiting service using Flask-Limiter.
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
            - DefaultLimits: list - Default rate limits (e.g., ["200 per day", "50 per hour"])
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
    default_limits = config.get('DefaultLimits', [])

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=default_limits,
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

        @app.route('/api/resource')
        @limit("5 per minute")
        def resource():
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
