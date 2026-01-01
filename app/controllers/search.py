"""
Search controller - Searching crackmes.
"""

from flask import Blueprint, render_template, request, redirect, url_for
from app.models.crackme import search_crackme, random_crackme
from app.models.errors import ErrNoResult

search_bp = Blueprint('search', __name__)


@search_bp.route('/search', methods=['GET'])
def search_get():
    """Display the search page."""
    return render_template('search/search.html', crackmes=[], page=1, has_more=False, show_all=False, search_params={})


@search_bp.route('/search', methods=['POST'])
def search_post():
    """Handle search form submission."""
    name = request.form.get('name', '')
    author = request.form.get('author', '')
    lang = request.form.get('lang', '')
    arch = request.form.get('arch', '')
    platform = request.form.get('platform', '')

    # Get difficulty range
    try:
        difficulty_min = int(request.form.get('difficulty-min', 1))
    except (ValueError, TypeError):
        difficulty_min = 1

    try:
        difficulty_max = int(request.form.get('difficulty-max', 6))
    except (ValueError, TypeError):
        difficulty_max = 6

    # Get quality range
    try:
        quality_min = int(request.form.get('quality-min', 1))
    except (ValueError, TypeError):
        quality_min = 1

    try:
        quality_max = int(request.form.get('quality-max', 6))
    except (ValueError, TypeError):
        quality_max = 6

    # Get minimum downloads
    try:
        downloads_min = int(request.form.get('downloads-min', 0))
        if downloads_min < 0:
            downloads_min = 0
    except (ValueError, TypeError):
        downloads_min = 0

    # Get page number and show_all flag
    try:
        page = int(request.form.get('page', 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    show_all = request.form.get('show_all') == '1'

    # Store search params for pagination
    search_params = {
        'name': name,
        'author': author,
        'lang': lang,
        'arch': arch,
        'platform': platform,
        'difficulty-min': difficulty_min,
        'difficulty-max': difficulty_max,
        'quality-min': quality_min,
        'quality-max': quality_max,
        'downloads-min': downloads_min
    }

    try:
        if show_all:
            crackmes, _ = search_crackme(
                name=name,
                author=author,
                lang=lang,
                arch=arch,
                platform=platform,
                difficulty_min=difficulty_min,
                difficulty_max=difficulty_max,
                quality_min=quality_min,
                quality_max=quality_max,
                downloads_min=downloads_min,
                page=1,
                per_page=10000
            )
            has_more = False
        else:
            crackmes, has_more = search_crackme(
                name=name,
                author=author,
                lang=lang,
                arch=arch,
                platform=platform,
                difficulty_min=difficulty_min,
                difficulty_max=difficulty_max,
                quality_min=quality_min,
                quality_max=quality_max,
                downloads_min=downloads_min,
                page=page
            )
    except Exception as e:
        print(f"Search error: {e}")
        crackmes = []
        has_more = False

    return render_template('search/search.html',
                           crackmes=crackmes,
                           page=page,
                           has_more=has_more,
                           show_all=show_all,
                           search_params=search_params)


@search_bp.route('/random', methods=['GET'])
def random_get():
    """Redirect to a random crackme."""
    try:
        crackme = random_crackme()
        return redirect(f"/crackme/{crackme['hexid']}")
    except ErrNoResult:
        return redirect(url_for('search.search_get'))
