#!/usr/bin/env python3
"""
Migration script to remove old password references from crackme descriptions.

Crackmes imported from crackmes.de often contain text like:
  "The password of the archive is 'crackmes.de'"

Since the archive passwords have been migrated to 'crackmes.one', this outdated
information should be removed from descriptions to avoid confusion.

Usage:
    python script/remove_old_password_from_descriptions.py              # Dry run (default)
    python script/remove_old_password_from_descriptions.py --execute    # Actually perform updates
"""

import argparse
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

DEFAULT_MONGODB_HOST = os.getenv("MONGODB_HOST", "127.0.0.1")
DEFAULT_MONGODB_PORT = int(os.getenv("MONGODB_PORT", "27017"))
DEFAULT_DATABASE_NAME = os.getenv("DATABASE_NAME", "crackmesone")

# Patterns to match and remove from descriptions
# These patterns match common ways the old password is mentioned
PATTERNS_TO_REMOVE = [
    # Match variations of "The password of the archive is 'crackmes.de'"
    r"[Tt]he password (?:of the archive |for the archive |)is ['\"]?crackmes\.de['\"]?\.?\s*",
    # Match "Password: crackmes.de" or "password: crackmes.de"
    r"[Pp]assword:?\s*['\"]?crackmes\.de['\"]?\.?\s*",
    # Match "archive password is crackmes.de"
    r"[Aa]rchive password (?:is )?['\"]?crackmes\.de['\"]?\.?\s*",
    # Match "zip password: crackmes.de"
    r"[Zz]ip password:?\s*['\"]?crackmes\.de['\"]?\.?\s*",
    # Match standalone "crackmes.de" that appears to be a password reference
    # (preceded by "password" on same line)
    r"(?<=password[:\s])['\"]?crackmes\.de['\"]?",
]


def find_crackmes_with_old_password(db):
    """Find all crackmes that mention 'crackmes.de' in their description."""
    return list(db.crackme.find({
        "info": {"$regex": "crackmes\\.de", "$options": "i"}
    }))


def clean_description(info: str) -> str:
    """Remove old password references from the description."""
    cleaned = info
    for pattern in PATTERNS_TO_REMOVE:
        cleaned = re.sub(pattern, "", cleaned)

    # Clean up any resulting double newlines or trailing whitespace
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    return cleaned


def main():
    parser = argparse.ArgumentParser(
        description="Remove old password references from crackme descriptions"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the updates (default is dry-run mode)"
    )
    parser.add_argument(
        "--mongodb-host",
        default=DEFAULT_MONGODB_HOST,
        help=f"MongoDB host (default: {DEFAULT_MONGODB_HOST})"
    )
    parser.add_argument(
        "--mongodb-port",
        type=int,
        default=DEFAULT_MONGODB_PORT,
        help=f"MongoDB port (default: {DEFAULT_MONGODB_PORT})"
    )
    parser.add_argument(
        "--database",
        default=DEFAULT_DATABASE_NAME,
        help=f"Database name (default: {DEFAULT_DATABASE_NAME})"
    )
    args = parser.parse_args()

    dry_run = not args.execute

    print("=" * 60)
    print("Remove Old Password References from Crackme Descriptions")
    print("=" * 60)
    if dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***\n")

    # Connect to MongoDB
    try:
        client = MongoClient(args.mongodb_host, args.mongodb_port)
        db = client[args.database]
        print(f"Connected to MongoDB at {args.mongodb_host}:{args.mongodb_port}")
        print(f"Database: {args.database}")
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        sys.exit(1)

    # Find crackmes with old password references
    crackmes = find_crackmes_with_old_password(db)
    print(f"\nFound {len(crackmes)} crackmes with 'crackmes.de' in description")

    if not crackmes:
        print("No crackmes need to be updated.")
        return 0

    updated_count = 0
    skipped_count = 0

    print("\n" + "-" * 60)
    for crackme in crackmes:
        crackme_id = crackme["_id"]
        name = crackme.get("name", "Unknown")
        author = crackme.get("author", "Unknown")
        original_info = crackme.get("info", "")

        cleaned_info = clean_description(original_info)

        if cleaned_info == original_info:
            # No changes made (the pattern didn't match our removal patterns)
            print(f"\n[SKIP] {name} by {author} (ID: {crackme_id})")
            print(f"  Contains 'crackmes.de' but not in a removable password pattern")
            skipped_count += 1
            continue

        print(f"\n[UPDATE] {name} by {author} (ID: {crackme_id})")
        print(f"  Original: {repr(original_info[:100])}...")
        print(f"  Cleaned:  {repr(cleaned_info[:100])}...")

        if not dry_run:
            try:
                db.crackme.update_one(
                    {"_id": crackme_id},
                    {"$set": {"info": cleaned_info}}
                )
                updated_count += 1
            except Exception as e:
                print(f"  Error updating: {e}")
        else:
            updated_count += 1

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total crackmes found with 'crackmes.de': {len(crackmes)}")
    print(f"Updated:  {updated_count}")
    print(f"Skipped:  {skipped_count}")

    if dry_run:
        print("\n[DRY RUN] No changes were made to the database.")
        print("Run with --execute to apply updates.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
