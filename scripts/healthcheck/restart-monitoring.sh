#!/bin/bash

# Script pour redémarrer les services de monitoring avec les bonnes variables

# Obtenir le chemin du script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Naviguer vers le répertoire du projet
cd "$PROJECT_ROOT"

echo "🔄 Redémarrage des services de monitoring..."

# Charger les deux fichiers .env
if [ -f ".env.healthchecks" ]; then
    echo "📋 Chargement de .env et .env.healthchecks"

    # Exporter les variables de .env.healthchecks
    export $(grep -v '^#' .env.healthchecks | xargs)

    # Redémarrer les services de monitoring
    docker-compose --env-file .env --env-file .env.healthchecks \
        up -d --force-recreate \
        celery-worker-monitoring celery-beat

    echo "✅ Services redémarrés avec les variables Healthchecks"

    # Attendre un peu
    sleep 5

    # Vérifier le statut
    echo ""
    echo "📊 Statut des services:"
    docker-compose ps celery-worker-monitoring celery-beat

    echo ""
    echo "🔍 Vérification des variables dans le worker:"
    docker-compose exec celery-worker-monitoring env | grep HC_CHECK_ | head -5
else
    echo "❌ Fichier .env.healthchecks non trouvé"
    exit 1
fi