"""
Reviewer Logger - Logs reviewer operations to file and Discord.
"""

import logging
import os
import requests
import datetime
from datetime import timezone

# Set up logging configuration - log file in review folder
REVIEW_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(REVIEW_DIR, "review_operations.log")
DISCORD_WEBHOOK_LOG = None  # Will be set by init_logger()

# Configure file logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
    ]
)

logger = logging.getLogger(__name__)


def init_logger(discord_webhook=None):
    """Initialize logger with Discord webhook from config."""
    global DISCORD_WEBHOOK_LOG
    DISCORD_WEBHOOK_LOG = discord_webhook


def log_reviewer_operation(operation_type, user, details, success=True):
    """
    Log a reviewer operation to both local file and Discord webhook.

    Args:
        operation_type (str): Type of operation (e.g., 'delete_solution', 'validate_crackme')
        user (str): Username performing the operation
        details (dict): Additional details about the operation
        success (bool): Whether the operation was successful
    """
    status = "SUCCESS" if success else "FAILED"
    log_message = f"{operation_type} - User: {user} - Status: {status} - Details: {details}"

    # Log to file
    if success:
        logger.info(log_message)
    else:
        logger.error(log_message)

    # Send to Discord webhook if configured
    if DISCORD_WEBHOOK_LOG:
        send_discord_log(operation_type, user, details, success)


def send_discord_log(operation_type, user, details, success):
    """
    Send reviewer operation log to Discord webhook.
    """
    timestamp = datetime.datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    # Determine color based on operation type and success
    if not success:
        color = 16711680  # Red for failures
    elif operation_type.startswith('delete'):
        color = 16753920  # Orange for deletions
    elif operation_type.startswith('validate') or operation_type.startswith('approve'):
        color = 65280  # Green for validations/approvals
    else:
        color = 3447003  # Blue for other operations

    # Format details for Discord
    details_text = "\n".join([f"**{k}:** {v}" for k, v in details.items()]) if details else "No additional details"

    data = {
        "embeds": [
            {
                "title": f"Reviewer Operation: {operation_type.replace('_', ' ').title()}",
                "description": f"Operation performed by **{user}**",
                "color": color,
                "fields": [
                    {
                        "name": "Status",
                        "value": "✅ Success" if success else "❌ Failed",
                        "inline": True
                    },
                    {
                        "name": "Details",
                        "value": details_text[:1024],  # Discord field value limit
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "CrackMes.One Reviewer Tool",
                },
                "timestamp": timestamp,
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_LOG, json=data, timeout=10)
        if response.status_code != 204:
            logger.warning(f"Failed to send Discord log: {response.status_code}")
    except Exception as e:
        logger.warning(f"Failed to send Discord log: {str(e)}")
