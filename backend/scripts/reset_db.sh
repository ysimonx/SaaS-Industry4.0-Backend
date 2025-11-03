#!/bin/bash
# Script to completely reset the database and migrations
# This is useful for development when you want to start fresh
#
# USAGE:
#   From host:     ./backend/scripts/reset_db.sh
#   From Docker:   docker-compose exec api bash scripts/reset_db.sh

set -e  # Exit on error

echo "============================================================"
echo "SaaS Platform - Complete Database Reset"
echo "============================================================"
echo ""
echo "This will:"
echo "  1. Remove old migration files"
echo "  2. Drop the saas_platform database"
echo "  3. Create a fresh saas_platform database"
echo "  4. Generate a new migration from models"
echo "  5. Apply the migration to create all tables"
echo ""
echo "WARNING: This will DELETE ALL DATA!"
echo ""

# Detect if running inside Docker container API service
# We check for /.dockerenv AND if we're in the api container
if [ -f "/.dockerenv" ] && [ -f "/app/run.py" ]; then
    # Running inside Docker api container
    echo "Detected: Running inside Docker API container"
    FLASK_CMD="flask"
    PYTHON_CMD="python"
    # Use docker-compose from inside container to access postgres
    # This won't work - we need to call postgres container differently
    echo ""
    echo "ERROR: This script cannot be run from inside the API container."
    echo "Please run it from the host machine instead:"
    echo ""
    echo "  ./backend/scripts/reset_db.sh"
    echo ""
    echo "Or use the manual commands from inside the API container:"
    echo "  # From another terminal on host:"
    echo "  docker-compose exec postgres psql -U postgres -c \"DROP DATABASE IF EXISTS saas_platform;\""
    echo "  docker-compose exec postgres psql -U postgres -c \"CREATE DATABASE saas_platform;\""
    echo "  # Then from API container:"
    echo "  flask db migrate -m \"Initial migration\""
    echo "  flask db upgrade"
    exit 1
else
    # Running on host - use docker-compose exec
    echo "Detected: Running on host machine"
    FLASK_CMD="docker-compose exec -T api flask"
    PYTHON_CMD="docker-compose exec -T api python"
    PSQL_CMD="docker-compose exec -T postgres psql -U postgres"
fi

# Confirmation
read -p "Type 'yes' to continue: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "============================================================"
echo "Step 1: Cleaning old migration files"
echo "============================================================"
# Remove all migration files from versions directory
if [ -d "backend/migrations/versions" ]; then
    rm -f backend/migrations/versions/*.py
    echo "✓ Removed old migration files"
else
    echo "✓ No old migration files to remove"
fi

echo ""
echo "============================================================"
echo "Step 2: Dropping database"
echo "============================================================"
$PSQL_CMD -c "DROP DATABASE IF EXISTS saas_platform;" || {
    echo "Warning: Could not drop database (may not exist)"
}

echo ""
echo "============================================================"
echo "Step 3: Creating fresh database"
echo "============================================================"
$PSQL_CMD -c "CREATE DATABASE saas_platform;" || {
    echo "Error: Failed to create database"
    exit 1
}

echo ""
echo "============================================================"
echo "Step 4: Generating migration from models"
echo "============================================================"
$FLASK_CMD db migrate -m "Initial migration: User, Tenant, UserTenantAssociation" || {
    echo "Error: Failed to generate migration"
    exit 1
}

echo ""
echo "============================================================"
echo "Step 5: Applying migration"
echo "============================================================"
$FLASK_CMD db upgrade || {
    echo "Error: Failed to apply migration"
    exit 1
}

echo ""
echo "============================================================"
echo "Step 6: Verifying tables"
echo "============================================================"
$PSQL_CMD -d saas_platform -c "\dt"

echo ""
echo "============================================================"
echo "SUCCESS - Database reset complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Create admin user and test tenant:"
echo "     docker-compose exec api python scripts/init_db.py --create-admin --create-test-tenant"
echo ""
echo "  2. Or just start the API:"
echo "     docker-compose up api"
echo ""
echo "============================================================"
