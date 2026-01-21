"""
Provides simple XOR-based obfuscation for writeup content to prevent
trivial scraping while allowing client-side deobfuscation for display.

NOTE: This is NOT encryption - the key is sent to the client.
"""

import hashlib
import base64
from itertools import cycle

DEFAULT_OBFUSCATION_SALT = "crackmes-writeup-default-salt"


def get_obfuscation_salt(config: dict) -> str:
    """Get the obfuscation salt from config, or return default."""
    salt = config.get('APP_CONFIG', {}).get('Writeup', {}).get('ObfuscationSalt')
    if not salt or not isinstance(salt, str) or len(salt.strip()) == 0:
        return DEFAULT_OBFUSCATION_SALT
    return salt


def get_obfuscation_key_base64(hexid: str, salt: str) -> str:
    """Derive a base64-encoded key from hexid and salt for client-side deobfuscation."""
    return base64.b64encode(_derive_key(hexid, salt)).decode('ascii')


def _derive_key(hexid: str, salt: str) -> bytes:
    """Derive a 32-byte key from hexid and salt using SHA-256."""
    return hashlib.sha256(f"{hexid}:{salt}".encode('utf-8')).digest()


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR data with a repeating key."""
    return bytes(a ^ b for a, b in zip(data, cycle(key)))


def obfuscate_writeup(content: str, hexid: str, salt: str) -> bytes:
    """Obfuscate writeup content for storage using XOR."""
    return _xor_bytes(content.encode('utf-8'), _derive_key(hexid, salt))
