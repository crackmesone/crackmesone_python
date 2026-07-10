"""
Solution controller - Solution uploading and viewing.

A solution carries a short summary (info) plus a writeup body that may be inline
markdown content, an attached file, or both. Markdown content is stored as
cleartext in the database and obfuscated at the serving boundary (see the
/solution/<hexid>/content route) so raw code snippets never appear in page source.
"""

import os
from html import escape as html_escape
from flask import Blueprint, render_template, request, redirect, flash, session, abort, current_app, Response
from werkzeug.utils import secure_filename
import bleach
from app.models.crackme import crackme_by_hexid
from app.models.solution import solution_create, solution_exists, solution_by_hexid
from app.models.notification import notification_add
from app.models.errors import ErrNoResult
from app.services.database import get_collection
from app.services.recaptcha import verify as verify_recaptcha
from app.services.limiter import limit
from app.services.view import FLASH_ERROR, is_valid_hexid
from app.services.archive import is_archive_password_protected, is_pe_file, is_single_file_archive, is_unsupported_archive
from app.services.discord import notify_new_solution
from app.services.crypto import obfuscate_writeup, get_obfuscation_key_base64, get_obfuscation_salt
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
    """Fetch a visible solution by hexid, abort with 404/500 on error."""
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


def _validate_attachment(file):
    """Validate an uploaded attachment. Returns (data, error_message).

    error_message is None when the file is acceptable.
    """
    if file.content_length and file.content_length > MAX_FILE_SIZE:
        return None, 'This file is too large!'

    try:
        data = file.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        abort(500)

    if len(data) > MAX_FILE_SIZE:
        return None, 'This file is too large!'
    if is_unsupported_archive(data):
        return None, ('RAR and tar archives are not supported. Please upload a ZIP file for '
                      'multiple files, or upload single files directly.')
    if is_archive_password_protected(data):
        return None, ('Password-protected archives are not allowed. Do NOT add a password '
                      'yourself - the server handles this automatically.')
    if is_single_file_archive(data):
        return None, ('Archives containing only one file are not allowed. Please upload the '
                      'file directly without wrapping it in an archive.')
    if is_pe_file(file.filename, data):
        return None, ('Executable files (PE binaries) are not allowed as solutions. Please '
                      'submit a writeup that analyzes the algorithm instead of a patched binary.')
    return data, None


@solution_bp.route('/upload/solution/<hexidcrackme>', methods=['GET'])
@login_required
def upload_solution_get(hexidcrackme):
    """Display the solution submission form (markdown editor + optional attachment)."""
    crackme = _get_crackme_or_abort(hexidcrackme)
    return render_template('solution/editor.html',
                           hexidcrackme=hexidcrackme,
                           username=crackme.get('author', ''),
                           crackmename=crackme.get('name', ''),
                           min_content_length=MIN_CONTENT_LENGTH,
                           max_content_length=MAX_CONTENT_LENGTH)


@solution_bp.route('/upload/solution/<hexidcrackme>/editor', methods=['GET'])
@login_required
def editor_solution_get(hexidcrackme):
    """Backwards-compatible alias: the editor is now the primary submission form."""
    return redirect(f'/upload/solution/{hexidcrackme}')


@solution_bp.route('/upload/solution/<hexidcrackme>', methods=['POST'])
@solution_bp.route('/upload/solution/<hexidcrackme>/editor', methods=['POST'])
@login_required
@limit("20 per day", key_func=lambda: session.get('name'))
def upload_solution_post(hexidcrackme):
    """Handle a solution submission: inline markdown content, an attached file, or both."""
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

    # Summary
    info = bleach.clean(request.form.get('info', ''))
    if len(info) > MAX_INFO_LENGTH:
        flash(f'Info field exceeds maximum length of {MAX_INFO_LENGTH} characters.', FLASH_ERROR)
        return redirect(redirect_url)

    # Inline markdown content (optional)
    content = request.form.get('content', '').strip()
    if content:
        if len(content) < MIN_CONTENT_LENGTH:
            flash(f'Your writeup is too short. Please write at least {MIN_CONTENT_LENGTH} characters.', FLASH_ERROR)
            return redirect(redirect_url)
        if len(content) > MAX_CONTENT_LENGTH:
            flash(f'Your writeup exceeds the maximum length of {MAX_CONTENT_LENGTH:,} characters.', FLASH_ERROR)
            return redirect(redirect_url)
    else:
        content = None

    # Attachment (optional)
    file = request.files.get('file')
    has_file = file is not None and file.filename != ''
    data = None
    original_filename = None
    if has_file:
        data, error = _validate_attachment(file)
        if error:
            flash(error, FLASH_ERROR)
            return redirect(redirect_url)
        original_filename = secure_filename(file.filename) or "unnamed"

    # A solution must have a writeup body: markdown content, an attachment, or both.
    if content is None and not has_file:
        flash('Please write a markdown writeup or attach a file (or both).', FLASH_ERROR)
        return redirect(redirect_url)

    try:
        solution = solution_create(info, username, crackme, content=content, original_filename=original_filename)
    except Exception as e:
        print(f"Error creating solution: {e}")
        abort(500)

    # Save the attachment alongside the DB record (markdown lives in the DB only)
    if has_file:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        try:
            with open(os.path.join(UPLOAD_FOLDER, solution['hexid']), 'wb') as f:
                f.write(data)
        except Exception as e:
            print(f"File write error: {e}")
            # Roll back the just-created record so it doesn't linger in the review queue
            try:
                get_collection('solution').delete_one({'hexid': solution['hexid']})
            except Exception as cleanup_error:
                print(f"Failed to roll back solution record: {cleanup_error}")
            flash('An error occurred on the server. Please try again later.', FLASH_ERROR)
            return redirect(redirect_url)

    return _send_notifications_and_render_success(username, crackme)


@solution_bp.route('/solution/<hexid>', methods=['GET'])
def view_solution(hexid):
    """Display a solution's writeup page (public)."""
    solution = _get_solution_or_abort(hexid)
    salt = get_obfuscation_salt(current_app.config)
    has_content = bool(solution.get('content'))
    has_attachment = bool(solution.get('has_attachment'))

    return render_template('solution/read.html',
                           solution=solution,
                           has_content=has_content,
                           has_attachment=has_attachment,
                           obfuscation_key=get_obfuscation_key_base64(hexid, salt))


@solution_bp.route('/solution/<hexid>/content', methods=['GET'])
def solution_content(hexid):
    """Serve a solution's markdown body as obfuscated bytes (public).

    The content is stored cleartext in the database but XOR-obfuscated here so the
    served payload (and anything that scans it) never sees raw code snippets; the
    browser deobfuscates and renders it client-side.
    """
    solution = _get_solution_or_abort(hexid)
    content = solution.get('content')
    if not content:
        abort(404)

    salt = get_obfuscation_salt(current_app.config)
    obfuscated = obfuscate_writeup(content, hexid, salt)
    return Response(obfuscated, mimetype='application/octet-stream')
