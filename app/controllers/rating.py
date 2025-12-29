"""
Rating controller - Rate crackme difficulty and quality.
"""

from flask import Blueprint, request, redirect, flash, session
from app.models.crackme import crackme_update_difficulty, crackme_update_quality
from app.models.rating import (
    is_already_rated_difficulty, is_already_rated_quality,
    rating_difficulty_create, rating_difficulty_set_rating,
    rating_quality_create, rating_quality_set_rating
)
from app.services.view import FLASH_ERROR, FLASH_SUCCESS, validate_required
from app.controllers.decorators import login_required

rating_bp = Blueprint('rating', __name__)


@rating_bp.route('/crackme/rate-diff/<hexid>', methods=['POST'])
@login_required
def rate_difficulty(hexid):
    """Rate a crackme's difficulty."""
    username = session.get('name')

    # Validate required fields
    is_valid, missing = validate_required(request.form, ['difficulty'])
    if not is_valid:
        flash(f'Field missing: {missing}', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    # Parse and validate rating
    try:
        rating = int(request.form.get('difficulty', 0))
        if rating < 1 or rating > 6:
            raise ValueError()
    except (ValueError, TypeError):
        print("Wrong rating number")
        return redirect(f'/crackme/{hexid}'), 500

    try:
        already_rated = is_already_rated_difficulty(username, hexid)

        if already_rated:
            rating_difficulty_set_rating(username, hexid, rating)
        else:
            rating_difficulty_create(username, hexid, rating)

        # Recalculate difficulty rating
        crackme_update_difficulty(hexid)

    except Exception as e:
        print(f"Rating error: {e}")
        return redirect(f'/crackme/{hexid}'), 500

    flash('Rated!', FLASH_SUCCESS)
    return redirect(f'/crackme/{hexid}')


@rating_bp.route('/crackme/rate-qual/<hexid>', methods=['POST'])
@login_required
def rate_quality(hexid):
    """Rate a crackme's quality."""
    username = session.get('name')

    # Validate required fields
    is_valid, missing = validate_required(request.form, ['quality'])
    if not is_valid:
        flash(f'Field missing: {missing}', FLASH_ERROR)
        return redirect(f'/crackme/{hexid}')

    # Parse and validate rating
    try:
        rating = int(request.form.get('quality', 0))
        if rating < 1 or rating > 6:
            raise ValueError()
    except (ValueError, TypeError):
        print("Wrong rating number")
        return redirect(f'/crackme/{hexid}'), 500

    try:
        already_rated = is_already_rated_quality(username, hexid)

        if already_rated:
            rating_quality_set_rating(username, hexid, rating)
        else:
            rating_quality_create(username, hexid, rating)

        # Recalculate quality rating
        crackme_update_quality(hexid)

    except Exception as e:
        print(f"Rating error: {e}")
        return redirect(f'/crackme/{hexid}'), 500

    flash('Rated!', FLASH_SUCCESS)
    return redirect(f'/crackme/{hexid}')
