"""
View service for template rendering and helpers.
"""

import re
import os
from datetime import datetime
from flask import flash as flask_flash
from markupsafe import Markup

# Constants for flash message classes (Bootstrap)
FLASH_ERROR = 'alert-danger'
FLASH_SUCCESS = 'alert-success'
FLASH_NOTICE = 'alert-info'
FLASH_WARNING = 'alert-warning'

# Authorized characters for usernames/emails
AUTHORIZED_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-@.+"

# Global view configuration
view_config = {}


def init_view(app, config):
    """Initialize view configuration."""
    global view_config
    view_config = config


def read_config():
    """Return the view configuration."""
    return view_config


def authorized_chars_only(s: str) -> bool:
    """Check if string contains only authorized characters."""
    for char in s:
        if char not in AUTHORIZED_CHARS:
            return False
    return True


def validate_required(form, required_fields):
    """Validate that all required fields are present.

    Args:
        form: Flask request form
        required_fields: List of required field names

    Returns:
        Tuple of (is_valid, missing_field)
    """
    for field in required_fields:
        if not form.get(field):
            return False, field
    return True, None


def add_flash(message, category=FLASH_NOTICE):
    """Add a flash message.

    Args:
        message: The flash message text
        category: The message category/class
    """
    flask_flash(message, category)


def register_filters(app):
    """Register custom Jinja2 filters."""

    @app.template_filter('PRETTYTIME')
    def pretty_time(dt):
        """Format datetime in a human-readable way."""
        if dt is None or (hasattr(dt, '_undefined_name')):
            return ''
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except ValueError:
                return dt
        try:
            return dt.strftime('%Y-%m-%d %H:%M')
        except AttributeError:
            return ''

    @app.template_filter('TIMECOMPARE')
    def time_compare(dt1, dt2):
        """Compare two datetime objects."""
        if dt1 is None or dt2 is None:
            return False
        return dt1 > dt2

    @app.template_filter('PRETTYTIMEFORMAT')
    def pretty_time_format(dt, fmt):
        """Format datetime with custom format string."""
        if dt is None or (hasattr(dt, '_undefined_name')):
            return ''
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except ValueError:
                return dt
        try:
            return dt.strftime(fmt)
        except AttributeError:
            return ''

    @app.template_global('TIMECOMPARE')
    def time_compare_global(dt1, dt2, seconds_threshold):
        """Compare if two datetimes differ by more than threshold seconds."""
        if dt1 is None or dt2 is None:
            return True
        try:
            diff = abs((dt2 - dt1).total_seconds())
            return diff > seconds_threshold
        except (TypeError, AttributeError):
            return True

    @app.template_filter('noescape')
    def no_escape(value):
        """Mark a value as safe (no HTML escaping)."""
        return Markup(value)


def repopulate(fields, form_data, context):
    """Repopulate form fields in template context.

    Args:
        fields: List of field names to repopulate
        form_data: Form data dict
        context: Template context dict to update
    """
    for field in fields:
        context[field] = form_data.get(field, '')


class Flash:
    """Flash message class for template compatibility."""

    def __init__(self, message, css_class=FLASH_NOTICE):
        self.Message = message
        self.Class = css_class
