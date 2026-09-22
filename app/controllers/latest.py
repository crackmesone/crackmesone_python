"""Combined and category-specific latest activity pages."""

from flask import Blueprint, abort, redirect, render_template

from app.models.crackme import crackmes_by_hexids, last_crackmes
from app.models.solution import latest_solutions
from app.models.solve import latest_solves
from app.models.user import users_by_hexids


latest_bp = Blueprint('latest', __name__)


def _latest_solve_rows(page, per_page):
    solves, has_more = latest_solves(page, per_page)
    users = users_by_hexids(solve['user_hexid'] for solve in solves)
    crackmes = crackmes_by_hexids(solve['crackme_hexid'] for solve in solves)
    rows = [
        {
            'solve': solve,
            'username': users.get(solve['user_hexid'], {}).get('name', 'Deleted user'),
            'crackmename': crackmes.get(solve['crackme_hexid'], {}).get(
                'name', 'Unknown crackme'
            ),
        }
        for solve in solves
    ]
    return rows, has_more


@latest_bp.route('/latest')
def latest_overview():
    """Show the 20 newest crackmes, writeups, and solves."""
    try:
        crackmes, more_crackmes = last_crackmes(1, per_page=20)
        solutions, more_solutions = latest_solutions(1, per_page=20)
        solves, more_solves = _latest_solve_rows(1, per_page=20)
    except Exception as error:
        print(f"Error getting latest activity: {error}")
        abort(500)

    return render_template(
        'latest/index.html',
        crackmes=crackmes,
        solutions=solutions,
        solves=solves,
        more_crackmes=more_crackmes,
        more_solutions=more_solutions,
        more_solves=more_solves,
    )


@latest_bp.route('/latest/solutions')
def latest_solutions_redirect():
    return redirect('/latest/solutions/1')


@latest_bp.route('/latest/solutions/<int:page>')
def latest_solutions_page(page):
    """Display approved writeups newest first."""
    page = max(page, 1)
    try:
        solutions, has_more = latest_solutions(page)
    except Exception as error:
        print(f"Error getting latest solutions: {error}")
        abort(500)
    return render_template(
        'latest/solutions.html', solutions=solutions, page=page, has_more=has_more
    )


@latest_bp.route('/latest/solves')
def latest_solves_redirect():
    return redirect('/latest/solves/1')


@latest_bp.route('/latest/solves/<int:page>')
def latest_solves_page(page):
    """Display flag solves newest first."""
    page = max(page, 1)
    try:
        solves, has_more = _latest_solve_rows(page, 50)
    except Exception as error:
        print(f"Error getting latest solves: {error}")
        abort(500)
    return render_template(
        'latest/solves.html', solves=solves, page=page, has_more=has_more
    )
