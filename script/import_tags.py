#!/usr/bin/env python3
"""
Import obfuscation tags from the crackmes-RE dataset into the database.

The dataset (https://github.com/crackmesone/crackmes-re-dataset) ships one JSONL
record per crackme, keyed by `hexid`. Each record has an `obfuscation_classes`
list of high-level tags plus finer sub-label lists (antidebug_methods, packers,
controlflow_methods), all produced by an AI reading public solutions and
comments. This script joins those records to crackme documents by hexid and
writes the combined, normalized tags (classes + sub-labels) into the `tags`
field.

Only tags in the controlled vocabulary (app/services/tags.py) are kept, so the
site and the dataset never drift apart.

Usage:
    cd /path/to/crackmesone_python/script
    python import_tags.py --dataset /path/to/crackmes_dataset.jsonl            # Dry run
    python import_tags.py --dataset /path/to/crackmes_dataset.jsonl --apply    # Apply

    --overwrite   Replace existing tags even if a crackme already has some
                  (default: skip crackmes that already have a non-empty tags list)
"""

import argparse
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient

from app.services.tags import normalize_tags, SUBLABEL_FIELDS


def load_dataset_tags(dataset_path):
    """Return {hexid: [normalized tags]} from a dataset JSONL file.

    Combines the high-level ``obfuscation_classes`` with the sub-label fields
    (antidebug_methods, packers, controlflow_methods) into a single tag list.
    """
    mapping = {}
    with open(dataset_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  Skipping malformed line: {e}")
                continue
            hexid = record.get("hexid")
            if not hexid:
                continue
            raw = list(record.get("obfuscation_classes", []) or [])
            for field in SUBLABEL_FIELDS:
                raw.extend(record.get(field, []) or [])
            mapping[hexid] = normalize_tags(raw)
    return mapping


def main():
    parser = argparse.ArgumentParser(description="Import obfuscation tags from the crackmes-RE dataset")
    parser.add_argument("--dataset", required=True, help="Path to crackmes_dataset.jsonl")
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace tags even on crackmes that already have some")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"Error: dataset file not found: {args.dataset}")
        return 1

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "config.json"
    )
    with open(config_path, "r") as f:
        config = json.load(f)

    mongo_url = config["Database"].get("URL", "mongodb://127.0.0.1:27017")
    db_name = config["Database"].get("Name", "crackmesone")
    client = MongoClient(mongo_url)
    collection = client[db_name]["crackme"]
    print(f"Connected to MongoDB: {db_name}")

    dry_run = not args.apply
    if dry_run:
        print("\n[DRY RUN MODE - No changes will be made; use --apply to write]\n")

    print(f"Loading dataset from {args.dataset} ...")
    dataset_tags = load_dataset_tags(args.dataset)
    print(f"Loaded tags for {len(dataset_tags)} dataset records\n")

    updated = 0
    skipped_existing = 0
    skipped_no_tags = 0
    not_in_db = 0

    for hexid, tags in dataset_tags.items():
        crackme = collection.find_one({"hexid": hexid}, {"tags": 1})
        if not crackme:
            not_in_db += 1
            continue

        if not tags:
            skipped_no_tags += 1
            continue

        existing = crackme.get("tags") or []
        if existing and not args.overwrite:
            skipped_existing += 1
            continue

        if sorted(existing) == sorted(tags):
            continue

        if dry_run:
            print(f"  {hexid}: {existing} -> {tags}")
        else:
            collection.update_one({"hexid": hexid}, {"$set": {"tags": tags}})
        updated += 1

    print(f"\n{'=' * 70}")
    print("Summary:")
    print(f"  {'Would update' if dry_run else 'Updated'}: {updated}")
    print(f"  Skipped (already tagged, no --overwrite): {skipped_existing}")
    print(f"  Skipped (dataset had no valid tags): {skipped_no_tags}")
    print(f"  Dataset records not in DB: {not_in_db}")
    print(f"{'=' * 70}")

    if dry_run and updated > 0:
        print("\nRun with --apply to actually update the database")
    return 0


if __name__ == "__main__":
    sys.exit(main())
