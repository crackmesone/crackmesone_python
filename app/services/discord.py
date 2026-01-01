"""
Discord webhook notification service.

Two webhooks are supported:
- WebhookPublic: Public channel for approved crackmes/solutions notifications
- WebhookPrivate: Private/admin channel for pending submissions and reviewer logs
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


def get_public_webhook():
    """Get the public Discord webhook URL (for approved items)."""
    return discord_config.get('WebhookPublic', '')


def get_private_webhook():
    """Get the private Discord webhook URL (for pending items and logs)."""
    return discord_config.get('WebhookPrivate', '')


def send_to_webhook(webhook_url: str, message: str) -> bool:
    """Send a message to a specific Discord webhook.

    Args:
        webhook_url: The webhook URL to send to
        message: The message to send

    Returns:
        True if the notification was sent successfully, False otherwise
    """
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


def send_public_notification(message: str) -> bool:
    """Send a notification to the public Discord channel.

    Args:
        message: The message to send

    Returns:
        True if the notification was sent successfully, False otherwise
    """
    if not is_enabled():
        return True
    return send_to_webhook(get_public_webhook(), message)


def send_private_notification(message: str) -> bool:
    """Send a notification to the private/admin Discord channel.

    Args:
        message: The message to send

    Returns:
        True if the notification was sent successfully, False otherwise
    """
    if not is_enabled():
        return True
    return send_to_webhook(get_private_webhook(), message)


def notify_new_crackme(username: str, crackme_name: str) -> bool:
    """Send notification for a new crackme submission (pending review).

    Sent to PRIVATE channel - only admins/reviewers need to see this.

    Args:
        username: The user who submitted the crackme
        crackme_name: The name of the crackme

    Returns:
        True if notification was sent successfully
    """
    message = f"New crackme submission awaiting review: **{crackme_name}** by **{username}**"
    return send_private_notification(message)


def notify_new_solution(username: str, crackme_name: str) -> bool:
    """Send notification for a new solution submission (pending review).

    Sent to PRIVATE channel - only admins/reviewers need to see this.

    Args:
        username: The user who submitted the solution
        crackme_name: The name of the crackme that was solved

    Returns:
        True if notification was sent successfully
    """
    message = f"New solution submission awaiting review: Solution for **{crackme_name}** by **{username}**"
    return send_private_notification(message)
