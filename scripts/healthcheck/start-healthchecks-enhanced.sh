#!/bin/bash

# Script pour démarrer et configurer Healthchecks.io avec synchronisation des UUIDs
# Ce script s'assure que tous les checks existent avec les UUIDs spécifiés

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🏥 Starting Healthchecks.io with UUID synchronization..."
echo "SCRIPT_DIR=$SCRIPT_DIR"
echo "PROJECT_ROOT=$PROJECT_ROOT"
rm -f "$PROJECT_ROOT/.healthchecks-admin-created"

# Charger les variables d'environnement
ENV_FILE="$PROJECT_ROOT/../.env.healthchecks"
if [ -f "$ENV_FILE" ]; then
    echo "📋 Loading configuration from .env.healthchecks..."
    export $(cat "$ENV_FILE" | grep -v '^#' | xargs)
else
    echo "❌ .env.healthchecks not found!"
    echo "   Please create it from .env.healthchecks.example"
    exit 1
fi

# Vérifier si les conteneurs sont en cours d'exécution
echo "🐳 Checking Docker containers..."

# Démarrer Healthchecks si nécessaire
if ! docker-compose -f "$PROJECT_ROOT/../docker-compose.healthchecks.yml" ps | grep -q "healthchecks.*Up"; then
    echo "🚀 Starting Healthchecks containers..."
    echo "docker-compose --env-file \"$ENV_FILE\" -f \"$PROJECT_ROOT/../docker-compose.healthchecks.yml\" up -d"
    docker-compose --env-file "$ENV_FILE" -f "$PROJECT_ROOT/../docker-compose.healthchecks.yml" up -d
    echo "⏳ Waiting for Healthchecks to be ready..."
    sleep 10
else
    echo "✓ Healthchecks containers are running"
fi

docker-compose up -d --force-recreate api && echo "✅ api container recreated"

docker-compose up -d --force-recreate celery-worker-monitoring && echo "✅ Monitoring worker recreated"

# Vérifier la connexion à Healthchecks
echo "🔍 Checking Healthchecks connectivity..."
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/status/ | grep -q "200"; then
        echo "✓ Healthchecks is responsive"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    echo "   Waiting for Healthchecks... (attempt $ATTEMPT/$MAX_ATTEMPTS)"
    sleep 2
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "❌ Healthchecks is not responding after $MAX_ATTEMPTS attempts"
    exit 1
fi

# Créer un compte admin et récupérer la clé API
if [ ! -f "$PROJECT_ROOT/.healthchecks-admin-created" ]; then
    echo "👤 Creating Healthchecks admin account..."

    # Utiliser le script de création d'admin
    if [ -f "$SCRIPT_DIR/create-healthchecks-admin.sh" ]; then
        bash "$SCRIPT_DIR/create-healthchecks-admin.sh"
        touch "$PROJECT_ROOT/.healthchecks-admin-created"
    else
        echo "⚠️  Admin creation script not found, skipping..."
    fi
else
    echo "✓ Admin account already exists"
fi

# Créer un projet par défaut et récupérer/générer la clé API
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
" 2>&1 | tee /dev/stderr | grep -v "^INFO:" | grep -v "^ERROR:" | grep -v "^Traceback" | grep -v "^  File" | grep -v "^    " | grep -v "^django\." | tail -n 1)

if [ -n "$API_KEY" ]; then
    echo "✓ API Key retrieved: ${API_KEY:0:10}..."

    # Mettre à jour le fichier .env.healthchecks avec la vraie clé API
    if grep -q "^HEALTHCHECKS_API_KEY=" "$ENV_FILE"; then
        # Remplacer l'ancienne clé
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s/^HEALTHCHECKS_API_KEY=.*/HEALTHCHECKS_API_KEY=$API_KEY/" "$ENV_FILE"
        else
            # Linux
            sed -i "s/^HEALTHCHECKS_API_KEY=.*/HEALTHCHECKS_API_KEY=$API_KEY/" "$ENV_FILE"
        fi
        echo "✓ Updated HEALTHCHECKS_API_KEY in .env.healthchecks"
    else
        # Ajouter la clé si elle n'existe pas
        echo "HEALTHCHECKS_API_KEY=$API_KEY" >> "$ENV_FILE"
        echo "✓ Added HEALTHCHECKS_API_KEY to .env.healthchecks"
    fi

    # Également mettre à jour HEALTHCHECKS_READ_KEY
    if grep -q "^HEALTHCHECKS_READ_KEY=" "$ENV_FILE"; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/^HEALTHCHECKS_READ_KEY=.*/HEALTHCHECKS_READ_KEY=$API_KEY/" "$ENV_FILE"
        else
            sed -i "s/^HEALTHCHECKS_READ_KEY=.*/HEALTHCHECKS_READ_KEY=$API_KEY/" "$ENV_FILE"
        fi
        echo "✓ Updated HEALTHCHECKS_READ_KEY in .env.healthchecks"
    fi

    # Exporter la clé API pour la suite du script
    export HEALTHCHECKS_API_KEY=$API_KEY
else
    echo "⚠️  Could not retrieve API key, using existing value from .env.healthchecks"
fi

# Synchroniser les checks avec les UUIDs fournis
echo "🔄 Synchronizing Healthchecks with UUIDs from .env.healthchecks..."

# Utiliser le nouveau script qui garantit les UUIDs via Django ORM
if [ -f "$SCRIPT_DIR/sync-healthchecks-uuids.sh" ]; then
    echo "📊 Running sync-healthchecks-uuids.sh..."
    bash "$SCRIPT_DIR/sync-healthchecks-uuids.sh"

    # Copier le fichier UPDATÉ dans le backend pour Docker
    echo "📝 Copying updated .env.healthchecks to backend..."
    cp "$ENV_FILE" "$PROJECT_ROOT/../backend/.env.healthchecks"

    # Recréer les conteneurs importants
    cd "$PROJECT_ROOT/../backend"
    docker-compose up -d --force-recreate celery-worker-monitoring && echo "✅ Monitoring worker recreated"
else
    echo "⚠️  sync-healthchecks-uuids.sh not found, skipping synchronization"
fi

# Supprime eventuellement les anciens checks (ou doublons)
echo "📊 Running cleanup-duplicate-checks..."
bash "$SCRIPT_DIR/cleanup-duplicate-checks.sh"



echo ""
echo "✅ Healthchecks.io is ready!"
echo ""
echo "📊 Access points:"
echo "   - Web UI: http://localhost:8000"
echo "   - API: http://localhost:8000/api/v1/"
echo ""
echo "🔑 Default credentials (if just created):"
echo "   - Email: admin@example.com"
echo "   - Password: 12345678"
echo ""
echo "📝 Check IDs from .env.healthchecks:"
echo "   HC_CHECK_POSTGRES: ${HC_CHECK_POSTGRES:-not set}"
echo "   HC_CHECK_REDIS: ${HC_CHECK_REDIS:-not set}"
echo "   HC_CHECK_API: ${HC_CHECK_API:-not set}"
echo "   HC_CHECK_CELERY_WORKER: ${HC_CHECK_CELERY_WORKER:-not set}"
echo "   HC_CHECK_CELERY_BEAT: ${HC_CHECK_CELERY_BEAT:-not set}"
echo ""
echo "🎯 Next steps:"
echo "   1. Access the web UI and verify checks are created"
echo "   2. Configure alert channels (email, Slack, etc.)"
echo "   3. Restart API and Celery workers to start monitoring"
echo "   4. Test: docker-compose exec api python -m app.tasks.monitoring_tasks"