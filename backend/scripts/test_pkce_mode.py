#!/usr/bin/env python
"""
Test PKCE Mode Script

This script tests if Azure AD is configured to accept PKCE without client_secret.

Usage:
    docker-compose exec api python scripts/test_pkce_mode.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import TenantSSOConfig
from app.services.azure_ad_service import AzureADService


def test_pkce_mode():
    """Test if PKCE mode is working."""
    app = create_app()

    with app.app_context():
        # Find SSO configuration
        config = TenantSSOConfig.query.filter_by(
            client_id='28d84fdd-1d63-4257-8543-86294a55aa80'
        ).first()

        if not config:
            print("❌ SSO configuration not found")
            return False

        print("="*60)
        print("SSO CONFIGURATION STATUS")
        print("="*60)
        print(f"Client ID: {config.client_id}")
        print(f"Azure Tenant: {config.provider_tenant_id}")
        print(f"Redirect URI: {config.redirect_uri}")
        print(f"Has client_secret: {'Yes ⚠️' if config.client_secret else 'No ✅'}")
        print()

        if config.client_secret:
            print("⚠️  ATTENTION:")
            print("Un client_secret est configuré dans la base de données.")
            print("Le backend utilisera le secret au lieu de PKCE.")
            print()
            print("Pour utiliser PKCE sans secret :")
            print("1. Activez 'Allow public client flows' dans Azure Portal")
            print("2. Supprimez le secret de la base de données :")
            print()
            print("   docker-compose exec postgres psql -U postgres -d saas_platform -c \\")
            print("   \"UPDATE tenant_sso_configs SET client_secret = NULL WHERE client_id = '28d84fdd-1d63-4257-8543-86294a55aa80';\"")
            print()
        else:
            print("✅ Aucun client_secret configuré")
            print("Le backend utilisera PKCE (code_verifier)")
            print()
            print("Si vous avez l'erreur AADSTS7000218 :")
            print("→ Activez 'Allow public client flows' dans Azure Portal")
            print()
            print("Si tout est configuré, testez :")
            print(f"http://localhost:4999/api/auth/sso/azure/login/cb859f98-291e-41b2-b30f-2287c2699205")

        print("="*60)
        return True


if __name__ == "__main__":
    test_pkce_mode()