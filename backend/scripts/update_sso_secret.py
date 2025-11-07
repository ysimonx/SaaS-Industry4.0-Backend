#!/usr/bin/env python
"""
Update SSO Client Secret Script

This script updates the client_secret for an SSO configuration.
Use this after creating a new client secret in Azure Portal.

Usage:
    docker-compose exec api python scripts/update_sso_secret.py
"""

import os
import sys
import getpass

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import Tenant, TenantSSOConfig
from app.extensions import db


def update_client_secret():
    """Update client secret for SSO configuration."""
    app = create_app()

    with app.app_context():
        # Find tenants with SSO
        tenants = Tenant.query.filter(
            Tenant.auth_method.in_(['sso', 'both'])
        ).all()

        if not tenants:
            print("No tenants with SSO enabled found.")
            return False

        print("Found tenants with SSO enabled:")
        for i, tenant in enumerate(tenants, 1):
            config = TenantSSOConfig.find_enabled_by_tenant_id(tenant.id)
            if config:
                print(f"{i}. {tenant.name} (ID: {tenant.id})")
                print(f"   Client ID: {config.client_id}")
                print(f"   Has secret: {'Yes' if config.client_secret else 'No'}")

        # Select tenant
        if len(tenants) == 1:
            selected_tenant = tenants[0]
            print(f"\nUpdating SSO configuration for: {selected_tenant.name}")
        else:
            try:
                choice = int(input("\nSelect tenant number to update: "))
                if 1 <= choice <= len(tenants):
                    selected_tenant = tenants[choice - 1]
                else:
                    print("Invalid selection")
                    return False
            except (ValueError, KeyboardInterrupt):
                print("\nCancelled")
                return False

        # Get SSO config
        sso_config = TenantSSOConfig.find_enabled_by_tenant_id(selected_tenant.id)
        if not sso_config:
            print(f"No SSO configuration found for tenant {selected_tenant.name}")
            return False

        print(f"\nCurrent configuration:")
        print(f"  Client ID: {sso_config.client_id}")
        print(f"  Azure Tenant: {sso_config.provider_tenant_id}")
        print(f"  Has secret: {'Yes' if sso_config.client_secret else 'No'}")

        # Get new secret
        print("\n" + "="*60)
        print("INSTRUCTIONS:")
        print("1. Go to Azure Portal → App registrations")
        print(f"2. Find app with Client ID: {sso_config.client_id}")
        print("3. Go to 'Certificates & secrets' → 'Client secrets'")
        print("4. Click 'New client secret'")
        print("5. Copy the secret VALUE (not the ID)")
        print("="*60)

        try:
            # Use getpass for secure input
            client_secret = getpass.getpass("\nPaste the client secret here (hidden): ").strip()

            if not client_secret:
                print("No secret provided")
                return False

            # Confirm
            print(f"\nSecret length: {len(client_secret)} characters")
            confirm = input("Save this client secret? (yes/no): ").lower()

            if confirm == 'yes':
                sso_config.client_secret = client_secret
                db.session.commit()
                print("✅ Client secret updated successfully!")
                print("\nYou can now test SSO login:")
                print(f"http://localhost:4999/api/auth/sso/azure/login/{selected_tenant.id}")
                return True
            else:
                print("Cancelled")
                return False

        except KeyboardInterrupt:
            print("\nCancelled")
            return False


def main():
    """Main function."""
    success = update_client_secret()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())