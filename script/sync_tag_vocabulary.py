#!/usr/bin/env python3
"""
Sync the tag vocabulary (obfuscation classes + sub-labels) into the database.

The site reads its controlled tag vocabulary from the ``tag_vocabulary``
MongoDB collection (a single document, ``_id = "current"``) so it can be
updated without code changes. This script (re)builds that document from the
crackmes-RE dataset:

- classes         = distinct ``obfuscation_classes`` values, ordered by frequency
- sub-labels      = distinct values of each sub-label field, ordered by frequency
                    and grouped under the parent class the field maps to
- shared values   = values that appear under more than one field (e.g. AES, which
                    is in both crypto_methods and encryption_methods) are
                    qualified with the source context ("AES (crypto)" /
                    "AES (encryption)") so each tag has exactly one parent

The dataset->parent field mapping and the qualification suffixes come from the
built-in defaults in ``app/services/tags.py`` (stable dataset-schema config).

Usage:
    cd /path/to/crackmesone_python/script
    python sync_tag_vocabulary.py --dataset /path/to/crackmes_dataset.jsonl          # dry run
    python sync_tag_vocabulary.py --dataset /path/to/crackmes_dataset.jsonl --apply   # write
    python sync_tag_vocabulary.py --seed-default --apply                              # write built-in default

After syncing the vocabulary, run ``import_tags.py`` to (re)apply crackme tags.
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient

from app.services.tags import (
    VOCAB_COLLECTION, VOCAB_ID, DATASET_URL,
    DEFAULT_FIELD_PARENTS, DEFAULT_QUALIFY_SUFFIX,
    default_vocabulary_doc,
)


def build_vocabulary_from_dataset(dataset_path):
    """Derive a vocabulary document from a dataset JSONL file."""
    field_parents = dict(DEFAULT_FIELD_PARENTS)
    qualify_suffix = dict(DEFAULT_QUALIFY_SUFFIX)

    class_counts = Counter()
    field_value_counts = {f: Counter() for f in field_parents}
    value_fields = defaultdict(set)  # raw value -> set of fields it appears in

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
            for c in (record.get("obfuscation_classes") or []):
                class_counts[c] += 1
            for field in field_parents:
                for v in (record.get(field) or []):
                    field_value_counts[field][v] += 1
                    value_fields[v].add(field)

    # Values that appear under more than one field must be qualified.
    qualify_values = sorted(v for v, fields in value_fields.items() if len(fields) > 1)

    # Warn if a shared value lives in a field without a qualification suffix
    # (that would collide once qualified only on one side).
    for v in qualify_values:
        for field in value_fields[v]:
            if field not in qualify_suffix:
                print(f"  WARNING: shared value {v!r} in field {field!r} has no "
                      f"qualify suffix; it may collide across parents.")

    def canonical(field, value):
        suffix = qualify_suffix.get(field)
        if suffix and value in qualify_values:
            return "{} ({})".format(value, suffix)
        return value

    # Classes ordered by frequency (desc).
    classes = [c for c, _ in class_counts.most_common()]

    # Sub-labels grouped under their parent class, ordered by frequency.
    sublabels = defaultdict(list)
    for field, parent in field_parents.items():
        for value, _ in field_value_counts[field].most_common():
            tag = canonical(field, value)
            if tag not in sublabels[parent]:
                sublabels[parent].append(tag)

    # Any parent that has sub-labels but somehow isn't in the class list gets
    # appended, so every sub-label has a home (should not happen once the
    # dataset satisfies "sub-label implies parent class").
    for parent in sublabels:
        if parent not in classes:
            print(f"  NOTE: parent class {parent!r} has sub-labels but no "
                  f"obfuscation_classes occurrences; appending it.")
            classes.append(parent)

    return {
        "classes": classes,
        "sublabels": {k: v for k, v in sublabels.items()},
        "field_parents": field_parents,
        "qualify_suffix": qualify_suffix,
        "qualify_values": qualify_values,
        "dataset_url": DATASET_URL,
    }


def main():
    parser = argparse.ArgumentParser(description="Sync the tag vocabulary into the DB")
    parser.add_argument("--dataset", help="Path to crackmes_dataset.jsonl")
    parser.add_argument("--seed-default", action="store_true",
                        help="Write the built-in default vocabulary instead of deriving from a dataset")
    parser.add_argument("--apply", action="store_true", help="Actually write the document")
    args = parser.parse_args()

    if args.seed_default:
        doc = default_vocabulary_doc()
    elif args.dataset:
        if not os.path.exists(args.dataset):
            print(f"Error: dataset file not found: {args.dataset}")
            return 1
        doc = build_vocabulary_from_dataset(args.dataset)
    else:
        print("Error: pass --dataset <path> or --seed-default")
        return 2

    doc["_id"] = VOCAB_ID

    print(f"Vocabulary: {len(doc['classes'])} classes, "
          f"{sum(len(v) for v in doc['sublabels'].values())} sub-labels, "
          f"{len(doc['qualify_values'])} qualified values")
    print("  classes:", doc["classes"])
    print("  qualified values:", doc["qualify_values"])

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "config.json"
    )
    with open(config_path, "r") as f:
        config = json.load(f)
    mongo_url = config["Database"].get("URL", "mongodb://127.0.0.1:27017")
    db_name = config["Database"].get("Name", "crackmesone")
    collection = MongoClient(mongo_url)[db_name][VOCAB_COLLECTION]

    if not args.apply:
        print("\n[DRY RUN] Not written. Re-run with --apply to store this vocabulary.")
        return 0

    collection.replace_one({"_id": VOCAB_ID}, doc, upsert=True)
    print(f"\nWrote vocabulary document to {db_name}.{VOCAB_COLLECTION} (_id={VOCAB_ID})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
