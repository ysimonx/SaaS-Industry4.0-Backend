#!/bin/sh
set -e

UNSEAL_KEYS_FILE="/vault/data/unseal-keys.json"
ROOT_TOKEN_FILE="/vault/data/root-token.txt"

echo "=========================================="
echo "🔓 Vault Auto-Unseal Script"
echo "=========================================="
echo ""

# Attendre que Vault soit démarré
echo "→ Attente du démarrage de Vault..."
sleep 5

MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if vault status >/dev/null 2>&1; then
        echo "✓ Vault est accessible"
        break
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  Tentative $RETRY_COUNT/$MAX_RETRIES..."
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ ERREUR: Vault n'est pas accessible après $MAX_RETRIES tentatives"
    exit 1
fi

# Vérifier si Vault est déjà initialisé
if vault status 2>&1 | grep -q "Initialized.*true"; then
    echo "✓ Vault est déjà initialisé"

    # Vérifier si les clés d'unseal existent
    if [ ! -f "$UNSEAL_KEYS_FILE" ]; then
        echo "❌ ERREUR: Vault est initialisé mais les clés d'unseal sont introuvables"
        echo "   Fichier attendu: $UNSEAL_KEYS_FILE"
        exit 1
    fi

    # Vérifier si Vault est scellé (sealed)
    if vault status 2>&1 | grep -q "Sealed.*true"; then
        echo "🔒 Vault est scellé, déverrouillage en cours..."

        # Extraire les clés d'unseal du fichier JSON
        UNSEAL_KEY_1=$(cat "$UNSEAL_KEYS_FILE" | grep -o '"unseal_keys_b64":\[[^]]*\]' | grep -o '"[^"]*"' | sed -n '1p' | tr -d '"')
        UNSEAL_KEY_2=$(cat "$UNSEAL_KEYS_FILE" | grep -o '"unseal_keys_b64":\[[^]]*\]' | grep -o '"[^"]*"' | sed -n '2p' | tr -d '"')
        UNSEAL_KEY_3=$(cat "$UNSEAL_KEYS_FILE" | grep -o '"unseal_keys_b64":\[[^]]*\]' | grep -o '"[^"]*"' | sed -n '3p' | tr -d '"')

        if [ -z "$UNSEAL_KEY_1" ] || [ -z "$UNSEAL_KEY_2" ] || [ -z "$UNSEAL_KEY_3" ]; then
            echo "❌ ERREUR: Impossible d'extraire les clés d'unseal du fichier JSON"
            exit 1
        fi

        # Unseal avec les 3 clés
        echo "→ Application de la clé 1/3..."
        vault operator unseal "$UNSEAL_KEY_1" >/dev/null

        echo "→ Application de la clé 2/3..."
        vault operator unseal "$UNSEAL_KEY_2" >/dev/null

        echo "→ Application de la clé 3/3..."
        vault operator unseal "$UNSEAL_KEY_3" >/dev/null

        echo "✅ Vault déverrouillé avec succès"
    else
        echo "✓ Vault est déjà déverrouillé"
    fi

else
    echo "🔧 Vault n'est pas initialisé, initialisation en cours..."

    # Initialiser Vault avec 5 clés et un seuil de 3
    INIT_OUTPUT=$(vault operator init -key-shares=5 -key-threshold=3 -format=json)

    # Extraire les clés et le token root
    echo "$INIT_OUTPUT" > "$UNSEAL_KEYS_FILE"
    chmod 600 "$UNSEAL_KEYS_FILE"

    ROOT_TOKEN=$(echo "$INIT_OUTPUT" | grep -o '"root_token":"[^"]*"' | cut -d'"' -f4)
    echo "$ROOT_TOKEN" > "$ROOT_TOKEN_FILE"
    chmod 600 "$ROOT_TOKEN_FILE"

    echo "✓ Vault initialisé"
    echo "✓ Clés d'unseal sauvegardées: $UNSEAL_KEYS_FILE"
    echo "✓ Token root sauvegardé: $ROOT_TOKEN_FILE"

    # Unseal immédiatement après l'initialisation
    echo "→ Déverrouillage de Vault..."

    UNSEAL_KEY_1=$(echo "$INIT_OUTPUT" | grep -o '"unseal_keys_b64":\[[^]]*\]' | grep -o '"[^"]*"' | sed -n '1p' | tr -d '"')
    UNSEAL_KEY_2=$(echo "$INIT_OUTPUT" | grep -o '"unseal_keys_b64":\[[^]]*\]' | grep -o '"[^"]*"' | sed -n '2p' | tr -d '"')
    UNSEAL_KEY_3=$(echo "$INIT_OUTPUT" | grep -o '"unseal_keys_b64":\[[^]]*\]' | grep -o '"[^"]*"' | sed -n '3p' | tr -d '"')

    vault operator unseal "$UNSEAL_KEY_1" >/dev/null
    vault operator unseal "$UNSEAL_KEY_2" >/dev/null
    vault operator unseal "$UNSEAL_KEY_3" >/dev/null

    echo "✅ Vault initialisé et déverrouillé avec succès"
fi

# Afficher le statut final
echo ""
echo "=========================================="
echo "📊 Statut Final de Vault"
echo "=========================================="
vault status

echo ""
echo "=========================================="
echo "✅ AUTO-UNSEAL TERMINÉ AVEC SUCCÈS"
echo "=========================================="
echo ""
echo "📝 Informations importantes:"
echo "   - Clés d'unseal: $UNSEAL_KEYS_FILE"
echo "   - Token root: $ROOT_TOKEN_FILE"
echo "   - Interface Web: http://localhost:8200/ui"
echo ""
echo "⚠️  SÉCURITÉ: Ces fichiers contiennent des secrets critiques"
echo "   - NE PAS les commiter dans Git"
echo "   - Sauvegarder dans un gestionnaire de mots de passe"
echo "=========================================="

exit 0
