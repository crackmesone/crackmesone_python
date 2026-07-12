"""
Obfuscation tag vocabulary and helpers.

Crackmes can be labeled with high-level anti-analysis / obfuscation tags
(anti-debugging, string encryption, packers, ...).  The controlled vocabulary
below mirrors the 21 "obfuscation classes" of the crackmes-RE dataset, whose
labels were produced by an AI reading public solution writeups and comments and
are therefore **not guaranteed to be accurate**.  The dataset is what seeds the
initial tags (see ``script/import_tags.py``); afterwards authors pick tags at
submission time, reviewers can override them, and any user can request changes.
"""

# Canonical, ordered list of obfuscation tags (the 21 dataset classes).
# Order is roughly by how common the class is so the UI reads sensibly.
OBFUSCATION_TAGS = [
    "Anti-debugging",
    "Packer",
    "String / data encryption",
    "Self-modifying / runtime decrypt",
    "Code virtualization / VM",
    "Crypto / hash algorithm",
    "Anti-tamper / integrity",
    "Control-flow obfuscation",
    "Anti-disassembly",
    "Timing checks",
    "Exception-based",
    "Import / API obfuscation",
    "Custom / generic obfuscation",
    "Encoding (base64/hex)",
    "Commercial protector",
    "Stripped / no symbols",
    "Anti-attach / thread tricks",
    "Binary hardening (ASLR/PIE/canary)",
    "Anti-VM / sandbox",
    "Nag / trial",
    "Anti-static analysis",
]

# Fast membership set and canonical ordering index.
TAG_SET = set(OBFUSCATION_TAGS)
_TAG_ORDER = {tag: i for i, tag in enumerate(OBFUSCATION_TAGS)}

# Where the "?" next to the tags links to.  The tags originate from this
# AI-generated dataset, so the explanation of their (im)precision lives there.
DATASET_URL = "https://github.com/crackmesone/crackmes-re-dataset"


def normalize_tags(raw_tags):
    """Validate, de-duplicate, and canonically order a list of tags.

    Accepts any iterable of strings (e.g. ``request.form.getlist('tags')``),
    drops anything not in the controlled vocabulary, removes duplicates, and
    returns the survivors in the canonical :data:`OBFUSCATION_TAGS` order.
    """
    if not raw_tags:
        return []

    seen = set()
    for tag in raw_tags:
        if isinstance(tag, str):
            tag = tag.strip()
        if tag in TAG_SET:
            seen.add(tag)

    return sorted(seen, key=lambda t: _TAG_ORDER[t])


def is_valid_tag(tag):
    """Return True if ``tag`` is part of the controlled vocabulary."""
    return tag in TAG_SET
