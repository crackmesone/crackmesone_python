#!/usr/bin/env python3
"""
Rename the "tags" domain concept to "labels" in the database (issue #167).

The site-wide rename from *tags* to *labels* changes the persisted names too, so
existing data has to be migrated once:

  1. crackme documents:  the ``tags`` array field  ->  ``labels``
  2. collection:         ``tag_vocabulary``         ->  ``label_vocabulary``
  3. collection:         ``tag_request``            ->  ``label_request``

The migration is idempotent: rerunning it after a successful pass is a no-op
(the old field/collections are already gone). It reads the DB connection from
config/config.json, matching the other one-off scripts in this directory.

Usage:
    cd /path/to/crackmesone_python/script
    python migrate_tags_to_labels.py            # dry run (default)
    python migrate_tags_to_labels.py --apply    # actually migrate

Run it once when deploying the rename, then restart the app workers.
"""

import json
import os
import sys

from pymongo import MongoClient
from pymongo.errors import OperationFailure

# (old -> new) collection renames.
COLLECTION_RENAMES = [
    ("tag_vocabulary", "label_vocabulary"),
    ("tag_request", "label_request"),
]

# (old -> new) crackme document field rename.
FIELD_OLD = "tags"
FIELD_NEW = "labels"


def main():
    apply_changes = "--apply" in sys.argv
    dry_run = not apply_changes

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(os.path.dirname(here), "config", "config.json")) as f:
        config = json.load(f)

    mongo_url = config["Database"].get("URL", "mongodb://127.0.0.1:27017")
    db_name = config["Database"].get("Name", "crackmesone")
    client = MongoClient(mongo_url)
    db = client[db_name]

    print(f"Connected to MongoDB: {db_name}")
    print(f"Mode: {'DRY RUN (no writes)' if dry_run else 'APPLY'}\n")

    existing = set(db.list_collection_names())

    # ---- Collection renames ----
    print("== Collections ==")
    for old, new in COLLECTION_RENAMES:
        if old not in existing:
            if new in existing:
                print(f"  {old} -> {new}: already migrated (skip)")
            else:
                print(f"  {old} -> {new}: source missing, nothing to do (skip)")
            continue
        if new in existing:
            print(f"  {old} -> {new}: TARGET ALREADY EXISTS, refusing to overwrite (skip)")
            continue
        count = db[old].count_documents({})
        if dry_run:
            print(f"  {old} -> {new}: would rename ({count} documents)")
        else:
            try:
                db[old].rename(new)
                print(f"  {old} -> {new}: renamed ({count} documents)")
            except OperationFailure as e:
                print(f"  {old} -> {new}: FAILED ({e})")

    # ---- crackme.tags -> crackme.labels ----
    print("\n== crackme field rename ==")
    crackme = db["crackme"]
    to_migrate = crackme.count_documents({FIELD_OLD: {"$exists": True}})
    if to_migrate == 0:
        print(f"  {FIELD_OLD} -> {FIELD_NEW}: no documents carry '{FIELD_OLD}' (skip)")
    elif dry_run:
        print(f"  {FIELD_OLD} -> {FIELD_NEW}: would rename on {to_migrate} crackme(s)")
    else:
        result = crackme.update_many(
            {FIELD_OLD: {"$exists": True}},
            {"$rename": {FIELD_OLD: FIELD_NEW}},
        )
        print(f"  {FIELD_OLD} -> {FIELD_NEW}: renamed on {result.modified_count} crackme(s)")

    if dry_run:
        print("\nDry run only. Re-run with --apply to perform the migration.")
    else:
        print("\nDone. Restart the app workers so they pick up the new names.")


if __name__ == "__main__":
    main()
