"""
Error handlers.
"""

import random
from flask import Blueprint, render_template

error_bp = Blueprint('error', __name__)

MESSAGES_404 = [
    "This page threw an access violation!",
    "The anti-debug check failed.",
    "This page requires a valid license key.",
    "The unpacker couldn't find this page.",
    "NOP sled detected. Nothing to execute here!",
    "Strings didn't help you find this one, huh?",
    "This is not the flag you're looking for.",
    "Invalid opcode at address 0x404.",
    "The keygen for this page doesn't exist yet.",
    "0x404: mov eax, PAGE | 0x408: jmp NOWHERE",
    "Symbol 'page' not found in symbol table.",
    "Single-stepped right past this page.",
]


@error_bp.app_errorhandler(404)
def error_404(error):
    """Handle 404 - Page Not Found."""
    message = random.choice(MESSAGES_404)
    return render_template('error/404.html', message=message), 404


@error_bp.app_errorhandler(500)
def error_500(error):
    """Handle 500 - Internal Server Error."""
    return 'Internal Server Error 500', 500


@error_bp.app_errorhandler(403)
def invalid_token(error):
    """Handle 403 - CSRF token error."""
    return '''Your token <strong>expired</strong>, click <a href="javascript:void(0)" onclick="location.replace(document.referrer)">here</a> to try again.''', 403
