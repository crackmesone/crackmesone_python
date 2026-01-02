"""
Discord webhook notification service.

Two webhooks are supported:
- WebhookPublic: Public channel for approved crackmes/solutions notifications
- WebhookPrivate: Private/admin channel for pending submissions and reviewer logs
"""

import datetime
from datetime import timezone
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


def send_to_webhook(webhook_url: str, message: str = None, embed: dict = None) -> bool:
    """Send a message to a specific Discord webhook.

    Args:
        webhook_url: The webhook URL to send to
        message: The text message to send (optional if embed provided)
        embed: The embed object to send (optional if message provided)

    Returns:
        True if the notification was sent successfully, False otherwise
    """
    if not webhook_url:
        return False

    try:
        payload = {}
        if message:
            payload['content'] = message
        if embed:
            payload['embeds'] = [embed]

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


def send_private_notification(message: str = None, embed: dict = None) -> bool:
    """Send a notification to the private/admin Discord channel.

    Args:
        message: The text message to send (optional if embed provided)
        embed: The embed object to send (optional if message provided)

    Returns:
        True if the notification was sent successfully, False otherwise
    """
    if not is_enabled():
        return True
    return send_to_webhook(get_private_webhook(), message=message, embed=embed)


def _create_pending_embed(title: str, submission_type: str, details: dict) -> dict:
    """Create a Discord embed for pending submissions.

    Args:
        title: The embed title
        submission_type: Type of submission ('crackme' or 'solution')
        details: Dictionary of field name -> value pairs

    Returns:
        Discord embed dictionary
    """
    timestamp = (
        datetime.datetime.utcnow()
        .replace(tzinfo=timezone.utc)
        .isoformat(timespec='milliseconds')
        .replace('+00:00', 'Z')
    )

    # Yellow/gold color for pending items
    color = 16776960

    # Format details as fields
    fields = [
        {"name": key, "value": str(value), "inline": True}
        for key, value in details.items()
    ]

    return {
        "title": title,
        "description": f"New {submission_type} awaiting review",
        "color": color,
        "fields": fields,
        "footer": {
            "text": "CrackMes.One Reviewer Tool",
        },
        "timestamp": timestamp,
    }


def notify_new_crackme(username: str, crackme_name: str) -> bool:
    """Send notification for a new crackme submission (pending review).

    Sent to PRIVATE channel - only admins/reviewers need to see this.

    Args:
        username: The user who submitted the crackme
        crackme_name: The name of the crackme

    Returns:
        True if notification was sent successfully
    """
    embed = _create_pending_embed(
        title="Pending Crackme Submission",
        submission_type="crackme",
        details={
            "Challenge": crackme_name,
            "Author": username,
        }
    )
    return send_private_notification(embed=embed)


def notify_new_solution(username: str, crackme_name: str) -> bool:
    """Send notification for a new solution submission (pending review).

    Sent to PRIVATE channel - only admins/reviewers need to see this.

    Args:
        username: The user who submitted the solution
        crackme_name: The name of the crackme that was solved

    Returns:
        True if notification was sent successfully
    """
    embed = _create_pending_embed(
        title="Pending Solution Submission",
        submission_type="solution",
        details={
            "Challenge": crackme_name,
            "Author": username,
        }
    )
    return send_private_notification(embed=embed)
