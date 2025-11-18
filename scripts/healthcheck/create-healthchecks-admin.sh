#!/bin/bash
# ============================================================================
# Script: create-healthchecks-admin.sh
# Description: Creates the Healthchecks.io admin account
# Usage: ./scripts/create-healthchecks-admin.sh [username] [email] [password]
# ============================================================================

set -e

# Default values
DEFAULT_USERNAME="admin"
DEFAULT_EMAIL="admin@example.com"
DEFAULT_PASSWORD="12345678"

# Get parameters or use defaults
USERNAME="${1:-$DEFAULT_USERNAME}"
EMAIL="${2:-$DEFAULT_EMAIL}"
PASSWORD="${3:-$DEFAULT_PASSWORD}"

echo "================================================"
echo "Creating Healthchecks.io Admin Account"
echo "================================================"
echo "Username: $USERNAME"
echo "Email: $EMAIL"
echo "Password: $PASSWORD"
echo "================================================"
echo ""

# Check if Healthchecks container is running
if ! docker ps --format '{{.Names}}' | grep -q 'saas-healthchecks'; then
    echo "❌ Error: Healthchecks container is not running!"
    echo ""
    echo "Start Healthchecks with:"
    echo "  docker-compose -f docker-compose.healthchecks.yml up -d"
    exit 1
fi

# Create admin account
docker-compose -f docker-compose.healthchecks.yml exec healthchecks python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hc.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

username = '$USERNAME'
email = '$EMAIL'
password = '$PASSWORD'

try:
    if not User.objects.filter(email=email).exists():
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        print('✅ Superuser created successfully!')
        print(f'   Username: {username}')
        print(f'   Email: {email}')
        print(f'   Password: {password}')
    else:
        print(f'⚠️  User {email} already exists')
        user = User.objects.get(email=email)
        user.set_password(password)
        user.is_superuser = True
        user.is_staff = True
        user.save()
        print('✅ Password updated!')
        print(f'   New password: {password}')
except Exception as e:
    print(f'❌ Error: {e}')
    exit(1)
" 2>&1 | grep -v 'warning msg='

echo ""
echo "================================================"
echo "Login Information"
echo "================================================"
echo "URL: http://localhost:8000/accounts/login/"
echo "Username: $USERNAME (or Email: $EMAIL)"
echo "Password: $PASSWORD"
echo ""
echo "⚠️  IMPORTANT: Change this password in production!"
echo "================================================"
