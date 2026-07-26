"""Controlled vocabularies for a crackme's single-value classification fields.

Language, architecture and platform are each a single value chosen on the
upload and edit forms. Keeping the option lists here (instead of hardcoding
them into each template) means the upload form, the edit form and any future
consumer all agree on the exact same choices.
"""

# (submitted value, display label) pairs — the value is the stored integer.
DIFFICULTY_CHOICES = [
    ('1', '1. Very Easy'),
    ('2', '2. Easy'),
    ('3', '3. Medium'),
    ('4', '4. Hard'),
    ('5', '5. Very Hard'),
    ('6', '6. Insane'),
]

LANG_CHOICES = [
    'C/C++',
    'Assembler',
    'Java',
    'Go',
    'Rust',
    'WebAssembly',
    'Python',
    'AutoIt',
    '(Visual) Basic',
    'Borland Delphi',
    'Turbo Pascal',
    '.NET',
    'Unspecified/other',
]

ARCH_CHOICES = [
    'x86',
    'x86-64',
    'java',
    'ARM',
    'MIPS',
    'RISC-V',
    'other',
]

PLATFORM_CHOICES = [
    'Mac OS X',
    'Multiplatform',
    'Unix/linux etc.',
    'Windows',
    'Android',
    'iOS',
    'Unspecified/other',
]
