"""
Unit tests for PE file detection.
"""
import pytest
from app.services.pe_detector import is_pe_file


class TestPEDetector:
    """Tests for PE file detection."""

    def test_pe_file_with_extension_exe(self):
        """Test that .exe extension is detected as PE."""
        # Just the extension should be enough
        result = is_pe_file(b'', 'program.exe')
        assert result is True

    def test_pe_file_with_extension_dll(self):
        """Test that .dll extension is detected as PE."""
        result = is_pe_file(b'', 'library.dll')
        assert result is True

    def test_pe_file_with_extension_sys(self):
        """Test that .sys extension is detected as PE."""
        result = is_pe_file(b'', 'driver.sys')
        assert result is True

    def test_pe_file_with_valid_headers(self):
        """Test detection of valid PE file by header."""
        # Create minimal PE file structure
        # DOS header with MZ signature
        dos_header = b'MZ' + b'\x00' * 58  # DOS stub (60 bytes)
        dos_header += b'\x40\x00\x00\x00'  # PE offset at 0x40 (64 bytes)
        
        # PE signature at offset 0x40
        pe_signature = b'PE\x00\x00'
        
        # Combine
        pe_file = dos_header + pe_signature + b'\x00' * 100
        
        result = is_pe_file(pe_file, 'test.bin')
        assert result is True

    def test_non_pe_file_no_mz_header(self):
        """Test that files without MZ header are not detected as PE."""
        # Regular text file
        data = b'This is a text file'
        result = is_pe_file(data, 'readme.txt')
        assert result is False

    def test_non_pe_file_zip_archive(self):
        """Test that ZIP archives are not detected as PE."""
        # ZIP file signature
        zip_data = b'PK\x03\x04' + b'\x00' * 100
        result = is_pe_file(zip_data, 'solution.zip')
        assert result is False

    def test_mz_header_only_no_pe_signature(self):
        """Test file with MZ header but no valid PE signature."""
        # DOS header with MZ but invalid PE signature
        dos_header = b'MZ' + b'\x00' * 58
        dos_header += b'\x40\x00\x00\x00'  # PE offset at 0x40
        
        # Wrong signature at offset 0x40
        invalid_data = dos_header + b'XX\x00\x00' + b'\x00' * 100
        
        result = is_pe_file(invalid_data, 'not_pe.bin')
        assert result is False

    def test_file_too_small(self):
        """Test that very small files are not detected as PE."""
        small_data = b'MZ'
        result = is_pe_file(small_data, 'tiny.bin')
        assert result is False

    def test_pe_offset_out_of_bounds(self):
        """Test file with PE offset pointing outside file bounds."""
        dos_header = b'MZ' + b'\x00' * 58
        dos_header += b'\xFF\xFF\xFF\xFF'  # Invalid PE offset
        
        result = is_pe_file(dos_header, 'invalid.bin')
        assert result is False

    def test_case_insensitive_extension(self):
        """Test that extension check is case-insensitive."""
        result = is_pe_file(b'', 'PROGRAM.EXE')
        assert result is True
        
        result = is_pe_file(b'', 'Library.DLL')
        assert result is True

    def test_empty_filename(self):
        """Test with empty filename."""
        # Should only check content
        non_pe_data = b'Hello World'
        result = is_pe_file(non_pe_data, '')
        assert result is False

    def test_no_filename_with_pe_content(self):
        """Test PE detection without filename but with valid PE content."""
        dos_header = b'MZ' + b'\x00' * 58
        dos_header += b'\x40\x00\x00\x00'
        pe_signature = b'PE\x00\x00'
        pe_file = dos_header + pe_signature + b'\x00' * 100
        
        result = is_pe_file(pe_file)
        assert result is True
