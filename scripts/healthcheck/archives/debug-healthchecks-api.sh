#!/bin/bash
# Script de débogage pour comprendre la structure de Healthchecks.io

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🔍 Debugging Healthchecks.io structure..."
echo ""

# Vérifier l'utilisateur admin
echo "👤 Checking admin user..."
docker-compose -f "$PROJECT_ROOT/../docker-compose.healthchecks.yml" exec healthchecks python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hc.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()
try:
    user = User.objects.get(email='admin@example.com')
    print(f'✓ User found: {user.email}')
    print(f'  - ID: {user.id}')
    print(f'  - Username: {user.username}')
    print(f'  - Is superuser: {user.is_superuser}')
except Exception as e:
    print(f'❌ Error: {e}')
"

echo ""
echo "📊 Checking Project model structure..."
docker-compose -f "$PROJECT_ROOT/../docker-compose.healthchecks.yml" exec healthchecks python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hc.settings')
django.setup()

from hc.api.models import Project
from django.contrib.auth import get_user_model

print('Project model fields:')
for field in Project._meta.get_fields():
    print(f'  - {field.name} ({type(field).__name__})')
"

echo ""
echo "📋 Listing existing projects..."
docker-compose -f "$PROJECT_ROOT/../docker-compose.healthchecks.yml" exec healthchecks python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hc.settings')
django.setup()

from hc.api.models import Project
from django.contrib.auth import get_user_model

User = get_user_model()
try:
    user = User.objects.get(email='admin@example.com')
    projects = Project.objects.filter(owner=user)

    if projects.exists():
        print(f'✓ Found {projects.count()} project(s):')
        for p in projects:
            print(f'  - Name: {p.name}')
            print(f'    Code: {p.code}')
            print(f'    API Key: {p.api_key}')
            print(f'    Owner: {p.owner.email}')
            print()
    else:
        print('⚠️  No projects found for this user')
        print()
        print('All projects in database:')
        all_projects = Project.objects.all()
        if all_projects.exists():
            for p in all_projects:
                print(f'  - {p.name} (owner: {p.owner.email})')
        else:
            print('  No projects at all in database')
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
"

echo ""
echo "🔧 Attempting to create a project..."
docker-compose -f "$PROJECT_ROOT/../docker-compose.healthchecks.yml" exec healthchecks python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hc.settings')
django.setup()

from hc.api.models import Project
from django.contrib.auth import get_user_model

User = get_user_model()
try:
    user = User.objects.get(email='admin@example.com')

    # Essayer de créer un projet
    project = Project.objects.create(
        owner=user,
        name='SaaS Backend Monitoring'
    )

    print(f'✓ Project created successfully!')
    print(f'  - Name: {project.name}')
    print(f'  - Code: {project.code}')
    print(f'  - API Key: {project.api_key}')
    print(f'  - API Key (readonly): {project.api_key_readonly}')

except Exception as e:
    print(f'❌ Error creating project: {e}')
    import traceback
    traceback.print_exc()
"

echo ""
echo "✅ Debug complete!"
