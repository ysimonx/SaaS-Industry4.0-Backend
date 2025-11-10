# ⚠️ OBSOLETE: Azure AD PKCE Configuration

## 🚨 THIS DOCUMENT IS OBSOLETE 🚨

**The platform NO LONGER uses PKCE (Proof Key for Code Exchange).**

**Current authentication mode: Confidential Application with client_secret**

---

## Migration Notice

This document described a PKCE-based configuration that is **NO LONGER USED**.

### What Changed

| Before (PKCE) | Now (Confidential) |
|---------------|-------------------|
| ❌ Public client mode | ✅ Confidential application mode |
| ❌ PKCE code challenge | ✅ Client secret authentication |
| ❌ No client secret | ✅ Client secret REQUIRED |
| ❌ "Allow public client flows" enabled | ✅ "Allow public client flows" DISABLED |

---

## ⚠️ If You're Getting "The application requires a client secret" Error

This error means you need to:

1. **Create a client secret in Azure Portal**:
   - Go to **Certificates & secrets**
   - Click **New client secret**
   - Copy the value immediately

2. **Disable public client flows**:
   - Go to **Authentication**
   - Under **Advanced settings**
   - Set "Allow public client flows" to **NO**

3. **Include client_secret in your SSO configuration**:
   ```bash
   curl -X POST http://localhost:4999/api/tenants/{tenant_id}/sso/config \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "client_id": "your-client-id",
       "client_secret": "your-client-secret",
       "provider_tenant_id": "your-tenant-id"
     }'
   ```

---

## ✅ Current Documentation

For the correct, up-to-date configuration, see:

📖 **[AZURE_AD_CONFIDENTIAL_MODE.md](AZURE_AD_CONFIDENTIAL_MODE.md)**

This document contains:
- Correct Azure Portal configuration steps
- Confidential application mode setup
- Client secret management
- Troubleshooting for confidential mode
- Security best practices

---

## Why The Change?

### PKCE Was Intended For:
- Single Page Applications (SPAs)
- Mobile applications
- Public clients that cannot store secrets

### This Platform Is:
- A backend server application
- Capable of securely storing client secrets
- Better suited for confidential application mode
- Aligned with enterprise security requirements

### Benefits of Confidential Mode:
1. ✅ More secure for server-side applications
2. ✅ Standard OAuth2 flow for web applications
3. ✅ Required by many enterprise Azure AD configurations
4. ✅ Supports advanced features (client credentials grant, etc.)
5. ✅ Better alignment with security best practices

---

## Historical Context (For Reference Only)

This document previously described configuring Azure AD for PKCE mode, which included:

- ~~Enabling "Allow public client flows"~~
- ~~NOT creating a client secret~~
- ~~Using PKCE code challenge/verifier~~

**These instructions are now INCORRECT and should NOT be followed.**

---

## Action Required

If you configured SSO using the old PKCE instructions:

1. ✅ Read the new documentation: [AZURE_AD_CONFIDENTIAL_MODE.md](AZURE_AD_CONFIDENTIAL_MODE.md)
2. ✅ Create a client secret in Azure Portal
3. ✅ Disable "Allow public client flows"
4. ✅ Update your SSO configuration to include client_secret
5. ✅ Test the SSO flow

---

## Questions?

For current SSO configuration help, refer to:

- 📖 [AZURE_AD_CONFIDENTIAL_MODE.md](AZURE_AD_CONFIDENTIAL_MODE.md) - Detailed setup guide
- 📖 [README.md](../../README.md#azure-sso-configuration) - Quick start guide
- 📖 [ARCHITECTURE.md](../ARCHITECTURE.md#azure-ad-single-sign-on-sso) - Technical architecture

---

**Last Updated**: 2025-11-10
**Status**: OBSOLETE - Replaced by AZURE_AD_CONFIDENTIAL_MODE.md
