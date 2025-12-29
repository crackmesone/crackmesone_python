"""
Email service for sending SMTP emails.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64

# Global email configuration
email_config = {}


def configure(config):
    """Configure email settings."""
    global email_config
    email_config = config


def read_config():
    """Return the email configuration."""
    return email_config


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)

    Returns:
        True if email sent successfully, False otherwise
    """
    global email_config

    if not email_config:
        print("Email not configured")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = email_config.get('From', '')
        msg['To'] = to
        msg['Subject'] = subject
        msg['MIME-Version'] = '1.0'

        # Attach the body as plain text
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # Connect to SMTP server
        hostname = email_config.get('Hostname', '')
        port = email_config.get('Port', 587)
        username = email_config.get('Username', '')
        password = email_config.get('Password', '')

        with smtplib.SMTP(hostname, port) as server:
            server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False
