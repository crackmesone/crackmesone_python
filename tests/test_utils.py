"""
Test utilities for creating sample file data.
"""


def create_minimal_pe_file():
    """Create minimal valid PE file data for testing.
    
    Returns:
        bytes: Binary data representing a minimal but valid PE file structure
    """
    # DOS header with MZ signature
    dos_header = b'MZ' + b'\x00' * 58  # MZ (2 bytes) + padding (58 bytes)
    dos_header += b'\x40\x00\x00\x00'  # PE offset at 0x40 (total 64 bytes)
    
    # PE signature at offset 0x40
    pe_signature = b'PE\x00\x00'
    
    # Combine with some padding
    return dos_header + pe_signature + b'\x00' * 100


def create_zip_file():
    """Create minimal ZIP file data for testing.
    
    Returns:
        bytes: Binary data with ZIP file signature
    """
    # ZIP file signature
    return b'PK\x03\x04' + b'\x00' * 100
