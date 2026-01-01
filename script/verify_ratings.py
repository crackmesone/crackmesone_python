#!/usr/bin/env python3
"""
Verify and fix incorrect difficulty/quality ratings in the database.

This script:
1. Checks all crackmes for incorrect rating calculations
2. Identifies crackmes with NaN values
3. Identifies crackmes with no ratings and injects default ratings from author
4. Scales rating values outside 1-6 range down to that range
5. Can fix incorrect values when run with --apply flag

Usage:
    python verify_ratings.py                    # Dry-run mode (shows issues)
    python verify_ratings.py --apply            # Apply fixes to database
    python verify_ratings.py --uri mongodb://host:port --db dbname
"""

import argparse
import math
import sys
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient


def scale_to_range(value, old_max=9, new_min=1, new_max=6):
    """Scale a value from 1-9 to 1-6 range and round to integer."""
    if value <= 0:
        return new_min
    if value <= new_max:
        return round(value)
    # Linear mapping from 1-9 to 1-6
    scaled = new_min + (value - 1) * (new_max - new_min) / (old_max - 1)
    return round(min(max(scaled, new_min), new_max))


def calculate_average(ratings):
    """Calculate average rating, returning 0.0 if no ratings."""
    if not ratings:
        return 0.0
    return sum(r['rating'] for r in ratings) / len(ratings)


def create_rating(collection, username, crackme_hexid, rating):
    """Create a rating document."""
    obj_id = ObjectId()
    rating_doc = {
        '_id': obj_id,
        'rating': rating,
        'author': username,
        'crackmehexid': crackme_hexid,
        'created_at': datetime.utcnow(),
        'visible': True,
        'deleted': False
    }
    collection.insert_one(rating_doc)
    return rating_doc


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
    out_of_range_ratings_count = 0
    injected_difficulty_count = 0
    injected_quality_count = 0

    # First pass: fix any ratings that are out of range (> 6)
    print("Checking for out-of-range ratings...")
    high_diff_ratings = list(difficulty_collection.find({'rating': {'$gt': 6}}))
    high_qual_ratings = list(quality_collection.find({'rating': {'$gt': 6}}))

    if high_diff_ratings or high_qual_ratings:
        out_of_range_ratings_count = len(high_diff_ratings) + len(high_qual_ratings)
        print(f"  Found {len(high_diff_ratings)} difficulty ratings > 6")
        print(f"  Found {len(high_qual_ratings)} quality ratings > 6")

        if args.apply:
            for r in high_diff_ratings:
                old_val = r.get('rating')
                new_val = scale_to_range(old_val)
                difficulty_collection.update_one(
                    {'_id': r['_id']},
                    {'$set': {'rating': new_val}}
                )
                print(f"  ✅ Scaled difficulty rating {old_val} -> {new_val}")

            for r in high_qual_ratings:
                old_val = r.get('rating')
                new_val = scale_to_range(old_val)
                quality_collection.update_one(
                    {'_id': r['_id']},
                    {'$set': {'rating': new_val}}
                )
                print(f"  ✅ Scaled quality rating {old_val} -> {new_val}")
    else:
        print("  No out-of-range ratings found")
    print()

    for i, crackme in enumerate(crackmes, 1):
        has_issue = False
        hexid = crackme.get('hexid', '')
        name = crackme.get('name', 'Unknown')
        author = crackme.get('author', 'unknown')
        stored_difficulty = crackme.get('difficulty', 0.0)
        stored_quality = crackme.get('quality', 0.0)

        # Fetch difficulty ratings
        difficulty_ratings = list(difficulty_collection.find({'crackmehexid': hexid}))

        # Fetch quality ratings
        quality_ratings = list(quality_collection.find({'crackmehexid': hexid}))

        # Check for missing ratings and inject if needed
        if len(difficulty_ratings) == 0:
            if not has_issue:
                print(f"[{i}] Crackme: {name} ({hexid})")
                has_issue = True
            no_difficulty_ratings_count += 1

            # Scale the stored value to 1-6 range
            injected_value = scale_to_range(stored_difficulty)
            print(f"  ⚠️  No difficulty ratings found (stored: {stored_difficulty:.2f}, will inject: {injected_value})")

            if args.apply:
                create_rating(difficulty_collection, author, hexid, injected_value)
                print(f"  ✅ Injected difficulty rating {injected_value} from author '{author}'")
                injected_difficulty_count += 1
                # Refresh ratings list after injection
                difficulty_ratings = list(difficulty_collection.find({'crackmehexid': hexid}))

        if len(quality_ratings) == 0:
            if not has_issue:
                print(f"[{i}] Crackme: {name} ({hexid})")
                has_issue = True
            no_quality_ratings_count += 1

            # Scale the stored value to 1-6 range
            injected_value = scale_to_range(stored_quality)
            print(f"  ⚠️  No quality ratings found (stored: {stored_quality:.2f}, will inject: {injected_value})")

            if args.apply:
                create_rating(quality_collection, author, hexid, injected_value)
                print(f"  ✅ Injected quality rating {injected_value} from author '{author}'")
                injected_quality_count += 1
                # Refresh ratings list after injection
                quality_ratings = list(quality_collection.find({'crackmehexid': hexid}))

        # Calculate expected values from ratings
        expected_difficulty = calculate_average(difficulty_ratings)
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
    print(f"  Crackmes with issues: {incorrect_count}")
    print(f"  Crackmes with NaN values: {nan_count}")
    print(f"  Crackmes with no difficulty ratings: {no_difficulty_ratings_count}")
    print(f"  Crackmes with no quality ratings: {no_quality_ratings_count}")
    print(f"  Out-of-range ratings (> 6): {out_of_range_ratings_count}")

    if args.apply:
        print(f"\nApplied fixes:")
        print(f"  Injected difficulty ratings: {injected_difficulty_count}")
        print(f"  Injected quality ratings: {injected_quality_count}")
        print(f"  Scaled out-of-range ratings: {out_of_range_ratings_count}")

    total_issues = incorrect_count + out_of_range_ratings_count
    if not args.apply and total_issues > 0:
        print("\nTo apply these changes, run with --apply flag")
    elif args.apply and total_issues > 0:
        print("\n✅ Changes have been applied to the database")

    if total_issues > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
