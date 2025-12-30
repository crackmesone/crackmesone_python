"""
User controller - User profiles.
"""

from flask import Blueprint, render_template, session, abort
from app.models.user import user_by_name
from app.models.crackme import crackmes_by_user
from app.models.solution import solutions_by_user
from app.models.comment import comments_by_user
from app.models.errors import ErrNoResult

user_bp = Blueprint('user', __name__)


@user_bp.route('/user/<name>')
def user_profile(name):
    """Display a user's profile."""
    try:
        user = user_by_name(name)
    except ErrNoResult:
        abort(404)
    except Exception as e:
        print(f"Error getting user: {e}")
        abort(500)

    # Use actual username from database (for case consistency)
    actual_username = user['name']

    try:
        # Get user's crackmes, solutions, and comments
        crackmes = crackmes_by_user(actual_username)
        solutions = solutions_by_user(actual_username)
        comments = comments_by_user(actual_username)

        # Use len() instead of separate count queries
        nb_crackmes = len(crackmes)
        nb_solutions = len(solutions)
        nb_comments = len(comments)

        # Build extended solutions using stored crackme name (no N+1 queries)
        solutions_extended = []
        for solution in solutions:
            solutions_extended.append({
                'solution': solution,
                'crackmeshexid': solution.get('crackmehexid', ''),
                'crackmename': solution.get('crackmename', '')
            })

        # Check if viewing own profile
        session_username = session.get('name', '')
        viewing_own_page = session_username and session_username == actual_username

        return render_template('user/read.html',
                               username=user['name'],
                               NbCrackmes=nb_crackmes,
                               NbSolutions=nb_solutions,
                               NbComments=nb_comments,
                               crackmes=crackmes,
                               solutions=solutions_extended,
                               comments=comments,
                               viewingOwnPage=viewing_own_page)

    except Exception as e:
        print(f"Error getting user data: {e}")
        abort(500)
