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

    # Check if email service is configured
    if not email_is_configured():
        flash('Password reset is currently unavailable. Please contact support.', FLASH_ERROR)
        return render_template('password_reset/forgot.html')

    # Always show success message to prevent email enumeration
    success_message = 'If an account with that email exists, a password reset link has been sent.'

    # Check per-email quota first (prevents spam to single address)
    # We check this before user lookup to prevent timing-based enumeration
    if email_quota_exceeded(email):
        # Don't reveal rate limiting - show same success message
        flash(success_message, FLASH_SUCCESS)
        return render_template('password_reset/forgot.html')

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

    flash(success_message, FLASH_SUCCESS)
    return render_template('password_reset/forgot.html')


@password_reset_bp.route('/reset-password/<token>', methods=['GET'])
@anonymous_required
def reset_password_get(token):
    """Display the reset password form."""
    try:
        # Validate token exists and is not expired
        get_reset_token(token)
        return render_template('password_reset/reset.html', token=token)
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

    # Validate passwords
    if not new_password or not new_password_verify:
        flash('Please fill in all password fields', FLASH_ERROR)
        return render_template('password_reset/reset.html', token=token)

    if new_password != new_password_verify:
        flash('Passwords do not match', FLASH_ERROR)
        return render_template('password_reset/reset.html', token=token)

    if len(new_password) < 8:
        flash('Password must be at least 8 characters long', FLASH_ERROR)
        return render_template('password_reset/reset.html', token=token)

    try:
        # Validate token and get associated email
        token_doc = get_reset_token(token)
        email = token_doc['email']

        # Find user by email
        user = user_by_mail(email)

        # Hash new password
        hashed_password = hash_string(new_password)

        # Update user's password
        update_user_password(user['name'], hashed_password)

        # Delete the used token
        delete_reset_token(token)

        # Notify moderation channel
        notify_password_reset_complete(user['name'], email)

        flash('Your password has been reset successfully. You can now log in.', FLASH_SUCCESS)
        return redirect('/login')

    except ErrNoResult:
        flash('This password reset link is invalid or has expired.', FLASH_ERROR)
        return redirect('/forgot-password')
    except Exception as e:
        print(f"Error resetting password: {e}")
        flash('An error occurred while resetting your password. Please try again.', FLASH_ERROR)
        return render_template('password_reset/reset.html', token=token)
