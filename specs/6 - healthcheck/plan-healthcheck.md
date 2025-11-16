# Plan d'intégration Healthchecks.io pour le Backend SaaS Multi-tenant

## 📚 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture de monitoring](#architecture-de-monitoring)
3. [Services à monitorer](#services-à-monitorer)
4. [Configuration Healthchecks.io](#configuration-healthchecksio)
5. [Implémentation par phases](#implémentation-par-phases)
6. [Intégration détaillée](#intégration-détaillée)
7. [Alertes et notifications](#alertes-et-notifications)
8. [Métriques et KPIs](#métriques-et-kpis)
9. [Maintenance et évolution](#maintenance-et-évolution)

---

## 🎯 Vue d'ensemble

### Objectifs
- **Monitoring proactif** : Détecter les problèmes avant qu'ils n'impactent les utilisateurs
- **Disponibilité 99.9%** : Assurer la haute disponibilité du backend SaaS
- **Alertes intelligentes** : Notifications pertinentes sans fatigue d'alerte
- **Observabilité complète** : Vue d'ensemble de tous les services critiques

### Périmètre
- **15+ services Docker** : PostgreSQL, Redis, Kafka, MinIO, Vault, API, Workers
- **4 tâches planifiées Celery** : Token refresh, cleanup, rotation, health checks
- **Multi-tenant** : Monitoring par tenant pour les services critiques
- **Environnements** : Development, Staging, Production

### Stack technique
- **Healthchecks.io** : Self-hosted dans Docker
- **PostgreSQL** : Base dédiée pour Healthchecks
- **Python Client** : Intégration native dans le backend
- **Celery** : Tâches de monitoring asynchrones
- **Alertes** : Email, Slack, Webhooks, PagerDuty

---

## 🏗️ Architecture de monitoring

```ascii
┌─────────────────────────────────────────────────────────────────────┐
│                         HEALTHCHECKS.IO                            │
│                    (Container Docker - Port 8000)                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ Ping Checks  │  │ Cron Checks  │  │  API Checks  │            │
│  │   (HTTP)     │  │   (Schedule) │  │   (Custom)   │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                  │                  │                    │
└─────────┼──────────────────┼──────────────────┼────────────────────┘
          │                  │                  │
    ┌─────▼──────────────────▼──────────────────▼─────┐
    │                MONITORING LAYER                   │
    ├───────────────────────────────────────────────────┤
    │                                                   │
    │  ┌─────────────────────────────────────────┐    │
    │  │     Healthchecks Python Client          │    │
    │  │  (backend/app/monitoring/client.py)     │    │
    │  └─────────────────────────────────────────┘    │
    │                                                   │
    │  ┌─────────────────────────────────────────┐    │
    │  │      Monitoring Decorators              │    │
    │  │   @monitor_task @monitor_endpoint       │    │
    │  └─────────────────────────────────────────┘    │
    │                                                   │
    │  ┌─────────────────────────────────────────┐    │
    │  │      Celery Monitoring Tasks            │    │
    │  │   (backend/app/tasks/monitoring.py)     │    │
    │  └─────────────────────────────────────────┘    │
    └───────────────────────────────────────────────┘
                            │
    ┌───────────────────────▼───────────────────────┐
    │              SERVICES TO MONITOR               │
    ├─────────────────────────────────────────────────┤
    │                                                 │
    │  Infrastructure        Application            │
    │  ├─ PostgreSQL        ├─ Flask API           │
    │  ├─ Redis             ├─ Celery Workers      │
    │  ├─ Kafka/Zookeeper   ├─ Kafka Consumer      │
    │  ├─ MinIO             └─ Scheduled Tasks     │
    │  └─ Vault                                     │
    └─────────────────────────────────────────────────┘
```

---

## 📊 Services à monitorer

### Tier 1 - Services Critiques (Intervalle: 30s-1m)

| Service | Type | Port | Check Method | Intervalle | Timeout | Grace |
|---------|------|------|--------------|------------|---------|--------|
| PostgreSQL | Database | 5432 | `pg_isready` + SELECT 1 | 30s | 10s | 2m |
| Redis | Cache/Broker | 6379 | `redis-cli ping` + INFO | 30s | 5s | 2m |
| Flask API | Application | 4999 | HTTP GET /health | 1m | 15s | 3m |
| Celery Worker SSO | Task Worker | - | `celery inspect ping` | 1m | 10s | 5m |
| Celery Beat | Scheduler | - | Schedule file mtime | 1m | 5s | 5m |

### Tier 2 - Services Essentiels (Intervalle: 1-5m)

| Service | Type | Port | Check Method | Intervalle | Timeout | Grace |
|---------|------|------|--------------|------------|---------|--------|
| Kafka | Message Queue | 9092 | Broker metadata | 2m | 10s | 5m |
| Zookeeper | Coordinator | 2181 | 4-letter word: ruok | 2m | 5s | 5m |
| MinIO | Storage | 9000 | HTTP GET /minio/health/live | 5m | 10s | 10m |
| Vault | Secrets | 8201 | HTTP GET /v1/sys/health | 5m | 10s | 10m |
| Kafka Worker | Consumer | - | Consumer lag check | 2m | 10s | 5m |

### Tier 3 - Tâches Planifiées (Cron Monitoring)

| Tâche | Schedule | Expected Run | Grace Period | Check Type |
|-------|----------|--------------|--------------|------------|
| refresh_expiring_tokens | */15 * * * * | 15 min | 5 min | Cron + Success ping |
| health_check | */5 * * * * | 5 min | 2 min | Cron + Result validation |
| cleanup_expired_tokens | 0 2 * * * | Daily 2am | 1 hour | Cron + Row count |
| rotate_encryption_keys | 0 3 1 * * | Monthly 3am | 2 hours | Cron + Version check |

### Tier 4 - Business Metrics (Intervalle: 5-30m)

| Métrique | Check Method | Intervalle | Seuil d'alerte |
|----------|--------------|------------|----------------|
| Active Tenants | SQL COUNT | 30m | < 1 |
| Failed Logins | Log analysis | 5m | > 10/min |
| API Response Time | p95 latency | 5m | > 2s |
| Database Connections | pg_stat_activity | 5m | > 80% pool |
| Redis Memory | INFO memory | 10m | > 200MB |
| Kafka Consumer Lag | Consumer metrics | 5m | > 1000 messages |
| S3 Storage Usage | MinIO metrics | 30m | > 80% capacity |
| Token Refresh Rate | Success/Fail ratio | 15m | < 95% success |

---

## ⚙️ Configuration Healthchecks.io

### Variables d'environnement

```bash
# === HEALTHCHECKS CORE ===
HEALTHCHECKS_ENABLED=true
HEALTHCHECKS_HOST=http://healthchecks:8000
HEALTHCHECKS_API_URL=http://healthchecks:8000/api/v1
HEALTHCHECKS_PING_URL=http://healthchecks:8000/ping
HEALTHCHECKS_API_KEY=your-project-api-key-here
HEALTHCHECKS_READ_KEY=your-readonly-api-key-here

# === HEALTHCHECKS DATABASE ===
HEALTHCHECKS_DB_NAME=healthchecks
HEALTHCHECKS_DB_USER=healthchecks
HEALTHCHECKS_DB_PASSWORD=secure-password-here
HEALTHCHECKS_DB_HOST=healthchecks-db
HEALTHCHECKS_DB_PORT=5432

# === HEALTHCHECKS SETTINGS ===
HEALTHCHECKS_SECRET_KEY=generate-50-char-secret-key
HEALTHCHECKS_SITE_NAME=SaaS Backend Monitoring
HEALTHCHECKS_REGISTRATION_OPEN=False
HEALTHCHECKS_TIMEZONE=UTC
HEALTHCHECKS_ALLOWED_HOSTS=healthchecks,localhost,monitoring.example.com

# === ALERTING CHANNELS ===
HEALTHCHECKS_EMAIL_HOST=smtp.gmail.com
HEALTHCHECKS_EMAIL_PORT=587
HEALTHCHECKS_EMAIL_USE_TLS=True
HEALTHCHECKS_EMAIL_HOST_USER=monitoring@example.com
HEALTHCHECKS_EMAIL_HOST_PASSWORD=app-specific-password
HEALTHCHECKS_DEFAULT_FROM_EMAIL=monitoring@example.com

HEALTHCHECKS_SLACK_ENABLED=true
HEALTHCHECKS_SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
HEALTHCHECKS_SLACK_CHANNEL=#monitoring

HEALTHCHECKS_PAGERDUTY_ENABLED=false
HEALTHCHECKS_PAGERDUTY_KEY=your-integration-key

# === MONITORING SETTINGS ===
HEALTHCHECKS_CHECK_TIMEOUT=30  # secondes
HEALTHCHECKS_GRACE_MULTIPLIER=2  # grace = interval * multiplier
HEALTHCHECKS_RETRY_COUNT=3
HEALTHCHECKS_RETRY_DELAY=10  # secondes
```

### Docker Compose Service

```yaml
# docker-compose.healthchecks.yml
version: '3.8'

services:
  healthchecks:
    image: healthchecks/healthchecks:v2.10
    container_name: saas-healthchecks
    restart: unless-stopped
    ports:
      - "8000:8000"  # Web UI
      - "8001:8001"  # SMTP (for email pings)
    environment:
      - SECRET_KEY=${HEALTHCHECKS_SECRET_KEY}
      - DEBUG=False
      - REGISTRATION_OPEN=${HEALTHCHECKS_REGISTRATION_OPEN}
      - SITE_NAME=${HEALTHCHECKS_SITE_NAME}
      - DEFAULT_FROM_EMAIL=${HEALTHCHECKS_DEFAULT_FROM_EMAIL}
      - EMAIL_HOST=${HEALTHCHECKS_EMAIL_HOST}
      - EMAIL_PORT=${HEALTHCHECKS_EMAIL_PORT}
      - EMAIL_HOST_USER=${HEALTHCHECKS_EMAIL_HOST_USER}
      - EMAIL_HOST_PASSWORD=${HEALTHCHECKS_EMAIL_HOST_PASSWORD}
      - EMAIL_USE_TLS=${HEALTHCHECKS_EMAIL_USE_TLS}
      - ALLOWED_HOSTS=${HEALTHCHECKS_ALLOWED_HOSTS}
      - DB=postgres
      - DB_HOST=${HEALTHCHECKS_DB_HOST}
      - DB_PORT=${HEALTHCHECKS_DB_PORT}
      - DB_NAME=${HEALTHCHECKS_DB_NAME}
      - DB_USER=${HEALTHCHECKS_DB_USER}
      - DB_PASSWORD=${HEALTHCHECKS_DB_PASSWORD}
      - SLACK_ENABLED=${HEALTHCHECKS_SLACK_ENABLED}
      - SLACK_WEBHOOK_URL=${HEALTHCHECKS_SLACK_WEBHOOK}
    depends_on:
      healthchecks-db:
        condition: service_healthy
    volumes:
      - healthchecks-media:/opt/healthchecks/media
    networks:
      - saas_network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/status"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  healthchecks-db:
    image: postgres:13-alpine
    container_name: saas-healthchecks-db
    restart: unless-stopped
    environment:
      - POSTGRES_DB=${HEALTHCHECKS_DB_NAME}
      - POSTGRES_USER=${HEALTHCHECKS_DB_USER}
      - POSTGRES_PASSWORD=${HEALTHCHECKS_DB_PASSWORD}
      - POSTGRES_INITDB_ARGS=--encoding=UTF-8
    volumes:
      - healthchecks-db-data:/var/lib/postgresql/data
    networks:
      - saas_network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${HEALTHCHECKS_DB_USER} -d ${HEALTHCHECKS_DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  healthchecks-db-data:
    driver: local
  healthchecks-media:
    driver: local

networks:
  saas_network:
    external: true
```

---

## 📦 Implémentation par phases

### Phase 1: Infrastructure de base (Semaine 1)

#### Jour 1-2: Setup Healthchecks.io
- [ ] Créer `docker-compose.healthchecks.yml`
- [ ] Configurer la base PostgreSQL dédiée
- [ ] Démarrer et initialiser Healthchecks
- [ ] Créer le premier projet via UI
- [ ] Récupérer les API keys

#### Jour 3-4: Client Python
- [ ] Créer `backend/app/monitoring/healthchecks_client.py`
- [ ] Implémenter les méthodes de base (ping, fail, start)
- [ ] Ajouter la gestion des erreurs et retry logic
- [ ] Créer les tests unitaires

#### Jour 5-7: Intégration basique
- [ ] Intégrer le health check de l'API Flask
- [ ] Ajouter le monitoring PostgreSQL
- [ ] Ajouter le monitoring Redis
- [ ] Tester les alertes email

### Phase 2: Monitoring avancé (Semaine 2)

#### Jour 8-10: Celery & Workers
- [ ] Créer un décorateur `@monitor_celery_task`
- [ ] Intégrer le monitoring Celery Beat
- [ ] Monitorer les workers SSO
- [ ] Ajouter les checks pour les tâches planifiées

#### Jour 11-12: Kafka & Services
- [ ] Implémenter le monitoring Kafka consumer
- [ ] Ajouter les checks pour MinIO
- [ ] Intégrer le monitoring Vault
- [ ] Créer un dashboard de santé globale

#### Jour 13-14: Tests & Optimisation
- [ ] Tests de charge sur le monitoring
- [ ] Optimiser les intervalles de check
- [ ] Configurer les grace periods
- [ ] Documentation utilisateur

### Phase 3: Métriques avancées (Semaine 3)

#### Jour 15-17: Business Metrics
- [ ] Monitoring par tenant
- [ ] Métriques d'utilisation API
- [ ] Tracking des erreurs métier
- [ ] Analyse des patterns d'usage

#### Jour 18-19: Alerting avancé
- [ ] Configuration Slack
- [ ] Intégration PagerDuty (production)
- [ ] Webhooks personnalisés
- [ ] Escalade d'alertes

#### Jour 20-21: Dashboard & Reporting
- [ ] Dashboard Healthchecks personnalisé
- [ ] Rapports hebdomadaires automatiques
- [ ] Intégration avec Grafana (optionnel)
- [ ] Export des métriques

---

## 🔧 Intégration détaillée

### 1. Client Python Healthchecks

```python
# backend/app/monitoring/healthchecks_client.py

import os
import requests
import logging
from typing import Optional, Dict, Any
from functools import wraps
from datetime import datetime, timedelta
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class HealthchecksClient:
    """Client pour interagir avec l'API Healthchecks.io"""

    def __init__(self):
        self.enabled = os.getenv('HEALTHCHECKS_ENABLED', 'false').lower() == 'true'
        self.api_url = os.getenv('HEALTHCHECKS_API_URL', 'http://healthchecks:8000/api/v1')
        self.ping_url = os.getenv('HEALTHCHECKS_PING_URL', 'http://healthchecks:8000/ping')
        self.api_key = os.getenv('HEALTHCHECKS_API_KEY')
        self.timeout = int(os.getenv('HEALTHCHECKS_CHECK_TIMEOUT', '30'))
        self.retry_count = int(os.getenv('HEALTHCHECKS_RETRY_COUNT', '3'))
        self.retry_delay = int(os.getenv('HEALTHCHECKS_RETRY_DELAY', '10'))

        if self.enabled and not self.api_key:
            logger.warning("Healthchecks enabled but API key not configured")
            self.enabled = False

    def ping(self, check_id: str, status: str = '') -> bool:
        """
        Envoie un ping à Healthchecks

        Args:
            check_id: UUID du check
            status: '', '/start', '/fail', ou code de sortie

        Returns:
            True si succès, False sinon
        """
        if not self.enabled:
            return True

        url = f"{self.ping_url}/{check_id}{status}"

        for attempt in range(self.retry_count):
            try:
                response = requests.get(
                    url,
                    timeout=self.timeout,
                    headers={'User-Agent': 'SaaS-Backend-Monitor/1.0'}
                )
                if response.status_code == 200:
                    logger.debug(f"Ping successful for check {check_id}")
                    return True
                logger.warning(f"Ping failed with status {response.status_code}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Ping error (attempt {attempt + 1}): {str(e)}")
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)

        return False

    def ping_start(self, check_id: str) -> bool:
        """Signale le début d'une tâche"""
        return self.ping(check_id, '/start')

    def ping_success(self, check_id: str) -> bool:
        """Signale le succès d'une tâche"""
        return self.ping(check_id)

    def ping_fail(self, check_id: str) -> bool:
        """Signale l'échec d'une tâche"""
        return self.ping(check_id, '/fail')

    def create_check(self, name: str, tags: str = '',
                    schedule: str = '* * * * *',
                    tz: str = 'UTC',
                    grace: int = 3600) -> Optional[Dict[str, Any]]:
        """
        Crée un nouveau check via l'API

        Args:
            name: Nom du check
            tags: Tags séparés par des espaces
            schedule: Expression cron ou intervalle en secondes
            tz: Timezone
            grace: Grace period en secondes

        Returns:
            Dict avec les infos du check créé ou None
        """
        if not self.enabled:
            return None

        url = urljoin(self.api_url, 'checks/')
        headers = {
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        }

        data = {
            'name': name,
            'tags': tags,
            'timeout': grace,
            'grace': grace,
            'channels': '*',  # Utilise tous les canaux configurés
        }

        # Déterminer le type de schedule
        if schedule.isdigit():
            data['kind'] = 'simple'
            data['timeout'] = int(schedule)
        else:
            data['kind'] = 'cron'
            data['schedule'] = schedule
            data['tz'] = tz

        try:
            response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
            if response.status_code == 201:
                check_data = response.json()
                logger.info(f"Check '{name}' created with ID {check_data.get('ping_url')}")
                return check_data
            logger.error(f"Failed to create check: {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating check: {str(e)}")

        return None

    def list_checks(self, tag: Optional[str] = None) -> list:
        """Liste tous les checks, optionnellement filtrés par tag"""
        if not self.enabled:
            return []

        url = urljoin(self.api_url, 'checks/')
        headers = {'X-Api-Key': self.api_key}
        params = {'tag': tag} if tag else {}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
            if response.status_code == 200:
                return response.json().get('checks', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing checks: {str(e)}")

        return []

    def get_check(self, check_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les détails d'un check"""
        if not self.enabled:
            return None

        url = urljoin(self.api_url, f'checks/{check_id}')
        headers = {'X-Api-Key': self.api_key}

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting check: {str(e)}")

        return None

    def pause_check(self, check_id: str) -> bool:
        """Met en pause un check"""
        return self._update_check(check_id, {'status': 'paused'})

    def resume_check(self, check_id: str) -> bool:
        """Réactive un check en pause"""
        return self._update_check(check_id, {'status': 'new'})

    def _update_check(self, check_id: str, data: Dict[str, Any]) -> bool:
        """Met à jour un check"""
        if not self.enabled:
            return False

        url = urljoin(self.api_url, f'checks/{check_id}')
        headers = {
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating check: {str(e)}")

        return False

# Instance singleton
healthchecks = HealthchecksClient()
```

### 2. Décorateur de monitoring

```python
# backend/app/monitoring/decorators.py

import time
import functools
import logging
from typing import Optional, Callable, Any
from .healthchecks_client import healthchecks

logger = logging.getLogger(__name__)

def monitor_task(check_id: Optional[str] = None,
                 check_name: Optional[str] = None,
                 auto_start: bool = True):
    """
    Décorateur pour monitorer l'exécution d'une tâche

    Args:
        check_id: UUID du check Healthchecks
        check_name: Nom pour créer automatiquement le check
        auto_start: Envoyer un ping /start au début

    Usage:
        @monitor_task(check_id='abc-123-def')
        def my_task():
            pass

        @monitor_task(check_name='my-scheduled-task')
        def my_scheduled_task():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Résoudre le check_id
            actual_check_id = check_id
            if not actual_check_id and check_name:
                # Tenter de créer ou récupérer le check
                checks = healthchecks.list_checks(tag=check_name)
                if checks:
                    actual_check_id = checks[0].get('ping_url', '').split('/')[-1]
                else:
                    check = healthchecks.create_check(
                        name=check_name,
                        tags=f'auto-created {func.__name__}',
                        schedule='* * * * *'  # Par défaut, à ajuster
                    )
                    if check:
                        actual_check_id = check.get('ping_url', '').split('/')[-1]

            if not actual_check_id:
                logger.warning(f"No check_id for monitoring {func.__name__}")
                return func(*args, **kwargs)

            # Signaler le début si demandé
            if auto_start:
                healthchecks.ping_start(actual_check_id)

            start_time = time.time()
            try:
                # Exécuter la fonction
                result = func(*args, **kwargs)

                # Signaler le succès
                execution_time = time.time() - start_time
                healthchecks.ping_success(actual_check_id)
                logger.info(f"Task {func.__name__} completed in {execution_time:.2f}s")

                return result

            except Exception as e:
                # Signaler l'échec
                execution_time = time.time() - start_time
                healthchecks.ping_fail(actual_check_id)
                logger.error(f"Task {func.__name__} failed after {execution_time:.2f}s: {str(e)}")
                raise

        return wrapper
    return decorator

def monitor_endpoint(check_id: Optional[str] = None,
                    check_name: Optional[str] = None):
    """
    Décorateur pour monitorer un endpoint Flask

    Usage:
        @app.route('/api/critical')
        @monitor_endpoint(check_name='critical-api-endpoint')
        def critical_endpoint():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Similaire à monitor_task mais adapté pour Flask
            actual_check_id = check_id
            if not actual_check_id and check_name:
                checks = healthchecks.list_checks(tag=check_name)
                if checks:
                    actual_check_id = checks[0].get('ping_url', '').split('/')[-1]

            if actual_check_id:
                try:
                    result = func(*args, **kwargs)
                    healthchecks.ping_success(actual_check_id)
                    return result
                except Exception as e:
                    healthchecks.ping_fail(actual_check_id)
                    raise

            return func(*args, **kwargs)

        return wrapper
    return decorator
```

### 3. Tâches Celery de monitoring

```python
# backend/app/tasks/monitoring_tasks.py

import os
import logging
import subprocess
import psutil
import redis
import requests
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy import text

from app.celery_app import celery
from app.extensions import db
from app.services.vault_service import vault_service
from app.monitoring.healthchecks_client import healthchecks
from app.monitoring.decorators import monitor_task
from app.utils.database import tenant_db_manager
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

# Check IDs (à configurer dans .env ou récupérer dynamiquement)
CHECK_IDS = {
    'postgres': os.getenv('HC_CHECK_POSTGRES'),
    'redis': os.getenv('HC_CHECK_REDIS'),
    'api': os.getenv('HC_CHECK_API'),
    'kafka': os.getenv('HC_CHECK_KAFKA'),
    'minio': os.getenv('HC_CHECK_MINIO'),
    'vault': os.getenv('HC_CHECK_VAULT'),
    'celery_worker': os.getenv('HC_CHECK_CELERY_WORKER'),
    'celery_beat': os.getenv('HC_CHECK_CELERY_BEAT'),
    'kafka_consumer': os.getenv('HC_CHECK_KAFKA_CONSUMER'),
}

@celery.task(name='monitoring.check_postgres')
@monitor_task(check_name='postgres-health')
def check_postgres_health() -> Dict[str, Any]:
    """
    Vérifie la santé de PostgreSQL

    Checks:
    - Connexion à la base principale
    - Connexions actives vs pool max
    - Taille de la base de données
    - Requêtes longues
    - Réplication lag (si applicable)
    """
    try:
        # Test de connexion basique
        result = db.session.execute(text("SELECT 1")).scalar()
        if result != 1:
            raise Exception("SELECT 1 failed")

        # Statistiques des connexions
        conn_stats = db.session.execute(text("""
            SELECT
                count(*) as active_connections,
                max(state_change) as last_activity
            FROM pg_stat_activity
            WHERE datname = current_database()
        """)).first()

        # Taille de la base de données
        db_size = db.session.execute(text("""
            SELECT pg_database_size(current_database()) as size_bytes
        """)).scalar()

        # Requêtes longues (> 30 secondes)
        slow_queries = db.session.execute(text("""
            SELECT count(*) as count
            FROM pg_stat_activity
            WHERE state = 'active'
            AND query_start < NOW() - INTERVAL '30 seconds'
            AND query NOT LIKE '%pg_stat_activity%'
        """)).scalar()

        # Vérifier la santé des bases tenant
        tenant_health = []
        tenants = Tenant.query.filter_by(is_active=True).all()
        for tenant in tenants[:5]:  # Limiter aux 5 premiers pour éviter la surcharge
            try:
                with tenant_db_manager.tenant_db_session(tenant.database_name) as session:
                    session.execute(text("SELECT 1"))
                    tenant_health.append({
                        'tenant_id': str(tenant.id),
                        'database': tenant.database_name,
                        'status': 'healthy'
                    })
            except Exception as e:
                tenant_health.append({
                    'tenant_id': str(tenant.id),
                    'database': tenant.database_name,
                    'status': 'unhealthy',
                    'error': str(e)
                })

        metrics = {
            'status': 'healthy',
            'active_connections': conn_stats.active_connections,
            'last_activity': conn_stats.last_activity.isoformat() if conn_stats.last_activity else None,
            'database_size_mb': round(db_size / 1024 / 1024, 2),
            'slow_queries': slow_queries,
            'tenant_databases': tenant_health,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Ping Healthchecks si tout est OK
        if CHECK_IDS.get('postgres'):
            healthchecks.ping_success(CHECK_IDS['postgres'])

        return metrics

    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {str(e)}")
        if CHECK_IDS.get('postgres'):
            healthchecks.ping_fail(CHECK_IDS['postgres'])
        raise

@celery.task(name='monitoring.check_redis')
@monitor_task(check_name='redis-health')
def check_redis_health() -> Dict[str, Any]:
    """
    Vérifie la santé de Redis

    Checks:
    - Connexion et ping
    - Utilisation mémoire
    - Nombre de clés par DB
    - Évictions
    - Latence
    """
    try:
        r = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            decode_responses=True
        )

        # Test ping
        if not r.ping():
            raise Exception("Redis ping failed")

        # Récupérer les infos
        info = r.info()
        info_memory = r.info('memory')
        info_stats = r.info('stats')

        # Vérifier chaque base de données utilisée
        db_stats = {}
        for db_num in [0, 2, 3, 4]:  # DBs utilisées par l'application
            r_db = redis.Redis(
                host=os.getenv('REDIS_HOST', 'redis'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=db_num,
                decode_responses=True
            )
            db_stats[f'db{db_num}'] = {
                'keys': r_db.dbsize(),
                'expires': len(r_db.keys('*')),  # Simplification
            }

        metrics = {
            'status': 'healthy',
            'connected_clients': info.get('connected_clients', 0),
            'used_memory_mb': round(info_memory.get('used_memory', 0) / 1024 / 1024, 2),
            'used_memory_peak_mb': round(info_memory.get('used_memory_peak', 0) / 1024 / 1024, 2),
            'memory_fragmentation': info_memory.get('mem_fragmentation_ratio', 0),
            'evicted_keys': info_stats.get('evicted_keys', 0),
            'keyspace_hits': info_stats.get('keyspace_hits', 0),
            'keyspace_misses': info_stats.get('keyspace_misses', 0),
            'databases': db_stats,
            'uptime_days': info.get('uptime_in_seconds', 0) / 86400,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Alerter si la mémoire dépasse 200MB
        if metrics['used_memory_mb'] > 200:
            logger.warning(f"Redis memory usage high: {metrics['used_memory_mb']}MB")

        if CHECK_IDS.get('redis'):
            healthchecks.ping_success(CHECK_IDS['redis'])

        return metrics

    except Exception as e:
        logger.error(f"Redis health check failed: {str(e)}")
        if CHECK_IDS.get('redis'):
            healthchecks.ping_fail(CHECK_IDS['redis'])
        raise

@celery.task(name='monitoring.check_api')
@monitor_task(check_name='api-health')
def check_api_health() -> Dict[str, Any]:
    """
    Vérifie la santé de l'API Flask

    Checks:
    - Endpoint /health
    - Temps de réponse
    - Endpoints critiques
    """
    api_url = f"http://api:{os.getenv('API_PORT', 4999)}"

    try:
        # Check principal /health
        start_time = time.time()
        response = requests.get(
            f"{api_url}/health",
            timeout=10
        )
        response_time = time.time() - start_time

        if response.status_code != 200:
            raise Exception(f"Health check returned {response.status_code}")

        health_data = response.json()

        # Vérifier quelques endpoints critiques
        critical_endpoints = [
            '/api/auth/health',
            '/api/tenants/health',
            '/api/users/health'
        ]

        endpoint_health = []
        for endpoint in critical_endpoints:
            try:
                ep_response = requests.get(f"{api_url}{endpoint}", timeout=5)
                endpoint_health.append({
                    'endpoint': endpoint,
                    'status_code': ep_response.status_code,
                    'healthy': ep_response.status_code < 500
                })
            except Exception as e:
                endpoint_health.append({
                    'endpoint': endpoint,
                    'status_code': 0,
                    'healthy': False,
                    'error': str(e)
                })

        metrics = {
            'status': 'healthy',
            'version': health_data.get('version'),
            'response_time_ms': round(response_time * 1000, 2),
            'endpoints': endpoint_health,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Alerter si temps de réponse > 2 secondes
        if response_time > 2:
            logger.warning(f"API response time slow: {response_time:.2f}s")

        if CHECK_IDS.get('api'):
            healthchecks.ping_success(CHECK_IDS['api'])

        return metrics

    except Exception as e:
        logger.error(f"API health check failed: {str(e)}")
        if CHECK_IDS.get('api'):
            healthchecks.ping_fail(CHECK_IDS['api'])
        raise

@celery.task(name='monitoring.check_celery')
@monitor_task(check_name='celery-health')
def check_celery_health() -> Dict[str, Any]:
    """
    Vérifie la santé de Celery (Workers et Beat)

    Checks:
    - Workers actifs
    - Beat scheduler
    - Queue sizes
    - Task stats
    """
    try:
        from app.celery_app import celery as celery_app

        # Inspecter les workers
        inspector = celery_app.control.inspect()

        # Workers actifs
        active_workers = inspector.active()
        if not active_workers:
            raise Exception("No active Celery workers found")

        # Statistiques des workers
        stats = inspector.stats()

        # Vérifier Celery Beat
        beat_status = 'unknown'
        beat_schedule_path = '/tmp/celerybeat-schedule'
        if os.path.exists(beat_schedule_path):
            beat_mtime = os.path.getmtime(beat_schedule_path)
            if time.time() - beat_mtime < 120:  # Modifié dans les 2 dernières minutes
                beat_status = 'healthy'
            else:
                beat_status = 'stale'

        # Taille des queues
        r = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=3,  # Celery broker DB
            decode_responses=True
        )

        queue_sizes = {}
        for queue in ['celery', 'sso', 'maintenance']:
            queue_sizes[queue] = r.llen(queue)

        metrics = {
            'status': 'healthy',
            'active_workers': len(active_workers),
            'worker_details': list(active_workers.keys()),
            'beat_status': beat_status,
            'queue_sizes': queue_sizes,
            'total_tasks_queued': sum(queue_sizes.values()),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Ping les checks appropriés
        if CHECK_IDS.get('celery_worker'):
            healthchecks.ping_success(CHECK_IDS['celery_worker'])
        if CHECK_IDS.get('celery_beat') and beat_status == 'healthy':
            healthchecks.ping_success(CHECK_IDS['celery_beat'])
        elif CHECK_IDS.get('celery_beat'):
            healthchecks.ping_fail(CHECK_IDS['celery_beat'])

        return metrics

    except Exception as e:
        logger.error(f"Celery health check failed: {str(e)}")
        if CHECK_IDS.get('celery_worker'):
            healthchecks.ping_fail(CHECK_IDS['celery_worker'])
        raise

@celery.task(name='monitoring.check_kafka')
@monitor_task(check_name='kafka-health')
def check_kafka_health() -> Dict[str, Any]:
    """
    Vérifie la santé de Kafka et du consumer

    Checks:
    - Broker connectivity
    - Topic list
    - Consumer lag
    - Consumer process
    """
    try:
        from kafka import KafkaAdminClient, KafkaConsumer
        from kafka.errors import KafkaError

        # Admin client pour vérifier le cluster
        admin = KafkaAdminClient(
            bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092'),
            request_timeout_ms=5000
        )

        # Lister les topics
        topics = admin.list_topics()

        # Vérifier le consumer process
        consumer_running = False
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'python -m app.worker.consumer'],
                capture_output=True,
                text=True,
                timeout=5
            )
            consumer_running = result.returncode == 0
        except Exception as e:
            logger.warning(f"Could not check consumer process: {e}")

        # Consumer lag (simplifié)
        consumer = KafkaConsumer(
            bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092'),
            group_id='saas-consumer-group',
            enable_auto_commit=False
        )

        lag_info = {}
        for topic in ['tenant.created', 'document.uploaded', 'file.process']:
            partitions = consumer.partitions_for_topic(topic)
            if partitions:
                # Simplification: juste vérifier l'existence
                lag_info[topic] = 'monitored'

        consumer.close()
        admin.close()

        metrics = {
            'status': 'healthy',
            'topics_count': len(topics),
            'topics': topics[:10],  # Limiter la liste
            'consumer_running': consumer_running,
            'consumer_lag': lag_info,
            'timestamp': datetime.utcnow().isoformat()
        }

        if CHECK_IDS.get('kafka'):
            healthchecks.ping_success(CHECK_IDS['kafka'])
        if CHECK_IDS.get('kafka_consumer') and consumer_running:
            healthchecks.ping_success(CHECK_IDS['kafka_consumer'])
        elif CHECK_IDS.get('kafka_consumer'):
            healthchecks.ping_fail(CHECK_IDS['kafka_consumer'])

        return metrics

    except Exception as e:
        logger.error(f"Kafka health check failed: {str(e)}")
        if CHECK_IDS.get('kafka'):
            healthchecks.ping_fail(CHECK_IDS['kafka'])
        raise

@celery.task(name='monitoring.check_minio')
@monitor_task(check_name='minio-health')
def check_minio_health() -> Dict[str, Any]:
    """
    Vérifie la santé de MinIO

    Checks:
    - Service availability
    - Bucket existence
    - Storage usage
    """
    try:
        minio_url = os.getenv('S3_ENDPOINT_URL', 'http://minio:9000')

        # Health endpoint
        response = requests.get(
            f"{minio_url}/minio/health/live",
            timeout=10
        )

        if response.status_code != 200:
            raise Exception(f"MinIO health check failed: {response.status_code}")

        # Vérifier le bucket via boto3
        import boto3
        from botocore.exceptions import ClientError

        s3 = boto3.client(
            's3',
            endpoint_url=minio_url,
            aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID', 'minioadmin'),
            aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY', 'minioadmin'),
            region_name='us-east-1'
        )

        # Vérifier que le bucket existe
        bucket_name = os.getenv('S3_BUCKET_NAME', 'saas-documents')
        try:
            s3.head_bucket(Bucket=bucket_name)
            bucket_exists = True

            # Obtenir des stats sur le bucket
            paginator = s3.get_paginator('list_objects_v2')
            total_objects = 0
            total_size = 0

            for page in paginator.paginate(Bucket=bucket_name):
                if 'Contents' in page:
                    total_objects += len(page['Contents'])
                    total_size += sum(obj['Size'] for obj in page['Contents'])

                # Limiter pour éviter de scanner tout le bucket
                if total_objects > 1000:
                    break

        except ClientError:
            bucket_exists = False
            total_objects = 0
            total_size = 0

        metrics = {
            'status': 'healthy',
            'endpoint': minio_url,
            'bucket_exists': bucket_exists,
            'bucket_name': bucket_name,
            'total_objects': total_objects,
            'total_size_mb': round(total_size / 1024 / 1024, 2),
            'timestamp': datetime.utcnow().isoformat()
        }

        if CHECK_IDS.get('minio'):
            healthchecks.ping_success(CHECK_IDS['minio'])

        return metrics

    except Exception as e:
        logger.error(f"MinIO health check failed: {str(e)}")
        if CHECK_IDS.get('minio'):
            healthchecks.ping_fail(CHECK_IDS['minio'])
        raise

@celery.task(name='monitoring.check_vault')
@monitor_task(check_name='vault-health')
def check_vault_health() -> Dict[str, Any]:
    """
    Vérifie la santé de Vault

    Checks:
    - Service availability
    - Seal status
    - Token validity
    """
    try:
        if not vault_service:
            return {
                'status': 'disabled',
                'message': 'Vault not configured',
                'timestamp': datetime.utcnow().isoformat()
            }

        # Vérifier la santé via le service
        is_healthy = vault_service.is_healthy()

        if not is_healthy:
            raise Exception("Vault health check failed")

        # Essayer de récupérer le status
        vault_url = os.getenv('VAULT_ADDR', 'http://vault:8200')
        response = requests.get(
            f"{vault_url}/v1/sys/health",
            timeout=10
        )

        health_data = response.json() if response.status_code == 200 else {}

        metrics = {
            'status': 'healthy',
            'initialized': health_data.get('initialized', False),
            'sealed': health_data.get('sealed', True),
            'version': health_data.get('version', 'unknown'),
            'cluster_name': health_data.get('cluster_name', 'unknown'),
            'timestamp': datetime.utcnow().isoformat()
        }

        if CHECK_IDS.get('vault'):
            healthchecks.ping_success(CHECK_IDS['vault'])

        return metrics

    except Exception as e:
        logger.error(f"Vault health check failed: {str(e)}")
        if CHECK_IDS.get('vault'):
            healthchecks.ping_fail(CHECK_IDS['vault'])
        raise

@celery.task(name='monitoring.comprehensive_health_check')
@monitor_task(check_name='comprehensive-health')
def comprehensive_health_check() -> Dict[str, Any]:
    """
    Effectue un check de santé complet de tous les services
    Agrège les résultats et génère un rapport global
    """
    results = {}
    errors = []

    # Liste des checks à effectuer
    checks = [
        ('postgres', check_postgres_health),
        ('redis', check_redis_health),
        ('api', check_api_health),
        ('celery', check_celery_health),
        ('kafka', check_kafka_health),
        ('minio', check_minio_health),
        ('vault', check_vault_health)
    ]

    # Exécuter chaque check
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            results[name] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            errors.append(f"{name}: {str(e)}")

    # Calculer le statut global
    healthy_count = sum(1 for r in results.values() if r.get('status') == 'healthy')
    total_count = len(results)

    overall_status = 'healthy' if healthy_count == total_count else \
                    'degraded' if healthy_count > total_count / 2 else \
                    'critical'

    report = {
        'overall_status': overall_status,
        'healthy_services': healthy_count,
        'total_services': total_count,
        'services': results,
        'errors': errors,
        'timestamp': datetime.utcnow().isoformat()
    }

    # Log le rapport
    if overall_status != 'healthy':
        logger.warning(f"System health: {overall_status} ({healthy_count}/{total_count} healthy)")
        if errors:
            logger.error(f"Health check errors: {', '.join(errors)}")
    else:
        logger.info(f"System health: All {total_count} services healthy")

    return report
```

### 4. Script d'initialisation

```python
# backend/scripts/setup_healthchecks.py

#!/usr/bin/env python3
"""
Script pour initialiser les checks Healthchecks.io
Usage: python scripts/setup_healthchecks.py
"""

import os
import sys
import json
import time
from typing import Dict, List

# Ajouter le backend au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.monitoring.healthchecks_client import healthchecks

# Configuration des checks à créer
CHECKS_CONFIG = [
    # Services Infrastructure
    {
        'name': 'PostgreSQL Database',
        'tags': 'database infrastructure tier1',
        'schedule': '30',  # 30 secondes
        'grace': 120,  # 2 minutes
        'desc': 'Main PostgreSQL database health'
    },
    {
        'name': 'Redis Cache/Broker',
        'tags': 'cache redis infrastructure tier1',
        'schedule': '30',
        'grace': 120,
        'desc': 'Redis for caching and Celery broker'
    },
    {
        'name': 'Flask API',
        'tags': 'api application tier1',
        'schedule': '60',
        'grace': 180,
        'desc': 'Main Flask API endpoints'
    },
    {
        'name': 'Celery Worker SSO',
        'tags': 'celery worker sso tier1',
        'schedule': '60',
        'grace': 300,
        'desc': 'SSO background task worker'
    },
    {
        'name': 'Celery Beat Scheduler',
        'tags': 'celery beat scheduler tier1',
        'schedule': '60',
        'grace': 300,
        'desc': 'Task scheduler'
    },

    # Services Tier 2
    {
        'name': 'Kafka Broker',
        'tags': 'kafka messaging tier2',
        'schedule': '120',
        'grace': 300,
        'desc': 'Apache Kafka message broker'
    },
    {
        'name': 'Kafka Consumer',
        'tags': 'kafka consumer worker tier2',
        'schedule': '120',
        'grace': 300,
        'desc': 'Kafka message consumer worker'
    },
    {
        'name': 'MinIO S3 Storage',
        'tags': 'minio storage s3 tier2',
        'schedule': '300',
        'grace': 600,
        'desc': 'S3-compatible object storage'
    },
    {
        'name': 'Vault Secrets',
        'tags': 'vault security secrets tier2',
        'schedule': '300',
        'grace': 600,
        'desc': 'HashiCorp Vault secrets management'
    },

    # Tâches planifiées
    {
        'name': 'SSO Token Refresh',
        'tags': 'task scheduled sso',
        'schedule': '*/15 * * * *',  # Toutes les 15 minutes
        'grace': 300,
        'desc': 'Refresh expiring SSO tokens'
    },
    {
        'name': 'Health Check Task',
        'tags': 'task scheduled monitoring',
        'schedule': '*/5 * * * *',  # Toutes les 5 minutes
        'grace': 120,
        'desc': 'Regular system health check'
    },
    {
        'name': 'Token Cleanup',
        'tags': 'task scheduled maintenance',
        'schedule': '0 2 * * *',  # 2h du matin
        'grace': 3600,
        'desc': 'Clean up expired tokens'
    },
    {
        'name': 'Encryption Key Rotation',
        'tags': 'task scheduled security',
        'schedule': '0 3 1 * *',  # 1er du mois à 3h
        'grace': 7200,
        'desc': 'Rotate Vault encryption keys'
    },

    # Check global
    {
        'name': 'Comprehensive Health Check',
        'tags': 'monitoring global all',
        'schedule': '600',  # 10 minutes
        'grace': 600,
        'desc': 'Full system health check'
    }
]

def setup_healthchecks():
    """Configure tous les checks Healthchecks.io"""

    print("🏥 Setting up Healthchecks.io monitoring...")

    if not healthchecks.enabled:
        print("❌ Healthchecks is not enabled. Set HEALTHCHECKS_ENABLED=true")
        return False

    # Vérifier la connexion
    existing_checks = healthchecks.list_checks()
    print(f"✓ Connected to Healthchecks. Found {len(existing_checks)} existing checks.")

    created_checks = []
    failed_checks = []

    for check_config in CHECKS_CONFIG:
        print(f"\n📊 Creating check: {check_config['name']}")

        # Vérifier si le check existe déjà
        existing = [c for c in existing_checks if c['name'] == check_config['name']]
        if existing:
            print(f"  ⚠️  Check already exists with ID: {existing[0]['ping_url'].split('/')[-1]}")
            created_checks.append(existing[0])
            continue

        # Créer le nouveau check
        check = healthchecks.create_check(
            name=check_config['name'],
            tags=check_config['tags'],
            schedule=check_config['schedule'],
            grace=check_config['grace']
        )

        if check:
            check_id = check.get('ping_url', '').split('/')[-1]
            print(f"  ✓ Created with ID: {check_id}")
            created_checks.append(check)
        else:
            print(f"  ❌ Failed to create check")
            failed_checks.append(check_config['name'])

        # Pause entre les créations pour éviter rate limiting
        time.sleep(0.5)

    # Générer le fichier de configuration
    print("\n📝 Generating environment variables...")
    env_vars = []

    for check in created_checks:
        name = check['name'].upper().replace(' ', '_').replace('-', '_')
        check_id = check.get('ping_url', '').split('/')[-1]
        env_vars.append(f"HC_CHECK_{name}={check_id}")

    env_file = 'healthchecks.env'
    with open(env_file, 'w') as f:
        f.write("# Healthchecks.io Check IDs\n")
        f.write("# Add these to your .env file\n\n")
        for var in sorted(env_vars):
            f.write(f"{var}\n")

    print(f"✓ Environment variables written to {env_file}")

    # Résumé
    print("\n" + "="*50)
    print("📊 SETUP SUMMARY")
    print("="*50)
    print(f"✓ Created: {len(created_checks)} checks")
    if failed_checks:
        print(f"❌ Failed: {len(failed_checks)} checks")
        for name in failed_checks:
            print(f"   - {name}")
    print(f"\n🎯 Next steps:")
    print(f"1. Copy variables from {env_file} to your .env")
    print(f"2. Restart the API container")
    print(f"3. Configure alert channels in Healthchecks UI")
    print(f"4. Start the monitoring tasks")

    return len(failed_checks) == 0

if __name__ == '__main__':
    success = setup_healthchecks()
    sys.exit(0 if success else 1)
```

---

## 🔔 Alertes et notifications

### Configuration des canaux

#### Email
```yaml
Channel: Email
To: ops@example.com, dev-team@example.com
Subject: [ALERT] {{check.name}} is {{check.status}}
```

#### Slack
```yaml
Channel: Slack
Webhook: https://hooks.slack.com/services/XXX/YYY/ZZZ
Channel: #monitoring
Username: Healthchecks Bot
Icon: :rotating_light:
```

#### PagerDuty (Production)
```yaml
Channel: PagerDuty
Integration Key: xxx-xxx-xxx
Severity: Based on tags (tier1=critical, tier2=warning)
```

### Règles d'escalade

| Niveau | Condition | Actions |
|--------|-----------|---------|
| **Info** | Service recovered | Email summary |
| **Warning** | Tier 2 service down | Email + Slack notification |
| **Critical** | Tier 1 service down | Email + Slack + PagerDuty |
| **Emergency** | Multiple Tier 1 down | All channels + Phone call |

### Templates de messages

```text
# Email Template
Subject: [{{severity}}] {{check.name}} - {{status}}

Service: {{check.name}}
Status: {{status}}
Last Ping: {{last_ping}}
Environment: {{tags}}
Duration: {{downtime}}

{{#if down}}
ACTIONS REQUIRED:
1. Check service logs: docker-compose logs -f {{service}}
2. Restart if needed: docker-compose restart {{service}}
3. Check dependencies
{{/if}}

Dashboard: {{dashboard_url}}
```

---

## 📈 Métriques et KPIs

### SLIs (Service Level Indicators)

| Métrique | Calcul | Objectif |
|----------|---------|----------|
| **Disponibilité API** | Uptime / Total time | 99.9% |
| **Latence P95** | 95th percentile response time | < 2s |
| **Taux d'erreur** | Errors / Total requests | < 0.1% |
| **Saturation DB** | Active connections / Pool size | < 80% |
| **Fraîcheur des données** | Time since last successful sync | < 5 min |

### SLOs (Service Level Objectives)

| Service | SLO | Mesure |
|---------|-----|--------|
| **API** | 99.9% uptime mensuel | 43.2 min downtime max |
| **Database** | 99.95% uptime | 21.6 min downtime max |
| **Background Jobs** | 95% success rate | < 5% échecs |
| **SSO Token Refresh** | 99% success rate | < 1% échecs |

### Dashboard Metrics

```python
# Requête pour dashboard temps réel
SELECT
    service_name,
    status,
    last_ping,
    EXTRACT(EPOCH FROM (NOW() - last_ping)) as seconds_since_ping,
    success_rate_7d,
    avg_response_time_1h,
    error_count_24h
FROM healthchecks_metrics
WHERE environment = 'production'
ORDER BY tier, service_name;
```

---

## 🔧 Maintenance et évolution

### Maintenance régulière

#### Quotidien
- [ ] Vérifier le dashboard Healthchecks
- [ ] Examiner les alertes de la nuit
- [ ] Vérifier les logs d'erreur

#### Hebdomadaire
- [ ] Review des métriques de performance
- [ ] Ajuster les seuils d'alerte si nécessaire
- [ ] Nettoyer les anciennes données de monitoring

#### Mensuel
- [ ] Rapport de disponibilité
- [ ] Analyse des tendances
- [ ] Mise à jour de la documentation
- [ ] Test de recovery procedures

### Plan d'évolution

#### Court terme (1-3 mois)
- Intégration Prometheus pour métriques détaillées
- Dashboard Grafana personnalisé
- Monitoring des métriques business par tenant
- Automatisation des actions de remédiation

#### Moyen terme (3-6 mois)
- Machine Learning pour détection d'anomalies
- Prédiction de pannes
- Capacity planning automatique
- Monitoring de la sécurité (intrusion detection)

#### Long terme (6-12 mois)
- Observabilité complète avec OpenTelemetry
- Distributed tracing
- Chaos engineering tests
- SRE practices complètes

### Troubleshooting

#### Check ne reçoit pas de pings
```bash
# Vérifier la configuration
docker-compose exec api python -c "
from app.monitoring.healthchecks_client import healthchecks
print('Enabled:', healthchecks.enabled)
print('API URL:', healthchecks.api_url)
print('API Key:', healthchecks.api_key[:10] + '...' if healthchecks.api_key else 'NOT SET')
"

# Tester manuellement un ping
curl -X GET http://localhost:8000/ping/{check_id}
```

#### Fausses alertes fréquentes
1. Augmenter la grace period
2. Ajuster l'intervalle de check
3. Vérifier les ressources du container
4. Examiner les logs pour patterns

#### Service Healthchecks down
```bash
# Redémarrer le service
docker-compose -f docker-compose.healthchecks.yml restart healthchecks

# Vérifier les logs
docker-compose -f docker-compose.healthchecks.yml logs -f healthchecks

# Backup de la base
docker-compose exec healthchecks-db pg_dump -U healthchecks healthchecks > healthchecks_backup.sql
```

---

## 📚 Ressources

### Documentation
- [Healthchecks.io Docs](https://healthchecks.io/docs/)
- [API Reference](https://healthchecks.io/docs/api/)
- [Self-hosting Guide](https://healthchecks.io/docs/self_hosted/)

### Outils complémentaires
- **Prometheus**: Métriques détaillées
- **Grafana**: Visualisation avancée
- **Jaeger**: Distributed tracing
- **ELK Stack**: Log aggregation

### Best Practices
- [Google SRE Book](https://sre.google/sre-book/table-of-contents/)
- [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- [The Four Golden Signals](https://sre.google/sre-book/monitoring-distributed-systems/#xref_monitoring_golden-signals)

---

## 🎯 Checklist de déploiement

### Pré-production
- [ ] Docker Compose configuré
- [ ] Variables d'environnement définies
- [ ] Healthchecks.io démarré et accessible
- [ ] Checks créés via script
- [ ] Client Python testé
- [ ] Alertes email configurées
- [ ] Documentation mise à jour

### Production
- [ ] Backup de configuration
- [ ] Haute disponibilité pour Healthchecks
- [ ] SSL/TLS configuré
- [ ] Authentification renforcée
- [ ] Intégration PagerDuty
- [ ] Monitoring du monitoring
- [ ] Runbook d'incident créé

### Post-déploiement
- [ ] Formation de l'équipe
- [ ] Test d'alerte complet
- [ ] Simulation de panne
- [ ] Revue des seuils après 1 semaine
- [ ] Optimisation après 1 mois

---

*Document créé le: 2024*
*Dernière mise à jour: À maintenir*
*Version: 1.0.0*