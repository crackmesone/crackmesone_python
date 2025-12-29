"""
Error handlers.
"""

from flask import Blueprint

error_bp = Blueprint('error', __name__)


@error_bp.app_errorhandler(404)
def error_404(error):
    """Handle 404 - Page Not Found."""
    return 'Not Found 404', 404


@error_bp.app_errorhandler(500)
def error_500(error):
    """Handle 500 - Internal Server Error."""
    return 'Internal Server Error 500', 500


@error_bp.app_errorhandler(403)
def invalid_token(error):
    """Handle 403 - CSRF token error."""
    return '''Your token <strong>expired</strong>, click <a href="javascript:void(0)" onclick="location.replace(document.referrer)">here</a> to try again.''', 403
