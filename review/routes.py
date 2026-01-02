"""
Reviewer Tool Routes - Flask Blueprint for managing crackme submissions.

This module provides a web interface for reviewers and admins to:
- Approve/reject pending crackme and solution submissions
- Manage approved content (admin only)
- Manage user accounts (admin only)
- Manage reviewer accounts (admin only)
"""

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, abort, send_file, session
)
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


# =============================================================================
# Configuration and Constants
# =============================================================================

# Deduce CRACKMESONE_DIR from script location (parent of review/ folder)
CRACKMESONE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Blueprint setup
reviewer_bp = Blueprint('reviewer', __name__,
                        template_folder='templates',
                        url_prefix='/review')

# Module-level configuration (set by init_reviewer)
PASSWORD_SALT = None
DISCORD_WEBHOOK_PUBLIC = None
g_crackmesone_db = None
users = {}
USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

# Session keys for reviewer authentication (prefixed to avoid conflicts)
REVIEWER_SESSION_KEY = '_reviewer_user'
REVIEWER_ADMIN_KEY = '_reviewer_is_admin'
REVIEWER_CSRF_KEY = '_reviewer_csrf_token'

# Archive password for approved submissions
ARCHIVE_PASSWORD = 'crackmes.one'


# =============================================================================
# Initialization
# =============================================================================

def init_reviewer(app):
    """
    Initialize reviewer module with app configuration.

    Reads configuration from the Flask app config and loads reviewer
    credentials from users.json.

    Args:
        app: Flask application instance with config containing:
            - REVIEWER_PASSWORD_SALT: Salt for hashing reviewer passwords
            - DISCORD_CONFIG: Dict with Enabled and WebhookPublic keys
    """
    global PASSWORD_SALT, DISCORD_WEBHOOK_PUBLIC, g_crackmesone_db, users

    PASSWORD_SALT = app.config.get(
        'REVIEWER_PASSWORD_SALT',
        os.getenv('REVIEWER_PASSWORD_SALT')
    )

    discord_config = app.config.get('DISCORD_CONFIG', {})
    if discord_config.get('Enabled', False):
        DISCORD_WEBHOOK_PUBLIC = discord_config.get('WebhookPublic', '')

    from app.services.database import get_db
    g_crackmesone_db = get_db()

    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            users.update(json.load(f))


def save_users():
    """
    Persist reviewer users to users.json file.

    Writes the current state of the users dict to disk with indentation
    for readability.
    """
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)


# =============================================================================
# Authentication Helpers
# =============================================================================

def hash_string(input_string):
    """
    Hash a string using SHA256.

    Args:
        input_string: Plain text string to hash

    Returns:
        Hexadecimal string representation of the SHA256 hash
    """
    return hashlib.sha256(input_string.encode('utf-8')).hexdigest()


def get_current_reviewer():
    """
    Get the current authenticated reviewer from session.

    Returns:
        Dict with 'username' and 'is_admin' keys if authenticated,
        None if not authenticated or user no longer exists.
    """
    username = session.get(REVIEWER_SESSION_KEY)
    if not username or username not in users:
        return None
    return {
        'username': username,
        'is_admin': users[username].get('is_admin', False)
    }


def clear_reviewer_session():
    """Remove reviewer authentication from session."""
    session.pop(REVIEWER_SESSION_KEY, None)
    session.pop(REVIEWER_ADMIN_KEY, None)


def token_required(f):
    """
    Decorator requiring reviewer authentication.

    Redirects to login page if not authenticated. Passes current_user
    dict as first argument to the decorated function.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        current_user = get_current_reviewer()
        if not current_user:
            clear_reviewer_session()
            return redirect(url_for('reviewer.login'))
        return f(current_user, *args, **kwargs)
    return decorated


def admin_required(f):
    """
    Decorator requiring admin authentication.

    Redirects to login if not authenticated, returns 403 if authenticated
    but not an admin. Passes current_user dict as first argument.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        current_user = get_current_reviewer()
        if not current_user:
            clear_reviewer_session()
            return redirect(url_for('reviewer.login'))
        if not current_user['is_admin']:
            abort(403)
        return f(current_user, *args, **kwargs)
    return decorated


# =============================================================================
# CSRF Protection
# =============================================================================

def generate_csrf_token():
    """
    Generate or retrieve CSRF token for the current session.

    Returns:
        32-byte hex string CSRF token
    """
    if REVIEWER_CSRF_KEY not in session:
        session[REVIEWER_CSRF_KEY] = hashlib.sha256(os.urandom(32)).hexdigest()
    return session[REVIEWER_CSRF_KEY]


def validate_csrf_token():
    """
    Validate CSRF token from form submission.

    Aborts with 403 if token is missing or invalid.
    """
    token = request.form.get('csrf_token')
    expected = session.get(REVIEWER_CSRF_KEY)
    if not token or not expected or token != expected:
        abort(403, description="CSRF token validation failed")


@reviewer_bp.context_processor
def inject_csrf_token():
    """Make csrf_token function available in all templates."""
    return {'csrf_token': generate_csrf_token}


# =============================================================================
# File and Path Helpers
# =============================================================================

def get_tmp_dir(item_type):
    """
    Get the temporary directory path for pending submissions.

    Args:
        item_type: Either 'crackme' or 'solution'

    Returns:
        Absolute path to the tmp directory for that item type
    """
    return os.path.join(CRACKMESONE_DIR, 'tmp', item_type)


def get_static_dir(item_type):
    """
    Get the static directory path for approved submissions.

    Args:
        item_type: Either 'crackme' or 'solution'

    Returns:
        Absolute path to the static directory for that item type
    """
    return os.path.join(CRACKMESONE_DIR, 'static', item_type)


def parse_pending_filename(filename):
    """
    Parse a pending submission filename into components.

    Pending files are named: author+++hexid+++original_filename

    Args:
        filename: The pending file's name

    Returns:
        Tuple of (author, hexid, original_filename) or None if invalid
    """
    parts = filename.split('+++')
    if len(parts) != 3:
        return None
    return tuple(parts)


def find_pending_file(item_type, target_uuid):
    """
    Find a pending submission file by its UUID.

    Args:
        item_type: Either 'crackme' or 'solution'
        target_uuid: The hexid to search for

    Returns:
        Filename if found, empty string if not found
    """
    tmp_dir = get_tmp_dir(item_type)
    if not os.path.exists(tmp_dir):
        return ""

    for filename in os.listdir(tmp_dir):
        parsed = parse_pending_filename(filename)
        if parsed and parsed[1] == target_uuid:
            return filename
    return ""


def count_pending_items(item_type):
    """
    Count pending submissions of a given type.

    Args:
        item_type: Either 'crackme' or 'solution'

    Returns:
        Number of valid pending submission files
    """
    tmp_dir = get_tmp_dir(item_type)
    if not os.path.exists(tmp_dir):
        return 0
    return sum(
        1 for f in os.listdir(tmp_dir)
        if parse_pending_filename(f) is not None
    )


# =============================================================================
# Database Helpers
# =============================================================================

def find_user_by_email_or_name(query):
    """
    Find a user by email or username (case-insensitive).

    Args:
        query: Email address or username to search for

    Returns:
        User document if found, None otherwise
    """
    escaped = re.escape(query)
    user_collection = g_crackmesone_db.user

    # Try email first
    user = user_collection.find_one({
        "email": {"$regex": f"^{escaped}$", "$options": "i"}
    })
    if user:
        return user

    # Try username
    return user_collection.find_one({
        "name": {"$regex": f"^{escaped}$", "$options": "i"}
    })


# =============================================================================
# Notification Helpers
# =============================================================================

def send_user_notification(username, text):
    """
    Send an in-app notification to a user.

    Creates a notification document in the database and increments
    the user's unread notification count.

    Args:
        username: Target user's username
        text: Notification message text
    """
    notif_coll = g_crackmesone_db.notifications
    users_coll = g_crackmesone_db.user

    ins_id = notif_coll.insert_one({
        "user": username,
        "time": datetime.datetime.now(timezone.utc),
        "seen": False,
        "text": text
    }).inserted_id

    notif_coll.find_one_and_update(
        {'_id': ins_id},
        {'$set': {'hexid': str(ins_id)}}
    )
    users_coll.update_one(
        {'name': username},
        {'$inc': {'unread_notifications': 1}}
    )


def post_discord_notification(title, description, fields):
    """
    Send a Discord webhook notification for approved content.

    Args:
        title: Embed title (e.g., "New crackme approved")
        description: Embed description
        fields: List of field dicts with 'name', 'value', 'inline' keys
    """
    if not DISCORD_WEBHOOK_PUBLIC:
        return

    timestamp = (
        datetime.datetime.utcnow()
        .replace(tzinfo=timezone.utc)
        .isoformat(timespec='milliseconds')
        .replace('+00:00', 'Z')
    )

    data = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": 65280,  # Green
            "author": {
                "name": "crackmes.one",
                "url": "https://crackmes.one",
                "icon_url": "https://i.imgur.com/YORPaBo.png"
            },
            "fields": fields,
            "footer": {
                "text": "crackmes.one",
                "icon_url": "https://i.imgur.com/YORPaBo.png"
            },
            "timestamp": timestamp,
        }]
    }

    try:
        requests.post(DISCORD_WEBHOOK_PUBLIC, json=data, timeout=10)
    except Exception as e:
        print(f"Discord notification error: {e}")


def notify_crackme_approved(crackme_name, crackme_uuid, author):
    """
    Send Discord notification for an approved crackme.

    Args:
        crackme_name: Name of the crackme
        crackme_uuid: Hex ID of the crackme
        author: Author's username
    """
    post_discord_notification(
        "New crackme approved",
        "New crackme has been approved on crackmes.one",
        [
            {
                "name": "Challenge",
                "value": f"[{crackme_name}](https://crackmes.one/crackme/{crackme_uuid})",
                "inline": True
            },
            {
                "name": "Crackme author",
                "value": f"[{author}](https://crackmes.one/user/{author})",
                "inline": True
            },
            {
                "name": "Download crackme",
                "value": f"[Link](https://crackmes.one/static/crackme/{crackme_uuid}.zip)",
                "inline": True
            }
        ]
    )


def notify_solution_approved(crackme_name, crackme_uuid, solution_uuid, author):
    """
    Send Discord notification for an approved solution.

    Args:
        crackme_name: Name of the related crackme
        crackme_uuid: Hex ID of the related crackme
        solution_uuid: Hex ID of the solution
        author: Solution author's username
    """
    post_discord_notification(
        "New solution approved",
        "New solution has been approved on crackmes.one",
        [
            {
                "name": "Challenge",
                "value": f"[{crackme_name}](https://crackmes.one/crackme/{crackme_uuid})",
                "inline": True
            },
            {
                "name": "Solution author",
                "value": f"[{author}](https://crackmes.one/user/{author})",
                "inline": True
            },
            {
                "name": "Download solution",
                "value": f"[Link](https://crackmes.one/static/solution/{solution_uuid}.zip)",
                "inline": True
            }
        ]
    )


# =============================================================================
# Archive Helpers
# =============================================================================

def create_password_protected_zip(source_path, dest_path_without_ext, filename_in_archive):
    """
    Create a password-protected zip archive.

    Moves the source file to a temp location with the desired archive name,
    creates the zip, then cleans up.

    Args:
        source_path: Path to the file to archive
        dest_path_without_ext: Destination path without .zip extension
        filename_in_archive: Name the file should have inside the archive

    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    # Move to temp location with desired filename
    temp_path = os.path.join(CRACKMESONE_DIR, filename_in_archive)
    shutil.move(source_path, temp_path)

    try:
        # Find zip command (use full path to avoid PATH issues in web server)
        zip_cmd = shutil.which("zip") or "/usr/bin/zip"

        # Create password-protected zip
        ret = call([
            zip_cmd, "-j", "--password", ARCHIVE_PASSWORD,
            dest_path_without_ext, "--", temp_path
        ])

        if ret != 0:
            # Move file back on failure
            if os.path.exists(temp_path):
                try:
                    shutil.move(temp_path, source_path)
                except Exception:
                    pass
            return False, "Failed to create zip archive"

        return True, None

    except FileNotFoundError:
        # zip command not found - move file back
        if os.path.exists(temp_path):
            try:
                shutil.move(temp_path, source_path)
            except Exception:
                pass
        return False, "zip command not found"

    except Exception as e:
        # Other errors - move file back
        if os.path.exists(temp_path):
            try:
                shutil.move(temp_path, source_path)
            except Exception:
                pass
        return False, f"Error creating zip: {str(e)}"

    finally:
        # Clean up temp file (only if zip succeeded, file was moved to archive)
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


# =============================================================================
# Pending Submission Operations
# =============================================================================

def get_pending_solutions():
    """
    Get list of pending solution submissions for review.

    Reads files from tmp/solution and looks up metadata from database.

    Returns:
        Tuple of (solutions_list, error_string or None)
        Each solution dict contains: crackme_name, solution_author,
        solution_uuid, crackme_uuid, date
    """
    tmp_dir = get_tmp_dir('solution')
    if not os.path.exists(tmp_dir):
        return [], "Solution directory not found"

    solutions = []
    errors = []

    for filename in os.listdir(tmp_dir):
        parsed = parse_pending_filename(filename)
        if not parsed:
            continue

        author, solution_uuid, _ = parsed

        if not ObjectId.is_valid(solution_uuid):
            errors.append(f"File {filename} has invalid uuid")
            continue

        solution_obj = g_crackmesone_db.solution.find_one({
            "_id": ObjectId(solution_uuid)
        })

        if not solution_obj:
            errors.append(f"File {filename} UUID not found in DB")
            continue

        crackme_obj = g_crackmesone_db.crackme.find_one({
            "_id": solution_obj["crackmeid"]
        })

        if not crackme_obj:
            errors.append(
                f"Crackme for solution {solution_uuid} not found in DB"
            )
            continue

        solutions.append({
            "crackme_name": crackme_obj["name"],
            "solution_author": author,
            "solution_uuid": solution_uuid,
            "crackme_uuid": crackme_obj["hexid"],
            "date": solution_obj["created_at"]
        })

    return solutions, "\n".join(errors) if errors else None


def get_pending_crackmes():
    """
    Get list of pending crackme submissions for review.

    Reads files from tmp/crackme and looks up metadata from database.

    Returns:
        Tuple of (crackmes_list, error_string or None)
        Each crackme dict contains: name, date, crackme_author, crackme_uuid
    """
    tmp_dir = get_tmp_dir('crackme')
    if not os.path.exists(tmp_dir):
        return [], "Crackme directory not found"

    crackmes = []
    errors = []

    for filename in os.listdir(tmp_dir):
        parsed = parse_pending_filename(filename)
        if not parsed:
            continue

        _, crackme_uuid, _ = parsed

        if not ObjectId.is_valid(crackme_uuid):
            errors.append(f"File {filename} has invalid uuid")
            continue

        crackme_obj = g_crackmesone_db.crackme.find_one({
            "_id": ObjectId(crackme_uuid)
        })

        if not crackme_obj:
            errors.append(f"File {filename}'s uuid not found in db")
            continue

        crackmes.append({
            "name": crackme_obj["name"],
            "date": crackme_obj["created_at"],
            "crackme_author": crackme_obj["author"],
            "crackme_uuid": crackme_obj["hexid"]
        })

    return crackmes, "\n".join(errors) if errors else None


def get_solution_details(uuid):
    """
    Get detailed information about a solution by UUID.

    Args:
        uuid: Solution's hex ID

    Returns:
        Tuple of (solution_dict, error_string)
        Solution dict contains: info, solution_uuid, solution_author,
        crackme_name, crackme_uuid
    """
    if not ObjectId.is_valid(uuid):
        return None, "Invalid uuid"

    solution_obj = g_crackmesone_db.solution.find_one({
        "_id": ObjectId(uuid)
    })

    if not solution_obj:
        return None, "Solution not found in database"

    crackme_obj = g_crackmesone_db.crackme.find_one({
        "_id": solution_obj["crackmeid"]
    })

    return {
        "info": solution_obj["info"],
        "solution_uuid": uuid,
        "solution_author": solution_obj["author"],
        "crackme_name": crackme_obj["name"] if crackme_obj else "Unknown",
        "crackme_uuid": str(solution_obj["crackmeid"])
    }, None


def get_crackme_details(uuid):
    """
    Get detailed information about a crackme by UUID.

    Args:
        uuid: Crackme's hex ID

    Returns:
        Tuple of (crackme_dict, error_string)
        Crackme dict contains: info, crackme_uuid, name, author,
        lang, arch, platform
    """
    if not ObjectId.is_valid(uuid):
        return None, "Invalid uuid"

    crackme_obj = g_crackmesone_db.crackme.find_one({
        "_id": ObjectId(uuid)
    })

    if not crackme_obj:
        return None, "Crackme not found in database"

    return {
        "info": crackme_obj["info"],
        "crackme_uuid": uuid,
        "name": crackme_obj["name"],
        "author": crackme_obj["author"],
        "lang": crackme_obj["lang"],
        "arch": crackme_obj["arch"],
        "platform": crackme_obj["platform"]
    }, None


def reject_pending_crackme(file_loc, reject_reason=None):
    """
    Reject a pending crackme submission.

    Deletes the crackme from database, removes associated ratings,
    deletes the file from tmp/, and notifies the author.

    Args:
        file_loc: Pending filename (author+++hexid+++filename format)
        reject_reason: Optional reason to include in notification

    Returns:
        Tuple of (success: bool, message: str)
    """
    parsed = parse_pending_filename(file_loc)
    if not parsed:
        return False, "Invalid file format"

    _, hexid, _ = parsed

    try:
        crackme = g_crackmesone_db.crackme.find_one({'hexid': hexid})
        if not crackme:
            return False, "Crackme not found in database"

        # Delete from database
        g_crackmesone_db.crackme.delete_one({'hexid': hexid})
        g_crackmesone_db.rating_difficulty.delete_many({"crackmehexid": hexid})
        g_crackmesone_db.rating_quality.delete_many({"crackmehexid": hexid})

        # Remove file
        file_path = os.path.join(get_tmp_dir('crackme'), file_loc)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Notify author
        notif_text = f"Your crackme '{crackme['name']}' has been rejected!"
        if reject_reason:
            notif_text += f" Reason: {reject_reason}"
        send_user_notification(crackme["author"], notif_text)

        return True, f"Crackme '{crackme['name']}' rejected successfully"

    except Exception as e:
        return False, f"Error rejecting crackme: {str(e)}"


def reject_pending_solution(file_loc, reject_reason=None):
    """
    Reject a pending solution submission.

    Deletes the solution from database, removes the file from tmp/,
    and notifies the author.

    Args:
        file_loc: Pending filename (author+++hexid+++filename format)
        reject_reason: Optional reason to include in notification

    Returns:
        Tuple of (success: bool, message: str)
    """
    parsed = parse_pending_filename(file_loc)
    if not parsed:
        return False, "Invalid file format"

    _, hexid, _ = parsed

    try:
        solution = g_crackmesone_db.solution.find_one({'hexid': hexid})
        if not solution:
            return False, "Solution not found in database"

        # Get crackme name for notification
        crackme = g_crackmesone_db.crackme.find_one({
            '_id': solution["crackmeid"]
        })
        crackme_name = crackme["name"] if crackme else "Unknown"

        # Delete from database
        g_crackmesone_db.solution.delete_one({'hexid': hexid})

        # Remove file
        file_path = os.path.join(get_tmp_dir('solution'), file_loc)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Notify author
        notif_text = f"Your solution for '{crackme_name}' has been rejected!"
        if reject_reason:
            notif_text += f" Reason: {reject_reason}"
        send_user_notification(solution["author"], notif_text)

        return True, f"Solution for '{crackme_name}' rejected successfully"

    except Exception as e:
        return False, f"Error rejecting solution: {str(e)}"


def approve_pending_crackme(file_loc):
    """
    Approve a pending crackme submission.

    Sets the crackme as visible, creates a password-protected zip in
    static/crackme/, and notifies the author.

    Args:
        file_loc: Pending filename (author+++hexid+++filename format)

    Returns:
        Tuple of (success: bool, message: str)
    """
    parsed = parse_pending_filename(file_loc)
    if not parsed:
        return False, "Invalid file format"

    _, hexid, original_filename = parsed

    try:
        crackme = g_crackmesone_db.crackme.find_one({'hexid': hexid})
        if not crackme:
            return False, "Crackme not found in database"

        # Set visible
        g_crackmesone_db.crackme.update_one(
            {'hexid': hexid},
            {'$set': {'visible': True}}
        )

        # Create archive
        source_path = os.path.join(get_tmp_dir('crackme'), file_loc)
        if not os.path.exists(source_path):
            return False, "Crackme file not found in tmp directory"

        dest_path = os.path.join(get_static_dir('crackme'), hexid)
        success, error = create_password_protected_zip(
            source_path, dest_path, original_filename
        )

        if not success:
            # Revert visibility on failure
            g_crackmesone_db.crackme.update_one(
                {'hexid': hexid},
                {'$set': {'visible': False}}
            )
            return False, error

        # Notify author
        send_user_notification(
            crackme["author"],
            f"Your crackme '{crackme['name']}' has been accepted!"
        )

        return True, f"Crackme '{crackme['name']}' approved successfully"

    except Exception as e:
        return False, f"Error approving crackme: {str(e)}"


def approve_pending_solution(file_loc):
    """
    Approve a pending solution submission.

    Sets the solution as visible, creates a password-protected zip in
    static/solution/, notifies both the solution author and crackme author,
    and increments the crackme's solution count.

    Args:
        file_loc: Pending filename (author+++hexid+++filename format)

    Returns:
        Tuple of (success: bool, message: str)
    """
    parsed = parse_pending_filename(file_loc)
    if not parsed:
        return False, "Invalid file format"

    _, hexid, original_filename = parsed

    try:
        solution = g_crackmesone_db.solution.find_one({'hexid': hexid})
        if not solution:
            return False, "Solution not found in database"

        crackme = g_crackmesone_db.crackme.find_one({
            '_id': solution["crackmeid"]
        })
        if not crackme:
            return False, "Related crackme not found"

        crackme_name = crackme["name"]

        # Set visible
        g_crackmesone_db.solution.update_one(
            {'hexid': hexid},
            {'$set': {'visible': True}}
        )

        # Create archive
        source_path = os.path.join(get_tmp_dir('solution'), file_loc)
        if not os.path.exists(source_path):
            return False, "Solution file not found in tmp directory"

        dest_path = os.path.join(get_static_dir('solution'), hexid)
        success, error = create_password_protected_zip(
            source_path, dest_path, original_filename
        )

        if not success:
            g_crackmesone_db.solution.update_one(
                {'hexid': hexid},
                {'$set': {'visible': False}}
            )
            return False, error

        # Notify solution author
        send_user_notification(
            solution["author"],
            f"Your solution for '{crackme_name}' has been accepted!"
        )

        # Notify crackme author
        send_user_notification(
            crackme["author"],
            f"A new solution for your crackme '{crackme_name}' "
            f"has been submitted by: {solution['author']}"
        )

        return True, f"Solution for '{crackme_name}' approved successfully"

    except Exception as e:
        return False, f"Error approving solution: {str(e)}"


# =============================================================================
# Approved Content Deletion
# =============================================================================

def delete_approved_solution(solution_uuid):
    """
    Delete an already-approved solution.

    Removes the solution from database, deletes the zip file,
    and decrements the crackme's solution count.

    Args:
        solution_uuid: Solution's hex ID

    Returns:
        Status message string
    """
    if not ObjectId.is_valid(solution_uuid):
        return "Invalid UUID format"

    solution = g_crackmesone_db.solution.find_one({
        "_id": ObjectId(solution_uuid)
    })

    if not solution:
        return "Solution not found in database"

    crackme_id = solution.get("crackmeid")
    zip_path = os.path.join(
        get_static_dir('solution'),
        f"{solution_uuid}.zip"
    )

    # Delete zip file (if exists)
    try:
        os.remove(zip_path)
    except Exception:
        pass

    # Delete from database
    g_crackmesone_db.solution.delete_one({"_id": ObjectId(solution_uuid)})

    # Decrement crackme solution count (always, as long as solution was in database)
    if crackme_id:
        try:
            g_crackmesone_db.crackme.update_one(
                {"_id": crackme_id},
                {"$inc": {"nbsolutions": -1}}
            )
        except Exception as e:
            print(f"Error decrementing solution count: {e}")

    return "Solution deleted"


def delete_approved_crackme(crackme_uuid):
    """
    Delete an already-approved crackme with cascade deletion.

    Deletes the crackme, all its solutions, comments, and ratings.

    Args:
        crackme_uuid: Crackme's hex ID

    Returns:
        Status message string with deletion counts
    """
    if not ObjectId.is_valid(crackme_uuid):
        return "Invalid crackme uuid"

    crackme = g_crackmesone_db.crackme.find_one({
        "_id": ObjectId(crackme_uuid)
    })

    if not crackme:
        return "Crackme uuid not found"

    # Cascade delete related data
    deleted = _cascade_delete_crackme_data(
        ObjectId(crackme_uuid),
        crackme_uuid
    )

    # Delete zip file
    try:
        os.remove(os.path.join(
            get_static_dir('crackme'),
            f"{crackme_uuid}.zip"
        ))
    except Exception:
        pass

    # Delete crackme document
    g_crackmesone_db.crackme.delete_one({"_id": ObjectId(crackme_uuid)})

    return (
        f"Cascade deleted: {deleted['solutions']} solutions, "
        f"{deleted['comments']} comments, "
        f"{deleted['difficulty_ratings']} difficulty ratings, "
        f"{deleted['quality_ratings']} quality ratings\n"
        "Crackme deleted"
    )


def _cascade_delete_crackme_data(crackme_id, crackme_hexid):
    """
    Delete all data associated with a crackme.

    Args:
        crackme_id: ObjectId of the crackme
        crackme_hexid: Hex ID string of the crackme

    Returns:
        Dict with counts of deleted items
    """
    deleted = {
        'solutions': 0,
        'comments': 0,
        'difficulty_ratings': 0,
        'quality_ratings': 0
    }

    # Delete solutions
    for solution in g_crackmesone_db.solution.find({'crackmeid': crackme_id}):
        try:
            delete_approved_solution(str(solution["_id"]))
            deleted['solutions'] += 1
        except Exception as e:
            print(f"Warning: Failed to delete solution {solution['_id']}: {e}")

    # Delete comments
    result = g_crackmesone_db.comment.delete_many({
        'crackmehexid': crackme_hexid
    })
    deleted['comments'] = result.deleted_count

    # Delete ratings
    result = g_crackmesone_db.rating_difficulty.delete_many({
        'crackmehexid': crackme_hexid
    })
    deleted['difficulty_ratings'] = result.deleted_count

    result = g_crackmesone_db.rating_quality.delete_many({
        'crackmehexid': crackme_hexid
    })
    deleted['quality_ratings'] = result.deleted_count

    return deleted


# =============================================================================
# User Account Management
# =============================================================================

def reset_user_password(user_email):
    """
    Reset a main site user's password to a random string.

    Args:
        user_email: Email address of the user

    Returns:
        Message string with new password on success, error on failure
    """
    escaped = re.escape(user_email)
    user = g_crackmesone_db.user.find_one({
        "email": {"$regex": f"^{escaped}$", "$options": "i"}
    })

    if not user:
        return "Error: No user with the email found in database"

    # Generate random password
    chars = string.ascii_letters + string.digits
    plain_password = ''.join(random.choices(chars, k=16))
    hashed = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())

    result = g_crackmesone_db.user.update_one(
        {"email": {"$regex": f"^{escaped}$", "$options": "i"}},
        {"$set": {"password": hashed.decode('utf-8')}}
    )

    if result.modified_count != 1:
        return "Error: Password update failed"

    return (
        f"Password reset successful.\n"
        f"Name: {user.get('name')}\n"
        f"Email: {user.get('email')}\n"
        f"New password: {plain_password}"
    )


def preview_user_deletion(user_email):
    """
    Preview what would be deleted if a user account is deleted.

    Args:
        user_email: Email address of the user

    Returns:
        Tuple of (preview_dict, error_string)
    """
    user = find_user_by_email_or_name(user_email)
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
        db = g_crackmesone_db

        preview['notifications'] = db.notifications.count_documents({
            "user": username
        })
        preview['solutions'] = db.solution.count_documents({
            "author": username
        })

        # Count data for each crackme
        for crackme in db.crackme.find({"author": username}):
            hexid = crackme.get("hexid")
            cid = crackme.get("_id")

            if hexid and cid:
                detail = {
                    'name': crackme.get("name", "Unnamed"),
                    'hexid': hexid,
                    'solutions': db.solution.count_documents({"crackmeid": cid}),
                    'comments': db.comment.count_documents({"crackmehexid": hexid}),
                    'difficulty_ratings': db.rating_difficulty.count_documents({
                        "crackmehexid": hexid
                    }),
                    'quality_ratings': db.rating_quality.count_documents({
                        "crackmehexid": hexid
                    })
                }
                preview['crackme_details'].append(detail)
                preview['total_solutions_on_user_crackmes'] += detail['solutions']
                preview['total_comments'] += detail['comments']

        preview['crackmes'] = len(preview['crackme_details'])

        # User's comments on other crackmes
        user_hexids = [c['hexid'] for c in preview['crackme_details']]
        if user_hexids:
            preview['user_comments'] = db.comment.count_documents({
                "author": username,
                "crackmehexid": {"$nin": user_hexids}
            })
        else:
            preview['user_comments'] = db.comment.count_documents({
                "author": username
            })

        preview['total_comments'] += preview['user_comments']
        preview['difficulty_ratings'] = db.rating_difficulty.count_documents({
            "author": username
        })
        preview['quality_ratings'] = db.rating_quality.count_documents({
            "author": username
        })

        return preview, None

    except Exception as e:
        return None, f"Error previewing deletion: {str(e)}"


def delete_user_account(user_email, admin_username=None):
    """
    Delete a main site user account and all associated data.

    Deletes: notifications, solutions, crackmes (with cascade),
    comments, ratings. Recalculates affected crackme ratings.

    Args:
        user_email: Email address of the user to delete
        admin_username: Username of admin performing deletion (for logging)

    Returns:
        Status message string
    """
    escaped = re.escape(user_email)
    user = g_crackmesone_db.user.find_one({
        "email": {"$regex": f"^{escaped}$", "$options": "i"}
    })

    if not user:
        return "Error: No user found with this email address."

    username = user.get("name")
    if not username:
        return "Error: User has no username."

    db = g_crackmesone_db
    deletion_log = []
    cascade_stats = {
        'solutions_on_user_crackmes': 0,
        'comments_on_user_crackmes': 0
    }

    try:
        # 1. Delete notifications
        result = db.notifications.delete_many({"user": username})
        deletion_log.append(f"Deleted {result.deleted_count} notifications")

        # 2. Delete user's solutions
        solution_count = 0
        for solution in db.solution.find({"author": username}):
            delete_approved_solution(str(solution["_id"]))
            solution_count += 1
        deletion_log.append(f"Deleted {solution_count} solutions by user")

        # 3. Delete user's crackmes with cascade
        crackmes = list(db.crackme.find({"author": username}))
        user_hexids = []
        crackme_count = 0

        for crackme in crackmes:
            hexid = crackme.get("hexid")
            if hexid:
                user_hexids.append(hexid)
                cid = crackme.get("_id")
                if cid:
                    cascade_stats['solutions_on_user_crackmes'] += \
                        db.solution.count_documents({"crackmeid": cid})
                    cascade_stats['comments_on_user_crackmes'] += \
                        db.comment.count_documents({"crackmehexid": hexid})
                delete_approved_crackme(hexid)
                crackme_count += 1

        deletion_log.append(f"Deleted {crackme_count} crackmes by user")
        deletion_log.append(
            f"  -> Cascade deleted {cascade_stats['solutions_on_user_crackmes']} "
            "solutions on user's crackmes"
        )
        deletion_log.append(
            f"  -> Cascade deleted {cascade_stats['comments_on_user_crackmes']} "
            "comments on user's crackmes"
        )

        # 4. Delete user's comments on other crackmes
        comments_to_delete = list(db.comment.find({
            "author": username,
            "crackmehexid": {"$nin": user_hexids}
        })) if user_hexids else list(db.comment.find({"author": username}))

        # Track per-crackme counts for counter updates
        comment_counts = {}
        for comment in comments_to_delete:
            hexid = comment.get("crackmehexid")
            if hexid:
                comment_counts[hexid] = comment_counts.get(hexid, 0) + 1

        if user_hexids:
            result = db.comment.delete_many({
                "author": username,
                "crackmehexid": {"$nin": user_hexids}
            })
        else:
            result = db.comment.delete_many({"author": username})
        deletion_log.append(
            f"Deleted {result.deleted_count} comments by user on other crackmes"
        )

        # Update comment counters
        for hexid, count in comment_counts.items():
            try:
                db.crackme.update_one(
                    {"_id": ObjectId(hexid)},
                    {"$inc": {"nbcomments": -count}}
                )
            except Exception:
                pass

        # 5-6. Delete ratings and track affected crackmes
        difficulty_crackmes = set()
        for rating in db.rating_difficulty.find({"author": username}):
            hexid = rating.get("crackmehexid")
            if hexid and hexid not in user_hexids:
                difficulty_crackmes.add(hexid)

        diff_result = db.rating_difficulty.delete_many({"author": username})
        deletion_log.append(
            f"Deleted {diff_result.deleted_count} difficulty ratings by user"
        )

        quality_crackmes = set()
        for rating in db.rating_quality.find({"author": username}):
            hexid = rating.get("crackmehexid")
            if hexid and hexid not in user_hexids:
                quality_crackmes.add(hexid)

        qual_result = db.rating_quality.delete_many({"author": username})
        deletion_log.append(
            f"Deleted {qual_result.deleted_count} quality ratings by user"
        )

        # 7-8. Recalculate ratings for affected crackmes
        recalc_diff = _recalculate_ratings(
            db.rating_difficulty, db.crackme, difficulty_crackmes, 'difficulty'
        )
        recalc_qual = _recalculate_ratings(
            db.rating_quality, db.crackme, quality_crackmes, 'quality'
        )
        deletion_log.append(f"Recalculated difficulty for {recalc_diff} crackmes")
        deletion_log.append(f"Recalculated quality for {recalc_qual} crackmes")

        # 9. Delete user account
        result = db.user.delete_one({"_id": user["_id"]})
        if result.deleted_count != 1:
            return "Error: Failed to delete user account"
        deletion_log.append(f"Deleted user account: {username} ({user_email})")

        # 10. Log operation
        if admin_username:
            log_reviewer_operation(
                "delete_user_account",
                admin_username,
                {
                    "deleted_user": username,
                    "email": user_email,
                    "crackmes": crackme_count,
                    "solutions": solution_count,
                    "difficulty_ratings": diff_result.deleted_count,
                    "quality_ratings": qual_result.deleted_count
                },
                success=True
            )

        return "User account deletion successful!\n" + "\n".join(deletion_log)

    except Exception as e:
        return f"Error during deletion: {str(e)}"


def _recalculate_ratings(rating_collection, crackme_collection, hexids, field):
    """
    Recalculate average ratings for affected crackmes.

    Args:
        rating_collection: MongoDB collection for ratings
        crackme_collection: MongoDB collection for crackmes
        hexids: Set of crackme hex IDs to recalculate
        field: Field name to update ('difficulty' or 'quality')

    Returns:
        Number of crackmes recalculated
    """
    count = 0
    for hexid in hexids:
        if not hexid:
            continue
        ratings = list(rating_collection.find({"crackmehexid": hexid}))
        if ratings:
            avg = sum(r["rating"] for r in ratings) / len(ratings)
        else:
            avg = 0.0
        crackme_collection.update_one(
            {"hexid": hexid},
            {"$set": {field: avg}}
        )
        count += 1
    return count


# =============================================================================
# Route Handlers - Authentication
# =============================================================================

@reviewer_bp.route('/')
def index():
    """Redirect root to login page."""
    return redirect(url_for('reviewer.login'))


@reviewer_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handle reviewer login.

    GET: Display login form
    POST: Validate credentials and create session
    """
    if session.get(REVIEWER_SESSION_KEY):
        return redirect(url_for('reviewer.dashboard'))

    if request.method == 'POST':
        validate_csrf_token()
        username = request.form.get('username')
        password = request.form.get('password')

        expected_hash = users.get(username, {}).get("password_hash")
        if expected_hash and expected_hash == hash_string(password + PASSWORD_SALT):
            session[REVIEWER_SESSION_KEY] = username
            session[REVIEWER_ADMIN_KEY] = users[username].get("is_admin", False)
            return redirect(url_for('reviewer.dashboard'))

        return render_template('reviewer/login.html', error='Invalid credentials')

    return render_template('reviewer/login.html')


@reviewer_bp.route('/logout')
def logout():
    """Log out and redirect to login page."""
    clear_reviewer_session()
    return redirect(url_for('reviewer.login'))


# =============================================================================
# Route Handlers - Dashboard
# =============================================================================

@reviewer_bp.route('/dashboard')
@token_required
def dashboard(current_user):
    """Display dashboard with pending submission counts."""
    return render_template(
        'reviewer/dashboard.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        solution_cnt=count_pending_items('solution'),
        crackme_cnt=count_pending_items('crackme')
    )


# =============================================================================
# Route Handlers - Review Pending Submissions
# =============================================================================

@reviewer_bp.route('/reviewsolution')
@token_required
def reviewsolution(current_user):
    """Display list of pending solutions for review."""
    solutions, error = get_pending_solutions()
    message = request.args.get('message') or error
    return render_template(
        'reviewer/reviewsolution.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        solutions=solutions,
        message=message
    )


@reviewer_bp.route('/viewsolution')
@token_required
def viewsolution(current_user):
    """Display details of a pending solution."""
    solution_uuid = request.args.get("solution_uuid")
    if not solution_uuid:
        return redirect(url_for('reviewer.dashboard'))

    solution, error = get_solution_details(solution_uuid)
    if error:
        return error

    return render_template(
        'reviewer/viewsolution.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        solution=solution
    )


@reviewer_bp.route('/reviewcrackme')
@token_required
def reviewcrackme(current_user):
    """Display list of pending crackmes for review."""
    crackmes, error = get_pending_crackmes()
    message = request.args.get('message') or error
    return render_template(
        'reviewer/reviewcrackme.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        crackmes=crackmes,
        message=message
    )


@reviewer_bp.route('/viewcrackme')
@token_required
def viewcrackme(current_user):
    """Display details of a pending crackme."""
    crackme_uuid = request.args.get("crackme_uuid")
    if not crackme_uuid:
        return redirect(url_for('reviewer.dashboard'))

    crackme, error = get_crackme_details(crackme_uuid)
    if error:
        return error

    return render_template(
        'reviewer/viewcrackme.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        crackme=crackme
    )


@reviewer_bp.route('/downloadreview')
@token_required
def downloadreview(current_user):
    """Download a pending submission file for review."""
    download_type = request.args.get("type")
    uuid = request.args.get("uuid")

    if download_type not in ('solution', 'crackme'):
        abort(404)

    tmp_dir = get_tmp_dir(download_type)
    if not os.path.exists(tmp_dir):
        abort(404)

    for filename in os.listdir(tmp_dir):
        parsed = parse_pending_filename(filename)
        if parsed and parsed[1] == uuid:
            return send_file(
                os.path.join(tmp_dir, filename),
                as_attachment=True
            )

    abort(404)


# =============================================================================
# Route Handlers - Approve/Reject Submissions
# =============================================================================

@reviewer_bp.route('/rejectsolution', methods=['POST'])
@token_required
def rejectsolution(current_user):
    """Reject a pending solution submission."""
    validate_csrf_token()
    solution_uuid = request.form.get('uuid')
    reject_reason = request.form.get('reject_reason')

    solution_file = find_pending_file('solution', solution_uuid)

    if not solution_file:
        log_reviewer_operation(
            "reject_solution", current_user['username'],
            {"solution_uuid": solution_uuid, "error": "File not found"},
            False
        )
        return redirect(url_for(
            'reviewer.reviewsolution',
            message="Solution file not found"
        ))

    success, message = reject_pending_solution(solution_file, reject_reason)

    log_reviewer_operation(
        "reject_solution", current_user['username'],
        {
            "solution_uuid": solution_uuid,
            "reject_reason": reject_reason,
            "result": message
        },
        success
    )

    return redirect(url_for('reviewer.reviewsolution', message=message))


@reviewer_bp.route('/approvesolution', methods=['POST'])
@token_required
def approvesolution(current_user):
    """Approve a pending solution submission."""
    validate_csrf_token()
    solution_uuid = request.form.get('uuid')

    solution_file = find_pending_file('solution', solution_uuid)

    if not solution_file:
        log_reviewer_operation(
            "approve_solution", current_user['username'],
            {"solution_uuid": solution_uuid, "error": "File not found"},
            False
        )
        return redirect(url_for(
            'reviewer.reviewsolution',
            message="Solution file not found"
        ))

    success, message = approve_pending_solution(solution_file)

    log_reviewer_operation(
        "approve_solution", current_user['username'],
        {"solution_uuid": solution_uuid, "result": message},
        success
    )

    if success:
        solution, _ = get_solution_details(solution_uuid)
        if solution:
            notify_solution_approved(
                solution["crackme_name"],
                solution["crackme_uuid"],
                solution_uuid,
                solution["solution_author"]
            )
            # Increment solution counter
            try:
                g_crackmesone_db.crackme.update_one(
                    {"_id": ObjectId(solution["crackme_uuid"])},
                    {"$inc": {"nbsolutions": 1}}
                )
            except Exception as e:
                print(f"Error incrementing solution count: {e}")

    return redirect(url_for('reviewer.reviewsolution', message=message))


@reviewer_bp.route('/rejectcrackme', methods=['POST'])
@token_required
def rejectcrackme(current_user):
    """Reject a pending crackme submission."""
    validate_csrf_token()
    crackme_uuid = request.form.get('uuid')
    reject_reason = request.form.get('reject_reason')

    crackme_file = find_pending_file('crackme', crackme_uuid)

    if not crackme_file:
        log_reviewer_operation(
            "reject_crackme", current_user['username'],
            {"crackme_uuid": crackme_uuid, "error": "File not found"},
            False
        )
        return redirect(url_for(
            'reviewer.reviewcrackme',
            message="Crackme file not found"
        ))

    success, message = reject_pending_crackme(crackme_file, reject_reason)

    log_reviewer_operation(
        "reject_crackme", current_user['username'],
        {
            "crackme_uuid": crackme_uuid,
            "reject_reason": reject_reason,
            "result": message
        },
        success
    )

    return redirect(url_for('reviewer.reviewcrackme', message=message))


@reviewer_bp.route('/approvecrackme', methods=['POST'])
@token_required
def approvecrackme(current_user):
    """Approve a pending crackme submission."""
    validate_csrf_token()
    crackme_uuid = request.form.get('uuid')

    crackme_file = find_pending_file('crackme', crackme_uuid)

    if not crackme_file:
        log_reviewer_operation(
            "approve_crackme", current_user['username'],
            {"crackme_uuid": crackme_uuid, "error": "File not found"},
            False
        )
        return redirect(url_for(
            'reviewer.reviewcrackme',
            message="Crackme file not found"
        ))

    success, message = approve_pending_crackme(crackme_file)

    log_reviewer_operation(
        "approve_crackme", current_user['username'],
        {"crackme_uuid": crackme_uuid, "result": message},
        success
    )

    if success:
        crackme, _ = get_crackme_details(crackme_uuid)
        if crackme:
            notify_crackme_approved(
                crackme["name"],
                crackme_uuid,
                crackme["author"]
            )

    return redirect(url_for('reviewer.reviewcrackme', message=message))


# =============================================================================
# Route Handlers - Admin: Delete Approved Content
# =============================================================================

@reviewer_bp.route('/deletesolution', methods=['GET', 'POST'])
@admin_required
def deletesolution(current_user):
    """Delete an already-approved solution (admin only)."""
    message = None
    if request.method == 'POST':
        validate_csrf_token()
        solution_uuid = request.form.get('solution_uuid')
        message = delete_approved_solution(solution_uuid)

        log_reviewer_operation(
            "delete_solution_admin", current_user['username'],
            {"solution_uuid": solution_uuid, "result": message},
            "deleted" in message.lower()
        )

    return render_template(
        'reviewer/delsolution.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        message=message
    )


@reviewer_bp.route('/deletecrackme', methods=['GET', 'POST'])
@admin_required
def deletecrackme(current_user):
    """Delete an already-approved crackme (admin only)."""
    message = None
    if request.method == 'POST':
        validate_csrf_token()
        crackme_uuid = request.form.get('crackme_uuid')
        message = delete_approved_crackme(crackme_uuid)

        log_reviewer_operation(
            "delete_crackme_admin", current_user['username'],
            {"crackme_uuid": crackme_uuid, "result": message},
            "deleted" in message.lower()
        )

    return render_template(
        'reviewer/delcrackme.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        message=message
    )


@reviewer_bp.route('/editcrackme', methods=['GET', 'POST'])
@admin_required
def editcrackme(current_user):
    """Edit an approved crackme (admin only).

    Allows editing crackme metadata and optionally replacing the file.
    """
    message = None
    error = None
    crackme = None

    crackme_uuid = request.args.get('crackme_uuid') or request.form.get('crackme_uuid')

    if request.method == 'POST' and crackme_uuid:
        validate_csrf_token()

        # Get form data (name is not editable)
        info = request.form.get('info', '').strip()
        lang = request.form.get('lang', '')
        arch = request.form.get('arch', '')
        platform = request.form.get('platform', '')
        notify_author = request.form.get('notify_author') == 'on'

        if True:
            # Get current crackme
            crackme_obj = g_crackmesone_db.crackme.find_one({
                "_id": ObjectId(crackme_uuid)
            })

            if not crackme_obj:
                error = "Crackme not found"
            else:
                # Track changes (name is not editable)
                changes = []
                if crackme_obj.get('info') != info:
                    changes.append("description updated")
                if crackme_obj.get('lang') != lang:
                    changes.append(f"language: '{crackme_obj.get('lang')}' -> '{lang}'")
                if crackme_obj.get('arch') != arch:
                    changes.append(f"arch: '{crackme_obj.get('arch')}' -> '{arch}'")
                if crackme_obj.get('platform') != platform:
                    changes.append(f"platform: '{crackme_obj.get('platform')}' -> '{platform}'")

                # Update the crackme (name excluded)
                g_crackmesone_db.crackme.update_one(
                    {"_id": ObjectId(crackme_uuid)},
                    {"$set": {
                        "info": info,
                        "lang": lang,
                        "arch": arch,
                        "platform": platform
                    }}
                )

                # Handle file replacement
                file_replaced = False
                if 'file' in request.files:
                    file = request.files['file']
                    if file.filename:
                        file_data = file.read()
                        if len(file_data) > 0:
                            # Save to temp location
                            temp_path = os.path.join(
                                CRACKMESONE_DIR, 'tmp',
                                f"replace_{crackme_uuid}_{file.filename}"
                            )
                            os.makedirs(os.path.dirname(temp_path), exist_ok=True)

                            with open(temp_path, 'wb') as f:
                                f.write(file_data)

                            # Create password-protected zip
                            dest_path = os.path.join(
                                get_static_dir('crackme'),
                                crackme_obj['hexid']
                            )

                            # Remove old zip first
                            old_zip = dest_path + ".zip"
                            if os.path.exists(old_zip):
                                os.remove(old_zip)

                            success, zip_error = create_password_protected_zip(
                                temp_path, dest_path, file.filename
                            )

                            if success:
                                file_replaced = True
                                changes.append("file replaced")
                            else:
                                error = f"Failed to replace file: {zip_error}"

                if changes:
                    # Log the operation
                    log_reviewer_operation(
                        "edit_crackme_admin", current_user['username'],
                        {
                            "crackme_uuid": crackme_uuid,
                            "crackme_name": crackme_obj.get('name'),
                            "changes": changes
                        },
                        True
                    )

                    # Notify author if requested
                    if notify_author and not error:
                        try:
                            change_summary = ", ".join(changes[:3])
                            if len(changes) > 3:
                                change_summary += f" and {len(changes) - 3} more"
                            send_user_notification(
                                crackme_obj['author'],
                                f"Your crackme '{crackme_obj.get('name')}' has been updated by an admin: {change_summary}"
                            )
                        except Exception as e:
                            print(f"Notification error: {e}")

                    if not error:
                        message = f"Crackme '{crackme_obj.get('name')}' updated successfully"
                else:
                    message = "No changes were made"

    # Load crackme for display
    if crackme_uuid and ObjectId.is_valid(crackme_uuid):
        crackme_obj = g_crackmesone_db.crackme.find_one({
            "_id": ObjectId(crackme_uuid)
        })
        if crackme_obj:
            crackme = {
                "hexid": crackme_obj['hexid'],
                "name": crackme_obj.get('name', ''),
                "info": crackme_obj.get('info', ''),
                "lang": crackme_obj.get('lang', ''),
                "arch": crackme_obj.get('arch', ''),
                "platform": crackme_obj.get('platform', ''),
                "author": crackme_obj.get('author', '')
            }
        else:
            error = "Crackme not found"

    return render_template(
        'reviewer/editcrackme.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        crackme=crackme,
        message=message,
        error=error
    )


@reviewer_bp.route('/delcomment', methods=['GET', 'POST'])
@admin_required
def delcomment(current_user):
    """Manage comments on a crackme - delete or toggle spoiler (admin only)."""
    crackme_uuid = None
    error = None

    if request.method == 'POST':
        validate_csrf_token()
        crackme_uuid = request.form.get('crackme_uuid')
        comment_uuid = request.form.get('comment_uuid')
        action = request.form.get('action')

        if action == 'delete' and comment_uuid:
            comment = g_crackmesone_db.comment.find_one({
                "_id": ObjectId(comment_uuid)
            })
            comment_hexid = comment.get("crackmehexid") if comment else None

            result = g_crackmesone_db.comment.delete_one({
                "_id": ObjectId(comment_uuid)
            })

            # Decrement counter
            if result.deleted_count > 0 and comment_hexid:
                try:
                    g_crackmesone_db.crackme.update_one(
                        {"_id": ObjectId(comment_hexid)},
                        {"$inc": {"nbcomments": -1}}
                    )
                except Exception as e:
                    print(f"Error decrementing comment count: {e}")

            log_reviewer_operation(
                "delete_comment", current_user['username'],
                {
                    "comment_uuid": comment_uuid,
                    "crackme_uuid": crackme_uuid,
                    "deleted_count": result.deleted_count
                },
                bool(result.deleted_count)
            )

            if not result.deleted_count:
                error = "Failed to delete comment"

        elif action == 'toggle_spoiler' and comment_uuid:
            comment = g_crackmesone_db.comment.find_one({
                "_id": ObjectId(comment_uuid)
            })

            if comment:
                current_spoiler = comment.get('spoiler', False)
                new_spoiler = not current_spoiler

                g_crackmesone_db.comment.update_one(
                    {"_id": ObjectId(comment_uuid)},
                    {"$set": {"spoiler": new_spoiler}}
                )

                log_reviewer_operation(
                    "toggle_comment_spoiler", current_user['username'],
                    {
                        "comment_uuid": comment_uuid,
                        "crackme_uuid": crackme_uuid,
                        "new_spoiler_status": new_spoiler
                    },
                    True
                )
            else:
                error = "Comment not found"
    else:
        crackme_uuid = request.args.get("crackme_uuid")

    # Load comments for display
    comments = None
    if crackme_uuid:
        if ObjectId.is_valid(crackme_uuid):
            crackme = g_crackmesone_db.crackme.find_one({
                "_id": ObjectId(crackme_uuid)
            })
            if crackme:
                comments = [
                    {
                        'comment_uuid': str(c["_id"]),
                        'author': c["author"],
                        'content': c["info"],
                        'spoiler': c.get("spoiler", False)
                    }
                    for c in g_crackmesone_db.comment.find({
                        'crackmehexid': crackme_uuid
                    })
                ]
            else:
                error = "Crackme not found"
        else:
            error = "Wrong crackme UUID"

    return render_template(
        'reviewer/delcomment.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        comments=comments,
        crackme_uuid=crackme_uuid,
        error=error
    )


# =============================================================================
# Route Handlers - Admin: User Management
# =============================================================================

@reviewer_bp.route('/resetuserpassword', methods=['GET', 'POST'])
@admin_required
def resetuserpassword(current_user):
    """Reset a main site user's password (admin only)."""
    message = None
    if request.method == 'POST':
        validate_csrf_token()
        user_email = request.form.get('user_email')
        message = reset_user_password(user_email)

        log_reviewer_operation(
            "reset_user_password", current_user['username'],
            {
                "target_user_email": user_email,
                "result": "success" if "successful" in message.lower() else "failed"
            },
            "successful" in message.lower()
        )

    return render_template(
        'reviewer/resetuserpassword.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        message=message
    )


@reviewer_bp.route('/lookupuser', methods=['GET', 'POST'])
@admin_required
def lookupuser(current_user):
    """Look up main site user information (admin only)."""
    user_info = None
    message = None
    show_all = False
    all_data = None

    if request.method == 'POST':
        validate_csrf_token()
        search_query = request.form.get('search_query', '').strip()
        show_all = request.form.get('show_all') == '1'

        if search_query:
            user = find_user_by_email_or_name(search_query)

            if user:
                username = user.get("name")
                db = g_crackmesone_db

                # Extract registration time from ObjectId
                registration_time = None
                if user.get("_id"):
                    try:
                        registration_time = user["_id"].generation_time
                    except Exception:
                        pass

                user_info = {
                    'username': username,
                    'email': user.get("email"),
                    'is_admin': user.get("is_admin", False),
                    'registration_time': registration_time,
                    'crackmes_count': db.crackme.count_documents({"author": username}),
                    'solutions_count': db.solution.count_documents({"author": username}),
                    'comments_count': db.comment.count_documents({"author": username}),
                    'difficulty_ratings_count': db.rating_difficulty.count_documents({
                        "author": username
                    }),
                    'quality_ratings_count': db.rating_quality.count_documents({
                        "author": username
                    }),
                    'notifications_count': db.notifications.count_documents({
                        "user": username
                    })
                }

                # Fetch all detailed data if requested
                if show_all:
                    all_data = _fetch_all_user_data(db, username)

                log_reviewer_operation(
                    "lookup_user", current_user['username'],
                    {"search_query": search_query, "found_user": username,
                     "show_all": show_all},
                    True
                )
            else:
                message = f"No user found with email or username: {search_query}"
                log_reviewer_operation(
                    "lookup_user", current_user['username'],
                    {"search_query": search_query, "result": "not_found"},
                    False
                )
        else:
            message = "Please enter an email or username to search."

    return render_template(
        'reviewer/lookupuser.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        user_info=user_info,
        message=message,
        show_all=show_all,
        all_data=all_data
    )


def _fetch_all_user_data(db, username):
    """Fetch all detailed data for a user.

    Args:
        db: Database connection
        username: Username to fetch data for

    Returns:
        Dictionary containing all user data with URLs
    """
    # Fetch crackmes
    crackmes_raw = list(db.crackme.find(
        {"author": username},
        {"hexid": 1, "name": 1, "visible": 1, "created_at": 1}
    ).sort("created_at", -1))

    crackmes = []
    for cm in crackmes_raw:
        crackmes.append({
            "hexid": cm.get("hexid"),
            "name": cm.get("name"),
            "visible": cm.get("visible", False),
            "date": cm.get("created_at")
        })

    # Fetch solutions with crackme info
    solutions_raw = list(db.solution.find(
        {"author": username},
        {"hexid": 1, "crackmeid": 1, "visible": 1, "created_at": 1}
    ).sort("created_at", -1))

    solutions = []
    for sol in solutions_raw:
        crackme = db.crackme.find_one(
            {"_id": sol.get("crackmeid")},
            {"hexid": 1, "name": 1}
        )
        solutions.append({
            "hexid": sol.get("hexid"),
            "crackme_hexid": crackme.get("hexid") if crackme else None,
            "crackme_name": crackme.get("name") if crackme else "Unknown",
            "visible": sol.get("visible", False),
            "date": sol.get("created_at")
        })

    # Fetch comments with crackme info
    comments_raw = list(db.comment.find(
        {"author": username},
        {"crackmehexid": 1, "info": 1, "created_at": 1}
    ).sort("created_at", -1))

    comments = []
    for comm in comments_raw:
        crackme = db.crackme.find_one(
            {"hexid": comm.get("crackmehexid")},
            {"name": 1}
        )
        comment_text = comm.get("info", "")
        comments.append({
            "crackme_hexid": comm.get("crackmehexid"),
            "crackme_name": crackme.get("name") if crackme else "Unknown",
            "comment": comment_text[:100] + ("..." if len(comment_text) > 100 else ""),
            "date": comm.get("created_at")
        })

    # Fetch difficulty ratings with crackme info
    diff_ratings_raw = list(db.rating_difficulty.find(
        {"author": username},
        {"crackmehexid": 1, "rating": 1, "created_at": 1}
    ).sort("created_at", -1))

    diff_ratings = []
    for rating in diff_ratings_raw:
        crackme = db.crackme.find_one(
            {"hexid": rating.get("crackmehexid")},
            {"name": 1}
        )
        diff_ratings.append({
            "crackme_hexid": rating.get("crackmehexid"),
            "crackme_name": crackme.get("name") if crackme else "Unknown",
            "value": rating.get("rating"),
            "date": rating.get("created_at")
        })

    # Fetch quality ratings with crackme info
    qual_ratings_raw = list(db.rating_quality.find(
        {"author": username},
        {"crackmehexid": 1, "rating": 1, "created_at": 1}
    ).sort("created_at", -1))

    qual_ratings = []
    for rating in qual_ratings_raw:
        crackme = db.crackme.find_one(
            {"hexid": rating.get("crackmehexid")},
            {"name": 1}
        )
        qual_ratings.append({
            "crackme_hexid": rating.get("crackmehexid"),
            "crackme_name": crackme.get("name") if crackme else "Unknown",
            "value": rating.get("rating"),
            "date": rating.get("created_at")
        })

    # Fetch all notifications (no limit)
    notifications = list(db.notifications.find(
        {"user": username},
        {"text": 1, "time": 1, "seen": 1}
    ).sort("time", -1))

    return {
        "crackmes": crackmes,
        "solutions": solutions,
        "comments": comments,
        "difficulty_ratings": diff_ratings,
        "quality_ratings": qual_ratings,
        "notifications": notifications
    }


@reviewer_bp.route('/deleteuser', methods=['GET', 'POST'])
@admin_required
def deleteuser(current_user):
    """Delete a main site user account (admin only)."""
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
                    message = "Error: Email addresses do not match."
            else:
                message = "Error: Both email fields are required."

        elif action == 'confirm_delete':
            user_email = request.form.get('confirmed_email', '').strip()
            if user_email:
                message = delete_user_account(
                    user_email,
                    admin_username=current_user['username']
                )
            else:
                message = "Error: User email not found. Please start over."

    return render_template(
        'reviewer/deleteuser.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        message=message,
        preview=preview_data
    )


# =============================================================================
# Route Handlers - Admin: Reviewer Management
# =============================================================================

@reviewer_bp.route('/managereviewers', methods=['GET', 'POST'])
@admin_required
def managereviewers(current_user):
    """Manage reviewer accounts (admin only)."""
    global users
    message = None

    if request.method == 'POST':
        validate_csrf_token()
        action = request.form.get('action')

        if action == 'add':
            message = _handle_add_reviewer(current_user)
        elif action == 'delete':
            message = _handle_delete_reviewer(current_user)
        elif action == 'toggle_admin':
            message = _handle_toggle_admin(current_user)
        elif action == 'change_password':
            message = _handle_change_password(current_user)

    # Prepare reviewer list
    reviewers = sorted([
        {
            'username': username,
            'is_admin': info.get('is_admin', False),
            'is_current_user': username == current_user['username']
        }
        for username, info in users.items()
    ], key=lambda x: x['username'])

    return render_template(
        'reviewer/managereviewers.html',
        user=current_user['username'],
        is_admin=current_user['is_admin'],
        reviewers=reviewers,
        message=message
    )


def _handle_add_reviewer(current_user):
    """Handle adding a new reviewer account."""
    new_username = request.form.get('new_username', '').strip()
    new_password = request.form.get('new_password', '').strip()
    is_admin = request.form.get('is_admin') == 'on'

    if not new_username or not new_password:
        return "Error: Username and password are required."
    if new_username in users:
        return f"Error: Reviewer '{new_username}' already exists."

    users[new_username] = {
        "password_hash": hash_string(new_password + PASSWORD_SALT),
        "is_admin": is_admin
    }

    try:
        save_users()
        log_reviewer_operation(
            "add_reviewer", current_user['username'],
            {"new_reviewer": new_username, "is_admin": is_admin},
            True
        )
        return f"Success: Reviewer '{new_username}' added successfully."
    except Exception as e:
        del users[new_username]
        return f"Error saving to file: {str(e)}"


def _handle_delete_reviewer(current_user):
    """Handle deleting a reviewer account."""
    username = request.form.get('username_to_delete')

    if not username:
        return "Error: No username specified for deletion."
    if username == current_user['username']:
        return "Error: You cannot delete your own account."
    if username not in users:
        return f"Error: Reviewer '{username}' not found."

    deleted_info = users[username]
    del users[username]

    try:
        save_users()
        log_reviewer_operation(
            "delete_reviewer", current_user['username'],
            {
                "deleted_reviewer": username,
                "was_admin": deleted_info.get('is_admin', False)
            },
            True
        )
        return f"Success: Reviewer '{username}' deleted successfully."
    except Exception as e:
        users[username] = deleted_info
        return f"Error saving to file: {str(e)}"


def _handle_toggle_admin(current_user):
    """Handle toggling a reviewer's admin status."""
    username = request.form.get('username_to_toggle')

    if not username:
        return "Error: No username specified."
    if username == current_user['username']:
        return "Error: You cannot modify your own admin status."
    if username not in users:
        return f"Error: Reviewer '{username}' not found."

    old_status = users[username].get('is_admin', False)
    users[username]['is_admin'] = not old_status
    new_status = users[username]['is_admin']

    try:
        save_users()
        status_text = "admin" if new_status else "regular reviewer"
        log_reviewer_operation(
            "toggle_reviewer_admin", current_user['username'],
            {
                "target_reviewer": username,
                "old_status": old_status,
                "new_status": new_status
            },
            True
        )
        return f"Success: '{username}' is now a {status_text}."
    except Exception as e:
        users[username]['is_admin'] = old_status
        return f"Error saving to file: {str(e)}"


def _handle_change_password(current_user):
    """Handle changing a reviewer's password."""
    username = request.form.get('username_to_change')
    new_password = request.form.get('change_password', '').strip()

    if not username:
        return "Error: No username specified."
    if not new_password:
        return "Error: New password cannot be empty."
    if username not in users:
        return f"Error: Reviewer '{username}' not found."

    users[username]['password_hash'] = hash_string(new_password + PASSWORD_SALT)

    try:
        save_users()
        log_reviewer_operation(
            "change_reviewer_password", current_user['username'],
            {"target_reviewer": username},
            True
        )
        return f"Success: Password changed for '{username}'."
    except Exception as e:
        return f"Error saving to file: {str(e)}"
