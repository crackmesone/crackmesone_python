"""
Integration test for solution upload with PE file detection.
"""
import pytest
from app.services.pe_detector import is_pe_file
from tests.test_utils import create_minimal_pe_file, create_zip_file


class TestSolutionUploadPEDetection:
    """Test that the PE detector correctly identifies files in the upload context."""

    def test_pe_file_with_exe_extension(self):
        """Test that .exe files are detected."""
        pe_data = create_minimal_pe_file()
        assert is_pe_file(pe_data, "crackme.exe") is True

    def test_pe_file_with_dll_extension(self):
        """Test that .dll files are detected."""
        pe_data = create_minimal_pe_file()
        assert is_pe_file(pe_data, "library.dll") is True

    def test_pe_file_by_header_only(self):
        """Test detection by header when extension is not PE."""
        pe_data = create_minimal_pe_file()
        assert is_pe_file(pe_data, "file.bin") is True

    def test_zip_file_not_detected_as_pe(self):
        """Test that ZIP archives are not detected as PE files."""
        zip_data = create_zip_file()
        assert is_pe_file(zip_data, "solution.zip") is False

    def test_text_file_not_detected_as_pe(self):
        """Test that text files are not detected as PE files."""
        text_data = b"This is my solution writeup\nLine 2\nLine 3"
        assert is_pe_file(text_data, "solution.txt") is False

    def test_pdf_file_not_detected_as_pe(self):
        """Test that PDF files are not detected as PE files."""
        pdf_data = b"%PDF-1.4\n" + b"0" * 100
        assert is_pe_file(pdf_data, "writeup.pdf") is False

    def test_markdown_not_detected_as_pe(self):
        """Test that markdown files are not detected as PE files."""
        md_data = b"# Solution\n\n## Analysis\n\nHere is my analysis..."
        assert is_pe_file(md_data, "SOLUTION.md") is False
