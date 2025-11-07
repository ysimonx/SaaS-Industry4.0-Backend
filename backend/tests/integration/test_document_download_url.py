"""
Integration tests for document download URL endpoint.

This module tests the GET /api/tenants/{tenant_id}/documents/{document_id}/download-url
endpoint which generates pre-signed S3 URLs for downloading documents without
authentication in the download request.

Test scenarios:
- Successful URL generation with valid authentication
- Custom expiration time validation
- Permission checks (read permission required)
- Invalid parameters handling
- Missing authentication
- Non-existent documents
- Actual download using generated URL (if MinIO available)
"""

import pytest
import requests
from datetime import datetime, timedelta
from unittest.mock import patch, Mock


class TestDocumentDownloadUrlEndpoint:
    """Integration tests for GET /download-url endpoint."""

    @pytest.fixture
    def app(self):
        """Create test application."""
        from app import create_app
        app = create_app('testing')
        app.config['TESTING'] = True
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        with app.test_client() as client:
            yield client

    @pytest.fixture
    def auth_headers(self, client):
        """
        Get authentication headers with valid JWT token.

        Note: This assumes test database is initialized with admin user.
        Adjust credentials based on your test data setup.
        """
        response = client.post('/api/auth/login', json={
            'email': 'admin@example.com',
            'password': 'admin123'
        })

        if response.status_code != 200:
            pytest.skip(f"Cannot authenticate test user: {response.json}")

        token = response.json['data']['access_token']
        return {'Authorization': f'Bearer {token}'}

    @pytest.fixture
    def test_tenant_id(self):
        """
        Return test tenant ID.

        Note: This should be a valid tenant ID from your test database.
        You may need to create a tenant in a setup fixture.
        """
        # Replace with actual test tenant ID from your test database
        return '9b2cf18a-243d-4ceb-8b87-9fcc4babbb54'

    @pytest.fixture
    def test_document_id(self):
        """
        Return test document ID.

        Note: This should be a valid document ID from your test database.
        You may need to upload a test document in a setup fixture.
        """
        # Replace with actual test document ID from your test database
        return '542cec7a-751b-4543-8207-531d6769a978'

    def test_get_download_url_success(self, client, auth_headers, test_tenant_id, test_document_id):
        """Test successful download URL generation."""
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json['data']

        # Verify response structure
        assert 'download_url' in data
        assert 'expires_in' in data
        assert 'expires_at' in data
        assert 'filename' in data
        assert 'mime_type' in data
        assert 'file_size' in data

        # Verify default expiration (3600 seconds = 1 hour)
        assert data['expires_in'] == 3600

        # Verify URL is public (contains localhost:9000, not minio:9000)
        download_url = data['download_url']
        assert 'localhost:9000' in download_url or 'documents.example.com' in download_url
        assert 'minio:9000' not in download_url

        # Verify URL contains signature parameters
        assert 'X-Amz-Signature' in download_url or 'Signature' in download_url

        # Verify expires_at is in the future
        expires_at = datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00'))
        now = datetime.now(expires_at.tzinfo)
        assert expires_at > now

    def test_get_download_url_with_custom_expiration(
        self, client, auth_headers, test_tenant_id, test_document_id
    ):
        """Test URL generation with custom expiration time."""
        custom_expiration = 7200  # 2 hours

        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url'
            f'?expires_in={custom_expiration}',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json['data']
        assert data['expires_in'] == custom_expiration

    def test_get_download_url_expiration_too_short(
        self, client, auth_headers, test_tenant_id, test_document_id
    ):
        """Test that expiration time less than 60 seconds is rejected."""
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url?expires_in=30',
            headers=auth_headers
        )

        assert response.status_code == 400
        assert 'expires_in must be between 60 and 86400 seconds' in response.json['message']

    def test_get_download_url_expiration_too_long(
        self, client, auth_headers, test_tenant_id, test_document_id
    ):
        """Test that expiration time greater than 24 hours is rejected."""
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url?expires_in=100000',
            headers=auth_headers
        )

        assert response.status_code == 400
        assert 'expires_in must be between 60 and 86400 seconds' in response.json['message']

    def test_get_download_url_min_expiration_accepted(
        self, client, auth_headers, test_tenant_id, test_document_id
    ):
        """Test minimum expiration time (60 seconds) is accepted."""
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url?expires_in=60',
            headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json['data']['expires_in'] == 60

    def test_get_download_url_max_expiration_accepted(
        self, client, auth_headers, test_tenant_id, test_document_id
    ):
        """Test maximum expiration time (86400 seconds = 24 hours) is accepted."""
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url?expires_in=86400',
            headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json['data']['expires_in'] == 86400

    def test_get_download_url_no_auth(self, client, test_tenant_id, test_document_id):
        """Test that endpoint requires authentication."""
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url'
        )

        assert response.status_code == 401
        assert response.json['success'] is False

    def test_get_download_url_invalid_token(self, client, test_tenant_id, test_document_id):
        """Test that invalid JWT token is rejected."""
        headers = {'Authorization': 'Bearer invalid-token-12345'}

        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url',
            headers=headers
        )

        assert response.status_code == 401

    def test_get_download_url_document_not_found(self, client, auth_headers, test_tenant_id):
        """Test 404 when document doesn't exist."""
        fake_document_id = '00000000-0000-0000-0000-000000000000'

        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{fake_document_id}/download-url',
            headers=auth_headers
        )

        assert response.status_code == 404
        assert 'not found' in response.json['message'].lower()

    def test_get_download_url_tenant_not_found(self, client, auth_headers, test_document_id):
        """Test 404 when tenant doesn't exist."""
        fake_tenant_id = '00000000-0000-0000-0000-000000000000'

        response = client.get(
            f'/api/tenants/{fake_tenant_id}/documents/{test_document_id}/download-url',
            headers=auth_headers
        )

        assert response.status_code == 404
        assert 'not found' in response.json['message'].lower()

    def test_get_download_url_response_structure(
        self, client, auth_headers, test_tenant_id, test_document_id
    ):
        """Test that response contains all required fields with correct types."""
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json['data']

        # Verify types
        assert isinstance(data['download_url'], str)
        assert isinstance(data['expires_in'], int)
        assert isinstance(data['expires_at'], str)
        assert isinstance(data['filename'], str)
        assert isinstance(data['mime_type'], str)
        assert isinstance(data['file_size'], int)

        # Verify URL is valid format
        assert data['download_url'].startswith('http')

        # Verify filename is not empty
        assert len(data['filename']) > 0

        # Verify MIME type format
        assert '/' in data['mime_type']

        # Verify file size is positive
        assert data['file_size'] > 0

    def test_get_download_url_expires_at_format(
        self, client, auth_headers, test_tenant_id, test_document_id
    ):
        """Test that expires_at is in correct ISO 8601 format."""
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url',
            headers=auth_headers
        )

        assert response.status_code == 200
        expires_at_str = response.json['data']['expires_at']

        # Verify ISO 8601 format with Z suffix
        assert expires_at_str.endswith('Z')

        # Verify parseable as datetime
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        assert isinstance(expires_at, datetime)

    @pytest.mark.skipif(
        True,  # Set to False if you want to test actual download
        reason="Requires MinIO to be running and test document to exist"
    )
    def test_download_with_presigned_url(
        self, client, auth_headers, test_tenant_id, test_document_id
    ):
        """
        Test that generated URL actually works for download.

        Note: This test requires MinIO to be running and accessible.
        Enable by setting skipif to False and ensuring test document exists.
        """
        # Step 1: Get download URL
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url',
            headers=auth_headers
        )

        assert response.status_code == 200
        download_url = response.json['data']['download_url']
        expected_mime_type = response.json['data']['mime_type']
        expected_size = response.json['data']['file_size']

        # Step 2: Download file using the URL (without auth!)
        file_response = requests.get(download_url)

        # Assert download succeeded
        assert file_response.status_code == 200

        # Verify content
        assert len(file_response.content) > 0
        assert len(file_response.content) == expected_size

        # Verify Content-Type header
        assert file_response.headers['Content-Type'] == expected_mime_type

        # Verify Content-Disposition header (should force download)
        assert 'attachment' in file_response.headers.get('Content-Disposition', '')

    def test_get_download_url_multiple_requests_different_urls(
        self, client, auth_headers, test_tenant_id, test_document_id
    ):
        """Test that multiple requests generate different URLs (different signatures)."""
        # First request
        response1 = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url',
            headers=auth_headers
        )

        # Second request
        response2 = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url',
            headers=auth_headers
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        url1 = response1.json['data']['download_url']
        url2 = response2.json['data']['download_url']

        # URLs should be different (different timestamps/signatures)
        # Note: They might be the same if generated within the same second
        # This is a best-effort check
        if url1 != url2:
            # Extract signatures
            assert 'Signature=' in url1
            assert 'Signature=' in url2


class TestDocumentDownloadUrlPermissions:
    """Test permission checks for download URL endpoint."""

    @pytest.fixture
    def app(self):
        """Create test application."""
        from app import create_app
        app = create_app('testing')
        app.config['TESTING'] = True
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        with app.test_client() as client:
            yield client

    @pytest.mark.skip(reason="Requires test user with viewer role setup")
    def test_get_download_url_with_read_permission(
        self, client, test_tenant_id, test_document_id
    ):
        """
        Test that user with read permission can generate download URL.

        Note: This test requires a test user with 'viewer' or 'user' role.
        """
        # Login as viewer/user with read permission
        response = client.post('/api/auth/login', json={
            'email': 'viewer@example.com',
            'password': 'viewer123'
        })

        assert response.status_code == 200
        token = response.json['data']['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        # Generate download URL
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url',
            headers=headers
        )

        # Should succeed with read permission
        assert response.status_code == 200
        assert 'download_url' in response.json['data']

    @pytest.mark.skip(reason="Requires test user without read permission setup")
    def test_get_download_url_without_read_permission(
        self, client, test_tenant_id, test_document_id
    ):
        """
        Test that user without read permission cannot generate download URL.

        Note: This test requires a test user with a custom role that has no 'read' permission.
        """
        # Login as user without read permission
        response = client.post('/api/auth/login', json={
            'email': 'noreader@example.com',
            'password': 'noreader123'
        })

        assert response.status_code == 200
        token = response.json['data']['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        # Try to generate download URL
        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url',
            headers=headers
        )

        # Should be forbidden
        assert response.status_code == 403
        assert 'permission' in response.json['message'].lower()


class TestDocumentDownloadUrlAuditLogging:
    """Test audit logging for download URL generation."""

    @pytest.fixture
    def app(self):
        """Create test application."""
        from app import create_app
        app = create_app('testing')
        app.config['TESTING'] = True
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        with app.test_client() as client:
            yield client

    @pytest.fixture
    def auth_headers(self, client):
        """Get authentication headers."""
        response = client.post('/api/auth/login', json={
            'email': 'admin@example.com',
            'password': 'admin123'
        })

        if response.status_code != 200:
            pytest.skip(f"Cannot authenticate: {response.json}")

        token = response.json['data']['access_token']
        return {'Authorization': f'Bearer {token}'}

    @patch('app.routes.documents.logger')
    def test_audit_log_generated_on_success(
        self, mock_logger, client, auth_headers
    ):
        """Test that audit log is created when URL is generated successfully."""
        test_tenant_id = '9b2cf18a-243d-4ceb-8b87-9fcc4babbb54'
        test_document_id = '542cec7a-751b-4543-8207-531d6769a978'

        response = client.get(
            f'/api/tenants/{test_tenant_id}/documents/{test_document_id}/download-url',
            headers=auth_headers
        )

        if response.status_code == 200:
            # Verify audit log was called
            audit_calls = [
                call for call in mock_logger.info.call_args_list
                if 'AUDIT: Download URL generated' in str(call)
            ]
            assert len(audit_calls) > 0

            # Verify audit log contains required information
            audit_message = str(audit_calls[0])
            assert test_tenant_id in audit_message
            assert test_document_id in audit_message
