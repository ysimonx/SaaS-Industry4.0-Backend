#!/bin/sh
set -e

echo "=========================================="
echo "🚀 SaaS Backend - Docker Entrypoint"
echo "=========================================="

# Vérifier si USE_VAULT est activé
USE_VAULT=${USE_VAULT:-false}

if [ "$USE_VAULT" = "true" ]; then
    echo "→ Vault activé (USE_VAULT=true)"
    echo "→ Attente du fichier .env.vault..."

    # Attendre que .env.vault soit créé par vault-init
    VAULT_ENV_FILE="/.env.vault"
    MAX_WAIT=60
    WAIT_TIME=0

    while [ ! -f "$VAULT_ENV_FILE" ]; do
        if [ $WAIT_TIME -ge $MAX_WAIT ]; then
            echo "❌ ERREUR: Timeout - fichier $VAULT_ENV_FILE introuvable après ${MAX_WAIT}s"
            echo ""
            echo "Vérifiez que:"
            echo "  1. Le service vault-init s'est exécuté avec succès"
            echo "  2. Le volume .env.vault est correctement monté"
            echo "  3. Les logs du conteneur vault-init pour plus de détails"
            exit 1
        fi

        echo "   Attente de $VAULT_ENV_FILE... (${WAIT_TIME}s/${MAX_WAIT}s)"
        sleep 2
        WAIT_TIME=$((WAIT_TIME + 2))
    done

    echo "✅ Fichier .env.vault trouvé"

    # Charger les credentials Vault
    echo "→ Chargement des credentials Vault..."
    # shellcheck disable=SC1090
    . "$VAULT_ENV_FILE"

    # Vérifier que les variables sont bien chargées
    if [ -z "$VAULT_ADDR" ] || [ -z "$VAULT_ROLE_ID" ] || [ -z "$VAULT_SECRET_ID" ]; then
        echo "❌ ERREUR: Variables Vault manquantes dans .env.vault"
        echo "   VAULT_ADDR: ${VAULT_ADDR:-<manquant>}"
        echo "   VAULT_ROLE_ID: ${VAULT_ROLE_ID:-<manquant>}"
        echo "   VAULT_SECRET_ID: ${VAULT_SECRET_ID:-<manquant>}"
        exit 1
    fi

    # Exporter les variables pour l'application
    export VAULT_ADDR
    export VAULT_ROLE_ID
    export VAULT_SECRET_ID

    echo "✅ Credentials Vault chargés avec succès"
    echo "   VAULT_ADDR: $VAULT_ADDR"
    echo "   VAULT_ROLE_ID: ${VAULT_ROLE_ID:0:20}..."
    echo "   VAULT_SECRET_ID: ${VAULT_SECRET_ID:0:20}..."
else
    echo "→ Vault désactivé (USE_VAULT=false)"
    echo "→ Utilisation des variables d'environnement (.env.docker)"
fi

echo "=========================================="
echo "→ Démarrage de l'application..."
echo "=========================================="
echo ""

# Exécuter la commande passée au conteneur
exec "$@"
