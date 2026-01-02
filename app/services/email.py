"""
Email service using Resend API.
"""

import resend

# Global email configuration
email_config = {}


def configure(config):
    """Configure email settings with Resend API key."""
    global email_config
    email_config = config

    api_key = config.get('ApiKey', '')
    if api_key:
        resend.api_key = api_key


def read_config():
    """Return the email configuration."""
    return email_config


def is_configured():
    """Check if email service is properly configured."""
    return bool(email_config.get('ApiKey'))


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email using Resend.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)

    Returns:
        True if email sent successfully, False otherwise
    """
    global email_config

    if not is_configured():
        print("Email not configured: missing Resend API key")
        return False

    try:
        from_address = email_config.get('From', 'admin@mail.crackmes.one')

        params = {
            "from": from_address,
            "to": [to],
            "subject": subject,
            "text": body,
            "reply_to": "crackmesone@gmail.com",
        }

        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def send_html_email(to: str, subject: str, html_body: str, text_body: str = None) -> bool:
    """Send an HTML email using Resend.

    Args:
        to: Recipient email address
        subject: Email subject
        html_body: Email body (HTML)
        text_body: Optional plain text fallback

    Returns:
        True if email sent successfully, False otherwise
    """
    global email_config

    if not is_configured():
        print("Email not configured: missing Resend API key")
        return False

    try:
        from_address = email_config.get('From', 'admin@mail.crackmes.one')

        params = {
            "from": from_address,
            "to": [to],
            "subject": subject,
            "html": html_body,
        }

        if text_body:
            params["text"] = text_body

        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False
