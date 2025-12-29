"""
Unit tests for Flask routes.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestPublicRoutes:
    """Tests for public routes that don't require authentication."""

    def test_index_page(self, client):
        """Test the index page loads."""
        with patch('app.models.user.count_users', return_value=100):
            with patch('app.models.crackme.count_crackmes', return_value=500):
                with patch('app.models.solution.count_solutions', return_value=200):
                    response = client.get('/')
                    assert response.status_code == 200

    def test_faq_page(self, client):
        """Test the FAQ page loads."""
        response = client.get('/faq')
        assert response.status_code == 200
        assert b'FAQ' in response.data or b'Frequently Asked Questions' in response.data

    def test_crackme_rules_page(self, client):
        """Test the crackme rules page loads."""
        response = client.get('/upload/crackmerules')
        assert response.status_code == 200
        assert b'Crackme' in response.data

    def test_writeup_rules_page(self, client):
        """Test the writeup rules page loads."""
        response = client.get('/upload/writeuprules')
        assert response.status_code == 200
        assert b'Writeup' in response.data or b'Rules' in response.data

    def test_login_page(self, client):
        """Test the login page loads."""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'Login' in response.data or b'login' in response.data

    def test_register_page(self, client):
        """Test the register page loads."""
        response = client.get('/register')
        assert response.status_code == 200
        assert b'Register' in response.data or b'register' in response.data

    def test_search_page(self, client):
        """Test the search page loads."""
        response = client.get('/search')
        assert response.status_code == 200
        assert b'Search' in response.data or b'search' in response.data

    def test_lasts_page(self, client):
        """Test the latest crackmes page loads."""
        with patch('app.models.crackme.get_last_crackmes', return_value=[]):
            response = client.get('/lasts/1')
            assert response.status_code == 200

    def test_404_page(self, client):
        """Test 404 page for non-existent routes."""
        response = client.get('/nonexistent-page-12345')
        assert response.status_code == 404


class TestAuthRoutes:
    """Tests for authentication routes."""

    def test_login_post_empty_fields(self, client):
        """Test login with empty fields."""
        response = client.post('/login', data={
            'name': '',
            'password': ''
        })
        # Should either redirect or show error
        assert response.status_code in [200, 302, 400]

    def test_login_post_invalid_user(self, client):
        """Test login with invalid user."""
        with patch('app.models.user.user_by_name', return_value=None):
            response = client.post('/login', data={
                'name': 'nonexistent',
                'password': 'password123'
            })
            assert response.status_code in [200, 302]

    def test_register_post_empty_fields(self, client):
        """Test register with empty fields."""
        response = client.post('/register', data={
            'name': '',
            'email': '',
            'password': '',
            'password_verify': ''
        })
        assert response.status_code in [200, 302, 400]

    def test_register_post_password_mismatch(self, client):
        """Test register with mismatched passwords."""
        response = client.post('/register', data={
            'name': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'password_verify': 'different'
        })
        assert response.status_code in [200, 302]

    def test_logout_redirects(self, client):
        """Test logout redirects to index."""
        response = client.get('/logout')
        assert response.status_code in [302, 303]


class TestProtectedRoutes:
    """Tests for routes that require authentication."""

    def test_upload_crackme_requires_auth(self, client):
        """Test that upload crackme page requires authentication."""
        response = client.get('/upload/crackme')
        # Should redirect to login
        assert response.status_code in [302, 303, 401]

    def test_notifications_requires_auth(self, client):
        """Test that notifications page requires authentication."""
        response = client.get('/notifications')
        # Should redirect to login
        assert response.status_code in [302, 303, 401]

    def test_change_password_requires_auth(self, client):
        """Test that change password page requires authentication."""
        response = client.get('/change-password')
        # Should redirect to login
        assert response.status_code in [302, 303, 401]


class TestCrackmeRoutes:
    """Tests for crackme-related routes."""

    def test_view_crackme_not_found(self, client):
        """Test viewing a non-existent crackme."""
        with patch('app.models.crackme.crackme_by_hexid', return_value=None):
            response = client.get('/crackme/507f1f77bcf86cd799439011')
            assert response.status_code == 404

    def test_view_crackme_invalid_id(self, client):
        """Test viewing a crackme with invalid ID."""
        response = client.get('/crackme/invalid-id')
        assert response.status_code in [400, 404]


class TestUserRoutes:
    """Tests for user profile routes."""

    def test_view_user_not_found(self, client):
        """Test viewing a non-existent user profile."""
        with patch('app.models.user.user_by_name', return_value=None):
            with patch('app.models.crackme.get_crackmes_by_author', return_value=[]):
                with patch('app.models.solution.get_solutions_by_author', return_value=[]):
                    with patch('app.models.comment.get_comments_by_author', return_value=[]):
                        response = client.get('/user/nonexistent')
                        assert response.status_code in [200, 404]
