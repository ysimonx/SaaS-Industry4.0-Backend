#!/bin/sh
# Script wrapper pour exécuter les commandes Flask avec les variables Vault

# Charger les variables Vault depuis .env.vault si le fichier existe
if [ -f /.env.vault ]; then
    echo "Chargement des variables Vault..."

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
        fi
    done < /.env.vault

    echo "Variables Vault chargées avec succès"
fi

# Exécuter la commande Flask passée en argument
exec flask "$@"