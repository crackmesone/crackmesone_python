"""
Solution controller - Solution uploading.
"""

import os
from html import escape as html_escape
from flask import Blueprint, render_template, request, redirect, flash, session, abort
from werkzeug.utils import secure_filename
import bleach
from app.models.crackme import crackme_by_hexid
from app.models.solution import solution_create, solutions_by_user_and_crackme, last_solutions
from app.models.notification import notification_add
from app.models.errors import ErrNoResult
from app.services.recaptcha import verify as verify_recaptcha
from app.services.limiter import limit
from app.services.view import FLASH_ERROR, FLASH_SUCCESS
from app.services.archive import is_archive_password_protected, is_pe_file
from app.services.discord import notify_new_solution
from app.controllers.decorators import login_required

solution_bp = Blueprint('solution', __name__)

# Upload folder for solutions
UPLOAD_FOLDER = 'tmp/solution'
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@solution_bp.route('/writeups')
def last_writeups_redirect():
    """Redirect /writeups to /writeups/1."""
    return redirect('/writeups/1')


@solution_bp.route('/writeups/<int:page>')
def last_writeups_page(page):
    """Display latest writeups with pagination."""
    if page < 1:
        page = 1

    try:
        solutions, has_more = last_solutions(page)
    except Exception as e:
        print(f"Error getting solutions: {e}")
        abort(500)

    return render_template('solution/lasts.html',
                           solutions=solutions,
                           page=page,
                           has_more=has_more)



@solution_bp.route('/upload/solution/<hexidcrackme>', methods=['GET'])
@login_required
def upload_solution_get(hexidcrackme):
    """Display the solution upload form."""
    try:
        crackme = crackme_by_hexid(hexidcrackme)
    except ErrNoResult:
        abort(404)
    except Exception as e:
        print(f"Error getting crackme: {e}")
        abort(500)

    return render_template('solution/create.html',
                           hexidcrackme=hexidcrackme,
                           username=crackme.get('author', ''),
                           crackmename=crackme.get('name', ''))


@solution_bp.route('/upload/solution/<hexidcrackme>', methods=['POST'])
@login_required
@limit("20 per day", key_func=lambda: session.get('name'))
def upload_solution_post(hexidcrackme):
    """Handle solution upload."""
    username = session.get('name')

    info = bleach.clean(request.form.get('info', ''))

    # Check if user already submitted a solution
    try:
        solutions_by_user_and_crackme(username, hexidcrackme)
        flash("You've already submitted a solution to this crackme", FLASH_ERROR)
        return redirect(f'/upload/solution/{hexidcrackme}')
    except ErrNoResult:
        pass  # No existing solution, continue

    # Validate reCAPTCHA
    if not verify_recaptcha(request):
        flash('reCAPTCHA invalid!', FLASH_ERROR)
        return redirect(f'/upload/solution/{hexidcrackme}')

    # Check for file
    if 'file' not in request.files:
        flash('Field missing: file', FLASH_ERROR)
        return redirect(f'/upload/solution/{hexidcrackme}')

    file = request.files['file']
    if file.filename == '':
        flash('Field missing: file', FLASH_ERROR)
        return redirect(f'/upload/solution/{hexidcrackme}')

    # Check file size from header
    if file.content_length and file.content_length > MAX_FILE_SIZE:
        flash('This file is too large!', FLASH_ERROR)
        return redirect(f'/upload/solution/{hexidcrackme}')

    # Read file data
    try:
        data = file.read()
        if len(data) > MAX_FILE_SIZE:
            flash('This file is too large!', FLASH_ERROR)
            return redirect(f'/upload/solution/{hexidcrackme}')
    except Exception as e:
        print(f"Error reading file: {e}")
        abort(500)

    # Check for password-protected archives
    if is_archive_password_protected(data):
        flash('Password-protected archives are not allowed. Do NOT add a password yourself - the server handles this automatically.', FLASH_ERROR)
        return redirect(f'/upload/solution/{hexidcrackme}')

    # Check for PE files (patched binaries are not allowed)
    if is_pe_file(file.filename, data):
        flash('Executable files (PE binaries) are not allowed as solutions. '
              'Please submit a writeup that analyzes the algorithm instead of a patched binary.', FLASH_ERROR)
        return redirect(f'/upload/solution/{hexidcrackme}')

    # Create solution
    try:
        solution = solution_create(info, username, hexidcrackme)
    except Exception as e:
        print(f"Error creating solution: {e}")
        abort(500)

    # Secure filename and create path
    filename = secure_filename(file.filename)
    safe_path = os.path.join(UPLOAD_FOLDER, f"{username}+++{solution['hexid']}+++{filename}")

    # Ensure upload directory exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Save file
    try:
        with open(safe_path, 'wb') as f:
            f.write(data)
    except Exception as e:
        print(f"File write error: {e}")
        flash('An error occurred on the server. Please try again later.', FLASH_ERROR)
        return redirect(f'/upload/solution/{hexidcrackme}')

    # Send notification
    try:
        crackme = crackme_by_hexid(hexidcrackme)
        notification_add(username, f"Your solution for '{html_escape(crackme['name'])}' is waiting approval!")
        # Send Discord notification
        notify_new_solution(username, crackme['name'])
    except Exception as e:
        print(f"Notification error: {e}")

    return render_template('submission/success.html',
                           submission_type='Writeup',
                           name=crackme['name'],
                           username=username)
