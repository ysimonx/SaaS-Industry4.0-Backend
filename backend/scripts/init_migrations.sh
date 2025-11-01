#!/bin/bash

# Database Migrations Initialization Script
# This script initializes Flask-Migrate and creates the initial migration
# for the main database (User, Tenant, UserTenantAssociation tables)

set -e  # Exit on error

echo "========================================="
echo "Flask Database Migrations Initialization"
echo "========================================="
echo ""

# Navigate to backend directory
cd "$(dirname "$0")/.."
echo "Working directory: $(pwd)"
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "WARNING: Virtual environment not activated!"
    echo "Please activate your virtual environment first:"
    echo "  source venv/bin/activate  (Linux/Mac)"
    echo "  venv\\Scripts\\activate     (Windows)"
    echo ""
    exit 1
fi

# Set Flask app
export FLASK_APP=run

# Check if migrations directory already exists
if [ -d "migrations" ]; then
    echo "Migrations directory already exists."
    echo "Skipping 'flask db init'..."
else
    echo "Step 1: Initializing Flask-Migrate..."
    flask db init
    echo "✓ Flask-Migrate initialized"
    echo ""
fi

# Create initial migration
echo "Step 2: Creating initial migration..."
echo "This will create migration for User, Tenant, and UserTenantAssociation tables"
flask db migrate -m "Initial migration: users, tenants, user_tenant_associations"
echo "✓ Initial migration created"
echo ""

# Apply migration
echo "Step 3: Applying migration to database..."
flask db upgrade
echo "✓ Migration applied successfully"
echo ""

echo "========================================="
echo "Database migrations setup complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Review the generated migration in migrations/versions/"
echo "  2. Create a test tenant: python scripts/create_test_data.py"
echo "  3. Run the application: python run.py"
echo ""
echo "Useful commands:"
echo "  flask db migrate -m 'description'  - Create new migration"
echo "  flask db upgrade                   - Apply migrations"
echo "  flask db downgrade                 - Rollback migration"
echo "  flask db history                   - Show migration history"
echo "  flask db current                   - Show current migration"
echo ""
