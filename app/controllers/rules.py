"""
Rules controller - Crackme and solution rules pages.
"""

from flask import Blueprint, render_template

rules_bp = Blueprint('rules', __name__)


@rules_bp.route('/upload/writeuprules')
def solution_rules():
    """Display solution/writeup rules."""
    return render_template('rules/solutionrules.html')


@rules_bp.route('/upload/crackmerules')
def crackme_rules():
    """Display crackme upload rules."""
    return render_template('rules/crackmerules.html')
