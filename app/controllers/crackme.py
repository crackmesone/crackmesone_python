"""
Crackme controller - Crackme viewing and uploading.
"""

import os
from html import escape as html_escape
from flask import Blueprint, render_template, request, redirect, flash, session, abort
from werkzeug.utils import secure_filename
import bleach
from app.models.crackme import (
    crackme_by_hexid, last_crackmes, crackme_create_prepare,
    crackme_insert, crackme_delete_by_hexid, crackme_by_user_and_name,
    crackme_update_difficulty, crackme_update_quality, crackme_increment_downloads,
    crackme_update
)
from app.models.solution import solutions_by_crackme
from app.models.comment import comments_by_crackme
from app.models.rating import rating_difficulty_create, rating_quality_create, rating_difficulty_delete_by_crackme
from app.models.notification import notification_add
from app.models.tag_request import (
    tag_request_create, pending_tag_requests_by_user_and_crackme
)
from app.models.errors import ErrNoResult
from app.services.recaptcha import verify as verify_recaptcha
from app.services.limiter import limit
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, validate_required
from app.services.tags import OBFUSCATION_TAGS, DATASET_URL, normalize_tags
from app.services.archive import is_archive_password_protected, is_single_file_archive, is_unsupported_archive
from app.services.discord import notify_new_crackme
from app.controllers.decorators import login_required

crackme_bp = Blueprint('crackme', __name__)

# Upload folder for crackmes
UPLOAD_FOLDER = 'tmp/crackme'
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@crackme_bp.route('/crackme/<hexid>')
def crackme_view(hexid):
    """Display a crackme's details."""
    try:
        crackme = crackme_by_hexid(hexid)
    except ErrNoResult:
        abort(404)
    except Exception as e:
        print(f"Error getting crackme: {e}")
        abort(500)

    try:
        solutions = solutions_by_crackme(crackme['_id'])
        comments = comments_by_crackme(hexid)
    except Exception as e:
        print(f"Error getting crackme data: {e}")
        abort(500)

    # Get current user for edit permission check
    usersess = session.get('name')

    # Build mention targets for @mention autocomplete (author + commenters + solution authors)
    mention_targets = {crackme.get('author', '')}
    for comment in comments:
        mention_targets.add(comment.get('author', ''))
    for solution in solutions:
        mention_targets.add(solution.get('author', ''))
    mention_targets.discard('')  # Remove empty strings
    mention_targets = sorted(mention_targets)  # Sort alphabetically

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
                           mention_targets=mention_targets,
                           nbsolutions=crackme.get('nbsolutions', 0),
                           nbcomments=crackme.get('nbcomments', 0),
                           nbdownloads=crackme.get('nbdownloads', 0),
                           difficulty=f"{crackme.get('difficulty', 0):.1f}",
                           quality=f"{crackme.get('quality', 0):.1f}",
                           size=crackme.get('size', 0),
                           tags=crackme.get('tags', []),
                           all_tags=OBFUSCATION_TAGS,
                           tags_dataset_url=DATASET_URL,
                           usersess=usersess)


@crackme_bp.route('/lasts')
def last_crackmes_redirect():
    """Redirect /lasts to /lasts/1."""
    return redirect('/lasts/1')


@crackme_bp.route('/lasts/<int:page>')
def last_crackmes_page(page):
    """Display latest crackmes with pagination."""
    if page < 1:
        page = 1

    try:
        crackmes, has_more = last_crackmes(page)
    except Exception as e:
        print(f"Error getting crackmes: {e}")
        abort(500)

    return render_template('crackme/lasts.html',
                           crackmes=crackmes,
                           page=page,
                           has_more=has_more)


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
    return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)


@crackme_bp.route('/upload/crackme', methods=['POST'])
@login_required
@limit("10 per day", key_func=lambda: session.get('name'))
def upload_crackme_post():
    """Handle crackme upload."""
    username = session.get('name')

    # Validate required fields
    required = ['name', 'info', 'lang', 'difficulty', 'platform', 'arch']
    is_valid, missing = validate_required(request.form, required)
    if not is_valid:
        flash(f'Field missing: {missing}', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)

    name = bleach.clean(request.form.get('name', ''))
    info = bleach.clean(request.form.get('info', ''))
    lang = bleach.clean(request.form.get('lang', ''))
    arch = bleach.clean(request.form.get('arch', ''))
    platform = request.form.get('platform', '')
    difficulty = request.form.get('difficulty', '')
    # Tags are optional; keep only values from the controlled vocabulary.
    tags = normalize_tags(request.form.getlist('tags'))

    # Validate difficulty
    try:
        diff_int = int(difficulty)
        if diff_int < 1 or diff_int > 6:
            raise ValueError()
    except (ValueError, TypeError):
        flash('Wrong difficulty', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)

    # Validate reCAPTCHA
    if not verify_recaptcha(request):
        flash('reCAPTCHA invalid!', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)

    # Check for file
    if 'file' not in request.files:
        flash('Field missing: file', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)

    file = request.files['file']
    if file.filename == '':
        flash('Field missing: file', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)

    # Read file data
    file_data = file.read()

    # Check file size
    if len(file_data) > MAX_FILE_SIZE:
        flash('This file is too large!', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)

    # Check for unsupported archive formats (RAR, tar, etc.)
    if is_unsupported_archive(file_data):
        flash('RAR and tar archives are not supported. Please upload a ZIP file for multiple files, or upload single files directly.', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)

    # Check for password protection
    if is_archive_password_protected(file_data):
        flash('Password-protected archives are not allowed. Do NOT add a password yourself - the server handles this automatically.', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)

    # Check for single-file archives
    if is_single_file_archive(file_data):
        flash('Archives containing only one file are not allowed. Please upload the file directly without wrapping it in an archive.', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)

    # Store the uploaded file size
    size = len(file_data)

    # Check for duplicate pending submission
    try:
        crackme_by_user_and_name(username, name, visible=False)
        flash('You already have a pending crackme with this name. Please wait for review or choose a different name.', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)
    except ErrNoResult:
        pass  # No duplicate, continue

    # Secure filename (fallback to "unnamed" if filename has only unsafe characters)
    original_filename = secure_filename(file.filename) or "unnamed"

    # Prepare crackme
    try:
        crackme = crackme_create_prepare(name, info, username, lang, arch, platform, size, original_filename, tags=tags)
    except Exception as e:
        print(f"Error preparing crackme: {e}")
        abort(500)

    # Create path using hexid only
    safe_path = os.path.join(UPLOAD_FOLDER, crackme['hexid'])

    # Ensure upload directory exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Save file first
    try:
        with open(safe_path, 'wb') as f:
            f.write(file_data)
    except Exception as e:
        print(f"File write error: {e}")
        flash('Failed to save file. Please try again.', FLASH_ERROR)
        return render_template('crackme/create.html', all_tags=OBFUSCATION_TAGS)

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
        notification_add(username, f"Crackme '{html_escape(crackme['name'])}' added, waiting for approval!")
    except Exception as e:
        print(f"Notification error: {e}")

    # Send Discord notification
    try:
        notify_new_crackme(username, crackme['name'])
    except Exception as e:
        print(f"Discord notification error: {e}")

    return render_template('submission/success.html',
                           submission_type='Crackme',
                           name=crackme['name'],
                           username=username)


@crackme_bp.route('/crackme/<hexid>/edit', methods=['GET'])
@login_required
def edit_crackme_get(hexid):
    """Display the crackme edit form."""
    username = session.get('name')

    try:
        crackme = crackme_by_hexid(hexid)
    except ErrNoResult:
        abort(404)
    except Exception as e:
        print(f"Error getting crackme: {e}")
        abort(500)

    # Only author can edit their own crackme
    if crackme.get('author') != username:
        flash('You can only edit your own crackmes.', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    return render_template('crackme/edit.html', crackme=crackme)


@crackme_bp.route('/crackme/<hexid>/edit', methods=['POST'])
@login_required
def edit_crackme_post(hexid):
    """Handle crackme edit submission."""
    username = session.get('name')

    try:
        crackme = crackme_by_hexid(hexid)
    except ErrNoResult:
        abort(404)
    except Exception as e:
        print(f"Error getting crackme: {e}")
        abort(500)

    # Only author can edit their own crackme
    if crackme.get('author') != username:
        flash('You can only edit your own crackmes.', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    # Get form data (name is not editable)
    info = bleach.clean(request.form.get('info', ''))
    lang = bleach.clean(request.form.get('lang', ''))
    arch = bleach.clean(request.form.get('arch', ''))
    platform = request.form.get('platform', '')

    # Update the crackme
    updates = {
        'info': info,
        'lang': lang,
        'arch': arch,
        'platform': platform
    }

    try:
        changes = crackme_update(hexid, updates)
    except Exception as e:
        print(f"Error updating crackme: {e}")
        abort(500)

    if changes is None:
        abort(404)

    if changes:
        # Send notification to the author about the edit
        try:
            notification_add(username, f"Your crackme '<a href=\"/crackme/{hexid}\">{html_escape(crackme.get('name'))}</a>' has been updated.")
        except Exception as e:
            print(f"Notification error: {e}")

        flash('Crackme updated successfully!', FLASH_SUCCESS)
    else:
        flash('No changes were made.', FLASH_SUCCESS)

    return redirect(f'/crackme/{hexid}')


@crackme_bp.route('/crackme/<hexid>/tags/request', methods=['POST'])
@login_required
@limit("20 per day", key_func=lambda: session.get('name'))
def request_tag_change(hexid):
    """Submit a request to add and/or remove tags on a crackme.

    Requests are queued for reviewers; nothing changes on the crackme until a
    reviewer approves.
    """
    username = session.get('name')

    try:
        crackme = crackme_by_hexid(hexid)
    except ErrNoResult:
        abort(404)
    except Exception as e:
        print(f"Error getting crackme: {e}")
        abort(500)

    current = crackme.get('tags', [])
    # Only propose adds for tags not already present, and removes for tags that are.
    add = [t for t in normalize_tags(request.form.getlist('add')) if t not in current]
    remove = [t for t in normalize_tags(request.form.getlist('remove')) if t in current]
    note = bleach.clean(request.form.get('note', ''))[:500]

    if not add and not remove:
        flash('Select at least one tag to add or remove.', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    # Prevent a user from piling up duplicate pending requests on one crackme.
    try:
        if pending_tag_requests_by_user_and_crackme(username, hexid) > 0:
            flash('You already have a pending tag change request for this crackme.', FLASH_ERROR)
            return redirect(f'/crackme/{hexid}')
    except Exception as e:
        print(f"Error checking pending tag requests: {e}")

    try:
        tag_request_create(hexid, crackme.get('name', ''), username,
                           add=add, remove=remove, note=note)
    except Exception as e:
        print(f"Error creating tag request: {e}")
        abort(500)

    flash('Tag change request submitted for review. Thank you!', FLASH_SUCCESS)
    return redirect(f'/crackme/{hexid}')
