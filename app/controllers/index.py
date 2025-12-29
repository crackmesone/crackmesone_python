"""
Index controller - Home page.
"""

from flask import Blueprint, render_template
from app.models.user import count_users
from app.models.crackme import count_crackmes
from app.models.solution import count_solutions

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
