#!/usr/bin/env python
"""
Debug script to trace SSO authentication flow and identify PKCE issues.
"""

import sys
import os
import logging
import json
from urllib.parse import urlencode

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import TenantSSOConfig, Tenant
from app.services.azure_ad_service import AzureADService
from flask import url_for

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

def debug_sso_configuration():
    """Debug SSO configuration and test PKCE flow."""
    app = create_app()

    with app.app_context():
        with app.test_request_context():
            # Find SSO configuration
            sso_configs = TenantSSOConfig.query.filter_by(is_enabled=True).all()

            if not sso_configs:
                logger.error("No enabled SSO configurations found")
                return

            for config in sso_configs:
                tenant = Tenant.query.get(config.tenant_id)
                logger.info(f"\n{'='*60}")
                logger.info(f"Testing SSO for tenant: {tenant.name} ({tenant.id})")
                logger.info(f"{'='*60}")

                # Check configuration
                logger.info(f"Provider: {config.provider_type}")
                logger.info(f"Azure Tenant ID: {config.provider_tenant_id}")
                logger.info(f"Client ID: {config.client_id}")
                logger.info(f"Client Secret: {'[SET]' if config.client_secret else '[NOT SET]'}")
                if config.client_secret:
                    logger.info(f"Client Secret length: {len(config.client_secret)}")
                    logger.info(f"Client Secret is empty string: {config.client_secret == ''}")
                    logger.info(f"Client Secret after strip: {'[EMPTY]' if not config.client_secret.strip() else '[HAS VALUE]'}")

                logger.info(f"Redirect URI: {config.redirect_uri}")
                logger.info(f"Config Metadata: {json.dumps(config.config_metadata, indent=2)}")

                # Initialize Azure AD service
                azure_service = AzureADService(config.tenant_id)

                # Test PKCE generation
                code_verifier, code_challenge = azure_service.generate_pkce_pair()
                state = azure_service.generate_state_token()

                logger.info(f"\nPKCE Parameters:")
                logger.info(f"Code Verifier: {code_verifier[:20]}... (length: {len(code_verifier)})")
                logger.info(f"Code Challenge: {code_challenge[:20]}... (length: {len(code_challenge)})")
                logger.info(f"State Token: {state[:20]}... (length: {len(state)})")

                # Build authorization URL
                redirect_uri = url_for('sso_auth.azure_callback', _external=True)
                logger.info(f"\nRedirect URI: {redirect_uri}")

                # Build the auth URL manually to see all parameters
                auth_params = {
                    'client_id': config.client_id,
                    'response_type': 'code',
                    'redirect_uri': redirect_uri,
                    'response_mode': 'query',
                    'scope': 'openid profile email User.Read',
                    'state': state,
                    'code_challenge': code_challenge,
                    'code_challenge_method': 'S256',
                    'prompt': 'select_account'
                }

                logger.info(f"\nAuthorization Parameters:")
                for key, value in auth_params.items():
                    if key in ['code_challenge', 'state']:
                        logger.info(f"  {key}: {value[:20]}... (length: {len(value)})")
                    else:
                        logger.info(f"  {key}: {value}")

                auth_url = f"{config.get_authorization_url()}?{urlencode(auth_params)}"
                logger.info(f"\nFull Authorization URL (first 200 chars):")
                logger.info(auth_url[:200] + "...")

                # Check what would be sent during token exchange
                logger.info(f"\n{'='*40}")
                logger.info("Token Exchange Configuration:")
                logger.info(f"{'='*40}")

                # Simulate what token_data would look like
                token_data = {
                    'client_id': config.client_id,
                    'grant_type': 'authorization_code',
                    'code': '[AUTHORIZATION_CODE]',
                    'redirect_uri': redirect_uri,
                    'scope': 'openid profile email User.Read'
                }

                # Check the condition that determines PKCE vs client_secret
                if config.client_secret and config.client_secret.strip():
                    token_data['client_secret'] = '[CLIENT_SECRET]'
                    logger.info("✗ WILL USE CLIENT_SECRET (Confidential App)")
                    logger.warning("This is why you're getting the error!")
                else:
                    token_data['code_verifier'] = '[CODE_VERIFIER]'
                    logger.info("✓ WILL USE PKCE CODE_VERIFIER (Public App)")

                logger.info(f"\nToken request will include:")
                for key in token_data.keys():
                    logger.info(f"  - {key}")

                # Check Azure Portal configuration requirements
                logger.info(f"\n{'='*40}")
                logger.info("Azure Portal Configuration Requirements:")
                logger.info(f"{'='*40}")
                logger.info("1. Go to Azure Portal > App registrations > Your App")
                logger.info("2. Go to 'Authentication' section")
                logger.info("3. Under 'Advanced settings':")
                logger.info("   - Enable 'Allow public client flows': YES")
                logger.info("4. Platform configuration should be:")
                logger.info("   - Platform: Web (NOT Single-page application)")
                logger.info(f"   - Redirect URI: {redirect_uri}")
                logger.info("5. Do NOT add a client secret if using PKCE")

if __name__ == "__main__":
    debug_sso_configuration()