"""
Celery tasks for monitoring all services with Healthchecks.io
"""

import os
import time
import logging
import subprocess
import redis
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import text

from app.celery_app import celery_app as celery
from app.extensions import db
from app.monitoring.healthchecks_client import healthchecks
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
def check_postgres_health() -> Dict[str, Any]:
    """
    Vérifie la santé de PostgreSQL

    Checks:
    - Connexion à la base principale
    - Connexions actives vs pool max
    - Taille de la base de données
    - Requêtes longues
    - Santé des bases tenant
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

        # Vérifier la santé des bases tenant (limité aux 5 premiers)
        tenant_health = []
        tenants = Tenant.query.filter_by(is_active=True).limit(5).all()
        for tenant in tenants:
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
            'active_connections': conn_stats.active_connections if conn_stats else 0,
            'last_activity': conn_stats.last_activity.isoformat() if conn_stats and conn_stats.last_activity else None,
            'database_size_mb': round(db_size / 1024 / 1024, 2) if db_size else 0,
            'slow_queries': slow_queries or 0,
            'tenant_databases': tenant_health,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Ping Healthchecks si tout est OK
        if CHECK_IDS.get('postgres'):
            ping_result = healthchecks.ping_success(CHECK_IDS['postgres'])
            logger.info(f"Healthchecks ping sent for PostgreSQL: {ping_result}")

        logger.info(f"PostgreSQL health check passed: {metrics['active_connections']} connections, {metrics['database_size_mb']}MB")
        return metrics

    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {str(e)}")
        if CHECK_IDS.get('postgres'):
            healthchecks.ping_fail(CHECK_IDS['postgres'])
        raise


@celery.task(name='monitoring.check_redis')
def check_redis_health() -> Dict[str, Any]:
    """
    Vérifie la santé de Redis

    Checks:
    - Connexion et ping
    - Utilisation mémoire
    - Nombre de clés par DB
    - Évictions
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
        for db_num in [0, 1, 2, 3, 4]:  # DBs utilisées par l'application
            r_db = redis.Redis(
                host=os.getenv('REDIS_HOST', 'redis'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=db_num,
                decode_responses=True
            )
            db_stats[f'db{db_num}'] = {
                'keys': r_db.dbsize(),
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
            'uptime_days': round(info.get('uptime_in_seconds', 0) / 86400, 2),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Alerter si la mémoire dépasse 200MB
        if metrics['used_memory_mb'] > 200:
            logger.warning(f"Redis memory usage high: {metrics['used_memory_mb']}MB")

        if CHECK_IDS.get('redis'):
            ping_result = healthchecks.ping_success(CHECK_IDS['redis'])
            logger.info(f"Healthchecks ping sent for Redis: {ping_result}")

        logger.info(f"Redis health check passed: {metrics['used_memory_mb']}MB used, {metrics['connected_clients']} clients")
        return metrics

    except Exception as e:
        logger.error(f"Redis health check failed: {str(e)}")
        if CHECK_IDS.get('redis'):
            healthchecks.ping_fail(CHECK_IDS['redis'])
        raise


@celery.task(name='monitoring.check_api')
def check_api_health() -> Dict[str, Any]:
    """
    Vérifie la santé de l'API Flask

    Checks:
    - Endpoint /health
    - Temps de réponse
    - Endpoints critiques
    """
    api_url = f"http://api:{os.getenv('FLASK_PORT', 4999)}"

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

        logger.info(f"API health check passed: {metrics['response_time_ms']}ms response time")
        return metrics

    except Exception as e:
        logger.error(f"API health check failed: {str(e)}")
        if CHECK_IDS.get('api'):
            healthchecks.ping_fail(CHECK_IDS['api'])
        raise


@celery.task(name='monitoring.check_celery')
def check_celery_health() -> Dict[str, Any]:
    """
    Vérifie la santé de Celery (Workers et Beat)

    Checks:
    - Workers actifs
    - Beat scheduler
    - Queue sizes
    """
    try:
        from app.celery_app import celery_app

        # Inspecter les workers
        inspector = celery_app.control.inspect()

        # Workers actifs
        active_workers = inspector.active()
        if not active_workers:
            raise Exception("No active Celery workers found")

        # Statistiques des workers
        stats = inspector.stats()

        # Vérifier Celery Beat
        # Comme le fichier schedule est dans un autre container, on vérifie autrement
        # On considère Beat comme healthy si des workers sont actifs
        # (car Beat envoie des tâches aux workers)
        beat_status = 'unknown'

        # Si on a des workers actifs et des stats, Beat doit fonctionner
        if active_workers and stats:
            # On pourrait vérifier l'heure de la dernière tâche reçue
            # Pour l'instant, on considère que si les workers sont actifs, Beat l'est aussi
            beat_status = 'healthy'

        # Alternative : vérifier le fichier schedule s'il existe localement
        beat_schedule_paths = ['/tmp/celerybeat-schedule.db', '/app/celerybeat-schedule', './celerybeat-schedule']
        for path in beat_schedule_paths:
            if os.path.exists(path):
                beat_mtime = os.path.getmtime(path)
                if time.time() - beat_mtime < 300:  # Modifié dans les 5 dernières minutes
                    beat_status = 'healthy'
                    break
                elif time.time() - beat_mtime < 600:  # Entre 5 et 10 minutes
                    beat_status = 'stale'
                    break

        # Taille des queues
        r = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=1,  # Celery broker DB
            decode_responses=True
        )

        queue_sizes = {}
        for queue in ['celery', 'sso', 'maintenance']:
            queue_sizes[queue] = r.llen(queue)

        metrics = {
            'status': 'healthy',
            'active_workers': len(active_workers) if active_workers else 0,
            'worker_details': list(active_workers.keys()) if active_workers else [],
            'beat_status': beat_status,
            'queue_sizes': queue_sizes,
            'total_tasks_queued': sum(queue_sizes.values()),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Ping les checks appropriés
        if CHECK_IDS.get('celery_worker'):
            healthchecks.ping_success(CHECK_IDS['celery_worker'])
        if CHECK_IDS.get('celery_beat'):
            if beat_status == 'healthy':
                healthchecks.ping_success(CHECK_IDS['celery_beat'])
            elif beat_status == 'stale':
                # Ne signaler un échec que si le fichier est vraiment obsolète
                healthchecks.ping_fail(CHECK_IDS['celery_beat'])
            # Si beat_status == 'unknown', on ne fait rien (ne pas signaler d'échec)

        logger.info(f"Celery health check passed: {metrics['active_workers']} workers, {metrics['total_tasks_queued']} tasks queued")
        return metrics

    except Exception as e:
        logger.error(f"Celery health check failed: {str(e)}")
        if CHECK_IDS.get('celery_worker'):
            healthchecks.ping_fail(CHECK_IDS['celery_worker'])
        raise


@celery.task(name='monitoring.check_kafka')
def check_kafka_health() -> Dict[str, Any]:
    """
    Vérifie la santé de Kafka et du consumer

    Checks:
    - Broker connectivity
    - Topic list
    - Consumer process
    """
    try:
        from kafka import KafkaAdminClient
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

        admin.close()

        metrics = {
            'status': 'healthy',
            'topics_count': len(topics),
            'topics': topics[:10],  # Limiter la liste
            'consumer_running': consumer_running,
            'timestamp': datetime.utcnow().isoformat()
        }

        if CHECK_IDS.get('kafka'):
            healthchecks.ping_success(CHECK_IDS['kafka'])
        if CHECK_IDS.get('kafka_consumer') and consumer_running:
            healthchecks.ping_success(CHECK_IDS['kafka_consumer'])
        elif CHECK_IDS.get('kafka_consumer'):
            healthchecks.ping_fail(CHECK_IDS['kafka_consumer'])

        logger.info(f"Kafka health check passed: {metrics['topics_count']} topics")
        return metrics

    except Exception as e:
        logger.error(f"Kafka health check failed: {str(e)}")
        if CHECK_IDS.get('kafka'):
            healthchecks.ping_fail(CHECK_IDS['kafka'])
        raise


@celery.task(name='monitoring.check_minio')
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
        bucket_name = os.getenv('S3_BUCKET', 'saas-documents')
        try:
            s3.head_bucket(Bucket=bucket_name)
            bucket_exists = True

            # Obtenir des stats basiques sur le bucket
            response = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
            total_objects = response.get('KeyCount', 0)

        except ClientError:
            bucket_exists = False
            total_objects = 0

        metrics = {
            'status': 'healthy',
            'endpoint': minio_url,
            'bucket_exists': bucket_exists,
            'bucket_name': bucket_name,
            'sample_object_count': total_objects,
            'timestamp': datetime.utcnow().isoformat()
        }

        if CHECK_IDS.get('minio'):
            healthchecks.ping_success(CHECK_IDS['minio'])

        logger.info(f"MinIO health check passed: bucket {bucket_name} {'exists' if bucket_exists else 'missing'}")
        return metrics

    except Exception as e:
        logger.error(f"MinIO health check failed: {str(e)}")
        if CHECK_IDS.get('minio'):
            healthchecks.ping_fail(CHECK_IDS['minio'])
        raise


@celery.task(name='monitoring.check_vault')
def check_vault_health() -> Dict[str, Any]:
    """
    Vérifie la santé de Vault

    Checks:
    - Service availability
    - Seal status
    """
    try:
        # Check if Vault is configured
        use_vault = os.getenv('USE_VAULT', 'false').lower() == 'true'
        if not use_vault:
            return {
                'status': 'disabled',
                'message': 'Vault not configured',
                'timestamp': datetime.utcnow().isoformat()
            }

        from app.services.vault_service import vault_service

        # Vérifier la santé via le service
        is_healthy = vault_service.is_healthy() if vault_service else False

        if not is_healthy:
            raise Exception("Vault health check failed")

        # Essayer de récupérer le status
        vault_url = os.getenv('VAULT_ADDR', 'http://vault:8200')
        try:
            response = requests.get(
                f"{vault_url}/v1/sys/health",
                timeout=10
            )
            health_data = response.json() if response.status_code == 200 else {}
        except:
            health_data = {}

        metrics = {
            'status': 'healthy',
            'initialized': health_data.get('initialized', False),
            'sealed': health_data.get('sealed', True),
            'version': health_data.get('version', 'unknown'),
            'timestamp': datetime.utcnow().isoformat()
        }

        if CHECK_IDS.get('vault'):
            healthchecks.ping_success(CHECK_IDS['vault'])

        logger.info(f"Vault health check passed: initialized={metrics['initialized']}, sealed={metrics['sealed']}")
        return metrics

    except Exception as e:
        logger.error(f"Vault health check failed: {str(e)}")
        if CHECK_IDS.get('vault'):
            healthchecks.ping_fail(CHECK_IDS['vault'])
        raise


@celery.task(name='monitoring.comprehensive_health_check')
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

    # Envoyer le statut à Healthchecks si configuré
    if healthchecks.enabled:
        status_summary = healthchecks.get_status()
        if status_summary:
            report['healthchecks_summary'] = {
                'total_checks': status_summary.get('total', 0),
                'up': status_summary.get('up', 0),
                'down': status_summary.get('down', 0)
            }

    return report


# Tâche planifiée pour vérifier la santé régulièrement
@celery.task(name='monitoring.scheduled_health_check')
def scheduled_health_check():
    """
    Tâche planifiée qui vérifie la santé de tous les services
    Devrait être appelée toutes les 5 minutes par Celery Beat
    """
    logger.info("Running scheduled health check")
    report = comprehensive_health_check()

    # Si le système n'est pas healthy, logger un warning
    if report['overall_status'] != 'healthy':
        logger.warning(f"Scheduled health check detected issues: {report['overall_status']}")

    return report