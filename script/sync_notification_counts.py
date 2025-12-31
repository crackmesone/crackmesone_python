#!/usr/bin/env python3
"""
Sync notification counts from notifications collection to user records.

Usage:
    cd /path/to/crackmesone_python/script
    python sync_notification_counts.py          # Dry run (default)
    python sync_notification_counts.py --apply  # Actually apply changes

This script counts unseen notifications per user and updates the
unread_notifications field in their user record.
"""

import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient


def main():
    apply_changes = '--apply' in sys.argv
    dry_run = not apply_changes

    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Connect to MongoDB
    mongo_url = config['Database'].get('URL', 'mongodb://127.0.0.1:27017')
    db_name = config['Database'].get('Name', 'crackmesone')

    client = MongoClient(mongo_url)
    db = client[db_name]
    users_collection = db['user']
    notifs_collection = db['notifications']

    print(f"Connected to MongoDB: {db_name}")

    if dry_run:
        print("\n[DRY RUN MODE - No changes will be made]")
        print("[Use --apply to actually apply changes]\n")

    # Get all users
    users = list(users_collection.find({}, {'name': 1, 'unread_notifications': 1}))
    print(f"Found {len(users)} users")

    updated = 0
    unchanged = 0

    for user in users:
        username = user['name']
        current_count = user.get('unread_notifications')  # None if missing

        # Count actual unseen notifications
        actual_count = notifs_collection.count_documents({
            'user': username,
            'seen': False
        })

        # Update if count differs OR if field is missing (ensure all users have the field)
        if actual_count != current_count:
            current_display = current_count if current_count is not None else 0
            if dry_run:
                print(f"  Would update {username}: {current_display} -> {actual_count}")
            else:
                users_collection.update_one(
                    {'_id': user['_id']},
                    {'$set': {'unread_notifications': actual_count}}
                )
                print(f"  Updated {username}: {current_display} -> {actual_count}")
            updated += 1
        else:
            unchanged += 1

    print(f"\nResults:")
    print(f"  Updated: {updated}")
    print(f"  Unchanged: {unchanged}")

    if dry_run:
        print("\nThis was a dry run. Use --apply to actually apply changes.")

    client.close()


if __name__ == '__main__':
    main()
