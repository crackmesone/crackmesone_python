"""
Crackme controller - Crackme viewing and uploading.
"""

import os
from html import escape as html_escape
from flask import Blueprint, render_template, request, redirect, flash, jsonify, session, abort
from werkzeug.utils import secure_filename
import bleach
from app.models.crackme import (
    crackme_by_hexid, last_crackmes, crackme_create_prepare,
    crackme_insert, crackme_delete_by_hexid, crackme_by_user_and_name,
    crackme_update_difficulty, crackme_update_quality, crackme_increment_downloads,
    crackme_update, crackme_is_auto_validated
)
from app.models.solution import solutions_by_crackme
from app.models.comment import comments_by_crackme
from app.models.rating import rating_difficulty_create, rating_quality_create, rating_difficulty_delete_by_crackme
from app.models.notification import notification_add
from app.models.label_request import (
    label_request_create, pending_label_requests_by_user_and_crackme
)
from app.models.solve import (
    solve_by_user_and_crackme, solve_create, count_solves_by_crackme
)
from app.models.user import user_by_name
from app.models.errors import ErrNoResult
from app.services.recaptcha import verify as verify_recaptcha
from app.services.limiter import limit
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, FLASH_NOTICE, validate_required
from app.services.labels import get_label_groups, get_dataset_url, normalize_labels
from app.services.archive import is_archive_password_protected, is_single_file_archive, is_unsupported_archive
from app.services.discord import notify_new_crackme
from app.services.flag import (
    FLAG_FORMAT_HINT, flags_match, is_valid_flag_format, normalize_flag
)
from app.services.points import points_for_solve, solve_difficulty
from app.controllers.decorators import login_required

crackme_bp = Blueprint('crackme', __name__)

# Upload folder for crackmes
UPLOAD_FOLDER = 'tmp/crackme'
# Source archives for auto-validated crackmes. Never served: this directory sits
# outside static/ so the only way to read one is the reviewer download route.
SOURCE_UPLOAD_FOLDER = 'private/crackme_source'
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

    # Flag submission panel. Only auto-validated crackmes pay for these extra
    # queries; everything else renders exactly as before.
    auto_validation = crackme_is_auto_validated(crackme)
    nbsolves = 0
    user_solve = None
    if auto_validation:
        try:
            nbsolves = count_solves_by_crackme(hexid)
            viewer_hexid = _user_hexid(usersess) if usersess else None
            if viewer_hexid:
                user_solve = solve_by_user_and_crackme(viewer_hexid, hexid)
        except Exception as e:
            print(f"Error getting solve data: {e}")

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
                           labels=crackme.get('labels', []),
                           label_groups=get_label_groups(),
                           labels_dataset_url=get_dataset_url(),
                           auto_validation=auto_validation,
                           nbsolves=nbsolves,
                           user_solve=user_solve,
                           solve_points=points_for_solve(crackme) if auto_validation else 0,
                           flag_format_hint=FLAG_FORMAT_HINT,
                           usersess=usersess)


def _user_hexid(username):
    """Resolve a username to the immutable id solves are keyed by.

    Returns None when the user can't be resolved, which callers treat as "no
    solve" rather than an error.
    """
    try:
        user = user_by_name(username)
    except Exception:
        return None
    return user.get('hexid') or str(user['_id'])


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
    return render_template('crackme/create.html', label_groups=get_label_groups())


def _upload_rejected(message):
    """Reject an upload without throwing away what the user typed.

    An AJAX submission gets the message as JSON and the browser keeps the page
    (and the files the user picked) untouched; a plain form post falls back to
    re-rendering the form with the submitted values filled back in. Either way a
    single missing field no longer costs someone the whole form.
    """
    if _wants_json():
        return jsonify({'ok': False, 'error': message}), 400

    flash(message, FLASH_ERROR)
    return render_template('crackme/create.html',
                           label_groups=get_label_groups(),
                           form=_submitted_form_values())


def _wants_json():
    """True when the upload form posted in the background rather than navigating."""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _submitted_form_values():
    """The submitted values, shaped for re-rendering the upload form.

    File inputs are deliberately absent: browsers won't let a server refill them,
    which is exactly why the form posts over fetch when it can.
    """
    return {
        'name': request.form.get('name', ''),
        'info': request.form.get('info', ''),
        'lang': request.form.get('lang', ''),
        'arch': request.form.get('arch', ''),
        'platform': request.form.get('platform', ''),
        'difficulty': request.form.get('difficulty', ''),
        'labels': normalize_labels(request.form.getlist('labels')),
        'auto_validation': bool(request.form.get('auto_validation')),
        'flag': request.form.get('flag', ''),
    }


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
        return _upload_rejected(f'Field missing: {missing}')

    name = bleach.clean(request.form.get('name', ''))
    info = bleach.clean(request.form.get('info', ''))
    lang = bleach.clean(request.form.get('lang', ''))
    arch = bleach.clean(request.form.get('arch', ''))
    platform = request.form.get('platform', '')
    difficulty = request.form.get('difficulty', '')
    # Keep only values from the controlled vocabulary. Labels are not mandatory
    # (a crackme with no matching technique may legitimately have none).
    labels = normalize_labels(request.form.getlist('labels'))

    # Validate difficulty
    try:
        diff_int = int(difficulty)
        if diff_int < 1 or diff_int > 6:
            raise ValueError()
    except (ValueError, TypeError):
        return _upload_rejected('Wrong difficulty')

    # Validate reCAPTCHA
    if not verify_recaptcha(request):
        return _upload_rejected('reCAPTCHA invalid!')

    # Check for file
    if 'file' not in request.files:
        return _upload_rejected('Field missing: file')

    file = request.files['file']
    if file.filename == '':
        return _upload_rejected('Field missing: file')

    # Read file data
    file_data = file.read()

    # Check file size
    if len(file_data) > MAX_FILE_SIZE:
        return _upload_rejected('This file is too large!')

    # Check for unsupported archive formats (RAR, tar, etc.)
    if is_unsupported_archive(file_data):
        return _upload_rejected('RAR and tar archives are not supported. Please upload a ZIP file for multiple files, or upload single files directly.')

    # Check for password protection
    if is_archive_password_protected(file_data):
        return _upload_rejected('Password-protected archives are not allowed. Do NOT add a password yourself - the server handles this automatically.')

    # Check for single-file archives
    if is_single_file_archive(file_data):
        return _upload_rejected('Archives containing only one file are not allowed. Please upload the file directly without wrapping it in an archive.')

    # Auto-validation opt-in: the flag users will submit, plus the private source
    # archive a reviewer needs to confirm that flag is actually the right one.
    flag = None
    source_data = None
    source_filename = None
    if request.form.get('auto_validation'):
        flag = normalize_flag(request.form.get('flag', ''))
        if not is_valid_flag_format(flag):
            return _upload_rejected(f'Invalid flag format. {FLAG_FORMAT_HINT}')

        source = request.files.get('source')
        if source is None or source.filename == '':
            return _upload_rejected('Auto-validation needs a source archive so reviewers can verify the flag.')

        source_data = source.read()
        if len(source_data) > MAX_FILE_SIZE:
            return _upload_rejected('The source archive is too large!')
        if is_unsupported_archive(source_data):
            return _upload_rejected('RAR and tar source archives are not supported. Please upload a ZIP file.')
        if is_archive_password_protected(source_data):
            return _upload_rejected('Password-protected source archives are not allowed - reviewers need to be able to open it.')

        source_filename = secure_filename(source.filename) or "source"

    # Store the uploaded file size
    size = len(file_data)

    # Check for duplicate pending submission
    try:
        crackme_by_user_and_name(username, name, visible=False)
        return _upload_rejected('You already have a pending crackme with this name. Please wait for review or choose a different name.')
    except ErrNoResult:
        pass  # No duplicate, continue

    # Secure filename (fallback to "unnamed" if filename has only unsafe characters)
    original_filename = secure_filename(file.filename) or "unnamed"

    # Prepare crackme
    try:
        crackme = crackme_create_prepare(name, info, username, lang, arch, platform, size, original_filename,
                                         labels=labels, flag=flag,
                                         source_original_filename=source_filename)
    except Exception as e:
        print(f"Error preparing crackme: {e}")
        abort(500)

    # Create path using hexid only
    safe_path = os.path.join(UPLOAD_FOLDER, crackme['hexid'])
    source_path = os.path.join(SOURCE_UPLOAD_FOLDER, crackme['hexid'])

    # Ensure upload directory exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Save file first
    try:
        with open(safe_path, 'wb') as f:
            f.write(file_data)
    except Exception as e:
        print(f"File write error: {e}")
        return _upload_rejected('Failed to save file. Please try again.')

    if source_data is not None:
        try:
            os.makedirs(SOURCE_UPLOAD_FOLDER, exist_ok=True)
            with open(source_path, 'wb') as f:
                f.write(source_data)
        except Exception as e:
            print(f"Source file write error: {e}")
            os.remove(safe_path)
            return _upload_rejected('Failed to save the source archive. Please try again.')

    def _cleanup_files():
        for path in (safe_path, source_path if source_data is not None else None):
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass

    # Insert crackme into database
    try:
        crackme_insert(crackme)
    except Exception as e:
        print(f"Database insert error: {e}")
        _cleanup_files()  # Cleanup
        abort(500)

    # Create ratings
    try:
        rating_difficulty_create(username, crackme['hexid'], diff_int)
        rating_quality_create(username, crackme['hexid'], 4)
    except Exception as e:
        print(f"Rating creation error: {e}")
        _cleanup_files()
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

    # Post/redirect/get: the confirmation lives at its own URL, so the browser
    # (and the background submit above, which just follows the redirect) can't
    # re-post the upload by refreshing.
    session['submitted_crackme'] = crackme['name']
    if _wants_json():
        return jsonify({'ok': True, 'redirect': '/upload/crackme/submitted'})
    return redirect('/upload/crackme/submitted')


@crackme_bp.route('/upload/crackme/submitted', methods=['GET'])
@login_required
def upload_crackme_submitted():
    """Confirm a crackme upload that just went through."""
    name = session.pop('submitted_crackme', None)
    if not name:
        return redirect('/upload/crackme')

    return render_template('submission/success.html',
                           submission_type='Crackme',
                           name=name,
                           username=session.get('name'))


@crackme_bp.route('/crackme/<hexid>/solve', methods=['POST'])
@login_required
# Guessing a flag is meant to be impossible, but a slow attempt rate makes that
# true even for a badly chosen flag.
@limit("20 per hour", key_func=lambda: session.get('name'))
def submit_flag(hexid):
    """Validate a submitted flag and, if correct, record the solve."""
    username = session.get('name')

    try:
        crackme = crackme_by_hexid(hexid)
    except ErrNoResult:
        abort(404)
    except Exception as e:
        print(f"Error getting crackme: {e}")
        abort(500)

    if not crackme_is_auto_validated(crackme):
        flash('This crackme does not accept flag submissions.', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    # Authors already know their own flag; awarding them points for it would
    # make the scoreboard meaningless.
    if crackme.get('author') == username:
        flash("You can't submit a flag for your own crackme.", FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    user_hexid = _user_hexid(username)
    if not user_hexid:
        flash('Could not verify your account. Please log in again.', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    try:
        if solve_by_user_and_crackme(user_hexid, hexid):
            flash('You have already solved this crackme.', FLASH_NOTICE)
            return redirect(f'/crackme/{hexid}')
    except Exception as e:
        print(f"Error checking existing solve: {e}")
        abort(500)

    flag = normalize_flag(request.form.get('flag', ''))
    if not is_valid_flag_format(flag):
        flash(f'That is not a valid flag. {FLAG_FORMAT_HINT}', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    if not flags_match(crackme.get('flag'), flag):
        flash('Wrong flag. Keep trying!', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    points = points_for_solve(crackme)
    try:
        solve_create(user_hexid, hexid, points, solve_difficulty(crackme))
    except Exception as e:
        print(f"Error recording solve: {e}")
        abort(500)

    try:
        notification_add(
            username,
            f"Correct flag for '<a href=\"/crackme/{hexid}\">{html_escape(crackme.get('name', ''))}</a>' - {points} points earned!"
        )
    except Exception as e:
        print(f"Notification error: {e}")

    flash(f'Correct! You earned {points} points.', FLASH_SUCCESS)
    return redirect(f'/crackme/{hexid}')


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


@crackme_bp.route('/crackme/<hexid>/labels/request', methods=['POST'])
@login_required
@limit("20 per day", key_func=lambda: session.get('name'))
def request_label_change(hexid):
    """Submit a request to add and/or remove labels on a crackme.

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

    current = crackme.get('labels', [])
    # The form submits the full desired set of applied labels; derive the add/remove
    # sets by diffing against what the crackme currently carries.
    desired = normalize_labels(request.form.getlist('applied'))
    add = [t for t in desired if t not in current]
    remove = [t for t in current if t not in desired]
    note = bleach.clean(request.form.get('note', ''))[:500]

    if not add and not remove:
        flash('No label changes were selected.', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    # Prevent a user from piling up duplicate pending requests on one crackme.
    try:
        if pending_label_requests_by_user_and_crackme(username, hexid) > 0:
            flash('You already have a pending label change request for this crackme.', FLASH_ERROR)
            return redirect(f'/crackme/{hexid}')
    except Exception as e:
        print(f"Error checking pending label requests: {e}")

    try:
        label_request_create(hexid, crackme.get('name', ''), username,
                           add=add, remove=remove, note=note)
    except Exception as e:
        print(f"Error creating label request: {e}")
        abort(500)

    flash('Label change request submitted for review. Thank you!', FLASH_SUCCESS)
    return redirect(f'/crackme/{hexid}')
