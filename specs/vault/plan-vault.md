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

```yaml
services:
  # ... services existants ...

  vault:
    image: hashicorp/vault:1.15
    container_name: saas-vault
    ports:
      - "8200:8200"
    environment:
      VAULT_DEV_ROOT_TOKEN_ID: "root-token-dev"
      VAULT_DEV_LISTEN_ADDRESS: "0.0.0.0:8200"
      VAULT_ADDR: "http://0.0.0.0:8200"
    cap_add:
      - IPC_LOCK
    networks:
      - saas-network
    healthcheck:
      test: ["CMD", "vault", "status"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    volumes:
      - ./vault/config:/vault/config
      - ./vault/data:/vault/data
      - ./vault/logs:/vault/logs
    command: server -dev -dev-root-token-id="root-token-dev"
```

**Notes importantes:**
- **Mode Développement:** Le flag `-dev` lance Vault en mode développement (non-sécurisé, pas de persistence)
- **Token Root:** `root-token-dev` est utilisé pour l'initialisation (à changer en production)
- **Port 8200:** Port standard de l'API Vault
- **IPC_LOCK:** Capability nécessaire pour éviter le swap de la mémoire Vault
- **Health Check:** Permet aux autres services de démarrer après Vault

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
# Vault data (contient les secrets)
data/
logs/

# Tokens et credentials
.vault-token
*.token

# Configuration locale
config/local.hcl
```

---

## 3. Phase 2 - Configuration de Vault

### 3.1 Initialisation de Vault (Mode Dev)

**En mode développement**, Vault est déjà initialisé avec le token root. Pour vérifier:

```bash
# Démarrer les services
docker-compose up -d vault

# Vérifier le statut
docker exec -it saas-vault vault status

# Exporter les variables pour les commandes suivantes
export VAULT_ADDR='http://localhost:8200'
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

### 3.2 Activation du KV Secrets Engine v2

Le **Key-Value Secrets Engine v2** permet le versioning des secrets.

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

### 3.3 Création de la Structure de Chemins de Secrets

**Structure hiérarchique proposée:**

```
secret/
└── data/
    └── saas-project/
        ├── dev/
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
        └── prod/
            ├── database/
            ├── jwt/
            └── s3/
```

**Commandes pour créer les secrets (environnement dev):**

```bash
# Secrets de base de données
docker exec -it saas-vault vault kv put secret/saas-project/dev/database \
  main_url="postgresql://postgres:postgres@postgres:5432/saas_platform" \
  tenant_url_template="postgresql://postgres:postgres@postgres:5432/{database_name}"

# Secrets JWT
docker exec -it saas-vault vault kv put secret/saas-project/dev/jwt \
  secret_key="super-secret-jwt-key-change-in-production" \
  access_token_expires="900"

# Secrets S3/MinIO
docker exec -it saas-vault vault kv put secret/saas-project/dev/s3 \
  endpoint_url="http://minio:9000" \
  access_key_id="minioadmin" \
  secret_access_key="minioadmin" \
  bucket_name="saas-documents" \
  region="us-east-1"

# Vérifier la création
docker exec -it saas-vault vault kv get secret/saas-project/dev/database
```

### 3.4 Création de la Politique d'Accès (ACL Policy)

**Fichier:** `vault/policies/saas-app-policy.hcl`

```hcl
# Politique pour l'application SaaS Flask
# Permet uniquement la lecture des secrets dev

# Accès aux secrets de base de données
path "secret/data/saas-project/dev/database" {
  capabilities = ["read"]
}

# Accès aux secrets JWT
path "secret/data/saas-project/dev/jwt" {
  capabilities = ["read"]
}

# Accès aux secrets S3
path "secret/data/saas-project/dev/s3" {
  capabilities = ["read"]
}

# Accès aux métadonnées (pour lister les versions)
path "secret/metadata/saas-project/dev/*" {
  capabilities = ["list", "read"]
}

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

### 3.5 Configuration de l'Authentification AppRole

**Étape 1: Activer la méthode d'authentification AppRole**

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

```python
"""
Point d'entrée de l'application Flask.
Gère l'initialisation de Vault et le démarrage du serveur.
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


def main():
    """Point d'entrée principal de l'application."""

    # 1. Initialiser Vault (si activé)
    vault_client = initialize_vault()

    # 2. Créer l'application Flask
    config_name = os.environ.get("FLASK_ENV", "development")
    app = create_app(config_name, vault_client=vault_client)

    # 3. Démarrer le serveur
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

**Ajouter l'entrypoint et les variables d'environnement:**

```dockerfile
# ... contenu existant ...

# Copier le script d'entrypoint
COPY backend/scripts/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Définir l'entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Commande par défaut
CMD ["python", "run.py"]
```

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
      VAULT_ENVIRONMENT: "dev"
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
      VAULT_ENVIRONMENT: "dev"
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

### 6.2 Script de Migration des Secrets

**Fichier:** `vault/scripts/migrate-secrets.sh`

```bash
#!/bin/bash

# Script de migration des secrets depuis .env vers Vault
# Usage: ./migrate-secrets.sh <environment>

set -e

ENVIRONMENT=${1:-dev}
ENV_FILE=".env.${ENVIRONMENT}"

if [ ! -f "$ENV_FILE" ]; then
    echo "Erreur: Fichier $ENV_FILE introuvable"
    exit 1
fi

echo "Migration des secrets depuis $ENV_FILE vers Vault (environnement: $ENVIRONMENT)"

# Charger les variables d'environnement
source "$ENV_FILE"

export VAULT_ADDR='http://localhost:8200'
export VAULT_TOKEN='root-token-dev'

# Fonction pour échapper les valeurs contenant des espaces ou caractères spéciaux
escape_value() {
    echo "$1" | sed 's/"/\\"/g'
}

# Migration des secrets de base de données
echo "Migration des secrets database..."
docker exec -e VAULT_TOKEN=$VAULT_TOKEN -it saas-vault vault kv put "secret/saas-project/${ENVIRONMENT}/database" \
  "main_url=$(escape_value "$DATABASE_URL")" \
  "tenant_url_template=$(escape_value "$TENANT_DATABASE_URL_TEMPLATE")"

# Migration des secrets JWT
echo "Migration des secrets JWT..."
docker exec -e VAULT_TOKEN=$VAULT_TOKEN -it saas-vault vault kv put "secret/saas-project/${ENVIRONMENT}/jwt" \
  "secret_key=$(escape_value "$JWT_SECRET_KEY")" \
  "access_token_expires=$(escape_value "${JWT_ACCESS_TOKEN_EXPIRES:-900}")"

# Migration des secrets S3
echo "Migration des secrets S3..."
docker exec -e VAULT_TOKEN=$VAULT_TOKEN -it saas-vault vault kv put "secret/saas-project/${ENVIRONMENT}/s3" \
  "endpoint_url=$(escape_value "$S3_ENDPOINT_URL")" \
  "access_key_id=$(escape_value "$S3_ACCESS_KEY_ID")" \
  "secret_access_key=$(escape_value "$S3_SECRET_ACCESS_KEY")" \
  "bucket_name=$(escape_value "$S3_BUCKET_NAME")" \
  "region=$(escape_value "$S3_REGION")"

echo "Migration terminée avec succès!"
echo ""
echo "Vérification des secrets migrés:"
docker exec -e VAULT_TOKEN=$VAULT_TOKEN -it saas-vault vault kv get "secret/saas-project/${ENVIRONMENT}/database"
docker exec -e VAULT_TOKEN=$VAULT_TOKEN -it saas-vault vault kv get "secret/saas-project/${ENVIRONMENT}/jwt"
docker exec -e VAULT_TOKEN=$VAULT_TOKEN -it saas-vault vault kv get "secret/saas-project/${ENVIRONMENT}/s3"
```

**Rendre le script exécutable:**

```bash
chmod +x vault/scripts/migrate-secrets.sh
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

# 6. Migrer les secrets
./vault/scripts/migrate-secrets.sh dev

# 7. Démarrer l'application avec Vault activé
docker-compose up -d api worker

# 8. Vérifier les logs
docker-compose logs -f api

# 9. Tester l'endpoint de health check
curl http://localhost:4999/api/health

# 10. Exécuter les tests
docker-compose exec api pytest tests/integration/test_vault_integration.py -v
```

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

**Fichier `.env.vault` (à ne pas commiter):**

```bash
# HashiCorp Vault Configuration
VAULT_ADDR=http://vault:8200
VAULT_ROLE_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890
VAULT_SECRET_ID=f9e8d7c6-b5a4-3210-9876-543210fedcba
```

**Variables à ajouter dans `docker-compose.yml`:**

```yaml
environment:
  # Vault
  USE_VAULT: "true"
  VAULT_ENVIRONMENT: "dev"  # ou "prod"
  VAULT_ADDR: "http://vault:8200"
  # VAULT_ROLE_ID et VAULT_SECRET_ID chargés depuis .env.vault
```

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

## Conclusion

Ce plan d'intégration détaille toutes les étapes nécessaires pour migrer votre SaaS Platform vers une gestion de secrets sécurisée avec HashiCorp Vault. L'implémentation suit les best practices de sécurité avec :

- ✅ Authentification AppRole pour les applications
- ✅ Politiques ACL restrictives (read-only)
- ✅ Renouvellement automatique des tokens
- ✅ Architecture résiliente avec fallback
- ✅ Audit trail complet
- ✅ Tests unitaires et d'intégration

**Prochaines étapes:**

1. Exécuter Phase 1 (Préparation)
2. Exécuter Phase 2 (Configuration Vault)
3. Exécuter Phase 3 (Code Application)
4. Exécuter Phase 4 (Token Renewal)
5. Exécuter Phase 5 (Migration et Tests)

**Ressources supplémentaires:**

- Documentation Vault: https://www.vaultproject.io/docs
- Bibliothèque hvac: https://hvac.readthedocs.io/
- Best Practices: https://www.vaultproject.io/docs/internals/security

**Support:**

Pour toute question ou assistance, référez-vous à la documentation officielle de HashiCorp Vault ou contactez l'équipe DevSecOps.

---

**Fin du document**
