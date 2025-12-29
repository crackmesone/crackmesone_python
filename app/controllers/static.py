"""
Static files controller.
"""

from flask import Blueprint, send_from_directory, abort
import os

static_bp = Blueprint('static_files', __name__)


@static_bp.route('/static/<path:filepath>')
def serve_static(filepath):
    """Serve static files."""
    static_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'static')
    return send_from_directory(static_folder, filepath)


@static_bp.route('/.well-known/<path:filepath>')
def serve_well_known(filepath):
    """Serve .well-known files (for Let's Encrypt, etc.)."""
    well_known_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.well-known')
    return send_from_directory(well_known_folder, filepath)
