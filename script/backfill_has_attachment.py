#!/usr/bin/env python3
"""
Backfill the `has_attachment` field on existing solution documents.

On-site markdown writeups introduced a `has_attachment` flag on solutions
(True when the user uploaded a file, so a downloadable archive exists; False for
markdown-only writeups). Solutions created before this feature have no such
field. Every pre-feature solution was a file upload and therefore has a
downloadable archive, so they must be backfilled to has_attachment=True,
otherwise their "Download" button disappears.

This only touches documents that are MISSING the field, so it is safe to re-run
and it never overwrites values set by the application. Before this feature was
deployed, every solution submission required an uploaded file, so every
pre-feature solution missing this field has an attachment.

Usage:
    cd /path/to/crackmesone_python/script
    python backfill_has_attachment.py            # Dry run (default)
    python backfill_has_attachment.py --apply    # Actually apply changes
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient


# Every pre-feature solution was file-backed.
MISSING_FILTER = {'has_attachment': {'$exists': False}}


def main():
    apply_changes = '--apply' in sys.argv
    dry_run = not apply_changes

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'config.json'
    )
    with open(config_path, 'r') as f:
        config = json.load(f)

    mongo_url = config['Database'].get('URL', 'mongodb://127.0.0.1:27017')
    db_name = config['Database'].get('Name', 'crackmesone')

    client = MongoClient(mongo_url)
    collection = client[db_name]['solution']
    print(f"Connected to MongoDB: {db_name}")

    total_missing = collection.count_documents(MISSING_FILTER)

    print(f"\nSolutions missing 'has_attachment': {total_missing}")
    print(f"  -> set has_attachment=True: {total_missing}")

    if total_missing == 0:
        print("\nNothing to backfill. Done.")
        return

    if dry_run:
        print("\n[DRY RUN - no changes made. Use --apply to write.]")
        return

    result = collection.update_many(
        MISSING_FILTER, {'$set': {'has_attachment': True}}
    )

    print(f"\nApplied: {result.modified_count} set True")
    remaining = collection.count_documents(MISSING_FILTER)
    print(f"Remaining without the field: {remaining}")


if __name__ == '__main__':
    main()
