"""
Obfuscation label vocabulary and helpers.

Crackmes can be labeled with high-level anti-analysis / obfuscation labels
(anti-debugging, string encryption, packers, ...) plus finer **sub-labels**
nested under some of those classes. The labels come from the crackmes-RE dataset
(AI-generated, so **not guaranteed accurate**).

The controlled vocabulary is **stored in the ``label_vocabulary`` MongoDB
collection** (a single document) so it can be updated without code changes when
the dataset changes -- regenerate it (and re-label crackmes) from the dataset
with ``script/sync_labels.py``. The ``DEFAULT_*`` values below are the
built-in baseline: they seed that collection and act as a fallback when it is
empty (fresh DB, tests, DB unavailable).

Callers should use the accessor functions (``get_label_groups()``,
``normalize_labels()``, ...) rather than reading module-level constants, because
the active vocabulary is resolved from the database at runtime.
"""

from app.services.database import get_collection, check_connection

# Collection + document id that hold the live vocabulary.
VOCAB_COLLECTION = "label_vocabulary"
VOCAB_ID = "current"

# Where the "?" next to the labels links to (the AI-generated source dataset).
DATASET_URL = "https://github.com/crackmesone/crackmes-re-dataset"

# ---------------------------------------------------------------------------
# Built-in baseline (used to seed the DB collection and as a fallback)
# ---------------------------------------------------------------------------

# High-level obfuscation classes, ordered by how common they are.
DEFAULT_CLASSES = [
    "Anti-debugging",
    "Packer",
    "String / data encryption",
    "Self-modifying / runtime decrypt",
    "Code virtualization / VM",
    "Crypto / hash algorithm",
    "Control-flow obfuscation",
    "Anti-tamper / integrity",
    "Anti-disassembly",
    "Import / API obfuscation",
    "Custom / generic obfuscation",
    "Encoding (base64/hex)",
    "Binary hardening (ASLR/PIE/canary)",
    "Anti-VM / sandbox",
    "Nag / trial",
    "Anti-static analysis",
]

# Finer sub-labels nested under their parent class.
DEFAULT_SUBLABELS = {
    "Anti-debugging": [
        "IsDebuggerPresent",
        "Debugger/tool window detection",
        "Timing (rdtsc/GetTickCount)",
        "PEB BeingDebugged / NtGlobalFlag",
        "INT3 / 0xCC breakpoint scan",
        "ptrace (Linux)",
        "Exception-based (SEH/VEH/INT2D)",
        "Hardware breakpoints (DRx)",
        "NtQueryInformationProcess",
        "OutputDebugString",
        "CheckRemoteDebuggerPresent",
        "Self-debug / block debugger",
        "TLS callback",
        "Anti-dump",
        "Parent-process check",
        "Anti-attach / thread suspension",
        "DbgBreakPoint/DbgUiRemoteBreakin patch",
        "CloseHandle invalid-handle",
    ],
    "Packer": [
        "UPX",
        "FSG",
        "ASPack",
        "MPRESS",
        "tElock",
        "VMProtect",
        "Petite",
        "Yoda",
        "ASProtect",
        ".NET Reactor",
        "ConfuserEx",
        "PECompact",
        "exepack",
        "Enigma",
        "Themida",
        "ExeCryptor",
        "WinLicense",
        "SmartAssembly",
        "Other named (Morphine/Neolite/PEtite…)",
        "PELock",
        "CodeVirtualizer",
        "PKLite",
        "MEW",
        "Dotfuscator",
    ],
    "Control-flow obfuscation": [
        "Spaghetti / junk-branch",
        "Exception / interrupt-based",
        "Indirect / computed jumps & calls",
        "State machine / dispatcher",
        "Control-flow flattening (CFF)",
        "Return-address / stack-based",
    ],
    "Anti-disassembly": [
        "Junk / garbage bytes",
        "Malformed PE / bad bytes (UD2)",
        "Opaque predicates",
        "Overlapping / misaligned instructions",
        "Jump-based desync",
    ],
    # AES / Base64 / RC4 / TEA-XTEA also appear as string-encryption ciphers, so
    # they are qualified with "(crypto)" here to keep each label under one parent.
    "Crypto / hash algorithm": [
        "MD5",
        "CRC32",
        "Base64 (crypto)",
        "RSA",
        "AES (crypto)",
        "SHA-256",
        "Other / custom hash",
        "RC4 (crypto)",
        "TEA / XTEA (crypto)",
        "SHA-1",
        "Blowfish",
        "DES / 3DES",
    ],
    # ...and the same four ciphers are qualified with "(encryption)" here.
    "String / data encryption": [
        "XOR",
        "Base64 (encryption)",
        "AES (encryption)",
        "RC4 (encryption)",
        "TEA / XTEA (encryption)",
        "Substitution / table",
    ],
}

# Dataset field name -> parent class (which sub-label list each field feeds).
DEFAULT_FIELD_PARENTS = {
    "antidebug_methods": "Anti-debugging",
    "packers": "Packer",
    "controlflow_methods": "Control-flow obfuscation",
    "antidisasm_methods": "Anti-disassembly",
    "crypto_methods": "Crypto / hash algorithm",
    "encryption_methods": "String / data encryption",
}

# Some algorithm names appear under more than one field; they are qualified with
# the source context so each maps to exactly one parent (e.g. dataset "AES" ->
# "AES (crypto)" or "AES (encryption)").
DEFAULT_QUALIFY_SUFFIX = {"crypto_methods": "crypto", "encryption_methods": "encryption"}
DEFAULT_QUALIFY_VALUES = ["AES", "Base64", "RC4", "TEA / XTEA"]


def default_vocabulary_doc():
    """The built-in vocabulary as a plain dict (also used to seed the DB)."""
    return {
        "classes": list(DEFAULT_CLASSES),
        "sublabels": {k: list(v) for k, v in DEFAULT_SUBLABELS.items()},
        "field_parents": dict(DEFAULT_FIELD_PARENTS),
        "qualify_suffix": dict(DEFAULT_QUALIFY_SUFFIX),
        "qualify_values": list(DEFAULT_QUALIFY_VALUES),
        "dataset_url": DATASET_URL,
    }


# ---------------------------------------------------------------------------
# Vocabulary object + DB loading (cached)
# ---------------------------------------------------------------------------

class Vocabulary:
    """An immutable view of the controlled vocabulary with derived lookups."""

    def __init__(self, doc):
        self.classes = list(doc.get("classes") or [])
        self.sublabels = {k: list(v) for k, v in (doc.get("sublabels") or {}).items()}
        self.field_parents = dict(doc.get("field_parents") or {})
        self.qualify_suffix = dict(doc.get("qualify_suffix") or {})
        self.qualify_values = set(doc.get("qualify_values") or [])
        self.dataset_url = doc.get("dataset_url") or DATASET_URL

        # Grouped view for templates: class then its (possibly empty) sub-labels.
        self.label_groups = [
            {"label": c, "sublabels": self.sublabels.get(c, [])}
            for c in self.classes
        ]
        # Flat canonical order: each class immediately followed by its sub-labels.
        self.all_labels = []
        for group in self.label_groups:
            self.all_labels.append(group["label"])
            self.all_labels.extend(group["sublabels"])
        self.label_set = set(self.all_labels)
        self._order = {label: i for i, label in enumerate(self.all_labels)}

    def normalize(self, raw_labels):
        if not raw_labels:
            return []
        seen = set()
        for label in raw_labels:
            if isinstance(label, str):
                label = label.strip()
            if label in self.label_set:
                seen.add(label)
        return sorted(seen, key=lambda t: self._order[t])

    def is_valid(self, label):
        return label in self.label_set

    def sublabel_label(self, field, value):
        suffix = self.qualify_suffix.get(field)
        if suffix and value in self.qualify_values:
            return "{} ({})".format(value, suffix)
        return value


_cache = None


def _load_vocabulary_doc():
    """Return the vocabulary document from the DB, or the default if absent."""
    try:
        if check_connection():
            doc = get_collection(VOCAB_COLLECTION).find_one({"_id": VOCAB_ID})
            if doc:
                return doc
    except Exception as e:  # pragma: no cover - defensive; fall back to default
        print(f"Label vocabulary load error, using default: {e}")
    return default_vocabulary_doc()


def get_vocabulary():
    """Return the active :class:`Vocabulary`, loading (and caching) it lazily."""
    global _cache
    if _cache is None:
        _cache = Vocabulary(_load_vocabulary_doc())
    return _cache


def reload_vocabulary():
    """Drop the cache so the next access re-reads the DB (after a sync/edit)."""
    global _cache
    _cache = None


# ---------------------------------------------------------------------------
# Public API (stable for controllers, templates, scripts)
# ---------------------------------------------------------------------------

def normalize_labels(raw_labels):
    """Validate, de-duplicate, and canonically order a list of labels."""
    return get_vocabulary().normalize(raw_labels)


def is_valid_label(label):
    """Return True if ``label`` is part of the active controlled vocabulary."""
    return get_vocabulary().is_valid(label)


def dataset_sublabel_label(field, value):
    """Map a raw dataset sub-label ``(field, value)`` to its canonical label."""
    return get_vocabulary().sublabel_label(field, value)


def get_label_groups():
    """Ordered ``[{"label", "sublabels"}]`` for rendering the label picker."""
    return get_vocabulary().label_groups


def get_all_labels():
    """Flat list of every valid label in canonical order."""
    return get_vocabulary().all_labels


def get_classes():
    """The high-level obfuscation classes, ordered."""
    return get_vocabulary().classes


def get_sublabels():
    """Mapping of parent class -> ordered sub-labels."""
    return get_vocabulary().sublabels


def get_sublabel_fields():
    """Mapping of dataset field name -> parent class."""
    return get_vocabulary().field_parents


def get_dataset_url():
    """URL the labels "?" help link points at."""
    return get_vocabulary().dataset_url
