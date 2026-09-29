"""
Password reset controller - Request and complete password reset.
"""

from flask import Blueprint, render_template, request, flash, redirect, current_app
from app.models.user import user_by_mail, update_user_password
from app.models.password_reset import create_reset_token, get_reset_token, delete_reset_token
from app.models.email_quota import (
    can_send_email, increment_daily_count, quota_exceeded,
    email_quota_exceeded, increment_email_daily_count
)
from app.models.errors import ErrNoResult
from app.services.passhash import hash_string
from app.services.email import send_email, is_configured as email_is_configured
from app.services.discord import notify_password_reset_request, notify_password_reset_complete
from app.services.recaptcha import verify as verify_recaptcha
from app.controllers.decorators import anonymous_required

password_reset_bp = Blueprint('password_reset', __name__)

FLASH_SUCCESS = 'success'
FLASH_ERROR = 'error'
FLASH_WARNING = 'warning'


@password_reset_bp.route('/forgot-password', methods=['GET'])
@anonymous_required
def forgot_password_get():
    """Display the forgot password form or FAQ link if quota exceeded."""
    if quota_exceeded():
        return render_template('password_reset/quota_exceeded.html')
    return render_template('password_reset/forgot.html')


@password_reset_bp.route('/forgot-password', methods=['POST'])
@anonymous_required
def forgot_password_post():
    """Handle forgot password request - send reset email."""
    # Check quota first (in case someone bypasses the form)
    if quota_exceeded():
        return render_template('password_reset/quota_exceeded.html')

    email = request.form.get('email', '').strip()

    if not email:
        flash('Please enter your email address', FLASH_ERROR)
        return render_template('password_reset/forgot.html')

    # Validate reCAPTCHA
    if not verify_recaptcha(request):
        flash('Verification failed. Please complete the challenge and try again.', FLASH_ERROR)
        return render_template('password_reset/forgot.html')

    # Check if email service is configured
    if not email_is_configured():
        flash('Password reset is currently unavailable. Please contact support.', FLASH_ERROR)
        return render_template('password_reset/forgot.html')

    # Check per-email quota first (prevents spam to single address)
    # We check this before user lookup to prevent timing-based enumeration
    if email_quota_exceeded(email):
        # Don't reveal rate limiting - show same success page
        return render_template('password_reset/email_sent.html')

    try:
        # Check if user exists
        user = user_by_mail(email)

        # Create reset token
        token = create_reset_token(user['email'])

        # Build reset URL using configured base URL (prevents Host header injection)
        site_config = current_app.config.get('APP_CONFIG', {}).get('Site', {})
        base_url = site_config.get('BaseURL', 'https://crackmes.one')
        reset_url = f"{base_url}/reset-password/{token}"

        # Send email
        subject = "Password Reset Request - crackmes.one"
        body = f"""Hello,

You have requested to reset your password on crackmes.one.

Click the link below to reset your password:
{reset_url}

This link will expire in 1 hour.

If you did not request this password reset, please ignore this email.

Best regards,
The crackmes.one team
"""

        email_sent = send_email(user['email'], subject, body)
        if email_sent:
            increment_daily_count()
            increment_email_daily_count(user['email'])
            notify_password_reset_request(user['email'])
        else:
            print(f"Failed to send password reset email to {user['email']}")

    except ErrNoResult:
        # User not found - don't reveal this to prevent enumeration
        pass
    except Exception as e:
        print(f"Error during password reset request: {e}")

    # Show landing page with instructions (prevents email enumeration)
    return render_template('password_reset/email_sent.html')


@password_reset_bp.route('/reset-password/<token>', methods=['GET'])
@anonymous_required
def reset_password_get(token):
    """Display the reset password form."""
    try:
        # Validate token exists and is not expired
        token_doc = get_reset_token(token)
        # Look up user to get username
        user = user_by_mail(token_doc['email'])
        return render_template('password_reset/reset.html', token=token, username=user['name'])
    except ErrNoResult:
        flash('This password reset link is invalid or has expired.', FLASH_ERROR)
        return redirect('/forgot-password')
    except Exception as e:
        print(f"Error validating reset token: {e}")
        flash('An error occurred. Please try again.', FLASH_ERROR)
        return redirect('/forgot-password')


@password_reset_bp.route('/reset-password/<token>', methods=['POST'])
@anonymous_required
def reset_password_post(token):
    """Handle password reset submission."""
    new_password = request.form.get('new_password', '')
    new_password_verify = request.form.get('new_password_verify', '')

    # Validate token and get user first (so we can show username in error messages)
    try:
        token_doc = get_reset_token(token)
        email = token_doc['email']
        user = user_by_mail(email)
        username = user['name']
    except ErrNoResult:
        flash('This password reset link is invalid or has expired.', FLASH_ERROR)
        return redirect('/forgot-password')
    except Exception as e:
        print(f"Error validating reset token: {e}")
        flash('An error occurred. Please try again.', FLASH_ERROR)
        return redirect('/forgot-password')

    # Validate passwords
    if not new_password or not new_password_verify:
        flash('Please fill in all password fields', FLASH_ERROR)
        return render_template('password_reset/reset.html', token=token, username=username)

    if new_password != new_password_verify:
        flash('Passwords do not match', FLASH_ERROR)
        return render_template('password_reset/reset.html', token=token, username=username)

    if len(new_password) < 8:
        flash('Password must be at least 8 characters long', FLASH_ERROR)
        return render_template('password_reset/reset.html', token=token, username=username)

    try:
        # Hash new password
        hashed_password = hash_string(new_password)

        # Update user's password
        update_user_password(username, hashed_password)

        # Delete the used token
        delete_reset_token(token)

        # Notify moderation channel
        notify_password_reset_complete(username, email)

        flash(f'Password reset successfully for {username}. You can now log in.', FLASH_SUCCESS)
        return redirect('/login')

    except Exception as e:
        print(f"Error resetting password: {e}")
        flash('An error occurred while resetting your password. Please try again.', FLASH_ERROR)
        return render_template('password_reset/reset.html', token=token, username=username)
