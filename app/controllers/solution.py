"""
Solution controller - Solution uploading and viewing.
"""

import os
from html import escape as html_escape
from flask import Blueprint, render_template, request, redirect, flash, session, abort, current_app
from werkzeug.utils import secure_filename
import bleach
from app.models.crackme import crackme_by_hexid
from app.models.solution import solution_create, solution_exists, solution_by_hexid
from app.models.notification import notification_add
from app.models.errors import ErrNoResult
from app.services.recaptcha import verify as verify_recaptcha
from app.services.limiter import limit
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, is_valid_hexid
from app.services.archive import is_archive_password_protected, is_pe_file, is_single_file_archive, is_unsupported_archive
from app.services.discord import notify_new_solution
from app.services.crypto import get_obfuscation_key_base64, get_obfuscation_salt
from app.controllers.decorators import login_required

solution_bp = Blueprint('solution', __name__)

UPLOAD_FOLDER = 'tmp/solution'
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_INFO_LENGTH = 200
MAX_CONTENT_LENGTH = 50000
MIN_CONTENT_LENGTH = 200


def _get_crackme_or_abort(hexid):
    """Fetch crackme by hexid, abort with 404/500 on error."""
    if not is_valid_hexid(hexid):
        abort(404)
    try:
        return crackme_by_hexid(hexid)
    except ErrNoResult:
        abort(404)
    except Exception as e:
        print(f"Error getting crackme: {e}")
        abort(500)


def _get_solution_or_abort(hexid):
    """Fetch solution by hexid, abort with 404/500 on error."""
    if not is_valid_hexid(hexid):
        abort(404)
    try:
        return solution_by_hexid(hexid)
    except ErrNoResult:
        abort(404)
    except Exception as e:
        print(f"Error getting solution: {e}")
        abort(500)


def _send_notifications_and_render_success(username, crackme):
    """Send notifications and render the success page after solution creation."""
    try:
        notification_add(username, f"Your solution for '{html_escape(crackme['name'])}' is waiting approval!")
        notify_new_solution(username, crackme['name'])
    except Exception as e:
        print(f"Notification error: {e}")

    return render_template('submission/success.html',
                           submission_type='Writeup',
                           name=crackme['name'],
                           username=username)


@solution_bp.route('/upload/solution/<hexidcrackme>', methods=['GET'])
@login_required
def upload_solution_get(hexidcrackme):
    """Display the solution upload form."""
    crackme = _get_crackme_or_abort(hexidcrackme)
    return render_template('solution/create.html',
                           hexidcrackme=hexidcrackme,
                           username=crackme.get('author', ''),
                           crackmename=crackme.get('name', ''))


@solution_bp.route('/upload/solution/<hexidcrackme>', methods=['POST'])
@login_required
@limit("20 per day", key_func=lambda: session.get('name'))
def upload_solution_post(hexidcrackme):
    """Handle solution file upload."""
    crackme = _get_crackme_or_abort(hexidcrackme)
    username = session.get('name')
    redirect_url = f'/upload/solution/{hexidcrackme}'

    # Check if user already submitted a solution
    if solution_exists(username, crackme['_id']):
        flash("You've already submitted a solution to this crackme", FLASH_ERROR)
        return redirect(redirect_url)

    if not verify_recaptcha(request):
        flash('reCAPTCHA invalid!', FLASH_ERROR)
        return redirect(redirect_url)

    # Validate file presence
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('Field missing: file', FLASH_ERROR)
        return redirect(redirect_url)

    file = request.files['file']

    # Check file size (header and actual)
    if file.content_length and file.content_length > MAX_FILE_SIZE:
        flash('This file is too large!', FLASH_ERROR)
        return redirect(redirect_url)

    try:
        data = file.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        abort(500)

    if len(data) > MAX_FILE_SIZE:
        flash('This file is too large!', FLASH_ERROR)
        return redirect(redirect_url)

    # Check for unsupported archive formats (RAR, tar, etc.)
    if is_unsupported_archive(data):
        flash('RAR and tar archives are not supported. Please upload a ZIP file for multiple files, or upload single files directly.', FLASH_ERROR)
        return redirect(redirect_url)

    # Check for password-protected archives
    if is_archive_password_protected(data):
        flash('Password-protected archives are not allowed. Do NOT add a password yourself - the server handles this automatically.', FLASH_ERROR)
        return redirect(redirect_url)

    # Check for single-file archives
    if is_single_file_archive(data):
        flash('Archives containing only one file are not allowed. Please upload the file directly without wrapping it in an archive.', FLASH_ERROR)
        return redirect(redirect_url)

    # Check for PE files (patched binaries are not allowed)
    if is_pe_file(file.filename, data):
        flash('Executable files (PE binaries) are not allowed as solutions. Please submit a writeup that analyzes the algorithm instead of a patched binary.', FLASH_ERROR)
        return redirect(redirect_url)

    info = bleach.clean(request.form.get('info', ''))
    if len(info) > MAX_INFO_LENGTH:
        flash(f'Info field exceeds maximum length of {MAX_INFO_LENGTH} characters.', FLASH_ERROR)
        return redirect(redirect_url)

    original_filename = secure_filename(file.filename) or "unnamed"

    try:
        solution, crackme = solution_create(info, username, hexidcrackme, original_filename)
    except Exception as e:
        print(f"Error creating solution: {e}")
        abort(500)

    # Save uploaded file
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    try:
        with open(os.path.join(UPLOAD_FOLDER, solution['hexid']), 'wb') as f:
            f.write(data)
    except Exception as e:
        print(f"File write error: {e}")
        flash('An error occurred on the server. Please try again later.', FLASH_ERROR)
        return redirect(redirect_url)

    return _send_notifications_and_render_success(username, crackme)


@solution_bp.route('/solution/<hexid>', methods=['GET'])
@login_required
def view_solution(hexid):
    """Display a solution's writeup page."""
    solution = _get_solution_or_abort(hexid)
    salt = get_obfuscation_salt(current_app.config)

    return render_template('solution/read.html',
                           solution=solution,
                           obfuscation_key=get_obfuscation_key_base64(hexid, salt))


@solution_bp.route('/upload/solution/<hexidcrackme>/editor', methods=['GET'])
@login_required
def editor_solution_get(hexidcrackme):
    """Display the web-based markdown editor for writing solutions."""
    crackme = _get_crackme_or_abort(hexidcrackme)
    return render_template('solution/editor.html',
                           hexidcrackme=hexidcrackme,
                           username=crackme.get('author', ''),
                           crackmename=crackme.get('name', ''),
                           min_content_length=MIN_CONTENT_LENGTH,
                           max_content_length=MAX_CONTENT_LENGTH)


@solution_bp.route('/upload/solution/<hexidcrackme>/editor', methods=['POST'])
@login_required
@limit("20 per day", key_func=lambda: session.get('name'))
def editor_solution_post(hexidcrackme):
    """Handle solution submission from the web editor."""
    crackme = _get_crackme_or_abort(hexidcrackme)
    username = session.get('name')
    redirect_url = f'/upload/solution/{hexidcrackme}/editor'

    # Check if user already submitted a solution
    if solution_exists(username, crackme['_id']):
        flash("You've already submitted a solution to this crackme", FLASH_ERROR)
        return redirect(redirect_url)

    if not verify_recaptcha(request):
        flash('reCAPTCHA invalid!', FLASH_ERROR)
        return redirect(redirect_url)

    content = request.form.get('content', '').strip()

    # Validate content length
    if len(content) < MIN_CONTENT_LENGTH:
        flash(f'Your writeup is too short. Please write at least {MIN_CONTENT_LENGTH} characters.', FLASH_ERROR)
        return redirect(redirect_url)

    if len(content) > MAX_CONTENT_LENGTH:
        flash(f'Your writeup exceeds the maximum length of {MAX_CONTENT_LENGTH:,} characters.', FLASH_ERROR)
        return redirect(redirect_url)

    info = bleach.clean(request.form.get('info', ''))
    if len(info) > MAX_INFO_LENGTH:
        flash(f'Info field exceeds maximum length of {MAX_INFO_LENGTH} characters.', FLASH_ERROR)
        return redirect(redirect_url)

    try:
        solution, crackme = solution_create(info, username, hexidcrackme, original_filename='writeup.md', has_markdown=True)
    except Exception as e:
        print(f"Error creating solution: {e}")
        abort(500)

    # Save markdown content
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    try:
        with open(os.path.join(UPLOAD_FOLDER, solution['hexid']), 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"File write error: {e}")
        flash('An error occurred on the server. Please try again later.', FLASH_ERROR)
        return redirect(redirect_url)

    return _send_notifications_and_render_success(username, crackme)
