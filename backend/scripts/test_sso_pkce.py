#!/usr/bin/env python
"""
Test script to verify PKCE configuration and fix empty client_secret issues.

This script:
1. Checks SSO configurations
2. Cleans up empty client_secret values
3. Tests the PKCE flow
"""

import sys
import os
import logging

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import TenantSSOConfig, Tenant
from app.services.azure_ad_service import AzureADService
from app.extensions import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_and_fix_sso_configs():
    """Check and fix SSO configurations with empty client_secret values."""
    app = create_app()

    with app.app_context():
        # Find all SSO configurations
        sso_configs = TenantSSOConfig.query.all()

        if not sso_configs:
            logger.info("No SSO configurations found in database.")
            return

        fixed_count = 0
        for config in sso_configs:
            tenant = Tenant.query.get(config.tenant_id)
            logger.info(f"Checking SSO config for tenant: {tenant.name} (ID: {config.tenant_id})")

            # Check if client_secret is empty string or whitespace
            if config.client_secret is not None:
                if not config.client_secret.strip():
                    logger.warning(f"  Found empty client_secret for tenant {tenant.name}")
                    config.client_secret = None
                    fixed_count += 1
                    logger.info(f"  Set client_secret to None (enabling PKCE-only mode)")
                else:
                    logger.info(f"  Has client_secret configured (confidential app mode)")
            else:
                logger.info(f"  No client_secret configured (PKCE-only mode)")

            # Ensure app_type is set to 'public' in metadata
            if not config.config_metadata:
                config.config_metadata = {}

            config.config_metadata['app_type'] = 'public'
            logger.info(f"  Set app_type to 'public' in metadata")

            # Test PKCE generation
            try:
                azure_service = AzureADService(config.tenant_id)
                code_verifier, code_challenge = azure_service.generate_pkce_pair()
                logger.info(f"  PKCE test successful - generated challenge with length {len(code_challenge)}")
            except Exception as e:
                logger.error(f"  PKCE test failed: {str(e)}")

        if fixed_count > 0:
            db.session.commit()
            logger.info(f"\n✅ Fixed {fixed_count} SSO configuration(s) with empty client_secret")
        else:
            logger.info("\n✅ All SSO configurations are properly configured")

        # Summary
        logger.info("\n=== SSO Configuration Summary ===")
        for config in sso_configs:
            tenant = Tenant.query.get(config.tenant_id)
            mode = "Confidential App" if config.client_secret else "Public App (PKCE)"
            status = "✅ Enabled" if config.is_enabled else "❌ Disabled"
            logger.info(f"  {tenant.name}: {mode} - {status}")

if __name__ == "__main__":
    check_and_fix_sso_configs()