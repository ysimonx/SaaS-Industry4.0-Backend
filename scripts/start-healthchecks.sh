#!/bin/bash

# Script pour démarrer Healthchecks avec le bon fichier d'environnement
# Usage: ./scripts/start-healthchecks.sh [up|down|restart|logs]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Naviguer vers le répertoire du projet
cd "$PROJECT_ROOT"

# Commande par défaut
COMMAND="${1:-up -d}"

echo "🏥 Gestion de Healthchecks.io..."

# Utiliser les deux fichiers .env et .env.healthchecks
if [ -f ".env.healthchecks" ]; then
    echo "📋 Utilisation de .env et .env.healthchecks"
    docker-compose --env-file .env --env-file .env.healthchecks -f docker-compose.healthchecks.yml $COMMAND
else
    echo "⚠️  Fichier .env.healthchecks non trouvé, utilisation de .env uniquement"
    docker-compose -f docker-compose.healthchecks.yml $COMMAND
fi

# Afficher le statut si on démarre ou redémarre
if [[ "$COMMAND" == *"up"* ]] || [[ "$COMMAND" == "restart" ]]; then
    echo ""
    echo "✅ Healthchecks status:"
    docker-compose -f docker-compose.healthchecks.yml ps
    echo ""
    echo "🌐 Interface disponible sur: http://localhost:8000"
fi