"""
Archive service for validating uploaded archive files.
"""

import zipfile
import io


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
