# Plan d'activation du chiffrement Vault Transit pour les tokens SSO

## Vue d'ensemble

Ce document décrit les étapes nécessaires pour activer le chiffrement des tokens Azure AD (access_token, refresh_token, id_token) stockés en base de données via HashiCorp Vault Transit Engine.

### Situation actuelle

**Ce qui existe déjà :**
- ✅ `VaultEncryptionService` complètement implémenté ([backend/app/services/vault_encryption_service.py](backend/app/services/vault_encryption_service.py))
  - Méthodes `encrypt_token()` / `decrypt_token()`
  - Méthode `ensure_encryption_key()` - création de clés par tenant
  - Méthodes `rotate_encryption_key()` / `rewrap_tokens()` - rotation de clés
  - Isolation complète par tenant (clé nommée `azure-tokens-{tenant_id}`)

**Ce qui manque :**
- ❌ `UserAzureIdentity.save_tokens()` et `get_decrypted_tokens()` n'utilisent PAS le service de chiffrement
  - Stockage actuel avec préfixe "dev:" (mode développement)
  - Warning explicite : "Implement VaultEncryptionService for production use"
- ❌ Pas de variable d'environnement pour activer/désactiver cette fonctionnalité
- ❌ La clé de chiffrement Vault n'est pas créée automatiquement lors de la configuration SSO
- ❌ Pas de script de migration pour les tokens existants

### Approche d'activation du chiffrement

Le chiffrement Vault sera activé selon **deux méthodes combinées** :

```python
# Le chiffrement est activé si :
# 1. USE_VAULT_TOKEN_ENCRYPTION=true (activation explicite)
# OU
# 2. FLASK_ENV=production (activation automatique pour la sécurité)
use_vault_encryption = (
    current_app.config.get('USE_VAULT_TOKEN_ENCRYPTION', False) or
    current_app.config.get('FLASK_ENV') == 'production'
)
```

**Avantages de cette approche :**
- ✅ **Sécurité par défaut** : tout environnement en production utilisera automatiquement Vault
- ✅ **Flexibilité en développement** : possibilité de tester le chiffrement avec `USE_VAULT_TOKEN_ENCRYPTION=true`
- ✅ **Override possible** : peut être désactivé explicitement en prod avec `USE_VAULT_TOKEN_ENCRYPTION=false` (non recommandé)
- ✅ **Conforme à l'intention du code** : répond au warning "for production use"

---

## Matrice de décision du chiffrement

| FLASK_ENV | USE_VAULT_TOKEN_ENCRYPTION | Chiffrement actif ? | Format tokens | Cas d'usage |
|-----------|---------------------------|---------------------|---------------|-------------|
| development | (non défini/false) | ❌ Non | `dev:...` | Développement normal |
| development | true | ✅ Oui | `vault:v1:...` | Test du chiffrement en dev |
| production | (non défini) | ✅ Oui | `vault:v1:...` | **Production (recommandé)** |
| production | true | ✅ Oui | `vault:v1:...` | Production (redondant) |
| production | false | ❌ Non | `dev:...` | Production sans chiffrement ⚠️ |

---

## Plan d'implémentation

### 1. Configuration (backend/app/config.py)

**Objectif :** Ajouter une variable d'environnement optionnelle pour contrôler l'activation du chiffrement.

**Modifications :**

```python
# Dans la classe Config
USE_VAULT_TOKEN_ENCRYPTION = os.environ.get('USE_VAULT_TOKEN_ENCRYPTION', 'false').lower() == 'true'
```

**Note importante :** Cette variable est **optionnelle**. En `FLASK_ENV=production`, le chiffrement est activé automatiquement même si cette variable n'est pas définie.

**Fichiers à modifier :**
- [backend/app/config.py](backend/app/config.py) - ajouter la variable dans la classe `Config`
- `.env.docker.minimal` - ajouter la documentation de la variable (optionnelle)
- `.env.docker` - ajouter la variable avec valeur par défaut

**Exemple dans .env :**
```bash
# ============================================================================
# Vault Transit Engine Configuration (OPTIONAL)
# ============================================================================
# Enable encryption of SSO tokens using Vault Transit Engine
#
# - If FLASK_ENV=production: encryption is ENABLED by default (secure by default)
# - If FLASK_ENV=development: encryption is DISABLED by default
# - Set to 'true' to force enable in development (for testing Vault)
# - Set to 'false' to force disable in production (NOT RECOMMENDED)
#
# Default behavior:
#   - production: tokens encrypted with Vault (vault:v1:...)
#   - development: tokens stored with 'dev:' prefix
USE_VAULT_TOKEN_ENCRYPTION=false
```

---

### 2. Intégration dans UserAzureIdentity (backend/app/models/user_azure_identity.py)

#### 2.1 Modifier `save_tokens()` (lignes 190-237)

**Objectif :** Utiliser VaultEncryptionService pour chiffrer les tokens selon la logique combinée.

**Logique :**
1. Vérifier si chiffrement activé via la condition combinée :
   - `USE_VAULT_TOKEN_ENCRYPTION=true` (explicite) **OU**
   - `FLASK_ENV=production` (automatique)
2. Si activé :
   - Importer `VaultEncryptionService`
   - Initialiser le service (gérer les erreurs d'initialisation)
   - Appeler `ensure_encryption_key(tenant_id)` pour créer la clé si nécessaire
   - Chiffrer chaque token avec `encrypt_token(tenant_id, token)`
   - Stocker les tokens chiffrés (format `vault:v1:...`)
3. Si NON ou en cas d'erreur Vault :
   - Conserver le mode actuel avec préfixe "dev:"
   - Logger un warning approprié

**Code complet :**
```python
def save_tokens(self, access_token, refresh_token, id_token, expires_in, refresh_expires_in=None):
    """
    Save OAuth2 tokens securely using encryption.

    Tokens are encrypted with Vault Transit Engine if:
    - USE_VAULT_TOKEN_ENCRYPTION=true (explicit activation)
    - OR FLASK_ENV=production (automatic activation for security)

    Args:
        access_token: Azure AD access token
        refresh_token: Azure AD refresh token
        id_token: Azure AD ID token
        expires_in: Access token lifetime in seconds
        refresh_expires_in: Refresh token lifetime in seconds (optional)
    """
    try:
        # Chiffrement activé si :
        # 1. USE_VAULT_TOKEN_ENCRYPTION=true (explicite)
        # 2. OU FLASK_ENV=production (automatique pour sécurité)
        use_vault = (
            current_app.config.get('USE_VAULT_TOKEN_ENCRYPTION', False) or
            current_app.config.get('FLASK_ENV') == 'production'
        )

        if use_vault:
            try:
                from app.services.vault_encryption_service import VaultEncryptionService
                vault_service = VaultEncryptionService()

                # Créer la clé de chiffrement si nécessaire
                vault_service.ensure_encryption_key(str(self.tenant_id))

                # Chiffrer les tokens
                self.encrypted_access_token = vault_service.encrypt_token(
                    str(self.tenant_id), access_token
                )
                self.encrypted_refresh_token = vault_service.encrypt_token(
                    str(self.tenant_id), refresh_token
                )
                self.encrypted_id_token = vault_service.encrypt_token(
                    str(self.tenant_id), id_token
                )

                # Log détaillé sur la raison de l'activation
                if current_app.config.get('USE_VAULT_TOKEN_ENCRYPTION'):
                    logger.info(
                        f"Tokens encrypted with Vault (explicit USE_VAULT_TOKEN_ENCRYPTION=true) "
                        f"for user {self.user_id} on tenant {self.tenant_id}"
                    )
                else:
                    logger.info(
                        f"Tokens encrypted with Vault (automatic in production mode) "
                        f"for user {self.user_id} on tenant {self.tenant_id}"
                    )

            except Exception as e:
                logger.error(f"Vault encryption failed, falling back to dev mode: {str(e)}")
                # Fallback vers le mode dev:
                self.encrypted_access_token = f"dev:{access_token}"
                self.encrypted_refresh_token = f"dev:{refresh_token}"
                self.encrypted_id_token = f"dev:{id_token}"
        else:
            # Mode développement (pas de Vault)
            env = current_app.config.get('FLASK_ENV', 'unknown')
            logger.info(
                f"Tokens stored in dev mode (FLASK_ENV={env}, "
                f"USE_VAULT_TOKEN_ENCRYPTION not enabled) for user {self.user_id}"
            )
            self.encrypted_access_token = f"dev:{access_token}"
            self.encrypted_refresh_token = f"dev:{refresh_token}"
            self.encrypted_id_token = f"dev:{id_token}"

        # Calculer les expirations
        now = datetime.utcnow()
        self.token_expires_at = now + timedelta(seconds=expires_in)

        if refresh_expires_in:
            self.refresh_token_expires_at = now + timedelta(seconds=refresh_expires_in)
        else:
            # Default refresh token expiration (7 days)
            self.refresh_token_expires_at = now + timedelta(days=7)

        self.last_sync = now

        logger.info(
            f"Tokens saved for user {self.user_id} on tenant {self.tenant_id}. "
            f"Access token expires at {self.token_expires_at}"
        )

    except Exception as e:
        logger.error(f"Error saving tokens: {str(e)}", exc_info=True)
        raise
```

#### 2.2 Modifier `get_decrypted_tokens()` (lignes 239-271)

**Objectif :** Détecter automatiquement le format du token et utiliser la bonne méthode de déchiffrement.

**Logique :**
1. Pour chaque token chiffré, détecter son format :
   - Si commence par `vault:v1:` → utiliser `VaultEncryptionService.decrypt_token()`
   - Si commence par `dev:` → utiliser le déchiffrement simple (retirer le préfixe)
   - Sinon → retourner None
2. Gérer les erreurs de déchiffrement Vault gracieusement

**Code complet :**
```python
def get_decrypted_tokens(self) -> Dict[str, Optional[str]]:
    """
    Get decrypted OAuth2 tokens.

    Automatically detects token format and uses appropriate decryption:
    - vault:v1:... → VaultEncryptionService (if enabled)
    - dev:... → simple prefix removal

    Returns:
        Dictionary with decrypted tokens (access_token, refresh_token, id_token)
    """
    try:
        tokens = {
            'access_token': None,
            'refresh_token': None,
            'id_token': None
        }

        # Initialiser le service Vault seulement si nécessaire
        vault_service = None

        # Utiliser la même logique combinée que save_tokens()
        use_vault = (
            current_app.config.get('USE_VAULT_TOKEN_ENCRYPTION', False) or
            current_app.config.get('FLASK_ENV') == 'production'
        )

        # Fonction helper pour déchiffrer un token
        def decrypt_token(encrypted_token):
            if not encrypted_token:
                return None

            # Détection automatique du format
            if encrypted_token.startswith('vault:v'):
                # Format Vault - nécessite VaultEncryptionService
                if use_vault:
                    nonlocal vault_service
                    if vault_service is None:
                        from app.services.vault_encryption_service import VaultEncryptionService
                        vault_service = VaultEncryptionService()

                    try:
                        return vault_service.decrypt_token(
                            str(self.tenant_id), encrypted_token
                        )
                    except Exception as e:
                        logger.error(
                            f"Vault decryption failed for tenant {self.tenant_id}: {str(e)}"
                        )
                        return None
                else:
                    logger.warning(
                        f"Vault token found but encryption is disabled "
                        f"(FLASK_ENV={current_app.config.get('FLASK_ENV')}, "
                        f"USE_VAULT_TOKEN_ENCRYPTION={current_app.config.get('USE_VAULT_TOKEN_ENCRYPTION')})"
                    )
                    return None

            elif encrypted_token.startswith('dev:'):
                # Format dev - simple déchiffrement
                return encrypted_token[4:]

            else:
                # Format inconnu
                logger.warning(
                    f"Unknown token format for tenant {self.tenant_id}: "
                    f"{encrypted_token[:20]}..."
                )
                return None

        # Déchiffrer chaque token
        tokens['access_token'] = decrypt_token(self.encrypted_access_token)
        tokens['refresh_token'] = decrypt_token(self.encrypted_refresh_token)
        tokens['id_token'] = decrypt_token(self.encrypted_id_token)

        return tokens

    except Exception as e:
        logger.error(f"Error decrypting tokens: {str(e)}", exc_info=True)
        return {'access_token': None, 'refresh_token': None, 'id_token': None}
```

**Avantages de cette approche :**
- ✅ Rétrocompatibilité totale avec tokens existants en format "dev:"
- ✅ Migration progressive (pas besoin de migrer tous les tokens d'un coup)
- ✅ Détection automatique du format (pas de configuration supplémentaire)
- ✅ Graceful degradation en cas d'erreur Vault
- ✅ Cohérence avec la logique d'activation de `save_tokens()`

---

### 3. Création automatique des clés Vault (backend/app/services/tenant_sso_config_service.py)

#### 3.1 Modifier `create_sso_config()` (après ligne 100)

**Objectif :** Créer automatiquement la clé de chiffrement Vault lors de la création de la config SSO si le chiffrement est activé.

**Modifications :**
```python
try:
    db.session.add(sso_config)
    db.session.commit()
    logger.info(f"Created SSO configuration for tenant {tenant_id}")

    # Créer la clé de chiffrement Vault si activé
    # (même logique combinée que UserAzureIdentity)
    use_vault = (
        current_app.config.get('USE_VAULT_TOKEN_ENCRYPTION', False) or
        current_app.config.get('FLASK_ENV') == 'production'
    )

    if use_vault:
        try:
            from app.services.vault_encryption_service import VaultEncryptionService
            vault_service = VaultEncryptionService()
            vault_service.ensure_encryption_key(tenant_id)

            if current_app.config.get('USE_VAULT_TOKEN_ENCRYPTION'):
                logger.info(
                    f"Created Vault encryption key for tenant {tenant_id} "
                    f"(USE_VAULT_TOKEN_ENCRYPTION=true)"
                )
            else:
                logger.info(
                    f"Created Vault encryption key for tenant {tenant_id} "
                    f"(automatic in production mode)"
                )
        except Exception as e:
            # Ne pas bloquer la création de la config SSO si Vault échoue
            logger.warning(
                f"Failed to create Vault encryption key for tenant {tenant_id}: {str(e)}. "
                f"Tokens will be stored in dev mode until Vault is available."
            )

    return sso_config
```

#### 3.2 Modifier `enable_sso()` (ligne 229+)

**Objectif :** Créer la clé de chiffrement lors de l'activation SSO si elle n'existe pas.

**Logique similaire :**
```python
# Après avoir activé is_enabled=True
use_vault = (
    current_app.config.get('USE_VAULT_TOKEN_ENCRYPTION', False) or
    current_app.config.get('FLASK_ENV') == 'production'
)

if use_vault:
    try:
        from app.services.vault_encryption_service import VaultEncryptionService
        vault_service = VaultEncryptionService()
        vault_service.ensure_encryption_key(tenant_id)
        logger.info(f"Ensured Vault encryption key exists for tenant {tenant_id}")
    except Exception as e:
        logger.warning(f"Failed to ensure Vault encryption key: {str(e)}")
```

---

### 4. Script de migration (backend/scripts/migrate_tokens_to_vault.py)

**Objectif :** Fournir un script optionnel pour re-chiffrer les tokens existants au format "dev:" vers le format Vault.

**Note :** Le script détecte automatiquement si le chiffrement est activé (via la logique combinée).

**Fonctionnalités :**
1. Lister tous les `UserAzureIdentity` avec tokens au format "dev:"
2. Vérifier que le chiffrement Vault est activé (USE_VAULT_TOKEN_ENCRYPTION ou FLASK_ENV=production)
3. Pour chaque tenant unique, créer la clé Vault si nécessaire
4. Re-chiffrer tous les tokens avec `VaultEncryptionService`
5. Mettre à jour en base de données
6. Générer un rapport détaillé (succès/échecs)
7. Support du mode `--dry-run` pour prévisualisation
8. Support du flag `--tenant-id` pour migrer un seul tenant

**Code complet :**
```python
#!/usr/bin/env python
"""
Script de migration des tokens SSO vers le chiffrement Vault Transit.

Usage:
    python scripts/migrate_tokens_to_vault.py [--dry-run] [--tenant-id <uuid>]

Options:
    --dry-run       Afficher les changements sans les appliquer
    --tenant-id     Migrer uniquement un tenant spécifique

Note:
    Le script vérifie automatiquement si le chiffrement Vault est activé via:
    - USE_VAULT_TOKEN_ENCRYPTION=true (explicite)
    - OU FLASK_ENV=production (automatique)
"""

import argparse
import sys
from sqlalchemy import func
from app import create_app
from app.models import UserAzureIdentity
from app.services.vault_encryption_service import VaultEncryptionService
from app.extensions import db

def main():
    parser = argparse.ArgumentParser(description='Migrate SSO tokens to Vault encryption')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--tenant-id', help='Migrate only this tenant')
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        # Vérifier que le chiffrement Vault est activé
        # (même logique combinée que UserAzureIdentity)
        use_vault = (
            app.config.get('USE_VAULT_TOKEN_ENCRYPTION', False) or
            app.config.get('FLASK_ENV') == 'production'
        )

        if not use_vault:
            print("ERROR: Vault token encryption is not enabled")
            print(f"Current config: FLASK_ENV={app.config.get('FLASK_ENV')}, "
                  f"USE_VAULT_TOKEN_ENCRYPTION={app.config.get('USE_VAULT_TOKEN_ENCRYPTION')}")
            print("\nTo enable encryption, either:")
            print("  1. Set USE_VAULT_TOKEN_ENCRYPTION=true")
            print("  2. OR set FLASK_ENV=production")
            sys.exit(1)

        # Initialiser Vault service
        try:
            vault_service = VaultEncryptionService()
            if not vault_service.is_healthy():
                print("ERROR: Vault is not healthy")
                sys.exit(1)
        except Exception as e:
            print(f"ERROR: Failed to initialize Vault service: {e}")
            sys.exit(1)

        # Trouver les identités avec tokens en format "dev:"
        query = UserAzureIdentity.query.filter(
            UserAzureIdentity.encrypted_access_token.like('dev:%')
        )

        if args.tenant_id:
            query = query.filter_by(tenant_id=args.tenant_id)

        identities = query.all()

        print(f"Found {len(identities)} identities with dev tokens")
        print(f"Encryption enabled by: ", end="")
        if app.config.get('USE_VAULT_TOKEN_ENCRYPTION'):
            print("USE_VAULT_TOKEN_ENCRYPTION=true")
        else:
            print(f"FLASK_ENV={app.config.get('FLASK_ENV')} (automatic)")

        if args.dry_run:
            print("\n[DRY RUN MODE - No changes will be made]")

        # Grouper par tenant
        tenants = {}
        for identity in identities:
            tenant_id = str(identity.tenant_id)
            if tenant_id not in tenants:
                tenants[tenant_id] = []
            tenants[tenant_id].append(identity)

        stats = {'success': 0, 'failed': 0, 'total': len(identities)}

        # Migrer chaque tenant
        for tenant_id, tenant_identities in tenants.items():
            print(f"\nProcessing tenant {tenant_id} ({len(tenant_identities)} identities)...")

            # Créer la clé de chiffrement
            try:
                if not args.dry_run:
                    vault_service.ensure_encryption_key(tenant_id)
                print(f"  ✓ Encryption key ensured for tenant {tenant_id}")
            except Exception as e:
                print(f"  ✗ Failed to create key for tenant {tenant_id}: {e}")
                stats['failed'] += len(tenant_identities)
                continue

            # Re-chiffrer les tokens
            for identity in tenant_identities:
                try:
                    # Déchiffrer les tokens dev:
                    old_access = identity.encrypted_access_token[4:] if identity.encrypted_access_token else None
                    old_refresh = identity.encrypted_refresh_token[4:] if identity.encrypted_refresh_token else None
                    old_id = identity.encrypted_id_token[4:] if identity.encrypted_id_token else None

                    if not args.dry_run:
                        # Re-chiffrer avec Vault
                        identity.encrypted_access_token = vault_service.encrypt_token(tenant_id, old_access)
                        identity.encrypted_refresh_token = vault_service.encrypt_token(tenant_id, old_refresh)
                        identity.encrypted_id_token = vault_service.encrypt_token(tenant_id, old_id)

                    stats['success'] += 1
                    print(f"  ✓ Migrated tokens for user {identity.user_id}")

                except Exception as e:
                    print(f"  ✗ Failed to migrate identity {identity.id}: {e}")
                    stats['failed'] += 1

        # Commit si pas en dry-run
        if not args.dry_run:
            db.session.commit()
            print("\n✓ All changes committed to database")
        else:
            print("\n[DRY RUN COMPLETE - No changes were made]")

        # Rapport final
        print("\n" + "="*60)
        print("MIGRATION REPORT")
        print("="*60)
        print(f"Total identities: {stats['total']}")
        print(f"Successfully migrated: {stats['success']}")
        print(f"Failed: {stats['failed']}")
        if stats['total'] > 0:
            print(f"Success rate: {stats['success']/stats['total']*100:.1f}%")

if __name__ == '__main__':
    main()
```

**Usage :**
```bash
# Prévisualisation (dry-run)
docker-compose exec api python scripts/migrate_tokens_to_vault.py --dry-run

# Migration complète
docker-compose exec api python scripts/migrate_tokens_to_vault.py

# Migration d'un seul tenant
docker-compose exec api python scripts/migrate_tokens_to_vault.py --tenant-id <uuid>
```

---

## Guide de migration en production

Cette section couvre tous les aspects pratiques pour migrer en toute sécurité les tokens existants du format "dev:" vers le chiffrement Vault en production.

### Vue d'ensemble de la migration

**Contexte :** Si vous avez déjà des tokens SSO stockés en format "dev:" en base de données, vous devez les migrer vers le format chiffré "vault:v1:" lors du passage en production.

**Bonne nouvelle :** La migration peut être **progressive** et **sans interruption de service** grâce à la détection automatique du format de token.

**Stratégies de migration :**
1. **Migration immédiate** : Migrer tous les tokens en une seule fois (recommandé si < 1000 utilisateurs)
2. **Migration progressive** : Laisser coexister les deux formats et migrer par vagues
3. **Migration naturelle** : Attendre que les tokens expirent et se renouvellent automatiquement

---

### Précautions AVANT la migration

#### 1. Backup de la base de données

**CRITIQUE** : Toujours effectuer un backup avant toute migration.

```bash
# Backup PostgreSQL complet
docker-compose exec postgres pg_dump -U postgres saas_platform > backup_before_vault_migration_$(date +%Y%m%d_%H%M%S).sql

# OU Backup uniquement de la table user_azure_identities
docker-compose exec postgres pg_dump -U postgres -t user_azure_identities saas_platform > backup_azure_identities_$(date +%Y%m%d_%H%M%S).sql

# Vérifier la taille du backup
ls -lh backup_*.sql
```

#### 2. Vérifier la santé de Vault

```bash
# 1. Vérifier que Vault est accessible
curl -f http://localhost:8201/v1/sys/health || echo "ERREUR: Vault inaccessible"

# 2. Vérifier que Transit Engine est activé
docker-compose exec vault vault secrets list | grep transit || echo "ERREUR: Transit Engine non activé"

# 3. Tester la création d'une clé test
docker-compose exec vault vault write -f transit/keys/test-migration
docker-compose exec vault vault read transit/keys/test-migration
docker-compose exec vault vault delete transit/keys/test-migration

# 4. Vérifier l'espace disque
docker-compose exec vault df -h /vault/data
```

#### 3. Inventaire des tokens à migrer

```bash
# Compter les tokens à migrer
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT
    COUNT(*) as total_identities,
    COUNT(DISTINCT tenant_id) as affected_tenants,
    COUNT(CASE WHEN encrypted_access_token LIKE 'dev:%' THEN 1 END) as dev_tokens,
    COUNT(CASE WHEN encrypted_access_token LIKE 'vault:v%' THEN 1 END) as vault_tokens
FROM user_azure_identities;
"

# Lister les tenants affectés
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT
    t.name as tenant_name,
    t.id as tenant_id,
    COUNT(uai.id) as user_count
FROM user_azure_identities uai
JOIN tenants t ON t.id = uai.tenant_id
WHERE uai.encrypted_access_token LIKE 'dev:%'
GROUP BY t.id, t.name
ORDER BY user_count DESC;
"
```

#### 4. Estimation du temps de migration

**Règle empirique :**
- **~100 tokens/seconde** (dépend de Vault et de la latence réseau)
- Pour 1000 tokens : ~10 secondes
- Pour 10 000 tokens : ~1-2 minutes
- Pour 100 000 tokens : ~15-20 minutes

```bash
# Estimer le temps
TOTAL_TOKENS=$(docker-compose exec postgres psql -U postgres -d saas_platform -t -c "SELECT COUNT(*) FROM user_azure_identities WHERE encrypted_access_token LIKE 'dev:%';")
echo "Temps estimé: $((TOTAL_TOKENS / 100)) secondes (~$((TOTAL_TOKENS / 100 / 60)) minutes)"
```

---

### Stratégie 1 : Migration immédiate (recommandée)

**Quand l'utiliser :**
- Moins de 10 000 utilisateurs SSO
- Possibilité d'une courte fenêtre de maintenance
- Besoin de sécuriser rapidement tous les tokens

**Procédure complète :**

#### Étape 1 : Préparation (sans impact)

```bash
# 1. Activer le chiffrement en production (si pas déjà fait)
# Dans .env ou docker-compose.yml
FLASK_ENV=production

# 2. Redémarrer l'API (les nouveaux tokens seront chiffrés)
docker-compose restart api celery-worker-sso

# 3. Vérifier les logs
docker-compose logs api | grep -E "automatic in production|Vault"

# 4. Tester avec un nouveau login SSO
# Le nouveau token devrait être en format vault:v1:
```

#### Étape 2 : Dry-run (sans impact)

```bash
# Test complet sans modification
docker-compose exec api python scripts/migrate_tokens_to_vault.py --dry-run

# Vérifier le rapport :
# - Nombre de tokens à migrer
# - Nombre de tenants affectés
# - Vérifier qu'il n'y a pas d'erreurs
```

#### Étape 3 : Migration réelle

```bash
# ATTENTION : Cette commande modifie la base de données !

# Option A : Migration en une seule fois
docker-compose exec api python scripts/migrate_tokens_to_vault.py

# Option B : Migration par tenant (plus sûr)
# Lister les tenants
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT DISTINCT tenant_id FROM user_azure_identities WHERE encrypted_access_token LIKE 'dev:%';
"

# Migrer tenant par tenant
docker-compose exec api python scripts/migrate_tokens_to_vault.py --tenant-id <tenant-id-1>
docker-compose exec api python scripts/migrate_tokens_to_vault.py --tenant-id <tenant-id-2>
# etc.
```

#### Étape 4 : Vérification post-migration

```bash
# 1. Compter les tokens migrés
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT
    COUNT(CASE WHEN encrypted_access_token LIKE 'dev:%' THEN 1 END) as dev_tokens,
    COUNT(CASE WHEN encrypted_access_token LIKE 'vault:v%' THEN 1 END) as vault_tokens,
    COUNT(*) as total
FROM user_azure_identities;
"

# Résultat attendu :
# dev_tokens | vault_tokens | total
# -----------+--------------+-------
#          0 |         1234 |  1234

# 2. Tester le déchiffrement d'un token aléatoire
docker-compose exec api python -c "
from app import create_app
from app.models import UserAzureIdentity

app = create_app()
with app.app_context():
    identity = UserAzureIdentity.query.filter(
        UserAzureIdentity.encrypted_access_token.like('vault:v%')
    ).first()

    if identity:
        tokens = identity.get_decrypted_tokens()
        print(f'✓ Token decrypted successfully for user {identity.user_id}')
        print(f'  Access token length: {len(tokens[\"access_token\"]) if tokens[\"access_token\"] else 0}')
        print(f'  Refresh token length: {len(tokens[\"refresh_token\"]) if tokens[\"refresh_token\"] else 0}')
    else:
        print('✗ No vault tokens found')
"

# 3. Tester un refresh de token SSO
# Via l'API ou en attendant le prochain cycle Celery
docker-compose logs -f celery-worker-sso | grep "refresh"
```

---

### Stratégie 2 : Migration progressive

**Quand l'utiliser :**
- Plus de 10 000 utilisateurs SSO
- Pas de fenêtre de maintenance possible
- Préférence pour une migration par vagues

**Avantages :**
- Zéro interruption de service
- Possibilité de rollback partiel
- Détection des problèmes sur un sous-ensemble

**Procédure :**

#### Phase 1 : Activer le chiffrement (nouveaux tokens uniquement)

```bash
# 1. Activer le chiffrement
FLASK_ENV=production
docker-compose restart api celery-worker-sso

# Résultat : Les nouveaux logins SSO créent des tokens vault:v1:
# Les anciens tokens dev: continuent de fonctionner
```

#### Phase 2 : Migration par vagues (exemple : 20% par vague)

```bash
# Vague 1 : Migrer 20% des tenants
TENANT_IDS=$(docker-compose exec postgres psql -U postgres -d saas_platform -t -c "
SELECT DISTINCT tenant_id
FROM user_azure_identities
WHERE encrypted_access_token LIKE 'dev:%'
LIMIT 5;  -- Ajuster selon le nombre de tenants
")

for tenant_id in $TENANT_IDS; do
    echo "Migrating tenant: $tenant_id"
    docker-compose exec api python scripts/migrate_tokens_to_vault.py --tenant-id $tenant_id
done

# Attendre 1-2 heures et monitorer les logs
docker-compose logs api | grep -E "decrypt|encrypt|Vault" | tail -100

# Si tout va bien, passer à la vague 2, etc.
```

#### Phase 3 : Monitorer la coexistence

```bash
# Script de monitoring (à exécuter périodiquement)
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT
    DATE(created_at) as date,
    COUNT(CASE WHEN encrypted_access_token LIKE 'dev:%' THEN 1 END) as dev_tokens,
    COUNT(CASE WHEN encrypted_access_token LIKE 'vault:v%' THEN 1 END) as vault_tokens,
    ROUND(100.0 * COUNT(CASE WHEN encrypted_access_token LIKE 'vault:v%' THEN 1 END) / COUNT(*), 2) as vault_percentage
FROM user_azure_identities
GROUP BY DATE(created_at)
ORDER BY date DESC
LIMIT 7;
"
```

---

### Stratégie 3 : Migration naturelle (sans action)

**Concept :** Laisser les tokens expirer et se renouveler automatiquement.

**Quand l'utiliser :**
- Pas d'urgence sécurité
- Infrastructure Vault récente (pas testée en prod)
- Préférence pour éviter toute manipulation manuelle

**Timeline :**
- **Access tokens** : expirent après 1h → renouvelés en format vault:v1:
- **Refresh tokens** : expirent après 7 jours → utilisateurs doivent se ré-authentifier

**Procédure :**

```bash
# 1. Activer le chiffrement
FLASK_ENV=production
docker-compose restart api celery-worker-sso

# 2. Ne rien faire et attendre

# 3. Monitorer la migration naturelle
watch -n 3600 'docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT
    COUNT(CASE WHEN encrypted_access_token LIKE \"dev:%\" THEN 1 END) as dev_tokens,
    COUNT(CASE WHEN encrypted_access_token LIKE \"vault:v%\" THEN 1 END) as vault_tokens
FROM user_azure_identities;
"'

# Après 7 jours, tous les refresh tokens auront expiré
# Les utilisateurs auront dû se ré-authentifier → nouveaux tokens chiffrés
```

**Inconvénient :** Certains utilisateurs inactifs gardent des tokens dev: pendant longtemps.

---

### Impact sur les sessions actives

#### Pendant la migration (stratégie immédiate)

**Question :** Que se passe-t-il pour les utilisateurs connectés pendant la migration ?

**Réponse :** **Aucun impact** - la migration est transparente !

**Explication :**
1. Le script modifie seulement le format de stockage en base
2. Les tokens eux-mêmes (valeur déchiffrée) restent identiques
3. L'application détecte automatiquement le format (dev: ou vault:v1:)
4. Les utilisateurs ne sont PAS déconnectés

**Exemple de flux :**

```
AVANT migration (10:00):
- User123 se connecte via SSO
- Token stocké : "dev:eyJ0eXAiOiJKV1QiLCJhbGc..."
- User123 utilise l'API normalement

PENDANT migration (10:05):
- Script migre le token de User123
- Token stocké : "vault:v1:AEEeDGsj3SlKKMx..."
- User123 continue d'utiliser l'API sans interruption

APRÈS migration (10:10):
- User123 fait un refresh de token
- Nouveau token créé : "vault:v1:BHGtPlm9OlmzNx..."
- User123 ne remarque aucune différence
```

#### Ordre des opérations recommandé

**Option 1 : Activer AVANT de migrer** (recommandé)
```
1. Activer FLASK_ENV=production
2. Redémarrer l'API
3. Attendre 5-10 minutes (stabilisation)
4. Lancer la migration
```

**Avantage :** Les nouveaux logins créent déjà des tokens chiffrés pendant la migration.

**Option 2 : Migrer PUIS activer**
```
1. Lancer la migration (avec FLASK_ENV=development + USE_VAULT_TOKEN_ENCRYPTION=true)
2. Vérifier le résultat
3. Activer FLASK_ENV=production
4. Redémarrer l'API
```

**Avantage :** Permet de tester la migration avant d'activer en production.

---

### Vérification post-migration complète

#### 1. Vérifications en base de données

```bash
# Test 1 : Aucun token dev: ne doit rester
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT COUNT(*) as remaining_dev_tokens
FROM user_azure_identities
WHERE encrypted_access_token LIKE 'dev:%';
"
# Résultat attendu : 0

# Test 2 : Tous les tokens doivent être en vault:v1:
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT COUNT(*) as vault_tokens
FROM user_azure_identities
WHERE encrypted_access_token LIKE 'vault:v%';
"

# Test 3 : Vérifier quelques tokens aléatoires
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT
    user_id,
    LEFT(encrypted_access_token, 30) as token_prefix,
    token_expires_at,
    last_sync
FROM user_azure_identities
ORDER BY RANDOM()
LIMIT 5;
"
# Tous les token_prefix doivent commencer par "vault:v1:"
```

#### 2. Test fonctionnel complet

```bash
# Test de déchiffrement sur tous les tokens
docker-compose exec api python -c "
from app import create_app
from app.models import UserAzureIdentity

app = create_app()
with app.app_context():
    identities = UserAzureIdentity.query.all()
    success = 0
    failed = 0

    for identity in identities:
        tokens = identity.get_decrypted_tokens()
        if tokens['access_token']:
            success += 1
        else:
            failed += 1
            print(f'✗ Failed to decrypt for user {identity.user_id}')

    print(f'\n✓ Successfully decrypted: {success}/{len(identities)}')
    print(f'✗ Failed to decrypt: {failed}/{len(identities)}')
"
```

#### 3. Test de refresh de token

```bash
# Forcer un refresh manuel via Celery
docker-compose exec api python -c "
from app.tasks.sso_tasks import refresh_expiring_tokens
result = refresh_expiring_tokens.delay()
print(f'Task ID: {result.id}')
print('Check Flower for results: http://localhost:5555')
"

# Vérifier les logs
docker-compose logs celery-worker-sso | grep -E "refresh.*success|refresh.*failed"
```

#### 4. Test end-to-end SSO

```bash
# 1. Faire un login SSO complet
curl -X GET "http://localhost:4999/api/auth/sso/azure/login/<tenant-id>"

# 2. Suivre le flux OAuth2 dans le navigateur

# 3. Après callback, vérifier que le token est chiffré
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT
    user_id,
    LEFT(encrypted_access_token, 30),
    created_at
FROM user_azure_identities
ORDER BY created_at DESC
LIMIT 1;
"
# Doit afficher vault:v1:...
```

---

### Procédure de rollback

#### Cas 1 : Rollback complet (migration échouée)

**Si la migration a échoué avant le commit :**
```bash
# La transaction est automatiquement annulée
# Aucune action nécessaire
```

**Si la migration est partiellement réussie :**

```bash
# 1. Restaurer le backup
docker-compose exec postgres psql -U postgres saas_platform < backup_before_vault_migration_*.sql

# 2. Désactiver le chiffrement
# Dans .env
FLASK_ENV=development
# OU
USE_VAULT_TOKEN_ENCRYPTION=false

# 3. Redémarrer l'API
docker-compose restart api celery-worker-sso

# 4. Vérifier que les tokens dev: fonctionnent
docker-compose logs api | grep "dev mode"
```

#### Cas 2 : Rollback partiel (certains tenants problématiques)

**Identifier les tenants problématiques :**
```bash
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT
    tenant_id,
    COUNT(*) as total,
    COUNT(CASE WHEN encrypted_access_token LIKE 'dev:%' THEN 1 END) as dev_tokens,
    COUNT(CASE WHEN encrypted_access_token LIKE 'vault:v%' THEN 1 END) as vault_tokens
FROM user_azure_identities
GROUP BY tenant_id
HAVING COUNT(CASE WHEN encrypted_access_token LIKE 'dev:%' THEN 1 END) > 0
   AND COUNT(CASE WHEN encrypted_access_token LIKE 'vault:v%' THEN 1 END) > 0;
"
# Tenants avec mix dev:/vault: = problème
```

**Rollback sélectif :**
```sql
-- ATTENTION : Nécessite d'avoir gardé une copie des anciens tokens
-- Recommandé : Forcer la ré-authentification SSO pour ces utilisateurs

-- Marquer les tokens comme expirés pour forcer re-auth
UPDATE user_azure_identities
SET
    token_expires_at = NOW() - INTERVAL '1 hour',
    refresh_token_expires_at = NOW() - INTERVAL '1 hour'
WHERE tenant_id = '<problematic-tenant-id>';
```

---

### Timeline et coexistence des formats

#### Combien de temps peut-on laisser coexister dev: et vault:v1: ?

**Réponse courte :** **Indéfiniment** - c'est parfaitement supporté.

**Réponse détaillée :**

| Durée | Impact | Recommandation |
|-------|--------|----------------|
| < 1 heure | Aucun | Normal pendant migration immédiate |
| 1-7 jours | Aucun | OK pour migration progressive |
| 1-4 semaines | Aucun | OK si migration naturelle en cours |
| > 1 mois | Risque sécurité | **Non recommandé** - finaliser la migration |
| > 3 mois | Risque élevé | **À éviter** - tokens non chiffrés en prod |

**Problèmes potentiels de coexistence longue :**
1. **Sécurité :** Tokens dev: ne sont pas chiffrés (risque si backup DB volé)
2. **Complexité :** Mix de formats complique le debugging
3. **Compliance :** Certaines normes (PCI-DSS, HIPAA) exigent chiffrement complet

**Recommandation :** Finaliser la migration dans les **7 jours** maximum.

---

### Checklist complète de migration

Utilisez cette checklist pour une migration sans risque :

#### Pré-migration
- [ ] Backup de la base de données effectué
- [ ] Vault est sain et Transit Engine activé
- [ ] Inventaire des tokens (nombre, tenants affectés)
- [ ] Temps de migration estimé
- [ ] Dry-run réussi sans erreurs
- [ ] Fenêtre de maintenance planifiée (si nécessaire)
- [ ] Équipe technique prévenue et disponible

#### Migration
- [ ] FLASK_ENV=production activé
- [ ] API et workers redémarrés
- [ ] Logs vérifiés (pas d'erreur Vault)
- [ ] Script de migration exécuté
- [ ] Rapport de migration analysé (taux de succès > 99%)
- [ ] Aucune erreur critique dans les logs

#### Post-migration
- [ ] Vérification SQL : 0 tokens dev: restants
- [ ] Test de déchiffrement : tous les tokens déchiffrables
- [ ] Test de refresh : tokens renouvelables
- [ ] Test end-to-end SSO : nouveau login fonctionne
- [ ] Monitoring actif pendant 24h
- [ ] Backup post-migration effectué
- [ ] Documentation mise à jour

#### 24h après migration
- [ ] Aucun incident utilisateur reporté
- [ ] Logs Vault normaux (pas d'erreurs de déchiffrement)
- [ ] Tâches Celery refresh fonctionnent
- [ ] Métriques de performance normales
- [ ] Backup de sécurité conservé pendant 30 jours

---

### Cas particuliers et questions fréquentes

#### Q: Que faire si un utilisateur ne peut plus se connecter après migration ?

**Diagnostic :**
```bash
# Vérifier le token de cet utilisateur
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT
    user_id,
    tenant_id,
    LEFT(encrypted_access_token, 30) as token_prefix,
    token_expires_at,
    refresh_token_expires_at
FROM user_azure_identities
WHERE user_id = '<user-id>';
"
```

**Solutions :**
1. Si token expiré → Normal, re-authentification SSO requise
2. Si token vault: mais erreur déchiffrement → Vérifier que Vault est accessible
3. Si token corrompu → Forcer expiration et re-auth

```bash
# Forcer re-authentification
docker-compose exec postgres psql -U postgres -d saas_platform -c "
UPDATE user_azure_identities
SET token_expires_at = NOW() - INTERVAL '1 hour',
    refresh_token_expires_at = NOW() - INTERVAL '1 hour'
WHERE user_id = '<user-id>';
"
```

#### Q: Peut-on revenir au format dev: après migration ?

**Réponse :** Oui, mais **fortement déconseillé** en production.

```bash
# Désactiver le chiffrement (déconseillé en prod)
USE_VAULT_TOKEN_ENCRYPTION=false
FLASK_ENV=development

# Les tokens vault:v1: existants NE SERONT PLUS déchiffrables
# Les utilisateurs devront se ré-authentifier
```

#### Q: Que se passe-t-il si Vault tombe après la migration ?

**Impact :**
- Les tokens vault:v1: existants ne peuvent plus être déchiffrés
- Les utilisateurs doivent se ré-authentifier
- Nouveaux tokens stockés en format dev: (fallback)

**Recommandation :**
- Vault en mode HA (High Availability) en production
- Monitoring actif sur Vault
- Alertes sur échecs de déchiffrement

#### Q: Combien de temps garder les backups ?

**Recommandation :**
- **Backup pré-migration :** 30 jours minimum
- **Backup post-migration :** permanent (rotation standard)
- **Backups chiffrés :** car contiennent des tokens Vault

---

### 5. Tests

#### 5.1 Tests unitaires (backend/tests/unit/test_vault_token_encryption.py)

**Scénarios à tester :**
1. ✅ `save_tokens()` avec `USE_VAULT_TOKEN_ENCRYPTION=True` stocke au format `vault:v1:`
2. ✅ `save_tokens()` avec `FLASK_ENV=production` (sans variable) stocke au format `vault:v1:`
3. ✅ `save_tokens()` avec `FLASK_ENV=development` stocke au format `dev:`
4. ✅ `save_tokens()` avec `FLASK_ENV=production` + `USE_VAULT_TOKEN_ENCRYPTION=False` stocke au format `dev:` (override)
5. ✅ `get_decrypted_tokens()` déchiffre correctement les tokens Vault
6. ✅ `get_decrypted_tokens()` déchiffre correctement les tokens dev:
7. ✅ Rétrocompatibilité : tokens dev: peuvent être lus même avec Vault activé
8. ✅ Gestion d'erreur : échec Vault → fallback vers mode dev:
9. ✅ Création automatique de clé lors de `create_sso_config()`

#### 5.2 Tests d'intégration (backend/tests/integration/test_sso_token_lifecycle.py)

**Scénarios à tester :**
1. ✅ Flux complet SSO → stockage → refresh → relecture avec Vault
2. ✅ Tâches Celery de refresh fonctionnent avec tokens Vault
3. ✅ Rotation de clés Vault via `rotate_encryption_keys()`
4. ✅ Migration de tokens dev: → vault: ne casse pas les sessions actives
5. ✅ Comportement en production (FLASK_ENV=production) active automatiquement Vault

#### 5.3 Tests manuels

**Checklist :**
- [ ] **Scénario 1 : Développement sans chiffrement**
  - [ ] `FLASK_ENV=development` (pas de variable USE_VAULT_TOKEN_ENCRYPTION)
  - [ ] Faire un login SSO
  - [ ] Vérifier en base : tokens au format `dev:`

- [ ] **Scénario 2 : Développement avec chiffrement (test)**
  - [ ] `FLASK_ENV=development` + `USE_VAULT_TOKEN_ENCRYPTION=true`
  - [ ] Redémarrer l'app
  - [ ] Faire un login SSO
  - [ ] Vérifier en base : tokens au format `vault:v1:`

- [ ] **Scénario 3 : Production avec chiffrement (automatique)**
  - [ ] `FLASK_ENV=production` (pas de variable USE_VAULT_TOKEN_ENCRYPTION)
  - [ ] Redémarrer l'app
  - [ ] Faire un login SSO
  - [ ] Vérifier en base : tokens au format `vault:v1:`

- [ ] **Scénario 4 : Rétrocompatibilité**
  - [ ] Vérifier que les anciens tokens dev: peuvent toujours être rafraîchis
  - [ ] Lancer le script de migration
  - [ ] Vérifier tous les tokens sont maintenant en format `vault:v1:`

---

### 6. Documentation

#### 6.1 Mettre à jour CLAUDE.md

**Section à ajouter :**
```markdown
### SSO Token Encryption with Vault Transit

The platform supports encryption of SSO tokens (access_token, refresh_token, id_token)
using HashiCorp Vault Transit Engine.

**Automatic Activation:**
Encryption is **automatically enabled in production mode** (`FLASK_ENV=production`) for security by default.

**Configuration:**
```bash
# Optional: force enable in development (for testing)
USE_VAULT_TOKEN_ENCRYPTION=true

# Optional: force disable in production (NOT RECOMMENDED)
USE_VAULT_TOKEN_ENCRYPTION=false
```

**Activation Logic:**
```python
# Encryption is enabled if:
# 1. USE_VAULT_TOKEN_ENCRYPTION=true (explicit)
# OR
# 2. FLASK_ENV=production (automatic)
```

**Decision Matrix:**

| FLASK_ENV | USE_VAULT_TOKEN_ENCRYPTION | Encryption | Token Format |
|-----------|---------------------------|------------|--------------|
| development | (unset/false) | ❌ Disabled | `dev:...` |
| development | true | ✅ Enabled | `vault:v1:...` |
| production | (unset) | ✅ Enabled | `vault:v1:...` |
| production | false | ❌ Disabled ⚠️ | `dev:...` |

**How it works:**
- Each tenant gets a dedicated encryption key: `azure-tokens-{tenant_id}`
- Keys are created automatically when SSO is configured for a tenant
- Tokens are encrypted before being stored in the database
- Automatic key rotation every 30 days (configurable in Vault)
- Backward compatible with existing unencrypted tokens

**Migration:**
```bash
# Migrate existing dev: tokens to Vault encryption
docker-compose exec api python scripts/migrate_tokens_to_vault.py --dry-run
docker-compose exec api python scripts/migrate_tokens_to_vault.py
```

**Troubleshooting:**
- If Vault is unavailable, tokens are stored in development mode (prefix `dev:`)
- Check Vault health: `curl http://localhost:8201/v1/sys/health`
- Check if Transit Engine is enabled: `docker-compose exec vault vault secrets list`
- View encryption keys: `docker-compose exec vault vault list transit/keys`
```

#### 6.2 Variables d'environnement

**Documenter dans .env.docker.minimal :**
```bash
# ============================================================================
# Vault Transit Engine for Token Encryption (OPTIONAL)
# ============================================================================
# Control encryption of SSO tokens using Vault Transit Engine
#
# AUTOMATIC BEHAVIOR:
#   - FLASK_ENV=production  → Encryption ENABLED (secure by default)
#   - FLASK_ENV=development → Encryption DISABLED
#
# MANUAL OVERRIDE:
#   - Set to 'true' to force enable in development (for testing Vault)
#   - Set to 'false' to force disable in production (NOT RECOMMENDED)
#
# Requires Vault to be running with Transit Engine enabled
# Default: automatic based on FLASK_ENV
#
# USE_VAULT_TOKEN_ENCRYPTION=false  # Uncomment to override
```

---

## Activation finale

### Scénario 1 : Production (recommandé - chiffrement automatique)

**Configuration minimale :**
```bash
# Dans .env
FLASK_ENV=production
# Pas besoin de USE_VAULT_TOKEN_ENCRYPTION - c'est automatique !
```

**Étapes :**

1. **Vérifier que Vault Transit est actif :**
```bash
docker-compose exec vault vault secrets list
# Devrait afficher: transit/    transit    n/a    ...
```

2. **Démarrer en mode production :**
```bash
docker-compose up -d
```

3. **Vérifier le chiffrement :**
```bash
# Logs montrant l'activation automatique
docker-compose logs api | grep -i "automatic in production"

# Faire un login SSO test
curl -X POST http://localhost:4999/api/auth/sso/azure/login/<tenant_id>

# Vérifier en base : tokens au format vault:v1:
docker-compose exec postgres psql -U postgres -d saas_platform -c \
  "SELECT user_id, LEFT(encrypted_access_token, 20) FROM user_azure_identities LIMIT 5;"
```

4. **Migrer les tokens existants (si applicable) :**
```bash
docker-compose exec api python scripts/migrate_tokens_to_vault.py --dry-run
docker-compose exec api python scripts/migrate_tokens_to_vault.py
```

---

### Scénario 2 : Développement avec test du chiffrement

**Configuration :**
```bash
# Dans .env
FLASK_ENV=development
USE_VAULT_TOKEN_ENCRYPTION=true  # Activation explicite pour tester
```

**Étapes :**

1. **Démarrer Vault et l'application :**
```bash
cp .env.docker.minimal .env
echo "USE_VAULT_TOKEN_ENCRYPTION=true" >> .env
docker-compose up -d
```

2. **Tester le chiffrement en dev :**
```bash
# Les logs devraient montrer : "explicit USE_VAULT_TOKEN_ENCRYPTION=true"
docker-compose logs api | grep -i "explicit USE_VAULT_TOKEN_ENCRYPTION"

# Faire un login SSO
# Vérifier que les tokens sont chiffrés (format vault:v1:)
```

---

### Scénario 3 : Développement normal (sans chiffrement)

**Configuration :**
```bash
# Dans .env
FLASK_ENV=development
# Pas de USE_VAULT_TOKEN_ENCRYPTION (ou =false)
```

**Résultat :**
- Tokens stockés au format `dev:...`
- Pas besoin de Vault fonctionnel
- Développement simplifié

---

## Monitoring et maintenance

### Vérifier la configuration active

```bash
# Voir quelle méthode active le chiffrement
docker-compose logs api | grep -E "explicit USE_VAULT_TOKEN_ENCRYPTION|automatic in production"

# Vérifier l'environnement
docker-compose exec api env | grep -E "FLASK_ENV|USE_VAULT_TOKEN_ENCRYPTION"
```

### Vérifier la santé de Vault

```bash
# Health check
curl http://localhost:8201/v1/sys/health

# Lister les clés de chiffrement
docker-compose exec vault vault list transit/keys

# Voir les détails d'une clé
docker-compose exec vault vault read transit/keys/azure-tokens-<tenant_id>
```

### Rotation manuelle des clés

```bash
# Via Celery task
docker-compose exec api python -c "
from app.tasks.sso_tasks import rotate_encryption_keys
result = rotate_encryption_keys.delay()
print(f'Task ID: {result.id}')
"

# Suivre le résultat dans Flower
open http://localhost:5555
```

### Logs importants

```bash
# Logs de chiffrement/déchiffrement
docker-compose logs api | grep "encrypt\|decrypt\|Vault"

# Logs des tâches de refresh
docker-compose logs celery-worker-sso | grep "refresh"

# Logs de rotation de clés
docker-compose logs celery-beat | grep "rotate"
```

---

## Rotation des clés de chiffrement Vault

### Principe de la rotation de clés dans Vault Transit

**Question :** Que se passe-t-il quand Vault fait une rotation de ses clés de chiffrement ?

**Réponse courte :** Les anciens tokens **restent déchiffrables** grâce au **versioning des clés** dans Vault Transit.

**Explication détaillée :**

Vault Transit utilise un système de **versioning** des clés de chiffrement :

```
Cycle de vie d'une clé de chiffrement :
┌─────────────────────────────────────────────────────────────┐
│ Création    │ Rotation #1  │ Rotation #2  │ Rotation #3   │
│ (Jour 0)    │ (Jour 30)    │ (Jour 60)    │ (Jour 90)     │
├─────────────┼──────────────┼──────────────┼───────────────┤
│ Version 1   │ Version 2    │ Version 3    │ Version 4     │
│ (active)    │ (active)     │ (active)     │ (active)      │
│             │ v1 conservée │ v1,v2 gardées│ v1,v2,v3 OK   │
└─────────────┴──────────────┴──────────────┴───────────────┘

Tokens stockés :
- User A (créé Jour 0)  : vault:v1:ABC...  ✅ Toujours déchiffrable
- User B (créé Jour 35) : vault:v2:DEF...  ✅ Toujours déchiffrable
- User C (créé Jour 65) : vault:v3:GHI...  ✅ Toujours déchiffrable
- User D (créé Jour 95) : vault:v4:JKL...  ✅ Déchiffré avec v4 (actuelle)
```

**Caractéristiques importantes :**

1. **Pas de perte de données** : Les tokens chiffrés avec v1, v2, v3 restent déchiffrables
2. **Nouveaux chiffrements** : Utilisent automatiquement la dernière version (v4)
3. **Transparence** : L'application n'a rien à changer, Vault gère le versioning
4. **Sécurité renforcée** : Limiter l'exposition en cas de compromission d'une version

---

### Configuration de la rotation automatique

#### Dans VaultEncryptionService (ligne 101-108)

La rotation est configurée **lors de la création de la clé** :

```python
# Configuration auto-rotation (optionnel)
self.client.secrets.transit.configure_key(
    name=key_name,
    mount_point=self.transit_mount,
    min_decryption_version=1,
    min_encryption_version=0,
    auto_rotate_period='30d'  # Rotation automatique tous les 30 jours
)
```

**Paramètres importants :**
- `auto_rotate_period='30d'` : Vault crée automatiquement une nouvelle version tous les 30 jours
- `min_decryption_version=1` : Toutes les versions depuis v1 peuvent déchiffrer
- `min_encryption_version=0` : Utilise toujours la dernière version pour chiffrer

#### Vérifier la configuration d'une clé

```bash
# Voir les détails d'une clé de tenant
docker-compose exec vault vault read transit/keys/azure-tokens-<tenant-id>

# Sortie attendue :
# Key                       Value
# ---                       -----
# allow_plaintext_backup    false
# auto_rotate_period        720h0m0s (30 days)
# deletion_allowed          false
# derived                   false
# exportable                false
# latest_version            3          ← Version actuelle
# min_decryption_version    1          ← Peut déchiffrer depuis v1
# min_encryption_version    0          ← Chiffre avec latest
# name                      azure-tokens-<tenant-id>
# supports_decryption       true
# supports_derivation       false
# supports_encryption       true
# supports_signing          false
# type                      aes256-gcm96
```

---

### Opération de rewrap (re-chiffrement)

#### Pourquoi faire du rewrap ?

**Problème :** Après plusieurs rotations, certains tokens sont encore chiffrés avec de très anciennes versions (v1, v2).

**Risque :** Si une ancienne version de clé est compromise, tous les tokens chiffrés avec cette version sont vulnérables.

**Solution :** **Rewrap** = re-chiffrer les tokens avec la dernière version **sans jamais les déchiffrer en clair**.

**Avantage de Vault Transit :**
```
Rewrap traditionnel (déchiffrer + chiffrer) :
Token (vault:v1:ABC) → Déchiffrement → Token clair ⚠️ → Chiffrement → Token (vault:v4:XYZ)
                        ↑ RISQUE : token exposé en mémoire

Rewrap Vault (opération atomique) :
Token (vault:v1:ABC) → Vault rewrap API → Token (vault:v4:XYZ)
                        ✅ Token jamais exposé en clair
```

#### Tâche Celery automatique : rotate_encryption_keys

**Fréquence :** Mensuelle (tous les 30 jours)

**Actions :**
1. Pour chaque tenant avec SSO activé :
   - Rotate la clé de chiffrement (crée une nouvelle version)
   - Liste tous les `UserAzureIdentity` du tenant
   - Rewrap tous les tokens avec la nouvelle version
   - Met à jour en base de données

**Code de la tâche** (backend/app/tasks/sso_tasks.py:166-235) :

```python
@celery_app.task(name='app.tasks.sso_tasks.rotate_encryption_keys')
def rotate_encryption_keys() -> Dict[str, Any]:
    """
    Rotate Vault encryption keys for enhanced security.

    This task runs monthly and rotates the encryption keys used for
    storing SSO tokens, then re-encrypts existing tokens with the new key.
    """
    vault_service = VaultEncryptionService()
    sso_configs = TenantSSOConfig.query.filter_by(is_enabled=True).all()

    results = {
        'rotated_tenants': 0,
        'rewrapped_tokens': 0,
        'total_tenants': len(sso_configs)
    }

    for config in sso_configs:
        tenant_id = str(config.tenant_id)

        # 1. Rotate the encryption key for this tenant
        vault_service.rotate_encryption_key(tenant_id)

        # 2. Re-wrap all tokens for this tenant
        identities = UserAzureIdentity.query.filter_by(
            tenant_id=config.tenant_id
        ).all()

        for identity in identities:
            if identity.encrypted_access_token:
                tokens_to_rewrap = [
                    identity.encrypted_access_token,
                    identity.encrypted_refresh_token,
                    identity.encrypted_id_token
                ]

                rewrapped = vault_service.rewrap_tokens(tenant_id, tokens_to_rewrap)

                identity.encrypted_access_token = rewrapped[0]
                identity.encrypted_refresh_token = rewrapped[1]
                identity.encrypted_id_token = rewrapped[2]

                results['rewrapped_tokens'] += 1

        results['rotated_tenants'] += 1

    db.session.commit()
    return results
```

---

### Impact sur les utilisateurs et sessions

#### Pendant la rotation (aucun impact ❌)

**Question :** Les utilisateurs sont-ils déconnectés lors de la rotation ?

**Réponse :** **Non, aucun impact !**

**Explication :**

```
Timeline de rotation (exemple) :
┌─────────────────────────────────────────────────────┐
│ 10:00 - Rotation démarre (Celery task)             │
│   ├─ Tenant A : rotate key v2 → v3                 │
│   ├─ Tenant A : rewrap 50 tokens (v2 → v3)         │
│   ├─ Tenant B : rotate key v1 → v2                 │
│   └─ Tenant B : rewrap 120 tokens (v1 → v2)        │
│                                                      │
│ 10:05 - Rotation terminée                           │
└─────────────────────────────────────────────────────┘

Pendant cette période :
- User123 fait une requête API → ✅ Fonctionne (token v2 déchiffrable)
- User456 refresh son token   → ✅ Fonctionne (nouveau token en v3)
- User789 se login via SSO     → ✅ Fonctionne (nouveau token en v3)

Aucune interruption de service !
```

**Pourquoi ça fonctionne ?**
1. Vault garde les anciennes versions disponibles
2. Le rewrap est **instantané** (< 10ms par token)
3. Les tokens ne changent pas de valeur déchiffrée (juste le format vault:vX:...)
4. L'application détecte automatiquement la version

#### Après la rotation (performance améliorée ✅)

**Avantage :** Tous les tokens utilisent la dernière version de clé (plus sécurisé)

---

### Scénarios de rotation

#### Scénario 1 : Rotation automatique (recommandée)

**Configuration :** Déjà en place avec `auto_rotate_period='30d'`

**Timeline :**
```
Jour 0  : Clé créée (v1)
Jour 30 : Vault auto-rotate → v2 créée
Jour 31 : Celery task rewrap tous les tokens
Jour 60 : Vault auto-rotate → v3 créée
Jour 61 : Celery task rewrap tous les tokens
...
```

**Aucune action manuelle requise** ✅

#### Scénario 2 : Rotation manuelle (urgence)

**Cas d'usage :** Suspicion de compromission d'une clé

**Procédure :**

```bash
# 1. Rotation manuelle immédiate via Celery
docker-compose exec api python -c "
from app.tasks.sso_tasks import rotate_encryption_keys
result = rotate_encryption_keys.delay()
print(f'Task ID: {result.id}')
print('Check Flower: http://localhost:5555')
"

# 2. Vérifier la progression dans Flower
open http://localhost:5555

# 3. Vérifier les nouvelles versions de clés
docker-compose exec vault vault read transit/keys/azure-tokens-<tenant-id>
# latest_version devrait avoir augmenté

# 4. Vérifier les logs
docker-compose logs celery-worker-sso | grep "rotate"

# Sortie attendue :
# Rotated keys for tenant <tenant-id>
# Rewrapped 150 tokens for tenant <tenant-id>
```

#### Scénario 3 : Rotation avec minimum version

**Cas d'usage :** Forcer l'abandon des anciennes versions de clés

**ATTENTION** : Cette opération peut rendre des tokens indéchiffrables si mal exécutée !

```bash
# 1. D'abord, rewrap TOUS les tokens (via Celery task)
docker-compose exec api python -c "
from app.tasks.sso_tasks import rotate_encryption_keys
rotate_encryption_keys.delay()
"

# 2. Attendre la fin du rewrap (vérifier dans Flower)

# 3. Configurer min_decryption_version pour forcer l'abandon de v1
docker-compose exec vault vault write transit/keys/azure-tokens-<tenant-id>/config \
    min_decryption_version=2

# Résultat : Les tokens en vault:v1:... ne seront PLUS déchiffrables
# Les utilisateurs concernés devront se ré-authentifier

# 4. Vérifier qu'aucun token v1 ne reste en base
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT COUNT(*)
FROM user_azure_identities
WHERE encrypted_access_token LIKE 'vault:v1:%';
"
# Doit retourner 0
```

**⚠️ Recommandation :** Ne jamais augmenter `min_decryption_version` sans avoir rewrap tous les tokens avant.

---

### Monitoring de la rotation

#### Vérifier l'historique des rotations

```bash
# Voir toutes les versions d'une clé
docker-compose exec vault vault read transit/keys/azure-tokens-<tenant-id>

# Sortie :
# Key                       Value
# ---                       -----
# keys                      map[1:1699876543 2:1702468543 3:1705060543]
#                               ↑ timestamp      ↑ timestamp    ↑ timestamp
# latest_version            3

# Les timestamps montrent quand chaque version a été créée
```

#### Vérifier la distribution des versions en base

```bash
# Analyse des versions de tokens en base de données
docker-compose exec postgres psql -U postgres -d saas_platform -c "
SELECT
    SUBSTRING(encrypted_access_token FROM 'vault:v([0-9]+):') as key_version,
    COUNT(*) as token_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM user_azure_identities
WHERE encrypted_access_token LIKE 'vault:v%'
GROUP BY key_version
ORDER BY key_version DESC;
"

# Exemple de sortie après plusieurs rotations :
#  key_version | token_count | percentage
# -------------+-------------+------------
#  4           |         850 |      68.00  ← Dernière rotation (la plupart)
#  3           |         320 |      25.60  ← Avant-dernière rotation
#  2           |          70 |       5.60  ← Il y a 2 mois
#  1           |          10 |       0.80  ← Utilisateurs inactifs depuis longtemps
```

**Interprétation :**
- **Bonne distribution** : Majorité des tokens (> 80%) sur la dernière version
- **Mauvaise distribution** : Beaucoup de tokens sur anciennes versions → Rewrap nécessaire

#### Alertes recommandées

**Alertes à configurer :**

1. **Échec de rotation** :
   - Trigger : Task Celery `rotate_encryption_keys` échoue
   - Action : Notification équipe SRE

2. **Rewrap incomplet** :
   - Trigger : > 20% des tokens sur versions > 2 versions en retard
   - Action : Forcer rewrap manuel

3. **Vault inaccessible pendant rotation** :
   - Trigger : Vault health check échoue pendant la fenêtre de rotation
   - Action : Retry automatique + alerte

**Configuration d'alertes (exemple avec logs) :**

```python
# Dans app/tasks/sso_tasks.py (à ajouter)
@celery_app.task
def check_token_version_distribution():
    """Alerte si trop de tokens sur anciennes versions"""

    # Compter tokens par version
    version_counts = db.session.execute("""
        SELECT
            SUBSTRING(encrypted_access_token FROM 'vault:v([0-9]+):') as version,
            COUNT(*) as count
        FROM user_azure_identities
        WHERE encrypted_access_token LIKE 'vault:v%'
        GROUP BY version
    """).fetchall()

    if not version_counts:
        return

    latest_version = max(int(v[0]) for v in version_counts)
    total = sum(v[1] for v in version_counts)
    old_tokens = sum(v[1] for v in version_counts if int(v[0]) < latest_version - 1)

    old_percentage = (old_tokens / total) * 100 if total > 0 else 0

    if old_percentage > 20:
        logger.warning(
            f"Token version alert: {old_percentage:.1f}% of tokens "
            f"are using versions older than v{latest_version - 1}. "
            f"Consider running rewrap task."
        )
```

---

### Politique de conservation des versions

#### Configuration par défaut (recommandée)

```python
# Dans VaultEncryptionService.ensure_encryption_key()
self.client.secrets.transit.configure_key(
    name=key_name,
    mount_point=self.transit_mount,
    min_decryption_version=1,      # Garder toutes les versions
    min_encryption_version=0,      # Toujours utiliser latest
    auto_rotate_period='30d'       # Rotation tous les 30 jours
)
```

**Avantages :**
- ✅ Aucun token perdu (toutes versions déchiffrables)
- ✅ Rotation régulière pour sécurité
- ✅ Rewrap automatique via Celery

#### Configuration stricte (haute sécurité)

**Cas d'usage :** Environnements hautement régulés (finance, santé)

```python
# Configuration plus stricte (à modifier dans VaultEncryptionService)
self.client.secrets.transit.configure_key(
    name=key_name,
    mount_point=self.transit_mount,
    min_decryption_version=None,   # Calculé dynamiquement (latest - 2)
    min_encryption_version=0,
    auto_rotate_period='7d'        # Rotation hebdomadaire
)

# Script Celery pour ajuster min_decryption_version après chaque rotation
@celery_app.task
def update_min_decryption_version():
    """Garde seulement les 3 dernières versions"""
    for tenant in get_all_sso_tenants():
        key_info = vault.read(f"transit/keys/azure-tokens-{tenant.id}")
        latest = key_info['latest_version']

        # Garder seulement les 3 dernières versions
        min_version = max(1, latest - 2)

        vault.write(
            f"transit/keys/azure-tokens-{tenant.id}/config",
            min_decryption_version=min_version
        )
```

**⚠️ Risque :** Les utilisateurs inactifs depuis > 3 rotations devront se ré-authentifier.

---

### FAQ sur la rotation

#### Q: Quelle est la différence entre rotation et rewrap ?

**Rotation :** Crée une **nouvelle version** de la clé dans Vault (v1 → v2)
**Rewrap :** Re-chiffre les tokens existants avec la nouvelle version

```
Sans rewrap :                    Avec rewrap :
Rotation v1→v2                   Rotation v1→v2
├─ Anciens tokens: vault:v1:..  ├─ Anciens tokens: vault:v2:.. (rewrappés)
└─ Nouveaux tokens: vault:v2:..  └─ Nouveaux tokens: vault:v2:..

Sécurité : Moyenne               Sécurité : Maximale
(mix de versions)                (tous sur dernière version)
```

#### Q: Combien de versions de clés garder ?

**Recommandation :** Minimum **3 versions** (90 jours avec rotation tous les 30j)

**Raisons :**
- Utilisateurs peuvent être inactifs pendant 2-3 mois
- Permet de récupérer d'un problème de rewrap
- Conformité avec politiques de rétention

**Maximum :** Illimité (mais > 10 versions = complexité de gestion)

#### Q: Que se passe-t-il si le rewrap échoue ?

**Scénario :** La tâche Celery `rotate_encryption_keys` échoue en plein milieu

**Impact :**
- Tokens déjà rewrappés : OK (vault:v2:...)
- Tokens non encore rewrappés : OK aussi (vault:v1:... toujours déchiffrables)
- **Aucune perte de données**

**Résolution :**
```bash
# 1. Vérifier les logs
docker-compose logs celery-worker-sso | grep "rotate"

# 2. Re-lancer la tâche manuellement
docker-compose exec api python -c "
from app.tasks.sso_tasks import rotate_encryption_keys
rotate_encryption_keys.delay()
"

# 3. Les tokens déjà rewrappés sont ignorés (idempotent)
```

#### Q: Peut-on désactiver la rotation automatique ?

**Oui, mais déconseillé en production.**

**Procédure :**
```bash
# Désactiver auto-rotation pour un tenant
docker-compose exec vault vault write \
    transit/keys/azure-tokens-<tenant-id>/config \
    auto_rotate_period=0

# Vérifier
docker-compose exec vault vault read transit/keys/azure-tokens-<tenant-id>
# auto_rotate_period devrait être "0s"
```

**Conséquences :**
- ❌ Exposition prolongée avec la même version de clé
- ❌ Non-conforme aux bonnes pratiques de sécurité
- ❌ Augmente le risque en cas de compromission

**Recommandation :** Garder la rotation activée (30 jours minimum)

#### Q: La rotation consomme-t-elle beaucoup de ressources ?

**Impact système :**
- **CPU** : Faible (~1-2% pendant la tâche)
- **Mémoire** : Faible (~50-100 MB)
- **Base de données** : Modéré (UPDATE de tous les tokens)
- **Vault** : Faible (opération native optimisée)

**Durée estimée :**
- 1000 tokens : ~10 secondes
- 10 000 tokens : ~1-2 minutes
- 100 000 tokens : ~15-20 minutes

**Optimisation :**
```python
# Traitement par batch pour gros volumes (à implémenter si nécessaire)
BATCH_SIZE = 1000
for i in range(0, total_identities, BATCH_SIZE):
    batch = identities[i:i+BATCH_SIZE]
    # Rewrap batch
    # Commit batch
    db.session.commit()
```

---

## Sécurité et bonnes pratiques

### ✅ Ce qui est bien
- **Sécurité par défaut** : chiffrement automatique en production
- **Isolation par tenant** : une clé par tenant
- **Rotation automatique** des clés tous les 30 jours
- **Clés non exportables** de Vault
- **Fallback gracieux** en cas de problème Vault
- **Rétrocompatibilité** avec tokens existants
- **Flexibilité** : peut être testé en développement

### ⚠️ Points d'attention
- S'assurer que Vault est **hautement disponible** en production
- **Sauvegarder les clés Vault** (Vault backup policy)
- **Monitorer les erreurs** de déchiffrement (alertes)
- Prévoir une **procédure de disaster recovery** si Vault est perdu
- Ne **jamais désactiver** le chiffrement en production avec `USE_VAULT_TOKEN_ENCRYPTION=false`

### 🔒 Sécurité renforcée (production)
- Activer l'**audit logging** de Vault
- Configurer des **politiques d'accès strictes** aux clés Transit
- Utiliser Vault en mode **HA** (High Availability)
- Configurer le **storage backend** Vault (Consul, PostgreSQL, etc.)
- Activer **TLS** pour toutes les communications avec Vault
- Configurer des **alertes** sur les échecs de chiffrement/déchiffrement

---

## Dépannage (Troubleshooting)

### Problème : "Vault client not authenticated"

**Cause :** Le token Vault a expiré ou les credentials AppRole sont invalides.

**Solution :**
```bash
# Vérifier les credentials Vault
docker-compose exec api env | grep VAULT

# Re-générer le token Vault
docker-compose restart vault-init
```

### Problème : "Transit Engine not enabled"

**Cause :** Le Transit Engine n'a pas été activé dans Vault.

**Solution :**
```bash
# Activer Transit Engine
docker-compose exec vault vault secrets enable transit

# Vérifier
docker-compose exec vault vault secrets list
```

### Problème : "Token decryption failed"

**Cause possible :** Version de clé trop ancienne ou clé supprimée.

**Solution :**
```bash
# Vérifier l'état de la clé
docker-compose exec vault vault read transit/keys/azure-tokens-<tenant_id>

# Si la clé a été supprimée, re-créer et forcer re-auth SSO
```

### Problème : Tokens stockés en "dev:" malgré FLASK_ENV=production

**Cause :** Vault non accessible ou erreur de configuration.

**Solution :**
```bash
# Vérifier les logs
docker-compose logs api | grep -i "vault encryption failed"

# Vérifier la connectivité Vault
docker-compose exec api curl -v http://vault:8200/v1/sys/health

# Vérifier la configuration
docker-compose exec api python -c "
from app import create_app
app = create_app()
with app.app_context():
    print(f'FLASK_ENV: {app.config.get(\"FLASK_ENV\")}')
    print(f'USE_VAULT_TOKEN_ENCRYPTION: {app.config.get(\"USE_VAULT_TOKEN_ENCRYPTION\")}')
"
```

### Problème : "Vault token found but encryption is disabled"

**Cause :** Tokens au format `vault:v1:` mais chiffrement désactivé (FLASK_ENV=development sans USE_VAULT_TOKEN_ENCRYPTION=true).

**Solution :**
```bash
# Option 1 : Activer le chiffrement
export USE_VAULT_TOKEN_ENCRYPTION=true
docker-compose restart api

# Option 2 : Passer en production
export FLASK_ENV=production
docker-compose restart api
```

---

## Résumé des fichiers à modifier

| Fichier | Modifications | Priorité |
|---------|---------------|----------|
| `backend/app/config.py` | Ajouter `USE_VAULT_TOKEN_ENCRYPTION` (optionnelle) | 🔴 Haute |
| `backend/app/models/user_azure_identity.py` | Modifier `save_tokens()` et `get_decrypted_tokens()` avec logique combinée | 🔴 Haute |
| `backend/app/services/tenant_sso_config_service.py` | Créer clés Vault dans `create_sso_config()` avec logique combinée | 🔴 Haute |
| `backend/scripts/migrate_tokens_to_vault.py` | Créer script de migration avec détection automatique | 🟡 Moyenne |
| `.env.docker.minimal` | Documenter la variable (optionnelle, automatique en prod) | 🟡 Moyenne |
| `.env.docker` | Ajouter la variable avec documentation | 🟡 Moyenne |
| `CLAUDE.md` | Documenter la fonctionnalité + matrice de décision | 🟡 Moyenne |
| `backend/tests/unit/test_vault_token_encryption.py` | Tests unitaires avec scénarios FLASK_ENV | 🟢 Basse |
| `backend/tests/integration/test_sso_token_lifecycle.py` | Tests d'intégration | 🟢 Basse |

---

## Estimation d'effort

- **Configuration et intégration de base :** 2-3 heures
- **Script de migration :** 1-2 heures
- **Tests :** 2-3 heures
- **Documentation :** 1 heure
- **Total :** 6-9 heures de développement

---

## Prochaines étapes recommandées

1. ✅ Implémenter les modifications dans `UserAzureIdentity` avec logique combinée
2. ✅ Ajouter la variable de configuration (optionnelle)
3. ✅ Intégrer dans `tenant_sso_config_service` avec logique combinée
4. ✅ Créer le script de migration avec détection automatique
5. ✅ Écrire les tests (incluant scénarios FLASK_ENV)
6. ✅ Mettre à jour la documentation avec matrice de décision
7. ✅ Tester en environnement de développement (avec et sans chiffrement)
8. ✅ Déployer en production (chiffrement automatique)
9. ✅ Migrer les tokens existants si nécessaire

---

## FAQ

### Q: Dois-je définir USE_VAULT_TOKEN_ENCRYPTION en production ?

**R:** Non, ce n'est **pas nécessaire**. En `FLASK_ENV=production`, le chiffrement est activé automatiquement pour la sécurité. La variable `USE_VAULT_TOKEN_ENCRYPTION` est principalement utile pour :
- Tester le chiffrement en développement (`USE_VAULT_TOKEN_ENCRYPTION=true`)
- Désactiver exceptionnellement en production (`USE_VAULT_TOKEN_ENCRYPTION=false`) - **non recommandé**

### Q: Comment tester le chiffrement Vault avant de passer en production ?

**R:** En développement, activez explicitement le chiffrement :
```bash
FLASK_ENV=development
USE_VAULT_TOKEN_ENCRYPTION=true
```

### Q: Que se passe-t-il si Vault tombe en panne en production ?

**R:** La logique de fallback entre en jeu :
- Les **nouveaux tokens** seront stockés en mode `dev:` (warning dans les logs)
- Les **tokens existants** en format `vault:v1:` ne pourront pas être déchiffrés
- Les utilisateurs devront se **ré-authentifier**
- Restaurez Vault rapidement pour minimiser l'impact

### Q: Puis-je migrer progressivement (mix de tokens dev: et vault:v1:) ?

**R:** Oui ! Le système gère automatiquement les deux formats :
- Détection automatique du format de chaque token
- Pas besoin de tout migrer d'un coup
- Les sessions existantes continuent de fonctionner

### Q: Comment vérifier que le chiffrement est bien activé ?

**R:**
```bash
# Vérifier les logs au démarrage
docker-compose logs api | grep -E "production mode|USE_VAULT_TOKEN_ENCRYPTION"

# Faire un login SSO et vérifier le format des tokens
docker-compose exec postgres psql -U postgres -d saas_platform -c \
  "SELECT LEFT(encrypted_access_token, 20) FROM user_azure_identities ORDER BY created_at DESC LIMIT 1;"

# Devrait afficher: vault:v1:...
```
