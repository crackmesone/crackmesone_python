#!/usr/bin/env python3
"""
Verify and fix incorrect difficulty/quality ratings in the database.

This script:
1. Checks all crackmes for incorrect rating calculations
2. Identifies crackmes with NaN values
3. Identifies crackmes with no ratings (potential divide by zero)
4. Can fix incorrect values when run with --apply flag

Usage:
    python verify_ratings.py                    # Dry-run mode (shows issues)
    python verify_ratings.py --apply            # Apply fixes to database
    python verify_ratings.py --uri mongodb://host:port --db dbname
"""

import argparse
import math
import sys
from pymongo import MongoClient


def calculate_average(ratings):
    """Calculate average rating, returning 0.0 if no ratings."""
    if not ratings:
        return 0.0
    return sum(r['rating'] for r in ratings) / len(ratings)


def main():
    parser = argparse.ArgumentParser(description='Verify and fix crackme ratings')
    parser.add_argument('--apply', action='store_true',
                        help='Apply changes to the database (default: dry-run mode)')
    parser.add_argument('--uri', default='mongodb://localhost:27017',
                        help='MongoDB URI (default: mongodb://localhost:27017)')
    parser.add_argument('--db', default='crackmesone',
                        help='Database name (default: crackmesone)')

    args = parser.parse_args()

    if args.apply:
        print("Running in APPLY mode - changes will be written to the database")
    else:
        print("Running in DRY-RUN mode - no changes will be made")
        print("Use --apply flag to apply changes")
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
    difficulty_collection = db['rating_difficulty']
    quality_collection = db['rating_quality']

    # Find all crackmes
    crackmes = list(crackme_collection.find({}))
    print(f"Found {len(crackmes)} crackmes to verify\n")

    incorrect_count = 0
    no_difficulty_ratings_count = 0
    no_quality_ratings_count = 0
    nan_count = 0

    for i, crackme in enumerate(crackmes, 1):
        has_issue = False
        hexid = crackme.get('hexid', '')
        name = crackme.get('name', 'Unknown')
        stored_difficulty = crackme.get('difficulty', 0.0)
        stored_quality = crackme.get('quality', 0.0)

        # Fetch difficulty ratings
        difficulty_ratings = list(difficulty_collection.find({'crackmehexid': hexid}))
        expected_difficulty = calculate_average(difficulty_ratings)

        # Fetch quality ratings
        quality_ratings = list(quality_collection.find({'crackmehexid': hexid}))
        expected_quality = calculate_average(quality_ratings)

        # Check for NaN values
        difficulty_is_nan = math.isnan(stored_difficulty) if isinstance(stored_difficulty, float) else False
        quality_is_nan = math.isnan(stored_quality) if isinstance(stored_quality, float) else False

        if difficulty_is_nan or quality_is_nan:
            if not has_issue:
                print(f"[{i}] Crackme: {name} ({hexid})")
                has_issue = True
                nan_count += 1
            if difficulty_is_nan:
                print(f"  ⚠️  Difficulty is NaN (ratings: {len(difficulty_ratings)})")
            if quality_is_nan:
                print(f"  ⚠️  Quality is NaN (ratings: {len(quality_ratings)})")

        # Check if difficulty needs updating (allow small floating point differences)
        difficulty_diff = abs(stored_difficulty - expected_difficulty) if not difficulty_is_nan else float('inf')
        if difficulty_diff > 0.001:
            if not has_issue:
                print(f"[{i}] Crackme: {name} ({hexid})")
                has_issue = True
            print(f"  ❌ Difficulty mismatch: stored={stored_difficulty:.2f}, "
                  f"expected={expected_difficulty:.2f} (diff={difficulty_diff:.4f}, "
                  f"ratings={len(difficulty_ratings)})")

        # Check if quality needs updating
        quality_diff = abs(stored_quality - expected_quality) if not quality_is_nan else float('inf')
        if quality_diff > 0.001:
            if not has_issue:
                print(f"[{i}] Crackme: {name} ({hexid})")
                has_issue = True
            print(f"  ❌ Quality mismatch: stored={stored_quality:.2f}, "
                  f"expected={expected_quality:.2f} (diff={quality_diff:.4f}, "
                  f"ratings={len(quality_ratings)})")

        # Check for missing ratings (potential divide by zero)
        if len(difficulty_ratings) == 0:
            if not has_issue:
                print(f"[{i}] Crackme: {name} ({hexid})")
                has_issue = True
            print(f"  ⚠️  No difficulty ratings found (stored value: {stored_difficulty:.2f})")
            no_difficulty_ratings_count += 1

        if len(quality_ratings) == 0:
            if not has_issue:
                print(f"[{i}] Crackme: {name} ({hexid})")
                has_issue = True
            print(f"  ⚠️  No quality ratings found (stored value: {stored_quality:.2f})")
            no_quality_ratings_count += 1

        # Apply fixes if requested
        if has_issue and args.apply:
            update = {}
            if difficulty_diff > 0.001 or difficulty_is_nan:
                update['difficulty'] = expected_difficulty
                print(f"  ✅ Updated difficulty to {expected_difficulty:.2f}")
            if quality_diff > 0.001 or quality_is_nan:
                update['quality'] = expected_quality
                print(f"  ✅ Updated quality to {expected_quality:.2f}")

            if update:
                try:
                    crackme_collection.update_one(
                        {'hexid': hexid},
                        {'$set': update}
                    )
                except Exception as e:
                    print(f"  ❌ Failed to update: {e}")

        if has_issue:
            incorrect_count += 1
            print()

    # Print summary
    print("=" * 60)
    print("Summary:")
    print(f"  Total crackmes: {len(crackmes)}")
    print(f"  Crackmes with incorrect ratings: {incorrect_count}")
    print(f"  Crackmes with NaN values: {nan_count}")
    print(f"  Crackmes with no difficulty ratings: {no_difficulty_ratings_count}")
    print(f"  Crackmes with no quality ratings: {no_quality_ratings_count}")

    if not args.apply and incorrect_count > 0:
        print("\nTo apply these changes, run with --apply flag")
    elif args.apply and incorrect_count > 0:
        print("\n✅ Changes have been applied to the database")

    if incorrect_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
