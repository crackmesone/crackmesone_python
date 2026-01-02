#!/usr/bin/env python3
"""
Generate password hash for reviewer tool users.

Reads the PasswordSalt from config/config.json and generates a SHA256 hash
of the provided password combined with the salt.

Usage: python script/generate_reviewer_password_hash.py <password>
"""

import sys
import hashlib
import json
import os


def load_password_salt():
    """Load the password salt from config file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, '..', 'config', 'config.json')

    if not os.path.exists(config_path):
        print(f"Error: Config file not found at {config_path}")
        sys.exit(1)

    with open(config_path, 'r') as f:
        config = json.load(f)

    reviewer_config = config.get('Reviewer', {})
    if not reviewer_config.get('Enabled', False):
        print("Warning: Reviewer is not enabled in config")

    password_salt = reviewer_config.get('PasswordSalt')
    if not password_salt:
        print("Error: Reviewer.PasswordSalt not found in config")
        sys.exit(1)

    return password_salt


def generate_hash(password, salt):
    """Generate SHA256 hash of password + salt."""
    hash_input = password + salt
    return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script/generate_reviewer_password_hash.py <password>")
        sys.exit(1)

    password = sys.argv[1]
    salt = load_password_salt()
    password_hash = generate_hash(password, salt)
    print(password_hash)
