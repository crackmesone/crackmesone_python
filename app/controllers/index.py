"""
Index controller - Home page.
"""

from math import ceil

from flask import Blueprint, abort, redirect, render_template
from app.models.user import count_users
from app.models.crackme import count_crackmes
from app.models.solution import count_solutions
from app.models.solve import scoreboard

index_bp = Blueprint('index', __name__)


@index_bp.route('/')
def index():
    """Display the home page."""
    try:
        nbusers = count_users()
        nbcrackmes = count_crackmes()
        nbsolutions = count_solutions()
    except Exception as e:
        print(f"Error getting counts: {e}")
        nbusers = nbcrackmes = nbsolutions = 0

    return render_template('index/index.html',
                           nbusers=nbusers,
                           nbcrackmes=nbcrackmes,
                           nbsolutions=nbsolutions)


@index_bp.route('/scoreboard')
def scoreboard_index():
    return _scoreboard_page(1)


def _scoreboard_page(page):
    try:
        rows, has_more, total = scoreboard(page)
    except Exception as e:
        print(f"Error getting scoreboard: {e}")
        abort(500)

    if page > 1 and not rows:
        last_page = max(1, ceil(total / 25))
        return redirect('/scoreboard' if last_page == 1
                        else f'/scoreboard/{last_page}')

    return render_template('scoreboard/index.html',
                           scoreboard=rows,
                           page=page,
                           has_more=has_more)


@index_bp.route('/scoreboard/<int:page>')
def scoreboard_page(page):
    if page < 2:
        return redirect('/scoreboard')
    return _scoreboard_page(page)
