"""
Crackme controller - Crackme viewing and uploading.
"""

import os
from flask import Blueprint, render_template, request, redirect, flash, session, abort
from werkzeug.utils import secure_filename
import bleach
from app.models.crackme import (
    crackme_by_hexid, last_crackmes, crackme_create_prepare,
    crackme_insert, crackme_delete_by_hexid, crackme_by_user_and_name,
    crackme_update_difficulty, crackme_update_quality, crackme_increment_downloads
)
from app.models.solution import solutions_by_crackme
from app.models.comment import comments_by_crackme
from app.models.rating import rating_difficulty_create, rating_quality_create, rating_difficulty_delete_by_crackme
from app.models.notification import notification_add
from app.models.errors import ErrNoResult
from app.services.recaptcha import verify as verify_recaptcha
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, validate_required
from app.services.archive import is_archive_password_protected
from app.services.discord import notify_new_crackme
from app.controllers.decorators import login_required

crackme_bp = Blueprint('crackme', __name__)

# Upload folder for crackmes
UPLOAD_FOLDER = 'tmp/crackme'
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


@crackme_bp.route('/crackme/<hexid>')
def crackme_view(hexid):
    """Display a crackme's details."""
    try:
        crackme = crackme_by_hexid(hexid)
    except ErrNoResult:
        abort(500)
    except Exception as e:
        print(f"Error getting crackme: {e}")
        abort(500)

    try:
        solutions = solutions_by_crackme(crackme['_id'])
        comments = comments_by_crackme(hexid)
    except Exception as e:
        print(f"Error getting crackme data: {e}")
        abort(500)

    return render_template('crackme/read.html',
                           info=crackme.get('info', ''),
                           name=crackme.get('name', ''),
                           hexid=crackme.get('hexid', ''),
                           lang=crackme.get('lang', ''),
                           arch=crackme.get('arch', ''),
                           createdat=crackme.get('created_at'),
                           username=crackme.get('author', ''),
                           platform=crackme.get('platform', ''),
                           solutions=solutions,
                           comments=comments,
                           nbsolutions=crackme.get('nbsolutions', 0),
                           nbcomments=crackme.get('nbcomments', 0),
                           nbdownloads=crackme.get('nbdownloads', 0),
                           difficulty=f"{crackme.get('difficulty', 0):.1f}",
                           quality=f"{crackme.get('quality', 0):.1f}")


@crackme_bp.route('/lasts/<int:page>')
def last_crackmes_page(page):
    """Display latest crackmes with pagination."""
    if page < 1:
        page = 1

    try:
        crackmes = last_crackmes(page)
    except Exception as e:
        print(f"Error getting crackmes: {e}")
        abort(500)

    prec = 1 if page == 1 else page - 1
    next_page = page + 1

    return render_template('crackme/lasts.html',
                           crackmes=crackmes,
                           prec=prec,
                           next=next_page)


@crackme_bp.route('/download/crackme/<hexid>')
def download_crackme(hexid):
    """Handle crackme download and track download count."""
    # Verify crackme exists
    try:
        crackme_by_hexid(hexid)
    except ErrNoResult:
        abort(404)
    except Exception as e:
        print(f"Error getting crackme: {e}")
        abort(500)

    # Increment download count
    try:
        crackme_increment_downloads(hexid)
    except Exception as e:
        print(f"Error incrementing download count: {e}")
        # Continue with download even if count fails

    # Redirect to static file
    return redirect(f'/static/crackme/{hexid}.zip')


@crackme_bp.route('/upload/crackme', methods=['GET'])
@login_required
def upload_crackme_get():
    """Display the crackme upload form."""
    return render_template('crackme/create.html')


@crackme_bp.route('/upload/crackme', methods=['POST'])
@login_required
def upload_crackme_post():
    """Handle crackme upload."""
    username = session.get('name')

    # Validate required fields
    required = ['name', 'info', 'lang', 'difficulty', 'platform', 'arch']
    is_valid, missing = validate_required(request.form, required)
    if not is_valid:
        flash(f'Field missing: {missing}', FLASH_ERROR)
        return render_template('crackme/create.html')

    name = bleach.clean(request.form.get('name', ''))
    info = bleach.clean(request.form.get('info', ''))
    lang = bleach.clean(request.form.get('lang', ''))
    arch = bleach.clean(request.form.get('arch', ''))
    platform = request.form.get('platform', '')
    difficulty = request.form.get('difficulty', '')

    # Validate difficulty
    try:
        diff_int = int(difficulty)
        if diff_int < 1 or diff_int > 6:
            raise ValueError()
    except (ValueError, TypeError):
        flash('Wrong difficulty', FLASH_ERROR)
        return render_template('crackme/create.html')

    # Validate reCAPTCHA
    if not verify_recaptcha(request):
        flash('reCAPTCHA invalid!', FLASH_ERROR)
        return render_template('crackme/create.html')

    # Check for file
    if 'file' not in request.files:
        flash('Field missing: file', FLASH_ERROR)
        return render_template('crackme/create.html')

    file = request.files['file']
    if file.filename == '':
        flash('Field missing: file', FLASH_ERROR)
        return render_template('crackme/create.html')

    # Read file data
    file_data = file.read()

    # Check file size
    if len(file_data) > MAX_FILE_SIZE:
        flash('This file is too large!', FLASH_ERROR)
        return render_template('crackme/create.html')

    # Check for password protection
    if is_archive_password_protected(file_data):
        flash('Password-protected archives are not allowed. Do NOT add a password yourself - the server handles this automatically.', FLASH_ERROR)
        return render_template('crackme/create.html')

    # Check for duplicate pending submission
    try:
        crackme_by_user_and_name(username, name, visible=False)
        flash('You already have a pending crackme with this name. Please wait for review or choose a different name.', FLASH_ERROR)
        return render_template('crackme/create.html')
    except ErrNoResult:
        pass  # No duplicate, continue

    # Prepare crackme
    try:
        crackme = crackme_create_prepare(name, info, username, lang, arch, platform)
    except Exception as e:
        print(f"Error preparing crackme: {e}")
        abort(500)

    # Secure filename and create path
    filename = secure_filename(file.filename)
    safe_path = os.path.join(UPLOAD_FOLDER, f"{username}+++{crackme['hexid']}+++{filename}")

    # Ensure upload directory exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Save file first
    try:
        with open(safe_path, 'wb') as f:
            f.write(file_data)
    except Exception as e:
        print(f"File write error: {e}")
        flash('Failed to save file. Please try again.', FLASH_ERROR)
        return render_template('crackme/create.html')

    # Insert crackme into database
    try:
        crackme_insert(crackme)
    except Exception as e:
        print(f"Database insert error: {e}")
        os.remove(safe_path)  # Cleanup
        abort(500)

    # Create ratings
    try:
        rating_difficulty_create(username, crackme['hexid'], diff_int)
        rating_quality_create(username, crackme['hexid'], 4)
    except Exception as e:
        print(f"Rating creation error: {e}")
        os.remove(safe_path)
        crackme_delete_by_hexid(crackme['hexid'])
        rating_difficulty_delete_by_crackme(crackme['hexid'])
        abort(500)

    # Update calculated ratings
    try:
        crackme_update_difficulty(crackme['hexid'])
        crackme_update_quality(crackme['hexid'])
    except Exception as e:
        print(f"Rating update error: {e}")

    # Send notification
    try:
        notification_add(username, f"Crackme '{crackme['name']}' added, waiting for approval!")
    except Exception as e:
        print(f"Notification error: {e}")

    # Send Discord notification
    try:
        notify_new_crackme(username, crackme['name'])
    except Exception as e:
        print(f"Discord notification error: {e}")

    flash('Crackme uploaded! Should be available soon.', FLASH_SUCCESS)
    return redirect(f'/user/{username}')
