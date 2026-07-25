#!/usr/bin/env python3
"""
Apply Detect It Easy / `file` audit corrections to the crackme collection.

Fixes mislabeled `platform`, `arch`, and `lang` fields on existing crackmes, using
values derived from static analysis of each shipped binary:
  * platform / architecture  - from the binary header (file + DIE), verified against
    every executable in the archive.
  * language                 - from definitive structural markers (.NET CLR header,
    MSVBVM/VB, Delphi RTL, Go pclntab, PyInstaller, ...), plus:
       -  7 pure-Python crackmes            -> Python
       -  5 Go crackmes (.gopclntab)        -> Go
       - ~58 PureBasic crackmes             -> "(Visual) Basic"   (merged into Basic)
       -  5 AutoIt3 crackmes                -> "AutoIt"           (new lang value)

Reads update_website_db_corrections.json (list of {hexid, field, old, new, reason}).

Usage:
    cd /path/to/crackmesone_python/script
    python update_website_db.py            # dry run (default) - shows what would change
    python update_website_db.py --apply    # actually apply changes to MongoDB

Idempotent: a field is only written when the current DB value differs from the target,
so re-running applies nothing further. When the live value differs from the recorded
`old` (i.e. the DB drifted since the audit) the row is still corrected to `new` (which is
binary-authoritative) but the divergence is logged.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient

# values we are ever allowed to write (guards against a malformed corrections file)
VALID = {
    "platform": {"Windows", "Unix/linux etc.", "Mac OS X", "DOS", "Multiplatform", "Android", "iOS"},
    "arch":     {"x86", "x86-64", "ARM", "MIPS", "java", "other"},
    "lang":     {"C/C++", "Assembler", "(Visual) Basic", ".NET", "Borland Delphi", "Java",
                 "Rust", "Python", "Turbo Pascal", "Go", "WebAssembly", "AutoIt"},
}


def main():
    apply_changes = '--apply' in sys.argv
    dry_run = not apply_changes

    here = os.path.dirname(os.path.abspath(__file__))

    config_path = os.path.join(os.path.dirname(here), 'config', 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)

    corr_path = os.path.join(here, 'update_website_db_corrections.json')
    with open(corr_path, 'r') as f:
        corrections = json.load(f)

    # validate every target value up front
    for c in corrections:
        if c['new'] not in VALID.get(c['field'], set()):
            sys.exit(f"error: illegal target value {c!r}")

    print(f"Loaded {len(corrections)} field corrections")
    by_field = {}
    for c in corrections:
        by_field[c['field']] = by_field.get(c['field'], 0) + 1
    print(f"  by field: {by_field}")

    mongo_url = config['Database'].get('URL', 'mongodb://127.0.0.1:27017')
    db_name = config['Database'].get('Name', 'crackmesone')
    client = MongoClient(mongo_url)
    db = client[db_name]
    collection = db['crackme']
    print(f"\nConnected to MongoDB: {db_name}")

    if dry_run:
        print("\n[DRY RUN MODE - no changes will be made]")
        print("[Use --apply to actually apply changes]\n")

    updated = already = not_found = drifted = 0
    for c in corrections:
        hexid, field, new = c['hexid'], c['field'], c['new']
        doc = collection.find_one({'hexid': hexid}, {field: 1})
        if not doc:
            not_found += 1
            continue
        current = doc.get(field)
        if current == new:
            already += 1
            continue
        if current != c.get('old'):
            drifted += 1
            print(f"  NOTE {hexid} {field}: live value {current!r} != recorded {c.get('old')!r}; correcting to {new!r}")
        if dry_run:
            print(f"  would set {hexid} {field}: {current!r} -> {new!r}")
        else:
            collection.update_one({'hexid': hexid}, {'$set': {field: new}})
        updated += 1

    print(f"\nResults:")
    print(f"  {'would update' if dry_run else 'updated'}: {updated}")
    print(f"  already correct (skipped): {already}")
    print(f"  live value had drifted (still corrected): {drifted}")
    print(f"  not found in database: {not_found}")
    if dry_run:
        print("\nThis was a dry run. Use --apply to actually apply changes.")

    client.close()


if __name__ == '__main__':
    main()
