"""
Account deletion controller - let a logged-in user request deletion of their
own account. The request lands in a reviewer queue; an admin approves it, which
runs the actual deletion and emails the user.
"""

from flask import Blueprint, render_template, request, session
from app.models.user import user_by_name
from app.models.account_deletion_request import (
    account_deletion_request_create,
    pending_account_deletion_request_by_user,
)
from app.services.passhash import match_string
from app.services.limiter import limit
from app.controllers.decorators import login_required

account_deletion_bp = Blueprint('account_deletion', __name__)


@account_deletion_bp.route('/delete-account', methods=['GET'])
@login_required
def delete_account_get():
    """Display the account deletion request form."""
    username = session.get('name')

    already_pending = False
    try:
        already_pending = bool(
            pending_account_deletion_request_by_user(username)
        )
    except Exception as e:
        print(f"Error checking pending deletion request: {e}")

    return render_template('user/delete-account.html',
                           already_pending=already_pending,
                           message=None,
                           submitted=False)


@account_deletion_bp.route('/delete-account', methods=['POST'])
@login_required
@limit("5 per hour", key_func=lambda: session.get('name'))
def delete_account_post():
    """Create a pending account deletion request for the current user."""
    username = session.get('name')
    if not username:
        return 'User not logged in or session invalid', 401

    password = request.form.get('password', '')
    note = request.form.get('note', '').strip()

    try:
        user = user_by_name(username)
    except Exception as e:
        print(f"Error: User not found: {e}")
        return render_template('user/delete-account.html',
                               already_pending=False,
                               message="User not found.",
                               submitted=False)

    # Require the current password to confirm the request. This prevents an
    # unattended/hijacked session from deleting the account.
    if not password or not match_string(user['password'], password):
        return render_template('user/delete-account.html',
                               already_pending=False,
                               message="Password is incorrect.",
                               submitted=False)

    # Don't stack duplicate pending requests for the same user.
    try:
        if pending_account_deletion_request_by_user(username):
            return render_template('user/delete-account.html',
                                   already_pending=True,
                                   message=None,
                                   submitted=False)
    except Exception as e:
        print(f"Error checking pending deletion request: {e}")

    try:
        account_deletion_request_create(username, user.get('email', ''), note)
    except Exception as e:
        print(f"Error creating deletion request: {e}")
        return render_template('user/delete-account.html',
                               already_pending=False,
                               message="Could not submit your request. Please try again later.",
                               submitted=False)

    return render_template('user/delete-account.html',
                           already_pending=True,
                           message=None,
                           submitted=True)
