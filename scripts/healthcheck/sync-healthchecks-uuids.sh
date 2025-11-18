#!/bin/bash
#
# Script pour synchroniser les checks Healthchecks.io avec les UUIDs de .env.healthchecks
# Utilise Django ORM directement pour garantir les UUIDs corrects
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "🔄 Synchronizing Healthchecks with UUIDs from .env.healthchecks..."

# Vérifier que le fichier .env.healthchecks existe
ENV_FILE="$PROJECT_ROOT/.env.healthchecks"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env.healthchecks not found at $ENV_FILE"
    exit 1
fi

# Vérifier que le script Python existe
PYTHON_SCRIPT="$PROJECT_ROOT/backend/scripts/ensure_healthchecks_with_uuid.py"
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "❌ ensure_healthchecks_with_uuid.py not found at $PYTHON_SCRIPT"
    exit 1
fi

# Détecter le nom du conteneur Healthchecks
HEALTHCHECKS_CONTAINER=$(docker-compose -f "$PROJECT_ROOT/docker-compose.healthchecks.yml" ps -q healthchecks)
if [ -z "$HEALTHCHECKS_CONTAINER" ]; then
    echo "❌ Healthchecks container is not running"
    echo "   Please start it first with: docker-compose -f docker-compose.healthchecks.yml up -d"
    exit 1
fi

# Copier le fichier .env.healthchecks dans le conteneur Healthchecks
echo "📋 Copying .env.healthchecks to Healthchecks container..."
docker cp "$ENV_FILE" "$HEALTHCHECKS_CONTAINER:/opt/healthchecks/.env.healthchecks"

# Copier le script Python dans le conteneur
echo "📋 Copying sync script to Healthchecks container..."
docker cp "$PYTHON_SCRIPT" "$HEALTHCHECKS_CONTAINER:/opt/healthchecks/ensure_healthchecks_with_uuid.py"

# Exécuter le script dans le conteneur via Django shell
echo "🚀 Executing sync script in Healthchecks container..."
docker-compose -f "$PROJECT_ROOT/docker-compose.healthchecks.yml" exec -T healthchecks python -c "
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hc.settings')
django.setup()

# Charger et exécuter le script
ENV_FILE = '/opt/healthchecks/.env.healthchecks'
exec(open('/opt/healthchecks/ensure_healthchecks_with_uuid.py').read())
ensure_checks_with_uuid(ENV_FILE)
"

echo ""
echo "✅ UUID synchronization complete!"
echo ""
echo "📊 Access Healthchecks UI: http://localhost:8000"
echo "   Email: admin@example.com"
echo "   Password: 12345678"
