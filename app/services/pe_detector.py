"""
PE file detector service for validating uploaded files.

This module detects Portable Executable (PE) files to prevent users from
submitting patched binaries instead of proper writeups.
"""

import os


def is_pe_file(file_data: bytes, filename: str = "") -> bool:
    """Check if a file is a Portable Executable (PE) file.

    This function checks both the file extension and the PE file signature
    to determine if the file is a Windows executable.

    PE files have:
    1. File extensions: .exe, .dll, .sys, .scr, etc.
    2. DOS header starting with "MZ" (0x4D5A) at offset 0
    3. PE signature "PE\\0\\0" at the offset specified in the DOS header

    Args:
        file_data: The binary content of the file
        filename: Optional filename to check extension

    Returns:
        True if the file is a PE file, False otherwise
    """
    # Check file extension
    if filename:
        ext = os.path.splitext(filename.lower())[1]
        pe_extensions = ['.exe', '.dll', '.sys', '.scr', '.cpl', '.ocx', '.ax', '.acm']
        if ext in pe_extensions:
            return True

    # Check for PE file signature
    # Minimum size for a valid PE file (DOS header is 64 bytes)
    if len(file_data) < 64:
        return False

    # Check for DOS header signature "MZ" (0x4D5A)
    if file_data[0:2] != b'MZ':
        return False

    # Get offset to PE header from DOS header (at offset 0x3C)
    try:
        pe_offset = int.from_bytes(file_data[0x3C:0x3C+4], byteorder='little')
    except Exception:
        return False

    # Verify PE header offset is within file bounds
    if pe_offset < 0 or pe_offset + 4 > len(file_data):
        return False

    # Check for PE signature "PE\0\0" (0x50450000)
    pe_signature = file_data[pe_offset:pe_offset+4]
    if pe_signature == b'PE\x00\x00':
        return True

    return False
