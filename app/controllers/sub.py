"""
Subs controller - Subs page.
"""

from flask import Blueprint, render_template, request, session, abort
from app.controllers.decorators import login_required
from app.models.user import user_by_name
from app.models.subscription import user_subscribe_to, user_unsubscribe_to, get_user_subs

sub_bp = Blueprint('sub', __name__)

@sub_bp.route('/subscriptions', methods=["GET"])
@login_required
def subscriptions():
    """Display the People user has subscribed to."""
    subscribed_users = get_user_subs(session.get('name', None))
    print(subscribed_users)
    return render_template('sub/subscriptions.html', subscribed_users=subscribed_users)

@sub_bp.route("/subscriptions/subscribe", methods=["POST"])
#@limit("20 per min") # enable rate limit if needed
@login_required
def subscribe():
    name = request.form.get('to')
    user = user_by_name(name).get('name')
    current_user = session.get('name', None)
    if not current_user or not user:
        abort(403)
    try:
        user_subscribe_to(current_user, user)
    except Exception as e:
        abort(500)
    
    return {"status": "ok"}

@sub_bp.route("/subscriptions/unsubscribe", methods=["POST"])
#@limit("20 per min") # enable rate limit if needed
@login_required
def unsubscribe():
    name = request.form.get('to')
    user = user_by_name(name).get('name')
    current_user = session.get('name', None)
    if not current_user or not user:
        abort(403)
    try:
        user_unsubscribe_to(current_user, user)
    except Exception as e:
        abort(500)
    
    return {"status": "ok"}