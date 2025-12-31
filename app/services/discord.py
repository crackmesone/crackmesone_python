"""
Discord webhook notification service.
"""

import requests

# Global Discord configuration
discord_config = {}


def init_discord(app, config):
    """Initialize Discord configuration."""
    global discord_config
    discord_config = config if config else {}
    app.config['DISCORD_CONFIG'] = discord_config


def is_enabled():
    """Check if Discord notifications are enabled."""
    return discord_config.get('Enabled', False)


def get_webhook_url():
    """Get the Discord webhook URL."""
    return discord_config.get('WebhookURL', '')


def send_notification(message: str) -> bool:
    """Send a notification to Discord via webhook.

    Args:
        message: The message to send

    Returns:
        True if the notification was sent successfully, False otherwise
    """
    if not is_enabled():
        return True

    webhook_url = get_webhook_url()
    if not webhook_url:
        return False

    try:
        payload = {
            'content': message
        }
        response = requests.post(webhook_url, json=payload, timeout=10)
        return response.status_code in (200, 204)
    except Exception as e:
        print(f"Discord notification error: {e}")
        return False


def notify_new_crackme(username: str, crackme_name: str) -> bool:
    """Send notification for a new crackme submission.

    Args:
        username: The user who submitted the crackme
        crackme_name: The name of the crackme

    Returns:
        True if notification was sent successfully
    """
    message = f"New crackme submission awaiting review: **{crackme_name}** by **{username}**"
    return send_notification(message)


def notify_new_solution(username: str, crackme_name: str) -> bool:
    """Send notification for a new solution submission.

    Args:
        username: The user who submitted the solution
        crackme_name: The name of the crackme that was solved

    Returns:
        True if notification was sent successfully
    """
    message = f"New solution submission awaiting review: Solution for **{crackme_name}** by **{username}**"
    return send_notification(message)
