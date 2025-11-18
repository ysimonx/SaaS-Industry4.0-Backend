#!/bin/bash

# Script pour démarrer et configurer Healthchecks.io avec synchronisation des UUIDs
# Ce script s'assure que tous les checks existent avec les UUIDs spécifiés

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🏥 Starting Healthchecks.io with UUID synchronization..."

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
    docker-compose --env-file "$ENV_FILE" -f "$PROJECT_ROOT/../docker-compose.healthchecks.yml" up -d
    echo "⏳ Waiting for Healthchecks to be ready..."
    sleep 10
else
    echo "✓ Healthchecks containers are running"
fi

docker-compose up -d --force-recreate api && echo "✅ Monitoring worker recreated"

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

# Créer un compte admin si nécessaire
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

# Synchroniser les checks avec les UUIDs fournis
echo "🔄 Synchronizing Healthchecks with UUIDs from .env.healthchecks..."

cd "$PROJECT_ROOT/../backend"

# Exécuter le script de synchronisation
# TOUJOURS utiliser Docker car il a toutes les dépendances Python
if [ -f "scripts/ensure_healthchecks.py" ]; then
    echo "📊 Running ensure_healthchecks.py via Docker..."

    # Créer une copie temporaire du fichier .env.healthchecks avec l'URL localhost pour l'accès depuis l'hôte
    # (nécessaire car le script sera exécuté dans le conteneur API qui doit accéder au conteneur healthchecks)
    echo "📝 Creating temporary .env.healthchecks.local with Docker network URLs..."

    # Le conteneur API doit utiliser http://healthchecks:8000 (réseau Docker interne)
    cp "$ENV_FILE" .env.healthchecks

    # Exécuter dans le conteneur Docker
    if docker-compose ps api | grep -q "Up"; then
        docker-compose exec -T api python scripts/ensure_healthchecks.py --env-file .env.healthchecks
    else
        echo "⚠️  API container is not running. Starting it..."
        docker-compose up -d api
        sleep 5
        docker-compose exec -T api python scripts/ensure_healthchecks.py --env-file .env.healthchecks
    fi

    # Pas besoin de nettoyer car on utilise le fichier original
else
    echo "⚠️  ensure_healthchecks.py not found, skipping synchronization"
fi

echo ""
echo "✅ Healthchecks.io is ready!"
echo ""
echo "📊 Access points:"
echo "   - Web UI: http://localhost:8000"
echo "   - API: http://localhost:8000/api/v1/"
echo ""
echo "🔑 Default credentials (if just created):"
echo "   - Email: admin@example.com"
echo "   - Password: admin123"
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