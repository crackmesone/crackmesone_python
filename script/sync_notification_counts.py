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

    # Aggregate unseen notification counts per user in one query
    print("Aggregating unseen notifications...")
    pipeline = [
        {'$match': {'seen': False}},
        {'$group': {'_id': '$user', 'count': {'$sum': 1}}}
    ]
    actual_counts = {doc['_id']: doc['count'] for doc in notifs_collection.aggregate(pipeline)}
    print(f"  Found {len(actual_counts)} users with unseen notifications")

    # Get all users with their current counts
    print("Fetching user records...")
    users = {
        user['name']: (user['_id'], user.get('unread_notifications', 0) or 0)
        for user in users_collection.find({}, {'name': 1, 'unread_notifications': 1})
    }
    print(f"  Found {len(users)} total users")

    print("Comparing counts...")

    updated = 0
    unchanged = 0

    # Check users who have unseen notifications
    for username, actual_count in actual_counts.items():
        if username not in users:
            continue  # Skip notifications for non-existent users
        user_id, current_count = users[username]
        if actual_count != current_count:
            if dry_run:
                print(f"  Would update {username}: {current_count} -> {actual_count}")
            else:
                users_collection.update_one(
                    {'_id': user_id},
                    {'$set': {'unread_notifications': actual_count}}
                )
                print(f"  Updated {username}: {current_count} -> {actual_count}")
            updated += 1
        else:
            unchanged += 1

    # Check users who should have 0 but don't (not in actual_counts means 0 unseen)
    for username, (user_id, current_count) in users.items():
        if username not in actual_counts and current_count != 0:
            if dry_run:
                print(f"  Would update {username}: {current_count} -> 0")
            else:
                users_collection.update_one(
                    {'_id': user_id},
                    {'$set': {'unread_notifications': 0}}
                )
                print(f"  Updated {username}: {current_count} -> 0")
            updated += 1

    print(f"\nResults:")
    print(f"  Updated: {updated}")
    print(f"  Unchanged: {len(users) - updated}")

    if dry_run:
        print("\nThis was a dry run. Use --apply to actually apply changes.")

    client.close()


if __name__ == '__main__':
    main()
