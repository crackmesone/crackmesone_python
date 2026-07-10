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
and it never overwrites values set by the application. As a safeguard, any
markdown-only writeup that predates the field (content present, no uploaded
file) is set to False rather than True.

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


# Documents missing the field that are actually markdown-only writeups
# (content present, no uploaded file) -> has_attachment should be False.
MARKDOWN_ONLY_FILTER = {
    'has_attachment': {'$exists': False},
    'content': {'$exists': True, '$nin': [None, '']},
    '$or': [
        {'original_filename': {'$exists': False}},
        {'original_filename': {'$in': [None, '']}},
    ],
}

# Everything else missing the field is a pre-feature file solution -> True.
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
    md_only = collection.count_documents(MARKDOWN_ONLY_FILTER)
    to_true = total_missing - md_only

    print(f"\nSolutions missing 'has_attachment': {total_missing}")
    print(f"  -> set has_attachment=True  (file solutions): {to_true}")
    print(f"  -> set has_attachment=False (markdown-only)  : {md_only}")

    if total_missing == 0:
        print("\nNothing to backfill. Done.")
        return

    if dry_run:
        print("\n[DRY RUN - no changes made. Use --apply to write.]")
        return

    # Mark markdown-only writeups first so they are no longer "missing",
    # then set every remaining missing document to True.
    false_res = collection.update_many(
        MARKDOWN_ONLY_FILTER, {'$set': {'has_attachment': False}}
    )
    true_res = collection.update_many(
        MISSING_FILTER, {'$set': {'has_attachment': True}}
    )

    print(f"\nApplied: {true_res.modified_count} set True, "
          f"{false_res.modified_count} set False")
    remaining = collection.count_documents(MISSING_FILTER)
    print(f"Remaining without the field: {remaining}")


if __name__ == '__main__':
    main()
