"""
Discord webhook notification service.

Three webhooks are supported:
- WebhookPublic: Public channel for approved crackmes/solutions notifications
- WebhookPrivate: Private/admin channel for pending submissions and reviewer logs
- WebhookModeration: Moderation channel for user activity (comments, etc.)
"""

import datetime
from datetime import timezone
import requests

# Global Discord configuration
discord_config = {}
site_config = {}


def init_discord(app, config):
    """Initialize Discord configuration."""
    global discord_config, site_config
    discord_config = config if config else {}
    app.config['DISCORD_CONFIG'] = discord_config
    # Store site config for base URL
    site_config = app.config.get('APP_CONFIG', {}).get('Site', {})


def get_base_url():
    """Get configured base URL."""
    return site_config.get('BaseURL', 'https://crackmes.one')


def is_enabled():
    """Check if Discord notifications are enabled."""
    return discord_config.get('Enabled', False)


def get_public_webhook():
    """Get the public Discord webhook URL (for approved items)."""
    return discord_config.get('WebhookPublic', '')


def get_private_webhook():
    """Get the private Discord webhook URL (for pending items and logs)."""
    return discord_config.get('WebhookPrivate', '')


def get_moderation_webhook():
    """Get the moderation Discord webhook URL (for user activity like comments)."""
    return discord_config.get('WebhookModeration', '')


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


def send_moderation_notification(embed: dict) -> bool:
    """Send a notification to the moderation Discord channel.

    Args:
        embed: The embed object to send

    Returns:
        True if the notification was sent successfully, False otherwise
    """
    if not is_enabled():
        return True
    return send_to_webhook(get_moderation_webhook(), embed=embed)


def notify_new_comment(username: str, crackme_name: str, crackme_hexid: str,
                       comment_text: str, is_spoiler: bool = False,
                       comment_id: str = None, spoiler_token: str = None) -> bool:
    """Send notification for a new comment posted.

    Sent to MODERATION channel for monitoring user activity.

    Args:
        username: The user who posted the comment
        crackme_name: The name of the crackme
        crackme_hexid: The hexid of the crackme (for link)
        comment_text: The comment content
        is_spoiler: Whether the comment is marked as spoiler
        comment_id: The comment ID (for mark-as-spoiler link)
        spoiler_token: Secret token for mark-as-spoiler action

    Returns:
        True if notification was sent successfully
    """
    timestamp = (
        datetime.datetime.utcnow()
        .replace(tzinfo=timezone.utc)
        .isoformat(timespec='milliseconds')
        .replace('+00:00', 'Z')
    )

    # Cyan/teal for normal comments, orange for spoiler-marked comments
    color = 16753920 if is_spoiler else 65535

    # Truncate comment if too long
    truncated_comment = comment_text[:500] + "..." if len(comment_text) > 500 else comment_text

    # Build title with spoiler indicator
    title = "New Comment Posted"
    if is_spoiler:
        title += " [SPOILER]"

    fields = [
        {
            "name": "Challenge",
            "value": f"[{crackme_name}]({get_base_url()}/crackme/{crackme_hexid})",
            "inline": True
        },
        {
            "name": "Author",
            "value": f"[{username}]({get_base_url()}/user/{username})",
            "inline": True
        },
        {
            "name": "Comment",
            "value": truncated_comment,
            "inline": False
        }
    ]

    # Add mark-as-spoiler action link if not already a spoiler and token provided
    if not is_spoiler and comment_id and spoiler_token:
        fields.append({
            "name": "Actions",
            "value": f"[Mark as Spoiler]({get_base_url()}/comment/{comment_id}/spoiler-token/{spoiler_token})",
            "inline": False
        })

    embed = {
        "title": title,
        "description": f"A new comment has been posted on crackmes.one",
        "color": color,
        "fields": fields,
        "footer": {
            "text": "CrackMes.One",
        },
        "timestamp": timestamp,
    }
    return send_moderation_notification(embed)


def notify_spoiler_toggle(username: str, crackme_name: str, crackme_hexid: str,
                          comment_author: str, is_spoiler: bool) -> bool:
    """Send notification when a user marks/unmarks a comment as spoiler.

    Sent to MODERATION channel for monitoring user activity.

    Args:
        username: The crackme owner who toggled the spoiler
        crackme_name: The name of the crackme
        crackme_hexid: The hexid of the crackme (for link)
        comment_author: The author of the comment
        is_spoiler: True if marked as spoiler, False if unmarked

    Returns:
        True if notification was sent successfully
    """
    timestamp = (
        datetime.datetime.utcnow()
        .replace(tzinfo=timezone.utc)
        .isoformat(timespec='milliseconds')
        .replace('+00:00', 'Z')
    )

    # Orange color for spoiler actions
    color = 16753920

    action = "marked as spoiler" if is_spoiler else "unmarked as spoiler"

    embed = {
        "title": f"Comment {action.title()}",
        "description": f"A comment has been {action}",
        "color": color,
        "fields": [
            {
                "name": "Challenge",
                "value": f"[{crackme_name}](https://crackmes.one/crackme/{crackme_hexid})",
                "inline": True
            },
            {
                "name": "Marked by",
                "value": f"[{username}](https://crackmes.one/user/{username})",
                "inline": True
            },
            {
                "name": "Comment Author",
                "value": f"[{comment_author}](https://crackmes.one/user/{comment_author})",
                "inline": True
            }
        ],
        "footer": {
            "text": "CrackMes.One",
        },
        "timestamp": timestamp,
    }
    return send_moderation_notification(embed)


def notify_password_reset_request(email: str) -> bool:
    """Send notification when someone requests a password reset.

    Sent to MODERATION channel for monitoring.

    Args:
        email: The email address that requested reset

    Returns:
        True if notification was sent successfully
    """
    timestamp = (
        datetime.datetime.utcnow()
        .replace(tzinfo=timezone.utc)
        .isoformat(timespec='milliseconds')
        .replace('+00:00', 'Z')
    )

    # Orange color for password reset requests
    color = 16744448

    embed = {
        "title": "Password Reset Requested",
        "description": "A user has requested a password reset link",
        "color": color,
        "fields": [
            {
                "name": "Email",
                "value": email,
                "inline": True
            }
        ],
        "footer": {
            "text": "CrackMes.One",
        },
        "timestamp": timestamp,
    }
    return send_moderation_notification(embed)


def notify_password_reset_complete(username: str, email: str) -> bool:
    """Send notification when someone completes a password reset.

    Sent to MODERATION channel for monitoring.

    Args:
        username: The username whose password was reset
        email: The email address associated with the account

    Returns:
        True if notification was sent successfully
    """
    timestamp = (
        datetime.datetime.utcnow()
        .replace(tzinfo=timezone.utc)
        .isoformat(timespec='milliseconds')
        .replace('+00:00', 'Z')
    )

    # Green color for successful reset
    color = 65280

    embed = {
        "title": "Password Reset Completed",
        "description": "A user has successfully reset their password",
        "color": color,
        "fields": [
            {
                "name": "User",
                "value": f"[{username}]({get_base_url()}/user/{username})",
                "inline": True
            },
            {
                "name": "Email",
                "value": email,
                "inline": True
            }
        ],
        "footer": {
            "text": "CrackMes.One",
        },
        "timestamp": timestamp,
    }
    return send_moderation_notification(embed)
