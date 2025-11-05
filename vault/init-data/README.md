# Vault Secrets Initialization Data

Ce répertoire contient les fichiers de secrets **sources** qui seront injectés dans Vault lors de l'initialisation.

## ⚠️ SÉCURITÉ IMPORTANTE

**NE JAMAIS commiter les fichiers `.env` de ce répertoire dans Git !**

Les fichiers `.gitignore` sont configurés pour ignorer tous les fichiers sauf ce README.

## Fichiers de Secrets par Environnement

Créez un fichier pour chaque environnement :

- `docker.env` - Pour l'environnement Docker Compose local
- `dev.env` - Pour le développement local (sans Docker)
- `prod.env` - Pour la production

## Template docker.env (Développement Docker)

```bash
# Créer le fichier de secrets pour Docker
cat > vault/init-data/docker.env <<'SECRETS'
# ============================================================================
# Secrets pour Environnement DOCKER (Docker Compose Local)
# ============================================================================
# ⚠️  NE PAS COMMITER CE FICHIER
# ⚠️  Ces secrets seront injectés automatiquement dans Vault au démarrage

# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/saas_platform
TENANT_DATABASE_URL_TEMPLATE=postgresql://postgres:postgres@postgres:5432/{database_name}

# JWT - IMPORTANT: Générer une nouvelle clé sécurisée
# Générer avec: openssl rand -hex 32
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ACCESS_TOKEN_EXPIRES=900

# S3/MinIO
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents
S3_REGION=us-east-1
SECRETS
```

## Template dev.env (Développement Local)

```bash
# Créer le fichier de secrets pour Dev local
cat > vault/init-data/dev.env <<'SECRETS'
# ============================================================================
# Secrets pour Environnement DEV (Développement Local sans Docker)
# ============================================================================

# Database (localhost pour dev local)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/saas_platform
TENANT_DATABASE_URL_TEMPLATE=postgresql://postgres:postgres@localhost:5432/{database_name}

# JWT
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ACCESS_TOKEN_EXPIRES=900

# S3/MinIO (localhost pour dev local)
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents-dev
S3_REGION=us-east-1
SECRETS
```

## Template prod.env (Production)

```bash
# Créer le fichier de secrets pour Production
cat > vault/init-data/prod.env <<'SECRETS'
# ============================================================================
# Secrets pour Environnement PROD (Production)
# ============================================================================
# ⚠️  NE PAS COMMITER CE FICHIER
# ⚠️  À CONFIGURER MANUELLEMENT SUR LE SERVEUR DE PRODUCTION

# Database - REMPLACER PAR LES VRAIES VALEURS
DATABASE_URL=postgresql://prod_user:STRONG_PASSWORD@prod-db-host:5432/saas_platform_prod
TENANT_DATABASE_URL_TEMPLATE=postgresql://prod_user:STRONG_PASSWORD@prod-db-host:5432/{database_name}

# JWT - GÉNÉRER UNE CLÉ FORTE UNIQUE
# Générer avec: openssl rand -hex 32
JWT_SECRET_KEY=REPLACE_WITH_STRONG_RANDOM_KEY
JWT_ACCESS_TOKEN_EXPIRES=900

# S3 - REMPLACER PAR LES VRAIES VALEURS AWS/S3
S3_ENDPOINT_URL=https://s3.amazonaws.com
S3_ACCESS_KEY_ID=REPLACE_WITH_AWS_ACCESS_KEY
S3_SECRET_ACCESS_KEY=REPLACE_WITH_AWS_SECRET_KEY
S3_BUCKET=saas-documents-production
S3_REGION=us-east-1
SECRETS
```

## Utilisation

1. **Créer le fichier de secrets** pour votre environnement (par exemple `docker.env`)
2. **Démarrer Vault** : `docker-compose up -d vault vault-unseal`
3. **Initialiser les secrets** : `docker-compose up -d vault-init`
4. **Vérifier** : `cat .env.vault` (credentials AppRole créés)

## Vérification des Secrets dans Vault

```bash
# Se connecter à Vault avec le token root
VAULT_TOKEN=$(cat vault/data/root-token.txt)
docker exec -e VAULT_TOKEN=$VAULT_TOKEN saas-vault vault kv get secret/saas-project/docker/database

# Lister tous les secrets
docker exec -e VAULT_TOKEN=$VAULT_TOKEN saas-vault vault kv list secret/saas-project/docker
```

## Sécurité

- Les fichiers `.env` de ce répertoire ne doivent **JAMAIS** être committés dans Git
- Sauvegarder les secrets dans un gestionnaire de mots de passe (1Password, LastPass, etc.)
- En production, créer le fichier `prod.env` directement sur le serveur
- Utiliser des mots de passe forts et uniques pour chaque environnement
