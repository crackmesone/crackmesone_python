"""
Login controller - User authentication.
"""

from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, flash, session
from app.models.user import user_by_name
from app.models.errors import ErrNoResult
from app.services.passhash import match_string
from app.services.limiter import limit
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, FLASH_WARNING, authorized_chars_only
from app.controllers.decorators import anonymous_required

login_bp = Blueprint('login', __name__)


def clear_main_auth():
    """Clear main site auth session keys only."""
    session.pop('name', None)
    session.pop('email', None)
    session.pop('login_attempt', None)


@login_bp.route('/login', methods=['GET'])
@anonymous_required
def login_get():
    """Display the login page."""
    # Extract path from referrer URL, but only if it's from our own site
    referrer = request.referrer
    if referrer:
        parsed = urlparse(referrer)
        if parsed.netloc == request.host:
            referrer = parsed.path or '/'
        else:
            referrer = '/'
    else:
        referrer = '/'
    # Only update redirect if referrer is not an auth-related page
    excluded_pages = ['/login', '/register', '/logout', '/forgot-password', '/reset-password']
    if not any(page in referrer for page in excluded_pages):
        session['login_redirect'] = referrer
    
    return render_template('login/login.html')


@login_bp.route('/login', methods=['POST'])
@anonymous_required
@limit("20 per hour")
def login_post():
    """Handle login form submission."""
    name = request.form.get('name', '')
    password = request.form.get('password', '')

    # Validate required fields
    if not name or not password:
        missing = 'name' if not name else 'password'
        flash(f'Field missing: {missing}', FLASH_ERROR)
        return render_template('login/login.html')

    # Check authorized characters
    if not authorized_chars_only(name):
        flash('Non authorized chars', FLASH_ERROR)
        return render_template('login/login.html')

    # Track login attempts
    attempts = session.get('login_attempt', 0)

    try:
        user = user_by_name(name)

        # Check password
        if match_string(user['password'], password):
            # Login successful
            clear_main_auth()
            session['email'] = user['email']
            session['name'] = user['name']
            flash('Login successful!', FLASH_SUCCESS)
            
            # Retrieve and clear the redirect from session
            # Only allow relative URLs to prevent redirecting to external sites
            redirect_url = session.pop('login_redirect', '/')
            if not redirect_url.startswith('/'):
                redirect_url = '/'
            return redirect(redirect_url)
        else:
            attempts += 1
            session['login_attempt'] = attempts
            flash(f'Password is incorrect - Attempt: {attempts}', FLASH_WARNING)

    except ErrNoResult:
        attempts += 1
        session['login_attempt'] = attempts
        flash(f'Password is incorrect - Attempt: {attempts}', FLASH_WARNING)

    except Exception as e:
        print(f"Login error: {e}")
        flash('There was an error. Please try again later.', FLASH_ERROR)

    return render_template('login/login.html')


@login_bp.route('/logout')
def logout():
    """Log out the user."""
    if session.get('name'):
        clear_main_auth()
        flash('Goodbye!', 'alert-info')

    return redirect('/')
