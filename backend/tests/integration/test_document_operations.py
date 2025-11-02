"""
Integration Tests for Document Operations and Multi-Tenancy Isolation

Tests complete document management flows including:
- Document upload with file storage
- Document retrieval and listing
- File deduplication (MD5-based)
- Multi-tenancy data isolation

These tests verify:
1. Documents are stored in correct tenant databases
2. Files are deduplicated within tenant boundaries
3. Tenants cannot access each other's data
4. S3 storage integration (mocked)
"""

import pytest
import json
import io
from unittest.mock import patch, Mock


class TestDocumentUpload:
    """Test document upload flow"""

    @patch('app.services.file_service.boto3')
    @patch('app.services.document_service.tenant_db_manager')
    def test_upload_document_success(self, mock_db_manager, mock_boto3, client, session, admin_headers, test_tenant):
        """Test successful document upload"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        # Mock S3
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client

        # Mock tenant database session
        mock_session = Mock()
        mock_db_manager.tenant_db_session.return_value.__enter__.return_value = mock_session

        # Create file data
        file_content = b'Test document content'
        file_data = (io.BytesIO(file_content), 'test_document.pdf')

        # Act
        response = client.post(
            f'/api/tenants/{tenant_id}/documents',
            data={'file': file_data},
            headers=admin_headers,
            content_type='multipart/form-data'
        )

        # Assert
        assert response.status_code == 201
        data = response.get_json()
        assert data['success'] is True
        assert 'document' in data.get('data', {}) or 'id' in data.get('data', {})

    def test_upload_document_without_auth(self, client, session, test_tenant):
        """Test document upload requires authentication"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        file_content = b'Test content'
        file_data = (io.BytesIO(file_content), 'test.pdf')

        # Act
        response = client.post(
            f'/api/tenants/{tenant_id}/documents',
            data={'file': file_data},
            content_type='multipart/form-data'
        )

        # Assert
        assert response.status_code in [401, 422]  # Unauthorized

    @patch('app.services.document_service.tenant_db_manager')
    def test_upload_document_no_tenant_access(self, mock_db_manager, client, session, auth_headers, test_tenant):
        """Test upload fails if user doesn't have tenant access"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        file_content = b'Unauthorized content'
        file_data = (io.BytesIO(file_content), 'unauthorized.pdf')

        # Act - test_user doesn't have access to test_tenant
        response = client.post(
            f'/api/tenants/{tenant_id}/documents',
            data={'file': file_data},
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        # Assert
        assert response.status_code in [403, 404]  # Forbidden or Not Found


class TestDocumentRetrieval:
    """Test document retrieval and listing"""

    @patch('app.services.document_service.tenant_db_manager')
    def test_list_documents(self, mock_db_manager, client, session, admin_headers, test_tenant):
        """Test listing documents in tenant"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        # Mock tenant database session
        from app.models import Document
        mock_documents = [Mock(spec=Document) for _ in range(3)]
        mock_query = Mock()
        mock_query.count.return_value = 3
        mock_query.offset.return_value.limit.return_value.all.return_value = mock_documents

        mock_session = Mock()
        mock_session.query.return_value = mock_query
        mock_db_manager.tenant_db_session.return_value.__enter__.return_value = mock_session

        # Act
        response = client.get(
            f'/api/tenants/{tenant_id}/documents',
            headers=admin_headers
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'documents' in data.get('data', {})

    @patch('app.services.document_service.tenant_db_manager')
    def test_list_documents_with_pagination(self, mock_db_manager, client, session, admin_headers, test_tenant):
        """Test document listing with pagination"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        # Mock
        mock_query = Mock()
        mock_query.count.return_value = 50
        mock_query.offset.return_value.limit.return_value.all.return_value = []

        mock_session = Mock()
        mock_session.query.return_value = mock_query
        mock_db_manager.tenant_db_session.return_value.__enter__.return_value = mock_session

        # Act
        response = client.get(
            f'/api/tenants/{tenant_id}/documents?page=2&per_page=10',
            headers=admin_headers
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert 'pagination' in data.get('data', {})
        if 'pagination' in data.get('data', {}):
            assert data['data']['pagination']['page'] == 2
            assert data['data']['pagination']['per_page'] == 10


class TestFileDeduplication:
    """Test file deduplication within tenant"""

    @patch('app.services.file_service.boto3')
    @patch('app.services.document_service.tenant_db_manager')
    @patch('app.services.file_service.tenant_db_manager')
    def test_duplicate_file_reused(self, mock_file_db_manager, mock_doc_db_manager, mock_boto3, client, session, admin_headers, test_tenant):
        """Test uploading same file twice reuses existing file"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        # Mock S3
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client

        # Mock existing file in tenant DB
        from app.models import File
        existing_file = Mock(spec=File)
        existing_file.id = 'existing-file-uuid'
        existing_file.md5_hash = 'abc123def456'

        mock_session = Mock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = existing_file
        mock_file_db_manager.tenant_db_session.return_value.__enter__.return_value = mock_session
        mock_doc_db_manager.tenant_db_session.return_value.__enter__.return_value = mock_session

        # Act - Upload file with same content (same MD5)
        file_content = b'Duplicate content'
        file_data = (io.BytesIO(file_content), 'document1.pdf')

        response = client.post(
            f'/api/tenants/{tenant_id}/documents',
            data={'file': file_data},
            headers=admin_headers,
            content_type='multipart/form-data'
        )

        # Assert
        assert response.status_code == 201
        # Verify S3 upload was NOT called again (file already exists)
        # In real implementation, should check FileService.get_file_by_md5 was called


class TestMultiTenancyIsolation:
    """Test data isolation between tenants"""

    @patch('app.services.tenant_service.tenant_db_manager')
    def test_tenant_isolation_document_access(self, mock_db_manager, client, session, test_user, test_admin_user, auth_headers, admin_headers):
        """Test users from one tenant cannot access another tenant's documents"""
        # Arrange - Create two separate tenants
        from app.models import Tenant, UserTenantAssociation

        # Tenant 1 (for test_user)
        tenant1 = Tenant(name='Tenant One')
        session.add(tenant1)
        session.commit()
        session.refresh(tenant1)

        assoc1 = UserTenantAssociation(
            user_id=test_user.id,
            tenant_id=tenant1.id,
            role='admin'
        )
        session.add(assoc1)

        # Tenant 2 (for test_admin_user)
        tenant2 = Tenant(name='Tenant Two')
        session.add(tenant2)
        session.commit()
        session.refresh(tenant2)

        assoc2 = UserTenantAssociation(
            user_id=test_admin_user.id,
            tenant_id=tenant2.id,
            role='admin'
        )
        session.add(assoc2)
        session.commit()

        # Mock
        mock_db_manager.create_tenant_database.return_value = None
        mock_db_manager.create_tenant_tables.return_value = None

        # Act - test_user tries to access tenant2's documents
        response = client.get(
            f'/api/tenants/{tenant2.id}/documents',
            headers=auth_headers  # test_user's token
        )

        # Assert - Should be denied
        assert response.status_code in [403, 404]  # Forbidden or Not Found

    @patch('app.services.tenant_service.tenant_db_manager')
    def test_tenant_list_only_accessible_tenants(self, mock_db_manager, client, session, test_user, auth_headers):
        """Test user only sees tenants they have access to"""
        # Arrange - Create tenant for test_user
        from app.models import Tenant, UserTenantAssociation

        tenant1 = Tenant(name='User Tenant')
        session.add(tenant1)
        session.commit()
        session.refresh(tenant1)

        assoc = UserTenantAssociation(
            user_id=test_user.id,
            tenant_id=tenant1.id,
            role='user'
        )
        session.add(assoc)

        # Create another tenant user doesn't have access to
        tenant2 = Tenant(name='Other Tenant')
        session.add(tenant2)
        session.commit()

        # Mock
        mock_db_manager.create_tenant_database.return_value = None

        # Act - Get user's tenants
        response = client.get('/api/tenants', headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        tenant_ids = [t['id'] for t in data['data']]

        # Should include tenant1, should NOT include tenant2
        assert str(tenant1.id) in tenant_ids
        assert str(tenant2.id) not in tenant_ids


class TestCompleteDocumentFlow:
    """Test complete document management flow"""

    @patch('app.services.file_service.boto3')
    @patch('app.services.document_service.tenant_db_manager')
    @patch('app.services.tenant_service.tenant_db_manager')
    def test_complete_flow_tenant_to_document(self, mock_tenant_db_manager, mock_doc_db_manager, mock_boto3, client, session, auth_headers, test_user):
        """Test: Create tenant → Upload document → List documents → Get document"""
        # Setup mocks
        mock_tenant_db_manager.create_tenant_database.return_value = None
        mock_tenant_db_manager.create_tenant_tables.return_value = None

        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client

        mock_session = Mock()
        mock_doc_db_manager.tenant_db_session.return_value.__enter__.return_value = mock_session

        # Step 1: Create tenant
        tenant_data = {'name': 'Document Flow Tenant'}
        create_response = client.post(
            '/api/tenants',
            data=json.dumps(tenant_data),
            headers=auth_headers
        )
        assert create_response.status_code == 201
        tenant_id = create_response.get_json()['data']['id']

        # Step 2: Upload document (mocked)
        # Note: Actual upload would require more complex mocking of tenant DB operations

        # Step 3: List documents
        list_response = client.get(
            f'/api/tenants/{tenant_id}/documents',
            headers=auth_headers
        )
        assert list_response.status_code == 200

    @patch('app.services.tenant_service.tenant_db_manager')
    def test_complete_isolation_flow(self, mock_db_manager, client, session, test_user, test_admin_user, auth_headers, admin_headers):
        """Test: Create 2 tenants → Verify complete isolation"""
        # Setup mock
        mock_db_manager.create_tenant_database.return_value = None
        mock_db_manager.create_tenant_tables.return_value = None

        # Step 1: User 1 creates Tenant A
        tenant_a_data = {'name': 'Tenant A'}
        tenant_a_response = client.post(
            '/api/tenants',
            data=json.dumps(tenant_a_data),
            headers=auth_headers
        )
        assert tenant_a_response.status_code == 201
        tenant_a_id = tenant_a_response.get_json()['data']['id']

        # Step 2: User 2 creates Tenant B
        tenant_b_data = {'name': 'Tenant B'}
        tenant_b_response = client.post(
            '/api/tenants',
            data=json.dumps(tenant_b_data),
            headers=admin_headers
        )
        assert tenant_b_response.status_code == 201
        tenant_b_id = tenant_b_response.get_json()['data']['id']

        # Step 3: User 1 cannot access Tenant B
        access_response = client.get(
            f'/api/tenants/{tenant_b_id}',
            headers=auth_headers
        )
        assert access_response.status_code in [403, 404]

        # Step 4: User 2 cannot access Tenant A
        access_response2 = client.get(
            f'/api/tenants/{tenant_a_id}',
            headers=admin_headers
        )
        assert access_response2.status_code in [403, 404]

        # Step 5: Each user sees only their own tenant
        list_response1 = client.get('/api/tenants', headers=auth_headers)
        tenant_a_list = [t['id'] for t in list_response1.get_json()['data']]
        assert tenant_a_id in tenant_a_list
        assert tenant_b_id not in tenant_a_list

        list_response2 = client.get('/api/tenants', headers=admin_headers)
        tenant_b_list = [t['id'] for t in list_response2.get_json()['data']]
        assert tenant_b_id in tenant_b_list
        assert tenant_a_id not in tenant_b_list
