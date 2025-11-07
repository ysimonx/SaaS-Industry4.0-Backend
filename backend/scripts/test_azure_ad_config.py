#!/usr/bin/env python
"""
Test Azure AD Configuration Script

This script helps diagnose Azure AD configuration issues for SSO.
It checks if your Azure AD application is properly configured as a Web application
(not SPA) and validates the OAuth2 flow with PKCE.

Usage:
    docker-compose exec api python scripts/test_azure_ad_config.py
"""

import json
import logging
import os
import sys
import requests
from urllib.parse import urlencode

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_azure_ad_configuration(tenant_id: str = None):
    """
    Test Azure AD configuration for a tenant.
    """
    from app import create_app
    from app.models import Tenant, TenantSSOConfig
    from app.services.azure_ad_service import AzureADService

    app = create_app()

    with app.app_context():
        # Find a tenant with SSO configured
        if tenant_id:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                logger.error(f"Tenant {tenant_id} not found")
                return False
        else:
            # Find any tenant with SSO enabled
            tenant = Tenant.query.filter(
                Tenant.auth_method.in_(['sso', 'both']),
                Tenant.is_active == True
            ).first()

            if not tenant:
                logger.error("No tenant with SSO enabled found")
                return False

        logger.info(f"Testing SSO for tenant: {tenant.name} ({tenant.id})")

        # Get SSO configuration
        sso_config = TenantSSOConfig.find_enabled_by_tenant_id(tenant.id)
        if not sso_config:
            logger.error("No enabled SSO configuration found for tenant")
            return False

        logger.info(f"SSO Provider: {sso_config.provider_type}")
        logger.info(f"Client ID: {sso_config.client_id}")
        logger.info(f"Azure Tenant ID: {sso_config.provider_tenant_id}")

        # Test 1: Check OpenID configuration endpoint
        logger.info("\n=== Test 1: Checking Azure AD OpenID Configuration ===")
        discovery_url = f"https://login.microsoftonline.com/{sso_config.provider_tenant_id}/v2.0/.well-known/openid-configuration"

        try:
            response = requests.get(discovery_url, timeout=10)
            if response.status_code == 200:
                logger.info("✅ OpenID configuration endpoint is accessible")
                config = response.json()

                # Check if authorization endpoint supports 'code' response type
                if 'code' in config.get('response_types_supported', []):
                    logger.info("✅ Authorization code flow is supported")
                else:
                    logger.warning("⚠️ Authorization code flow may not be supported")

                # Check if PKCE is supported
                if 'S256' in config.get('code_challenge_methods_supported', []):
                    logger.info("✅ PKCE with S256 is supported")
                else:
                    logger.warning("⚠️ PKCE may not be supported")
            else:
                logger.error(f"❌ Failed to fetch OpenID configuration: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Error fetching OpenID configuration: {e}")
            return False

        # Test 2: Generate authorization URL
        logger.info("\n=== Test 2: Generating Authorization URL ===")
        try:
            azure_service = AzureADService(str(tenant.id))

            # Generate PKCE parameters
            code_verifier, code_challenge = azure_service.generate_pkce_pair()
            state = azure_service.generate_state_token()

            # Generate authorization URL
            auth_url = azure_service.get_authorization_url(
                redirect_uri=sso_config.redirect_uri,
                state=state,
                code_challenge=code_challenge
            )

            logger.info("✅ Authorization URL generated successfully")
            logger.info(f"URL (first 200 chars): {auth_url[:200]}...")

            # Check for HTML encoding issues
            if '&amp;' in auth_url:
                logger.error("❌ URL contains HTML entities (&amp;)")
                return False
            else:
                logger.info("✅ URL does not contain HTML entities")

        except Exception as e:
            logger.error(f"❌ Failed to generate authorization URL: {e}")
            return False

        # Test 3: Simulate token exchange (dry run)
        logger.info("\n=== Test 3: Token Exchange Configuration Check ===")
        logger.info("Token exchange will use:")
        logger.info(f"  - client_id: {sso_config.client_id}")
        logger.info(f"  - redirect_uri: {sso_config.redirect_uri}")
        logger.info(f"  - grant_type: authorization_code")
        logger.info(f"  - code_verifier: PKCE verifier (generated)")
        logger.info(f"  - NO client_secret (public client with PKCE)")

        # Test 4: Check for common misconfigurations
        logger.info("\n=== Test 4: Common Misconfiguration Checks ===")

        # Check redirect URI format
        redirect_uri = sso_config.redirect_uri
        if redirect_uri.startswith('http://localhost'):
            logger.info(f"✅ Localhost redirect URI configured: {redirect_uri}")
        elif redirect_uri.startswith('https://'):
            logger.info(f"✅ HTTPS redirect URI configured: {redirect_uri}")
        else:
            logger.warning(f"⚠️ Unusual redirect URI format: {redirect_uri}")

        # Check if it looks like a SPA redirect (common mistake)
        if '/index.html' in redirect_uri or '#' in redirect_uri:
            logger.warning("⚠️ Redirect URI looks like it might be for a SPA (contains /index.html or #)")
            logger.warning("   Make sure the Azure AD app is configured as 'Web' not 'SPA'")

        # Summary
        logger.info("\n" + "="*60)
        logger.info("CONFIGURATION SUMMARY")
        logger.info("="*60)
        logger.info(f"Tenant: {tenant.name}")
        logger.info(f"SSO Provider: {sso_config.provider_type}")
        logger.info(f"Auth Method: {tenant.auth_method}")
        logger.info(f"Auto-provisioning: {tenant.sso_auto_provisioning}")

        logger.info("\n⚠️  IMPORTANT AZURE AD PORTAL CHECKS:")
        logger.info("1. Go to Azure Portal → Azure Active Directory → App registrations")
        logger.info(f"2. Find your app (Client ID: {sso_config.client_id})")
        logger.info("3. Click on 'Authentication' in the left menu")
        logger.info("4. Verify:")
        logger.info("   - Platform type is 'Web' (NOT 'Single-page application')")
        logger.info(f"   - Redirect URI includes: {sso_config.redirect_uri}")
        logger.info("   - Implicit grant flows are NOT checked")
        logger.info("   - Allow public client flows: No (or Yes if using PKCE without secret)")
        logger.info("\nIf platform type is 'SPA', delete it and add a 'Web' platform instead.")

        return True


def main():
    """Main function."""
    # Check if tenant_id was provided as argument
    tenant_id = None
    if len(sys.argv) > 1:
        tenant_id = sys.argv[1]
        logger.info(f"Testing specific tenant: {tenant_id}")

    success = test_azure_ad_configuration(tenant_id)

    if success:
        logger.info("\n✅ Configuration tests passed. Check Azure Portal settings as indicated above.")
    else:
        logger.error("\n❌ Configuration tests failed. Review the errors above.")
        logger.error("See AZURE_AD_CONFIGURATION_GUIDE.md for detailed setup instructions.")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())