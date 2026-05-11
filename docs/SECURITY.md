# Modèle de sécurité

Ce document décrit les mécanismes de sécurité du backend SaaS multi-tenant.  
Pour l'architecture générale, voir [ARCHITECTURE.md](ARCHITECTURE.md).  
Pour le schéma des bases de données, voir [DATABASES.md](DATABASES.md).

---

## Table des matières

1. [Authentification — JWT](#1-authentification--jwt)
2. [Autorisation — RBAC](#2-autorisation--rbac)
3. [Isolation multi-tenant](#3-isolation-multi-tenant)
4. [Gestion des secrets — Vault](#4-gestion-des-secrets--vault)
5. [Chiffrement des données](#5-chiffrement-des-données)
6. [Sécurité des fichiers S3](#6-sécurité-des-fichiers-s3)
7. [SSO Azure AD](#7-sso-azure-ad)
8. [Sécurité applicative](#8-sécurité-applicative)
9. [Surface d'attaque connue et mitigations](#9-surface-dattaque-connue-et-mitigations)

---

## 1. Authentification — JWT

### Tokens

| Type | Durée | Stockage côté serveur |
|---|---|---|
| Access token | 15 minutes | Stateless (non stocké) |
| Refresh token | 7 jours | Blacklist en mémoire (dev) / Redis (prod) |

### Flux d'authentification

```
POST /api/auth/login
  → vérification email + bcrypt(password)
  → retourne {access_token, refresh_token}

POST /api/auth/refresh
  → vérifie refresh_token (non blacklisté)
  → retourne nouveau access_token

POST /api/auth/logout
  → ajoute jti du refresh_token à la blacklist
```

### Blacklist des tokens

- **Développement** : `set` Python en mémoire — réinitialisé au redémarrage du process. Acceptable uniquement en dev.
- **Production requise** : Redis avec TTL égal à l'expiration du token (`SETEX jti <ttl> "blacklisted"`). Voir [backend/app/services/auth_service.py](../backend/app/services/auth_service.py).

### Hachage des mots de passe

bcrypt avec `rounds=12` (production) / `rounds=4` (tests). Les utilisateurs SSO-only ont `password_hash = NULL`.

---

## 2. Autorisation — RBAC

### Hiérarchie des rôles (par tenant)

```
admin  >  user  >  viewer
  3         2         1       (niveau numérique dans has_permission())
```

| Rôle | Permissions |
|---|---|
| `admin` | CRUD complet sur toutes les ressources du tenant, gestion des utilisateurs |
| `user` | Créer, lire, modifier ses propres ressources ; lire celles des autres |
| `viewer` | Lecture seule |

### Application des droits — décorateurs

Définis dans [backend/app/utils/decorators.py](../backend/app/utils/decorators.py).

```python
@app.route('/api/tenants/<tenant_id>/...')
@jwt_required_custom          # 1. Valide le JWT + vérifie la blacklist
@tenant_required              # 2. Vérifie l'appartenance au tenant → set g.user_role
@role_required(['admin'])     # 3. Vérifie le niveau de rôle requis
def ma_route(tenant_id): ...
```

`g.user_id`, `g.tenant_id`, `g.user_role` sont injectés dans le contexte Flask à chaque requête authentifiée.

### Limites actuelles

- La sécurité au niveau des lignes (row-level security) n'est pas appliquée automatiquement dans les services — les filtres `user_id` sont optionnels et laissés à la discrétion du caller.
- Le décorateur `@tenant_required` doit être vérifié : s'assurer qu'il interroge bien `UserTenantAssociation` en base et ne retourne pas un rôle en dur (voir `TODO` dans le fichier).

---

## 3. Isolation multi-tenant

### Architecture deux niveaux

```
Base principale (saas_platform)
  └── users, tenants, user_tenant_associations
  └── tenant_sso_configs, user_azure_identities

Base tenant (tenant_<slug>_<uuid>)  — une par tenant
  └── files, documents
  └── [Nouveau] object_definitions, field_definitions, object_records, ...
```

### Garanties d'isolation

| Garantie | Mécanisme |
|---|---|
| Données séparées | Bases PostgreSQL distinctes par tenant |
| Connexions séparées | `TenantDatabaseManager` crée un engine SQLAlchemy par base |
| Pas de FK cross-tenant | Les références cross-DB (ex: `document.user_id`) sont des UUID sans contrainte FK |
| Nommage déterministe | `tenant_{slug}_{uuid4_8chars}` — collision improbable |

### Vecteur de risque principal

Une faille dans la résolution du `tenant_id` (ex: IDOR sur un UUID prévisible) permettrait l'accès aux données d'un autre tenant. Toute route exposant des données tenant doit valider `UserTenantAssociation` **en base**, pas seulement dans le JWT.

---

## 4. Gestion des secrets — Vault

### Modes de fonctionnement

| Mode | Variable | Usage |
|---|---|---|
| Avec Vault | `USE_VAULT=true` | Production — secrets chargés depuis HashiCorp Vault |
| Sans Vault | `USE_VAULT=false` | Développement — secrets depuis `.env` |

### Chemins Vault

```
secret/saas-project/{environment}/
  ├── database_url
  ├── jwt_secret_key
  ├── s3_access_key / s3_secret_key
  └── azure_client_secret (par tenant SSO)
```

### Authentification AppRole

Le backend s'authentifie à Vault via AppRole (`role_id` + `secret_id`). Le token Vault est renouvelé automatiquement avant expiration.

### Commandes Flask

En mode Vault, **toutes les commandes Flask doivent passer par le wrapper** :
```bash
docker-compose exec api /app/flask-wrapper.sh db migrate -m "..."
```
Sans le wrapper, `VAULT_ADDR` et les secrets ne sont pas chargés.

---

## 5. Chiffrement des données

### Mots de passe utilisateurs

bcrypt via `flask-bcrypt`. Jamais stockés en clair.

### Tokens Azure AD (SSO)

Les `access_token`, `refresh_token` et `id_token` Azure sont chiffrés avec le **Vault Transit Engine** avant stockage dans `user_azure_identities`. Le chiffrement est symétrique (AES-256-GCM) géré entièrement par Vault.

Voir [backend/app/services/vault_encryption_service.py](../backend/app/services/vault_encryption_service.py).

### Données tenant (files, documents)

Les données au repos dans PostgreSQL ne sont pas chiffrées au niveau applicatif (chiffrement géré par le provider d'hébergement PostgreSQL en production). Les fichiers S3 sont chiffrés côté serveur par MinIO/AWS (SSE).

---

## 6. Sécurité des fichiers S3

### Bucket privé

Le bucket MinIO est configuré en **accès privé**. Aucun fichier n'est accessible directement par URL publique.

### URLs pré-signées

```
GET /api/tenants/{id}/documents/{doc_id}/download-url
  → vérifie JWT + appartenance tenant
  → génère URL pré-signée MinIO (expiration configurable, défaut 3600s, max 86400s)
  → URL valide sans Bearer Token (utile pour email, iframe)
```

Les URLs pré-signées sont journalisées à chaque génération (audit trail).

### Déduplication MD5

La déduplication par MD5 est une optimisation de stockage, pas un mécanisme de sécurité. Un attaquant connaissant le MD5 d'un fichier ne peut pas accéder à son contenu sans JWT valide.

---

## 7. SSO Azure AD

### Mode confidentiel

L'intégration utilise le mode **application confidentielle** (client_secret requis). Le `client_secret` est chiffré dans Vault — jamais exposé dans les logs ni les réponses API.

### PKCE

Le flux OAuth2 utilise PKCE (Proof Key for Code Exchange) pour prévenir l'interception du code d'autorisation. Le `code_verifier` est stocké en Redis avec TTL court (5 minutes).

### Validation du state token

Un token `state` opaque (UUID) est généré à l'initiation du flux et vérifié au callback pour prévenir les attaques CSRF.

### Auto-provisioning

La création automatique d'utilisateurs sur première connexion SSO est contrôlée par :
- `sso_auto_provisioning` (booléen par tenant)
- `sso_domain_whitelist` (liste de domaines email autorisés)
- `group_role_mapping` (mapping groupes Azure AD → rôles SaaS)

---

## 8. Sécurité applicative

### CORS

Configuré via Flask-CORS. En développement : `localhost:3000`. En production : domaine(s) front-end explicitement listés — jamais `*` avec credentials.

### Rate limiting

Décorateur `@rate_limit` défini mais **non implémenté** (placeholder). À implémenter avec Redis avant mise en production pour les endpoints sensibles (`/login`, `/refresh`, `/register`).

### Validation des entrées

Marshmallow 3 valide tous les corps de requête aux endpoints. Les paramètres d'URL (UUIDs) sont validés par Python `uuid.UUID()` dans les services.

### Injection SQL

SQLAlchemy ORM avec requêtes paramétrées. Les requêtes SQL brutes (`text()`) utilisent systématiquement les bind parameters (`:param`) — jamais de f-strings dans les requêtes SQL.

### Headers de sécurité

Non configurés explicitement dans le code actuel. En production, ajouter via un reverse proxy (nginx) ou Flask-Talisman :
- `Strict-Transport-Security`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy`

---

## 9. Surface d'attaque connue et mitigations

| Vecteur | Risque | Mitigation en place | Action requise |
|---|---|---|---|
| Blacklist tokens en mémoire | Refresh tokens révoqués réactivés au redémarrage | Acceptable en dev | Migrer vers Redis en prod |
| `@tenant_required` placeholder | Rôle toujours `admin` si non implémenté | — | Vérifier l'implémentation DB |
| Row-level security absente | Un `user` peut lire les docs d'un autre user du même tenant | Isolation par tenant | Ajouter filtres `user_id` si requis |
| Rate limiting absent | Brute force sur `/login` | — | Implémenter avec Redis |
| Headers sécurité absents | Clickjacking, MIME sniffing | — | Ajouter Flask-Talisman ou nginx headers |
| client_secret Azure en base | Exposition si dump DB | Chiffrement Vault Transit | Rotation des secrets Azure régulière |
| Logs potentiellement verbeux | Fuite de tokens dans les logs debug | — | Vérifier niveau de log en prod (`WARNING`) |
