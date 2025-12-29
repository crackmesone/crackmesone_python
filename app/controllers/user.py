"""
User controller - User profiles.
"""

from flask import Blueprint, render_template, session, abort
from app.models.user import user_by_name
from app.models.crackme import crackmes_by_user, count_crackmes_by_user, crackme_by_hexid
from app.models.solution import solutions_by_user, count_solutions_by_user
from app.models.comment import comments_by_user, count_comments_by_user
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
        # Get user's crackmes
        crackmes = crackmes_by_user(actual_username)
        nb_crackmes = count_crackmes_by_user(actual_username)

        # Get user's solutions
        solutions = solutions_by_user(actual_username)
        nb_solutions = count_solutions_by_user(actual_username)

        # Get user's comments
        comments = comments_by_user(actual_username)
        nb_comments = count_comments_by_user(actual_username)

        # Extend solutions with crackme info
        solutions_extended = []
        for solution in solutions:
            crackme_hexid = str(solution['crackmeid'])
            try:
                crackme = crackme_by_hexid(crackme_hexid)
                solutions_extended.append({
                    'solution': solution,
                    'crackmeshexid': crackme_hexid,
                    'crackmename': crackme['name']
                })
            except ErrNoResult:
                solutions_extended.append({
                    'solution': solution,
                    'crackmeshexid': crackme_hexid,
                    'crackmename': '[Deleted]'
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
