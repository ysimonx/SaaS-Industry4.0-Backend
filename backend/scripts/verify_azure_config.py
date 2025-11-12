#!/usr/bin/env python
"""
Verify Azure AD configuration and ensure PKCE is properly configured.
"""

import sys
import os
import json
import requests

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import TenantSSOConfig, Tenant
from app.extensions import db

def verify_azure_config():
    """Verify and display Azure AD configuration."""
    app = create_app()

    with app.app_context():
        # Find all SSO configurations
        sso_configs = TenantSSOConfig.query.all()

        if not sso_configs:
            print("❌ No SSO configurations found")
            return

        for config in sso_configs:
            tenant = Tenant.query.get(config.tenant_id)

            print(f"\n{'='*60}")
            print(f"Tenant: {tenant.name} ({tenant.id})")
            print(f"{'='*60}")

            # Configuration details
            print("\n📋 Configuration:")
            print(f"  Provider Type: {config.provider_type}")
            print(f"  Azure Tenant ID: {config.provider_tenant_id}")
            print(f"  Client ID: {config.client_id}")
            print(f"  Client Secret: ", end="")
            if config.client_secret is None:
                print("✅ None (PKCE mode)")
            elif config.client_secret == "":
                print("⚠️  Empty string (will cause issues!)")
                # Fix it
                print("  🔧 Fixing: Setting to None...")
                config.client_secret = None
                db.session.commit()
                print("  ✅ Fixed!")
            elif config.client_secret.strip() == "":
                print("⚠️  Whitespace only (will cause issues!)")
                # Fix it
                print("  🔧 Fixing: Setting to None...")
                config.client_secret = None
                db.session.commit()
                print("  ✅ Fixed!")
            else:
                print(f"❌ Set ({len(config.client_secret)} chars) - Remove for PKCE!")

            print(f"  Redirect URI: {config.redirect_uri}")
            print(f"  Is Enabled: {'✅' if config.is_enabled else '❌'}")

            # Metadata
            print(f"\n📦 Config Metadata:")
            if config.config_metadata:
                print(f"  App Type: {config.config_metadata.get('app_type', 'NOT SET')}")
                if config.config_metadata.get('app_type') != 'public':
                    print("  ⚠️  App type should be 'public' for PKCE")
                    config.config_metadata['app_type'] = 'public'
                    db.session.commit()
                    print("  ✅ Fixed: Set app_type to 'public'")
            else:
                print("  ⚠️  No metadata - creating default...")
                config.config_metadata = {'app_type': 'public'}
                db.session.commit()
                print("  ✅ Created default metadata")

            # Azure AD URLs
            print(f"\n🔗 Azure AD URLs:")
            print(f"  Authority: {config.get_authority_url()}")
            print(f"  Authorization: {config.get_authorization_url()}")
            print(f"  Token: {config.get_token_url()}")

            # Test connectivity (optional)
            print(f"\n🌐 Testing Azure AD connectivity...")
            try:
                # Try to reach the OpenID configuration
                openid_url = f"{config.get_authority_url()}/v2.0/.well-known/openid-configuration"
                response = requests.get(openid_url, timeout=5)
                if response.status_code == 200:
                    print(f"  ✅ Azure AD tenant is reachable")
                    data = response.json()
                    print(f"  Authorization endpoint: {data.get('authorization_endpoint', 'N/A')}")
                    print(f"  Token endpoint: {data.get('token_endpoint', 'N/A')}")
                else:
                    print(f"  ⚠️  Azure AD returned status {response.status_code}")
            except Exception as e:
                print(f"  ❌ Could not reach Azure AD: {str(e)}")

            print(f"\n🔧 Azure Portal Configuration Checklist:")
            print(f"  1. App Registration > Authentication > Platform configurations")
            print(f"     ✓ Platform type: Web (NOT SPA)")
            print(f"     ✓ Redirect URI: {config.redirect_uri}")
            print(f"  2. App Registration > Authentication > Advanced settings")
            print(f"     ✓ Allow public client flows: YES ⚠️ CRITICAL")
            print(f"  3. App Registration > Certificates & secrets")
            print(f"     ✓ NO client secret should be configured for PKCE")
            print(f"  4. App Registration > API permissions")
            print(f"     ✓ Microsoft Graph > User.Read (Delegated)")
            print(f"     ✓ openid, profile, email (Delegated)")

if __name__ == "__main__":
    verify_azure_config()