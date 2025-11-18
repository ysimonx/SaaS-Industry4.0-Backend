#!/bin/bash
# Script pour récupérer ou créer l'API key du projet Healthchecks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🔑 Getting or creating Healthchecks API key..."

API_KEY=$(docker-compose -f "$PROJECT_ROOT/../docker-compose.healthchecks.yml" exec -T healthchecks python -c "
import os
import sys
import django
import secrets
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hc.settings')
django.setup()

from hc.api.models import Project
from django.contrib.auth import get_user_model

User = get_user_model()

def generate_api_key():
    '''Generate a random API key similar to Healthchecks format'''
    return secrets.token_urlsafe(24)

try:
    user = User.objects.get(email='admin@example.com')

    # Récupérer ou créer le projet
    project, created = Project.objects.get_or_create(
        owner=user,
        defaults={'name': 'SaaS Backend'}
    )

    # Si c'est le premier projet de l'utilisateur, utiliser le nom par défaut
    if created:
        project.name = 'SaaS Backend'
        project.save()
        print('INFO: Created new project', file=sys.stderr)

    # Vérifier si l'API key existe et n'est pas vide
    if not project.api_key or project.api_key.strip() == '':
        # Générer une nouvelle API key
        project.api_key = generate_api_key()
        project.save()
        print('INFO: Generated new API key', file=sys.stderr)
    else:
        print('INFO: Using existing API key', file=sys.stderr)

    # Afficher l'API key
    print(project.api_key)

except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    print('')
" 2>&1 | tee /dev/stderr | grep -v "^INFO:" | grep -v "^ERROR:" | tail -n 1)

if [ -n "$API_KEY" ] && [ "$API_KEY" != "" ]; then
    echo "✓ API Key: ${API_KEY:0:10}..."
    echo "$API_KEY"
else
    echo "❌ Failed to get API key"
    exit 1
fi
