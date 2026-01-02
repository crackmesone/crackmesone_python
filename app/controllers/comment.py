"""
Comment controller - Posting comments.
"""

import re
from html import escape as html_escape
from flask import Blueprint, request, redirect, flash, session
import bleach
from app.models.comment import comment_create, comment_by_id, comment_set_spoiler, get_thread_participants
from app.models.solution import get_solution_authors
from app.models.crackme import crackme_by_hexid, crackme_increment_comments
from app.models.notification import notification_add
from app.models.errors import ErrNoResult
from app.services.recaptcha import verify as verify_recaptcha
from app.services.limiter import limit
from app.services.discord import notify_new_comment, notify_spoiler_toggle
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, validate_required
from app.controllers.decorators import login_required

# Regex to match @mentions (only after whitespace or at start of text)
# Valid username characters: alphanumeric, _-@.+
MENTION_PATTERN = re.compile(r'(?:^|(?<=\s))@([a-zA-Z0-9_\-@.+]+)', re.MULTILINE)


def parse_mentions(text):
    """Extract @mentioned usernames from text.

    Args:
        text: Comment text to parse

    Returns:
        Set of mentioned usernames (without @ symbol)
    """
    matches = MENTION_PATTERN.findall(text)
    return set(matches)

comment_bp = Blueprint('comment', __name__)


@comment_bp.route('/comment/<hexid>', methods=['POST'])
@login_required
@limit("30 per hour", key_func=lambda: session.get('name'))
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
    is_spoiler = request.form.get('spoiler') == 'on'

    # Create comment
    try:
        comment_create(comment_text, username, hexid, spoiler=is_spoiler)
    except Exception as e:
        print(f"Error creating comment: {e}")
        flash('Comment creation failed. Please try again later.', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    # Increment comment count
    try:
        crackme_increment_comments(hexid)
    except Exception as e:
        print(f"Failed to increment comment count: {e}")

    # Send notification to crackme author and handle @mentions
    try:
        crackme = crackme_by_hexid(hexid)
        crackme_author = crackme.get('author')
        crackme_name = crackme['name']

        # Notify crackme author (if not the commenter)
        if crackme_author != username:
            notification_add(
                crackme_author,
                f"New comment on your crackme '<a href=\"/crackme/{hexid}\">{html_escape(crackme_name)}</a>' by: <a href=\"/user/{html_escape(username)}\">{html_escape(username)}</a>"
            )

        # Handle @mentions
        mentioned_users = parse_mentions(comment_text)
        if mentioned_users:
            # Get valid mention targets: crackme author + thread participants + solution authors
            thread_participants = get_thread_participants(hexid)
            solution_authors = get_solution_authors(hexid)
            valid_targets = thread_participants | solution_authors | {crackme_author}

            # Send notifications to valid mentioned users
            for mentioned_user in mentioned_users:
                # Skip if user mentioned themselves
                if mentioned_user == username:
                    continue
                # Skip if already notified as crackme author
                if mentioned_user == crackme_author:
                    continue
                # Only notify if user is a valid target
                if mentioned_user in valid_targets:
                    notification_add(
                        mentioned_user,
                        f"You were mentioned by <a href=\"/user/{html_escape(username)}\">{html_escape(username)}</a> in a comment on '<a href=\"/crackme/{hexid}\">{html_escape(crackme_name)}</a>'"
                    )

        # Send Discord moderation notification
        notify_new_comment(username, crackme_name, hexid, comment_text)
    except Exception as e:
        print(f"Notification error: {e}")

    flash('Comment uploaded!', FLASH_SUCCESS)
    return redirect(f'/crackme/{hexid}')


@comment_bp.route('/comment/<comment_id>/spoiler', methods=['POST'])
@login_required
def toggle_spoiler(comment_id):
    """Toggle spoiler status on a comment.

    Permissions:
    - Crackme author: can mark and unmark any comment on their crackme
    - Comment author: can only mark their own comment (cannot unmark)
    """
    username = session.get('name')

    # Get the comment
    try:
        comment = comment_by_id(comment_id)
    except ErrNoResult:
        flash('Comment not found.', FLASH_ERROR)
        return redirect('/')

    crackme_hexid = comment.get('crackmehexid')
    comment_author = comment.get('author')
    current_spoiler = comment.get('spoiler', False)

    # Get the crackme
    try:
        crackme = crackme_by_hexid(crackme_hexid)
    except ErrNoResult:
        flash('Crackme not found.', FLASH_ERROR)
        return redirect('/')

    is_crackme_author = crackme.get('author') == username
    is_comment_author = comment_author == username

    # Check permissions
    if not is_crackme_author and not is_comment_author:
        flash('You can only mark comments as spoilers on your own crackmes or your own comments.', FLASH_ERROR)
        return redirect(f'/crackme/{crackme_hexid}')

    # Comment author can only mark, not unmark (unless they're also crackme author)
    if is_comment_author and not is_crackme_author and current_spoiler:
        flash('You cannot remove the spoiler mark from your own comment. Contact the crackme author.', FLASH_ERROR)
        return redirect(f'/crackme/{crackme_hexid}')

    # Toggle spoiler status
    new_spoiler = not current_spoiler

    try:
        comment_set_spoiler(comment_id, new_spoiler)
    except Exception as e:
        print(f"Error toggling spoiler: {e}")
        flash('Failed to update spoiler status.', FLASH_ERROR)
        return redirect(f'/crackme/{crackme_hexid}')

    # Send Discord moderation notification
    try:
        notify_spoiler_toggle(
            username,
            crackme['name'],
            crackme_hexid,
            comment.get('author', 'Unknown'),
            new_spoiler
        )
    except Exception as e:
        print(f"Discord notification error: {e}")

    if new_spoiler:
        flash('Comment marked as spoiler.', FLASH_SUCCESS)
    else:
        flash('Spoiler marking removed.', FLASH_SUCCESS)

    return redirect(f'/crackme/{crackme_hexid}')
