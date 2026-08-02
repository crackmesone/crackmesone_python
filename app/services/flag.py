"""Flag format and verification for auto-validated crackmes.

Authors of an auto-validated crackme submit the correct flag once, at upload
time. It is stored as a bcrypt hash and never in cleartext: the site only ever
needs to answer "does this submission match?", and a database leak of every
crackme's flag would quietly retire the whole point system.

That means nobody -- author, reviewer or admin -- can read a flag back out of
the site. Reviewers verify a submission by building it from the private source
archive and testing the flag they derive against the hash (see the check-flag
tool on the review page); if the author fat-fingered the flag, the test fails
and the crackme gets rejected rather than shipping unsolvable.
"""

import re

from app.services.passhash import hash_string, match_string

# Standardised flag format, per issue #127: a CM1 prefix and a brace-delimited
# body. The body is printable ASCII without braces, so a flag is always a single
# unambiguous token that authors can embed in a binary and users can copy-paste.
FLAG_PREFIX = 'CM1'
FLAG_BODY_MAX = 56
# Printable ASCII (0x21-0x7e) minus the braces, which keeps the closing brace
# unambiguous. Keeping a flag a single whitespace-free ASCII token means neither
# copy-pasting it out of a terminal nor re-encoding it can silently change it --
# and it bounds a flag's byte length, which matters below.
FLAG_PATTERN = re.compile(
    r'^%s\{[\x21-\x7a\x7c\x7e]{1,%d}\}$' % (FLAG_PREFIX, FLAG_BODY_MAX)
)

FLAG_FORMAT_HINT = f'Flags look like {FLAG_PREFIX}{{...}}'

# bcrypt silently truncates at 72 bytes, which would make two flags sharing a
# long prefix interchangeable. FLAG_BODY_MAX keeps every valid flag well under
# that, so the truncation can never be reached.
assert len(FLAG_PREFIX) + 2 + FLAG_BODY_MAX < 72


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


def hash_flag(flag):
    """Hash a flag for storage. The cleartext is never persisted."""
    return hash_string(flag)


def verify_flag(flag_hash, flag):
    """Return True if ``flag`` matches the stored hash.

    Comparison happens inside bcrypt, so it is constant-time with respect to the
    hash contents.
    """
    if not flag_hash or not flag:
        return False
    return match_string(flag_hash, flag)
