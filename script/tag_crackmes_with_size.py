#!/usr/bin/env python3
"""
Calculate and add uncompressed archive sizes to crackmes.

This script:
1. Finds all crackmes without a 'size' field (or with size=0)
2. Calculates the uncompressed size from the archive files
3. Updates the database with the calculated sizes

Usage:
    cd /path/to/crackmesone_python/script
    python tag_crackmes_with_size.py          # Dry run (default)
    python tag_crackmes_with_size.py --apply  # Actually apply changes
"""

import json
import sys
import os
import zipfile
import io

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient


def get_uncompressed_size(zip_path):
    """Calculate the total uncompressed size of a crackme archive.

    The outer zip is always password-protected with 'crackmes.one'.
    Inside, there can be:
    1. Another zip file (no password) - return sum of files within it
    2. A raw file - return its uncompressed size

    Returns total uncompressed size in bytes, or None on error.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as outer_zip:
            total_size = 0
            for info in outer_zip.infolist():
                try:
                    # Extract file data from outer zip using password
                    size = _calculate_archive_size(outer_zip.read(info.filename, pwd=b"crackmes.one"))
                    if size is None: return None
                    total_size += size
                except Exception as e:
                    print(f"    Error reading {zip_path}/{info.filename}: {e}")
                    return None
            return total_size
    except Exception as e:
        print(f"    Error reading {zip_path}: {e}")
        return None


def get_uncompressed_size_from_raw(file_path):
    """Calculate the total uncompressed size from a raw archive file (no outer encryption).

    For unapproved crackmes, the file is the raw upload without password protection.
    Inside, there can be:
    1. A zip file - return sum of files within it
    2. A raw file - return its uncompressed size

    Returns total uncompressed size in bytes, or None on error.
    """
    try:
        file_data = open(file_path, "rb").read()
        return _calculate_archive_size(file_data)
    except Exception as e:
        print(f"    Error reading {file_path}: {e}")
        return None


def _calculate_archive_size(file_data):
    try:
        with zipfile.ZipFile(io.BytesIO(file_data), "r") as zip_obj:
            return sum(info.file_size for info in zip_obj.infolist())
    except zipfile.BadZipFile:
        return len(file_data)
    except Exception:
        return None


def find_crackme_file(static_dir, hexid):
    """Trys to find the crackme zip file for a given hexid."""
    static_path = os.path.join(static_dir, f"{hexid}.zip")
    if os.path.exists(static_path):
        return static_path
    return None


def find_unapproved_crackme_file(tmp_dir, author, hexid):
    """Find an unapproved crackme file in tmp/crackme directory.

    Unapproved crackmes are stored with naming pattern: author+++hexid+++filename
    This function finds the file matching the author and hexid prefix.

    Returns the full path if found, None otherwise.
    """
    if not os.path.exists(tmp_dir): return None

    try:
        prefix = f"{author}+++{hexid}+++"
        for filename in os.listdir(tmp_dir):
            if filename.startswith(prefix):
                return os.path.join(tmp_dir, filename)
    except Exception as e:
        print(f"    Error scanning tmp directory for {author}/{hexid}: {e}")
    return None


def format_size(size_bytes):
    """Format bytes to human-readable format."""
    if size_bytes > 2**30:
        return f"{size_bytes / 2**30:.2f} GB"
    elif size_bytes > 2**20:
        return f"{size_bytes / 2**20:.2f} MB"
    elif size_bytes > 2**10:
        return f"{size_bytes / 2**10:.2f} KB"
    else:
        return f"{size_bytes} B"


def main():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"config","config.json"), "r") as f:
        config = json.load(f)

    # Connect to MongoDB
    mongo_url = config["Database"].get("URL", "mongodb://127.0.0.1:27017")
    db_name = config["Database"].get("Name", "crackmesone")

    client = MongoClient(mongo_url)
    db = client[db_name]
    collection = db["crackme"]

    print(f"Connected to MongoDB: {db_name}")

    dry_run = "--apply" not in sys.argv
    if dry_run:
        print("\n[DRY RUN MODE - No changes will be made]")
        print("[Use --apply to actually apply changes]\n")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "static", "crackme")
    tmp_dir = os.path.join(base_dir, "tmp", "crackme")

    if not os.path.exists(static_dir):
        print(f"Error: Static crackme directory not found at {static_dir}")
        return

    # Fetch both approved and unapproved crackmes without size
    print("Fetching crackmes without size (both approved and unapproved)...")
    crackmes = list(
        collection.find({"$or": [{"size": {"$exists": False}}, {"size": 0}]})
    )

    if not crackmes:
        print("All crackmes already have sizes!")
        return

    print(f"Found {len(crackmes)} crackmes without size\n")

    updated = 0
    not_found = 0
    errors = 0

    for crackme in crackmes:
        hexid = crackme.get("hexid")
        is_visible = crackme.get("visible", False)

        # Determine location and size calculation method
        if is_visible:
            # Approved crackme - look in static/crackme/
            location = "approved"
            fn = get_uncompressed_size
            file_path = find_crackme_file(static_dir, hexid)
        else:
            # Unapproved crackme - look in tmp/crackme/
            location = "unapproved"
            fn = get_uncompressed_size_from_raw
            file_path = find_unapproved_crackme_file(
                tmp_dir, crackme.get("author", ""), hexid
            )

        if file_path is None:
            print(f"  {hexid} ({location}): File not found")
            not_found += 1
            continue

        size = fn(file_path)
        if size is None:
            errors += 1
            continue

        size_str = format_size(size)
        if dry_run:
            print(f"  {hexid} ({location}): Would set size to {size} bytes ({size_str})")
        else:
            collection.update_one({"hexid": hexid}, {"$set": {"size": size}})
            print(f"  {hexid} ({location}): Updated size to {size} bytes ({size_str})")

        updated += 1

    print(f"\n{'=' * 70}")
    print(f"Summary:")
    print(f"  Updated: {updated}")
    print(f"  Not found: {not_found}")
    print(f"  Errors: {errors}")
    print(f"{'=' * 70}")

    if dry_run and updated > 0:
        print("\nRun with --apply flag to actually update the database")


if __name__ == "__main__":
    main()