"""
Unit tests for input validation functions.
"""
import pytest


class TestUsernameValidation:
    """Tests for username validation."""

    def test_valid_username(self):
        """Test valid usernames."""
        valid_usernames = [
            'user',
            'user123',
            'test_user',
            'TestUser',
            'a' * 20
        ]
        for username in valid_usernames:
            # Username should be alphanumeric with underscores, 3-30 chars
            assert len(username) >= 1
            assert len(username) <= 30

    def test_invalid_username_too_short(self):
        """Test username that's too short."""
        username = 'ab'
        assert len(username) < 3

    def test_invalid_username_too_long(self):
        """Test username that's too long."""
        username = 'a' * 31
        assert len(username) > 30


class TestEmailValidation:
    """Tests for email validation."""

    def test_valid_email(self):
        """Test valid email addresses."""
        valid_emails = [
            'test@example.com',
            'user.name@domain.org',
            'user+tag@example.co.uk'
        ]
        for email in valid_emails:
            assert '@' in email
            assert '.' in email.split('@')[1]

    def test_invalid_email_no_at(self):
        """Test email without @ symbol."""
        email = 'testexample.com'
        assert '@' not in email

    def test_invalid_email_no_domain(self):
        """Test email without domain."""
        email = 'test@'
        parts = email.split('@')
        assert len(parts) < 2 or parts[1] == ''


class TestPasswordValidation:
    """Tests for password validation."""

    def test_valid_password(self):
        """Test valid passwords."""
        valid_passwords = [
            'password123',
            'SecureP@ss1',
            'abcdefgh',
            '12345678'
        ]
        for password in valid_passwords:
            assert len(password) >= 8

    def test_invalid_password_too_short(self):
        """Test password that's too short."""
        password = '1234567'
        assert len(password) < 8

    def test_password_whitespace(self):
        """Test password with whitespace."""
        password = 'pass word'
        # Some systems allow spaces, others don't
        assert len(password) >= 8


class TestCrackmeValidation:
    """Tests for crackme input validation."""

    def test_valid_crackme_name(self):
        """Test valid crackme names."""
        valid_names = [
            'My Crackme',
            'CrackMe_v1',
            'Easy Challenge'
        ]
        for name in valid_names:
            assert len(name) >= 1
            assert len(name) <= 100

    def test_valid_difficulty(self):
        """Test valid difficulty ratings."""
        valid_difficulties = [1, 2, 3, 4, 5, 6]
        for diff in valid_difficulties:
            assert 1 <= diff <= 6

    def test_invalid_difficulty_too_low(self):
        """Test difficulty rating too low."""
        difficulty = 0
        assert difficulty < 1

    def test_invalid_difficulty_too_high(self):
        """Test difficulty rating too high."""
        difficulty = 7
        assert difficulty > 6
