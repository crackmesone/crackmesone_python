"""
FAQ controller - FAQ page.
"""

from flask import Blueprint, render_template

faq_bp = Blueprint('faq', __name__)


@faq_bp.route('/faq')
def faq():
    """Display the FAQ page."""
    return render_template('faq/faq.html')
