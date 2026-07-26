#!/usr/bin/env python3
"""
Additively import the DIE-detected packer labels into the database.

This is the SAFE, incremental counterpart to sync_labels.py. Where sync_labels.py is
authoritative (it clears every crackme's labels and rewrites them from the dataset,
which would wipe any label edits made on the site since the initial import), this
script only ADDS the packer labels to the specific crackmes that gained them, using
$addToSet. It never removes a label and never touches any other crackme, so manual
edits made after the initial import are preserved.

What it does:
  Phase A (vocabulary): $addToSet the packer sub-labels into the existing
    label_vocabulary document (so new names like "PE-PACK" become selectable /
    filterable). Non-destructive - only adds, existing entries untouched.
  Phase B (crackme labels): for each affected crackme, $addToSet "Packer" plus its
    specific packer name(s) into the crackme's labels array. Non-destructive.

Reads packer_labels.json  ->  {hexid: [packer sub-label names]}  (empty list = the
crackme is packed but with an unreliable/obscure packer, so only the generic
"Packer" class is added).

Usage:
    cd /path/to/crackmesone_python/script
    python import_packer_labels.py            # dry run (default)
    python import_packer_labels.py --apply    # actually write

After --apply, restart the app workers so they pick up the new vocabulary.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient

# Stable constants (kept local so this script needs only pymongo, not the full app).
VOCAB_COLLECTION = "label_vocabulary"
VOCAB_ID = "current"
PACKER_CLASS = "Packer"


def main():
    apply_changes = "--apply" in sys.argv
    dry_run = not apply_changes

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(os.path.dirname(here), "config", "config.json")) as f:
        config = json.load(f)
    with open(os.path.join(here, "packer_labels.json")) as f:
        packer_labels = json.load(f)

    mongo_url = config["Database"].get("URL", "mongodb://127.0.0.1:27017")
    db_name = config["Database"].get("Name", "crackmesone")
    client = MongoClient(mongo_url)
    db = client[db_name]
    crackme = db["crackme"]
    vocab_col = db[VOCAB_COLLECTION]

    print(f"Connected to MongoDB: {db_name}")
    print(f"Loaded {len(packer_labels)} crackmes with packer findings")
    if dry_run:
        print("\n[DRY RUN - no changes written; re-run with --apply]\n")

    # distinct sub-label names we may need in the vocabulary
    sublabels = sorted({n for names in packer_labels.values() for n in names})

    # ---- Phase A: vocabulary (additive) ----
    print("== Phase A: vocabulary ==")
    voc = vocab_col.find_one({"_id": VOCAB_ID})
    if voc is None:
        print("  WARNING: no label_vocabulary document found. The site is on the built-in")
        print("  default vocabulary. Establish a DB vocabulary first (e.g. sync_labels.py")
        print("  --vocab-only --apply), then re-run this script. Skipping vocab phase.")
    else:
        have = set(voc.get("sublabels", {}).get(PACKER_CLASS, []))
        missing = [s for s in sublabels if s not in have]
        class_missing = PACKER_CLASS not in (voc.get("classes") or [])
        print(f"  new packer sub-labels to add: {missing or 'none'}")
        if class_missing:
            print(f"  '{PACKER_CLASS}' class missing from vocabulary -> will add")
        if not dry_run and (missing or class_missing):
            update = {}
            if missing:
                update.setdefault("$addToSet", {})[f"sublabels.{PACKER_CLASS}"] = {"$each": missing}
            if class_missing:
                update.setdefault("$addToSet", {})["classes"] = PACKER_CLASS
            vocab_col.update_one({"_id": VOCAB_ID}, update)
            print("  vocabulary updated")

    # ---- Phase B: crackme labels (additive, per hexid) ----
    print("\n== Phase B: crackme labels ==")
    would = already = not_found = 0
    for hexid, names in packer_labels.items():
        add = [PACKER_CLASS] + list(names)
        doc = crackme.find_one({"hexid": hexid}, {"labels": 1})
        if not doc:
            not_found += 1
            continue
        current = set(doc.get("labels") or [])
        new = [t for t in add if t not in current]
        if not new:
            already += 1
            continue
        would += 1
        if not dry_run:
            crackme.update_one({"hexid": hexid}, {"$addToSet": {"labels": {"$each": add}}})

    print(f"  crackmes that {'would gain' if dry_run else 'gained'} packer labels: {would}")
    print(f"  already had them (skipped): {already}")
    print(f"  not found in database: {not_found}")

    if dry_run:
        print("\nThis was a dry run. Re-run with --apply to write.")
    else:
        print("\nDone. Restart the app workers to pick up the new vocabulary.")
    client.close()


if __name__ == "__main__":
    main()
