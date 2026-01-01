"""
Reviewer Tool Routes - Flask Blueprint for managing crackme submissions.
"""

from flask import Blueprint, render_template, request, redirect, url_for, abort, send_file, session
from functools import wraps
import datetime
from datetime import timezone
import hashlib
import os
import json
import re
import requests
from subprocess import call
from bson.objectid import ObjectId
import shutil
import random
import string
import bcrypt
from review.logger import log_reviewer_operation

# Deduce CRACKMESONE_DIR from script location (parent of review/ folder)
CRACKMESONE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

reviewer_bp = Blueprint('reviewer', __name__,
                        template_folder='templates',
                        url_prefix='/review')

# Configuration - will be set from main app config
PASSWORD_SALT = None
DISCORD_WEBHOOK_PUBLIC = None  # For approved crackmes/solutions (public notifications)
g_crackmesone_db = None
users = {}
USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

# Session keys for reviewer authentication
REVIEWER_SESSION_KEY = '_reviewer_user'
REVIEWER_ADMIN_KEY = '_reviewer_is_admin'


def init_reviewer(app):
    """Initialize reviewer module with app configuration."""
    global PASSWORD_SALT, DISCORD_WEBHOOK_PUBLIC
    global g_crackmesone_db, users

    PASSWORD_SALT = app.config.get('REVIEWER_PASSWORD_SALT', os.getenv('REVIEWER_PASSWORD_SALT'))

    # Get Discord public webhook for approved item notifications
    discord_config = app.config.get('DISCORD_CONFIG', {})
    if discord_config.get('Enabled', False):
        DISCORD_WEBHOOK_PUBLIC = discord_config.get('WebhookPublic', '')

    # Use the main app's MongoDB connection
    from app.services.database import get_db
    g_crackmesone_db = get_db()

    # Load reviewer users from separate credentials file
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            users.update(json.load(f))


def save_users():
    """Save users to the users.json file."""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)


def hash_string(input_string):
    """Hash a string using SHA256."""
    sha256_hash = hashlib.sha256()
    sha256_hash.update(input_string.encode('utf-8'))
    return sha256_hash.hexdigest()


def generate_csrf_token():
    """Generate a CSRF token for forms."""
    from flask import session
    if '_reviewer_csrf_token' not in session:
        session['_reviewer_csrf_token'] = hashlib.sha256(os.urandom(32)).hexdigest()
    return session['_reviewer_csrf_token']


def validate_csrf_token():
    """Validate CSRF token from form submission."""
    from flask import session
    token = request.form.get('csrf_token')
    expected = session.get('_reviewer_csrf_token')
    if not token or not expected or token != expected:
        abort(403, description="CSRF token validation failed")
    return True


# Make csrf_token available in templates
@reviewer_bp.context_processor
def inject_csrf_token():
    return {'csrf_token': generate_csrf_token}


# Decorator to protect dashboard route
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        username = session.get(REVIEWER_SESSION_KEY)

        if not username:
            return redirect(url_for('reviewer.login'))

        # Verify user still exists in users.json
        if username not in users:
            session.pop(REVIEWER_SESSION_KEY, None)
            session.pop(REVIEWER_ADMIN_KEY, None)
            return redirect(url_for('reviewer.login'))

        # Use current admin status from users.json
        user_data = {
            'username': username,
            'is_admin': users[username].get('is_admin', False)
        }

        return f(user_data, *args, **kwargs)
    return decorated


# Decorator to protect admin-only routes
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        username = session.get(REVIEWER_SESSION_KEY)

        if not username:
            return redirect(url_for('reviewer.login'))

        # Verify user still exists in users.json
        if username not in users:
            session.pop(REVIEWER_SESSION_KEY, None)
            session.pop(REVIEWER_ADMIN_KEY, None)
            return redirect(url_for('reviewer.login'))

        # Use current admin status from users.json
        current_is_admin = users[username].get('is_admin', False)

        if not current_is_admin:
            abort(403)  # Forbidden - not an admin

        user_data = {
            'username': username,
            'is_admin': current_is_admin
        }

        return f(user_data, *args, **kwargs)
    return decorated


@reviewer_bp.route('/')
def index():
    return redirect(url_for('reviewer.login'))


@reviewer_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, redirect to dashboard
    if session.get(REVIEWER_SESSION_KEY):
        return redirect(url_for('reviewer.dashboard'))

    if request.method == 'POST':
        validate_csrf_token()
        username = request.form.get('username')
        password = request.form.get('password')

        if username in users and users[username]["password_hash"] == hash_string(password + PASSWORD_SALT):
            # Set session variables
            session[REVIEWER_SESSION_KEY] = username
            session[REVIEWER_ADMIN_KEY] = users[username].get("is_admin", False)
            return redirect(url_for('reviewer.dashboard'))

        return render_template('reviewer/login.html', error='Invalid credentials')

    return render_template('reviewer/login.html')


@reviewer_bp.route('/dashboard')
@token_required
def dashboard(current_user):
    solution_dir = os.path.join(CRACKMESONE_DIR, "tmp/solution")
    crackme_dir = os.path.join(CRACKMESONE_DIR, "tmp/crackme")

    solution_cnt = 0
    crackme_cnt = 0

    if os.path.exists(solution_dir):
        solution_cnt = sum(1 for f in os.listdir(solution_dir) if len(f.split("+++")) == 3)
    if os.path.exists(crackme_dir):
        crackme_cnt = sum(1 for f in os.listdir(crackme_dir) if len(f.split("+++")) == 3)

    return render_template('reviewer/dashboard.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           solution_cnt=solution_cnt,
                           crackme_cnt=crackme_cnt)


@reviewer_bp.route('/delcomment', methods=['GET', 'POST'])
@admin_required
def delcomment(current_user):
    """Delete comment - FIXED: only accepts deletion via POST, not GET."""
    crackme_uuid = None
    comment_uuid = None
    error = None

    if request.method == 'POST':
        validate_csrf_token()
        crackme_uuid = request.form.get('crackme_uuid')
        comment_uuid = request.form.get('comment_uuid')
        action = request.form.get('action')

        # Only perform deletion when action is 'delete'
        if action == 'delete' and comment_uuid:
            collection = g_crackmesone_db.comment

            # Get the comment to find its crackme before deleting
            comment = collection.find_one({"_id": ObjectId(comment_uuid)})
            comment_crackme_hexid = comment.get("crackmehexid") if comment else None

            result = collection.delete_one({"_id": ObjectId(comment_uuid)})

            # Decrement the comment counter for the crackme
            if result.deleted_count > 0 and comment_crackme_hexid:
                try:
                    crackme_collection = g_crackmesone_db.crackme
                    crackme_collection.update_one(
                        {"_id": ObjectId(comment_crackme_hexid)},
                        {"$inc": {"nbcomments": -1}}
                    )
                except Exception as e:
                    print(f"Error decrementing comment count for crackme {comment_crackme_hexid}: {e}")

            # Log the operation
            operation_success = bool(result.deleted_count)
            log_reviewer_operation(
                "delete_comment",
                current_user['username'],
                {
                    "comment_uuid": comment_uuid,
                    "crackme_uuid": crackme_uuid,
                    "deleted_count": result.deleted_count
                },
                operation_success
            )

            if not result.deleted_count:
                error = "Failed to delete comment"

        # Load comments action
        elif action == 'load' and crackme_uuid:
            pass  # Just fall through to display comments

    elif request.method == 'GET':
        # GET only loads comments for display, never performs deletion
        crackme_uuid = request.args.get("crackme_uuid")

    # Load comments for display
    comments = None
    if crackme_uuid:
        if ObjectId.is_valid(crackme_uuid):
            collection = g_crackmesone_db.crackme
            result = collection.find_one({"_id": ObjectId(crackme_uuid)})
            if result:
                comments = []
                collection = g_crackmesone_db.comment
                objects = collection.find({'crackmehexid': crackme_uuid})
                for obj in objects:
                    comments.append({
                        'comment_uuid': str(obj.get("_id")),
                        'author': obj["author"],
                        'content': obj["info"]
                    })
            else:
                error = "Crackme not found"
        else:
            error = "Wrong crackme UUID"

    return render_template('reviewer/delcomment.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           comments=comments,
                           crackme_uuid=crackme_uuid,
                           error=error)


@reviewer_bp.route('/deletesolution', methods=['GET', 'POST'])
@admin_required
def deletesolution(current_user):
    """Delete an already approved solution (admin only)."""
    message = None
    if request.method == 'POST':
        validate_csrf_token()
        solution_uuid = request.form.get('solution_uuid')
        message = delete_solution(solution_uuid)

        log_reviewer_operation(
            "delete_solution_admin",
            current_user['username'],
            {
                "solution_uuid": solution_uuid,
                "result": message
            },
            "deleted" in message.lower()
        )

    return render_template('reviewer/delsolution.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           message=message)


@reviewer_bp.route('/deletecrackme', methods=['GET', 'POST'])
@admin_required
def deletecrackme(current_user):
    """Delete an already approved crackme (admin only)."""
    message = None
    if request.method == 'POST':
        validate_csrf_token()
        crackme_uuid = request.form.get('crackme_uuid')
        message = delete_crackme(crackme_uuid)

        log_reviewer_operation(
            "delete_crackme_admin",
            current_user['username'],
            {
                "crackme_uuid": crackme_uuid,
                "result": message
            },
            "deleted" in message.lower()
        )

    return render_template('reviewer/delcrackme.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           message=message)


@reviewer_bp.route('/reviewsolution')
@token_required
def reviewsolution(current_user):
    solutions, error = get_list_review_solution()
    # Get message from query params (for redirect after approve/reject)
    message = request.args.get('message') or error
    return render_template('reviewer/reviewsolution.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           solutions=solutions,
                           message=message)


@reviewer_bp.route('/viewsolution')
@token_required
def viewsolution(current_user):
    solution_uuid = request.args.get("solution_uuid")
    if solution_uuid is None:
        return redirect(url_for('reviewer.dashboard'))

    solution, error = get_solution_by_uuid(solution_uuid)
    if error is not None:
        return error
    return render_template('reviewer/viewsolution.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           solution=solution)


@reviewer_bp.route('/reviewcrackme')
@token_required
def reviewcrackme(current_user):
    crackmes, error = get_list_review_crackme()
    # Get message from query params (for redirect after approve/reject)
    message = request.args.get('message') or error
    return render_template('reviewer/reviewcrackme.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           crackmes=crackmes,
                           message=message)


@reviewer_bp.route('/viewcrackme')
@token_required
def viewcrackme(current_user):
    crackme_uuid = request.args.get("crackme_uuid")
    if crackme_uuid is None:
        return redirect(url_for('reviewer.dashboard'))

    crackme, error = get_crackme_by_uuid(crackme_uuid)
    if error is not None:
        return error

    return render_template('reviewer/viewcrackme.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           crackme=crackme)


@reviewer_bp.route('/downloadreview')
@token_required
def downloadreview(current_user):
    download_type = request.args.get("type")
    uuid = request.args.get("uuid")

    download_path = ""
    if download_type == "solution":
        download_path = os.path.join(CRACKMESONE_DIR, "tmp/solution")
    elif download_type == "crackme":
        download_path = os.path.join(CRACKMESONE_DIR, "tmp/crackme")
    else:
        abort(404)

    if not os.path.exists(download_path):
        abort(404)

    files = os.listdir(download_path)

    for file in files:
        parts = file.split("+++")
        if len(parts) != 3:
            continue
        author, file_uuid, filename = parts
        if file_uuid == uuid:
            return send_file(os.path.join(download_path, file), as_attachment=True)

    abort(404)


@reviewer_bp.route('/rejectsolution', methods=['POST'])
@token_required
def rejectsolution(current_user):
    """Reject a pending solution submission (accessible by all reviewers)."""
    validate_csrf_token()
    solution_uuid = request.form.get('uuid')
    reject_reason = request.form.get('reject_reason')

    solution_dir = os.path.join(CRACKMESONE_DIR, "tmp/solution")
    solution_file = ""

    if os.path.exists(solution_dir):
        for file in os.listdir(solution_dir):
            parts = file.split("+++")
            if len(parts) != 3:
                continue
            author, file_uuid, filename = parts
            if file_uuid == solution_uuid:
                solution_file = file
                break

    if solution_file == "":
        log_reviewer_operation(
            "reject_solution",
            current_user['username'],
            {
                "solution_uuid": solution_uuid,
                "error": "Solution file not found"
            },
            False
        )
        return redirect(url_for('reviewer.reviewsolution', message="Solution file not found", success='0'))

    success, message = reject_pending_solution(solution_file, reject_reason)

    log_reviewer_operation(
        "reject_solution",
        current_user['username'],
        {
            "solution_uuid": solution_uuid,
            "solution_file": solution_file,
            "reject_reason": reject_reason,
            "result": message
        },
        success
    )

    return redirect(url_for('reviewer.reviewsolution', message=message, success='1' if success else '0'))


@reviewer_bp.route('/approvesolution', methods=['POST'])
@token_required
def approvesolution(current_user):
    """Approve a pending solution submission (accessible by all reviewers)."""
    validate_csrf_token()
    solution_uuid = request.form.get('uuid')

    solution_dir = os.path.join(CRACKMESONE_DIR, "tmp/solution")
    solution_file = ""

    if os.path.exists(solution_dir):
        for file in os.listdir(solution_dir):
            parts = file.split("+++")
            if len(parts) != 3:
                continue
            author, file_uuid, filename = parts
            if file_uuid == solution_uuid:
                solution_file = file
                break

    if solution_file == "":
        log_reviewer_operation(
            "approve_solution",
            current_user['username'],
            {
                "solution_uuid": solution_uuid,
                "error": "Solution file not found"
            },
            False
        )
        return redirect(url_for('reviewer.reviewsolution', message="Solution file not found", success='0'))

    success, message = approve_pending_solution(solution_file)

    log_reviewer_operation(
        "approve_solution",
        current_user['username'],
        {
            "solution_uuid": solution_uuid,
            "solution_file": solution_file,
            "result": message
        },
        success
    )

    if success:
        # Send Discord notification and increment solution counter
        solution, error = get_solution_by_uuid(solution_uuid)
        if solution:
            post_discord_notification_solution(
                solution["crackme_name"],
                solution["crackme_uuid"],
                solution_uuid,
                solution["solution_author"]
            )

            # Increment the solution counter for the crackme
            try:
                crackme_collection = g_crackmesone_db.crackme
                crackme_id = ObjectId(solution["crackme_uuid"])
                crackme_collection.update_one(
                    {"_id": crackme_id},
                    {"$inc": {"nbsolutions": 1}}
                )
            except Exception as e:
                print(f"Error incrementing solution count for crackme {solution['crackme_uuid']}: {e}")

    return redirect(url_for('reviewer.reviewsolution', message=message, success='1' if success else '0'))


@reviewer_bp.route('/rejectcrackme', methods=['POST'])
@token_required
def rejectcrackme(current_user):
    """Reject a pending crackme submission (accessible by all reviewers)."""
    validate_csrf_token()
    crackme_uuid = request.form.get('uuid')
    reject_reason = request.form.get('reject_reason')

    crackme_dir = os.path.join(CRACKMESONE_DIR, "tmp/crackme")
    crackme_file = ""

    if os.path.exists(crackme_dir):
        for file in os.listdir(crackme_dir):
            parts = file.split("+++")
            if len(parts) != 3:
                continue
            author, file_uuid, filename = parts
            if file_uuid == crackme_uuid:
                crackme_file = file
                break

    if crackme_file == "":
        log_reviewer_operation(
            "reject_crackme",
            current_user['username'],
            {
                "crackme_uuid": crackme_uuid,
                "error": "Crackme file not found"
            },
            False
        )
        return redirect(url_for('reviewer.reviewcrackme', message="Crackme file not found", success='0'))

    success, message = reject_pending_crackme(crackme_file, reject_reason)

    log_reviewer_operation(
        "reject_crackme",
        current_user['username'],
        {
            "crackme_uuid": crackme_uuid,
            "crackme_file": crackme_file,
            "reject_reason": reject_reason,
            "result": message
        },
        success
    )

    return redirect(url_for('reviewer.reviewcrackme', message=message, success='1' if success else '0'))


@reviewer_bp.route('/approvecrackme', methods=['POST'])
@token_required
def approvecrackme(current_user):
    """Approve a pending crackme submission (accessible by all reviewers)."""
    validate_csrf_token()
    crackme_uuid = request.form.get('uuid')
    crackme_dir = os.path.join(CRACKMESONE_DIR, "tmp/crackme")
    crackme_file = ""

    if os.path.exists(crackme_dir):
        for file in os.listdir(crackme_dir):
            parts = file.split("+++")
            if len(parts) != 3:
                continue
            author, file_uuid, filename = parts
            if file_uuid == crackme_uuid:
                crackme_file = file
                break

    if crackme_file == "":
        log_reviewer_operation(
            "approve_crackme",
            current_user['username'],
            {
                "crackme_uuid": crackme_uuid,
                "error": "Crackme file not found"
            },
            False
        )
        return redirect(url_for('reviewer.reviewcrackme', message="Crackme file not found", success='0'))

    success, message = approve_pending_crackme(crackme_file)

    log_reviewer_operation(
        "approve_crackme",
        current_user['username'],
        {
            "crackme_uuid": crackme_uuid,
            "crackme_file": crackme_file,
            "result": message
        },
        success
    )

    if success:
        # Send Discord notification
        crackme, error = get_crackme_by_uuid(crackme_uuid)
        if crackme:
            post_discord_notification_crackme(crackme["name"], crackme_uuid, crackme["author"])

    return redirect(url_for('reviewer.reviewcrackme', message=message, success='1' if success else '0'))


@reviewer_bp.route('/logout')
def logout():
    session.pop(REVIEWER_SESSION_KEY, None)
    session.pop(REVIEWER_ADMIN_KEY, None)
    return redirect(url_for('reviewer.login'))


@reviewer_bp.route('/resetuserpassword', methods=['GET', 'POST'])
@admin_required
def resetuserpassword(current_user):
    message = None
    if request.method == 'POST':
        validate_csrf_token()
        user_email = request.form.get('user_email')
        message = reset_user_password(user_email)

        log_reviewer_operation(
            "reset_user_password",
            current_user['username'],
            {
                "target_user_email": user_email,
                "result": "success" if "successful" in message.lower() else "failed"
            },
            "successful" in message.lower()
        )

    return render_template('reviewer/resetuserpassword.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           message=message)


@reviewer_bp.route('/lookupuser', methods=['GET', 'POST'])
@admin_required
def lookupuser(current_user):
    user_info = None
    message = None

    if request.method == 'POST':
        validate_csrf_token()
        search_query = request.form.get('search_query', '').strip()

        if search_query:
            user_collection = g_crackmesone_db.user

            # Escape regex special characters to prevent injection
            escaped_query = re.escape(search_query)

            # Try to find by email first (case-insensitive)
            user = user_collection.find_one({"email": {"$regex": f"^{escaped_query}$", "$options": "i"}})

            # If not found by email, try by username
            if not user:
                user = user_collection.find_one({"name": {"$regex": f"^{escaped_query}$", "$options": "i"}})

            if user:
                username = user.get("name")
                user_info = {
                    'username': username,
                    'email': user.get("email"),
                    'is_admin': user.get("is_admin", False),
                    'created_at': user.get("created_at", "Unknown"),
                    'crackmes_count': g_crackmesone_db.crackme.count_documents({"author": username}),
                    'solutions_count': g_crackmesone_db.solution.count_documents({"author": username}),
                    'comments_count': g_crackmesone_db.comment.count_documents({"author": username}),
                    'difficulty_ratings_count': g_crackmesone_db.rating_difficulty.count_documents({"author": username}),
                    'quality_ratings_count': g_crackmesone_db.rating_quality.count_documents({"author": username}),
                    'notifications_count': g_crackmesone_db.notifications.count_documents({"user": username})
                }

                log_reviewer_operation(
                    "lookup_user",
                    current_user['username'],
                    {"search_query": search_query, "found_user": username},
                    True
                )
            else:
                message = f"No user found with email or username: {search_query}"
                log_reviewer_operation(
                    "lookup_user",
                    current_user['username'],
                    {"search_query": search_query, "result": "not_found"},
                    False
                )
        else:
            message = "Please enter an email or username to search."

    return render_template('reviewer/lookupuser.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           user_info=user_info,
                           message=message)


@reviewer_bp.route('/managereviewers', methods=['GET', 'POST'])
@admin_required
def managereviewers(current_user):
    global users
    message = None

    if request.method == 'POST':
        validate_csrf_token()
        action = request.form.get('action')

        if action == 'add':
            new_username = request.form.get('new_username', '').strip()
            new_password = request.form.get('new_password', '').strip()
            is_admin = request.form.get('is_admin') == 'on'

            if not new_username or not new_password:
                message = "Error: Username and password are required."
            elif new_username in users:
                message = f"Error: Reviewer '{new_username}' already exists."
            else:
                password_hash = hash_string(new_password + PASSWORD_SALT)
                users[new_username] = {
                    "password_hash": password_hash,
                    "is_admin": is_admin
                }

                try:
                    save_users()
                    message = f"Success: Reviewer '{new_username}' added successfully."
                    log_reviewer_operation(
                        "add_reviewer",
                        current_user['username'],
                        {"new_reviewer": new_username, "is_admin": is_admin},
                        True
                    )
                except Exception as e:
                    message = f"Error saving to file: {str(e)}"

        elif action == 'delete':
            username_to_delete = request.form.get('username_to_delete')

            if not username_to_delete:
                message = "Error: No username specified for deletion."
            elif username_to_delete == current_user['username']:
                message = "Error: You cannot delete your own account."
            elif username_to_delete not in users:
                message = f"Error: Reviewer '{username_to_delete}' not found."
            else:
                deleted_user_info = users[username_to_delete]
                del users[username_to_delete]

                try:
                    save_users()
                    message = f"Success: Reviewer '{username_to_delete}' deleted successfully."
                    log_reviewer_operation(
                        "delete_reviewer",
                        current_user['username'],
                        {"deleted_reviewer": username_to_delete, "was_admin": deleted_user_info.get('is_admin', False)},
                        True
                    )
                except Exception as e:
                    users[username_to_delete] = deleted_user_info
                    message = f"Error saving to file: {str(e)}"

        elif action == 'toggle_admin':
            username_to_toggle = request.form.get('username_to_toggle')

            if not username_to_toggle:
                message = "Error: No username specified."
            elif username_to_toggle == current_user['username']:
                message = "Error: You cannot modify your own admin status."
            elif username_to_toggle not in users:
                message = f"Error: Reviewer '{username_to_toggle}' not found."
            else:
                old_status = users[username_to_toggle].get('is_admin', False)
                users[username_to_toggle]['is_admin'] = not old_status
                new_status = users[username_to_toggle]['is_admin']

                try:
                    save_users()
                    status_text = "admin" if new_status else "regular reviewer"
                    message = f"Success: '{username_to_toggle}' is now a {status_text}."
                    log_reviewer_operation(
                        "toggle_reviewer_admin",
                        current_user['username'],
                        {"target_reviewer": username_to_toggle, "old_status": old_status, "new_status": new_status},
                        True
                    )
                except Exception as e:
                    users[username_to_toggle]['is_admin'] = old_status
                    message = f"Error saving to file: {str(e)}"

        elif action == 'change_password':
            username_to_change = request.form.get('username_to_change')
            new_password = request.form.get('change_password', '').strip()

            if not username_to_change:
                message = "Error: No username specified."
            elif not new_password:
                message = "Error: New password cannot be empty."
            elif username_to_change not in users:
                message = f"Error: Reviewer '{username_to_change}' not found."
            else:
                password_hash = hash_string(new_password + PASSWORD_SALT)
                users[username_to_change]['password_hash'] = password_hash

                try:
                    save_users()
                    message = f"Success: Password changed for '{username_to_change}'."
                    log_reviewer_operation(
                        "change_reviewer_password",
                        current_user['username'],
                        {"target_reviewer": username_to_change},
                        True
                    )
                except Exception as e:
                    message = f"Error saving to file: {str(e)}"

    # Prepare reviewer list for display
    reviewers = []
    for username, info in users.items():
        reviewers.append({
            'username': username,
            'is_admin': info.get('is_admin', False),
            'is_current_user': username == current_user['username']
        })

    reviewers.sort(key=lambda x: x['username'])

    return render_template('reviewer/managereviewers.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           reviewers=reviewers,
                           message=message)


@reviewer_bp.route('/deleteuser', methods=['GET', 'POST'])
@admin_required
def deleteuser(current_user):
    message = None
    preview_data = None

    if request.method == 'POST':
        validate_csrf_token()
        action = request.form.get('action')
        user_email = request.form.get('user_email', '').strip()
        confirm_email = request.form.get('confirm_email', '').strip()

        if action == 'preview':
            if user_email and confirm_email:
                if user_email.lower() == confirm_email.lower():
                    preview_data, error = preview_user_deletion(user_email)
                    if error:
                        message = error
                else:
                    message = "Error: Email addresses do not match. Please try again."
            else:
                message = "Error: Both email fields are required."

        elif action == 'confirm_delete':
            user_email = request.form.get('confirmed_email', '').strip()
            if user_email:
                message = delete_user_account(user_email, admin_username=current_user['username'])
            else:
                message = "Error: User email not found. Please start over."

    return render_template('reviewer/deleteuser.html',
                           user=current_user['username'],
                           is_admin=current_user['is_admin'],
                           message=message,
                           preview=preview_data)


# Helper functions

def get_list_review_solution():
    solution_dir = os.path.join(CRACKMESONE_DIR, "tmp/solution")
    if not os.path.exists(solution_dir):
        return [], "Solution directory not found"

    files = os.listdir(solution_dir)
    crackme_collection = g_crackmesone_db.crackme
    solution_collection = g_crackmesone_db.solution

    solutions = []
    error = ""

    for file in files:
        parts = file.split("+++")
        if len(parts) != 3:
            continue
        author, solution_uuid, filename = parts
        if not ObjectId.is_valid(solution_uuid):
            error += f"File {file} has invalid uuid\n"
            continue

        solution_obj = solution_collection.find_one({"_id": ObjectId(solution_uuid)})
        if solution_obj:
            crackme_uuid = solution_obj["crackmeid"]
            crackme_obj = crackme_collection.find_one({"_id": crackme_uuid})
            if not crackme_obj:
                error += f"Crackme related to solution uuid {solution_uuid} not found in DB\n"
                continue
            crackme_name = crackme_obj["name"]
            solutions.append({
                "crackme_name": crackme_name,
                "solution_author": author,
                "solution_uuid": solution_uuid,
                "crackme_uuid": crackme_obj["hexid"],
                "date": solution_obj["created_at"]
            })
        else:
            error += f"File {file} UUID not found in DB\n"

    return solutions, error if error else None


def get_solution_by_uuid(uuid):
    if not ObjectId.is_valid(uuid):
        return None, "Invalid uuid"

    solution_uuid = ObjectId(uuid)
    solution_collection = g_crackmesone_db.solution
    solution_obj = solution_collection.find_one({"_id": solution_uuid})

    if solution_obj:
        crackme_collection = g_crackmesone_db.crackme
        crackme_obj = crackme_collection.find_one({"_id": solution_obj["crackmeid"]})
        crackme_name = crackme_obj["name"]
        solution = {
            "info": solution_obj["info"],
            "solution_uuid": uuid,
            "solution_author": solution_obj["author"],
            "crackme_name": crackme_name,
            "crackme_uuid": str(solution_obj["crackmeid"])
        }
        return solution, None
    else:
        return None, "Solution not found on db"


def delete_solution(solution_uuid):
    solution_collection = g_crackmesone_db.solution
    message = ""
    if ObjectId.is_valid(solution_uuid):
        result = solution_collection.find_one({"_id": ObjectId(solution_uuid)})
        if result:
            crackme_id = result.get("crackmeid")
            solution_file_path = os.path.join(CRACKMESONE_DIR, "static/solution", f"{solution_uuid}.zip")
            was_approved = os.path.exists(solution_file_path)

            try:
                os.remove(solution_file_path)
            except:
                pass
            solution_collection.delete_one({"_id": ObjectId(solution_uuid)})

            if crackme_id and was_approved:
                try:
                    crackme_collection = g_crackmesone_db.crackme
                    crackme_collection.update_one(
                        {"_id": crackme_id},
                        {"$inc": {"nbsolutions": -1}}
                    )
                except Exception as e:
                    print(f"Error decrementing solution count for crackme {crackme_id}: {e}")

            message = "Solution deleted"
        else:
            message = "Solution not found in database"
    else:
        message = "Invalid UUID format"

    return message


def get_list_review_crackme():
    crackme_dir = os.path.join(CRACKMESONE_DIR, "tmp/crackme")
    if not os.path.exists(crackme_dir):
        return [], "Crackme directory not found"

    files = os.listdir(crackme_dir)
    crackme_collection = g_crackmesone_db.crackme

    crackmes = []
    error = ""

    for file in files:
        parts = file.split("+++")
        if len(parts) != 3:
            continue
        author, crackme_uuid, filename = parts
        if not ObjectId.is_valid(crackme_uuid):
            error += f"File {file} has invalid uuid\n"
            continue

        crackme_obj = crackme_collection.find_one({"_id": ObjectId(crackme_uuid)})
        if crackme_obj:
            crackmes.append({
                "name": crackme_obj["name"],
                "date": crackme_obj["created_at"],
                "crackme_author": crackme_obj["author"],
                "crackme_uuid": crackme_obj["hexid"]
            })
        else:
            error += f"File {file}'s uuid not found in db\n"

    return crackmes, error if error else None


def get_crackme_by_uuid(uuid):
    if not ObjectId.is_valid(uuid):
        return None, "Invalid uuid"

    crackme_uuid = ObjectId(uuid)
    crackme_collection = g_crackmesone_db.crackme
    crackme_obj = crackme_collection.find_one({"_id": crackme_uuid})

    if crackme_obj:
        crackme = {
            "info": crackme_obj["info"],
            "crackme_uuid": uuid,
            "name": crackme_obj["name"],
            "author": crackme_obj["author"],
            "lang": crackme_obj["lang"],
            "arch": crackme_obj["arch"],
            "platform": crackme_obj["platform"]
        }
        return crackme, None
    else:
        return None, "Crackme not found on db"


def cascade_delete_crackme_data(db, crackme_id, crackme_hexid):
    deleted_counts = {
        'solutions': 0,
        'comments': 0,
        'difficulty_ratings': 0,
        'quality_ratings': 0
    }

    solutions = db.solution.find({'crackmeid': crackme_id})
    for solution in solutions:
        try:
            delete_solution(str(solution["_id"]))
            deleted_counts['solutions'] += 1
        except Exception as e:
            print(f"Warning: Failed to delete solution {solution['_id']}: {e}")

    result = db.comment.delete_many({'crackmehexid': crackme_hexid})
    deleted_counts['comments'] = result.deleted_count

    result = db.rating_difficulty.delete_many({'crackmehexid': crackme_hexid})
    deleted_counts['difficulty_ratings'] = result.deleted_count

    result = db.rating_quality.delete_many({'crackmehexid': crackme_hexid})
    deleted_counts['quality_ratings'] = result.deleted_count

    return deleted_counts


def delete_crackme(crackme_uuid):
    message = ""
    if ObjectId.is_valid(crackme_uuid):
        crackme_collection = g_crackmesone_db.crackme
        result = crackme_collection.find_one({"_id": ObjectId(crackme_uuid)})
        if result:
            deleted = cascade_delete_crackme_data(
                g_crackmesone_db,
                ObjectId(crackme_uuid),
                crackme_uuid
            )

            message += f"Cascade deleted: {deleted['solutions']} solutions, "
            message += f"{deleted['comments']} comments, "
            message += f"{deleted['difficulty_ratings']} difficulty ratings, "
            message += f"{deleted['quality_ratings']} quality ratings\n"

            try:
                os.remove(os.path.join(CRACKMESONE_DIR, "static/crackme", f"{crackme_uuid}.zip"))
            except:
                pass

            crackme_collection.delete_one({"_id": ObjectId(crackme_uuid)})
            message += "Crackme deleted"
        else:
            message = "Crackme uuid not found"
    else:
        message = "Invalid crackme uuid"

    return message


def reset_user_password(user_email):
    user_collection = g_crackmesone_db.user

    # Escape regex special characters to prevent injection
    escaped_email = re.escape(user_email)

    result = user_collection.find_one({"email": {"$regex": f"^{escaped_email}$", "$options": "i"}})

    if not result:
        return "Error: No user with the email found in database"

    chars = string.ascii_letters + string.digits
    plain_password = ''.join(random.choices(chars, k=16))

    hashed_password = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())

    update_result = user_collection.update_one(
        {"email": {"$regex": f"^{escaped_email}$", "$options": "i"}},
        {"$set": {"password": hashed_password.decode('utf-8')}}
    )

    if update_result.modified_count != 1:
        return "Error: Password update failed"

    name = result.get("name")
    email = result.get("email")

    return f"Password reset successful.\nName: {name}\nEmail: {email}\nNew password: {plain_password}"


def preview_user_deletion(user_email):
    user_collection = g_crackmesone_db.user

    # Escape regex special characters to prevent injection
    escaped_email = re.escape(user_email)

    user = user_collection.find_one({"email": {"$regex": f"^{escaped_email}$", "$options": "i"}})

    if not user:
        return None, "Error: No user found with this email address."

    username = user.get("name")
    if not username:
        return None, "Error: User has no username."

    preview = {
        'username': username,
        'email': user_email,
        'notifications': 0,
        'solutions': 0,
        'crackmes': 0,
        'crackme_details': [],
        'user_comments': 0,
        'difficulty_ratings': 0,
        'quality_ratings': 0,
        'total_comments': 0,
        'total_solutions_on_user_crackmes': 0
    }

    try:
        notification_collection = g_crackmesone_db.notifications
        preview['notifications'] = notification_collection.count_documents({"user": username})

        solution_collection = g_crackmesone_db.solution
        preview['solutions'] = solution_collection.count_documents({"author": username})

        crackme_collection = g_crackmesone_db.crackme
        crackmes = crackme_collection.find({"author": username})

        for crackme in crackmes:
            crackme_hexid = crackme.get("hexid")
            crackme_id = crackme.get("_id")
            crackme_name = crackme.get("name", "Unnamed")

            if crackme_hexid and crackme_id:
                solutions_count = solution_collection.count_documents({"crackmeid": crackme_id})
                comments_count = g_crackmesone_db.comment.count_documents({"crackmehexid": crackme_hexid})
                difficulty_ratings_count = g_crackmesone_db.rating_difficulty.count_documents({"crackmehexid": crackme_hexid})
                quality_ratings_count = g_crackmesone_db.rating_quality.count_documents({"crackmehexid": crackme_hexid})

                preview['crackme_details'].append({
                    'name': crackme_name,
                    'hexid': crackme_hexid,
                    'solutions': solutions_count,
                    'comments': comments_count,
                    'difficulty_ratings': difficulty_ratings_count,
                    'quality_ratings': quality_ratings_count
                })

                preview['total_solutions_on_user_crackmes'] += solutions_count
                preview['total_comments'] += comments_count

        preview['crackmes'] = len(preview['crackme_details'])

        user_crackme_hexids = [c['hexid'] for c in preview['crackme_details']]
        if user_crackme_hexids:
            preview['user_comments'] = g_crackmesone_db.comment.count_documents({
                "author": username,
                "crackmehexid": {"$nin": user_crackme_hexids}
            })
        else:
            preview['user_comments'] = g_crackmesone_db.comment.count_documents({"author": username})

        preview['total_comments'] += preview['user_comments']

        preview['difficulty_ratings'] = g_crackmesone_db.rating_difficulty.count_documents({"author": username})
        preview['quality_ratings'] = g_crackmesone_db.rating_quality.count_documents({"author": username})

        return preview, None

    except Exception as e:
        return None, f"Error previewing deletion: {str(e)}"


def delete_user_account(user_email, admin_username=None):
    user_collection = g_crackmesone_db.user

    # Escape regex special characters to prevent injection
    escaped_email = re.escape(user_email)

    user = user_collection.find_one({"email": {"$regex": f"^{escaped_email}$", "$options": "i"}})

    if not user:
        return "Error: No user found with this email address."

    username = user.get("name")
    if not username:
        return "Error: User has no username."

    deletion_log = []
    cascade_stats = {
        'solutions_on_user_crackmes': 0,
        'comments_on_user_crackmes': 0,
        'difficulty_ratings_on_user_crackmes': 0,
        'quality_ratings_on_user_crackmes': 0
    }

    try:
        # 1. Delete notifications
        notification_collection = g_crackmesone_db.notifications
        notification_result = notification_collection.delete_many({"user": username})
        deletion_log.append(f"Deleted {notification_result.deleted_count} notifications")

        # 2. Delete user's own solutions
        solution_collection = g_crackmesone_db.solution
        solutions = solution_collection.find({"author": username})
        solution_count = 0
        for solution in solutions:
            solution_uuid = str(solution["_id"])
            delete_solution(solution_uuid)
            solution_count += 1
        deletion_log.append(f"Deleted {solution_count} solutions by user")

        # 3. Delete crackmes by user with CASCADE DELETION
        crackme_collection = g_crackmesone_db.crackme
        crackmes = list(crackme_collection.find({"author": username}))
        crackme_count = 0
        for crackme in crackmes:
            crackme_uuid = crackme.get("hexid")
            if crackme_uuid:
                crackme_id = crackme.get("_id")
                crackme_hexid = crackme.get("hexid")

                if crackme_id and crackme_hexid:
                    cascade_stats['solutions_on_user_crackmes'] += solution_collection.count_documents({"crackmeid": crackme_id})
                    cascade_stats['comments_on_user_crackmes'] += g_crackmesone_db.comment.count_documents({"crackmehexid": crackme_hexid})
                    cascade_stats['difficulty_ratings_on_user_crackmes'] += g_crackmesone_db.rating_difficulty.count_documents({"crackmehexid": crackme_hexid})
                    cascade_stats['quality_ratings_on_user_crackmes'] += g_crackmesone_db.rating_quality.count_documents({"crackmehexid": crackme_hexid})

                delete_crackme(crackme_uuid)
                crackme_count += 1

        deletion_log.append(f"Deleted {crackme_count} crackmes by user")
        deletion_log.append(f"  -> Cascade deleted {cascade_stats['solutions_on_user_crackmes']} solutions on user's crackmes")
        deletion_log.append(f"  -> Cascade deleted {cascade_stats['comments_on_user_crackmes']} comments on user's crackmes")

        # 4. Delete user's comments on OTHER people's crackmes
        user_crackme_hexids = [c.get("hexid") for c in crackmes if c.get("hexid")]
        comment_collection = g_crackmesone_db.comment

        comments_to_delete = list(comment_collection.find({
            "author": username,
            "crackmehexid": {"$nin": user_crackme_hexids}
        })) if user_crackme_hexids else list(comment_collection.find({"author": username}))

        comment_counts_per_crackme = {}
        for comment in comments_to_delete:
            crackme_hexid = comment.get("crackmehexid")
            if crackme_hexid:
                comment_counts_per_crackme[crackme_hexid] = comment_counts_per_crackme.get(crackme_hexid, 0) + 1

        if user_crackme_hexids:
            comment_result = comment_collection.delete_many({
                "author": username,
                "crackmehexid": {"$nin": user_crackme_hexids}
            })
        else:
            comment_result = comment_collection.delete_many({"author": username})
        deletion_log.append(f"Deleted {comment_result.deleted_count} comments by user on other crackmes")

        for crackme_hexid, count in comment_counts_per_crackme.items():
            try:
                crackme_collection.update_one(
                    {"_id": ObjectId(crackme_hexid)},
                    {"$inc": {"nbcomments": -count}}
                )
            except Exception as e:
                print(f"Error decrementing comment count for crackme {crackme_hexid}: {e}")

        # 5. Delete difficulty ratings
        rating_difficulty_collection = g_crackmesone_db.rating_difficulty
        difficulty_ratings = rating_difficulty_collection.find({"author": username})
        difficulty_crackmes = set()
        for rating in difficulty_ratings:
            hexid = rating.get("crackmehexid")
            if hexid and hexid not in user_crackme_hexids:
                difficulty_crackmes.add(hexid)

        rating_difficulty_result = rating_difficulty_collection.delete_many({"author": username})
        deletion_log.append(f"Deleted {rating_difficulty_result.deleted_count} difficulty ratings by user")

        # 6. Delete quality ratings
        rating_quality_collection = g_crackmesone_db.rating_quality
        quality_ratings = rating_quality_collection.find({"author": username})
        quality_crackmes = set()
        for rating in quality_ratings:
            hexid = rating.get("crackmehexid")
            if hexid and hexid not in user_crackme_hexids:
                quality_crackmes.add(hexid)

        rating_quality_result = rating_quality_collection.delete_many({"author": username})
        deletion_log.append(f"Deleted {rating_quality_result.deleted_count} quality ratings by user")

        # 7. Recalculate difficulty for affected crackmes
        recalculated_difficulty = 0
        for crackme_hexid in difficulty_crackmes:
            if crackme_hexid:
                remaining_ratings = rating_difficulty_collection.find({"crackmehexid": crackme_hexid})
                ratings_list = list(remaining_ratings)
                if ratings_list:
                    avg_difficulty = sum(r["rating"] for r in ratings_list) / len(ratings_list)
                    crackme_collection.update_one(
                        {"hexid": crackme_hexid},
                        {"$set": {"difficulty": avg_difficulty}}
                    )
                else:
                    crackme_collection.update_one(
                        {"hexid": crackme_hexid},
                        {"$set": {"difficulty": 0.0}}
                    )
                recalculated_difficulty += 1

        # 8. Recalculate quality for affected crackmes
        recalculated_quality = 0
        for crackme_hexid in quality_crackmes:
            if crackme_hexid:
                remaining_ratings = rating_quality_collection.find({"crackmehexid": crackme_hexid})
                ratings_list = list(remaining_ratings)
                if ratings_list:
                    avg_quality = sum(r["rating"] for r in ratings_list) / len(ratings_list)
                    crackme_collection.update_one(
                        {"hexid": crackme_hexid},
                        {"$set": {"quality": avg_quality}}
                    )
                else:
                    crackme_collection.update_one(
                        {"hexid": crackme_hexid},
                        {"$set": {"quality": 0.0}}
                    )
                recalculated_quality += 1

        deletion_log.append(f"Recalculated difficulty for {recalculated_difficulty} crackmes")
        deletion_log.append(f"Recalculated quality for {recalculated_quality} crackmes")

        # 9. Delete the user account
        user_result = user_collection.delete_one({"_id": user["_id"]})
        if user_result.deleted_count == 1:
            deletion_log.append(f"Deleted user account: {username} ({user_email})")
        else:
            return "Error: Failed to delete user account"

        # 10. Log the operation
        if admin_username:
            total_solutions = solution_count + cascade_stats['solutions_on_user_crackmes']
            total_comments = comment_result.deleted_count + cascade_stats['comments_on_user_crackmes']
            log_reviewer_operation(
                "delete_user_account",
                admin_username,
                {
                    "deleted_user": username,
                    "email": user_email,
                    "crackmes": crackme_count,
                    "solutions": f"{total_solutions} ({solution_count} by user + {cascade_stats['solutions_on_user_crackmes']} cascade)",
                    "comments": f"{total_comments} ({comment_result.deleted_count} by user + {cascade_stats['comments_on_user_crackmes']} cascade)",
                    "difficulty_ratings": rating_difficulty_result.deleted_count,
                    "quality_ratings": rating_quality_result.deleted_count,
                    "notifications": notification_result.deleted_count
                },
                success=True
            )

        return f"User account deletion successful!\n" + "\n".join(deletion_log)

    except Exception as e:
        return f"Error during deletion: {str(e)}"


def post_discord_notification_solution(crackme_name, crackme_uuid, solution_uuid, author):
    """Send PUBLIC notification for an approved solution."""
    if not DISCORD_WEBHOOK_PUBLIC:
        return
    timestamp = datetime.datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    data = {
        "embeds": [
            {
                "title": "New solution approved",
                "description": "New solution has been approved on crackmes.one",
                "color": 65280,
                "author": {
                    "name": "crackmes.one",
                    "url": "https://crackmes.one",
                    "icon_url": "https://i.imgur.com/YORPaBo.png"
                },
                "fields": [
                    {"name": "Challenge", "value": f"[{crackme_name}](https://crackmes.one/crackme/{crackme_uuid})", "inline": True},
                    {"name": "Solution author", "value": f"[{author}](https://crackmes.one/user/{author})", "inline": True},
                    {"name": "Download solution", "value": f"[Link](https://crackmes.one/static/solution/{solution_uuid}.zip)", "inline": True}
                ],
                "footer": {"text": "crackmes.one", "icon_url": "https://i.imgur.com/YORPaBo.png"},
                "timestamp": timestamp,
            }
        ]
    }

    try:
        requests.post(DISCORD_WEBHOOK_PUBLIC, json=data, timeout=10)
    except Exception as e:
        print(f"Discord notification error: {e}")


def post_discord_notification_crackme(crackme_name, crackme_uuid, author):
    """Send PUBLIC notification for an approved crackme."""
    if not DISCORD_WEBHOOK_PUBLIC:
        return
    timestamp = datetime.datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    data = {
        "embeds": [
            {
                "title": "New crackme approved",
                "description": "New crackme has been approved on crackmes.one",
                "color": 65280,
                "author": {
                    "name": "crackmes.one",
                    "url": "https://crackmes.one",
                    "icon_url": "https://i.imgur.com/YORPaBo.png"
                },
                "fields": [
                    {"name": "Challenge", "value": f"[{crackme_name}](https://crackmes.one/crackme/{crackme_uuid})", "inline": True},
                    {"name": "Crackme author", "value": f"[{author}](https://crackmes.one/user/{author})", "inline": True},
                    {"name": "Download crackme", "value": f"[Link](https://crackmes.one/static/crackme/{crackme_uuid}.zip)", "inline": True}
                ],
                "footer": {"text": "crackmes.one", "icon_url": "https://i.imgur.com/YORPaBo.png"},
                "timestamp": timestamp,
            }
        ]
    }

    try:
        requests.post(DISCORD_WEBHOOK_PUBLIC, json=data, timeout=10)
    except Exception as e:
        print(f"Discord notification error: {e}")


def reject_pending_crackme(file_loc, reject_reason=None):
    """
    Reject a pending crackme submission.
    Removes the file from tmp/ and sends a rejection notification to the author.
    """
    try:
        parts = file_loc.split('+++')
        if len(parts) != 3:
            return False, "Invalid file format"

        username, hexid, filename = parts

        # Find in database
        collection = g_crackmesone_db.crackme
        db_object = collection.find_one({'hexid': hexid})

        if db_object is None:
            return False, "Crackme not found in database"

        # Delete from database
        collection.delete_one({'hexid': hexid})

        # Delete any ratings that were created
        g_crackmesone_db.rating_difficulty.delete_many({"crackmehexid": hexid})
        g_crackmesone_db.rating_quality.delete_many({"crackmehexid": hexid})

        # Remove file from tmp/crackme
        file_path = os.path.join(CRACKMESONE_DIR, 'tmp', 'crackme', file_loc)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Send rejection notification
        notif_coll = g_crackmesone_db.notifications
        users_coll = g_crackmesone_db.user
        author_name = db_object["author"]

        notif_text = f"Your crackme '{db_object['name']}' has been rejected!"
        if reject_reason:
            notif_text += f" Reason: {reject_reason}"

        ins_id = notif_coll.insert_one({
            "user": author_name,
            "time": datetime.datetime.now(datetime.timezone.utc),
            "seen": False,
            "text": notif_text
        }).inserted_id
        notif_coll.find_one_and_update({'_id': ins_id}, {'$set': {'hexid': str(ins_id)}})
        users_coll.update_one({'name': author_name}, {'$inc': {'unread_notifications': 1}})

        return True, f"Crackme '{db_object['name']}' rejected successfully"

    except Exception as e:
        return False, f"Error rejecting crackme: {str(e)}"


def reject_pending_solution(file_loc, reject_reason=None):
    """
    Reject a pending solution submission.
    Removes the file from tmp/ and sends a rejection notification to the author.
    """
    try:
        parts = file_loc.split('+++')
        if len(parts) != 3:
            return False, "Invalid file format"

        username, hexid, filename = parts

        # Find in database
        collection = g_crackmesone_db.solution
        db_object = collection.find_one({'hexid': hexid})

        if db_object is None:
            return False, "Solution not found in database"

        # Get crackme info for notification
        crackme_obj = g_crackmesone_db.crackme.find_one({'_id': db_object["crackmeid"]})
        crackme_name = crackme_obj["name"] if crackme_obj else "Unknown"

        # Delete from database
        collection.delete_one({'hexid': hexid})

        # Remove file from tmp/solution
        file_path = os.path.join(CRACKMESONE_DIR, 'tmp', 'solution', file_loc)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Send rejection notification
        notif_coll = g_crackmesone_db.notifications
        users_coll = g_crackmesone_db.user
        author_name = db_object["author"]

        notif_text = f"Your solution for '{crackme_name}' has been rejected!"
        if reject_reason:
            notif_text += f" Reason: {reject_reason}"

        ins_id = notif_coll.insert_one({
            "user": author_name,
            "time": datetime.datetime.now(datetime.timezone.utc),
            "seen": False,
            "text": notif_text
        }).inserted_id
        notif_coll.find_one_and_update({'_id': ins_id}, {'$set': {'hexid': str(ins_id)}})
        users_coll.update_one({'name': author_name}, {'$inc': {'unread_notifications': 1}})

        return True, f"Solution for '{crackme_name}' rejected successfully"

    except Exception as e:
        return False, f"Error rejecting solution: {str(e)}"


def approve_pending_crackme(file_loc):
    """
    Approve a pending crackme submission.
    Moves the file from tmp/ to static/, zips it with password, and sends approval notification.
    """
    try:
        parts = file_loc.split('+++')
        if len(parts) != 3:
            return False, "Invalid file format"

        username, hexid, filename = parts

        # Find in database
        collection = g_crackmesone_db.crackme
        db_object = collection.find_one({'hexid': hexid})

        if db_object is None:
            return False, "Crackme not found in database"

        # Set visible to true
        collection.update_one({'hexid': hexid}, {'$set': {'visible': True}})

        # Move file from tmp to static (zipped with password)
        file_path = os.path.join(CRACKMESONE_DIR, 'tmp', 'crackme', file_loc)
        if not os.path.exists(file_path):
            return False, "Crackme file not found in tmp directory"

        # Create temp file for zipping
        temp_filename = os.path.join(CRACKMESONE_DIR, filename)
        shutil.move(file_path, temp_filename)

        # Create zip with password in static directory
        zip_output = os.path.join(CRACKMESONE_DIR, 'static', 'crackme', hexid)
        zip_ret = call(["zip", "-j", "--password", "crackmes.one", "--", zip_output, temp_filename])
        if zip_ret != 0:
            # Revert visibility flag since packaging failed
            collection.update_one({'hexid': hexid}, {'$set': {'visible': False}})
            # Attempt to move the file back to its original location so it is not lost
            if os.path.exists(temp_filename):
                try:
                    shutil.move(temp_filename, file_path)
                except Exception:
                    # If we can't move it back, at least ensure it does not remain in an inconsistent temp location
                    pass
            return False, "Failed to package crackme (zip command failed)"

        # Clean up temp file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

        # Send approval notification
        notif_coll = g_crackmesone_db.notifications
        users_coll = g_crackmesone_db.user
        author_name = db_object["author"]

        ins_id = notif_coll.insert_one({
            "user": author_name,
            "time": datetime.datetime.now(datetime.timezone.utc),
            "seen": False,
            "text": f"Your crackme '{db_object['name']}' has been accepted!"
        }).inserted_id
        notif_coll.find_one_and_update({'_id': ins_id}, {'$set': {'hexid': str(ins_id)}})
        users_coll.update_one({'name': author_name}, {'$inc': {'unread_notifications': 1}})

        return True, f"Crackme '{db_object['name']}' approved successfully"

    except Exception as e:
        return False, f"Error approving crackme: {str(e)}"


def approve_pending_solution(file_loc):
    """
    Approve a pending solution submission.
    Moves the file from tmp/ to static/, zips it with password, and sends approval notification.
    """
    try:
        parts = file_loc.split('+++')
        if len(parts) != 3:
            return False, "Invalid file format"

        username, hexid, filename = parts

        # Find in database
        collection = g_crackmesone_db.solution
        db_object = collection.find_one({'hexid': hexid})

        if db_object is None:
            return False, "Solution not found in database"

        # Get crackme info for notification
        crackme_obj = g_crackmesone_db.crackme.find_one({'_id': db_object["crackmeid"]})
        if not crackme_obj:
            return False, "Related crackme not found"
        crackme_name = crackme_obj["name"]

        # Set visible to true
        collection.update_one({'hexid': hexid}, {'$set': {'visible': True}})

        # Move file from tmp to static (zipped with password)
        file_path = os.path.join(CRACKMESONE_DIR, 'tmp', 'solution', file_loc)
        if not os.path.exists(file_path):
            return False, "Solution file not found in tmp directory"

        # Create temp file for zipping
        temp_filename = os.path.join(CRACKMESONE_DIR, filename)
        shutil.move(file_path, temp_filename)

        # Create zip with password in static directory
        zip_output = os.path.join(CRACKMESONE_DIR, 'static', 'solution', hexid)
        zip_rc = call(["zip", "-j", "--password", "crackmes.one", "--", zip_output, temp_filename])
        if zip_rc != 0:
            # Revert visibility if packaging failed
            collection.update_one({'hexid': hexid}, {'$set': {'visible': False}})
            # Best-effort: move file back to tmp or remove it
            try:
                if os.path.exists(temp_filename):
                    shutil.move(temp_filename, file_path)
            except Exception:
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
            return False, "Failed to package solution file"

        # Clean up temp file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

        # Send approval notification to solution author
        notif_coll = g_crackmesone_db.notifications
        users_coll = g_crackmesone_db.user
        author_name = db_object["author"]

        ins_id = notif_coll.insert_one({
            "user": author_name,
            "time": datetime.datetime.now(datetime.timezone.utc),
            "seen": False,
            "text": f"Your solution for '{crackme_name}' has been accepted!"
        }).inserted_id
        notif_coll.find_one_and_update({'_id': ins_id}, {'$set': {'hexid': str(ins_id)}})
        users_coll.update_one({'name': author_name}, {'$inc': {'unread_notifications': 1}})

        # Notify crackme author about new solution
        crackme_author = crackme_obj["author"]
        ins_id = notif_coll.insert_one({
            "user": crackme_author,
            "time": datetime.datetime.now(datetime.timezone.utc),
            "seen": False,
            "text": f"A new solution for your crackme '{crackme_name}' has been submitted by: {author_name}"
        }).inserted_id
        notif_coll.find_one_and_update({'_id': ins_id}, {'$set': {'hexid': str(ins_id)}})
        users_coll.update_one({'name': crackme_author}, {'$inc': {'unread_notifications': 1}})

        return True, f"Solution for '{crackme_name}' approved successfully"

    except Exception as e:
        return False, f"Error approving solution: {str(e)}"
