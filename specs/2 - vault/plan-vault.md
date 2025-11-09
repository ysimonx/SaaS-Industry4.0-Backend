# 🔐 Plan d'Intégration HashiCorp Vault - SaaS Platform

**Version:** 1.0
**Date:** 2025-11-04
**Projet:** SaaS Python/Flask Multi-Tenant Platform

---

## Table des Matières

1. [Introduction et Vue d'Ensemble](#1-introduction-et-vue-densemble)
2. [Phase 1 - Préparation de l'Environnement Local](#2-phase-1---préparation-de-lenvironnement-local)
3. [Phase 2 - Configuration de Vault](#3-phase-2---configuration-de-vault)
4. [Phase 3 - Mise à jour de l'Application Flask](#4-phase-3---mise-à-jour-de-lapplication-flask)
5. [Phase 4 - Implémentation du Renouvellement de Token](#5-phase-4---implémentation-du-renouvellement-de-token)
6. [Phase 5 - Migration et Tests](#6-phase-5---migration-et-tests)
7. [Annexes](#7-annexes)

---

## 0. QuickStart - Démarrage Rapide

### Pour les impatients qui veulent juste démarrer Vault

Si vous voulez simplement démarrer Vault avec stockage persistant et auto-unseal:

```bash
# 1. Créer la structure de répertoires
mkdir -p vault/{config,data,logs,scripts,init-data}

# 2. Créer le fichier de configuration Vault (voir section 2.3.1)
# 3. Créer le script d'unseal (voir section 2.3.2)
# 4. Rendre le script exécutable
chmod +x vault/scripts/unseal-vault.sh

# 5. Démarrer Vault et l'auto-unseal
docker-compose up -d vault vault-unseal

# 6. Vérifier les logs d'unseal
docker logs saas-vault-unseal

# 7. Vérifier le statut de Vault
docker exec saas-vault vault status

# 8. Récupérer le token root (première fois uniquement)
cat vault/data/root-token.txt
```

**Après le premier démarrage:**
- Les clés d'unseal sont dans `vault/data/unseal-keys.json` (NE PAS COMMITER)
- Le token root est dans `vault/data/root-token.txt` (NE PAS COMMITER)
- Vault se déverrouillera automatiquement à chaque redémarrage
- Interface Web disponible sur: http://localhost:8201/ui (port 8201 car 8200 est souvent utilisé par OneDrive sur macOS)

**Pour initialiser les secrets dans Vault:**

```bash
# 1. Créer le fichier de secrets pour votre environnement
cat > vault/init-data/docker.env <<'EOF'
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/saas_platform
TENANT_DATABASE_URL_TEMPLATE=postgresql://postgres:postgres@postgres:5432/{database_name}
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ACCESS_TOKEN_EXPIRES=900
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents
S3_REGION=us-east-1
EOF

# 2. Lancer le service d'initialisation
docker-compose up -d vault-init

# 3. Vérifier que les secrets sont créés
docker exec saas-vault vault login $(cat vault/data/root-token.txt)
docker exec saas-vault vault kv get secret/saas-project/docker/database

# 4. Les credentials AppRole sont dans .env.vault (créé automatiquement)
cat .env.vault
```

**Documentation complète:** Voir les sections ci-dessous pour comprendre chaque étape en détail.

---

## 1. Introduction et Vue d'Ensemble

### 1.1 Contexte du Projet

Ce document décrit le plan d'intégration de **HashiCorp Vault** dans l'architecture du projet SaaS multi-tenant Python/Flask. L'objectif est de remplacer la gestion actuelle des secrets (variables d'environnement et fichiers `.env`) par une solution centralisée, sécurisée et auditable.

### 1.2 État Actuel de la Gestion des Secrets

**Problèmes Identifiés:**
- Secrets stockés en clair dans les fichiers `.env` (`.env.development`, `.env.production`, `.env.docker`)
- Credentials hardcodés dans `docker-compose.yml` (PostgreSQL: `postgres:postgres`, MinIO: `minioadmin:minioadmin`)
- Plus de 30 variables d'environnement contenant des informations sensibles
- Aucun mécanisme de rotation des secrets
- Aucun audit trail des accès aux secrets
- Risque de fuite via commits Git ou logs

**Secrets Critiques à Migrer:**
1. **Base de données:** `DATABASE_URL`, `TENANT_DATABASE_URL_TEMPLATE`
2. **JWT:** `JWT_SECRET_KEY`, `SECRET_KEY`
3. **S3/MinIO:** `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL`
4. **Kafka:** `KAFKA_BOOTSTRAP_SERVERS` (pour évolution future avec authentification)

### 1.3 Architecture Cible avec Vault

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Network (saas-network)            │
│                                                              │
│  ┌──────────────┐         ┌─────────────────┐              │
│  │              │         │                 │              │
│  │  Flask API   │◄────────┤  HashiCorp      │              │
│  │  Container   │ AppRole │  Vault          │              │
│  │              │ Auth    │  (Container)    │              │
│  └──────┬───────┘         └─────────────────┘              │
│         │                                                    │
│         │ Read Secrets via Token                           │
│         │                                                    │
│  ┌──────▼───────┐         ┌─────────────────┐              │
│  │              │         │                 │              │
│  │  Kafka       │         │  PostgreSQL     │              │
│  │  Worker      │         │  MinIO          │              │
│  │  Container   │         │  Kafka/Zookeeper│              │
│  │              │         │                 │              │
│  └──────────────┘         └─────────────────┘              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 Bénéfices de l'Intégration Vault

- ✅ **Sécurité renforcée:** Secrets chiffrés au repos et en transit
- ✅ **Authentification forte:** AppRole avec Role ID + Secret ID
- ✅ **Audit complet:** Traçabilité de tous les accès aux secrets
- ✅ **Rotation automatique:** Capacité de renouveler les credentials
- ✅ **Gestion centralisée:** Un seul point de vérité pour tous les secrets
- ✅ **Séparation des environnements:** Dev/Staging/Prod isolés
- ✅ **Conformité:** Répond aux standards de sécurité (SOC2, ISO27001)

---

## 2. Phase 1 - Préparation de l'Environnement Local

### 2.1 Ajout du Service Vault dans Docker Compose

**Fichier:** `docker-compose.yml`

**Action:** Ajouter le service `vault` dans la section `services:`

**IMPORTANT:** Cette configuration utilise un stockage persistant sur disque avec auto-unseal au démarrage.

```yaml
services:
  # ... services existants ...

  vault:
    image: hashicorp/vault:1.15
    container_name: saas-vault
    ports:
      - "8201:8200"  # Port 8201 on host (8200 often used by OneDrive on macOS)
    environment:
      VAULT_ADDR: "http://0.0.0.0:8200"
      VAULT_API_ADDR: "http://0.0.0.0:8200"
      SKIP_SETCAP: "true"
    cap_add:
      - IPC_LOCK
    networks:
      - saas-network
    healthcheck:
      test: ["CMD", "vault", "status"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
    volumes:
      - ./vault/config:/vault/config:ro
      - ./vault/data:/vault/data
      - ./vault/logs:/vault/logs
      - ./vault/scripts:/vault/scripts:ro
    command: server -config=/vault/config/vault.hcl
    restart: unless-stopped

  vault-unseal:
    image: hashicorp/vault:1.15
    container_name: saas-vault-unseal
    depends_on:
      vault:
        condition: service_started
    environment:
      VAULT_ADDR: "http://vault:8200"
    volumes:
      - ./vault/scripts:/scripts:ro
      - ./vault/data:/vault/data
    command: /scripts/unseal-vault.sh
    networks:
      - saas-network
    restart: "no"
```

**Notes importantes:**
- **Stockage Persistant:** Les données sont stockées dans `./vault/data` (backend file)
- **Auto-Unseal:** Le service `vault-unseal` déverrouille automatiquement Vault au démarrage
- **Configuration HCL:** Vault utilise un fichier de configuration `/vault/config/vault.hcl`
- **Port 8201 (hôte) -> 8200 (container):** Port standard de l'API Vault. Le port 8201 est utilisé sur l'hôte car 8200 est souvent occupé par OneDrive sur macOS
- **IPC_LOCK:** Capability nécessaire pour éviter le swap de la mémoire Vault
- **Health Check:** Permet aux autres services de démarrer après Vault
- **Persistence:** Les clés d'unseal sont stockées dans `./vault/data/unseal-keys.json` (NE PAS COMMITER)

### 2.2 Ajout de la Dépendance Python hvac

**Fichier:** `backend/requirements.txt`

**Action:** Ajouter la ligne suivante

```
hvac==2.1.0
```

**Installation pour le développement local:**

```bash
cd backend
source venv/bin/activate
pip install hvac==2.1.0
pip freeze > requirements.txt
```

### 2.3 Création de la Structure de Répertoires

**Commandes:**

```bash
# Créer les répertoires Vault
mkdir -p vault/config
mkdir -p vault/data
mkdir -p vault/logs
mkdir -p vault/scripts

# Créer les répertoires pour les scripts d'initialisation
mkdir -p backend/scripts
```

### 2.3.1 Création du Fichier de Configuration Vault

**Fichier:** `vault/config/vault.hcl`

```hcl
# Configuration HashiCorp Vault - Mode Développement avec Persistance
# Documentation: https://developer.hashicorp.com/vault/docs/configuration

# Interface d'écoute
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

# Backend de stockage - File (persistant sur disque)
storage "file" {
  path = "/vault/data"
}

# Configuration de l'API
api_addr = "http://0.0.0.0:8200"
cluster_addr = "https://0.0.0.0:8201"

# Interface utilisateur Web
ui = true

# Désactiver mlock pour Docker (déjà géré par IPC_LOCK)
disable_mlock = true

# Niveau de logs
log_level = "info"

# Fichier de logs
log_file = "/vault/logs/vault.log"

# Rotation des logs
log_rotate_duration = "24h"
log_rotate_max_files = 7
```

**Notes importantes:**
- **TLS désactivé:** Pour le développement local (activer en production)
- **Storage file:** Stockage persistant dans `/vault/data`
- **UI activée:** Interface web accessible sur http://localhost:8201/ui (port 8201 car 8200 est souvent utilisé par OneDrive sur macOS)
- **disable_mlock:** Nécessaire pour Docker, la sécurité est assurée par IPC_LOCK

### 2.3.2 Création du Script d'Auto-Unseal

**Fichier:** `vault/scripts/unseal-vault.sh`

```bash
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
        UNSEAL_KEY_1=$(cat "$UNSEAL_KEYS_FILE" | grep -o '"unseal_key_1":"[^"]*"' | cut -d'"' -f4)
        UNSEAL_KEY_2=$(cat "$UNSEAL_KEYS_FILE" | grep -o '"unseal_key_2":"[^"]*"' | cut -d'"' -f4)
        UNSEAL_KEY_3=$(cat "$UNSEAL_KEYS_FILE" | grep -o '"unseal_key_3":"[^"]*"' | cut -d'"' -f4)

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
echo "   - Interface Web: http://localhost:8201/ui"
echo ""
echo "⚠️  SÉCURITÉ: Ces fichiers contiennent des secrets critiques"
echo "   - NE PAS les commiter dans Git"
echo "   - Sauvegarder dans un gestionnaire de mots de passe"
echo "=========================================="

exit 0
```

**Rendre le script exécutable:**

```bash
chmod +x vault/scripts/unseal-vault.sh
```

**Notes importantes:**
- **Initialisation automatique:** Si Vault n'est pas initialisé, le script le fait automatiquement
- **Sauvegarde des clés:** Les clés d'unseal sont sauvegardées dans `/vault/data/unseal-keys.json`
- **Auto-unseal:** Au redémarrage, Vault est automatiquement déverrouillé
- **Sécurité:** Les fichiers de clés doivent être protégés (chmod 600) et JAMAIS commités

### 2.4 Mise à jour des Dépendances des Services

**Action:** Modifier `docker-compose.yml` pour que les services Flask attendent Vault

```yaml
services:
  api:
    depends_on:
      postgres:
        condition: service_healthy
      kafka:
        condition: service_healthy
      minio:
        condition: service_healthy
      vault:  # AJOUT
        condition: service_healthy

  worker:
    depends_on:
      postgres:
        condition: service_healthy
      kafka:
        condition: service_healthy
      minio:
        condition: service_healthy
      vault:  # AJOUT
        condition: service_healthy
```

### 2.5 Création du Fichier .gitignore pour Vault

**Fichier:** `vault/.gitignore`

```
# Vault data (contient les secrets et clés d'unseal)
data/
logs/

# Tokens et credentials
.vault-token
*.token

# Configuration locale
config/local.hcl

# Secrets initiaux (ne JAMAIS commiter)
init-data/
```

**Fichier:** `vault/init-data/.gitignore`

```
# Ignorer TOUS les fichiers de secrets
*
!.gitignore
```

**Fichier:** `vault/data/.gitignore`

```
# Ignorer TOUS les fichiers de données Vault
*
!.gitignore

# CRITIQUE: Ces fichiers contiennent les clés d'unseal
# Ne JAMAIS commiter unseal-keys.json et root-token.txt
```

**Fichier:** `.gitignore` (à la racine du projet)

**Ajouter ces lignes:**

```
# HashiCorp Vault
vault/data/
vault/logs/
vault/init-data/
.env.vault

# Clés d'unseal et tokens root (CRITIQUE)
vault/data/unseal-keys.json
vault/data/root-token.txt
vault/data/*.db
vault/data/*.bin

# Backups temporaires des anciens .env (à supprimer après migration)
.env.*.backup
```

**Créer les fichiers .gitignore:**

```bash
# Créer le .gitignore pour vault/data
mkdir -p vault/data
cat > vault/data/.gitignore <<'EOF'
# Ignorer TOUS les fichiers de données Vault
*
!.gitignore
EOF
```

### 2.6 Configuration de l'Auto-Initialisation de Vault

**Important:** Cette section configure l'**injection automatique des secrets** dans Vault au démarrage. Vault devient la **source unique de vérité**.

#### 2.6.1 Ajout du Service vault-init dans docker-compose.yml

**Fichier:** `docker-compose.yml`

**Action:** Ajouter le service `vault-init` après le service `vault`

```yaml
services:
  # ... service vault existant ...

  vault-init:
    image: hashicorp/vault:1.15
    container_name: saas-vault-init
    depends_on:
      vault:
        condition: service_healthy
    environment:
      VAULT_ADDR: "http://vault:8200"
      VAULT_TOKEN: "root-token-dev"
      VAULT_ENV: "${VAULT_ENV:-docker}"  # dev, docker, ou prod
    volumes:
      - ./vault/scripts:/scripts:ro
      - ./vault/init-data:/init-data:ro
      - ./.env.vault:/output/.env.vault
    command: /scripts/init-vault.sh
    networks:
      - saas-network
    restart: "no"  # S'exécute une seule fois
```

**Notes importantes:**
- **depends_on vault:healthy** : S'assure que Vault est prêt avant l'initialisation
- **VAULT_ENV** : Environnement à initialiser (dev, docker, prod)
- **volumes** :
  - `scripts:ro` : Scripts en lecture seule
  - `init-data:ro` : Secrets en lecture seule
  - `.env.vault` : Écriture des credentials AppRole
- **restart: no** : Le conteneur s'arrête après l'initialisation

#### 2.6.2 Création du Script d'Initialisation

**Fichier:** `vault/scripts/init-vault.sh`

```bash
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
vault secrets enable -version=2 -path=secret kv 2>/dev/null && echo "✓ KV engine activé" || echo "✓ KV engine déjà activé"

# Injection des secrets DATABASE
echo "→ Injection des secrets DATABASE pour environnement '$VAULT_ENV'..."
vault kv put "secret/saas-project/${VAULT_ENV}/database" \
  main_url="$DATABASE_URL" \
  tenant_url_template="$TENANT_DATABASE_URL_TEMPLATE"
echo "✓ Secrets DATABASE injectés"

# Injection des secrets JWT
echo "→ Injection des secrets JWT pour environnement '$VAULT_ENV'..."
vault kv put "secret/saas-project/${VAULT_ENV}/jwt" \
  secret_key="$JWT_SECRET_KEY" \
  access_token_expires="${JWT_ACCESS_TOKEN_EXPIRES:-900}"
echo "✓ Secrets JWT injectés"

# Injection des secrets S3
echo "→ Injection des secrets S3 pour environnement '$VAULT_ENV'..."
vault kv put "secret/saas-project/${VAULT_ENV}/s3" \
  endpoint_url="$S3_ENDPOINT_URL" \
  access_key_id="$S3_ACCESS_KEY_ID" \
  secret_access_key="$S3_SECRET_ACCESS_KEY" \
  bucket_name="${S3_BUCKET:-saas-documents}" \
  region="${S3_REGION:-us-east-1}"
echo "✓ Secrets S3 injectés"

# Configuration de l'authentification AppRole
echo "→ Configuration de l'authentification AppRole..."
vault auth enable approle 2>/dev/null && echo "✓ AppRole activé" || echo "✓ AppRole déjà activé"

# Créer la politique d'accès
echo "→ Création de la politique Vault pour environnement '$VAULT_ENV'..."
vault policy write saas-app-policy-${VAULT_ENV} - <<EOF
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
echo "✓ Politique créée: saas-app-policy-${VAULT_ENV}"

# Configurer le rôle AppRole
echo "→ Configuration du rôle AppRole..."
vault write auth/approle/role/saas-app-role-${VAULT_ENV} \
  token_policies="saas-app-policy-${VAULT_ENV}" \
  token_ttl=1h \
  token_max_ttl=4h \
  secret_id_ttl=0 \
  secret_id_num_uses=0 2>/dev/null || echo "✓ Rôle AppRole déjà configuré"
echo "✓ Rôle AppRole configuré: saas-app-role-${VAULT_ENV}"

# Récupérer les credentials AppRole
echo "→ Génération des credentials AppRole..."
ROLE_ID=$(vault read -field=role_id auth/approle/role/saas-app-role-${VAULT_ENV}/role-id)
SECRET_ID=$(vault write -field=secret_id -f auth/approle/role/saas-app-role-${VAULT_ENV}/secret-id)

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
echo "✓ Fichier .env.vault créé avec permissions 600"

echo ""
echo "=========================================="
echo "✅ INITIALISATION TERMINÉE AVEC SUCCÈS"
echo "=========================================="
echo "Environnement  : $VAULT_ENV"
echo "Secrets créés  : secret/saas-project/${VAULT_ENV}/*"
echo "Politique      : saas-app-policy-${VAULT_ENV}"
echo "Rôle AppRole   : saas-app-role-${VAULT_ENV}"
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
```

**Rendre le script exécutable:**

```bash
chmod +x vault/scripts/init-vault.sh
```

### 2.7 Préparation des Secrets Initiaux

**Important:** Les secrets doivent être stockés dans `vault/init-data/` et **JAMAIS commités dans Git**.

#### 2.7.1 Création des Répertoires

```bash
# Créer les répertoires
mkdir -p vault/init-data

# Créer le .gitignore
cat > vault/init-data/.gitignore <<EOF
# Ignorer TOUS les fichiers de secrets
*
!.gitignore
EOF
```

#### 2.7.2 Migration depuis les Anciens .env

**Étape 1 : Créer les Backups**

```bash
# Sauvegarder les anciens fichiers .env
cp .env.docker .env.docker.backup
cp .env.development .env.development.backup
cp .env.production .env.production.backup 2>/dev/null || true
```

**Étape 2 : Créer vault/init-data/docker.env**

```bash
cat > vault/init-data/docker.env <<'EOF'
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
JWT_SECRET_KEY=CHANGE_ME_$(openssl rand -hex 32)
JWT_ACCESS_TOKEN_EXPIRES=900

# S3/MinIO
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents
S3_REGION=us-east-1
EOF
```

**Étape 3 : Créer vault/init-data/dev.env**

```bash
cat > vault/init-data/dev.env <<'EOF'
# ============================================================================
# Secrets pour Environnement DEV (Développement Local sans Docker)
# ============================================================================
# ⚠️  NE PAS COMMITER CE FICHIER

# Database (localhost pour dev local)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/saas_platform
TENANT_DATABASE_URL_TEMPLATE=postgresql://postgres:postgres@localhost:5432/{database_name}

# JWT
JWT_SECRET_KEY=dev-local-secret-$(openssl rand -hex 16)
JWT_ACCESS_TOKEN_EXPIRES=900

# S3/MinIO (localhost pour dev local)
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents-dev
S3_REGION=us-east-1
EOF
```

**Étape 4 : Créer vault/init-data/prod.env (Template)**

```bash
cat > vault/init-data/prod.env <<'EOF'
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
EOF
```

#### 2.7.3 Nettoyage des Fichiers .env Existants

**Les fichiers .env ne doivent plus contenir de secrets, seulement des configurations non-sensibles.**

**Fichier:** `.env.docker` (nettoyer)

```bash
# ============================================================================
# Configuration NON-SENSIBLE pour Docker Compose
# ============================================================================
# ✅ Ce fichier peut être commité (aucun secret)
# ✅ Les secrets sont dans Vault (chargés depuis vault/init-data/docker.env)

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=false

# Logging
LOG_LEVEL=DEBUG

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:4999

# Kafka Configuration (non sensible)
KAFKA_CONSUMER_GROUP_ID=saas-consumer-group
KAFKA_AUTO_OFFSET_RESET=earliest
KAFKA_ENABLE_AUTO_COMMIT=true
KAFKA_MAX_POLL_RECORDS=100

# Database Pool Configuration (non sensible)
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# ⚠️  AUCUN SECRET DANS CE FICHIER
# ⚠️  Tous les secrets sont dans vault/init-data/docker.env
```

**Appliquer le même nettoyage pour `.env.development` et `.env.production`**

---

## 3. Phase 2 - Configuration de Vault

> **⚡ NOTE IMPORTANTE:** Avec la configuration d'auto-initialisation mise en place dans les sections 2.6 et 2.7, **toutes les étapes de cette phase sont automatisées** par le script `init-vault.sh`.
>
> Les sections ci-dessous sont conservées **à titre informatif** pour comprendre ce qui se passe en arrière-plan. Vous n'avez **pas besoin d'exécuter ces commandes manuellement**.
>
> **Pour initialiser Vault, il suffit de lancer :**
> ```bash
> docker-compose up -d vault vault-init
> ```

### 3.1 Initialisation de Vault (Mode Dev) - ⚙️ AUTOMATISÉ

**En mode développement**, Vault est déjà initialisé avec le token root. Pour vérifier:

```bash
# Démarrer les services
docker-compose up -d vault

# Vérifier le statut
docker exec -it saas-vault vault status

# Exporter les variables pour les commandes suivantes
export VAULT_ADDR='http://localhost:8201'
export VAULT_TOKEN='root-token-dev'
```

**Sortie attendue:**

```
Key             Value
---             -----
Seal Type       shamir
Initialized     true
Sealed          false
Total Shares    1
Threshold       1
Version         1.15.0
Storage Type    inmem
Cluster Name    vault-cluster-dev
Cluster ID      ...
HA Enabled      false
```

### 3.2 Activation du KV Secrets Engine v2 - ⚙️ AUTOMATISÉ

Le **Key-Value Secrets Engine v2** permet le versioning des secrets.

> **✅ Cette étape est automatiquement exécutée par `init-vault.sh`**

```bash
# Activer le KV engine au chemin "secret/"
docker exec -it saas-vault vault secrets enable -version=2 -path=secret kv

# Vérifier l'activation
docker exec -it saas-vault vault secrets list
```

**Sortie attendue:**

```
Path          Type         Description
----          ----         -----------
cubbyhole/    cubbyhole    per-token private secret storage
identity/     identity     identity store
secret/       kv           n/a
sys/          system       system endpoints used for control
```

### 3.3 Création de la Structure de Chemins de Secrets - ⚙️ AUTOMATISÉ

> **✅ Cette étape est automatiquement exécutée par `init-vault.sh`**
>
> Les secrets sont créés depuis les fichiers `vault/init-data/{env}.env`

**Structure hiérarchique proposée:**

```
secret/
└── data/
    └── saas-project/
        ├── dev/              # Développement local (.env.development)
        │   ├── database/
        │   │   ├── main_url
        │   │   └── tenant_url_template
        │   ├── jwt/
        │   │   ├── secret_key
        │   │   └── access_token_expires
        │   └── s3/
        │       ├── endpoint_url
        │       ├── access_key_id
        │       ├── secret_access_key
        │       ├── bucket_name
        │       └── region
        ├── docker/           # Environnement Docker local (.env.docker)
        │   ├── database/
        │   ├── jwt/
        │   └── s3/
        └── prod/             # Production (.env.production)
            ├── database/
            ├── jwt/
            └── s3/
```

**Note sur les environnements :**
- `dev` : Développement local (correspond à `.env.development`)
- `docker` : Docker Compose local (correspond à `.env.docker`) - **environnement principal pour le développement**
- `prod` : Production (correspond à `.env.production`)

**Commandes pour créer les secrets (environnement docker - recommandé pour le développement):**

```bash
# Secrets de base de données (Docker)
docker exec -it saas-vault vault kv put secret/saas-project/docker/database \
  main_url="postgresql://postgres:postgres@postgres:5432/saas_platform" \
  tenant_url_template="postgresql://postgres:postgres@postgres:5432/{database_name}"

# Secrets JWT (Docker)
docker exec -it saas-vault vault kv put secret/saas-project/docker/jwt \
  secret_key="dev-secret-jwt-key-change-in-production" \
  access_token_expires="900"

# Secrets S3/MinIO (Docker)
docker exec -it saas-vault vault kv put secret/saas-project/docker/s3 \
  endpoint_url="http://minio:9000" \
  access_key_id="minioadmin" \
  secret_access_key="minioadmin" \
  bucket_name="saas-documents" \
  region="us-east-1"

# Vérifier la création
docker exec -it saas-vault vault kv get secret/saas-project/docker/database
```

**Commandes pour créer les secrets (environnement dev - développement local sans Docker):**

```bash
# Secrets de base de données (Dev local)
docker exec -it saas-vault vault kv put secret/saas-project/dev/database \
  main_url="postgresql://postgres:postgres@localhost:5432/saas_platform" \
  tenant_url_template="postgresql://postgres:postgres@localhost:5432/{database_name}"

# Secrets JWT (Dev local)
docker exec -it saas-vault vault kv put secret/saas-project/dev/jwt \
  secret_key="dev-local-secret-jwt-key" \
  access_token_expires="900"

# Secrets S3/MinIO (Dev local)
docker exec -it saas-vault vault kv put secret/saas-project/dev/s3 \
  endpoint_url="http://localhost:9000" \
  access_key_id="minioadmin" \
  secret_access_key="minioadmin" \
  bucket_name="saas-documents" \
  region="us-east-1"
```

### 3.4 Création de la Politique d'Accès (ACL Policy) - ⚙️ AUTOMATISÉ

> **✅ Cette étape est automatiquement exécutée par `init-vault.sh`**
>
> La politique est créée dynamiquement pour chaque environnement (dev, docker, prod)

**Exemple de politique (générée automatiquement) :**

```hcl
# Politique pour l'application SaaS Flask
# Permet uniquement la lecture des secrets pour les environnements dev, docker et prod

# ============================================================================
# Environnement DEV (développement local)
# ============================================================================
path "secret/data/saas-project/dev/database" {
  capabilities = ["read"]
}

path "secret/data/saas-project/dev/jwt" {
  capabilities = ["read"]
}

path "secret/data/saas-project/dev/s3" {
  capabilities = ["read"]
}

path "secret/metadata/saas-project/dev/*" {
  capabilities = ["list", "read"]
}

# ============================================================================
# Environnement DOCKER (Docker Compose local)
# ============================================================================
path "secret/data/saas-project/docker/database" {
  capabilities = ["read"]
}

path "secret/data/saas-project/docker/jwt" {
  capabilities = ["read"]
}

path "secret/data/saas-project/docker/s3" {
  capabilities = ["read"]
}

path "secret/metadata/saas-project/docker/*" {
  capabilities = ["list", "read"]
}

# ============================================================================
# Environnement PROD (production)
# ============================================================================
path "secret/data/saas-project/prod/database" {
  capabilities = ["read"]
}

path "secret/data/saas-project/prod/jwt" {
  capabilities = ["read"]
}

path "secret/data/saas-project/prod/s3" {
  capabilities = ["read"]
}

path "secret/metadata/saas-project/prod/*" {
  capabilities = ["list", "read"]
}

# ============================================================================
# Gestion des tokens
# ============================================================================
# Renouvellement de token
path "auth/token/renew-self" {
  capabilities = ["update"]
}

# Lookup du token (pour vérifier TTL)
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
```

**Créer la politique dans Vault:**

```bash
# Copier le fichier de politique dans le conteneur
docker cp vault/policies/saas-app-policy.hcl saas-vault:/tmp/

# Créer la politique
docker exec -it saas-vault vault policy write saas-app-policy /tmp/saas-app-policy.hcl

# Vérifier la création
docker exec -it saas-vault vault policy read saas-app-policy
```

### 3.5 Configuration de l'Authentification AppRole - ⚙️ AUTOMATISÉ

> **✅ Toutes ces étapes sont automatiquement exécutées par `init-vault.sh`**
>
> Le script génère également le fichier `.env.vault` avec les credentials AppRole

**Étape 1: Activer la méthode d'authentification AppRole** (automatique)

```bash
docker exec -it saas-vault vault auth enable approle
```

**Étape 2: Créer un rôle AppRole pour l'application Flask**

```bash
docker exec -it saas-vault vault write auth/approle/role/saas-app-role \
  token_policies="saas-app-policy" \
  token_ttl=1h \
  token_max_ttl=4h \
  secret_id_ttl=0 \
  secret_id_num_uses=0
```

**Paramètres expliqués:**
- `token_policies`: Politique(s) associée(s) au token généré
- `token_ttl`: Durée de vie initiale du token (1 heure)
- `token_max_ttl`: Durée maximale après renouvellements (4 heures)
- `secret_id_ttl=0`: Secret ID ne expire jamais (OK pour dev, à restreindre en prod)
- `secret_id_num_uses=0`: Secret ID réutilisable à l'infini (OK pour dev)

**Étape 3: Récupérer le Role ID**

```bash
docker exec -it saas-vault vault read auth/approle/role/saas-app-role/role-id
```

**Sortie:**

```
Key        Value
---        -----
role_id    a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Étape 4: Générer un Secret ID**

```bash
docker exec -it saas-vault vault write -f auth/approle/role/saas-app-role/secret-id
```

**Sortie:**

```
Key                   Value
---                   -----
secret_id             f9e8d7c6-b5a4-3210-9876-543210fedcba
secret_id_accessor    accessor-xyz123
secret_id_ttl         0s
```

**Étape 5: Stocker les credentials AppRole pour Docker Compose**

**Fichier:** `.env.vault` (à créer, **NE PAS COMMITER**)

```bash
# AppRole credentials pour l'authentification à Vault
VAULT_ADDR=http://vault:8200
VAULT_ROLE_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890
VAULT_SECRET_ID=f9e8d7c6-b5a4-3210-9876-543210fedcba
```

**Ajouter à `.gitignore`:**

```
.env.vault
```

### 3.6 Test de l'Authentification AppRole

**Vérifier que l'authentification fonctionne:**

```bash
# Obtenir un token avec Role ID et Secret ID
docker exec -it saas-vault vault write auth/approle/login \
  role_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  secret_id="f9e8d7c6-b5a4-3210-9876-543210fedcba"
```

**Sortie attendue:**

```
Key                     Value
---                     -----
token                   hvs.CAESIJxxx...
token_accessor          accessor-123
token_duration          1h
token_renewable         true
token_policies          ["default" "saas-app-policy"]
```

**Tester l'accès aux secrets avec le token obtenu:**

```bash
export VAULT_TOKEN="hvs.CAESIJxxx..."

docker exec -e VAULT_TOKEN=$VAULT_TOKEN -it saas-vault \
  vault kv get secret/saas-project/dev/database
```

Si la commande retourne les secrets, l'authentification AppRole fonctionne correctement.

---

## 4. Phase 3 - Mise à jour de l'Application Flask

### 4.1 Création du Module VaultClient

**Fichier:** `backend/app/utils/vault_client.py`

```python
"""
Module de gestion de l'authentification et des interactions avec HashiCorp Vault.
Utilise la méthode AppRole pour l'authentification.
"""

import os
import logging
from typing import Dict, Any, Optional
import hvac
from hvac.exceptions import VaultError, InvalidPath

logger = logging.getLogger(__name__)


class VaultClient:
    """
    Client Vault pour l'authentification AppRole et la récupération de secrets.
    """

    def __init__(
        self,
        vault_addr: Optional[str] = None,
        role_id: Optional[str] = None,
        secret_id: Optional[str] = None,
    ):
        """
        Initialise le client Vault.

        Args:
            vault_addr: URL du serveur Vault (ex: http://vault:8200)
            role_id: Role ID pour l'authentification AppRole
            secret_id: Secret ID pour l'authentification AppRole
        """
        self.vault_addr = vault_addr or os.environ.get("VAULT_ADDR")
        self.role_id = role_id or os.environ.get("VAULT_ROLE_ID")
        self.secret_id = secret_id or os.environ.get("VAULT_SECRET_ID")

        if not all([self.vault_addr, self.role_id, self.secret_id]):
            raise ValueError(
                "VAULT_ADDR, VAULT_ROLE_ID et VAULT_SECRET_ID doivent être définis"
            )

        self.client: Optional[hvac.Client] = None
        self.token: Optional[str] = None
        self.token_ttl: int = 0

        logger.info(f"VaultClient initialisé avec l'adresse: {self.vault_addr}")

    def authenticate(self) -> str:
        """
        Authentifie l'application auprès de Vault en utilisant AppRole.

        Returns:
            str: Token Vault obtenu

        Raises:
            VaultError: En cas d'erreur d'authentification
        """
        try:
            # Créer un client Vault non authentifié
            self.client = hvac.Client(url=self.vault_addr)

            # Vérifier que Vault est accessible
            if not self.client.sys.is_initialized():
                raise VaultError("Vault n'est pas initialisé")

            if self.client.sys.is_sealed():
                raise VaultError("Vault est scellé (sealed)")

            logger.info("Connexion à Vault établie, tentative d'authentification AppRole...")

            # Authentification avec AppRole
            auth_response = self.client.auth.approle.login(
                role_id=self.role_id,
                secret_id=self.secret_id,
            )

            # Extraire le token et le TTL
            self.token = auth_response["auth"]["client_token"]
            self.token_ttl = auth_response["auth"]["lease_duration"]

            # Définir le token sur le client
            self.client.token = self.token

            logger.info(
                f"Authentification AppRole réussie. Token TTL: {self.token_ttl}s"
            )

            return self.token

        except VaultError as e:
            logger.error(f"Erreur d'authentification Vault: {e}")
            raise
        except Exception as e:
            logger.error(f"Erreur inattendue lors de l'authentification Vault: {e}")
            raise VaultError(f"Erreur inattendue: {e}")

    def get_secret(self, path: str) -> Dict[str, Any]:
        """
        Récupère un secret depuis Vault.

        Args:
            path: Chemin du secret (ex: "saas-project/dev/database")

        Returns:
            Dict contenant les données du secret

        Raises:
            VaultError: En cas d'erreur de récupération
        """
        if not self.client or not self.client.is_authenticated():
            logger.warning("Client non authentifié, tentative d'authentification...")
            self.authenticate()

        try:
            # Le chemin KV v2 nécessite le préfixe "secret/data/"
            full_path = f"secret/data/{path}"
            logger.debug(f"Lecture du secret: {full_path}")

            response = self.client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point="secret",
            )

            secret_data = response["data"]["data"]
            logger.info(f"Secret récupéré avec succès: {path}")

            return secret_data

        except InvalidPath:
            logger.error(f"Chemin de secret invalide ou inexistant: {path}")
            raise VaultError(f"Secret non trouvé: {path}")
        except VaultError as e:
            logger.error(f"Erreur lors de la récupération du secret {path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la lecture du secret {path}: {e}")
            raise VaultError(f"Erreur inattendue: {e}")

    def get_all_secrets(self, environment: str = "dev") -> Dict[str, Any]:
        """
        Récupère tous les secrets nécessaires pour l'application.

        Args:
            environment: Environnement (dev, prod)

        Returns:
            Dict avec tous les secrets organisés par catégorie
        """
        secrets = {}

        # Liste des chemins de secrets à récupérer
        secret_paths = {
            "database": f"saas-project/{environment}/database",
            "jwt": f"saas-project/{environment}/jwt",
            "s3": f"saas-project/{environment}/s3",
        }

        for category, path in secret_paths.items():
            try:
                secrets[category] = self.get_secret(path)
            except VaultError as e:
                logger.error(f"Impossible de récupérer les secrets {category}: {e}")
                raise

        logger.info(f"Tous les secrets de l'environnement '{environment}' récupérés")
        return secrets

    def renew_token(self) -> int:
        """
        Renouvelle le token Vault actuel.

        Returns:
            int: Nouveau TTL du token en secondes

        Raises:
            VaultError: En cas d'erreur de renouvellement
        """
        if not self.client or not self.token:
            raise VaultError("Client non authentifié, impossible de renouveler le token")

        try:
            logger.info("Renouvellement du token Vault...")

            response = self.client.auth.token.renew_self()
            self.token_ttl = response["auth"]["lease_duration"]

            logger.info(f"Token renouvelé avec succès. Nouveau TTL: {self.token_ttl}s")

            return self.token_ttl

        except VaultError as e:
            logger.error(f"Erreur lors du renouvellement du token: {e}")
            raise
        except Exception as e:
            logger.error(f"Erreur inattendue lors du renouvellement: {e}")
            raise VaultError(f"Erreur inattendue: {e}")

    def get_token_ttl(self) -> int:
        """
        Récupère le TTL restant du token actuel.

        Returns:
            int: TTL en secondes
        """
        if not self.client or not self.token:
            return 0

        try:
            response = self.client.auth.token.lookup_self()
            return response["data"]["ttl"]
        except Exception as e:
            logger.warning(f"Impossible de récupérer le TTL du token: {e}")
            return 0

    def is_authenticated(self) -> bool:
        """
        Vérifie si le client est authentifié.

        Returns:
            bool: True si authentifié, False sinon
        """
        return self.client is not None and self.client.is_authenticated()
```

### 4.2 Modification du Module de Configuration

**Fichier:** `backend/app/config.py`

**Ajouter la méthode de chargement depuis Vault:**

```python
import os
from datetime import timedelta


class Config:
    """Configuration de base"""

    # Flag pour activer Vault
    USE_VAULT = os.environ.get("USE_VAULT", "false").lower() == "true"
    VAULT_ENVIRONMENT = os.environ.get("VAULT_ENVIRONMENT", "dev")

    # Configuration Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # Configuration de la base de données (fallback sur .env)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/saas_platform"
    )
    TENANT_DATABASE_URL_TEMPLATE = os.environ.get(
        "TENANT_DATABASE_URL_TEMPLATE",
        "postgresql://postgres:postgres@localhost:5432/{database_name}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_timeout": 30,
        "pool_recycle": 3600,
        "max_overflow": 20,
    }

    # Configuration JWT (fallback sur .env)
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-secret-key")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", "900"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    JWT_BLACKLIST_ENABLED = True
    JWT_BLACKLIST_TOKEN_CHECKS = ["access", "refresh"]

    # Configuration S3 (fallback sur .env)
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")
    S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID", "minioadmin")
    S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY", "minioadmin")
    S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "saas-documents")
    S3_REGION = os.environ.get("S3_REGION", "us-east-1")

    # Configuration Kafka
    KAFKA_BOOTSTRAP_SERVERS = os.environ.get(
        "KAFKA_BOOTSTRAP_SERVERS", "localhost:9093"
    )

    @classmethod
    def load_from_vault(cls, vault_client):
        """
        Charge la configuration depuis HashiCorp Vault.

        Args:
            vault_client: Instance de VaultClient authentifié
        """
        from app.utils.vault_client import VaultError
        import logging

        logger = logging.getLogger(__name__)

        try:
            logger.info(
                f"Chargement de la configuration depuis Vault (env: {cls.VAULT_ENVIRONMENT})"
            )

            # Récupérer tous les secrets
            secrets = vault_client.get_all_secrets(environment=cls.VAULT_ENVIRONMENT)

            # Configuration Database
            if "database" in secrets:
                db_secrets = secrets["database"]
                cls.SQLALCHEMY_DATABASE_URI = db_secrets.get("main_url")
                cls.TENANT_DATABASE_URL_TEMPLATE = db_secrets.get("tenant_url_template")
                logger.info("Configuration database chargée depuis Vault")

            # Configuration JWT
            if "jwt" in secrets:
                jwt_secrets = secrets["jwt"]
                cls.JWT_SECRET_KEY = jwt_secrets.get("secret_key")
                cls.SECRET_KEY = jwt_secrets.get("secret_key")  # Utiliser la même clé

                # Gestion du TTL
                access_token_expires = jwt_secrets.get("access_token_expires")
                if access_token_expires:
                    cls.JWT_ACCESS_TOKEN_EXPIRES = timedelta(
                        seconds=int(access_token_expires)
                    )
                logger.info("Configuration JWT chargée depuis Vault")

            # Configuration S3
            if "s3" in secrets:
                s3_secrets = secrets["s3"]
                cls.S3_ENDPOINT_URL = s3_secrets.get("endpoint_url")
                cls.S3_ACCESS_KEY_ID = s3_secrets.get("access_key_id")
                cls.S3_SECRET_ACCESS_KEY = s3_secrets.get("secret_access_key")
                cls.S3_BUCKET_NAME = s3_secrets.get("bucket_name")
                cls.S3_REGION = s3_secrets.get("region")
                logger.info("Configuration S3 chargée depuis Vault")

            logger.info("Configuration complète chargée depuis Vault avec succès")

        except VaultError as e:
            logger.error(f"Erreur lors du chargement de la configuration depuis Vault: {e}")
            logger.warning("Utilisation de la configuration par défaut (variables d'environnement)")
            # On laisse les valeurs par défaut chargées depuis .env
        except Exception as e:
            logger.error(f"Erreur inattendue lors du chargement depuis Vault: {e}")
            raise


class DevelopmentConfig(Config):
    """Configuration de développement"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Configuration de production"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Configuration de test"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
```

### 4.3 Modification du Point d'Entrée de l'Application

**Fichier:** `backend/run.py`

**Important:** Ce fichier sert à deux usages :
1. **Développement local** : Lancement direct avec `python run.py` (serveur Flask intégré)
2. **Production avec Gunicorn** : Gunicorn appelle `run:app` pour obtenir l'instance Flask

```python
"""
Point d'entrée de l'application Flask.
Gère l'initialisation de Vault et le démarrage du serveur.

Usage:
  - Développement: python run.py
  - Production (Gunicorn): gunicorn run:app
"""

import os
import sys
import logging
from app import create_app

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def initialize_vault():
    """
    Initialise la connexion à Vault et charge les secrets.

    Returns:
        VaultClient authentifié ou None si Vault n'est pas activé
    """
    use_vault = os.environ.get("USE_VAULT", "false").lower() == "true"

    if not use_vault:
        logger.info("Vault désactivé (USE_VAULT=false). Utilisation des variables d'environnement.")
        return None

    try:
        from app.utils.vault_client import VaultClient, VaultError

        logger.info("Initialisation de Vault...")

        # Créer le client Vault
        vault_client = VaultClient()

        # Authentification AppRole
        vault_client.authenticate()

        logger.info("Authentification Vault réussie")

        return vault_client

    except VaultError as e:
        logger.error(f"Erreur d'initialisation de Vault: {e}")
        logger.error("L'application ne peut pas démarrer sans accès à Vault")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'initialisation de Vault: {e}")
        sys.exit(1)


# Initialiser Vault et créer l'application Flask
# Cette instance est utilisée par Gunicorn (run:app)
vault_client = initialize_vault()
config_name = os.environ.get("FLASK_ENV", "development")
app = create_app(config_name, vault_client=vault_client)


def main():
    """
    Point d'entrée pour le développement local uniquement.
    En production, Gunicorn utilise directement l'objet 'app' ci-dessus.
    """
    # Démarrer le serveur Flask intégré (développement uniquement)
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 4999))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    logger.info(f"Démarrage du serveur Flask sur {host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
```

### 4.4 Modification de la Factory de l'Application

**Fichier:** `backend/app/__init__.py`

```python
"""
Factory de l'application Flask.
"""

import logging
from flask import Flask
from app.config import config
from app.extensions import initialize_extensions
from app.routes import register_blueprints
from app.errors import register_error_handlers

logger = logging.getLogger(__name__)


def create_app(config_name="development", vault_client=None):
    """
    Factory pour créer l'application Flask.

    Args:
        config_name: Nom de la configuration (development, production, testing)
        vault_client: Instance de VaultClient (optionnel)

    Returns:
        Application Flask configurée
    """
    app = Flask(__name__)

    # Charger la configuration de base
    app.config.from_object(config[config_name])

    # Charger les secrets depuis Vault si disponible
    if vault_client and app.config.get("USE_VAULT"):
        logger.info("Chargement de la configuration depuis Vault...")
        config[config_name].load_from_vault(vault_client)

        # Stocker le client Vault dans l'app context pour le renouvellement de token
        app.vault_client = vault_client
    else:
        logger.info("Utilisation de la configuration par défaut (variables d'environnement)")
        app.vault_client = None

    # Initialiser les extensions
    initialize_extensions(app)

    # Enregistrer les blueprints
    register_blueprints(app)

    # Enregistrer les gestionnaires d'erreurs
    register_error_handlers(app)

    # Configuration du logging
    configure_logging(app)

    # Shell context pour flask shell
    register_shell_context(app)

    logger.info(f"Application Flask créée avec succès (config: {config_name})")

    return app


def configure_logging(app):
    """Configure le logging de l'application."""
    if not app.debug and not app.testing:
        # Configuration pour la production
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


def register_shell_context(app):
    """Enregistre le contexte du shell Flask."""
    from app.models.user import User
    from app.models.tenant import Tenant
    from app.extensions import db

    @app.shell_context_processor
    def make_shell_context():
        return {
            "db": db,
            "User": User,
            "Tenant": Tenant,
        }
```

### 4.5 Création du Script d'Entrypoint Docker

**Fichier:** `backend/scripts/docker-entrypoint.sh`

```bash
#!/bin/bash
set -e

echo "==================================="
echo "SaaS Platform - Docker Entrypoint"
echo "==================================="

# Attendre que Vault soit prêt (si activé)
if [ "$USE_VAULT" = "true" ]; then
    echo "Vault activé, vérification de la disponibilité..."

    MAX_RETRIES=30
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -s -o /dev/null -w "%{http_code}" "$VAULT_ADDR/v1/sys/health" | grep -q "200\|429\|473"; then
            echo "Vault est accessible et initialisé"
            break
        fi

        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo "Attente de Vault... ($RETRY_COUNT/$MAX_RETRIES)"
        sleep 2
    done

    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo "ERREUR: Vault n'est pas accessible après $MAX_RETRIES tentatives"
        exit 1
    fi
fi

# Exécuter les migrations de base de données (si en mode API)
if [ "$FLASK_APP_TYPE" = "api" ]; then
    echo "Exécution des migrations de base de données..."
    flask db upgrade || {
        echo "ERREUR: Échec des migrations de base de données"
        exit 1
    }
fi

echo "Démarrage de l'application..."
echo "==================================="

# Exécuter la commande passée au conteneur
exec "$@"
```

**Rendre le script exécutable:**

```bash
chmod +x backend/scripts/docker-entrypoint.sh
```

### 4.6 Mise à jour des Dockerfiles

**Fichier:** `docker/Dockerfile.api`

**Ajouter l'entrypoint (garder le CMD Gunicorn existant):**

```dockerfile
# ... contenu existant ...

# Copier le script d'entrypoint
COPY backend/scripts/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Définir l'entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Commande par défaut (Gunicorn pour production)
# IMPORTANT: Garder la configuration Gunicorn existante
CMD ["gunicorn", \
     "-w", "4", \
     "-b", "0.0.0.0:4999", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "50", \
     "run:app"]
```

**Note:** L'entrypoint script exécutera les vérifications (Vault, migrations) puis lancera Gunicorn via `exec "$@"`.

**Fichier:** `docker/Dockerfile.worker`

**Même modification pour le worker:**

```dockerfile
# ... contenu existant ...

# Copier le script d'entrypoint
COPY backend/scripts/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Définir l'entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Commande par défaut
CMD ["python", "-m", "app.worker.consumer"]
```

### 4.7 Mise à jour de docker-compose.yml avec les Variables Vault

**Fichier:** `docker-compose.yml`

**Modifier les services `api` et `worker`:**

```yaml
services:
  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    container_name: saas-api
    ports:
      - "4999:4999"
    env_file:
      - .env.docker
      - .env.vault  # AJOUT: Variables Vault
    environment:
      # Activation de Vault
      USE_VAULT: "true"
      VAULT_ENVIRONMENT: "docker"  # Utilise l'environnement docker de Vault
      VAULT_ADDR: "http://vault:8200"
      # Les VAULT_ROLE_ID et VAULT_SECRET_ID sont chargés depuis .env.vault

      # Configuration Flask
      FLASK_APP_TYPE: "api"
      FLASK_ENV: "development"
      FLASK_DEBUG: "false"
      FLASK_HOST: "0.0.0.0"
      FLASK_PORT: "4999"
    depends_on:
      postgres:
        condition: service_healthy
      kafka:
        condition: service_healthy
      minio:
        condition: service_healthy
      vault:
        condition: service_healthy
    networks:
      - saas-network
    volumes:
      - ./backend:/app
    restart: unless-stopped

  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    container_name: saas-worker
    env_file:
      - .env.docker
      - .env.vault  # AJOUT: Variables Vault
    environment:
      # Activation de Vault
      USE_VAULT: "true"
      VAULT_ENVIRONMENT: "docker"  # Utilise l'environnement docker de Vault
      VAULT_ADDR: "http://vault:8200"

      # Configuration Worker
      FLASK_ENV: "development"
      WORKER_TYPE: "kafka_consumer"
    depends_on:
      postgres:
        condition: service_healthy
      kafka:
        condition: service_healthy
      minio:
        condition: service_healthy
      vault:
        condition: service_healthy
    networks:
      - saas-network
    volumes:
      - ./backend:/app
    restart: unless-stopped
```

---

## 5. Phase 4 - Implémentation du Renouvellement de Token

### 5.1 Création du Module de Renouvellement de Token

**Fichier:** `backend/app/utils/vault_token_renewer.py`

```python
"""
Module de renouvellement automatique des tokens Vault.
Utilise un thread en arrière-plan pour surveiller et renouveler le token.
"""

import time
import logging
import threading
from typing import Optional
from app.utils.vault_client import VaultClient, VaultError

logger = logging.getLogger(__name__)


class VaultTokenRenewer:
    """
    Gestionnaire de renouvellement automatique des tokens Vault.
    """

    def __init__(
        self,
        vault_client: VaultClient,
        renewal_threshold: float = 0.75,
        check_interval: int = 60,
    ):
        """
        Initialise le renewer.

        Args:
            vault_client: Instance de VaultClient authentifié
            renewal_threshold: Seuil de renouvellement (0.75 = renouveler à 75% du TTL)
            check_interval: Intervalle de vérification en secondes
        """
        self.vault_client = vault_client
        self.renewal_threshold = renewal_threshold
        self.check_interval = check_interval

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False

        logger.info(
            f"VaultTokenRenewer initialisé (threshold: {renewal_threshold}, "
            f"interval: {check_interval}s)"
        )

    def start(self):
        """Démarre le thread de renouvellement."""
        if self._running:
            logger.warning("Le renewer est déjà démarré")
            return

        logger.info("Démarrage du renouvellement automatique de token Vault...")

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._renewal_loop, daemon=True)
        self._thread.start()
        self._running = True

        logger.info("Thread de renouvellement démarré")

    def stop(self):
        """Arrête le thread de renouvellement."""
        if not self._running:
            return

        logger.info("Arrêt du renouvellement automatique de token Vault...")

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

        self._running = False
        logger.info("Thread de renouvellement arrêté")

    def _renewal_loop(self):
        """
        Boucle principale de renouvellement.
        Vérifie périodiquement le TTL et renouvelle si nécessaire.
        """
        logger.info("Boucle de renouvellement de token démarrée")

        while not self._stop_event.is_set():
            try:
                # Vérifier si le client est authentifié
                if not self.vault_client.is_authenticated():
                    logger.error("Client Vault non authentifié, tentative de réauthentification...")
                    try:
                        self.vault_client.authenticate()
                        logger.info("Réauthentification réussie")
                    except VaultError as e:
                        logger.critical(f"Échec de la réauthentification: {e}")
                        # Attendre avant de réessayer
                        time.sleep(self.check_interval)
                        continue

                # Récupérer le TTL actuel
                current_ttl = self.vault_client.get_token_ttl()

                if current_ttl <= 0:
                    logger.warning("TTL du token expiré ou invalide, réauthentification...")
                    try:
                        self.vault_client.authenticate()
                        logger.info("Réauthentification réussie")
                    except VaultError as e:
                        logger.critical(f"Échec de la réauthentification: {e}")

                    time.sleep(self.check_interval)
                    continue

                # Calculer le seuil de renouvellement
                # Si le token a un TTL de 3600s et threshold=0.75, on renouvelle à 900s restants
                initial_ttl = self.vault_client.token_ttl
                renewal_time = initial_ttl * (1 - self.renewal_threshold)

                logger.debug(
                    f"TTL actuel: {current_ttl}s, TTL initial: {initial_ttl}s, "
                    f"Seuil de renouvellement: {renewal_time}s"
                )

                # Renouveler si on atteint le seuil
                if current_ttl <= renewal_time:
                    logger.info(
                        f"Seuil de renouvellement atteint ({current_ttl}s <= {renewal_time}s), "
                        f"renouvellement du token..."
                    )

                    try:
                        new_ttl = self.vault_client.renew_token()
                        logger.info(f"Token renouvelé avec succès, nouveau TTL: {new_ttl}s")
                    except VaultError as e:
                        logger.error(f"Échec du renouvellement du token: {e}")
                        logger.warning("Tentative de réauthentification...")
                        try:
                            self.vault_client.authenticate()
                            logger.info("Réauthentification réussie")
                        except VaultError as auth_error:
                            logger.critical(
                                f"Échec de la réauthentification: {auth_error}"
                            )

            except Exception as e:
                logger.error(f"Erreur inattendue dans la boucle de renouvellement: {e}")

            # Attendre avant la prochaine vérification
            self._stop_event.wait(timeout=self.check_interval)

        logger.info("Boucle de renouvellement de token terminée")

    def is_running(self) -> bool:
        """
        Vérifie si le renewer est en cours d'exécution.

        Returns:
            bool: True si en cours, False sinon
        """
        return self._running
```

### 5.2 Intégration du Renewer dans l'Application Flask

**Fichier:** `backend/app/__init__.py`

**Ajouter le démarrage du renewer:**

```python
"""
Factory de l'application Flask.
"""

import logging
import atexit
from flask import Flask
from app.config import config
from app.extensions import initialize_extensions
from app.routes import register_blueprints
from app.errors import register_error_handlers

logger = logging.getLogger(__name__)


def create_app(config_name="development", vault_client=None):
    """
    Factory pour créer l'application Flask.

    Args:
        config_name: Nom de la configuration (development, production, testing)
        vault_client: Instance de VaultClient (optionnel)

    Returns:
        Application Flask configurée
    """
    app = Flask(__name__)

    # Charger la configuration de base
    app.config.from_object(config[config_name])

    # Charger les secrets depuis Vault si disponible
    if vault_client and app.config.get("USE_VAULT"):
        logger.info("Chargement de la configuration depuis Vault...")
        config[config_name].load_from_vault(vault_client)

        # Stocker le client Vault dans l'app context
        app.vault_client = vault_client

        # Démarrer le renouvellement automatique de token
        from app.utils.vault_token_renewer import VaultTokenRenewer

        app.vault_renewer = VaultTokenRenewer(
            vault_client=vault_client,
            renewal_threshold=0.75,  # Renouveler à 75% du TTL
            check_interval=60,  # Vérifier toutes les 60 secondes
        )
        app.vault_renewer.start()
        logger.info("Renouvellement automatique de token Vault activé")

        # Enregistrer l'arrêt du renewer lors de la fermeture de l'app
        @atexit.register
        def cleanup_vault_renewer():
            if hasattr(app, "vault_renewer") and app.vault_renewer:
                logger.info("Arrêt du renouvellement de token Vault...")
                app.vault_renewer.stop()
    else:
        logger.info("Utilisation de la configuration par défaut (variables d'environnement)")
        app.vault_client = None
        app.vault_renewer = None

    # Initialiser les extensions
    initialize_extensions(app)

    # Enregistrer les blueprints
    register_blueprints(app)

    # Enregistrer les gestionnaires d'erreurs
    register_error_handlers(app)

    # Configuration du logging
    configure_logging(app)

    # Shell context pour flask shell
    register_shell_context(app)

    logger.info(f"Application Flask créée avec succès (config: {config_name})")

    return app


def configure_logging(app):
    """Configure le logging de l'application."""
    if not app.debug and not app.testing:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


def register_shell_context(app):
    """Enregistre le contexte du shell Flask."""
    from app.models.user import User
    from app.models.tenant import Tenant
    from app.extensions import db

    @app.shell_context_processor
    def make_shell_context():
        return {
            "db": db,
            "User": User,
            "Tenant": Tenant,
        }
```

### 5.3 Gestion des Signaux et Arrêt Gracieux

**Fichier:** `backend/run.py`

**Ajouter la gestion des signaux SIGTERM/SIGINT:**

```python
"""
Point d'entrée de l'application Flask.
Gère l'initialisation de Vault et le démarrage du serveur.
"""

import os
import sys
import signal
import logging
from app import create_app

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

# Variable globale pour l'application (pour les signal handlers)
app_instance = None


def signal_handler(signum, frame):
    """
    Gestionnaire de signaux pour un arrêt gracieux.
    """
    logger.info(f"Signal {signum} reçu, arrêt gracieux de l'application...")

    if app_instance and hasattr(app_instance, "vault_renewer"):
        if app_instance.vault_renewer:
            app_instance.vault_renewer.stop()

    sys.exit(0)


def initialize_vault():
    """
    Initialise la connexion à Vault et charge les secrets.

    Returns:
        VaultClient authentifié ou None si Vault n'est pas activé
    """
    use_vault = os.environ.get("USE_VAULT", "false").lower() == "true"

    if not use_vault:
        logger.info("Vault désactivé (USE_VAULT=false). Utilisation des variables d'environnement.")
        return None

    try:
        from app.utils.vault_client import VaultClient, VaultError

        logger.info("Initialisation de Vault...")

        # Créer le client Vault
        vault_client = VaultClient()

        # Authentification AppRole
        vault_client.authenticate()

        logger.info("Authentification Vault réussie")

        return vault_client

    except VaultError as e:
        logger.error(f"Erreur d'initialisation de Vault: {e}")
        logger.error("L'application ne peut pas démarrer sans accès à Vault")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'initialisation de Vault: {e}")
        sys.exit(1)


def main():
    """Point d'entrée principal de l'application."""
    global app_instance

    # Enregistrer les gestionnaires de signaux
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 1. Initialiser Vault (si activé)
    vault_client = initialize_vault()

    # 2. Créer l'application Flask
    config_name = os.environ.get("FLASK_ENV", "development")
    app_instance = create_app(config_name, vault_client=vault_client)

    # 3. Démarrer le serveur
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 4999))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    logger.info(f"Démarrage du serveur Flask sur {host}:{port}")
    app_instance.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
```

---

## 6. Phase 5 - Migration et Tests

### 6.1 Checklist de Migration

**Étape par étape:**

- [ ] **Préparation:**
  - [ ] Backup des fichiers `.env` actuels
  - [ ] Documentation des secrets existants
  - [ ] Création du fichier `.env.vault` avec Role ID et Secret ID

- [ ] **Déploiement de Vault:**
  - [ ] Ajout du service Vault dans `docker-compose.yml`
  - [ ] Démarrage du conteneur Vault
  - [ ] Vérification de l'état de Vault (`vault status`)

- [ ] **Configuration de Vault:**
  - [ ] Activation du KV Secrets Engine v2
  - [ ] Création de la structure de chemins
  - [ ] Injection de tous les secrets dans Vault
  - [ ] Création de la politique ACL
  - [ ] Configuration d'AppRole
  - [ ] Génération et sauvegarde des credentials AppRole

- [ ] **Mise à jour du Code:**
  - [ ] Ajout de `hvac` dans `requirements.txt`
  - [ ] Création de `vault_client.py`
  - [ ] Création de `vault_token_renewer.py`
  - [ ] Modification de `config.py`
  - [ ] Modification de `run.py`
  - [ ] Modification de `__init__.py`
  - [ ] Création de `docker-entrypoint.sh`
  - [ ] Mise à jour des Dockerfiles

- [ ] **Tests:**
  - [ ] Tests unitaires du VaultClient
  - [ ] Tests d'intégration avec Vault
  - [ ] Tests du renouvellement de token
  - [ ] Tests de l'application complète

- [ ] **Déploiement:**
  - [ ] Rebuild des images Docker
  - [ ] Démarrage des services avec Vault activé
  - [ ] Vérification des logs
  - [ ] Tests fonctionnels de l'application

### 6.2 Workflow d'Initialisation Automatique

> **✅ La migration des secrets est automatisée via le service `vault-init`**
>
> Cette section explique le workflow complet d'initialisation

#### 6.2.1 Premier Démarrage - Configuration Initiale

**Étape 1 : Vérifier que les Secrets Initiaux Sont Prêts**

```bash
# Vérifier que le fichier de secrets existe
ls -l vault/init-data/docker.env

# Si le fichier n'existe pas, le créer (voir Section 2.7)
# Exemple rapide :
cat > vault/init-data/docker.env <<'EOF'
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/saas_platform
TENANT_DATABASE_URL_TEMPLATE=postgresql://postgres:postgres@postgres:5432/{database_name}
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ACCESS_TOKEN_EXPIRES=900
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents
S3_REGION=us-east-1
EOF
```

**Étape 2 : Démarrer Vault et L'Initialiser**

```bash
# Démarrer Vault
docker-compose up -d vault

# Attendre que Vault soit ready (quelques secondes)
docker-compose logs -f vault

# Démarrer l'initialisation automatique
docker-compose up -d vault-init

# Suivre l'initialisation en temps réel
docker-compose logs -f vault-init
```

**Sortie attendue de `vault-init` :**

```
==========================================
🔐 Initialisation Automatique de Vault
==========================================
Environnement : docker
Fichier source: /init-data/docker.env
==========================================

✓ Chargement des secrets depuis /init-data/docker.env
→ Attente de Vault...
→ Activation du KV Secrets Engine v2...
✓ KV engine activé
→ Injection des secrets DATABASE pour environnement 'docker'...
✓ Secrets DATABASE injectés
→ Injection des secrets JWT pour environnement 'docker'...
✓ Secrets JWT injectés
→ Injection des secrets S3 pour environnement 'docker'...
✓ Secrets S3 injectés
→ Configuration de l'authentification AppRole...
✓ AppRole activé
→ Création de la politique Vault pour environnement 'docker'...
✓ Politique créée: saas-app-policy-docker
→ Configuration du rôle AppRole...
✓ Rôle AppRole configuré: saas-app-role-docker
→ Génération des credentials AppRole...
→ Écriture du fichier .env.vault...
✓ Fichier .env.vault créé avec permissions 600

==========================================
✅ INITIALISATION TERMINÉE AVEC SUCCÈS
==========================================
Environnement  : docker
Secrets créés  : secret/saas-project/docker/*
Politique      : saas-app-policy-docker
Rôle AppRole   : saas-app-role-docker

📄 Credentials Vault:
   VAULT_ADDR     : http://vault:8200
   VAULT_ROLE_ID  : xxxxx-xxxxx-xxxxx
   VAULT_SECRET_ID: xxxxx-xxxxx-xxxxx

✓ Ces credentials ont été écrits dans .env.vault
✓ L'application peut maintenant démarrer et lire les secrets depuis Vault
==========================================
```

**Étape 3 : Vérifier Que .env.vault a Été Créé**

```bash
# Vérifier le fichier généré
cat .env.vault

# Sortie attendue :
# VAULT_ADDR=http://vault:8200
# VAULT_ROLE_ID=xxxxx-xxxxx-xxxxx
# VAULT_SECRET_ID=xxxxx-xxxxx-xxxxx
```

**Étape 4 : Démarrer l'Application**

```bash
# Démarrer tous les services
docker-compose up -d

# Vérifier les logs de l'API
docker-compose logs -f api

# Sortie attendue :
# - "Vault désactivé" OU "Initialisation de Vault..."
# - "Authentification Vault réussie"
# - "Chargement de la configuration depuis Vault..."
# - "Configuration database chargée depuis Vault"
# - "Listening at: http://0.0.0.0:4999" (Gunicorn)
```

#### 6.2.2 Redémarrages Ultérieurs

**Workflow Normal (Docker-Compose Up)**

```bash
# Un simple docker-compose up suffit
docker-compose up -d

# Le workflow automatique :
# 1. Vault démarre (mode dev, données en mémoire)
# 2. vault-init réinjecte automatiquement les secrets
# 3. .env.vault est regénéré
# 4. L'application démarre et lit depuis Vault
```

**En Cas de Problème**

```bash
# Redémarrer Vault et l'initialisation
docker-compose restart vault vault-init

# Vérifier les logs
docker-compose logs vault vault-init

# Forcer une réinitialisation complète
docker-compose down
docker-compose up -d vault vault-init
docker-compose logs -f vault-init
```

#### 6.2.3 Initialisation pour Différents Environnements

**Environnement DEV (développement local) :**

```bash
# Créer vault/init-data/dev.env d'abord (voir Section 2.7)

# Lancer avec l'environnement DEV
VAULT_ENV=dev docker-compose up -d vault vault-init

# Vérifier
docker-compose logs vault-init
```

**Environnement PROD (production) :**

```bash
# Sur le serveur de production :
# 1. Créer vault/init-data/prod.env avec les vraies valeurs

# 2. Lancer avec l'environnement PROD
VAULT_ENV=prod docker-compose up -d vault vault-init

# 3. Vérifier que .env.vault a été créé
cat .env.vault
```

#### 6.2.4 Vérification Manuelle des Secrets

**Vérifier que les secrets ont bien été injectés :**

```bash
# Se connecter au conteneur Vault
docker exec -it saas-vault sh

# À l'intérieur du conteneur
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='root-token-dev'

# Lister les secrets
vault kv list secret/saas-project/docker

# Lire un secret spécifique
vault kv get secret/saas-project/docker/database
vault kv get secret/saas-project/docker/jwt
vault kv get secret/saas-project/docker/s3

# Vérifier la politique
vault policy read saas-app-policy-docker

# Vérifier le rôle AppRole
vault read auth/approle/role/saas-app-role-docker

# Sortir
exit
```

### 6.3 Tests Unitaires du VaultClient

**Fichier:** `backend/tests/utils/test_vault_client.py`

```python
"""
Tests unitaires pour le VaultClient.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.utils.vault_client import VaultClient, VaultError


class TestVaultClient:
    """Tests pour la classe VaultClient."""

    @pytest.fixture
    def mock_env_vars(self, monkeypatch):
        """Mock des variables d'environnement."""
        monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
        monkeypatch.setenv("VAULT_ROLE_ID", "test-role-id")
        monkeypatch.setenv("VAULT_SECRET_ID", "test-secret-id")

    def test_init_with_env_vars(self, mock_env_vars):
        """Test l'initialisation avec les variables d'environnement."""
        client = VaultClient()

        assert client.vault_addr == "http://vault:8200"
        assert client.role_id == "test-role-id"
        assert client.secret_id == "test-secret-id"

    def test_init_without_credentials_raises_error(self):
        """Test que l'initialisation échoue sans credentials."""
        with pytest.raises(ValueError):
            VaultClient()

    @patch("hvac.Client")
    def test_authenticate_success(self, mock_hvac_client, mock_env_vars):
        """Test l'authentification réussie."""
        # Mock du client hvac
        mock_client_instance = MagicMock()
        mock_hvac_client.return_value = mock_client_instance

        # Mock des réponses
        mock_client_instance.sys.is_initialized.return_value = True
        mock_client_instance.sys.is_sealed.return_value = False
        mock_client_instance.auth.approle.login.return_value = {
            "auth": {
                "client_token": "test-token",
                "lease_duration": 3600,
            }
        }

        # Exécuter
        client = VaultClient()
        token = client.authenticate()

        # Vérifier
        assert token == "test-token"
        assert client.token == "test-token"
        assert client.token_ttl == 3600
        mock_client_instance.auth.approle.login.assert_called_once()

    @patch("hvac.Client")
    def test_get_secret_success(self, mock_hvac_client, mock_env_vars):
        """Test la récupération d'un secret."""
        # Setup
        mock_client_instance = MagicMock()
        mock_hvac_client.return_value = mock_client_instance

        mock_client_instance.is_authenticated.return_value = True
        mock_client_instance.secrets.kv.v2.read_secret_version.return_value = {
            "data": {
                "data": {
                    "key1": "value1",
                    "key2": "value2",
                }
            }
        }

        # Exécuter
        client = VaultClient()
        client.client = mock_client_instance
        secret = client.get_secret("saas-project/dev/database")

        # Vérifier
        assert secret == {"key1": "value1", "key2": "value2"}

    @patch("hvac.Client")
    def test_renew_token_success(self, mock_hvac_client, mock_env_vars):
        """Test le renouvellement du token."""
        # Setup
        mock_client_instance = MagicMock()
        mock_hvac_client.return_value = mock_client_instance

        mock_client_instance.auth.token.renew_self.return_value = {
            "auth": {
                "lease_duration": 3600,
            }
        }

        # Exécuter
        client = VaultClient()
        client.client = mock_client_instance
        client.token = "test-token"

        new_ttl = client.renew_token()

        # Vérifier
        assert new_ttl == 3600
        assert client.token_ttl == 3600
```

### 6.4 Tests d'Intégration avec Vault

**Fichier:** `backend/tests/integration/test_vault_integration.py`

```python
"""
Tests d'intégration avec Vault.
Nécessite un Vault en cours d'exécution.
"""

import os
import pytest
from app.utils.vault_client import VaultClient, VaultError


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("USE_VAULT") != "true",
    reason="Vault non activé"
)
class TestVaultIntegration:
    """Tests d'intégration avec Vault réel."""

    @pytest.fixture
    def vault_client(self):
        """Crée un client Vault authentifié."""
        client = VaultClient()
        client.authenticate()
        return client

    def test_authenticate_and_get_secrets(self, vault_client):
        """Test l'authentification et la récupération de secrets."""
        # Vérifier l'authentification
        assert vault_client.is_authenticated()
        assert vault_client.token is not None

        # Récupérer un secret
        secrets = vault_client.get_secret("saas-project/dev/database")

        assert "main_url" in secrets
        assert "tenant_url_template" in secrets

    def test_get_all_secrets(self, vault_client):
        """Test la récupération de tous les secrets."""
        secrets = vault_client.get_all_secrets(environment="dev")

        assert "database" in secrets
        assert "jwt" in secrets
        assert "s3" in secrets

    def test_renew_token(self, vault_client):
        """Test le renouvellement du token."""
        initial_ttl = vault_client.get_token_ttl()

        # Renouveler
        new_ttl = vault_client.renew_token()

        assert new_ttl > 0
        assert new_ttl >= initial_ttl  # Le TTL devrait être réinitialisé
```

### 6.5 Procédure de Test Complète

**Commandes pour tester l'intégration:**

```bash
# 1. Démarrer Vault seul
docker-compose up -d vault

# 2. Attendre que Vault soit prêt
sleep 5

# 3. Configurer Vault (politique + AppRole)
docker cp vault/policies/saas-app-policy.hcl saas-vault:/tmp/
docker exec -it saas-vault vault policy write saas-app-policy /tmp/saas-app-policy.hcl
docker exec -it saas-vault vault auth enable approle
docker exec -it saas-vault vault write auth/approle/role/saas-app-role \
  token_policies="saas-app-policy" \
  token_ttl=1h \
  token_max_ttl=4h

# 4. Récupérer Role ID et Secret ID
ROLE_ID=$(docker exec -it saas-vault vault read -field=role_id auth/approle/role/saas-app-role/role-id)
SECRET_ID=$(docker exec -it saas-vault vault write -field=secret_id -f auth/approle/role/saas-app-role/secret-id)

# 5. Créer .env.vault
cat > .env.vault <<EOF
VAULT_ADDR=http://vault:8200
VAULT_ROLE_ID=$ROLE_ID
VAULT_SECRET_ID=$SECRET_ID
EOF

# 6. Migrer les secrets (environnement docker par défaut)
./vault/scripts/migrate-secrets.sh docker

# OU pour migrer les autres environnements:
# ./vault/scripts/migrate-secrets.sh dev   # .env.development
# ./vault/scripts/migrate-secrets.sh prod  # .env.production

# 7. Démarrer l'application avec Vault activé
docker-compose up -d api worker

# 8. Vérifier les logs (vous devriez voir Gunicorn démarrer avec 4 workers)
docker-compose logs -f api
# Sortie attendue:
# - "Vault est accessible et initialisé"
# - "Exécution des migrations de base de données..."
# - "Authentification Vault réussie"
# - "Chargement de la configuration depuis Vault..."
# - "Listening at: http://0.0.0.0:4999" (Gunicorn)
# - "Using worker: sync" (Gunicorn)
# - "Booting worker with pid: ..." (4 workers)

# 9. Tester l'endpoint de health check
curl http://localhost:4999/api/health

# 10. Exécuter les tests
docker-compose exec api pytest tests/integration/test_vault_integration.py -v
```

**Note importante sur le flux de démarrage avec Gunicorn:**

1. **Entrypoint** (`docker-entrypoint.sh`) :
   - Vérifie que Vault est accessible
   - Exécute les migrations DB
   - Lance la commande : `exec gunicorn ...`

2. **Gunicorn démarre** et importe `run:app` :
   - Le code au niveau module de `run.py` s'exécute
   - `initialize_vault()` est appelé
   - `app = create_app(...)` crée l'instance Flask avec Vault
   - Le token renewer démarre dans chaque worker

3. **4 workers Gunicorn** sont créés :
   - Chaque worker a sa propre instance de l'app Flask
   - Chaque worker a son propre VaultClient et TokenRenewer
   - Les workers partagent les secrets chargés au démarrage

### 6.6 Procédure de Rollback

**En cas de problème, revenir à la configuration précédente:**

```bash
# 1. Arrêter tous les services
docker-compose down

# 2. Désactiver Vault dans docker-compose.yml
# Modifier les variables d'environnement:
# USE_VAULT: "false"

# 3. Restaurer les fichiers .env originaux
cp .env.backup .env.docker

# 4. Redémarrer sans Vault
docker-compose up -d api worker

# 5. Vérifier que l'application fonctionne
curl http://localhost:4999/api/health
```

---

## 7. Annexes

### 7.1 Commandes CLI Vault de Référence

**Commandes essentielles:**

```bash
# Statut de Vault
vault status

# Lister les secrets engines
vault secrets list

# Lister les méthodes d'authentification
vault auth list

# Lire un secret
vault kv get secret/saas-project/dev/database

# Écrire un secret
vault kv put secret/saas-project/dev/test key=value

# Supprimer un secret
vault kv delete secret/saas-project/dev/test

# Lister les versions d'un secret
vault kv metadata get secret/saas-project/dev/database

# Lire une politique
vault policy read saas-app-policy

# Lister les rôles AppRole
vault list auth/approle/role

# Vérifier un token
vault token lookup

# Renouveler un token
vault token renew

# Révoquer un token
vault token revoke <token>
```

### 7.2 Structure de Répertoires Complète

```
SaaSBackendWithClaude/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py  (MODIFIÉ)
│   │   ├── utils/
│   │   │   ├── vault_client.py  (NOUVEAU)
│   │   │   └── vault_token_renewer.py  (NOUVEAU)
│   │   └── ...
│   ├── scripts/
│   │   └── docker-entrypoint.sh  (NOUVEAU)
│   ├── run.py  (MODIFIÉ)
│   └── requirements.txt  (MODIFIÉ)
├── vault/
│   ├── config/  (NOUVEAU)
│   ├── data/  (NOUVEAU, git-ignored)
│   ├── logs/  (NOUVEAU, git-ignored)
│   ├── policies/  (NOUVEAU)
│   │   └── saas-app-policy.hcl
│   ├── scripts/  (NOUVEAU)
│   │   └── migrate-secrets.sh
│   └── .gitignore  (NOUVEAU)
├── docker/
│   ├── Dockerfile.api  (MODIFIÉ)
│   └── Dockerfile.worker  (MODIFIÉ)
├── docker-compose.yml  (MODIFIÉ)
├── .env.vault  (NOUVEAU, git-ignored)
└── ...
```

### 7.3 Variables d'Environnement Complètes

> **⚠️ IMPORTANT:** Avec l'auto-initialisation, les fichiers `.env.*` ne doivent **PLUS contenir de secrets**. Seulement des configurations non-sensibles.

#### 7.3.1 Fichier `.env.vault` (Auto-Généré)

**Ce fichier est généré automatiquement par `init-vault.sh` :**

```bash
# HashiCorp Vault Credentials
# Auto-généré par init-vault.sh le 2025-11-04
# Environnement: docker
#
# ⚠️  NE PAS COMMITER CE FICHIER
# ⚠️  Ces credentials donnent accès aux secrets Vault

VAULT_ADDR=http://vault:8200
VAULT_ROLE_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890
VAULT_SECRET_ID=f9e8d7c6-b5a4-3210-9876-543210fedcba
```

**⚠️ À AJOUTER dans `.gitignore` :**

```
.env.vault
```

#### 7.3.2 Fichier `.env.docker` (Sans Secrets)

**Ce fichier NE contient PLUS de secrets, seulement des configs non-sensibles :**

```bash
# ============================================================================
# Configuration NON-SENSIBLE pour Docker Compose
# ============================================================================
# ✅ Ce fichier peut être commité (aucun secret)
# ✅ Les secrets sont dans vault/init-data/docker.env (git-ignored)

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=false
FLASK_HOST=0.0.0.0
FLASK_PORT=4999

# Logging
LOG_LEVEL=DEBUG

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:4999

# Kafka Configuration (non sensible)
KAFKA_CONSUMER_GROUP_ID=saas-consumer-group
KAFKA_AUTO_OFFSET_RESET=earliest
KAFKA_ENABLE_AUTO_COMMIT=true
KAFKA_MAX_POLL_RECORDS=100

# Database Pool Configuration (non sensible)
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# ⚠️  AUCUN SECRET DANS CE FICHIER
# ⚠️  Tous les secrets sont dans vault/init-data/docker.env (git-ignored)
# ⚠️  et chargés automatiquement dans Vault au démarrage
```

#### 7.3.3 Fichier `vault/init-data/docker.env` (Secrets - Git-Ignored)

**Ce fichier contient TOUS les secrets et est git-ignored :**

```bash
# ============================================================================
# Secrets pour Environnement DOCKER (Docker Compose Local)
# ============================================================================
# ⚠️  NE PAS COMMITER CE FICHIER (dans .gitignore)
# ⚠️  Ces secrets seront injectés automatiquement dans Vault au démarrage

# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/saas_platform
TENANT_DATABASE_URL_TEMPLATE=postgresql://postgres:postgres@postgres:5432/{database_name}

# JWT - IMPORTANT: Générer une nouvelle clé sécurisée
# Générer avec: openssl rand -hex 32
JWT_SECRET_KEY=votre-cle-secrete-jwt-tres-longue-et-aleatoire
JWT_ACCESS_TOKEN_EXPIRES=900

# S3/MinIO
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents
S3_REGION=us-east-1
```

**⚠️ À AJOUTER dans `.gitignore` :**

```
vault/init-data/
```

**Variables à ajouter dans `docker-compose.yml`:**

```yaml
environment:
  # Vault
  USE_VAULT: "true"
  VAULT_ENVIRONMENT: "docker"  # Valeurs possibles: "dev", "docker", "prod"
  VAULT_ADDR: "http://vault:8200"
  # VAULT_ROLE_ID et VAULT_SECRET_ID chargés depuis .env.vault
```

**Correspondance des environnements:**
- `VAULT_ENVIRONMENT=dev` : Développement local (`.env.development`)
- `VAULT_ENVIRONMENT=docker` : Docker Compose local (`.env.docker`) - **recommandé**
- `VAULT_ENVIRONMENT=prod` : Production (`.env.production`)

### 7.4 Troubleshooting Guide

**Problème: "Vault is sealed"**

```bash
# Vérifier l'état
docker exec -it saas-vault vault status

# En mode dev, Vault ne devrait pas être sealed
# Si sealed, redémarrer le conteneur
docker-compose restart vault
```

**Problème: "Permission denied" lors de la lecture de secrets**

```bash
# Vérifier la politique
docker exec -it saas-vault vault policy read saas-app-policy

# Vérifier le token
docker exec -it saas-vault vault token lookup

# Tester l'accès avec le token
export VAULT_TOKEN="your-token"
docker exec -e VAULT_TOKEN=$VAULT_TOKEN -it saas-vault \
  vault kv get secret/saas-project/dev/database
```

**Problème: "Token expired"**

```bash
# Vérifier le TTL du token
docker exec -it saas-vault vault token lookup

# Se réauthentifier
ROLE_ID="your-role-id"
SECRET_ID="your-secret-id"
docker exec -it saas-vault vault write auth/approle/login \
  role_id=$ROLE_ID secret_id=$SECRET_ID
```

**Problème: L'application ne démarre pas**

```bash
# Vérifier les logs
docker-compose logs api

# Vérifier la connectivité à Vault
docker-compose exec api curl http://vault:8200/v1/sys/health

# Tester l'authentification manuellement
docker-compose exec api python -c "
from app.utils.vault_client import VaultClient
client = VaultClient()
client.authenticate()
print('Auth OK')
"
```

**Problème: Gunicorn démarre mais les workers crashent**

```bash
# Vérifier les logs détaillés
docker-compose logs api | grep -A 10 "worker"

# Symptômes courants:
# - "Worker timeout" : Vault prend trop de temps à répondre
# - "Worker failed to boot" : Erreur lors de l'import de run:app
# - Multiple workers démarrent/crashent en boucle

# Solutions:
# 1. Augmenter le timeout Gunicorn (dans Dockerfile.api)
CMD ["gunicorn", "--timeout", "300", ...]  # 5 minutes

# 2. Réduire le nombre de workers pendant le debug
CMD ["gunicorn", "-w", "1", ...]  # 1 worker pour isoler le problème

# 3. Vérifier que Vault est bien accessible AVANT le démarrage de Gunicorn
# Le entrypoint script doit attendre Vault correctement

# 4. Tester l'import manuel
docker-compose exec api python -c "from run import app; print('OK')"
```

**Problème: Les secrets ne sont pas chargés depuis Vault**

```bash
# Vérifier que USE_VAULT est activé
docker-compose exec api env | grep VAULT

# Vérifier l'ordre de chargement dans les logs
docker-compose logs api | grep -E "(Vault|Configuration|secrets)"

# Sortie attendue:
# - "Initialisation de Vault..."
# - "Authentification Vault réussie"
# - "Chargement de la configuration depuis Vault..."
# - "Configuration database chargée depuis Vault"
# - "Configuration JWT chargée depuis Vault"
# - "Configuration S3 chargée depuis Vault"

# Si les messages Vault n'apparaissent pas:
# 1. Vérifier que USE_VAULT=true dans docker-compose.yml
# 2. Vérifier que .env.vault contient VAULT_ROLE_ID et VAULT_SECRET_ID
# 3. Vérifier que l'ordre d'initialisation est correct dans run.py
```

### 7.5 Sécurité Best Practices

**Pour la Production:**

1. **Ne jamais utiliser le mode `-dev`**
   - Configurer Vault avec un backend de stockage persistent (Consul, S3, etc.)
   - Utiliser TLS pour toutes les communications
   - Implémenter un processus d'unsealing sécurisé

2. **Rotation des Secret IDs**
   ```bash
   # Configurer une durée de vie limitée
   vault write auth/approle/role/saas-app-role \
     secret_id_ttl=24h \
     secret_id_num_uses=1
   ```

3. **Politique de mot de passe fort**
   - Utiliser des secrets générés aléatoirement
   - Rotation régulière des credentials
   - Audit trail activé

4. **Monitoring et Alerting**
   - Surveiller les échecs d'authentification
   - Alerter sur les accès aux secrets sensibles
   - Logger tous les renouvellements de token

5. **Backup et Disaster Recovery**
   - Sauvegardes régulières du backend Vault
   - Documentation du processus de recovery
   - Tests réguliers de restauration

### 7.6 Transition vers Production

**Checklist pour passer en production:**

- [ ] Remplacer Vault en mode dev par un déploiement production
- [ ] Configurer un backend de stockage persistent (Consul, etcd, S3)
- [ ] Activer TLS/HTTPS pour toutes les communications
- [ ] Implémenter l'unsealing automatique (auto-unseal avec AWS KMS, GCP Cloud KMS, etc.)
- [ ] Configurer la rotation automatique des Secret IDs
- [ ] Mettre en place l'audit logging
- [ ] Configurer le monitoring (Prometheus, Grafana)
- [ ] Documenter le processus de disaster recovery
- [ ] Former l'équipe ops sur la gestion de Vault
- [ ] Effectuer un audit de sécurité complet

---

### 7.7 Gestion du Cycle de Vie des Secrets

Cette section détaille les opérations quotidiennes de gestion des secrets avec le système d'auto-initialisation.

#### 7.7.1 Workflow Quotidien (Démarrage Normal)

**Démarrage complet de l'environnement:**

```bash
# 1. Démarrer tous les services (y compris auto-init)
docker-compose up -d

# 2. Vérifier que l'initialisation s'est bien déroulée
docker-compose logs vault-init

# 3. Vérifier que .env.vault a été généré
ls -la .env.vault
cat .env.vault  # Doit contenir VAULT_ROLE_ID et VAULT_SECRET_ID

# 4. Vérifier que l'API a démarré correctement
docker-compose logs api | grep "Vault"
```

**Sortie attendue:**

```
vault-init_1  | ✅ KV Secrets Engine v2 activé
vault-init_1  | ✅ Secrets database injectés
vault-init_1  | ✅ Secrets JWT injectés
vault-init_1  | ✅ Secrets S3 injectés
vault-init_1  | ✅ AppRole 'saas-api-docker' créé
vault-init_1  | ✅ Fichier .env.vault généré avec succès
api_1         | INFO: Configuration complète chargée depuis Vault avec succès
```

**Workflow simplifié (après première initialisation):**

```bash
# Démarrage rapide - tout est automatique
docker-compose up -d

# L'ordre est géré par depends_on:
# 1. postgres, kafka, minio démarrent
# 2. vault démarre
# 3. vault-init injecte les secrets et génère .env.vault
# 4. api et worker démarrent avec les secrets de Vault
```

#### 7.7.2 Mise à Jour d'un Secret

**Scénario:** Rotation de la clé JWT

```bash
# 1. Générer une nouvelle clé
NEW_JWT_KEY=$(openssl rand -hex 32)

# 2. Mettre à jour le fichier de secrets
vim vault/init-data/docker.env

# Modifier la ligne:
# JWT_SECRET_KEY=ancienne-cle
# Par:
# JWT_SECRET_KEY=nouvelle-cle-generee

# 3. Redémarrer Vault et vault-init pour réinjecter
docker-compose restart vault
docker-compose up -d vault-init

# 4. Attendre la fin de l'initialisation
docker-compose logs -f vault-init

# 5. Redémarrer l'API pour charger le nouveau secret
docker-compose restart api

# 6. Vérifier que l'API utilise bien le nouveau secret
docker-compose logs api | grep "JWT"
```

**Alternative: Mise à jour manuelle via CLI Vault:**

```bash
# 1. Se connecter à Vault
export VAULT_ADDR="http://localhost:8201"
export VAULT_TOKEN="root-token-dev"

# 2. Mettre à jour un secret spécifique
vault kv put secret/saas-project/docker/jwt \
  secret_key="nouvelle-cle-jwt" \
  access_token_expires="900"

# 3. Redémarrer l'API (le token renewal rechargera les secrets)
docker-compose restart api
```

> **⚠️ IMPORTANT:** Pensez toujours à mettre à jour `vault/init-data/docker.env`
> pour que le secret soit persisté au prochain redémarrage de Vault.

#### 7.7.3 Rotation des Credentials AppRole

**Rotation du SECRET_ID (recommandé tous les 90 jours en production):**

```bash
# 1. Se connecter au conteneur vault-init
docker-compose run --rm vault-init sh

# 2. Générer un nouveau SECRET_ID
export VAULT_ADDR="http://vault:8200"
export VAULT_TOKEN="root-token-dev"
export VAULT_ENV="docker"

# 3. Créer un nouveau Secret ID
NEW_SECRET_ID=$(vault write -field=secret_id \
  auth/approle/role/saas-api-${VAULT_ENV}/secret-id)

echo "Nouveau SECRET_ID: $NEW_SECRET_ID"

# 4. Mettre à jour .env.vault
echo "VAULT_ADDR=http://vault:8200" > /output/.env.vault
echo "VAULT_ROLE_ID=$(vault read -field=role_id auth/approle/role/saas-api-${VAULT_ENV}/role-id)" >> /output/.env.vault
echo "VAULT_SECRET_ID=$NEW_SECRET_ID" >> /output/.env.vault
chmod 600 /output/.env.vault

# 5. Sortir du conteneur
exit

# 6. Redémarrer l'API
docker-compose restart api
```

**Rotation complète (Role ID + Secret ID):**

> **⚠️ ATTENTION:** Cette opération nécessite une interruption de service.

```bash
# 1. Supprimer l'ancien AppRole
docker-compose exec vault sh -c "
  export VAULT_ADDR='http://127.0.0.1:8200'
  export VAULT_TOKEN='root-token-dev'
  vault delete auth/approle/role/saas-api-docker
"

# 2. Relancer vault-init pour recréer le rôle
docker-compose up -d vault-init

# 3. Vérifier la génération du nouveau .env.vault
cat .env.vault

# 4. Redémarrer l'API
docker-compose restart api
```

#### 7.7.4 Gestion Multi-Environnements

**Configuration par environnement:**

```bash
# Développement local (.env.development)
VAULT_ENV=dev docker-compose up -d
# Utilise: vault/init-data/dev.env

# Docker local (.env.docker) - PAR DÉFAUT
docker-compose up -d
# Utilise: vault/init-data/docker.env

# Production (.env.production)
VAULT_ENV=prod docker-compose -f docker-compose.prod.yml up -d
# Utilise: vault/init-data/prod.env
```

**Structure des secrets par environnement:**

```
vault/init-data/
├── dev.env           # Secrets de développement (minioadmin, JWT faible)
├── docker.env        # Secrets Docker Compose local
└── prod.env          # Secrets de production (forte entropie, rotation fréquente)
```

**Bonnes pratiques:**

- **dev.env:** Secrets simples, partagés avec l'équipe, pas de données sensibles
- **docker.env:** Secrets locaux pour tests d'intégration, peuvent être partagés
- **prod.env:** **JAMAIS commité**, généré uniquement sur les serveurs de production

#### 7.7.5 Sauvegarde et Disaster Recovery

**Sauvegarde des secrets initiaux:**

```bash
# 1. Créer un backup chiffré des secrets
tar -czf vault-secrets-backup-$(date +%Y%m%d).tar.gz vault/init-data/

# 2. Chiffrer le backup (GPG)
gpg --symmetric --cipher-algo AES256 vault-secrets-backup-*.tar.gz

# 3. Stocker le fichier .gpg dans un emplacement sécurisé
# (Coffre-fort d'entreprise, gestionnaire de mots de passe, HSM)

# 4. Supprimer les fichiers non chiffrés
rm vault-secrets-backup-*.tar.gz
```

**Restauration après sinistre:**

```bash
# 1. Récupérer le backup chiffré
# 2. Déchiffrer
gpg --decrypt vault-secrets-backup-YYYYMMDD.tar.gz.gpg > vault-secrets-backup.tar.gz

# 3. Extraire
tar -xzf vault-secrets-backup.tar.gz

# 4. Redémarrer l'environnement
docker-compose down -v  # ⚠️ Supprime TOUS les volumes
docker-compose up -d

# 5. Vérifier que les secrets ont été réinjectés
docker-compose logs vault-init
```

#### 7.7.6 Monitoring et Alertes

**Vérifications à automatiser:**

```bash
#!/bin/bash
# vault-health-check.sh

# 1. Vérifier que Vault répond
curl -sf http://localhost:8201/v1/sys/health || echo "❌ Vault ne répond pas"

# 2. Vérifier que l'API peut s'authentifier
docker-compose exec api python -c "
from app.utils.vault_client import VaultClient
try:
    vc = VaultClient()
    vc.authenticate()
    print('✅ API authentifiée sur Vault')
except Exception as e:
    print(f'❌ Erreur authentification: {e}')
    exit(1)
"

# 3. Vérifier que .env.vault existe et est valide
if [ ! -f .env.vault ]; then
    echo "❌ .env.vault manquant"
    exit 1
fi

if ! grep -q "VAULT_ROLE_ID" .env.vault; then
    echo "❌ .env.vault invalide"
    exit 1
fi

echo "✅ Tous les checks Vault OK"
```

**Alertes critiques à configurer:**

- ⚠️ Vault inaccessible (downtime)
- ⚠️ Échec d'authentification AppRole
- ⚠️ Token expiré et non renouvelé
- ⚠️ Espace disque faible (en production avec storage persistant)
- ⚠️ Secret ID proche de l'expiration (en production)

#### 7.7.7 Bonnes Pratiques de Sécurité

**DO ✅**

- Toujours utiliser `vault/init-data/` pour les secrets (git-ignored)
- Générer les secrets avec forte entropie (`openssl rand -hex 32`)
- Sauvegarder `vault/init-data/prod.env` de manière chiffrée hors du repo
- Tester la rotation des secrets en environnement de staging
- Documenter toute modification de secret dans un changelog sécurisé
- Utiliser des secrets différents entre dev/docker/prod
- Limiter l'accès au serveur de production (principe du moindre privilège)

**DON'T ❌**

- Ne JAMAIS commiter `vault/init-data/` dans Git
- Ne JAMAIS commiter `.env.vault` dans Git
- Ne JAMAIS utiliser les mêmes secrets entre dev et prod
- Ne JAMAIS partager le VAULT_TOKEN root en production
- Ne JAMAIS afficher les secrets dans les logs
- Ne JAMAIS stocker des secrets en clair dans des fichiers non protégés
- Ne JAMAIS utiliser le mode dev de Vault en production

**Checklist avant commit:**

```bash
# Vérifier qu'aucun secret n'est commité
git status
git diff

# Vérifier .gitignore
grep -E "(init-data|.env.vault)" .gitignore

# Scanner les secrets potentiels
git secrets --scan  # Installer avec: brew install git-secrets
```

---

## Conclusion

Ce plan d'intégration détaille toutes les étapes nécessaires pour migrer votre SaaS Platform vers une gestion de secrets sécurisée avec HashiCorp Vault. L'implémentation suit les best practices de sécurité avec :

- ✅ Authentification AppRole pour les applications
- ✅ Politiques ACL restrictives (read-only)
- ✅ Renouvellement automatique des tokens
- ✅ Architecture résiliente avec fallback
- ✅ Auto-initialisation complète des secrets
- ✅ Vault comme source unique de vérité (Single Source of Truth)
- ✅ Audit trail complet
- ✅ Tests unitaires et d'intégration

---

## Annexe A - Workflow Final Complet

### A.1 Premier Démarrage (Setup Initial)

**Étape 1: Préparation des secrets initiaux**

```bash
# 1. Créer la structure
mkdir -p vault/init-data vault/scripts

# 2. Créer le fichier de secrets pour l'environnement docker
cat > vault/init-data/docker.env << 'EOF'
# Database Configuration
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/saas_platform
TENANT_DATABASE_URL_TEMPLATE=postgresql://postgres:postgres@postgres:5432/{database_name}

# JWT Configuration (générer avec: openssl rand -hex 32)
JWT_SECRET_KEY=votre-cle-jwt-generee-avec-openssl-rand-hex-32
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=604800

# S3/MinIO Configuration
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET_NAME=saas-documents
S3_REGION=us-east-1

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
EOF

# 3. Sécuriser les permissions
chmod 600 vault/init-data/docker.env

# 4. Créer le script d'initialisation (voir section 2.6.2)
# Copier le contenu de init-vault.sh dans vault/scripts/init-vault.sh
chmod +x vault/scripts/init-vault.sh
```

**Étape 2: Mettre à jour .gitignore**

```bash
# Ajouter à .gitignore
cat >> .gitignore << 'EOF'

# HashiCorp Vault
vault/data/
vault/logs/
vault/init-data/
.env.vault
EOF
```

**Étape 3: Mettre à jour docker-compose.yml**

Ajouter les services `vault` et `vault-init` comme décrit dans la section 2.6.

**Étape 4: Premier lancement**

```bash
# 1. Démarrer l'infrastructure
docker-compose up -d

# 2. Vérifier les logs d'initialisation
docker-compose logs -f vault-init

# Sortie attendue:
# ✅ KV Secrets Engine v2 activé
# ✅ Secrets database injectés
# ✅ Secrets JWT injectés
# ✅ Secrets S3 injectés
# ✅ AppRole 'saas-api-docker' créé
# ✅ Policy 'saas-api-docker-policy' créée
# ✅ Fichier .env.vault généré avec succès

# 3. Vérifier .env.vault
cat .env.vault
# VAULT_ADDR=http://vault:8200
# VAULT_ROLE_ID=abcd1234-...
# VAULT_SECRET_ID=xyz9876-...

# 4. Vérifier que l'API a chargé les secrets
docker-compose logs api | grep "Vault"
# INFO: Configuration complète chargée depuis Vault avec succès
```

**Étape 5: Vérification complète**

```bash
# 1. Tester l'API
curl http://localhost:4999/health
# {"status": "healthy"}

# 2. Vérifier que les secrets sont bien dans Vault
docker-compose exec vault sh -c "
  export VAULT_ADDR='http://127.0.0.1:8200'
  export VAULT_TOKEN='root-token-dev'
  vault kv get secret/saas-project/docker/database
"

# 3. Tester l'authentification avec AppRole
docker-compose exec api python -c "
from app.utils.vault_client import VaultClient
vc = VaultClient()
token = vc.authenticate()
print(f'✅ Token obtenu: {token[:20]}...')
secrets = vc.get_all_secrets('docker')
print(f'✅ {len(secrets)} groupes de secrets récupérés')
"
```

### A.2 Utilisation Quotidienne

**Démarrage normal:**

```bash
# Démarrer tous les services
docker-compose up -d

# C'est tout ! L'auto-initialisation se fait automatiquement:
# 1. vault démarre
# 2. vault-init injecte les secrets et génère .env.vault
# 3. api et worker se connectent à Vault
```

**Arrêt:**

```bash
# Arrêt propre
docker-compose down

# Arrêt avec suppression des volumes (⚠️ perte de données)
docker-compose down -v
```

**Logs et debugging:**

```bash
# Logs de tous les services
docker-compose logs -f

# Logs spécifiques
docker-compose logs -f vault
docker-compose logs -f vault-init
docker-compose logs -f api

# Vérifier la santé de Vault
curl http://localhost:8201/v1/sys/health | jq
```

### A.3 Scénarios Courants

**Scénario 1: Ajouter un nouveau secret**

```bash
# 1. Éditer le fichier de secrets
vim vault/init-data/docker.env

# Ajouter:
# NEW_API_KEY=your-new-api-key-here

# 2. Redémarrer vault et vault-init
docker-compose restart vault
docker-compose up -d vault-init

# 3. Mettre à jour le code pour lire le nouveau secret
# Dans app/config.py:
#   NEW_API_KEY = os.environ.get("NEW_API_KEY")
# Dans app/config.py load_from_vault():
#   if "new_service" in secrets:
#       cls.NEW_API_KEY = secrets["new_service"].get("api_key")

# 4. Mettre à jour vault/scripts/init-vault.sh pour injecter le secret
# Ajouter dans la section appropriée:
#   vault kv put secret/saas-project/${VAULT_ENV}/new_service \
#     api_key="${NEW_API_KEY}"

# 5. Relancer l'initialisation
docker-compose restart vault
docker-compose up -d vault-init

# 6. Redémarrer l'API
docker-compose restart api
```

**Scénario 2: Changer d'environnement**

```bash
# Passer en environnement de développement
export VAULT_ENV=dev
docker-compose down
docker-compose up -d
# Utilisera vault/init-data/dev.env

# Passer en environnement de production
export VAULT_ENV=prod
docker-compose -f docker-compose.prod.yml up -d
# Utilisera vault/init-data/prod.env
```

**Scénario 3: Régénérer complètement .env.vault**

```bash
# 1. Supprimer l'ancien fichier
rm .env.vault

# 2. Relancer vault-init
docker-compose up -d vault-init

# 3. Vérifier le nouveau fichier
cat .env.vault

# 4. Redémarrer l'API
docker-compose restart api
```

**Scénario 4: Disaster Recovery**

```bash
# 1. Restaurer les secrets depuis backup
# (Voir section 7.7.5 - Sauvegarde et Disaster Recovery)

# 2. Redémarrer complètement l'infrastructure
docker-compose down -v
docker-compose up -d

# 3. Vérifier que tout fonctionne
docker-compose logs vault-init
docker-compose logs api | grep "Vault"
curl http://localhost:4999/health
```

### A.4 Troubleshooting Rapide

| Problème | Solution |
|----------|----------|
| `.env.vault` n'est pas généré | Vérifier `docker-compose logs vault-init`, vérifier que `vault/init-data/docker.env` existe |
| API ne peut pas s'authentifier | Vérifier que `.env.vault` existe et contient `VAULT_ROLE_ID` et `VAULT_SECRET_ID` |
| Secrets non chargés | Vérifier `docker-compose logs api`, vérifier `VAULT_ENVIRONMENT=docker` dans docker-compose.yml |
| Vault ne démarre pas | Vérifier `docker-compose logs vault`, vérifier que le port 8201 n'est pas déjà utilisé (8200 souvent occupé par OneDrive sur macOS) |
| Token expiré | Vérifier le token renewal dans les logs, redémarrer l'API |

### A.5 Checklist de Production

Avant de déployer en production, vérifier:

- [ ] `vault/init-data/prod.env` contient des secrets forts (générés avec `openssl rand -hex 32`)
- [ ] `vault/init-data/prod.env` est sauvegardé de manière chiffrée (GPG) hors du repo
- [ ] `.env.vault` est dans `.gitignore`
- [ ] `vault/init-data/` est dans `.gitignore`
- [ ] Les secrets de production sont DIFFÉRENTS de dev et docker
- [ ] Le mode dev de Vault est remplacé par un déploiement production (avec storage persistent)
- [ ] TLS/HTTPS est activé pour Vault
- [ ] L'audit logging est configuré
- [ ] Le monitoring est en place (healthchecks, alertes)
- [ ] La rotation des SECRET_ID est planifiée (tous les 90 jours)
- [ ] L'équipe connaît le processus de disaster recovery
- [ ] Un audit de sécurité a été réalisé

---

**Prochaines étapes recommandées:**

1. ✅ **Phase 1 (Préparation):** Créer `vault/init-data/docker.env` et le script d'init
2. ✅ **Phase 2 (Configuration Docker):** Ajouter les services `vault` et `vault-init`
3. ✅ **Phase 3 (Code Application):** Implémenter `VaultClient` et `Config.load_from_vault()`
4. ✅ **Phase 4 (Token Renewal):** Ajouter le background worker pour le renouvellement
5. ✅ **Phase 5 (Tests):** Tester l'ensemble du workflow
6. 🔄 **Phase 6 (Production):** Suivre la checklist de production ci-dessus

**Ressources supplémentaires:**

- Documentation Vault: https://www.vaultproject.io/docs
- Bibliothèque hvac: https://hvac.readthedocs.io/
- Best Practices: https://www.vaultproject.io/docs/internals/security
- AppRole Auth Method: https://www.vaultproject.io/docs/auth/approle

**Support:**

Pour toute question ou assistance, référez-vous à la documentation officielle de HashiCorp Vault ou contactez l'équipe DevSecOps.

---

**Fin du document - Version 2.0 avec Auto-Initialisation**

*Dernière mise à jour: Intégration complète du système d'auto-initialisation Vault avec support multi-environnements (dev/docker/prod)*
