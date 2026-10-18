#!/usr/bin/env python3
"""Quarantine old review files whose database records no longer exist.

Run from the project root with the application's virtual environment:
    python script/cleanup_orphaned_pending_files.py
    python script/cleanup_orphaned_pending_files.py --apply

The default is a dry run. No database documents or published archives are
modified. Recent files are skipped because uploads write files before inserting
their database records. Pause uploads while applying a cleanup; use
--min-age-seconds 0 only with uploads paused and in-flight requests finished.
"""

import argparse
import json
from pathlib import Path
import shutil
import stat
import tempfile
import time

from bson import ObjectId
from pymongo import MongoClient


def cleanup_orphaned_files(db, root, apply=False, min_age_seconds=300):
    """Return affected relative paths and the optional quarantine directory."""
    if min_age_seconds < 0:
        raise ValueError('min_age_seconds must be non-negative')
    root = Path(root).resolve()
    cutoff = time.time() - min_age_seconds
    affected = []
    quarantine = None

    for relative_dir, collection_name in (
        ('tmp/crackme', 'crackme'),
        ('tmp/solution', 'solution'),
        ('private/crackme_source', 'crackme'),
    ):
        directory = root / relative_dir
        if not directory.exists():
            continue
        for path in sorted(directory.iterdir()):
            if not ObjectId.is_valid(path.name):
                continue
            try:
                metadata = path.lstat()
            except FileNotFoundError:
                continue
            # Never follow symlinks or process directories, including ones with
            # valid ObjectId names. Leave new/in-progress uploads alone.
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mtime > cutoff:
                continue
            # Query the configured database for each file. Connection/query
            # errors propagate; they must never be interpreted as "no record".
            if db[collection_name].find_one(
                    {'_id': ObjectId(path.name)}, {'_id': 1}) is not None:
                continue

            relative = path.relative_to(root)
            if apply:
                if quarantine is None:
                    parent = root / 'private/orphaned_submissions'
                    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    quarantine = Path(tempfile.mkdtemp(prefix='cleanup-', dir=parent))
                    print(f'Quarantine directory: {quarantine}')
                destination = quarantine / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(destination))
            affected.append(relative)
            print(f'{"Quarantined" if apply else "Would quarantine"}: {relative}')

    return affected, quarantine


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Move orphaned files out of the queue')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--config', type=Path, help='Defaults to ROOT/config/config.json')
    parser.add_argument('--min-age-seconds', type=int, default=300,
                        help='Skip newer files (default: 300 seconds)')
    args = parser.parse_args(argv)
    if args.min_age_seconds < 0:
        parser.error('--min-age-seconds must be non-negative')
    config_path = args.config or args.root / 'config/config.json'
    with config_path.open() as handle:
        config = json.load(handle)['Database']

    with MongoClient(config.get('URL', 'mongodb://127.0.0.1:27017'),
                     serverSelectionTimeoutMS=10000) as client:
        client.admin.command('ping')
        database = client[config.get('Name', 'crackmesone')]
        affected, _ = cleanup_orphaned_files(
            database, args.root, args.apply, args.min_age_seconds)
    print(f'{len(affected)} orphaned file(s) {"quarantined" if args.apply else "found"}.')
    if not args.apply:
        print('Dry run: no changes made. Use --apply to quarantine these files.')


if __name__ == '__main__':
    main()
