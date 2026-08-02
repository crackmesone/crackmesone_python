"""Flag format and comparison for auto-validated crackmes.

Authors of an auto-validated crackme give us the correct flag once, at upload
time. It is stored in cleartext so reviewers can read it: verifying that a
submission really is solvable, and fixing a mistyped flag afterwards, both need
the actual value, and a hash would leave a wrong flag undetectable until users
started failing on it.

Cleartext storage means the flag must never leave the reviewer tool: the public
crackme page renders a fixed set of fields and the flag is not among them (see
``crackme_view``), and submissions are only ever compared against it here.
"""

import hmac
import re

# Standardised flag format, per issue #127: a CM1 prefix and a brace-delimited
# body, so a flag is always a single unambiguous token that authors can embed in
# a binary and users can copy-paste.
FLAG_PREFIX = 'CM1'
FLAG_BODY_MAX = 56
# Printable ASCII (0x21-0x7e) minus the braces, which keeps the closing brace
# unambiguous. Keeping a flag a single whitespace-free ASCII token means neither
# copy-pasting it out of a terminal nor re-encoding it can silently change it.
FLAG_PATTERN = re.compile(
    r'^%s\{[\x21-\x7a\x7c\x7e]{1,%d}\}$' % (FLAG_PREFIX, FLAG_BODY_MAX)
)

FLAG_FORMAT_HINT = f'Flags look like {FLAG_PREFIX}{{...}}'


def normalize_flag(flag):
    """Return a submitted flag with surrounding whitespace removed.

    Users copy flags out of terminals, so leading/trailing whitespace is noise
    rather than a wrong answer. Inner characters are left untouched -- they are
    part of the flag.
    """
    return (flag or '').strip()


def is_valid_flag_format(flag):
    """Return True if the flag matches the standardised CM1{...} format."""
    return bool(FLAG_PATTERN.match(flag or ''))


def flags_match(stored_flag, submitted_flag):
    """Return True if a submitted flag matches the crackme's stored one.

    Compared in constant time so the response can't be used to recover the flag
    character by character.
    """
    if not stored_flag or not submitted_flag:
        return False
    return hmac.compare_digest(stored_flag, submitted_flag)
