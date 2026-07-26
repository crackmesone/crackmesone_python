#!/usr/bin/env python3
"""
Sync obfuscation labels from the crackmes-RE dataset into the database.

Runs two phases, in order:

  1. Vocabulary  -> rebuild the ``label_vocabulary`` document (the valid classes,
     sub-labels, and qualification rules) so the site knows what labels exist.
  2. Crackme labels -> set each crackme's ``labels`` to the dataset-derived set,
     validated against that vocabulary.

The phases must run in this order -- crackme labels are validated against the
vocabulary, so re-labeling with a stale vocabulary would silently drop any newly
added labels. Keeping them in one command makes that ordering automatic.

Usage:
    cd /path/to/crackmesone_python/script
    python sync_labels.py --dataset /path/to/crackmes_dataset.jsonl            # dry run (both phases)
    python sync_labels.py --dataset /path/to/crackmes_dataset.jsonl --apply    # write both

    --vocab-only     Only rebuild the vocabulary document
    --labels-only      Only re-label crackmes (using the vocabulary already in the DB)
    --seed-default   Vocabulary phase writes the built-in default vocabulary
                     instead of deriving it from the dataset

After applying, restart the app workers so they pick up the new vocabulary.
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient

from app.services.labels import (
    Vocabulary, default_vocabulary_doc, get_vocabulary, reload_vocabulary,
    VOCAB_COLLECTION, VOCAB_ID, DATASET_URL,
    DEFAULT_FIELD_PARENTS, DEFAULT_QUALIFY_SUFFIX,
)


# ---------------------------------------------------------------------------
# Phase 1: build the vocabulary document from the dataset
# ---------------------------------------------------------------------------

def build_vocabulary_from_dataset(dataset_path):
    """Derive a vocabulary document (classes + sub-labels) from a JSONL dataset."""
    field_parents = dict(DEFAULT_FIELD_PARENTS)
    qualify_suffix = dict(DEFAULT_QUALIFY_SUFFIX)

    class_counts = Counter()
    field_value_counts = {f: Counter() for f in field_parents}
    value_fields = defaultdict(set)  # raw value -> set of fields it appears in

    for record in _iter_records(dataset_path):
        for c in (record.get("obfuscation_classes") or []):
            class_counts[c] += 1
        for field in field_parents:
            for v in (record.get(field) or []):
                field_value_counts[field][v] += 1
                value_fields[v].add(field)

    # Values that appear under more than one field must be qualified per source.
    qualify_values = sorted(v for v, fields in value_fields.items() if len(fields) > 1)
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

    classes = [c for c, _ in class_counts.most_common()]

    sublabels = defaultdict(list)
    for field, parent in field_parents.items():
        for value, _ in field_value_counts[field].most_common():
            label = canonical(field, value)
            if label not in sublabels[parent]:
                sublabels[parent].append(label)

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


# ---------------------------------------------------------------------------
# Phase 2: derive each crackme's labels from the dataset
# ---------------------------------------------------------------------------

def labels_from_dataset(dataset_path, voc):
    """Return ``{hexid: [normalized labels]}`` using the given vocabulary."""
    mapping = {}
    for record in _iter_records(dataset_path):
        hexid = record.get("hexid")
        if not hexid:
            continue
        raw = list(record.get("obfuscation_classes") or [])
        for field in voc.field_parents:
            for value in (record.get(field) or []):
                raw.append(voc.sublabel_label(field, value))
        mapping[hexid] = voc.normalize(raw)
    return mapping


def _iter_records(dataset_path):
    with open(dataset_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  Skipping malformed line: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _db(config_dir):
    with open(os.path.join(config_dir, "config", "config.json")) as f:
        config = json.load(f)
    mongo_url = config["Database"].get("URL", "mongodb://127.0.0.1:27017")
    db_name = config["Database"].get("Name", "crackmesone")
    return MongoClient(mongo_url)[db_name], db_name


def main():
    parser = argparse.ArgumentParser(description="Sync label vocabulary + crackme labels from the dataset")
    parser.add_argument("--dataset", help="Path to crackmes_dataset.jsonl")
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    parser.add_argument("--vocab-only", action="store_true", help="Only rebuild the vocabulary")
    parser.add_argument("--labels-only", action="store_true", help="Only re-label crackmes")
    parser.add_argument("--seed-default", action="store_true",
                        help="Vocabulary phase writes the built-in default instead of deriving it")
    args = parser.parse_args()

    if args.vocab_only and args.labels_only:
        print("Error: --vocab-only and --labels-only are mutually exclusive")
        return 2

    do_vocab = not args.labels_only
    do_labels = not args.vocab_only
    needs_dataset = do_labels or (do_vocab and not args.seed_default)
    if needs_dataset:
        if not args.dataset:
            print("Error: --dataset <path> is required")
            return 2
        if not os.path.exists(args.dataset):
            print(f"Error: dataset file not found: {args.dataset}")
            return 1

    dry_run = not args.apply
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db, db_name = _db(base_dir)
    print(f"Connected to MongoDB: {db_name}")
    if dry_run:
        print("[DRY RUN - no changes written; re-run with --apply]\n")

    # ---- Phase 1: vocabulary ----
    if do_vocab:
        print("== Phase 1: vocabulary ==")
        if args.seed_default:
            vocab_doc = default_vocabulary_doc()
        else:
            vocab_doc = build_vocabulary_from_dataset(args.dataset)
        print(f"  {len(vocab_doc['classes'])} classes, "
              f"{sum(len(v) for v in vocab_doc['sublabels'].values())} sub-labels, "
              f"qualified values: {vocab_doc['qualify_values']}")
        if not dry_run:
            doc = dict(vocab_doc, _id=VOCAB_ID)
            db[VOCAB_COLLECTION].replace_one({"_id": VOCAB_ID}, doc, upsert=True)
            reload_vocabulary()
            print(f"  wrote {db_name}.{VOCAB_COLLECTION} (_id={VOCAB_ID})")
        voc = Vocabulary(vocab_doc)
    else:
        reload_vocabulary()
        voc = get_vocabulary()
        print("== Phase 1: skipped (--labels-only); using vocabulary already in the DB ==")

    # ---- Phase 2: crackme labels ----
    if do_labels:
        print("\n== Phase 2: crackme labels ==")
        mapping = labels_from_dataset(args.dataset, voc)
        crackme = db["crackme"]

        # Authoritative: clear everyone, then set labels for dataset crackmes.
        if not dry_run:
            crackme.update_many({}, {"$set": {"labels": []}})

        labeled = not_in_db = no_labels = 0
        for hexid, labels in mapping.items():
            if not labels:
                no_labels += 1
                continue
            if not crackme.find_one({"hexid": hexid}, {"_id": 1}):
                not_in_db += 1
                continue
            if not dry_run:
                crackme.update_one({"hexid": hexid}, {"$set": {"labels": labels}})
            labeled += 1

        print(f"  dataset records: {len(mapping)}")
        print(f"  {'would label' if dry_run else 'labeled'} crackmes: {labeled}")
        print(f"  dataset records with no valid labels: {no_labels}")
        print(f"  dataset records not in DB: {not_in_db}")
    else:
        print("\n== Phase 2: skipped (--vocab-only) ==")

    if dry_run:
        print("\nRe-run with --apply to write these changes.")
    else:
        print("\nDone. Restart the app workers to pick up the new vocabulary.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
