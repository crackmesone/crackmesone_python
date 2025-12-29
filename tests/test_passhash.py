"""
Unit tests for password hashing service.
"""
import pytest
from app.services.passhash import hash_string, hash_bytes, match_string, match_bytes


class TestPasshashString:
    """Tests for string password hashing functions."""

    def test_hash_string_returns_string(self):
        """Test that hash_string returns a string."""
        password = "testpassword123"
        hashed = hash_string(password)
        assert isinstance(hashed, str)

    def test_hash_string_different_for_same_input(self):
        """Test that hashing same password twice gives different results (due to salt)."""
        password = "testpassword123"
        hash1 = hash_string(password)
        hash2 = hash_string(password)
        assert hash1 != hash2

    def test_match_string_correct(self):
        """Test that match_string returns True for correct password."""
        password = "testpassword123"
        hashed = hash_string(password)
        assert match_string(hashed, password) is True

    def test_match_string_incorrect(self):
        """Test that match_string returns False for incorrect password."""
        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = hash_string(password)
        assert match_string(hashed, wrong_password) is False

    def test_match_string_empty_password(self):
        """Test match_string with empty password."""
        password = "testpassword123"
        hashed = hash_string(password)
        assert match_string(hashed, "") is False

    def test_hash_string_special_characters(self):
        """Test hashing password with special characters."""
        password = "p@ssw0rd!#$%^&*()"
        hashed = hash_string(password)
        assert match_string(hashed, password) is True

    def test_hash_string_unicode(self):
        """Test hashing password with unicode characters."""
        password = "password123!"
        hashed = hash_string(password)
        assert match_string(hashed, password) is True

    def test_hash_string_long_password(self):
        """Test hashing a very long password."""
        password = "a" * 72  # bcrypt has a 72 byte limit
        hashed = hash_string(password)
        assert match_string(hashed, password) is True


class TestPasshashBytes:
    """Tests for bytes password hashing functions."""

    def test_hash_bytes_returns_bytes(self):
        """Test that hash_bytes returns bytes."""
        password = b"testpassword123"
        hashed = hash_bytes(password)
        assert isinstance(hashed, bytes)

    def test_hash_bytes_different_for_same_input(self):
        """Test that hashing same password twice gives different results."""
        password = b"testpassword123"
        hash1 = hash_bytes(password)
        hash2 = hash_bytes(password)
        assert hash1 != hash2

    def test_match_bytes_correct(self):
        """Test that match_bytes returns True for correct password."""
        password = b"testpassword123"
        hashed = hash_bytes(password)
        assert match_bytes(hashed, password) is True

    def test_match_bytes_incorrect(self):
        """Test that match_bytes returns False for incorrect password."""
        password = b"testpassword123"
        wrong_password = b"wrongpassword"
        hashed = hash_bytes(password)
        assert match_bytes(hashed, wrong_password) is False

    def test_match_bytes_empty_password(self):
        """Test match_bytes with empty password."""
        password = b"testpassword123"
        hashed = hash_bytes(password)
        assert match_bytes(hashed, b"") is False
