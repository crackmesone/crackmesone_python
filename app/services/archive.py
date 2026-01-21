"""
Archive service for validating uploaded archive files.
"""

import zipfile
import tarfile
import io
import struct


# PE file extensions (case-insensitive)
PE_EXTENSIONS = frozenset({'.exe', '.dll', '.sys', '.scr', '.ocx', '.com', '.drv', '.cpl', '.efi'})


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


def _is_metadata_file(filename: str) -> bool:
    """Check if a file is a metadata file that should be ignored when counting.

    Args:
        filename: The filename/path within the archive

    Returns:
        True if the file is a metadata file, False otherwise
    """
    # macOS resource fork files and metadata
    if filename.startswith('__MACOSX/'):
        return True
    # macOS AppleDouble files (resource forks)
    basename = filename.rsplit('/', 1)[-1]
    if basename.startswith('._'):
        return True
    # macOS .DS_Store files
    if basename == '.DS_Store':
        return True
    return False


def is_rar_file(file_data: bytes) -> bool:
    """Check if file is a RAR archive by magic bytes."""
    # RAR magic: "Rar!" (0x52 0x61 0x72 0x21)
    return file_data[:4] == b'Rar!'


def is_tar_file(file_data: bytes) -> bool:
    """Check if file is a tar archive (including .tar.gz, .tar.bz2, .tar.xz)."""
    # Check for gzip magic (1f 8b) - could be .tar.gz
    if file_data[:2] == b'\x1f\x8b':
        try:
            with tarfile.open(fileobj=io.BytesIO(file_data)) as tf:
                return True
        except Exception:
            return False

    # Check for bzip2 magic (42 5a 68) - could be .tar.bz2
    if file_data[:3] == b'BZh':
        try:
            with tarfile.open(fileobj=io.BytesIO(file_data)) as tf:
                return True
        except Exception:
            return False

    # Check for xz magic (fd 37 7a 58 5a 00) - could be .tar.xz
    if file_data[:6] == b'\xfd7zXZ\x00':
        try:
            with tarfile.open(fileobj=io.BytesIO(file_data)) as tf:
                return True
        except Exception:
            return False

    # Check for plain tar (ustar at offset 257)
    if len(file_data) > 262 and file_data[257:262] == b'ustar':
        return True

    return False


def is_unsupported_archive(file_data: bytes) -> bool:
    """Check if file is an unsupported archive format (RAR, tar, etc.).

    Only ZIP files are supported for multi-file uploads.
    """
    return is_rar_file(file_data) or is_tar_file(file_data)


def get_archive_file_count(file_data: bytes) -> int | None:
    """Get the number of files in a ZIP archive.

    Returns None if the file is not a valid ZIP archive.
    Excludes metadata files (macOS __MACOSX, .DS_Store, ._ files) from the count.

    Args:
        file_data: The binary content of the archive file

    Returns:
        Number of files in the archive, or None if not a valid ZIP archive
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_data), 'r') as zf:
            file_count = sum(
                1 for info in zf.infolist()
                if not info.is_dir() and not _is_metadata_file(info.filename)
            )
            return file_count
    except zipfile.BadZipFile:
        return None
    except Exception:
        return None


def is_single_file_archive(file_data: bytes) -> bool:
    """Check if an archive contains only a single file.

    This is used to reject archives that unnecessarily wrap a single file,
    since users should upload single files directly without archiving them.

    Args:
        file_data: The binary content of the archive file

    Returns:
        True if the archive contains exactly one file, False otherwise
    """
    file_count = get_archive_file_count(file_data)
    return file_count == 1


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
