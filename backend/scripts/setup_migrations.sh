#!/bin/bash
# Script to initialize Flask-Migrate (Alembic) migrations
# This must be run before init_db.py can apply migrations

set -e  # Exit on error

echo "============================================================"
echo "Flask-Migrate (Alembic) Setup Script"
echo "============================================================"

cd "$(dirname "$0")/.."  # Navigate to backend directory

# Check if migrations directory exists and is initialized
if [ -f "migrations/env.py" ]; then
    echo "✓ Migrations already initialized"
    echo "  Found: migrations/env.py"
    exit 0
fi

echo ""
echo "Initializing Flask-Migrate migrations directory..."
echo ""

# Initialize migrations
export FLASK_APP=run.py
flask db init

if [ -f "migrations/env.py" ]; then
    echo ""
    echo "✓ Migrations initialized successfully"
    echo ""
    echo "Next steps:"
    echo "1. Create initial migration: flask db migrate -m 'Initial migration'"
    echo "2. Apply migrations: flask db upgrade"
    echo "3. Or run: python scripts/init_db.py --create-admin --create-test-tenant"
else
    echo ""
    echo "ERROR: Failed to initialize migrations"
    echo "Please check if Flask-Migrate is installed:"
    echo "  pip install Flask-Migrate"
    exit 1
fi
