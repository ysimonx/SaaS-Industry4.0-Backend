#!/usr/bin/env python
"""
Setup SSO Test Script

This script helps set up and test Azure AD SSO integration for a tenant.
Run this after creating the database migrations.

Usage:
    docker-compose exec api python scripts/setup_sso_test.py
"""

import os
import sys
import json
import argparse
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, Tenant, TenantSSOConfig, UserTenantAssociation
from app.services.tenant_sso_config_service import TenantSSOConfigService


def setup_test_tenant_with_sso():
    """
    Create a test tenant with SSO configuration.
    """
    app = create_app()

    with app.app_context():
        print("\n=== Setting up Test Tenant with Azure SSO ===\n")

        # 1. Create or get test tenant
        print("1. Creating test tenant...")
        test_tenant = Tenant.query.filter_by(name="SSO Test Company").first()

        if not test_tenant:
            test_tenant = Tenant(
                name="SSO Test Company",
                auth_method="both",  # Allow both SSO and local auth
                sso_auto_provisioning=True,
                sso_default_role="viewer",
                sso_domain_whitelist=["@example.com", "@test.com"]
            )
            db.session.add(test_tenant)
            db.session.commit()

            # Create tenant database
            test_tenant.create_database()
            print(f"  ✓ Created tenant: {test_tenant.name} (ID: {test_tenant.id})")
        else:
            print(f"  → Using existing tenant: {test_tenant.name} (ID: {test_tenant.id})")

        # 2. Create admin user for the tenant
        print("\n2. Creating admin user...")
        admin_email = "admin@example.com"
        admin_user = User.find_by_email(admin_email)

        if not admin_user:
            admin_user = User(
                email=admin_email,
                first_name="Admin",
                last_name="User"
            )
            admin_user.set_password("12345678")
            db.session.add(admin_user)
            db.session.commit()
            print(f"  ✓ Created admin user: {admin_email}")
        else:
            print(f"  → Using existing user: {admin_email}")

        # 3. Associate admin with tenant
        print("\n3. Associating admin with tenant...")
        association = UserTenantAssociation.query.filter_by(
            user_id=admin_user.id,
            tenant_id=test_tenant.id
        ).first()

        if not association:
            association = UserTenantAssociation(
                user_id=admin_user.id,
                tenant_id=test_tenant.id,
                role="admin"
            )
            db.session.add(association)
            db.session.commit()
            print(f"  ✓ Associated admin user with tenant as 'admin'")
        else:
            print(f"  → User already associated with tenant as '{association.role}'")

        # 4. Configure SSO for the tenant
        print("\n4. Configuring Azure SSO...")

        # Check if SSO config already exists
        existing_config = TenantSSOConfig.find_by_tenant_id(test_tenant.id)

        if existing_config:
            print(f"  → SSO already configured for tenant")
            print(f"    Client ID: {existing_config.client_id}")
            print(f"    Provider Tenant: {existing_config.provider_tenant_id}")
            print(f"    Enabled: {existing_config.is_enabled}")
        else:
            # These values should be replaced with your actual Azure AD app registration
            AZURE_CLIENT_ID = os.getenv('AZURE_CLIENT_ID', '12345678-1234-1234-1234-123456789abc')
            AZURE_TENANT_ID = os.getenv('AZURE_TENANT_ID', 'common')  # Or your specific tenant ID

            print(f"  → Creating SSO configuration...")
            print(f"    Client ID: {AZURE_CLIENT_ID}")
            print(f"    Azure Tenant: {AZURE_TENANT_ID}")

            config_metadata = {
                "auto_provisioning": {
                    "enabled": True,
                    "default_role": "viewer",
                    "sync_attributes_on_login": True,
                    "allowed_email_domains": ["@example.com", "@test.com"],
                    "allowed_azure_groups": ["All-Employees"],
                    "group_role_mapping": {
                        "IT-Admins": "admin",
                        "Developers": "user",
                        "Readers": "viewer"
                    }
                }
            }

            try:
                sso_config = TenantSSOConfigService.create_sso_config(
                    tenant_id=str(test_tenant.id),
                    client_id=AZURE_CLIENT_ID,
                    provider_tenant_id=AZURE_TENANT_ID,
                    config_metadata=config_metadata,
                    enable=True
                )

                print(f"  ✓ SSO configuration created and enabled")
                print(f"    Redirect URI: {sso_config.redirect_uri}")

            except Exception as e:
                print(f"  ✗ Failed to create SSO config: {str(e)}")
                return

        # 5. Display test instructions
        print("\n" + "="*60)
        print("✅ SSO Test Setup Complete!")
        print("="*60)

        print("\n📋 Azure AD App Registration Requirements:")
        print("-" * 40)
        print("1. Go to Azure Portal > Azure Active Directory > App registrations")
        print("2. Create or update your app registration with:")
        print(f"   • Redirect URI: http://localhost:4999/api/auth/sso/azure/callback")
        print(f"   • Application type: Public client/native (mobile & desktop)")
        print(f"   • Supported account types: Your choice")
        print("3. Under 'Authentication' settings:")
        print("   • Enable 'Allow public client flows': Yes")
        print("   • Add platform: Single-page application or Mobile/Desktop")
        print("4. Under 'API permissions', add:")
        print("   • Microsoft Graph > User.Read (delegated)")
        print("   • Microsoft Graph > openid (delegated)")
        print("   • Microsoft Graph > profile (delegated)")
        print("   • Microsoft Graph > email (delegated)")

        print("\n🔧 Test Configuration:")
        print("-" * 40)
        print(f"Tenant ID: {test_tenant.id}")
        print(f"Tenant Name: {test_tenant.name}")
        print(f"Admin User: {admin_email}")
        print(f"Auth Method: {test_tenant.auth_method}")
        print(f"Auto-provisioning: {test_tenant.sso_auto_provisioning}")

        print("\n🌐 Test URLs:")
        print("-" * 40)
        print(f"1. Check SSO availability:")
        print(f"   GET http://localhost:4999/api/auth/sso/check-availability/{test_tenant.id}")

        print(f"\n2. Initiate SSO login:")
        print(f"   GET http://localhost:4999/api/auth/sso/azure/login/{test_tenant.id}")

        print(f"\n3. Get SSO configuration (requires JWT auth):")
        print(f"   GET http://localhost:4999/api/tenants/{test_tenant.id}/sso/config")

        print(f"\n4. Validate SSO configuration (requires JWT auth):")
        print(f"   GET http://localhost:4999/api/tenants/{test_tenant.id}/sso/config/validate")

        print("\n🔐 Testing with curl:")
        print("-" * 40)
        print("# First, login as admin to get JWT token:")
        print(f'''curl -X POST http://localhost:4999/api/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{{"email": "{admin_email}", "password": "12345678!"}}'
''')

        print("\n# Then use the token to check SSO config:")
        print(f'''curl -X GET http://localhost:4999/api/tenants/{test_tenant.id}/sso/config \\
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
''')

        print("\n✨ SSO is now configured and ready for testing!")
        print("="*60 + "\n")


def cleanup_test_data():
    """
    Clean up test data.
    """
    app = create_app()

    with app.app_context():
        print("\n=== Cleaning up Test Data ===\n")

        # Find and delete test tenant
        test_tenant = Tenant.query.filter_by(name="SSO Test Company").first()

        if test_tenant:
            # Delete tenant database
            if test_tenant.database_exists():
                test_tenant.delete_database(confirm=True)
                print(f"  ✓ Deleted tenant database: {test_tenant.database_name}")

            # Delete tenant record
            db.session.delete(test_tenant)
            db.session.commit()
            print(f"  ✓ Deleted tenant: {test_tenant.name}")
        else:
            print("  → No test tenant found")

        print("\n✅ Cleanup complete!\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup and test Azure SSO integration")
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='Clean up test data instead of creating it'
    )

    args = parser.parse_args()

    if args.cleanup:
        cleanup_test_data()
    else:
        setup_test_tenant_with_sso()