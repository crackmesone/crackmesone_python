#!/usr/bin/env python3
"""
Apply pre-calculated download counts to the database.

Usage:
    cd /path/to/crackmesone_python/script
    python apply_download_counts.py [--dry-run]

This script reads download_counts.json and updates the nbdownloads field
for each crackme in the database.
"""

import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient


def main():
    dry_run = '--dry-run' in sys.argv

    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Load download counts
    counts_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'download_counts.json')
    with open(counts_path, 'r') as f:
        download_counts = json.load(f)

    print(f"Loaded {len(download_counts)} crackme download counts")
    print(f"Total downloads: {sum(download_counts.values())}")

    # Connect to MongoDB
    mongo_url = config['Database'].get('URL', 'mongodb://127.0.0.1:27017')
    db_name = config['Database'].get('Name', 'crackmesone')

    client = MongoClient(mongo_url)
    db = client[db_name]
    collection = db['crackme']

    print(f"\nConnected to MongoDB: {db_name}")

    if dry_run:
        print("\n[DRY RUN MODE - No changes will be made]\n")

    updated = 0
    not_found = 0
    skipped = 0

    for hexid, count in sorted(download_counts.items(), key=lambda x: -x[1]):
        crackme = collection.find_one({'hexid': hexid})

        if crackme:
            current = crackme.get('nbdownloads', 0)

            if current > 0:
                # Already has downloads, skip to avoid double-counting
                skipped += 1
                continue

            if dry_run:
                print(f"  Would set {hexid}: 0 -> {count}")
            else:
                collection.update_one(
                    {'hexid': hexid},
                    {'$set': {'nbdownloads': count}}
                )
            updated += 1
        else:
            not_found += 1

    print(f"\nResults:")
    print(f"  Updated: {updated}")
    print(f"  Skipped (already has downloads): {skipped}")
    print(f"  Not found in database: {not_found}")

    if dry_run:
        print("\nThis was a dry run. Run without --dry-run to apply changes.")

    client.close()


if __name__ == '__main__':
    main()
