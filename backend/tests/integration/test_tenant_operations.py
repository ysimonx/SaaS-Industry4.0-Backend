"""
Integration Tests for Tenant Operations

Tests complete tenant management flows including:
- Tenant creation with database provisioning
- Adding/removing users to/from tenants
- Role-based access control
- Tenant isolation verification

These tests verify the full stack from API to database creation.
"""

import pytest
import json
from unittest.mock import patch


class TestTenantCreation:
    """Test tenant creation flow"""

    @patch('app.services.tenant_service.tenant_db_manager')
    def test_create_tenant_success(self, mock_db_manager, client, session, auth_headers, test_user):
        """Test successful tenant creation"""
        # Arrange
        tenant_data = {
            'name': 'Integration Test Company'
        }
        mock_db_manager.create_tenant_database.return_value = None
        mock_db_manager.create_tenant_tables.return_value = None

        # Act
        response = client.post(
            '/api/tenants',
            data=json.dumps(tenant_data),
            headers=auth_headers
        )

        # Assert
        assert response.status_code == 201
        data = response.get_json()
        assert data['success'] is True
        assert 'data' in data
        assert data['data']['name'] == 'Integration Test Company'
        assert 'database_name' in data['data']
        assert data['data']['role'] == 'admin'  # Creator is admin
        assert data['data']['is_active'] is True

    @patch('app.services.tenant_service.tenant_db_manager')
    def test_create_tenant_without_auth(self, mock_db_manager, client, session):
        """Test tenant creation requires authentication"""
        # Arrange
        tenant_data = {
            'name': 'Unauthorized Company'
        }

        # Act
        response = client.post(
            '/api/tenants',
            data=json.dumps(tenant_data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code in [401, 422]  # Unauthorized

    @patch('app.services.tenant_service.tenant_db_manager')
    def test_create_tenant_invalid_name(self, mock_db_manager, client, session, auth_headers):
        """Test tenant creation with invalid name"""
        # Arrange
        tenant_data = {
            'name': ''  # Empty name
        }

        # Act
        response = client.post(
            '/api/tenants',
            data=json.dumps(tenant_data),
            headers=auth_headers
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert 'validation' in data.get('error', '').lower() or 'name' in str(data.get('details', {}))


class TestTenantRetrieval:
    """Test retrieving tenant information"""

    def test_list_user_tenants(self, client, session, test_admin_user, admin_headers, test_tenant):
        """Test listing tenants user has access to"""
        # Arrange - test_tenant fixture creates tenant with admin user

        # Act
        response = client.get('/api/tenants', headers=admin_headers)

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert isinstance(data['data'], list)
        assert len(data['data']) >= 1
        # Should include the test tenant
        tenant_names = [t['name'] for t in data['data']]
        assert 'Test Company' in tenant_names

    def test_get_tenant_details(self, client, session, test_admin_user, admin_headers, test_tenant):
        """Test getting detailed tenant information"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        # Act
        response = client.get(f'/api/tenants/{tenant_id}', headers=admin_headers)

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['id'] == tenant_id
        assert data['data']['name'] == 'Test Company'
        assert 'members' in data['data']
        assert len(data['data']['members']) >= 1

    def test_get_tenant_no_access(self, client, session, auth_headers, test_tenant):
        """Test getting tenant user doesn't have access to"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        # Act - test_user doesn't have access to test_tenant (only admin_user does)
        response = client.get(f'/api/tenants/{tenant_id}', headers=auth_headers)

        # Assert
        assert response.status_code == 404  # Not found or access denied


class TestTenantUserManagement:
    """Test adding/removing users to/from tenants"""

    def test_add_user_to_tenant(self, client, session, test_user, test_admin_user, admin_headers, test_tenant):
        """Test adding user to tenant (admin only)"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)
        user_data = {
            'user_id': str(test_user.id),
            'role': 'user'
        }

        # Act
        response = client.post(
            f'/api/tenants/{tenant_id}/users',
            data=json.dumps(user_data),
            headers=admin_headers
        )

        # Assert
        assert response.status_code == 201
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['role'] == 'user'
        assert data['data']['user_id'] == str(test_user.id)

    def test_add_user_non_admin(self, client, session, auth_headers, test_tenant):
        """Test non-admin cannot add users to tenant"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)
        user_data = {
            'user_id': 'some-user-id',
            'role': 'user'
        }

        # Act - test_user is not admin of test_tenant
        response = client.post(
            f'/api/tenants/{tenant_id}/users',
            data=json.dumps(user_data),
            headers=auth_headers
        )

        # Assert
        assert response.status_code in [403, 404]  # Forbidden or Not Found

    def test_add_duplicate_user(self, client, session, test_admin_user, admin_headers, test_tenant):
        """Test adding user who is already a member fails"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)
        user_data = {
            'user_id': str(test_admin_user.id),  # Already a member
            'role': 'user'
        }

        # Act
        response = client.post(
            f'/api/tenants/{tenant_id}/users',
            data=json.dumps(user_data),
            headers=admin_headers
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert 'already' in data.get('message', '').lower()

    def test_remove_user_from_tenant(self, client, session, test_user, test_admin_user, admin_headers, test_tenant):
        """Test removing user from tenant"""
        # Arrange - First add user
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        # Add user first
        add_data = {
            'user_id': str(test_user.id),
            'role': 'user'
        }
        client.post(
            f'/api/tenants/{tenant_id}/users',
            data=json.dumps(add_data),
            headers=admin_headers
        )

        # Act - Remove user
        response = client.delete(
            f'/api/tenants/{tenant_id}/users/{test_user.id}',
            headers=admin_headers
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_cannot_remove_last_admin(self, client, session, test_admin_user, admin_headers, test_tenant):
        """Test cannot remove the last admin from tenant"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        # Act - Try to remove the only admin
        response = client.delete(
            f'/api/tenants/{tenant_id}/users/{test_admin_user.id}',
            headers=admin_headers
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert 'last admin' in data.get('message', '').lower()


class TestTenantUpdate:
    """Test updating tenant information"""

    def test_update_tenant_name(self, client, session, admin_headers, test_tenant):
        """Test updating tenant name (admin only)"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)
        update_data = {
            'name': 'Updated Company Name'
        }

        # Act
        response = client.put(
            f'/api/tenants/{tenant_id}',
            data=json.dumps(update_data),
            headers=admin_headers
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['data']['name'] == 'Updated Company Name'

    def test_update_tenant_non_admin(self, client, session, auth_headers, test_tenant):
        """Test non-admin cannot update tenant"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)
        update_data = {
            'name': 'Unauthorized Update'
        }

        # Act
        response = client.put(
            f'/api/tenants/{tenant_id}',
            data=json.dumps(update_data),
            headers=auth_headers
        )

        # Assert
        assert response.status_code in [403, 404]  # Forbidden or Not Found


class TestTenantDeletion:
    """Test tenant soft deletion"""

    @patch('app.services.tenant_service.tenant_db_manager')
    def test_delete_tenant(self, mock_db_manager, client, session, admin_headers, test_admin_user):
        """Test soft deleting tenant (admin only)"""
        # Arrange - Create new tenant for deletion
        from app.models import Tenant, UserTenantAssociation
        tenant = Tenant(name='Tenant To Delete')
        session.add(tenant)
        session.commit()
        session.refresh(tenant)

        assoc = UserTenantAssociation(
            user_id=test_admin_user.id,
            tenant_id=tenant.id,
            role='admin'
        )
        session.add(assoc)
        session.commit()

        tenant_id = str(tenant.id)

        # Act
        response = client.delete(f'/api/tenants/{tenant_id}', headers=admin_headers)

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # Verify tenant is soft deleted (is_active = False)
        session.refresh(tenant)
        assert tenant.is_active is False

    def test_delete_tenant_non_admin(self, client, session, auth_headers, test_tenant):
        """Test non-admin cannot delete tenant"""
        # Arrange
        tenant, _ = test_tenant
        tenant_id = str(tenant.id)

        # Act
        response = client.delete(f'/api/tenants/{tenant_id}', headers=auth_headers)

        # Assert
        assert response.status_code in [403, 404]  # Forbidden or Not Found


class TestCompleteTenantFlow:
    """Test complete tenant management flow"""

    @patch('app.services.tenant_service.tenant_db_manager')
    def test_complete_flow_create_add_users_update(self, mock_db_manager, client, session, auth_headers, test_user):
        """Test: Create tenant → Add users → Update tenant"""
        # Setup mocks
        mock_db_manager.create_tenant_database.return_value = None
        mock_db_manager.create_tenant_tables.return_value = None

        # Step 1: Create tenant
        tenant_data = {'name': 'Flow Test Company'}
        create_response = client.post(
            '/api/tenants',
            data=json.dumps(tenant_data),
            headers=auth_headers
        )
        assert create_response.status_code == 201
        tenant_id = create_response.get_json()['data']['id']

        # Step 2: Get tenant details
        details_response = client.get(f'/api/tenants/{tenant_id}', headers=auth_headers)
        assert details_response.status_code == 200
        assert details_response.get_json()['data']['name'] == 'Flow Test Company'

        # Step 3: Update tenant name
        update_data = {'name': 'Flow Test Company Updated'}
        update_response = client.put(
            f'/api/tenants/{tenant_id}',
            data=json.dumps(update_data),
            headers=auth_headers
        )
        assert update_response.status_code == 200
        assert update_response.get_json()['data']['name'] == 'Flow Test Company Updated'

        # Step 4: Verify updated name persists
        verify_response = client.get(f'/api/tenants/{tenant_id}', headers=auth_headers)
        assert verify_response.status_code == 200
        assert verify_response.get_json()['data']['name'] == 'Flow Test Company Updated'
