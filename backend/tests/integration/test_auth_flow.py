"""
Integration Tests for Authentication Flow

Tests complete authentication flows including:
- User registration → login → access protected routes
- Token refresh flow
- Logout and token blacklisting
- Invalid credentials handling
- Account status validation

These tests use real database connections and test the full stack
from HTTP request to database operations.
"""

import pytest
import json
from flask import Flask


class TestRegistrationFlow:
    """Test complete user registration flow"""

    def test_register_new_user(self, client, session):
        """Test successful user registration"""
        # Arrange
        user_data = {
            'first_name': 'Integration',
            'last_name': 'Test',
            'email': 'integration@example.com',
            'password': 'SecurePass123'
        }

        # Act
        response = client.post(
            '/api/auth/register',
            data=json.dumps(user_data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code == 201
        data = response.get_json()
        assert data['message'] == 'User registered successfully'
        assert 'user' in data
        assert data['user']['email'] == 'integration@example.com'
        assert data['user']['first_name'] == 'Integration'
        assert 'password_hash' not in data['user']  # Password should not be exposed

    def test_register_duplicate_email(self, client, session, test_user):
        """Test registration fails with duplicate email"""
        # Arrange
        user_data = {
            'first_name': 'Duplicate',
            'last_name': 'User',
            'email': test_user.email,  # Use existing user's email
            'password': 'SecurePass123'
        }

        # Act
        response = client.post(
            '/api/auth/register',
            data=json.dumps(user_data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code == 409
        data = response.get_json()
        assert 'error' in data
        assert 'already exists' in data['message'].lower()

    def test_register_invalid_email(self, client, session):
        """Test registration fails with invalid email"""
        # Arrange
        user_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'not-an-email',  # Invalid email
            'password': 'SecurePass123'
        }

        # Act
        response = client.post(
            '/api/auth/register',
            data=json.dumps(user_data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert 'validation_error' in data.get('error', '')

    def test_register_weak_password(self, client, session):
        """Test registration fails with weak password"""
        # Arrange
        user_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'test@example.com',
            'password': 'weak'  # Too short, no numbers
        }

        # Act
        response = client.post(
            '/api/auth/register',
            data=json.dumps(user_data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert 'password' in str(data.get('details', {}))


class TestLoginFlow:
    """Test complete user login flow"""

    def test_login_success(self, client, session, test_user):
        """Test successful login returns tokens"""
        # Arrange
        login_data = {
            'email': test_user.email,
            'password': 'TestPass123'
        }

        # Act
        response = client.post(
            '/api/auth/login',
            data=json.dumps(login_data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data['message'] == 'Login successful'
        assert 'access_token' in data
        assert 'refresh_token' in data
        assert 'user' in data
        assert data['user']['email'] == test_user.email
        assert 'tenants' in data  # List of user's tenants

    def test_login_invalid_email(self, client, session):
        """Test login fails with non-existent email"""
        # Arrange
        login_data = {
            'email': 'nonexistent@example.com',
            'password': '12345678'
        }

        # Act
        response = client.post(
            '/api/auth/login',
            data=json.dumps(login_data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code == 401
        data = response.get_json()
        assert 'invalid' in data['message'].lower()

    def test_login_wrong_password(self, client, session, test_user):
        """Test login fails with wrong password"""
        # Arrange
        login_data = {
            'email': test_user.email,
            'password': 'WrongP12345678'
        }

        # Act
        response = client.post(
            '/api/auth/login',
            data=json.dumps(login_data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code == 401
        data = response.get_json()
        assert 'invalid' in data['message'].lower()

    def test_login_inactive_account(self, client, session):
        """Test login fails with inactive account"""
        # Arrange - Create inactive user
        from app.models import User
        inactive_user = User(
            first_name='Inactive',
            last_name='User',
            email='inactive@example.com',
            is_active=False
        )
        inactive_user.set_password('12345678')
        session.add(inactive_user)
        session.commit()

        login_data = {
            'email': 'inactive@example.com',
            'password': '12345678'
        }

        # Act
        response = client.post(
            '/api/auth/login',
            data=json.dumps(login_data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code == 403
        data = response.get_json()
        assert 'inactive' in data['message'].lower() or 'deactivated' in data['message'].lower()


class TestProtectedRouteAccess:
    """Test accessing protected routes with JWT tokens"""

    def test_access_protected_route_with_valid_token(self, client, session, test_user, auth_headers):
        """Test accessing protected route with valid token"""
        # Act
        response = client.get(
            '/api/users/me',
            headers=auth_headers
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['email'] == test_user.email

    def test_access_protected_route_without_token(self, client, session):
        """Test accessing protected route without token fails"""
        # Act
        response = client.get('/api/users/me')

        # Assert
        assert response.status_code in [401, 422]  # Unauthorized or Unprocessable Entity

    def test_access_protected_route_with_invalid_token(self, client, session):
        """Test accessing protected route with invalid token fails"""
        # Arrange
        headers = {
            'Authorization': 'Bearer invalid_token_12345',
            'Content-Type': 'application/json'
        }

        # Act
        response = client.get('/api/users/me', headers=headers)

        # Assert
        assert response.status_code in [401, 422]


class TestTokenRefreshFlow:
    """Test token refresh functionality"""

    def test_refresh_token_success(self, client, session, test_user):
        """Test refreshing access token with valid refresh token"""
        # Arrange - First login to get tokens
        login_data = {
            'email': test_user.email,
            'password': 'TestPass123'
        }
        login_response = client.post(
            '/api/auth/login',
            data=json.dumps(login_data),
            content_type='application/json'
        )
        refresh_token = login_response.get_json()['refresh_token']

        # Act - Use refresh token to get new access token
        headers = {
            'Authorization': f'Bearer {refresh_token}',
            'Content-Type': 'application/json'
        }
        response = client.post('/api/auth/refresh', headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert 'access_token' in data
        # New access token should be different from refresh token
        assert data['access_token'] != refresh_token


class TestLogoutFlow:
    """Test logout and token blacklisting"""

    def test_logout_success(self, client, session, test_user, auth_headers):
        """Test successful logout"""
        # Act
        response = client.post(
            '/api/auth/logout',
            headers=auth_headers
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert 'Logged out successfully' in data['message']

    def test_access_after_logout(self, client, session, test_user):
        """Test that token cannot be used after logout"""
        # Arrange - Login and then logout
        login_data = {
            'email': test_user.email,
            'password': 'TestPass123'
        }
        login_response = client.post(
            '/api/auth/login',
            data=json.dumps(login_data),
            content_type='application/json'
        )
        access_token = login_response.get_json()['access_token']

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        # Logout
        client.post('/api/auth/logout', headers=headers)

        # Act - Try to use token after logout
        response = client.get('/api/users/me', headers=headers)

        # Assert - Token should be blacklisted
        assert response.status_code in [401, 422]


class TestCompleteAuthFlow:
    """Test complete authentication flow from registration to protected access"""

    def test_complete_flow_register_login_access(self, client, session):
        """Test: Register → Login → Access protected route"""
        # Step 1: Register
        register_data = {
            'first_name': 'Complete',
            'last_name': 'Flow',
            'email': 'complete.flow@example.com',
            'password': 'SecurePass123'
        }
        register_response = client.post(
            '/api/auth/register',
            data=json.dumps(register_data),
            content_type='application/json'
        )
        assert register_response.status_code == 201

        # Step 2: Login with new account
        login_data = {
            'email': 'complete.flow@example.com',
            'password': 'SecurePass123'
        }
        login_response = client.post(
            '/api/auth/login',
            data=json.dumps(login_data),
            content_type='application/json'
        )
        assert login_response.status_code == 200
        tokens = login_response.get_json()
        access_token = tokens['access_token']

        # Step 3: Access protected route
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        profile_response = client.get('/api/users/me', headers=headers)
        assert profile_response.status_code == 200
        profile_data = profile_response.get_json()
        assert profile_data['data']['email'] == 'complete.flow@example.com'

    def test_complete_flow_with_token_refresh(self, client, session):
        """Test: Register → Login → Refresh token → Access with new token"""
        # Step 1: Register
        register_data = {
            'first_name': 'Refresh',
            'last_name': 'Test',
            'email': 'refresh.test@example.com',
            'password': 'SecurePass123'
        }
        client.post(
            '/api/auth/register',
            data=json.dumps(register_data),
            content_type='application/json'
        )

        # Step 2: Login
        login_data = {
            'email': 'refresh.test@example.com',
            'password': 'SecurePass123'
        }
        login_response = client.post(
            '/api/auth/login',
            data=json.dumps(login_data),
            content_type='application/json'
        )
        tokens = login_response.get_json()
        refresh_token = tokens['refresh_token']

        # Step 3: Refresh access token
        refresh_headers = {
            'Authorization': f'Bearer {refresh_token}',
            'Content-Type': 'application/json'
        }
        refresh_response = client.post('/api/auth/refresh', headers=refresh_headers)
        assert refresh_response.status_code == 200
        new_access_token = refresh_response.get_json()['access_token']

        # Step 4: Access protected route with new token
        access_headers = {
            'Authorization': f'Bearer {new_access_token}',
            'Content-Type': 'application/json'
        }
        profile_response = client.get('/api/users/me', headers=access_headers)
        assert profile_response.status_code == 200
        assert profile_response.get_json()['data']['email'] == 'refresh.test@example.com'
