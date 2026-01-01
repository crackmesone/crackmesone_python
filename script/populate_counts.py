#!/usr/bin/env python3
"""
Verify and fix NbSolutions and NbComments counts for all crackmes.

This script:
1. Counts the actual number of visible solutions and comments for each crackme
2. Compares with the stored nbsolutions and nbcomments values
3. Shows differences (dry-run mode by default)
4. Updates database when --apply flag is provided

Usage:
    python populate_counts.py                    # Dry-run mode (shows differences)
    python populate_counts.py --apply            # Apply updates to database
    python populate_counts.py --uri mongodb://host:port --db dbname
"""

import argparse
import sys
from pymongo import MongoClient
from bson import ObjectId


def count_solutions_for_crackme(solutions_collection, crackme_id):
    """Count visible solutions for a crackme by ObjectId."""
    return solutions_collection.count_documents({
        'crackmeid': crackme_id,
        'visible': True
    })


def count_comments_for_crackme(comments_collection, hex_id):
    """Count visible comments for a crackme by hexid."""
    return comments_collection.count_documents({
        'crackmehexid': hex_id,
        'visible': True
    })


def main():
    parser = argparse.ArgumentParser(
        description='Verify and fix solution and comment counts for all crackmes'
    )
    parser.add_argument('--apply', action='store_true',
                        help='Apply changes to the database (default: dry-run mode)')
    parser.add_argument('--uri', default='mongodb://localhost:27017',
                        help='MongoDB URI (default: mongodb://localhost:27017)')
    parser.add_argument('--db', default='crackmesone',
                        help='Database name (default: crackmesone)')

    args = parser.parse_args()

    print("=" * 70)
    if args.apply:
        print("MODE: APPLY - Changes WILL be written to the database")
    else:
        print("MODE: DRY-RUN - Only showing differences, no changes will be made")
        print("      Use --apply flag to actually update the database")
    print("=" * 70)
    print()

    # Connect to MongoDB
    try:
        client = MongoClient(args.uri, serverSelectionTimeoutMS=5000)
        client.server_info()  # Trigger connection
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    db = client[args.db]
    crackme_collection = db['crackme']
    solutions_collection = db['solution']
    comments_collection = db['comment']

    # Find all crackmes
    crackmes = list(crackme_collection.find({}))
    print(f"Found {len(crackmes)} crackmes to process\n")

    updated_count = 0
    total_solutions = 0
    total_comments = 0

    for i, crackme in enumerate(crackmes, 1):
        hexid = crackme.get('hexid', '')
        name = crackme.get('name', 'Unknown')
        object_id = crackme.get('_id')

        current_nb_solutions = crackme.get('nbsolutions', 0)
        current_nb_comments = crackme.get('nbcomments', 0)

        # Count actual solutions and comments
        actual_solutions = count_solutions_for_crackme(solutions_collection, object_id)
        actual_comments = count_comments_for_crackme(comments_collection, hexid)

        total_solutions += actual_solutions
        total_comments += actual_comments

        # Check if update is needed
        needs_update = (
            current_nb_solutions != actual_solutions or
            current_nb_comments != actual_comments
        )

        if needs_update:
            updated_count += 1
            print(f"[{i}] Crackme: {name} ({hexid})")

            if current_nb_solutions != actual_solutions:
                print(f"  ❌ Solutions mismatch:")
                print(f"     Current (stored): {current_nb_solutions}")
                print(f"     Actual (counted): {actual_solutions}")
                diff = int(actual_solutions - current_nb_solutions)
                print(f"     Difference: {diff:+d}")

            if current_nb_comments != actual_comments:
                print(f"  ❌ Comments mismatch:")
                print(f"     Current (stored): {current_nb_comments}")
                print(f"     Actual (counted): {actual_comments}")
                diff = int(actual_comments - current_nb_comments)
                print(f"     Difference: {diff:+d}")

            if args.apply:
                try:
                    crackme_collection.update_one(
                        {'_id': object_id},
                        {'$set': {
                            'nbsolutions': int(actual_solutions),
                            'nbcomments': int(actual_comments)
                        }}
                    )
                    print(f"  ✅ Database updated successfully")
                except Exception as e:
                    print(f"  ❌ Database update failed: {e}")
            else:
                print(f"  ⚠️  Would update (use --apply to fix)")

            print()

    # Print summary
    print("=" * 70)
    print("SUMMARY:")
    print("=" * 70)
    print(f"Total crackmes processed:     {len(crackmes)}")
    print(f"Crackmes with mismatches:     {updated_count}")
    print(f"Crackmes already correct:     {len(crackmes) - updated_count}")
    print()
    print(f"Total solutions (actual):     {total_solutions}")
    print(f"Total comments (actual):      {total_comments}")
    print()

    if updated_count == 0:
        print("✅ All counts are already correct - no changes needed!")
    elif args.apply:
        print("✅ All mismatches have been fixed in the database")
    else:
        print(f"⚠️  Found {updated_count} crackme(s) with incorrect counts")
        print(f"   Run with --apply flag to fix them:")
        print(f"   python {sys.argv[0]} --apply")

    print("=" * 70)

    # Exit with error code if there are mismatches in dry-run mode
    if updated_count > 0 and not args.apply:
        sys.exit(1)


if __name__ == '__main__':
    main()
