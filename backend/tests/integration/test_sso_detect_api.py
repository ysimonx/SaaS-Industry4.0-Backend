"""
Integration test for SSO detection API endpoint.

This test verifies the /api/auth/sso/detect endpoint functionality
by mocking the database queries to avoid SQLite/JSONB compatibility issues.
"""

import json
from unittest.mock import patch, MagicMock


class TestSSODetectAPI:
    """Test SSO detect endpoint functionality."""

    @patch('app.routes.sso_auth.Tenant')
    @patch('app.routes.sso_auth.TenantSSOConfig')
    def test_detect_sso_with_matching_domain(self, mock_sso_config, mock_tenant, client):
        """Test SSO detection for email with matching domain."""
        # Setup mock tenant
        tenant = MagicMock()
        tenant.id = '123e4567-e89b-12d3-a456-426614174000'
        tenant.name = 'Test Corp'

        # Setup mock query that returns tenant
        mock_tenant.query.filter.return_value.all.return_value = [tenant]

        # Setup mock SSO config
        sso_config = MagicMock()
        sso_config.provider_type = 'azure_ad'
        sso_config.validate_configuration.return_value = (True, None)
        mock_sso_config.find_enabled_by_tenant_id.return_value = sso_config

        # Make request
        response = client.post(
            '/api/auth/sso/detect',
            data=json.dumps({'email': 'user@company.com'}),
            content_type='application/json'
        )

        # Assertions
        assert response.status_code == 200
        data = response.get_json()
        assert data['has_sso'] is True
        assert len(data['tenants']) == 1
        assert data['tenants'][0]['tenant_name'] == 'Test Corp'
        assert data['tenants'][0]['provider'] == 'azure_ad'

    @patch('app.routes.sso_auth.Tenant')
    def test_detect_sso_no_matching_domain(self, mock_tenant, client):
        """Test SSO detection for email with no matching domain."""
        # Setup mock query that returns empty list
        mock_tenant.query.filter.return_value.all.return_value = []

        # Make request
        response = client.post(
            '/api/auth/sso/detect',
            data=json.dumps({'email': 'user@unknown.com'}),
            content_type='application/json'
        )

        # Assertions
        assert response.status_code == 200
        data = response.get_json()
        assert data['has_sso'] is False
        assert data['tenants'] == []


    def test_detect_sso_missing_email(self, client):
        """Test SSO detection with missing email parameter."""
        response = client.post(
            '/api/auth/sso/detect',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'Email is required' in data['error']

    def test_detect_sso_invalid_email_format(self, client):
        """Test SSO detection with invalid email format."""
        response = client.post(
            '/api/auth/sso/detect',
            data=json.dumps({'email': 'notanemail'}),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'Invalid email format' in data['error']

    def test_azure_authorization_url_generation(self):
        """Test that Azure AD authorization URL is generated correctly."""
        from urllib.parse import urlparse, parse_qs
        from app.services.azure_ad_service import AzureADService

        # Create mock SSO config
        mock_sso_config = MagicMock()
        mock_sso_config.client_id = '61da75ae-c4de-4245-8eeb-7b49a5c50339'
        mock_sso_config.provider_tenant_id = '072a8ae9-5c75-4606-98c3-c0754cf130aa'
        mock_sso_config.get_authorization_url.return_value = (
            'https://login.microsoftonline.com/'
            '072a8ae9-5c75-4606-98c3-c0754cf130aa/oauth2/v2.0/authorize'
        )

        # Patch TenantSSOConfig.find_enabled_by_tenant_id
        with patch('app.services.azure_ad_service.TenantSSOConfig.'
                   'find_enabled_by_tenant_id') as mock_find:
            mock_find.return_value = mock_sso_config

            # Initialize Azure AD service
            azure_service = AzureADService('test-tenant-id')

            # Generate PKCE parameters
            _, code_challenge = azure_service.generate_pkce_pair()
            state = azure_service.generate_state_token()

            # Generate authorization URL
            auth_url = azure_service.get_authorization_url(
                redirect_uri='http://localhost:4999/api/auth/sso/azure/callback',
                state=state,
                code_challenge=code_challenge
            )

            # Verify the URL doesn't contain HTML entities
            assert '&amp;' not in auth_url, f"URL contains HTML entities: {auth_url}"

            # Parse the URL
            parsed = urlparse(auth_url)
            query_params = parse_qs(parsed.query)

            # Verify all required parameters are present
            required_params = ['client_id', 'response_type', 'redirect_uri', 'scope',
                              'state', 'code_challenge', 'code_challenge_method']

            for param in required_params:
                assert param in query_params, f"Missing parameter: {param}"

            # Verify scope parameter contains expected values
            scope = query_params.get('scope', [''])[0]
            expected_scopes = ['openid', 'profile', 'email', 'User.Read']
            for expected_scope in expected_scopes:
                assert expected_scope in scope, f"Missing scope: {expected_scope} in {scope}"

    @patch('app.routes.sso_auth.Tenant')
    @patch('app.routes.sso_auth.TenantSSOConfig')
    def test_detect_sso_multiple_tenants(self, mock_sso_config, mock_tenant, client):
        """Test SSO detection with multiple matching tenants."""
        # Setup mock tenants
        tenant1 = MagicMock()
        tenant1.id = '123e4567-e89b-12d3-a456-426614174001'
        tenant1.name = 'Corp One'

        tenant2 = MagicMock()
        tenant2.id = '123e4567-e89b-12d3-a456-426614174002'
        tenant2.name = 'Corp Two'

        # Setup mock query
        mock_tenant.query.filter.return_value.all.return_value = [tenant1, tenant2]

        # Setup mock SSO configs
        sso_config = MagicMock()
        sso_config.provider_type = 'azure_ad'
        sso_config.validate_configuration.return_value = (True, None)
        mock_sso_config.find_enabled_by_tenant_id.return_value = sso_config

        # Make request
        response = client.post(
            '/api/auth/sso/detect',
            data=json.dumps({'email': 'user@shared.com'}),
            content_type='application/json'
        )

        # Assertions
        assert response.status_code == 200
        data = response.get_json()
        assert data['has_sso'] is True
        assert len(data['tenants']) == 2
        assert data['tenants'][0]['tenant_name'] == 'Corp One'
        assert data['tenants'][1]['tenant_name'] == 'Corp Two'

    @patch('app.routes.sso_auth.Tenant')
    @patch('app.routes.sso_auth.TenantSSOConfig')
    def test_detect_sso_with_disabled_config(self, mock_sso_config, mock_tenant, client):
        """Test SSO detection excludes tenants with disabled SSO config."""
        # Setup mock tenant
        tenant = MagicMock()
        tenant.id = '123e4567-e89b-12d3-a456-426614174000'
        tenant.name = 'Test Corp'

        # Setup mock query
        mock_tenant.query.filter.return_value.all.return_value = [tenant]

        # SSO config not found (disabled)
        mock_sso_config.find_enabled_by_tenant_id.return_value = None

        # Make request
        response = client.post(
            '/api/auth/sso/detect',
            data=json.dumps({'email': 'user@disabled.com'}),
            content_type='application/json'
        )

        # Assertions
        assert response.status_code == 200
        data = response.get_json()
        assert data['has_sso'] is False
        assert data['tenants'] == []

    @patch('app.routes.sso_auth.Tenant')
    @patch('app.routes.sso_auth.TenantSSOConfig')
    def test_detect_sso_with_invalid_config(self, mock_sso_config, mock_tenant, client):
        """Test SSO detection excludes tenants with invalid SSO config."""
        # Setup mock tenant
        tenant = MagicMock()
        tenant.id = '123e4567-e89b-12d3-a456-426614174000'
        tenant.name = 'Test Corp'

        # Setup mock query
        mock_tenant.query.filter.return_value.all.return_value = [tenant]

        # Setup invalid SSO config
        sso_config = MagicMock()
        sso_config.provider_type = 'azure_ad'
        sso_config.validate_configuration.return_value = (False, 'Invalid configuration')
        mock_sso_config.find_enabled_by_tenant_id.return_value = sso_config

        # Make request
        response = client.post(
            '/api/auth/sso/detect',
            data=json.dumps({'email': 'user@invalid.com'}),
            content_type='application/json'
        )

        # Assertions
        assert response.status_code == 200
        data = response.get_json()
        assert data['has_sso'] is False
        assert data['tenants'] == []

