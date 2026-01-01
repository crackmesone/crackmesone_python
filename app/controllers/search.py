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
    return render_template('search/search.html', crackmes=[])


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
        difficulty_min = int(request.form.get('difficulty-min', 0))
    except (ValueError, TypeError):
        difficulty_min = 0

    try:
        difficulty_max = int(request.form.get('difficulty-max', 6))
    except (ValueError, TypeError):
        difficulty_max = 6

    # Get quality range
    try:
        quality_min = int(request.form.get('quality-min', 0))
    except (ValueError, TypeError):
        quality_min = 0

    try:
        quality_max = int(request.form.get('quality-max', 6))
    except (ValueError, TypeError):
        quality_max = 6

    try:
        crackmes = search_crackme(
            name=name,
            author=author,
            lang=lang,
            arch=arch,
            platform=platform,
            difficulty_min=difficulty_min,
            difficulty_max=difficulty_max,
            quality_min=quality_min,
            quality_max=quality_max
        )
    except Exception as e:
        print(f"Search error: {e}")
        crackmes = []

    return render_template('search/search.html', crackmes=crackmes)


@search_bp.route('/random', methods=['GET'])
def random_get():
    """Redirect to a random crackme."""
    try:
        crackme = random_crackme()
        return redirect(f"/crackme/{crackme['hexid']}")
    except ErrNoResult:
        return redirect(url_for('search.search_get'))
