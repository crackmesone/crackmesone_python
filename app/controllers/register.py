"""
Register controller - User registration.
"""

from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, flash, session
from app.models.user import user_by_name, user_by_mail, user_create
from app.models.errors import ErrNoResult
from app.services.passhash import hash_string
from app.services.recaptcha import verify as verify_recaptcha
from app.services.limiter import limit
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, authorized_chars_only
from app.controllers.decorators import anonymous_required

register_bp = Blueprint('register', __name__)


@register_bp.route('/register', methods=['GET'])
@anonymous_required
def register_get():
    """Display the registration page."""
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
    
    return render_template('register/register.html')


@register_bp.route('/register', methods=['POST'])
@anonymous_required
@limit("10 per hour")
def register_post():
    """Handle registration form submission."""
    # Check for brute force
    attempts = session.get('register_attempt', 0)
    if attempts >= 5:
        print("Brute force register prevented")
        return redirect('/register')

    name = request.form.get('name', '')
    email = request.form.get('email', '').lower()
    password = request.form.get('password', '')

    # Validate required fields
    if not name or not email or not password:
        missing = 'name' if not name else ('email' if not email else 'password')
        flash(f'Field missing: {missing}', FLASH_ERROR)
        return render_template('register/register.html', name=name, email=email)

    # Validate reCAPTCHA
    if not verify_recaptcha(request):
        flash('reCAPTCHA invalid!', FLASH_ERROR)
        return render_template('register/register.html', name=name, email=email)

    # Check authorized characters
    if not authorized_chars_only(name) or not authorized_chars_only(email):
        flash('Non allowed chars', FLASH_ERROR)
        return render_template('register/register.html', name=name, email=email)

    # Hash password
    try:
        hashed_password = hash_string(password)
    except Exception as e:
        print(f"Password hash error: {e}")
        flash('An error occurred on the server. Please try again later.', FLASH_ERROR)
        return redirect('/register')

    # Check if email already exists
    try:
        user_by_mail(email)
        flash(f'Account already exists for: {email}', FLASH_ERROR)
        return render_template('register/register.html', name=name, email=email)
    except ErrNoResult:
        pass  # Email not taken, continue
    except Exception as e:
        print(f"Database error: {e}")
        flash('An error occurred on the server. Please try again later.', FLASH_ERROR)
        return render_template('register/register.html', name=name, email=email)

    # Check if username already exists
    try:
        user_by_name(name)
        flash(f'Account already exists for: {name}', FLASH_ERROR)
        return render_template('register/register.html', name=name, email=email)
    except ErrNoResult:
        # Username not taken, create account
        try:
            user_create(name, email, hashed_password)
            flash(f'Account created successfully for: {name}', FLASH_SUCCESS)
            return redirect('/login')
        except Exception as e:
            print(f"User creation error: {e}")
            flash('An error occurred on the server. Please try again later.', FLASH_ERROR)
    except Exception as e:
        print(f"Database error: {e}")
        flash('An error occurred on the server. Please try again later.', FLASH_ERROR)

    return render_template('register/register.html', name=name, email=email)
