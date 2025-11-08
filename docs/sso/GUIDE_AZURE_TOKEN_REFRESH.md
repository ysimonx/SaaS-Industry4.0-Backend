# Guide : Refresh des Tokens Azure AD

## 📋 Vue d'ensemble

Votre application stocke deux types de tokens Azure AD pour chaque utilisateur SSO :

1. **Access Token** : Permet d'accéder aux API Microsoft (Graph, etc.)
   - Durée de vie : **1 heure** (3600 secondes)
   - Usage : Appels API vers Microsoft Graph
   - Peut être rafraîchi avec le refresh token

2. **Refresh Token** : Permet d'obtenir de nouveaux access tokens
   - Durée de vie : **90 jours** (7,776,000 secondes)
   - Usage : Rafraîchir l'access token sans ré-authentification
   - Stocké chiffré en base de données

---

## 🔍 Vérifier l'état des tokens

### Script de vérification

```bash
docker-compose exec api python scripts/check_azure_tokens.py
```

**Ce script affiche** :
- ✅ Présence des tokens (access, refresh, ID)
- ⏰ Dates d'expiration
- ⚠️ Tokens expirés ou expirant bientôt
- 📊 Résumé global

**Exemple de sortie** :
```
👤 Utilisateur: yannick.simon@fidwork.fr
   Tenant: fidwork

🔑 Tokens Azure AD:
   ✅ Access Token: Présent
      Expire dans: 0.8 heures
      Expire le: 2025-11-08 13:30:57 UTC
   ✅ Refresh Token: Présent
      Expire dans: 89.5 jours
      Expire le: 2026-02-06 11:30:57 UTC

📊 Statut:
   ✅ Tokens valides et fonctionnels
```

---

## 🔄 Tester le refresh des tokens

### Script de test manuel

```bash
docker-compose exec api python scripts/test_azure_token_refresh.py
```

**Ce script** :
1. Affiche l'état actuel des tokens
2. Demande confirmation avant le test
3. Appelle Azure AD pour rafraîchir l'access token
4. Sauvegarde les nouveaux tokens
5. Affiche le nouvel état

**Exemple d'exécution** :
```
👤 Utilisateur: yannick.simon@fidwork.fr

📊 État actuel des tokens:
   ✅ Refresh token valide (expire dans 89.5 jours)
   ⚠️  Access token expiré depuis 0.3 heures

🔄 Test du refresh token pour yannick.simon@fidwork.fr
   Continuer ? (oui/non): oui

⏳ Récupération du refresh token...
   ✅ Refresh token récupéré

⏳ Demande de nouveaux tokens à Azure AD...
   ✅ Nouveaux tokens reçus d'Azure AD!

📦 Nouveaux tokens:
   Access Token: ✅ Reçu
   Refresh Token: ⚠️ Non fourni (réutilise l'ancien)
   ID Token: ✅ Reçu
   Expires in: 3600 secondes

💾 Sauvegarde des nouveaux tokens...
   ✅ Tokens sauvegardés en base de données

📊 Nouvel état:
   Access token expire dans: 1.0 heures
   Expire le: 2025-11-08 14:45:23 UTC

✅ SUCCESS: Refresh token fonctionne correctement!
```

---

## 🤖 Refresh automatique avec Celery

Votre application inclut un système de refresh automatique des tokens via Celery.

### Architecture

```
┌─────────────┐
│ Celery Beat │ ──> Vérifie périodiquement (toutes les 30 min)
└─────────────┘
       │
       ▼
┌──────────────────┐
│ SSO Worker Tasks │ ──> Rafraîchit les tokens expirant bientôt
└──────────────────┘
       │
       ▼
┌─────────────┐
│ Azure AD    │ ──> Fournit de nouveaux tokens
└─────────────┘
```

### Services Celery

1. **celery-beat** : Planificateur qui déclenche les tâches périodiques
2. **celery-worker-sso** : Worker dédié au refresh des tokens SSO
3. **flower** : Dashboard de monitoring (http://localhost:5555)

### Démarrer les services

```bash
# Tous les services (incluant Celery)
docker-compose up -d

# Seulement les services Celery
docker-compose up -d celery-worker-sso celery-beat flower
```

### Vérifier l'état des workers

```bash
# Logs du worker SSO
docker-compose logs -f celery-worker-sso

# Logs du beat (planificateur)
docker-compose logs -f celery-beat

# Dashboard Flower
open http://localhost:5555
```

### Configuration du refresh automatique

**Fichier : `backend/app/tasks/sso_tasks.py`**

```python
@celery.task(name='refresh_expiring_azure_tokens')
def refresh_expiring_azure_tokens():
    """
    Rafraîchit les access tokens Azure AD qui expirent dans moins de 30 minutes.
    S'exécute toutes les 30 minutes via Celery Beat.
    """
    # ... logique de refresh ...
```

**Configuration Celery Beat** (dans `celery_app.py`) :
```python
app.conf.beat_schedule = {
    'refresh-expiring-azure-tokens': {
        'task': 'refresh_expiring_azure_tokens',
        'schedule': crontab(minute='*/30'),  # Toutes les 30 minutes
    },
}
```

---

## 🔧 API Endpoint pour le refresh

### Endpoint utilisateur

Les utilisateurs peuvent rafraîchir leurs propres tokens Azure AD :

```bash
POST /api/auth/sso/azure/refresh
Authorization: Bearer {refresh_token_jwt}

# Réponse
{
  "access_token": "eyJ0eXAiOiJKV1Q...",  # Nouveau JWT de l'app
  "refresh_token": "eyJ0eXAiOiJKV1Q...",
  "azure_access_token_expires_at": "2025-11-08T14:45:23Z",
  "message": "Azure AD tokens refreshed successfully"
}
```

### Tester avec curl

```bash
# 1. S'authentifier d'abord
RESPONSE=$(curl -s -X POST http://localhost:4999/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "yannick.simon@fidwork.fr",
    "password": "votre_password"
  }')

REFRESH_TOKEN=$(echo $RESPONSE | python -c "import sys, json; print(json.load(sys.stdin)['refresh_token'])")

# 2. Rafraîchir les tokens Azure AD
curl -X POST http://localhost:4999/api/auth/sso/azure/refresh \
  -H "Authorization: Bearer $REFRESH_TOKEN" | python -m json.tool
```

---

## 📊 Monitoring du refresh automatique

### Flower Dashboard

Accédez à http://localhost:5555 pour voir :
- 📈 Tâches en cours d'exécution
- ✅ Tâches réussies
- ❌ Tâches échouées
- ⏰ Prochaines exécutions planifiées

### Logs détaillés

```bash
# Voir les refresh automatiques en temps réel
docker-compose logs -f celery-worker-sso | grep -i "refresh"

# Logs attendus (toutes les 30 min)
INFO - Task refresh_expiring_azure_tokens started
INFO - Found 3 tokens expiring in the next 30 minutes
INFO - Successfully refreshed Azure tokens for yannick.simon@fidwork.fr
INFO - Task refresh_expiring_azure_tokens succeeded
```

---

## 🚨 Résolution de problèmes

### Problème : "Refresh token invalid or expired"

**Causes** :
- Le refresh token a expiré (après 90 jours)
- L'utilisateur a révoqué l'accès dans Azure AD
- Le client_secret a changé dans Azure Portal

**Solution** :
```bash
# L'utilisateur doit se ré-authentifier
# Rediriger vers :
http://localhost:4999/api/auth/sso/azure/login/{tenant_id}
```

### Problème : Celery worker ne démarre pas

**Vérifier** :
```bash
docker-compose ps celery-worker-sso

# Si "exited", voir les logs
docker-compose logs celery-worker-sso
```

**Solutions courantes** :
```bash
# Redémarrer le worker
docker-compose restart celery-worker-sso

# Reconstruire si nécessaire
docker-compose build celery-worker-sso
docker-compose up -d celery-worker-sso
```

### Problème : Tokens ne se rafraîchissent pas automatiquement

**Checklist** :
1. ✅ Celery Beat est démarré
   ```bash
   docker-compose ps celery-beat
   ```

2. ✅ Worker SSO est actif
   ```bash
   docker-compose ps celery-worker-sso
   ```

3. ✅ Redis est accessible (broker Celery)
   ```bash
   docker-compose ps redis
   ```

4. ✅ Vérifier la configuration
   ```bash
   docker-compose exec celery-worker-sso celery -A app.celery_app inspect scheduled
   ```

---

## 📈 Métriques et statistiques

### Commandes utiles

```bash
# Statistiques Celery
docker-compose exec celery-worker-sso celery -A app.celery_app inspect stats

# Tâches actives
docker-compose exec celery-worker-sso celery -A app.celery_app inspect active

# Tâches planifiées
docker-compose exec celery-worker-sso celery -A app.celery_app inspect scheduled

# Nombre de workers
docker-compose exec celery-worker-sso celery -A app.celery_app inspect active_queues
```

### Vérifier dans la base de données

```sql
-- Nombre d'utilisateurs avec tokens Azure
SELECT COUNT(*) FROM user_azure_identities
WHERE azure_refresh_token_encrypted IS NOT NULL;

-- Tokens expirant bientôt
SELECT
    u.email,
    t.name as tenant,
    uai.azure_access_token_expires_at,
    (uai.azure_access_token_expires_at - NOW()) as time_until_expiry
FROM user_azure_identities uai
JOIN users u ON u.id = uai.user_id
JOIN tenants t ON t.id = uai.tenant_id
WHERE uai.azure_access_token_expires_at < (NOW() + INTERVAL '30 minutes')
ORDER BY uai.azure_access_token_expires_at;
```

---

## 🔐 Sécurité des tokens

### Chiffrement avec Vault (Recommandé en production)

**Activez Vault** :
```bash
# Dans .env
USE_VAULT=true

# Redémarrer avec Vault
docker-compose up -d vault vault-init
docker-compose restart api celery-worker-sso
```

Les tokens Azure AD seront automatiquement chiffrés avec Vault Transit Engine.

### Rotation des refresh tokens

Azure AD peut (optionnellement) fournir un nouveau refresh token lors du refresh :
- ✅ Si fourni : Le nouveau remplace l'ancien
- ⚠️ Si non fourni : L'ancien est conservé

C'est géré automatiquement par le code.

---

## 📚 Résumé des commandes

| Action | Commande |
|--------|----------|
| Vérifier état tokens | `docker-compose exec api python scripts/check_azure_tokens.py` |
| Tester refresh | `docker-compose exec api python scripts/test_azure_token_refresh.py` |
| Voir logs worker | `docker-compose logs -f celery-worker-sso` |
| Dashboard Flower | `open http://localhost:5555` |
| Stats Celery | `docker-compose exec celery-worker-sso celery -A app.celery_app inspect stats` |

---

## ✅ Checklist pour le refresh automatique

- [ ] Celery Beat démarré
- [ ] Worker SSO actif
- [ ] Redis connecté
- [ ] Tâche planifiée visible dans Flower
- [ ] Logs montrent les refresh toutes les 30 min
- [ ] Tokens se rafraîchissent automatiquement
- [ ] Aucune erreur dans les logs

---

**Votre système de refresh Azure AD est maintenant surveillable et testable ! 🚀**