"""
Archive service for validating uploaded archive files.
"""

import zipfile
import io
import struct
from typing import Optional

# PE file extensions (case-insensitive)
PE_EXTENSIONS = {'.exe', '.dll', '.sys', '.scr', '.ocx', '.com', '.drv', '.cpl', '.efi'}


def is_pe_file(filename: str, file_data: bytes) -> bool:
    """Check if a file is a Windows PE (Portable Executable) file.

    Checks both the file extension and the PE header magic bytes.

    Args:
        filename: The name of the file (used for extension check)
        file_data: The binary content of the file

    Returns:
        True if the file appears to be a PE file, False otherwise
    """
    # Check file extension
    if filename:
        ext = filename.lower()
        # Get extension (handle files like "file.exe" or just check suffix)
        dot_idx = ext.rfind('.')
        if dot_idx != -1:
            ext = ext[dot_idx:]
            if ext in PE_EXTENSIONS:
                return True

    # Check PE header magic bytes
    if len(file_data) < 64:
        return False

    # Check for DOS MZ header
    if file_data[0:2] != b'MZ':
        return False

    # Get PE header offset from DOS header (at offset 0x3C)
    try:
        pe_offset = struct.unpack('<I', file_data[0x3C:0x40])[0]

        # Check if PE offset is reasonable
        if pe_offset < 64 or pe_offset > len(file_data) - 4:
            return False

        # Check for PE signature
        if file_data[pe_offset:pe_offset + 4] == b'PE\x00\x00':
            return True
    except (struct.error, IndexError):
        pass

    return False


def is_archive_password_protected(file_data: bytes) -> bool:
    """Check if an archive file is password-protected.

    Currently supports ZIP files. Other archive formats (RAR, 7z) are
    detected by attempting to read as ZIP and failing gracefully.

    Args:
        file_data: The binary content of the archive file

    Returns:
        True if the archive is password-protected, False otherwise
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_data), 'r') as zf:
            for info in zf.infolist():
                # Check if any file in the archive is encrypted
                # flag_bits bit 0 indicates encryption
                if info.flag_bits & 0x1:
                    return True
    except zipfile.BadZipFile:
        # Not a valid ZIP file, could be another format or not an archive
        # For non-ZIP archives, we can't easily detect password protection
        # without additional libraries, so we'll allow them through
        pass
    except Exception:
        # Any other error, allow the file through
        pass

    return False

def is_archive(file_data: bytes) -> bool:
    """Check if the provided file data is a recognized archive format.

    Args:
        file_data: The binary content of the archive file
    """
    try: 
        with zipfile.ZipFile(io.BytesIO(file_data), 'r') as zf:
            # read the list of files to confirm it's a valid archive
            _ = zf.namelist()
            return True
    except Exception: # May not be a archive or some other error
        pass
    return False

def size_of_archive_contents(file_data: bytes) -> Optional[int]:
    """Calculate the total uncompressed size of all files within the archive..

    Args:
        file_data: The binary content of the archive file

    Returns:
        Total size in bytes of all files within the archive if successful, None otherwise
    """
    total_size = 0
    try:
        with zipfile.ZipFile(io.BytesIO(file_data), 'r') as zf:
            for info in zf.infolist():
                total_size += info.file_size
        return total_size
    except zipfile.BadZipFile:
        pass
    except Exception:
        pass
    return None