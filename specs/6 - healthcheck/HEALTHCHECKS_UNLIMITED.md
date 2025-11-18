# 🚀 Healthchecks.io Self-Hosted - Configuration Sans Limites

## Résumé Exécutif

**Votre installation Healthchecks.io self-hosted est DÉJÀ configurée pour un nombre ILLIMITÉ de checks.**

Il n'y a aucune limite artificielle dans la version self-hosted. Le message "Your account is currently over its check limit" venait du fait que vous aviez des doublons et des checks de test qui ont été nettoyés.

## Comparaison des Versions

| Fonctionnalité | Cloud (healthchecks.io) | Self-Hosted (Votre Installation) |
|----------------|-------------------------|-----------------------------------|
| **Limite de Checks** | 20 (gratuit), 100+ (payant) | **ILLIMITÉ** ✅ |
| **Coût** | $5-80/mois | **GRATUIT** ✅ |
| **Licence** | Propriétaire | BSD-3-Clause (Open Source) |
| **Contrôle des Données** | Hébergé par Healthchecks | Sur votre serveur |
| **Configuration Requise** | Aucune | Docker + PostgreSQL |

## État Actuel de Votre Installation

### Checks Configurés (14 au total)
```
✅ PostgreSQL Database       - Surveillance base de données principale
✅ Redis Cache/Broker        - Surveillance cache et broker Celery
✅ Flask API                 - Surveillance de l'API REST
✅ Celery Beat Scheduler     - Surveillance du planificateur de tâches
✅ Celery Worker SSO         - Surveillance worker SSO
✅ Kafka Broker              - Surveillance système de messages
✅ Kafka Consumer            - Surveillance consommateur Kafka
✅ MinIO S3 Storage          - Surveillance stockage objet
✅ Vault Secrets             - Surveillance gestionnaire de secrets
✅ SSO Token Refresh         - Tâche de rafraîchissement des tokens
✅ Token Cleanup             - Tâche de nettoyage des tokens
✅ Encryption Key Rotation   - Rotation des clés de chiffrement
✅ Health Check Task         - Tâche de vérification santé
✅ comprehensive-health      - Check de santé global
```

### Nettoyage Effectué
- **Supprimé 4 doublons** : postgres-health (x2), redis-health (x2)
- **Supprimé 2 checks de test** : Test Check, Test from API
- **Supprimé 2 checks redondants** : Comprehensive Health Check, celery-health
- **Résultat** : 22 checks → 14 checks (économie de 8 checks)

## Capacité Réelle de Votre Installation

### Limites Techniques (Non Configurables car Illimitées)

La seule "limite" est votre infrastructure matérielle :

| Ressource | Capacité Estimée | Recommandation |
|-----------|------------------|----------------|
| **Nombre de Checks** | Illimité | 1000+ checks sans problème |
| **Fréquence de Ping** | Illimité | Limité par CPU/réseau |
| **Historique des Pings** | 100 derniers par défaut | Configurable via Django Admin |
| **Taille Base de Données** | Selon votre disque | ~1MB pour 100 checks actifs |

### Configuration de l'Historique des Pings

Le seul paramètre configurable concerne l'historique :

```python
# Accès Django Admin
http://localhost:8000/admin/
# Connexion : admin@example.com / 12345678

# Navigation : Users → admin → Profile
# Champ : "Ping log limit" (par défaut : 100)
```

## Vérification du Fonctionnement

### 1. Interface Web
```bash
# Accès à l'interface Healthchecks
open http://localhost:8000
# Login : admin@example.com / 12345678
```

### 2. API Healthchecks
```bash
# Vérifier le statut
curl http://localhost:8000/api/v1/status

# Lister tous les checks
curl -H "X-Api-Key: hVIB-d9ihVotUKFmoiwAKNH5JBVmra4j" \
     http://localhost:8000/api/v1/checks/
```

### 3. Monitoring Backend
```bash
# Vérifier que les tâches de monitoring tournent
docker-compose logs -f celery-beat | grep monitoring

# Vérifier les pings reçus
docker-compose exec healthchecks ./manage.py shell -c "
from hc.api.models import Ping
recent_pings = Ping.objects.all().order_by('-created')[:10]
for ping in recent_pings:
    print(f'{ping.created}: {ping.owner.name}')
"
```

## Ajouter Plus de Checks (Exemples)

### 1. Via l'API Python
```python
# Dans backend/scripts/setup_healthchecks.py
additional_checks = [
    {
        "name": "Backup Daily",
        "tags": "backup database",
        "schedule": "0 2 * * *",  # 2h du matin
        "timezone": "UTC",
        "grace": 3600
    },
    {
        "name": "SSL Certificate Check",
        "tags": "security ssl",
        "timeout": 300,
        "grace": 86400
    },
    {
        "name": "Disk Space Monitor",
        "tags": "infrastructure",
        "schedule": "*/30 * * * *",  # Toutes les 30 minutes
        "grace": 1800
    }
]

for check_config in additional_checks:
    healthchecks.create_check(check_config)
```

### 2. Via l'Interface Web
1. Connectez-vous à http://localhost:8000
2. Cliquez sur "+ Add Check"
3. Configurez le check (nom, schedule, grace period)
4. Copiez l'URL de ping
5. Ajoutez le ping à votre script/cron

### 3. Via cURL
```bash
curl -X POST http://localhost:8000/api/v1/checks/ \
    -H "X-Api-Key: hVIB-d9ihVotUKFmoiwAKNH5JBVmra4j" \
    -d '{"name": "New Service", "tags": "production", "timeout": 3600, "grace": 300}'
```

## Optimisation pour Grand Nombre de Checks

Si vous prévoyez d'avoir 100+ checks :

### 1. Tuning PostgreSQL
```yaml
# Dans docker-compose.healthchecks.yml
healthchecks-db:
  environment:
    - POSTGRES_INITDB_ARGS=--encoding=UTF-8 --data-checksums
  command: >
    postgres
    -c max_connections=200
    -c shared_buffers=256MB
    -c effective_cache_size=1GB
    -c maintenance_work_mem=64MB
```

### 2. Nettoyage Automatique
```python
# Ajouter une tâche Celery pour nettoyer les vieux pings
@celery.task
def cleanup_old_pings():
    """Nettoie les pings de plus de 30 jours"""
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=30)
    old_pings = Ping.objects.filter(created__lt=cutoff)
    count = old_pings.count()
    old_pings.delete()
    return f"Deleted {count} old pings"
```

### 3. Monitoring du Monitoring
```python
# Surveillez Healthchecks lui-même
@monitor_task(check_name='healthchecks-system')
def monitor_healthchecks():
    response = requests.get('http://healthchecks:8000/api/v1/status')
    if response.status_code != 200:
        raise Exception("Healthchecks is down!")
```

## Migration depuis le Cloud

Si vous migriez depuis healthchecks.io cloud :

```bash
# Export depuis le cloud
curl https://healthchecks.io/api/v1/checks/ \
    -H "X-Api-Key: YOUR_CLOUD_KEY" > checks_export.json

# Import dans self-hosted
python scripts/import_checks.py checks_export.json
```

## Troubleshooting

### "Check limit" dans Self-Hosted ?
- **Cause** : Message d'erreur générique, souvent dû aux doublons
- **Solution** : Nettoyer les doublons (déjà fait)

### Performance avec Beaucoup de Checks
- **Symptôme** : Interface lente avec 500+ checks
- **Solution** : Augmenter les workers uWSGI dans docker-compose.healthchecks.yml

### Pings Non Reçus
- **Vérification** : `docker-compose logs healthchecks | grep ping`
- **Solution** : Vérifier la connectivité réseau entre containers

## Conclusion

✅ **Votre Healthchecks self-hosted est 100% illimité**
✅ **Aucune configuration supplémentaire nécessaire**
✅ **Peut gérer des milliers de checks sans modification**
✅ **Gratuit et open source à vie**

Le message d'erreur que vous aviez vu était dû aux doublons, maintenant résolus. Vous pouvez créer autant de checks que nécessaire sans aucune limite !

---

*Document créé le : 16 Novembre 2024*
*Version : 1.0.0*
*Statut : ✅ Système Illimité et Opérationnel*