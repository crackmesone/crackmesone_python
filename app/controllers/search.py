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

    # Get downloads range
    try:
        downloads_min = int(request.form.get('downloads-min', 0))
        if downloads_min < 0:
            downloads_min = 0
    except (ValueError, TypeError):
        downloads_min = 0

    downloads_max_str = request.form.get('downloads-max', '')
    if downloads_max_str == '' or downloads_max_str.lower() == 'any':
        downloads_max = None
    else:
        try:
            downloads_max = int(downloads_max_str)
            if downloads_max < 0:
                downloads_max = None
        except (ValueError, TypeError):
            downloads_max = None

    # Get solutions range
    try:
        solutions_min = int(request.form.get('solutions-min', 0))
        if solutions_min < 0:
            solutions_min = 0
    except (ValueError, TypeError):
        solutions_min = 0

    solutions_max_str = request.form.get('solutions-max', '')
    if solutions_max_str == '' or solutions_max_str.lower() == 'any':
        solutions_max = None
    else:
        try:
            solutions_max = int(solutions_max_str)
            if solutions_max < 0:
                solutions_max = None
        except (ValueError, TypeError):
            solutions_max = None

    # Get comments range
    try:
        comments_min = int(request.form.get('comments-min', 0))
        if comments_min < 0:
            comments_min = 0
    except (ValueError, TypeError):
        comments_min = 0

    comments_max_str = request.form.get('comments-max', '')
    if comments_max_str == '' or comments_max_str.lower() == 'any':
        comments_max = None
    else:
        try:
            comments_max = int(comments_max_str)
            if comments_max < 0:
                comments_max = None
        except (ValueError, TypeError):
            comments_max = None

    # Get size range (convert from user units to bytes)
    def parse_size_with_unit(value_str, unit_str):
        """Parse size value and unit, return bytes."""
        if not value_str or value_str.strip() == '':
            return None
        try:
            value = float(value_str)
            if value < 0:
                return None
            unit = unit_str.upper() if unit_str else 'B'
            if unit == 'KB':
                return int(value * 1024)
            elif unit == 'MB':
                return int(value * 1024 * 1024)
            elif unit == 'GB':
                return int(value * 1024 * 1024 * 1024)
            else:  # Bytes
                return int(value)
        except (ValueError, TypeError):
            return None

    size_min_str = request.form.get('size-min', '')
    size_min_unit = request.form.get('size-min-unit', 'KB')
    size_min = parse_size_with_unit(size_min_str, size_min_unit)
    if size_min is None:
        size_min = 0

    size_max_str = request.form.get('size-max', '')
    size_max_unit = request.form.get('size-max-unit', 'MB')
    size_max = parse_size_with_unit(size_max_str, size_max_unit)

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
        'downloads-min': downloads_min,
        'downloads-max': downloads_max if downloads_max is not None else '',
        'solutions-min': solutions_min,
        'solutions-max': solutions_max if solutions_max is not None else '',
        'comments-min': comments_min,
        'comments-max': comments_max if comments_max is not None else '',
        'size-min': size_min_str,
        'size-min-unit': size_min_unit,
        'size-max': size_max_str,
        'size-max-unit': size_max_unit
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
                downloads_max=downloads_max,
                solutions_min=solutions_min,
                solutions_max=solutions_max,
                comments_min=comments_min,
                comments_max=comments_max,
                size_min=size_min,
                size_max=size_max,
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
                downloads_max=downloads_max,
                solutions_min=solutions_min,
                solutions_max=solutions_max,
                comments_min=comments_min,
                comments_max=comments_max,
                size_min=size_min,
                size_max=size_max,
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
    """Display 10 random crackmes in search results (no duplicates)."""
    crackmes = []
    seen_ids = set()
    try:
        attempts = 0
        max_attempts = 50
        while len(crackmes) < 50 and attempts < max_attempts:
            try:
                crackme = random_crackme()
                crackme_id = crackme.get('hexid')
                if crackme_id and crackme_id not in seen_ids:
                    crackmes.append(crackme)
                    seen_ids.add(crackme_id)
            except ErrNoResult:
                break
            attempts += 1
        
        if not crackmes:
            return redirect(url_for('search.search_get'))
        
        return render_template('search/search.html', crackmes=crackmes, page=1, has_more=False, show_all=False, search_params={})
    except Exception as e:
        print(f"Random crackmes error: {e}")
        return redirect(url_for('search.search_get'))
