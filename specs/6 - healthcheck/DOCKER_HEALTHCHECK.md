# 🏥 Monitoring avec Healthchecks.io - Guide Complet

## 📋 Vue d'ensemble

Ce document décrit l'implémentation complète du système de monitoring avec Healthchecks.io pour le backend SaaS multi-tenant. Le système surveille automatiquement 15+ services Docker et envoie des alertes en cas de problème.

## 🚀 Démarrage Rapide

### 1. Lancer Healthchecks.io

```bash
# Méthode recommandée : Utiliser le script helper
./scripts/start-healthchecks.sh

# Ou manuellement avec les deux fichiers .env
docker-compose --env-file .env --env-file .env.healthchecks \
  -f docker-compose.healthchecks.yml up -d

# Vérifier le statut
docker-compose -f docker-compose.healthchecks.yml ps

# Accéder à l'interface
open http://localhost:8000
```

### 2. Configuration Initiale

1. **Compte administrateur par défaut** :
   - Email : `admin@example.com`
   - Password : `admin123`
   - URL de connexion : http://localhost:8000/accounts/login/
   - **Important** : Changez ce mot de passe en production !

   **Clés API configurées** :
   - API Key : `hVIB-d9ihVotUKFmoiwAKNH5JBVmra4j`
   - Read-only Key : `MoT6b6wH1mAdzuUdDiMQyvGq01ETFuzn`

2. **Obtenir les clés API** :
   - Aller dans Settings → API Access
   - Copier la Project API key
   - Mettre à jour `HEALTHCHECKS_API_KEY` dans `.env.healthchecks`

3. **Initialiser les checks** :
   ```bash
   # Exécuter le script d'initialisation
   docker-compose exec api python scripts/setup_healthchecks.py

   # Les IDs des checks seront ajoutés automatiquement à .env.healthchecks
   # Pas besoin de copier, le script helper charge tout automatiquement
   ```

4. **Redémarrer les services** :
   ```bash
   docker-compose restart api celery-worker-sso celery-beat
   ```

## 🏗️ Architecture du Système

### Services Monitorés

| Tier | Service | Intervalle | Grace Period | Criticité |
|------|---------|------------|--------------|-----------|
| **1** | PostgreSQL | 30s | 2min | Critique |
| **1** | Redis | 30s | 2min | Critique |
| **1** | Flask API | 1min | 3min | Critique |
| **1** | Celery Worker SSO | 1min | 5min | Critique |
| **1** | Celery Beat | 1min | 5min | Critique |
| **2** | Kafka | 2min | 5min | Essentiel |
| **2** | Zookeeper | 2min | 5min | Essentiel |
| **2** | MinIO | 5min | 10min | Essentiel |
| **2** | Vault | 5min | 10min | Essentiel |
| **2** | Kafka Consumer | 2min | 5min | Essentiel |

### Tâches Planifiées Surveillées

| Tâche | Schedule | Description |
|-------|----------|-------------|
| SSO Token Refresh | */15 * * * * | Rafraîchit les tokens SSO expirants |
| Health Check | */5 * * * * | Vérification de santé système |
| Token Cleanup | 0 2 * * * | Nettoyage quotidien des tokens expirés |
| Key Rotation | 0 3 1 * * | Rotation mensuelle des clés de chiffrement |

## 📁 Structure des Fichiers

```
SaaSBackendWithClaude/
├── docker-compose.healthchecks.yml     # Configuration Docker pour Healthchecks
├── plan-healthcheck.md                 # Plan détaillé d'implémentation
├── .env                                 # Variables d'environnement principales
├── .env.healthchecks                   # Variables spécifiques à Healthchecks
├── scripts/
│   └── start-healthchecks.sh          # Script helper pour démarrer Healthchecks
├── backend/
│   ├── app/
│   │   ├── monitoring/                 # Module de monitoring
│   │   │   ├── __init__.py
│   │   │   ├── healthchecks_client.py  # Client API Healthchecks
│   │   │   └── decorators.py           # Décorateurs de monitoring
│   │   ├── tasks/
│   │   │   └── monitoring_tasks.py     # Tâches Celery de monitoring
│   │   └── routes/
│   │       └── monitoring.py           # API endpoints de monitoring
│   └── scripts/
│       └── setup_healthchecks.py       # Script d'initialisation
```

## 🔧 Configuration

### Variables d'Environnement

La configuration est divisée en deux fichiers :

**Dans `.env` (principal)** :
```bash
# Active le monitoring dans l'application
HEALTHCHECKS_ENABLED=true
```

**Dans `.env.healthchecks` (dédié)** :
```bash
# Configuration de base
HEALTHCHECKS_API_URL=http://healthchecks:8000/api/v1
HEALTHCHECKS_API_KEY=your-project-api-key-here

# Base de données Healthchecks
HEALTHCHECKS_DB_NAME=healthchecks
HEALTHCHECKS_DB_USER=healthchecks
HEALTHCHECKS_DB_PASSWORD=healthchecks_secure_password_change_me

# Alertes (optionnel)
HEALTHCHECKS_SLACK_ENABLED=False
HEALTHCHECKS_SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ

# IDs des checks (générés par setup_healthchecks.py)
HC_CHECK_POSTGRES=abc12345-6789-def0-1234-567890abcdef
HC_CHECK_REDIS=bcd23456-7890-ef01-2345-678901bcdef0
# ... etc
```

### Docker Compose

Le service Healthchecks utilise sa propre base PostgreSQL et est complètement isolé :

```yaml
services:
  healthchecks:
    image: healthchecks/healthchecks:v2.10
    ports:
      - "8000:8000"  # Interface Web
      - "8001:8001"  # SMTP pour email pings
    depends_on:
      - healthchecks-db

  healthchecks-db:
    image: postgres:13-alpine
    volumes:
      - healthchecks-db-data:/var/lib/postgresql/data
```

## 🔌 API Endpoints de Monitoring

| Endpoint | Méthode | Description | Auth Required |
|----------|---------|-------------|---------------|
| `/api/monitoring/health` | GET | Health check basique | Non |
| `/api/monitoring/status` | GET | Statut complet du monitoring | Admin |
| `/api/monitoring/check/<service>` | GET | Vérifier un service spécifique | User |
| `/api/monitoring/check/all` | GET | Check complet de tous les services | Admin |
| `/api/monitoring/checks` | GET | Lister tous les checks configurés | Admin |
| `/api/monitoring/checks/<id>/pause` | POST | Mettre en pause un check | Admin |
| `/api/monitoring/checks/<id>/resume` | POST | Reprendre un check | Admin |
| `/api/monitoring/dashboard` | GET | Données pour dashboard | User |

### Exemples d'Utilisation

```bash
# Obtenir le statut global
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:4999/api/monitoring/status

# Vérifier PostgreSQL
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:4999/api/monitoring/check/postgres

# Lancer un check complet
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:4999/api/monitoring/check/all

# Obtenir les données du dashboard
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:4999/api/monitoring/dashboard
```

## 🎯 Utilisation des Décorateurs

### Monitoring de Tâches

```python
from app.monitoring.decorators import monitor_task

@monitor_task(check_name='data-processing')
def process_data():
    # Votre code ici
    pass
```

### Monitoring de Tâches Celery

```python
from app.monitoring.decorators import monitor_celery_task

@celery.task
@monitor_celery_task(check_name='async-processing')
def async_task():
    # Votre code ici
    pass
```

### Monitoring de Tâches Planifiées

```python
from app.monitoring.decorators import monitor_scheduled_task

@celery.task
@monitor_scheduled_task(
    schedule="0 2 * * *",
    check_name="daily-backup",
    grace=7200
)
def daily_backup():
    # Votre code ici
    pass
```

## 🔔 Configuration des Alertes

### 1. Email (dans Healthchecks UI)

1. Aller dans **Settings** → **Email**
2. Configurer SMTP si nécessaire
3. Ajouter les adresses email de destination

### 2. Slack

1. Créer un Webhook Slack : https://api.slack.com/messaging/webhooks
2. Ajouter le webhook dans `.env` :
   ```bash
   HEALTHCHECKS_SLACK_ENABLED=True
   HEALTHCHECKS_SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
   ```
3. Dans Healthchecks UI : **Integrations** → **Add Slack**

### 3. PagerDuty (Production)

1. Obtenir une Integration Key depuis PagerDuty
2. Dans Healthchecks UI : **Integrations** → **Add PagerDuty**
3. Configurer les règles d'escalade

## 📊 Dashboard et Métriques

### Accès au Dashboard Healthchecks

- URL : http://localhost:8000
- Visualisation en temps réel de tous les checks
- Historique des incidents
- Graphiques de disponibilité

### Métriques Disponibles via l'API

```json
{
  "health_percentage": 95.5,
  "summary": {
    "total_checks": 14,
    "healthy": 13,
    "down": 1,
    "paused": 0
  },
  "recent_failures": [
    {
      "name": "Kafka Consumer",
      "last_ping": "2024-11-16T13:45:00Z",
      "status": "down"
    }
  ]
}
```

## 🐛 Troubleshooting

### Healthchecks ne démarre pas

```bash
# Vérifier les logs
docker-compose -f docker-compose.healthchecks.yml logs healthchecks

# Vérifier que les valeurs boolean sont en majuscules
grep SLACK_ENABLED .env.healthchecks  # Doit être "True" ou "False", pas "true"/"false"

# Vérifier que les deux fichiers .env sont chargés
./scripts/start-healthchecks.sh logs

# Recréer les containers
./scripts/start-healthchecks.sh down
./scripts/start-healthchecks.sh up -d
```

### Les checks ne reçoivent pas de pings

```bash
# Vérifier la configuration dans le container API
docker-compose exec api python -c "
from app.monitoring.healthchecks_client import healthchecks
print('Enabled:', healthchecks.enabled)
print('API URL:', healthchecks.api_url)
print('API Key set:', bool(healthchecks.api_key))
"

# Tester manuellement un ping
curl http://localhost:8000/ping/{check_id}
```

### Fausses alertes fréquentes

1. Augmenter la grace period dans le script `setup_healthchecks.py`
2. Ajuster les intervalles dans `celery_app.py`
3. Vérifier les ressources des containers
4. Examiner les logs pour identifier des patterns

## 🔄 Maintenance

### Sauvegarder la Configuration

```bash
# Backup de la base Healthchecks
docker-compose exec healthchecks-db \
  pg_dump -U healthchecks healthchecks > healthchecks_backup.sql

# Exporter la configuration des checks
docker-compose exec api python -c "
from app.monitoring.healthchecks_client import healthchecks
import json
checks = healthchecks.list_checks()
print(json.dumps(checks, indent=2))
" > checks_config.json
```

### Mettre à Jour Healthchecks

```bash
# Arrêter les services
docker-compose -f docker-compose.healthchecks.yml down

# Mettre à jour l'image
docker-compose -f docker-compose.healthchecks.yml pull

# Redémarrer avec la nouvelle version
docker-compose -f docker-compose.healthchecks.yml up -d
```

## 📈 Évolutions Futures

### Court Terme (1-3 mois)
- [ ] Intégration Prometheus pour métriques détaillées
- [ ] Dashboard Grafana personnalisé
- [ ] Monitoring par tenant
- [ ] Auto-remediation pour certains problèmes

### Moyen Terme (3-6 mois)
- [ ] Machine Learning pour détection d'anomalies
- [ ] Prédiction de pannes
- [ ] Capacity planning automatique
- [ ] Intégration avec incident management

### Long Terme (6-12 mois)
- [ ] Observabilité complète avec OpenTelemetry
- [ ] Distributed tracing
- [ ] Chaos engineering automatisé
- [ ] SRE practices complètes

## 📚 Ressources

- [Documentation Healthchecks.io](https://healthchecks.io/docs/)
- [API Reference](https://healthchecks.io/docs/api/)
- [Plan détaillé](plan-healthcheck.md)
- [Code source du monitoring](backend/app/monitoring/)

## 🎯 Checklist de Production

- [ ] Changer tous les mots de passe par défaut
- [ ] Configurer SSL/TLS pour Healthchecks
- [ ] Mettre en place l'authentification forte
- [ ] Configurer les canaux d'alerte (Email, Slack, PagerDuty)
- [ ] Définir les SLOs (Service Level Objectives)
- [ ] Créer un runbook pour chaque type d'alerte
- [ ] Former l'équipe sur le système de monitoring
- [ ] Tester les procédures d'escalade
- [ ] Documenter les procédures de recovery
- [ ] Mettre en place la haute disponibilité pour Healthchecks

---

*Document créé le : 16 Novembre 2024*
*Version : 1.0.0*
*Statut : ✅ Système Opérationnel*