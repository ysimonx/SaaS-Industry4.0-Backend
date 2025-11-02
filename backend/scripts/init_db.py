#!/usr/bin/env python
"""
Database Initialization Script

This script initializes the SaaS platform database:
1. Creates the main database if it doesn't exist
2. Runs Flask-Migrate migrations for main DB schema
3. Optionally creates an initial admin user
4. Optionally creates a test tenant with database and tables

Usage:
    # Initialize database only (no seed data)
    python scripts/init_db.py

    # Initialize with admin user
    python scripts/init_db.py --create-admin

    # Initialize with admin user and test tenant
    python scripts/init_db.py --create-admin --create-test-tenant

    # Non-interactive mode (use environment variables)
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=password123 \
    python scripts/init_db.py --create-admin --non-interactive

    # Drop all data and reinitialize (DANGEROUS!)
    python scripts/init_db.py --drop-all --create-admin --create-test-tenant

Environment Variables:
    ADMIN_EMAIL: Email for admin user (default: admin@example.com)
    ADMIN_PASSWORD: Password for admin user (default: prompted)
    ADMIN_FIRST_NAME: First name (default: Admin)
    ADMIN_LAST_NAME: Last name (default: User)
    TEST_TENANT_NAME: Name for test tenant (default: Test Tenant)
"""

import os
import sys
import argparse
import getpass
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from flask_migrate import upgrade as migrate_upgrade
from app import create_app
from app.extensions import db
from app.models import User, Tenant, UserTenantAssociation
from app.utils.database import tenant_db_manager
from app.config import config


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Initialize SaaS platform database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--create-admin',
        action='store_true',
        help='Create initial admin user'
    )
    parser.add_argument(
        '--create-test-tenant',
        action='store_true',
        help='Create test tenant with database and tables'
    )
    parser.add_argument(
        '--drop-all',
        action='store_true',
        help='Drop all existing data before initialization (DANGEROUS!)'
    )
    parser.add_argument(
        '--non-interactive',
        action='store_true',
        help='Non-interactive mode (use environment variables)'
    )
    parser.add_argument(
        '--config',
        default='development',
        choices=['development', 'production', 'testing'],
        help='Configuration to use (default: development)'
    )
    return parser.parse_args()


def create_database_if_not_exists(database_url):
    """
    Create the main database if it doesn't exist.

    Args:
        database_url: PostgreSQL connection URL

    Returns:
        bool: True if database was created, False if it already existed
    """
    print("\n" + "="*60)
    print("STEP 1: Checking if main database exists")
    print("="*60)

    # Parse database URL to extract database name and connection parameters
    # Format: postgresql://user:password@host:port/database
    if '/' not in database_url:
        print("ERROR: Invalid database URL format")
        return False

    base_url = database_url.rsplit('/', 1)[0]
    db_name = database_url.rsplit('/', 1)[1].split('?')[0]  # Remove query params

    print(f"Database name: {db_name}")
    print(f"Base connection: {base_url}/postgres")

    # Connect to default 'postgres' database to check/create our database
    engine = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")

    try:
        with engine.connect() as conn:
            # Check if database exists
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": db_name}
            )
            exists = result.fetchone() is not None

            if exists:
                print(f"✓ Database '{db_name}' already exists")
                return False
            else:
                print(f"Creating database '{db_name}'...")
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print(f"✓ Database '{db_name}' created successfully")
                return True

    except OperationalError as e:
        print(f"ERROR: Could not connect to PostgreSQL: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure PostgreSQL is running")
        print("2. Check DATABASE_URL in .env file")
        print("3. Verify PostgreSQL user has CREATE DATABASE privilege")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to create database: {e}")
        sys.exit(1)
    finally:
        engine.dispose()


def run_migrations(app):
    """
    Run Flask-Migrate migrations to create/update main database schema.

    Args:
        app: Flask application instance
    """
    print("\n" + "="*60)
    print("STEP 2: Running database migrations")
    print("="*60)

    with app.app_context():
        try:
            # Check if migrations directory exists
            migrations_dir = backend_dir / 'migrations'
            if not migrations_dir.exists():
                print("ERROR: Migrations directory not found")
                print(f"Expected location: {migrations_dir}")
                print("\nPlease run: flask db init")
                sys.exit(1)

            # Run migrations
            print("Applying migrations...")
            migrate_upgrade()
            print("✓ Migrations applied successfully")

            # Verify tables were created
            with db.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT tablename FROM pg_tables
                        WHERE schemaname = 'public'
                        ORDER BY tablename
                    """)
                )
                tables = [row[0] for row in result]

            print(f"\nCreated tables ({len(tables)}):")
            for table in tables:
                print(f"  - {table}")

            # Check for required tables
            required_tables = ['users', 'tenants', 'user_tenant_associations']
            missing_tables = [t for t in required_tables if t not in tables]

            if missing_tables:
                print(f"\nWARNING: Some required tables are missing: {missing_tables}")
                print("You may need to create a migration: flask db migrate")
            else:
                print("\n✓ All required tables present")

        except Exception as e:
            print(f"ERROR: Migration failed: {e}")
            print("\nTroubleshooting:")
            print("1. Check if migrations are up to date: flask db current")
            print("2. Create a migration if needed: flask db migrate")
            print("3. Check migration files in migrations/versions/")
            sys.exit(1)


def create_admin_user(app, interactive=True):
    """
    Create an initial admin user.

    Args:
        app: Flask application instance
        interactive: If True, prompt for user input; if False, use environment variables

    Returns:
        User: Created user object or None if user already exists
    """
    print("\n" + "="*60)
    print("STEP 3: Creating admin user")
    print("="*60)

    with app.app_context():
        try:
            # Get user details from environment or prompt
            if interactive:
                print("\nEnter admin user details:")
                email = input("Email (default: admin@example.com): ").strip() or "admin@example.com"
                first_name = input("First name (default: Admin): ").strip() or "Admin"
                last_name = input("Last name (default: User): ").strip() or "User"
                password = getpass.getpass("Password (min 8 chars): ").strip()

                if len(password) < 8:
                    print("ERROR: Password must be at least 8 characters")
                    return None
            else:
                email = os.getenv('ADMIN_EMAIL', 'admin@example.com')
                first_name = os.getenv('ADMIN_FIRST_NAME', 'Admin')
                last_name = os.getenv('ADMIN_LAST_NAME', 'User')
                password = os.getenv('ADMIN_PASSWORD')

                if not password:
                    print("ERROR: ADMIN_PASSWORD environment variable is required in non-interactive mode")
                    return None

                if len(password) < 8:
                    print("ERROR: ADMIN_PASSWORD must be at least 8 characters")
                    return None

            # Check if user already exists
            existing_user = User.find_by_email(email)
            if existing_user:
                print(f"\n✓ Admin user already exists: {email}")
                print(f"   ID: {existing_user.id}")
                print(f"   Name: {existing_user.get_full_name()}")
                print(f"   Active: {existing_user.is_active}")
                return existing_user

            # Create user
            print(f"\nCreating admin user: {email}")
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=True
            )
            user.set_password(password)

            db.session.add(user)
            db.session.commit()

            print(f"✓ Admin user created successfully")
            print(f"   ID: {user.id}")
            print(f"   Email: {user.email}")
            print(f"   Name: {user.get_full_name()}")

            return user

        except Exception as e:
            db.session.rollback()
            print(f"ERROR: Failed to create admin user: {e}")
            return None


def create_test_tenant(app, admin_user, interactive=True):
    """
    Create a test tenant with database and tables.

    Args:
        app: Flask application instance
        admin_user: User to be added as admin to the tenant
        interactive: If True, prompt for input; if False, use environment variables

    Returns:
        Tenant: Created tenant object or None if tenant already exists
    """
    print("\n" + "="*60)
    print("STEP 4: Creating test tenant")
    print("="*60)

    if not admin_user:
        print("ERROR: Admin user is required to create test tenant")
        return None

    with app.app_context():
        try:
            # Get tenant name from environment or prompt
            if interactive:
                tenant_name = input("\nTenant name (default: Test Tenant): ").strip() or "Test Tenant"
            else:
                tenant_name = os.getenv('TEST_TENANT_NAME', 'Test Tenant')

            # Check if tenant already exists
            existing_tenant = Tenant.find_by_name(tenant_name)
            if existing_tenant:
                print(f"\n✓ Test tenant already exists: {tenant_name}")
                print(f"   ID: {existing_tenant.id}")
                print(f"   Database: {existing_tenant.database_name}")
                print(f"   Active: {existing_tenant.is_active}")
                return existing_tenant

            # Create tenant
            print(f"\nCreating tenant: {tenant_name}")
            tenant = Tenant(
                name=tenant_name,
                is_active=True,
                created_by=admin_user.id
            )

            # Generate database name
            tenant.database_name = Tenant._generate_database_name(tenant_name)

            db.session.add(tenant)
            db.session.flush()  # Get tenant ID before creating database

            print(f"Tenant record created with ID: {tenant.id}")
            print(f"Database name: {tenant.database_name}")

            # Create tenant database
            print(f"\nCreating tenant database: {tenant.database_name}")
            tenant.create_database()
            print(f"✓ Tenant database created")

            # Create tables in tenant database
            print("Creating Document and File tables in tenant database...")
            tenant_db_manager.create_tenant_tables(tenant.database_name)
            print("✓ Tenant tables created")

            # Add admin user to tenant
            print(f"\nAdding {admin_user.email} as admin to tenant...")
            association = UserTenantAssociation.create_association(
                user_id=admin_user.id,
                tenant_id=tenant.id,
                role='admin'
            )
            db.session.add(association)

            db.session.commit()

            print(f"✓ Test tenant created successfully")
            print(f"   ID: {tenant.id}")
            print(f"   Name: {tenant.name}")
            print(f"   Database: {tenant.database_name}")
            print(f"   Admin: {admin_user.email}")

            return tenant

        except Exception as e:
            db.session.rollback()
            print(f"ERROR: Failed to create test tenant: {e}")
            import traceback
            traceback.print_exc()
            return None


def drop_all_data(app):
    """
    Drop all data from the database (DANGEROUS!).

    Args:
        app: Flask application instance
    """
    print("\n" + "="*60)
    print("WARNING: DROP ALL DATA")
    print("="*60)
    print("\nThis will delete ALL data from the database!")
    print("This action CANNOT be undone!")

    response = input("\nType 'DELETE EVERYTHING' to confirm: ").strip()

    if response != 'DELETE EVERYTHING':
        print("Aborted. No data was deleted.")
        return False

    with app.app_context():
        try:
            print("\nDropping all tables...")
            db.drop_all()
            print("✓ All tables dropped")

            print("\nRecreating tables...")
            db.create_all()
            print("✓ Tables recreated")

            return True

        except Exception as e:
            print(f"ERROR: Failed to drop tables: {e}")
            return False


def main():
    """Main initialization routine."""
    args = parse_args()

    print("="*60)
    print("SaaS Platform Database Initialization")
    print("="*60)
    print(f"Configuration: {args.config}")
    print(f"Backend directory: {backend_dir}")

    # Create Flask app
    app = create_app(args.config)

    # Get database URL from app config
    database_url = app.config.get('SQLALCHEMY_DATABASE_URI')
    if not database_url:
        print("ERROR: SQLALCHEMY_DATABASE_URI not configured")
        sys.exit(1)

    print(f"Database URL: {database_url.split('@')[1] if '@' in database_url else database_url}")

    # Step 0: Drop all data if requested
    if args.drop_all:
        if not drop_all_data(app):
            sys.exit(1)

    # Step 1: Create database if not exists
    create_database_if_not_exists(database_url)

    # Step 2: Run migrations
    run_migrations(app)

    # Step 3: Create admin user (optional)
    admin_user = None
    if args.create_admin:
        admin_user = create_admin_user(app, interactive=not args.non_interactive)
        if not admin_user:
            print("\nWARNING: Admin user creation failed")

    # Step 4: Create test tenant (optional)
    if args.create_test_tenant:
        if not admin_user:
            print("\nERROR: Cannot create test tenant without admin user")
            print("Please use --create-admin flag")
        else:
            test_tenant = create_test_tenant(app, admin_user, interactive=not args.non_interactive)
            if not test_tenant:
                print("\nWARNING: Test tenant creation failed")

    # Summary
    print("\n" + "="*60)
    print("INITIALIZATION COMPLETE")
    print("="*60)
    print("\nNext steps:")
    print("1. Start the Flask API: python run.py")
    print("2. Start the Kafka consumer: python -m app.worker.consumer")
    print("3. Test the API endpoints")

    if admin_user:
        print(f"\nAdmin user credentials:")
        print(f"  Email: {admin_user.email}")
        print(f"  Password: (as entered)")
        print(f"\nLogin endpoint: POST http://localhost:4999/api/auth/login")

    print("\n" + "="*60)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInitialization cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
