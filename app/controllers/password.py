"""
Password controller - Change password.
"""

from flask import Blueprint, render_template, request, session
from app.models.user import user_by_name, update_user_password
from app.services.passhash import hash_string, match_string
from app.services.limiter import limit
from app.controllers.decorators import login_required

password_bp = Blueprint('password', __name__)


@password_bp.route('/change-password', methods=['GET'])
@login_required
def change_password_get():
    """Display the change password form."""
    return render_template('user/change-password.html')


@password_bp.route('/change-password', methods=['POST'])
@login_required
@limit("5 per hour")
def change_password_post():
    """Handle password change."""
    username = session.get('name')

    if not username:
        return 'User not logged in or session invalid', 401

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    new_password_verify = request.form.get('new_password_verify', '')

    # Validate new passwords
    if not new_password or not new_password_verify:
        return 'New password fields cannot be empty', 400

    if new_password != new_password_verify:
        return 'Passwords do not match', 400

    if len(new_password) < 8:
        return 'New password must be at least 8 characters long', 400

    # Fetch user and verify current password
    try:
        user = user_by_name(username)
    except Exception as e:
        print(f"Error: User not found: {e}")
        return 'User not found', 400

    if not match_string(user['password'], current_password):
        return 'Current password is incorrect', 401

    # Hash and update the new password
    try:
        hashed_new_password = hash_string(new_password)
    except Exception as e:
        print(f"Error hashing new password: {e}")
        return 'Could not hash new password', 500

    try:
        update_user_password(username, hashed_new_password)
    except Exception as e:
        print(f"Error updating user password: {e}")
        return 'Could not update password', 500

    return 'Password has been successfully updated', 200
