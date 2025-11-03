#!/usr/bin/env python
"""
Flask-Migrate (Alembic) Setup Script

This script initializes the migrations directory for Flask-Migrate.
It must be run before init_db.py can apply migrations.

Usage:
    # In Docker:
    docker-compose exec api python scripts/setup_migrations.py

    # Locally:
    python scripts/setup_migrations.py
"""

import os
import sys
import subprocess
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)


def check_migrations_initialized():
    """Check if migrations directory is already initialized."""
    migrations_dir = backend_dir / 'migrations'
    env_py = migrations_dir / 'env.py'

    if env_py.exists():
        print("✓ Migrations already initialized")
        print(f"  Found: {env_py}")
        return True
    return False


def handle_incomplete_migrations():
    """Handle case where migrations directory exists but is incomplete."""
    migrations_dir = backend_dir / 'migrations'

    if not migrations_dir.exists():
        return False

    # Check if directory is empty or only contains README
    contents = list(migrations_dir.iterdir())
    is_incomplete = len(contents) == 0 or (
        len(contents) == 1 and contents[0].name == 'README.md'
    )

    if is_incomplete:
        print("⚠ Found incomplete migrations directory")
        print(f"  Contents: {[f.name for f in contents]}")
        print("\nRemoving incomplete migrations directory...")

        import shutil
        shutil.rmtree(migrations_dir)
        print("✓ Removed incomplete migrations directory")
        return True

    return False


def initialize_migrations():
    """Initialize Flask-Migrate migrations directory."""
    print("="*60)
    print("Flask-Migrate (Alembic) Setup")
    print("="*60)
    print()

    if check_migrations_initialized():
        print("\nMigrations are ready to use!")
        print("\nNext steps:")
        print("1. Create initial migration: flask db migrate -m 'Initial migration'")
        print("2. Apply migrations: flask db upgrade")
        print("3. Or run: python scripts/init_db.py --create-admin --create-test-tenant")
        return True

    # Handle incomplete migrations directory
    handle_incomplete_migrations()

    print("Initializing migrations directory...")
    print()

    try:
        # Set FLASK_APP environment variable
        os.environ['FLASK_APP'] = 'run.py'

        # Run flask db init
        result = subprocess.run(
            ['flask', 'db', 'init'],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            print("ERROR: Failed to initialize migrations")
            print(f"stdout: {result.stdout}")
            print(f"stderr: {result.stderr}")
            print("\nPossible issues:")
            print("1. Flask-Migrate not installed: pip install Flask-Migrate")
            print("2. Database connection issues")
            print("3. FLASK_APP environment variable not set correctly")
            return False

        print(result.stdout)

        # Verify initialization
        if check_migrations_initialized():
            print("\n✓ Migrations initialized successfully!")
            print()
            print("Next steps:")
            print("1. Create initial migration:")
            print("   docker-compose exec api flask db migrate -m 'Initial migration'")
            print()
            print("2. Apply migrations (or use init_db.py):")
            print("   docker-compose exec api flask db upgrade")
            print()
            print("3. Or run full initialization:")
            print("   docker-compose exec api python scripts/init_db.py --create-admin --create-test-tenant")
            return True
        else:
            print("\nERROR: Migrations directory not created")
            print("Please check the output above for errors")
            return False

    except FileNotFoundError:
        print("ERROR: 'flask' command not found")
        print("\nPlease ensure you are in the correct environment:")
        print("1. In Docker: docker-compose exec api python scripts/setup_migrations.py")
        print("2. Locally: activate your virtual environment first")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    print(f"Working directory: {backend_dir}")
    print()

    success = initialize_migrations()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
