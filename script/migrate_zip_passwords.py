#!/usr/bin/env python3
"""
Migration script to convert zip archive passwords from crackmes.de to crackmes.one.

This script:
1. Scans static/crackme and static/solution folders for zip files
2. Tests each zip to determine if it uses 'crackmes.one' or 'crackmes.de' password
3. For files using 'crackmes.de', extracts and re-creates with 'crackmes.one' password
4. Outputs converted files to converted/crackme or converted/solution folders

Usage:
    python script/migrate_zip_passwords.py [--dry-run]
"""

import os
import sys
import subprocess
import tempfile
import shutil
import argparse
import json
from datetime import datetime
from pathlib import Path


OLD_PASSWORD = "crackmes.de"
NEW_PASSWORD = "crackmes.one"

# Paths relative to project root
STATIC_DIR = Path("static")
CRACKME_DIR = STATIC_DIR / "crackme"
SOLUTION_DIR = STATIC_DIR / "solution"
OUTPUT_DIR = Path("converted")


def is_valid_zip(zip_path: Path) -> bool:
    """Check if a file is a valid zip archive."""
    try:
        result = subprocess.run(
            ["unzip", "-t", str(zip_path)],
            capture_output=True,
            timeout=30
        )
        # Return code 0 = OK, 1 = warning but OK, 82 = no files (empty)
        # Return code 9 = not a zip file
        return result.returncode not in [9, 2, 3]
    except Exception:
        return False


def test_zip_password(zip_path: Path, password: str) -> bool:
    """Test if a zip file can be opened with the given password."""
    try:
        result = subprocess.run(
            ["unzip", "-t", "-P", password, str(zip_path)],
            capture_output=True,
            timeout=30
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"  Warning: Timeout testing {zip_path}")
        return False
    except Exception as e:
        print(f"  Error testing {zip_path}: {e}")
        return False


def get_zip_password(zip_path: Path) -> str | None:
    """Determine which password a zip file uses. Returns None if neither works."""
    if test_zip_password(zip_path, NEW_PASSWORD):
        return NEW_PASSWORD
    if test_zip_password(zip_path, OLD_PASSWORD):
        return OLD_PASSWORD
    return None


def convert_zip(zip_path: Path, output_path: Path, dry_run: bool = False) -> bool:
    """Extract zip with old password and re-create with new password."""
    if dry_run:
        print(f"  [DRY RUN] Would convert {zip_path.name} -> {output_path}")
        return True

    # Create a temporary directory for extraction
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Extract with old password
        extract_result = subprocess.run(
            ["unzip", "-P", OLD_PASSWORD, "-d", str(temp_path), str(zip_path)],
            capture_output=True
        )

        if extract_result.returncode != 0:
            print(f"  Error extracting {zip_path}: {extract_result.stderr.decode()}")
            return False

        # Get list of extracted files/folders
        extracted_items = list(temp_path.iterdir())
        if not extracted_items:
            print(f"  Error: No files extracted from {zip_path}")
            return False

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove output file if it exists
        if output_path.exists():
            output_path.unlink()

        # Create new zip with new password
        # We need to zip from within the temp directory to preserve relative paths
        zip_result = subprocess.run(
            ["zip", "-r", "-P", NEW_PASSWORD, str(output_path.absolute())] +
            [item.name for item in extracted_items],
            cwd=str(temp_path),
            capture_output=True
        )

        if zip_result.returncode != 0:
            print(f"  Error creating new zip: {zip_result.stderr.decode()}")
            return False

        # Verify the new zip
        if not test_zip_password(output_path, NEW_PASSWORD):
            print(f"  Error: Verification failed for {output_path}")
            return False

        return True


def process_directory(source_dir: Path, output_subdir: str, dry_run: bool = False) -> tuple[dict, list]:
    """Process all zip files in a directory. Returns (stats, file_results)."""
    stats = {
        "total": 0,
        "already_new": 0,
        "converted": 0,
        "failed": 0,
        "unknown": 0,
        "corrupted": 0
    }
    file_results = []

    if not source_dir.exists():
        print(f"Directory not found: {source_dir}")
        return stats, file_results

    zip_files = sorted(source_dir.glob("*.zip"))
    stats["total"] = len(zip_files)

    print(f"\nProcessing {len(zip_files)} files in {source_dir}/")
    print("-" * 60)

    for zip_path in zip_files:
        print(f"  {zip_path.name}: ", end="", flush=True)
        result = {"file": zip_path.name, "status": None}

        # First check if it's a valid zip file
        if not is_valid_zip(zip_path):
            print("CORRUPTED/INVALID ZIP")
            stats["corrupted"] += 1
            result["status"] = "corrupted"
            file_results.append(result)
            continue

        password = get_zip_password(zip_path)

        if password == NEW_PASSWORD:
            print("already uses crackmes.one")
            stats["already_new"] += 1
            result["status"] = "already_new"
        elif password == OLD_PASSWORD:
            print("uses crackmes.de -> converting... ", end="", flush=True)
            output_path = OUTPUT_DIR / output_subdir / zip_path.name
            if convert_zip(zip_path, output_path, dry_run):
                print("OK")
                stats["converted"] += 1
                result["status"] = "converted"
            else:
                print("FAILED")
                stats["failed"] += 1
                result["status"] = "failed"
        else:
            print("UNKNOWN PASSWORD (neither works)")
            stats["unknown"] += 1
            result["status"] = "unknown"

        file_results.append(result)

    return stats, file_results


def main():
    parser = argparse.ArgumentParser(
        description="Convert zip passwords from crackmes.de to crackmes.one"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually converting"
    )
    args = parser.parse_args()

    # Change to project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)

    print("=" * 60)
    print("Zip Password Migration Script")
    print("=" * 60)
    print(f"Old password: {OLD_PASSWORD}")
    print(f"New password: {NEW_PASSWORD}")
    print(f"Output directory: {OUTPUT_DIR.absolute()}")
    if args.dry_run:
        print("\n*** DRY RUN MODE - No files will be modified ***")

    # Create output directories
    if not args.dry_run:
        (OUTPUT_DIR / "crackme").mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "solution").mkdir(parents=True, exist_ok=True)

    # Process crackmes
    crackme_stats, crackme_results = process_directory(CRACKME_DIR, "crackme", args.dry_run)

    # Process solutions
    solution_stats, solution_results = process_directory(SOLUTION_DIR, "solution", args.dry_run)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for name, stats in [("Crackmes", crackme_stats), ("Solutions", solution_stats)]:
        print(f"\n{name}:")
        print(f"  Total files:          {stats['total']}")
        print(f"  Already crackmes.one: {stats['already_new']}")
        print(f"  Converted:            {stats['converted']}")
        print(f"  Failed:               {stats['failed']}")
        print(f"  Unknown password:     {stats['unknown']}")
        print(f"  Corrupted/Invalid:    {stats['corrupted']}")

    total_converted = crackme_stats["converted"] + solution_stats["converted"]
    total_failed = crackme_stats["failed"] + solution_stats["failed"]

    # Write log file
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": args.dry_run,
        "old_password": OLD_PASSWORD,
        "new_password": NEW_PASSWORD,
        "crackmes": {
            "stats": crackme_stats,
            "files": crackme_results
        },
        "solutions": {
            "stats": solution_stats,
            "files": solution_results
        }
    }

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_filename = f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_path = log_dir / log_filename

    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)

    print(f"\nLog written to: {log_path.absolute()}")

    if total_converted > 0 and not args.dry_run:
        print(f"Converted files are in: {OUTPUT_DIR.absolute()}/")
        print("Review them and manually replace the originals when ready.")

    if total_failed > 0:
        print(f"\nWarning: {total_failed} file(s) failed to convert!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
