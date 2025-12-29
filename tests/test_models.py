"""
Unit tests for database models.
"""
import pytest
from unittest.mock import MagicMock, patch
from bson import ObjectId
from datetime import datetime


class TestUserModel:
    """Tests for User model functions."""

    def test_user_by_name_found(self, mock_db, sample_user):
        """Test finding a user by name."""
        mock_db.users.insert_one(sample_user)

        with patch('app.models.user.get_db', return_value=mock_db):
            from app.models.user import user_by_name
            result = user_by_name('testuser')
            assert result is not None
            assert result['name'] == 'testuser'

    def test_user_by_name_not_found(self, mock_db):
        """Test finding a non-existent user by name."""
        with patch('app.models.user.get_db', return_value=mock_db):
            from app.models.user import user_by_name
            result = user_by_name('nonexistent')
            assert result is None

    def test_user_by_email_found(self, mock_db, sample_user):
        """Test finding a user by email."""
        mock_db.users.insert_one(sample_user)

        with patch('app.models.user.get_db', return_value=mock_db):
            from app.models.user import user_by_email
            result = user_by_email('test@example.com')
            assert result is not None
            assert result['email'] == 'test@example.com'

    def test_user_by_email_not_found(self, mock_db):
        """Test finding a non-existent user by email."""
        with patch('app.models.user.get_db', return_value=mock_db):
            from app.models.user import user_by_email
            result = user_by_email('nonexistent@example.com')
            assert result is None


class TestCrackmeModel:
    """Tests for Crackme model functions."""

    def test_crackme_by_hexid_found(self, mock_db, sample_crackme):
        """Test finding a crackme by hex ID."""
        result = mock_db.crackmes.insert_one(sample_crackme)
        hexid = str(result.inserted_id)

        with patch('app.models.crackme.get_db', return_value=mock_db):
            from app.models.crackme import crackme_by_hexid
            crackme = crackme_by_hexid(hexid)
            assert crackme is not None
            assert crackme['name'] == 'Test Crackme'

    def test_crackme_by_hexid_not_found(self, mock_db):
        """Test finding a non-existent crackme."""
        fake_id = str(ObjectId())

        with patch('app.models.crackme.get_db', return_value=mock_db):
            from app.models.crackme import crackme_by_hexid
            result = crackme_by_hexid(fake_id)
            assert result is None

    def test_crackme_by_hexid_invalid_id(self, mock_db):
        """Test finding a crackme with invalid hex ID."""
        with patch('app.models.crackme.get_db', return_value=mock_db):
            from app.models.crackme import crackme_by_hexid
            result = crackme_by_hexid('invalid-id')
            assert result is None

    def test_get_last_crackmes(self, mock_db, sample_crackme):
        """Test getting the last crackmes."""
        # Insert multiple crackmes
        for i in range(5):
            crackme = sample_crackme.copy()
            crackme['name'] = f'Crackme {i}'
            crackme['visible'] = True
            mock_db.crackmes.insert_one(crackme)

        with patch('app.models.crackme.get_db', return_value=mock_db):
            from app.models.crackme import get_last_crackmes
            crackmes = get_last_crackmes(page=1, per_page=3)
            assert len(crackmes) == 3


class TestCommentModel:
    """Tests for Comment model functions."""

    def test_get_comments_for_crackme(self, mock_db):
        """Test getting comments for a crackme."""
        crackme_id = ObjectId()
        comments = [
            {
                'crackmeid': crackme_id,
                'author': 'user1',
                'content': 'Great crackme!',
                'created_at': datetime.utcnow()
            },
            {
                'crackmeid': crackme_id,
                'author': 'user2',
                'content': 'Very challenging!',
                'created_at': datetime.utcnow()
            }
        ]
        for comment in comments:
            mock_db.comments.insert_one(comment)

        with patch('app.models.comment.get_db', return_value=mock_db):
            from app.models.comment import get_comments_for_crackme
            result = get_comments_for_crackme(str(crackme_id))
            assert len(result) == 2


class TestSolutionModel:
    """Tests for Solution model functions."""

    def test_get_solutions_for_crackme(self, mock_db):
        """Test getting solutions for a crackme."""
        crackme_id = ObjectId()
        solutions = [
            {
                'crackmeid': crackme_id,
                'author': 'solver1',
                'info': 'Used static analysis',
                'visible': True,
                'created_at': datetime.utcnow()
            }
        ]
        for solution in solutions:
            mock_db.solutions.insert_one(solution)

        with patch('app.models.solution.get_db', return_value=mock_db):
            from app.models.solution import get_solutions_for_crackme
            result = get_solutions_for_crackme(str(crackme_id))
            assert len(result) == 1
            assert result[0]['author'] == 'solver1'
