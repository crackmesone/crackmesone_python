"""
Comment controller - Posting comments.
"""

from flask import Blueprint, request, redirect, flash, session
import bleach
from app.models.comment import comment_create
from app.models.crackme import crackme_by_hexid, crackme_increment_comments
from app.models.notification import notification_add
from app.models.errors import ErrNoResult
from app.services.recaptcha import verify as verify_recaptcha
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, validate_required
from app.controllers.decorators import login_required

comment_bp = Blueprint('comment', __name__)


@comment_bp.route('/comment/<hexid>', methods=['POST'])
@login_required
def leave_comment(hexid):
    """Post a comment on a crackme."""
    username = session.get('name')

    # Validate required fields
    is_valid, missing = validate_required(request.form, ['comment'])
    if not is_valid:
        flash(f'Field missing: {missing}', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    # Validate reCAPTCHA
    if not verify_recaptcha(request):
        flash('reCAPTCHA invalid!', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    comment_text = bleach.clean(request.form.get('comment', ''))

    # Create comment
    try:
        comment_create(comment_text, username, hexid)
    except Exception as e:
        print(f"Error creating comment: {e}")
        flash('Comment creation failed. Please try again later.', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    # Increment comment count
    try:
        crackme_increment_comments(hexid)
    except Exception as e:
        print(f"Failed to increment comment count: {e}")

    # Send notification to crackme author
    try:
        crackme = crackme_by_hexid(hexid)
        if crackme.get('author') != username:
            notification_add(
                crackme['author'],
                f"New comment on your crackme '{crackme['name']}' by: {username}"
            )
    except Exception as e:
        print(f"Notification error: {e}")

    flash('Comment uploaded!', FLASH_SUCCESS)
    return redirect(f'/crackme/{hexid}')
