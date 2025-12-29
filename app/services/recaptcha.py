"""
Google reCAPTCHA service.
"""

import requests

# Global recaptcha configuration
recaptcha_config = {}


def init_recaptcha(app, config):
    """Initialize reCAPTCHA configuration."""
    global recaptcha_config
    recaptcha_config = config
    app.config['RECAPTCHA_CONFIG'] = config


def read_config():
    """Return the reCAPTCHA configuration."""
    return recaptcha_config


def is_enabled():
    """Check if reCAPTCHA is enabled."""
    return recaptcha_config.get('Enabled', False)


def get_site_key():
    """Get the reCAPTCHA site key."""
    if is_enabled():
        return recaptcha_config.get('SiteKey', '')
    return ''


def verify(request) -> bool:
    """Verify the reCAPTCHA response.

    Args:
        request: Flask request object

    Returns:
        True if verification passed or reCAPTCHA is disabled
    """
    if not is_enabled():
        return True

    response_token = request.form.get('g-recaptcha-response', '')
    if not response_token:
        return False

    try:
        verify_url = 'https://www.google.com/recaptcha/api/siteverify'
        payload = {
            'secret': recaptcha_config.get('Secret', ''),
            'response': response_token,
            'remoteip': request.remote_addr
        }

        response = requests.post(verify_url, data=payload, timeout=10)
        result = response.json()

        return result.get('success', False)
    except Exception as e:
        print(f"reCAPTCHA verification error: {e}")
        return False
