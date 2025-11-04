#!/bin/sh
set -e

echo "=== Docker Entrypoint: Initialisation ==="

# Charger les variables Vault depuis .env.vault si le fichier existe
if [ -f /.env.vault ]; then
    echo "Chargement des credentials Vault depuis .env.vault..."

    # Exporter chaque ligne du fichier .env.vault
    while IFS='=' read -r key value; do
        # Ignorer les lignes vides et les commentaires
        case "$key" in
            ''|\#*) continue ;;
        esac

        # Retirer les espaces et quotes éventuelles
        key=$(echo "$key" | sed 's/^[ \t]*//;s/[ \t]*$//')
        value=$(echo "$value" | sed 's/^[ \t]*//;s/[ \t]*$//')

        # Exporter la variable
        if [ -n "$key" ] && [ -n "$value" ]; then
            export "$key=$value"
            echo "  ✓ Variable exportée: $key"
        fi
    done < /.env.vault

    echo "Variables Vault chargées avec succès"
else
    echo "⚠️  Fichier .env.vault non trouvé - utilisation des variables par défaut"
fi

# Vérifier que les variables Vault sont bien définies si USE_VAULT est activé
if [ "$USE_VAULT" = "true" ]; then
    echo "Vérification de la configuration Vault..."

    if [ -z "$VAULT_ADDR" ] || [ -z "$VAULT_ROLE_ID" ] || [ -z "$VAULT_SECRET_ID" ]; then
        echo "❌ Erreur: Variables Vault manquantes"
        echo "   VAULT_ADDR=$VAULT_ADDR"
        echo "   VAULT_ROLE_ID=${VAULT_ROLE_ID:+[SET]}"
        echo "   VAULT_SECRET_ID=${VAULT_SECRET_ID:+[SET]}"
        exit 1
    fi

    echo "✓ Configuration Vault valide"
    echo "  VAULT_ADDR: $VAULT_ADDR"
    echo "  VAULT_ROLE_ID: [SET]"
    echo "  VAULT_SECRET_ID: [SET]"
fi

echo "=== Démarrage de l'application ==="

# Exécuter la commande passée en argument
exec "$@"