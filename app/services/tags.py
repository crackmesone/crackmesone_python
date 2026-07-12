"""
Obfuscation tag vocabulary and helpers.

Crackmes can be labeled with high-level anti-analysis / obfuscation tags
(anti-debugging, string encryption, packers, ...).  The controlled vocabulary
below mirrors the crackmes-RE dataset: 21 high-level "obfuscation classes" plus
finer **sub-labels** nested under three of those classes (specific anti-debug
methods, packer names, and control-flow techniques).  The labels were produced
by an AI reading public solution writeups and comments and are therefore **not
guaranteed to be accurate**.  The dataset is what seeds the initial tags (see
``script/import_tags.py``); afterwards authors pick tags at submission time,
reviewers can override them, and any user can request changes.
"""

# Canonical, ordered list of high-level obfuscation tags (the 21 dataset
# classes).  Order is roughly by how common the class is so the UI reads sensibly.
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

# Finer sub-labels, nested under their parent class.  These come from the
# dataset's antidebug_methods / packers / controlflow_methods fields.  A crackme
# usually carries the parent class *and* the specific sub-labels it exhibits.
SUBLABELS = {
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
        "DbgBreakPoint/DbgUiRemoteBreakin patch",
        "CloseHandle invalid-handle",
    ],
    "Packer": [
        "UPX",
        "FSG",
        "ASPack",
        "MPRESS",
        "tElock",
        "Petite",
        "Yoda",
        "PECompact",
        "exepack",
        "Other named (Morphine/Neolite/PEtite…)",
        "PKLite",
        "MEW",
    ],
    "Control-flow obfuscation": [
        "Spaghetti / junk-branch",
        "Exception / interrupt-based",
        "Indirect / computed jumps & calls",
        "State machine / dispatcher",
        "Control-flow flattening (CFF)",
        "Return-address / stack-based",
    ],
}

# Dataset field name -> parent class, so the import script knows where each
# sub-label list belongs.
SUBLABEL_FIELDS = {
    "antidebug_methods": "Anti-debugging",
    "packers": "Packer",
    "controlflow_methods": "Control-flow obfuscation",
}

# Grouped view for templates: an ordered list of {"tag", "sublabels"} where a
# class's sub-labels (if any) render nested underneath it.
TAG_GROUPS = [
    {"tag": tag, "sublabels": SUBLABELS.get(tag, [])}
    for tag in OBFUSCATION_TAGS
]

# Flat canonical order: each class immediately followed by its sub-labels.  Used
# both for validation and to canonically order any selection.
ALL_TAGS = []
for _group in TAG_GROUPS:
    ALL_TAGS.append(_group["tag"])
    ALL_TAGS.extend(_group["sublabels"])

# Fast membership set and canonical ordering index.
TAG_SET = set(ALL_TAGS)
_TAG_ORDER = {tag: i for i, tag in enumerate(ALL_TAGS)}

# Where the "?" next to the tags links to.  The tags originate from this
# AI-generated dataset, so the explanation of their (im)precision lives there.
DATASET_URL = "https://github.com/crackmesone/crackmes-re-dataset"


def normalize_tags(raw_tags):
    """Validate, de-duplicate, and canonically order a list of tags.

    Accepts any iterable of strings (e.g. ``request.form.getlist('tags')``),
    drops anything not in the controlled vocabulary (classes or sub-labels),
    removes duplicates, and returns the survivors in canonical order (each class
    followed by its sub-labels).
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
