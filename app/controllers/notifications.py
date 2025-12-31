"""
Notifications controller - User notifications.
"""

from datetime import datetime
from flask import Blueprint, render_template, request, session
from app.models.notification import notifications_by_user, notification_remove, notification_mark_seen_single
from app.controllers.decorators import login_required

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/notifications', methods=['GET'])
@login_required
def notifications_get():
    """Display user notifications."""
    username = session.get('name')

    try:
        notifs = notifications_by_user(username)
    except Exception as e:
        print(f"Error getting notifications: {e}")
        notifs = []

    # Start time for comparison (Unix epoch)
    start_time = datetime(1970, 1, 1)

    return render_template('notifs/notifs.html',
                           notifs=notifs,
                           startTime=start_time)


@notifications_bp.route('/notifications/mark-seen', methods=['POST'])
@login_required
def notifications_mark_seen():
    """Mark a single notification as seen."""
    username = session.get('name')
    hexid = request.form.get('hexid', '')

    if not hexid:
        return '', 400

    try:
        notification_mark_seen_single(username, hexid)
        return '', 200
    except Exception as e:
        print(f"Error marking notification as seen: {e}")
        return '', 500


@notifications_bp.route('/notifications/delete', methods=['POST'])
@login_required
def notifications_delete():
    """Delete a notification."""
    username = session.get('name')
    hexid = request.form.get('hexid', '')

    if not hexid:
        return '', 400

    try:
        notification_remove(username, hexid)
        return '', 200
    except Exception as e:
        print(f"Error deleting notification: {e}")
        return '', 500
