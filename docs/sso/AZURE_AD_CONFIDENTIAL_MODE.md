# Azure AD Confidential Application Mode Configuration

## ⚠️ CRITICAL: This Platform Uses Confidential Mode (NOT PKCE)

This document clarifies the SSO authentication mode used by this platform.

---

## Authentication Mode: Confidential Application

### What This Means

This platform implements **OAuth2 Authorization Code Flow with Client Secret**, which is the standard for server-side web applications.

```
┌─────────────────────────────────────────────────────────────────┐
│  Authentication Flow: Confidential Application                  │
└─────────────────────────────────────────────────────────────────┘

1. User initiates login
2. Redirect to Azure AD with client_id
3. User authenticates in Azure AD
4. Azure returns authorization code
5. Backend exchanges code for tokens:
   ✓ Includes client_id
   ✓ Includes client_secret (REQUIRED)
   ✓ Includes redirect_uri
6. Azure validates credentials and returns tokens
```

---

## Why NOT PKCE?

### PKCE (Proof Key for Code Exchange) is for:
- ❌ Single Page Applications (SPAs)
- ❌ Mobile applications
- ❌ Desktop applications
- ❌ Public clients that CANNOT securely store secrets

### This Platform Uses Confidential Mode because:
- ✅ Backend server can securely store client_secret
- ✅ More secure than PKCE for server-side applications
- ✅ Standard OAuth2 flow for web applications
- ✅ Aligns with enterprise security requirements
- ✅ Required by many enterprise Azure AD configurations

---

## Azure Portal Configuration

### Step 1: Register Application

1. Go to: https://portal.azure.com
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **New registration**
4. Configure:
   - Name: "Your SaaS Platform"
   - Supported account types: "Accounts in this organizational directory only"
   - Redirect URI:
     - Type: **Web** (NOT Single-page application!)
     - URI: `http://localhost:4999/api/auth/sso/azure/callback`

### Step 2: Create Client Secret (REQUIRED)

1. Go to **Certificates & secrets** in left menu
2. Click **New client secret**
3. Configure:
   - Description: "SaaS Platform Secret"
   - Expiration: Choose 12 or 24 months
4. Click **Add**
5. **IMMEDIATELY COPY THE VALUE** (shown only once!)
6. Store securely - you'll need it for the API configuration

### Step 3: Authentication Settings

1. Go to **Authentication** in left menu
2. Under **Platform configurations**:
   - Verify platform type is **Web**
   - Verify redirect URI is correct
3. Under **Implicit grant and hybrid flows**:
   - ✓ Check "ID tokens"
   - ✓ Check "Access tokens"
4. Under **Advanced settings**:
   - ⚠️ **CRITICAL**: Ensure "Allow public client flows" is **NO** (disabled)
   - This confirms confidential mode

### Step 4: API Permissions

1. Go to **API permissions**
2. Ensure you have:
   - `Microsoft Graph > User.Read` (Delegated)
   - `Microsoft Graph > email` (Delegated)
   - `Microsoft Graph > profile` (Delegated)
   - `Microsoft Graph > openid` (Delegated)
3. Click **Grant admin consent** if available

### Step 5: Collect Configuration Values

Copy these values for API configuration:
- **Application (client) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- **Directory (tenant) ID**: `yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy`
- **Client secret**: `zzzzzzzz...` (from Step 2)

---

## Platform Configuration

### Create SSO Configuration via API

```bash
curl -X POST http://localhost:4999/api/tenants/{tenant_id}/sso/config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_secret": "zzzzzzzz...",
    "provider_tenant_id": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
    "enable": true,
    "config_metadata": {
      "auto_provisioning": {
        "enabled": true,
        "default_role": "viewer"
      }
    }
  }'
```

### Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| `client_id` | ✅ YES | Azure Application (client) ID |
| `client_secret` | ✅ YES | Azure client secret (confidential mode) |
| `provider_tenant_id` | ✅ YES | Azure Directory (tenant) ID or domain |
| `enable` | Optional | Enable SSO immediately (default: false) |
| `config_metadata` | Optional | Additional settings (auto-provisioning, etc.) |

---

## Security Considerations

### Client Secret Storage

The platform stores client_secret securely:

1. **Database**: Encrypted column in PostgreSQL
2. **Vault Transit**: Optional encryption via HashiCorp Vault
3. **Access Control**: Only admin users can configure SSO
4. **Rotation**: Support for secret rotation without downtime

### Token Security

Azure AD tokens are managed securely:

1. **Access Tokens**: Encrypted, stored in `UserAzureIdentity` table
2. **Refresh Tokens**: Encrypted, automatically rotated
3. **Expiration**: Tokens refreshed via Celery workers before expiry
4. **Cleanup**: Expired tokens removed automatically

---

## Troubleshooting

### Error: "The application requires a client secret"

**Cause**: Missing or invalid client_secret

**Solution**:
1. Verify you created a client secret in Azure Portal
2. Copy the secret value (not the Secret ID)
3. Include `client_secret` in the API request
4. Check secret hasn't expired

### Error: "AADSTS7000218: The request body must contain the following parameter: 'client_assertion'"

**Cause**: Azure AD expects certificate-based authentication, not client secret

**Solution**:
1. In Azure Portal → **Certificates & secrets**
2. Ensure you're using **Client secrets**, not Certificates
3. Remove any certificates if present
4. Create a new client secret

### Error: "AADSTS700016: Application not found"

**Cause**: Invalid client_id or wrong Azure tenant

**Solution**:
1. Verify client_id matches Application ID in Azure Portal
2. Verify provider_tenant_id matches Directory ID
3. Check application hasn't been deleted

### Error: "redirect_uri_mismatch"

**Cause**: Redirect URI doesn't match Azure configuration

**Solution**:
1. In Azure Portal → **Authentication**
2. Verify redirect URI is exactly: `http://localhost:4999/api/auth/sso/azure/callback`
3. Check for trailing slashes, protocol (http vs https)
4. Ensure port number matches (4999)

---

## Verification Checklist

Before testing SSO, verify:

- [ ] Application registered in Azure AD
- [ ] Platform type is **Web** (not SPA or mobile)
- [ ] Client secret created and copied
- [ ] "Allow public client flows" is **NO** (disabled)
- [ ] Redirect URI matches exactly
- [ ] API permissions granted
- [ ] SSO configuration created via API with all required fields
- [ ] `client_secret` included in configuration
- [ ] `app_type` is set to `confidential` in config_metadata

---

## Testing SSO Flow

### Step 1: Check SSO Availability

```bash
curl http://localhost:4999/api/auth/sso/check-availability/{tenant_id}
```

Expected response:
```json
{
  "available": true,
  "sso_login_url": "http://localhost:4999/api/auth/sso/azure/login/{tenant_id}"
}
```

### Step 2: Initiate SSO Login

Navigate to the `sso_login_url` in your browser.

Expected flow:
1. Redirect to Azure AD login page
2. Authenticate with Azure AD credentials
3. Consent screen (first time only)
4. Redirect back to callback URL
5. JWT tokens returned

### Step 3: Verify Logs

```bash
docker-compose logs -f api | grep -i "sso\|azure"
```

Look for:
- ✅ "SSO configuration loaded"
- ✅ "Using confidential application mode"
- ✅ "Token exchange successful"
- ❌ "client_secret is missing" (this should NOT appear)
- ❌ "PKCE" mentions (this should NOT appear)

---

## Common Misconceptions

### ❌ "I need to enable public client flows for OAuth2"

**NO.** Public client flows are ONLY for applications that cannot securely store secrets (SPAs, mobile apps). Backend servers should use confidential mode.

### ❌ "PKCE is more secure than client_secret"

**NO.** PKCE is a workaround for public clients that cannot use client secrets. For server-side applications, client_secret with proper storage is more secure.

### ❌ "I should use both PKCE and client_secret"

**NO.** These are mutually exclusive approaches. Use one or the other:
- Public clients (SPA, mobile) → PKCE (no secret)
- Confidential clients (backend) → client_secret

### ❌ "The platform uses PKCE because I saw it in old docs"

**NO.** The platform was refactored to use confidential mode. Old PKCE references are obsolete.

---

## Migration from PKCE to Confidential Mode

If you have an existing PKCE configuration:

1. **Azure Portal Changes**:
   - Go to **Certificates & secrets**
   - Create a new client secret
   - Copy the secret value
   - Go to **Authentication**
   - Disable "Allow public client flows"

2. **Platform Configuration**:
   ```bash
   # Update existing SSO configuration
   curl -X PUT http://localhost:4999/api/tenants/{tenant_id}/sso/config \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "client_secret": "your-new-client-secret"
     }'
   ```

3. **Test the SSO flow** to verify it works with client_secret

---

## Support

For additional help:

1. Check logs: `docker-compose logs -f api`
2. Review Azure AD sign-in logs in Azure Portal
3. Verify configuration with: `GET /api/tenants/{id}/sso/config`
4. Test token exchange manually using Azure AD OAuth2 endpoints

---

**Remember**: This platform uses **Confidential Application mode** with **client_secret**. PKCE is NOT used and NOT needed.
