"""
Login controller - User authentication.
"""

from flask import Blueprint, render_template, request, redirect, flash, session
from app.models.user import user_by_name
from app.models.errors import ErrNoResult
from app.services.passhash import match_string
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, FLASH_WARNING, authorized_chars_only
from app.controllers.decorators import anonymous_required

login_bp = Blueprint('login', __name__)


@login_bp.route('/login', methods=['GET'])
@anonymous_required
def login_get():
    """Display the login page."""
    return render_template('login/login.html')


@login_bp.route('/login', methods=['POST'])
@anonymous_required
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
            session.clear()
            session['email'] = user['email']
            session['name'] = user['name']
            flash('Login successful!', FLASH_SUCCESS)
            return redirect('/')
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
        session.clear()
        flash('Goodbye!', 'alert-info')

    return redirect('/')
