# Azure AD SSO Integration Guide

## Overview

This implementation provides Azure Active Directory (Microsoft Entra ID) Single Sign-On (SSO) capability for the multi-tenant SaaS platform. Each tenant can independently configure and enable Azure AD SSO for their users.

## Key Features

- **Public Application Mode**: Uses OAuth2 with PKCE (no client_secret required)
- **Multi-Tenant Support**: Each tenant can have its own Azure AD instance
- **Auto-Provisioning**: Automatically create users on first SSO login (optional)
- **Hybrid Authentication**: Support both SSO and local password authentication
- **Role Mapping**: Map Azure AD groups to application roles

## Architecture

### Models

1. **TenantSSOConfig**: Stores SSO configuration per tenant (1-to-1 relationship)
2. **UserAzureIdentity**: Maps users to their Azure AD identities per tenant
3. **Tenant** (extended): Added SSO-related fields (auth_method, auto_provisioning, etc.)
4. **User** (extended): Added SSO provider info and nullable password for SSO-only users

### Services

1. **AzureADService**: Handles OAuth2 flow, token management, and user provisioning
2. **TenantSSOConfigService**: Manages SSO configurations and statistics

### API Routes

#### Configuration Management (`/api/tenants/<tenant_id>/sso/config`)
- `GET`: Get SSO configuration
- `POST`: Create SSO configuration
- `PUT`: Update SSO configuration
- `DELETE`: Delete SSO configuration
- `POST /enable`: Enable SSO
- `POST /disable`: Disable SSO
- `GET /validate`: Validate configuration

#### Authentication Flow (`/api/auth/sso`)
- `GET /azure/login/<tenant_id>`: Initiate Azure AD login
- `GET /azure/callback`: Handle OAuth2 callback
- `POST /azure/refresh`: Refresh access token
- `POST /azure/logout/<tenant_id>`: Logout and clear tokens
- `GET /check-availability/<tenant_id>`: Check if SSO is available

## Setup Instructions

### 1. Database Setup

```bash
# Drop and recreate database (if needed)
docker-compose exec postgres psql -U postgres -c "DROP DATABASE IF EXISTS saas_platform;"
docker-compose exec postgres psql -U postgres -c "CREATE DATABASE saas_platform;"

# Remove old migrations
rm -f backend/migrations/versions/*

# Create new migration with SSO support
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Add SSO support"
docker-compose exec api /app/flask-wrapper.sh db upgrade

# Initialize with test data
docker-compose exec api python scripts/init_db.py --create-admin --create-test-tenant
```

### 2. Azure AD App Registration

1. Go to [Azure Portal](https://portal.azure.com) > Azure Active Directory > App registrations
2. Click "New registration"
3. Configure the application:
   - **Name**: Your App Name
   - **Supported account types**: Choose based on your needs
   - **Redirect URI**:
     - Platform: Web
     - URI: `http://localhost:4999/api/auth/sso/azure/callback`

4. After creation, note down:
   - **Application (client) ID**: You'll use this as `client_id`
   - **Directory (tenant) ID**: You'll use this as `provider_tenant_id`

5. Configure authentication:
   - Go to "Authentication" in the left menu
   - Under "Advanced settings":
     - Enable "Allow public client flows": **Yes**
   - Add platform if needed:
     - Platform type: Single-page application or Mobile and desktop applications

6. Configure API permissions:
   - Go to "API permissions"
   - Add permissions:
     - Microsoft Graph (Delegated):
       - `openid`
       - `profile`
       - `email`
       - `User.Read`
   - Click "Grant admin consent" if required

### 3. Configure SSO for a Tenant

#### Option A: Using the Test Script

```bash
# Set Azure AD credentials
export AZURE_CLIENT_ID="your-client-id"
export AZURE_TENANT_ID="your-azure-tenant-id"

# Run setup script
docker-compose exec api python scripts/setup_sso_test.py

# To cleanup test data
docker-compose exec api python scripts/setup_sso_test.py --cleanup
```

#### Option B: Using API Endpoints

1. **Login as tenant admin**:
```bash
curl -X POST http://localhost:4999/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "your-password"}'
```

2. **Create SSO configuration**:
```bash
curl -X POST http://localhost:4999/api/tenants/{tenant_id}/sso/config \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "your-azure-client-id",
    "provider_tenant_id": "your-azure-tenant-id",
    "enable": true,
    "config_metadata": {
      "auto_provisioning": {
        "enabled": true,
        "default_role": "viewer",
        "allowed_email_domains": ["@yourcompany.com"]
      }
    }
  }'
```

3. **Validate configuration**:
```bash
curl -X GET http://localhost:4999/api/tenants/{tenant_id}/sso/config/validate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Testing SSO Login

### 1. Check SSO Availability

```bash
curl -X GET http://localhost:4999/api/auth/sso/check-availability/{tenant_id}
```

Response:
```json
{
  "available": true,
  "auth_method": "both",
  "provider": "azure_ad",
  "auto_provisioning": true
}
```

### 2. Initiate SSO Login

Open in browser:
```
http://localhost:4999/api/auth/sso/azure/login/{tenant_id}
```

This will:
1. Redirect to Microsoft login page
2. After successful authentication, redirect back to callback URL
3. Create/update user account
4. Return JWT tokens for the application

### 3. Using the Tokens

The callback returns:
```json
{
  "access_token": "jwt-access-token",
  "refresh_token": "jwt-refresh-token",
  "user": {
    "id": "user-uuid",
    "email": "user@company.com",
    "first_name": "John",
    "last_name": "Doe"
  },
  "tenant_id": "tenant-uuid",
  "auth_method": "sso"
}
```

Use the access token for API requests:
```bash
curl -X GET http://localhost:4999/api/tenants/{tenant_id}/documents \
  -H "Authorization: Bearer {access_token}"
```

## Configuration Options

### Tenant Authentication Methods

- `local`: Only password authentication
- `sso`: Only SSO authentication
- `both`: Both SSO and password authentication

### Auto-Provisioning Settings

```json
{
  "auto_provisioning": {
    "enabled": true,
    "default_role": "viewer",
    "sync_attributes_on_login": true,
    "allowed_email_domains": ["@company.com"],
    "allowed_azure_groups": ["All-Employees"],
    "group_role_mapping": {
      "IT-Admins": "admin",
      "Developers": "user",
      "Readers": "viewer"
    }
  }
}
```

## Security Considerations

1. **PKCE Implementation**: Uses Proof Key for Code Exchange for secure public client flow
2. **State Token Validation**: Prevents CSRF attacks
3. **Token Storage**: Tokens are stored encrypted (implement Vault encryption in production)
4. **Session Security**: PKCE parameters stored in secure session
5. **Domain Whitelisting**: Restrict SSO to specific email domains
6. **No Client Secret**: Public application mode doesn't require storing secrets

## Troubleshooting

### Common Issues

1. **"No SSO configuration found"**
   - Ensure SSO is configured for the tenant
   - Check if SSO is enabled (`is_enabled=true`)

2. **"Invalid state token"**
   - Clear browser cookies and try again
   - Check session configuration in Flask

3. **Azure AD Error: "AADSTS50011"**
   - Redirect URI mismatch
   - Ensure the callback URL in Azure AD matches exactly

4. **"Email domain not allowed"**
   - Check `sso_domain_whitelist` in tenant settings
   - Update `allowed_email_domains` in auto-provisioning config

### Debug Mode

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check logs:
```bash
docker-compose logs -f api
```

## Production Checklist

- [ ] Configure production redirect URIs in Azure AD
- [ ] Implement token encryption with Vault Transit Engine
- [ ] Set up Redis for token blacklisting
- [ ] Configure HTTPS for all endpoints
- [ ] Enable rate limiting on authentication endpoints
- [ ] Set appropriate CORS policies
- [ ] Implement comprehensive audit logging
- [ ] Configure session security settings
- [ ] Set up monitoring and alerting
- [ ] Document Azure AD app registration process for tenants

## API Documentation

For detailed API documentation, see:
- [SSO Configuration API](./swagger.yaml#/paths/~1api~1tenants~1{tenant_id}~1sso~1config)
- [SSO Authentication API](./swagger.yaml#/paths/~1api~1auth~1sso)

## Support

For issues or questions:
1. Check the logs: `docker-compose logs api`
2. Validate configuration: `GET /api/tenants/{id}/sso/config/validate`
3. Review Azure AD app registration settings
4. Ensure all required Python packages are installed