"""
Account settings controller - change username and email.

Usernames and emails are denormalized across many collections, so both changes
route through dedicated model helpers (``user_rename`` / ``user_change_email``)
that cascade the update. A change is only applied after the new value is proven
free (not used by any other account, as either a name or an email) and the
current password is confirmed.
"""

from flask import Blueprint, render_template, request, redirect, flash, session
from app.models.user import (
    user_by_name, user_by_mail, user_rename, user_change_email
)
from app.models.errors import ErrNoResult
from app.services.passhash import match_string
from app.services.limiter import limit
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, authorized_chars_only
from app.controllers.decorators import login_required

account_settings_bp = Blueprint('account_settings', __name__)


def _name_available(candidate, current_id):
    """True if ``candidate`` is free to use as a username.

    Mirrors registration's cross-checks: it must not be another user's name and
    must not be any user's email. A match on the current user's own account
    (e.g. a case-only change) is allowed.
    """
    try:
        existing = user_by_name(candidate)
        if existing.get('_id') != current_id:
            return False
    except ErrNoResult:
        pass

    try:
        user_by_mail(candidate)
        return False  # Taken as some user's email.
    except ErrNoResult:
        pass

    return True


def _email_available(candidate, current_id):
    """True if ``candidate`` is free to use as an email.

    Must not be another user's email and must not be any user's username.
    """
    try:
        existing = user_by_mail(candidate)
        if existing.get('_id') != current_id:
            return False
    except ErrNoResult:
        pass

    try:
        user_by_name(candidate)
        return False  # Taken as some user's username.
    except ErrNoResult:
        pass

    return True


@account_settings_bp.route('/settings', methods=['GET'])
@login_required
def settings_get():
    """Display the account settings page."""
    username = session.get('name')
    try:
        user = user_by_name(username)
    except ErrNoResult:
        # Session references a user that no longer exists; force re-login.
        return redirect('/logout')

    return render_template('user/settings.html',
                           current_username=user['name'],
                           current_email=user['email'])


@account_settings_bp.route('/settings/username', methods=['POST'])
@login_required
@limit("5 per hour", key_func=lambda: session.get('name'))
def change_username_post():
    """Handle a username change, cascading it across all references."""
    username = session.get('name')
    new_name = request.form.get('name', '').strip()
    password = request.form.get('current_password', '')

    try:
        user = user_by_name(username)
    except ErrNoResult:
        return redirect('/logout')

    if not new_name:
        flash('Username cannot be empty.', FLASH_ERROR)
        return redirect('/settings')

    if not authorized_chars_only(new_name):
        flash('Username contains disallowed characters.', FLASH_ERROR)
        return redirect('/settings')

    if not match_string(user['password'], password):
        flash('Current password is incorrect.', FLASH_ERROR)
        return redirect('/settings')

    if new_name == user['name']:
        flash('That is already your username.', FLASH_ERROR)
        return redirect('/settings')

    try:
        available = _name_available(new_name, user.get('_id'))
    except Exception as e:
        print(f"Username availability check error: {e}")
        flash('An error occurred. Please try again later.', FLASH_ERROR)
        return redirect('/settings')

    if not available:
        flash(f'The username "{new_name}" is not available.', FLASH_ERROR)
        return redirect('/settings')

    try:
        user_rename(user['name'], new_name)
    except Exception as e:
        print(f"Username change error: {e}")
        flash('An error occurred. Please try again later.', FLASH_ERROR)
        return redirect('/settings')

    # Keep the session in step with the renamed account.
    session['name'] = new_name
    flash('Username updated successfully!', FLASH_SUCCESS)
    return redirect('/settings')


@account_settings_bp.route('/settings/email', methods=['POST'])
@login_required
@limit("5 per hour", key_func=lambda: session.get('name'))
def change_email_post():
    """Handle an email change, refreshing denormalized copies."""
    username = session.get('name')
    new_email = request.form.get('email', '').strip().lower()
    password = request.form.get('current_password', '')

    try:
        user = user_by_name(username)
    except ErrNoResult:
        return redirect('/logout')

    if not new_email:
        flash('Email cannot be empty.', FLASH_ERROR)
        return redirect('/settings')

    if not authorized_chars_only(new_email):
        flash('Email contains disallowed characters.', FLASH_ERROR)
        return redirect('/settings')

    if not match_string(user['password'], password):
        flash('Current password is incorrect.', FLASH_ERROR)
        return redirect('/settings')

    if new_email == (user.get('email') or '').lower():
        flash('That is already your email.', FLASH_ERROR)
        return redirect('/settings')

    try:
        available = _email_available(new_email, user.get('_id'))
    except Exception as e:
        print(f"Email availability check error: {e}")
        flash('An error occurred. Please try again later.', FLASH_ERROR)
        return redirect('/settings')

    if not available:
        flash(f'The email "{new_email}" is not available.', FLASH_ERROR)
        return redirect('/settings')

    try:
        user_change_email(user['name'], new_email)
    except Exception as e:
        print(f"Email change error: {e}")
        flash('An error occurred. Please try again later.', FLASH_ERROR)
        return redirect('/settings')

    session['email'] = new_email
    flash('Email updated successfully!', FLASH_SUCCESS)
    return redirect('/settings')
