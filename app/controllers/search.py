"""
Search controller - Searching crackmes.
"""

from flask import Blueprint, render_template, request, session
from app.models.crackme import search_crackme, random_crackmes
from app.models.user import user_all_solved_hexids  # Issue #182
from app.models.errors import ErrUnavailable
from app.services.labels import get_label_groups, normalize_labels

search_bp = Blueprint('search', __name__)


@search_bp.route('/search', methods=['GET'])
def search_get():
    """Display the search page.

    Searches are driven by URL query parameters so results are bookmarkable and
    shareable (issue #162). A bare ``/search`` with no parameters shows the empty
    form; any parameter (e.g. ``/search?labels=Packer``) runs a search.
    """
    username = session.get('name')
    if not request.args:
        solved_sets = user_all_solved_hexids(username) if username else {
            'official': frozenset(), 'manual': frozenset(), 'all': frozenset()
        }
        return render_template('search/search.html',
                               crackmes=[],
                               page=1,
                               has_more=False,
                               show_all=False,
                               search_params={},
                               label_groups=get_label_groups(),
                               official_solves=solved_sets['official'],
                               manual_solves=solved_sets['manual'],
                               all_solves=solved_sets['all'],
                               hide_solved=False,
                               is_logged_in=bool(username))
    return _render_search(request.args)


@search_bp.route('/search', methods=['POST'])
def search_post():
    """Handle a POST search submission (kept for backward compatibility)."""
    return _render_search(request.form)


def _render_search(source):
    """Run a crackme search from a request MultiDict (``request.args`` or form).

    ``source`` provides ``.get`` and ``.getlist``, so the same logic serves both
    bookmarkable GET URLs and legacy POST submissions.
    """
    name = source.get('name', '')
    author = source.get('author', '')
    # Use getlist() for multi-select fields
    lang = source.getlist('lang')
    arch = source.getlist('arch')
    platform = source.getlist('platform')
    # Accept the legacy ``tags`` param name so pre-rename bookmarked/shared
    # search URLs (issue #167) keep working.
    labels = normalize_labels(source.getlist('labels') or source.getlist('tags'))

    # Get difficulty range
    try:
        difficulty_min = int(source.get('difficulty-min', 1))
    except (ValueError, TypeError):
        difficulty_min = 1

    try:
        difficulty_max = int(source.get('difficulty-max', 6))
    except (ValueError, TypeError):
        difficulty_max = 6

    # Get quality range
    try:
        quality_min = int(source.get('quality-min', 1))
    except (ValueError, TypeError):
        quality_min = 1

    try:
        quality_max = int(source.get('quality-max', 6))
    except (ValueError, TypeError):
        quality_max = 6

    # Get downloads range
    try:
        downloads_min = int(source.get('downloads-min', 0))
        if downloads_min < 0:
            downloads_min = 0
    except (ValueError, TypeError):
        downloads_min = 0

    downloads_max_str = source.get('downloads-max', '')
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
        solutions_min = int(source.get('solutions-min', 0))
        if solutions_min < 0:
            solutions_min = 0
    except (ValueError, TypeError):
        solutions_min = 0

    solutions_max_str = source.get('solutions-max', '')
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
        comments_min = int(source.get('comments-min', 0))
        if comments_min < 0:
            comments_min = 0
    except (ValueError, TypeError):
        comments_min = 0

    comments_max_str = source.get('comments-max', '')
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

    size_min_str = source.get('size-min', '')
    size_min_unit = source.get('size-min-unit', 'KB')
    size_min = parse_size_with_unit(size_min_str, size_min_unit)
    if size_min is None:
        size_min = 0

    size_max_str = source.get('size-max', '')
    size_max_unit = source.get('size-max-unit', 'MB')
    size_max = parse_size_with_unit(size_max_str, size_max_unit)

    # Get page number and show_all flag
    try:
        page = int(source.get('page', 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    show_all = source.get('show_all') == '1'

    # Get sort options
    sort_by = source.get('sort_by', 'date')
    if sort_by not in ('date', 'size', 'downloads', 'solutions', 'comments', 'quality', 'difficulty'):
        sort_by = 'date'
    sort_order = source.get('sort_order', 'desc')
    if sort_order not in ('asc', 'desc'):
        sort_order = 'desc'

    # --- Solved crackmes (Issue #182) ---
    # For logged-in users: build a unified set of solved hexids (official +
    # manual) in a single function call (2 DB reads total, not N+1).
    # For guests: empty sets -- the feature is invisible but the page still works.
    username = session.get('name')
    solved_sets = user_all_solved_hexids(username) if username else {
        'official': frozenset(), 'manual': frozenset(), 'all': frozenset()
    }
    official_solves = solved_sets['official']
    manual_solves   = solved_sets['manual']
    all_solves      = solved_sets['all']

    # Hide solved: only active for logged-in users
    hide_solved = bool(source.get('hide_solved')) and bool(username)
    exclude_hexids = list(all_solves) if hide_solved else None

    # Store search params for pagination
    # lang, arch, platform are lists for multi-select support
    search_params = {
        'name': name,
        'author': author,
        'lang': lang,  # list
        'arch': arch,  # list
        'platform': platform,  # list
        'labels': labels,  # list
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
        'size-max-unit': size_max_unit,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'hide_solved': hide_solved,    # Issue #182
    }

    try:
        if show_all:
            crackmes, _ = search_crackme(
                name=name,
                author=author,
                lang=lang,
                arch=arch,
                platform=platform,
                labels=labels,
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
                sort_by=sort_by,
                sort_order=sort_order,
                page=1,
                per_page=10000,
                exclude_hexids=exclude_hexids   # Issue #182
            )
            has_more = False
        else:
            crackmes, has_more = search_crackme(
                name=name,
                author=author,
                lang=lang,
                arch=arch,
                platform=platform,
                labels=labels,
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
                sort_by=sort_by,
                sort_order=sort_order,
                page=page,
                exclude_hexids=exclude_hexids   # Issue #182
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
                           search_params=search_params,
                           label_groups=get_label_groups(),
                           official_solves=official_solves,   # Issue #182
                           manual_solves=manual_solves,       # Issue #182
                           all_solves=all_solves,             # Issue #182
                           hide_solved=hide_solved,           # Issue #182
                           is_logged_in=bool(username))       # Issue #182


@search_bp.route('/random', methods=['GET'])
def random_get():
    """Display 50 random crackmes."""
    # Get sort options from query params
    sort_by = request.args.get('sort_by', 'date')
    if sort_by not in ('date', 'size', 'downloads', 'solutions', 'comments', 'quality', 'difficulty'):
        sort_by = 'date'
    sort_order = request.args.get('sort_order', 'desc')
    if sort_order not in ('asc', 'desc'):
        sort_order = 'desc'

    username = session.get('name')
    hide_solved = bool(request.args.get('hide_solved'))

    if username:
        solved_sets = user_all_solved_hexids(username)
        official_solves = solved_sets['official']
        manual_solves   = solved_sets['manual']
        all_solves      = solved_sets['all']
        exclude_hexids  = all_solves if (hide_solved and all_solves) else None
    else:
        official_solves = frozenset()
        manual_solves   = frozenset()
        all_solves      = frozenset()
        exclude_hexids  = None
        hide_solved     = False

    try:
        crackmes = random_crackmes(50, exclude_hexids=exclude_hexids)
        # Sort the random results
        sort_key_map = {
            'date': 'created_at',
            'size': 'size',
            'downloads': 'nbdownloads',
            'solutions': 'nbsolutions',
            'comments': 'nbcomments',
            'quality': 'quality',
            'difficulty': 'difficulty',
        }
        sort_key = sort_key_map.get(sort_by, 'created_at')
        crackmes.sort(key=lambda x: x.get(sort_key) or 0, reverse=(sort_order == 'desc'))
    except ErrUnavailable:
        crackmes = []

    search_params = {
        'sort_by': sort_by,
        'sort_order': sort_order,
        'hide_solved': '1' if hide_solved else '',
    }

    return render_template('search/search.html',
                           crackmes=crackmes,
                           page=1,
                           has_more=False,
                           show_all=True,
                           search_params=search_params,
                           label_groups=get_label_groups(),
                           official_solves=official_solves,
                           manual_solves=manual_solves,
                           all_solves=all_solves,
                           hide_solved=hide_solved,
                           is_logged_in=bool(username))
