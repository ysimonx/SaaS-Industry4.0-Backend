#!/bin/bash
set -e

VAULT_ENV=${VAULT_ENV:-docker}
SECRETS_FILE="/init-data/${VAULT_ENV}.env"
OUTPUT_FILE="/output/.env.vault"

echo "=========================================="
echo "🔐 Initialisation Automatique de Vault"
echo "=========================================="
echo "Environnement : $VAULT_ENV"
echo "Fichier source: $SECRETS_FILE"
echo "=========================================="
echo ""

# Vérifier que le fichier de secrets existe
if [ ! -f "$SECRETS_FILE" ]; then
    echo "❌ ERREUR: Fichier $SECRETS_FILE introuvable"
    echo ""
    echo "📝 Créez ce fichier avec vos secrets pour l'environnement $VAULT_ENV"
    echo ""
    echo "Exemple:"
    echo "  cat > vault/init-data/${VAULT_ENV}.env <<EOF"
    echo "  DATABASE_URL=postgresql://..."
    echo "  JWT_SECRET_KEY=..."
    echo "  EOF"
    exit 1
fi

echo "✓ Chargement des secrets depuis $SECRETS_FILE"
source "$SECRETS_FILE"

# Attendre que Vault soit vraiment prêt
echo "→ Attente de Vault..."
sleep 3

# Activer le KV secrets engine v2 (si pas déjà fait)
echo "→ Activation du KV Secrets Engine v2..."
vault secrets enable -version=2 -path=secret kv 2>/dev/null && echo "✅ KV Secrets Engine v2 activé" || echo "✓ KV engine déjà activé"

# Injection des secrets DATABASE
echo "→ Injection des secrets DATABASE pour environnement '$VAULT_ENV'..."
vault kv put "secret/saas-project/${VAULT_ENV}/database" \
  main_url="$DATABASE_URL" \
  tenant_url_template="$TENANT_DATABASE_URL_TEMPLATE"
echo "✅ Secrets database injectés"

# Injection des secrets JWT
echo "→ Injection des secrets JWT pour environnement '$VAULT_ENV'..."
vault kv put "secret/saas-project/${VAULT_ENV}/jwt" \
  secret_key="$JWT_SECRET_KEY" \
  access_token_expires="${JWT_ACCESS_TOKEN_EXPIRES:-900}"
echo "✅ Secrets JWT injectés"

# Injection des secrets S3
echo "→ Injection des secrets S3 pour environnement '$VAULT_ENV'..."
vault kv put "secret/saas-project/${VAULT_ENV}/s3" \
  endpoint_url="$S3_ENDPOINT_URL" \
  access_key_id="$S3_ACCESS_KEY_ID" \
  secret_access_key="$S3_SECRET_ACCESS_KEY" \
  bucket_name="${S3_BUCKET:-saas-documents}" \
  region="${S3_REGION:-us-east-1}"
echo "✅ Secrets S3 injectés"

# Configuration de l'authentification AppRole
echo "→ Configuration de l'authentification AppRole..."
vault auth enable approle 2>/dev/null && echo "✓ AppRole activé" || echo "✓ AppRole déjà activé"

# Créer la politique d'accès
echo "→ Création de la politique Vault pour environnement '$VAULT_ENV'..."
vault policy write saas-api-docker-policy - <<EOF
# Politique pour l'environnement ${VAULT_ENV}
path "secret/data/saas-project/${VAULT_ENV}/*" {
  capabilities = ["read"]
}

path "secret/metadata/saas-project/${VAULT_ENV}/*" {
  capabilities = ["list", "read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF
echo "✅ Policy 'saas-api-docker-policy' créée"

# Configurer le rôle AppRole
echo "→ Configuration du rôle AppRole..."
vault write auth/approle/role/saas-api-docker \
  token_policies="saas-api-docker-policy" \
  token_ttl=1h \
  token_max_ttl=4h \
  secret_id_ttl=0 \
  secret_id_num_uses=0 2>/dev/null || echo "✓ Rôle AppRole déjà configuré"
echo "✅ AppRole 'saas-api-docker' créé"

# Récupérer les credentials AppRole
echo "→ Génération des credentials AppRole..."
ROLE_ID=$(vault read -field=role_id auth/approle/role/saas-api-docker/role-id)
SECRET_ID=$(vault write -field=secret_id -f auth/approle/role/saas-api-docker/secret-id)

# Écrire le fichier .env.vault
echo "→ Écriture du fichier .env.vault..."
cat > "$OUTPUT_FILE" <<EOF
# HashiCorp Vault Credentials
# Auto-généré par init-vault.sh le $(date)
# Environnement: ${VAULT_ENV}
#
# ⚠️  NE PAS COMMITER CE FICHIER
# ⚠️  Ces credentials donnent accès aux secrets Vault

VAULT_ADDR=http://vault:8200
VAULT_ROLE_ID=$ROLE_ID
VAULT_SECRET_ID=$SECRET_ID
EOF

chmod 600 "$OUTPUT_FILE" 2>/dev/null || true
echo "✅ Fichier .env.vault généré avec succès"

echo ""
echo "=========================================="
echo "✅ INITIALISATION TERMINÉE AVEC SUCCÈS"
echo "=========================================="
echo "Environnement  : $VAULT_ENV"
echo "Secrets créés  : secret/saas-project/${VAULT_ENV}/*"
echo "Politique      : saas-api-docker-policy"
echo "Rôle AppRole   : saas-api-docker"
echo ""
echo "📄 Credentials Vault:"
echo "   VAULT_ADDR     : http://vault:8200"
echo "   VAULT_ROLE_ID  : $ROLE_ID"
echo "   VAULT_SECRET_ID: $SECRET_ID"
echo ""
echo "✓ Ces credentials ont été écrits dans .env.vault"
echo "✓ L'application peut maintenant démarrer et lire les secrets depuis Vault"
echo "=========================================="

exit 0
