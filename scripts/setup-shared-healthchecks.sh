#!/bin/bash

# Script de configuration pour utiliser une instance Healthchecks.io partagée
# au lieu de multiples instances Docker locales

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🏥 Configuration de Healthchecks.io partagé"
echo "==========================================="
echo ""
echo "Ce script configure votre projet pour utiliser une instance"
echo "Healthchecks.io UNIQUE partagée entre tous vos environnements."
echo ""

# Fonction pour valider une URL
validate_url() {
    if [[ $1 =~ ^https?://[a-zA-Z0-9.-]+(:[0-9]+)?(/.*)?$ ]]; then
        return 0
    else
        return 1
    fi
}

# Menu de sélection
echo "Choisissez votre configuration :"
echo ""
echo "1) Utiliser healthchecks.io (SaaS - Recommandé pour la production)"
echo "2) Utiliser une instance Healthchecks auto-hébergée existante"
echo "3) Créer une nouvelle instance centrale (guide)"
echo "4) Environnement de développement local uniquement"
echo ""
read -p "Votre choix (1-4): " choice

case $choice in
    1)
        echo ""
        echo "📡 Configuration pour healthchecks.io (SaaS)"
        echo "--------------------------------------------"
        echo ""
        echo "1. Créez un compte sur https://healthchecks.io"
        echo "2. Créez un nouveau projet"
        echo "3. Récupérez l'API key du projet"
        echo ""
        read -p "Entrez votre API key: " api_key
        read -p "Entrez votre Read-Only API key (optionnel, Enter pour ignorer): " read_key

        cat > "$PROJECT_ROOT/.env.healthchecks" <<EOF
# ============================================================================
# Healthchecks.io Configuration - SaaS
# ============================================================================

# Service Configuration
HEALTHCHECKS_ENABLED=true
HEALTHCHECKS_HOST=https://healthchecks.io
HEALTHCHECKS_API_URL=https://healthchecks.io/api/v1
HEALTHCHECKS_PING_URL=https://hc-ping.com

# API Keys (partagées entre tous les environnements)
HEALTHCHECKS_API_KEY=$api_key
$([ -n "$read_key" ] && echo "HEALTHCHECKS_READ_KEY=$read_key")

# Settings
HEALTHCHECKS_CHECK_TIMEOUT=30
HEALTHCHECKS_RETRY_COUNT=3
HEALTHCHECKS_RETRY_DELAY=10
HEALTHCHECKS_AUTO_PROVISION=true

# Check UUIDs (seront générés automatiquement au premier ping)
HC_CHECK_API=
HC_CHECK_POSTGRES=
HC_CHECK_REDIS=
HC_CHECK_CELERY_WORKER=
HC_CHECK_CELERY_BEAT=
HC_CHECK_KAFKA=
HC_CHECK_KAFKA_CONSUMER=
HC_CHECK_MINIO=
HC_CHECK_VAULT=
HC_CHECK_SSO_TOKEN_REFRESH=
HC_CHECK_HEALTH_TASK=
HC_CHECK_TOKEN_CLEANUP=
HC_CHECK_KEY_ROTATION=
HC_CHECK_COMPREHENSIVE=
EOF

        echo ""
        echo "✅ Configuration créée pour healthchecks.io"
        ;;

    2)
        echo ""
        echo "🏠 Configuration pour instance auto-hébergée"
        echo "--------------------------------------------"
        echo ""

        # Demander l'URL de l'instance
        while true; do
            read -p "URL de votre instance Healthchecks (ex: https://monitoring.example.com): " instance_url
            if validate_url "$instance_url"; then
                break
            else
                echo "❌ URL invalide. Veuillez entrer une URL valide (http:// ou https://)"
            fi
        done

        read -p "API key de votre projet: " api_key
        read -p "Read-Only API key (optionnel, Enter pour ignorer): " read_key

        # Retirer le slash final si présent
        instance_url=${instance_url%/}

        cat > "$PROJECT_ROOT/.env.healthchecks" <<EOF
# ============================================================================
# Healthchecks.io Configuration - Auto-hébergé
# ============================================================================

# Service Configuration
HEALTHCHECKS_ENABLED=true
HEALTHCHECKS_HOST=$instance_url
HEALTHCHECKS_API_URL=$instance_url/api/v1
HEALTHCHECKS_PING_URL=$instance_url/ping

# API Keys (partagées entre tous les environnements)
HEALTHCHECKS_API_KEY=$api_key
$([ -n "$read_key" ] && echo "HEALTHCHECKS_READ_KEY=$read_key")

# Settings
HEALTHCHECKS_CHECK_TIMEOUT=30
HEALTHCHECKS_RETRY_COUNT=3
HEALTHCHECKS_RETRY_DELAY=10
HEALTHCHECKS_AUTO_PROVISION=true

# Check UUIDs (seront générés automatiquement au premier ping)
HC_CHECK_API=
HC_CHECK_POSTGRES=
HC_CHECK_REDIS=
HC_CHECK_CELERY_WORKER=
HC_CHECK_CELERY_BEAT=
HC_CHECK_KAFKA=
HC_CHECK_KAFKA_CONSUMER=
HC_CHECK_MINIO=
HC_CHECK_VAULT=
HC_CHECK_SSO_TOKEN_REFRESH=
HC_CHECK_HEALTH_TASK=
HC_CHECK_TOKEN_CLEANUP=
HC_CHECK_KEY_ROTATION=
HC_CHECK_COMPREHENSIVE=
EOF

        echo ""
        echo "✅ Configuration créée pour $instance_url"
        ;;

    3)
        echo ""
        echo "🚀 Guide de création d'une instance centrale"
        echo "--------------------------------------------"
        echo ""
        echo "Pour créer une instance Healthchecks centrale :"
        echo ""
        echo "1. Sur un VPS ou serveur dédié accessible depuis Internet :"
        echo ""
        echo "   # Créer docker-compose.yml"
        cat > "$PROJECT_ROOT/healthchecks-central.yml" <<'EOF'
version: '3.8'

services:
  healthchecks:
    image: healthchecks/healthchecks:latest
    environment:
      - ALLOWED_HOSTS=*  # À restreindre en production
      - DB=postgres
      - DB_NAME=healthchecks
      - DB_USER=healthchecks
      - DB_PASSWORD=changeme  # À CHANGER !
      - SECRET_KEY=changeme123  # À CHANGER !
      - SITE_ROOT=https://monitoring.example.com  # Votre domaine
      - REGISTRATION_OPEN=False  # Fermer les inscriptions publiques
    ports:
      - "8000:8000"
    depends_on:
      - postgres
    restart: unless-stopped

  postgres:
    image: postgres:13
    environment:
      - POSTGRES_DB=healthchecks
      - POSTGRES_USER=healthchecks
      - POSTGRES_PASSWORD=changeme  # À CHANGER !
    volumes:
      - healthchecks-data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  healthchecks-data:
EOF

        echo "   Fichier créé : healthchecks-central.yml"
        echo ""
        echo "2. Configurer un reverse proxy (Nginx/Caddy) avec SSL"
        echo ""
        echo "3. Démarrer l'instance :"
        echo "   docker-compose -f healthchecks-central.yml up -d"
        echo ""
        echo "4. Créer un compte admin :"
        echo "   docker-compose -f healthchecks-central.yml exec healthchecks python manage.py createsuperuser"
        echo ""
        echo "5. Accéder à l'interface et créer un projet"
        echo ""
        echo "6. Relancer ce script et choisir l'option 2"
        ;;

    4)
        echo ""
        echo "🔧 Configuration pour développement local"
        echo "-----------------------------------------"
        echo ""
        echo "Configuration pour une instance Healthchecks Docker locale..."

        cat > "$PROJECT_ROOT/.env.healthchecks" <<EOF
# ============================================================================
# Healthchecks.io Configuration - Local Development
# ============================================================================

# Service Configuration
HEALTHCHECKS_ENABLED=true
HEALTHCHECKS_HOST=http://localhost:8000
HEALTHCHECKS_API_URL=http://healthchecks:8000/api/v1
HEALTHCHECKS_PING_URL=http://healthchecks:8000/ping

# API Keys (générées localement)
HEALTHCHECKS_API_KEY=dev-api-key-change-me
HEALTHCHECKS_READ_KEY=

# Settings
HEALTHCHECKS_CHECK_TIMEOUT=30
HEALTHCHECKS_RETRY_COUNT=3
HEALTHCHECKS_RETRY_DELAY=10
HEALTHCHECKS_AUTO_PROVISION=true

# Check UUIDs (seront générés automatiquement)
HC_CHECK_API=
HC_CHECK_POSTGRES=
HC_CHECK_REDIS=
HC_CHECK_CELERY_WORKER=
HC_CHECK_CELERY_BEAT=
HC_CHECK_KAFKA=
HC_CHECK_KAFKA_CONSUMER=
HC_CHECK_MINIO=
HC_CHECK_VAULT=
HC_CHECK_SSO_TOKEN_REFRESH=
HC_CHECK_HEALTH_TASK=
HC_CHECK_TOKEN_CLEANUP=
HC_CHECK_KEY_ROTATION=
HC_CHECK_COMPREHENSIVE=
EOF

        echo ""
        echo "⚠️  ATTENTION : Configuration locale créée"
        echo "   Cette configuration nécessite de lancer Healthchecks localement."
        echo "   Pour la production, utilisez plutôt l'option 1 ou 2."
        ;;

    *)
        echo "❌ Option invalide"
        exit 1
        ;;
esac

# Créer le fichier .env.healthchecks.example si non existant
if [ ! -f "$PROJECT_ROOT/.env.healthchecks.example" ]; then
    cat > "$PROJECT_ROOT/.env.healthchecks.example" <<'EOF'
# ============================================================================
# Healthchecks.io Configuration Example
# ============================================================================
# Copy this file to .env.healthchecks and configure

# For healthchecks.io (SaaS)
#HEALTHCHECKS_HOST=https://healthchecks.io
#HEALTHCHECKS_API_URL=https://healthchecks.io/api/v1
#HEALTHCHECKS_PING_URL=https://hc-ping.com

# For self-hosted
#HEALTHCHECKS_HOST=https://monitoring.example.com
#HEALTHCHECKS_API_URL=https://monitoring.example.com/api/v1
#HEALTHCHECKS_PING_URL=https://monitoring.example.com/ping

# API Keys
HEALTHCHECKS_API_KEY=your-api-key-here
HEALTHCHECKS_READ_KEY=optional-read-only-key

# Settings
HEALTHCHECKS_ENABLED=true
HEALTHCHECKS_AUTO_PROVISION=true
EOF
    echo "📋 Fichier .env.healthchecks.example créé"
fi

# Afficher les prochaines étapes
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Configuration terminée !"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Prochaines étapes :"
echo ""

if [ "$choice" != "4" ]; then
    echo "1. NE PAS lancer Healthchecks localement :"
    echo "   docker-compose up -d api worker celery-beat  # Sans healthchecks"
    echo ""
    echo "2. Copier .env.healthchecks sur toutes vos machines :"
    echo "   scp .env.healthchecks user@server:/path/to/project/"
    echo ""
else
    echo "1. Lancer Healthchecks localement :"
    echo "   docker-compose up -d healthchecks healthchecks-db"
    echo ""
    echo "2. Créer un compte admin :"
    echo "   ./scripts/create-healthchecks-admin.sh"
    echo ""
fi

echo "3. Synchroniser les checks (optionnel) :"
echo "   cd backend && python scripts/ensure_healthchecks.py"
echo ""
echo "4. Tester la configuration :"
echo "   docker-compose exec api python -m app.tasks.monitoring_tasks"
echo ""

if [ "$choice" == "1" ]; then
    echo "📊 Dashboard : https://healthchecks.io"
elif [ "$choice" == "2" ]; then
    echo "📊 Dashboard : $instance_url"
else
    echo "📊 Dashboard : http://localhost:8000"
fi

echo ""
echo "💡 Tips :"
echo "- Utilisez la MÊME configuration .env.healthchecks partout"
echo "- Les UUIDs des checks seront automatiquement synchronisés"
echo "- L'auto-provisioning créera les checks manquants"
echo ""