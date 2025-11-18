#!/usr/bin/env python3
"""
Script pour créer/mettre à jour les checks Healthchecks.io avec les UUIDs depuis .env.healthchecks
Utilise directement Django ORM pour garantir les UUIDs corrects.

Usage:
  docker-compose exec healthchecks python manage.py shell < scripts/ensure_healthchecks_with_uuid.py
  ou
  docker-compose -f docker-compose.healthchecks.yml exec healthchecks python /opt/healthchecks/manage.py shell < /path/to/this/script.py
"""

import os
import sys
import uuid as uuid_lib
from datetime import timedelta

# Configuration des checks (doit correspondre à ensure_healthchecks.py)
CHECKS_CONFIG = {
    'HC_CHECK_POSTGRES': {
        'name': 'PostgreSQL Database',
        'tags': 'database infrastructure tier1',
        'timeout': 120,  # 2 minutes
        'grace': 240,    # 4 minutes
        'schedule': '*/2 * * * *',
        'desc': 'Main PostgreSQL database health'
    },
    'HC_CHECK_REDIS': {
        'name': 'Redis Cache/Broker',
        'tags': 'cache redis infrastructure tier1',
        'timeout': 120,
        'grace': 240,
        'schedule': '*/2 * * * *',
        'desc': 'Redis for caching and Celery broker'
    },
    'HC_CHECK_API': {
        'name': 'Flask API',
        'tags': 'api application tier1',
        'timeout': 180,
        'grace': 360,
        'schedule': '*/3 * * * *',
        'desc': 'Main Flask API endpoints'
    },
    'HC_CHECK_CELERY_WORKER': {
        'name': 'Celery Worker SSO',
        'tags': 'celery worker sso tier1',
        'timeout': 300,
        'grace': 600,
        'schedule': '*/5 * * * *',
        'desc': 'SSO background task worker'
    },
    'HC_CHECK_CELERY_BEAT': {
        'name': 'Celery Beat Scheduler',
        'tags': 'celery beat scheduler tier1',
        'timeout': 300,
        'grace': 600,
        'schedule': '*/5 * * * *',
        'desc': 'Task scheduler'
    },
    'HC_CHECK_KAFKA': {
        'name': 'Kafka Broker',
        'tags': 'kafka messaging tier2',
        'timeout': 120,
        'grace': 300,
        'schedule': '*/2 * * * *',
        'desc': 'Apache Kafka message broker'
    },
    'HC_CHECK_KAFKA_CONSUMER': {
        'name': 'Kafka Consumer',
        'tags': 'kafka consumer worker tier2',
        'timeout': 120,
        'grace': 300,
        'schedule': '*/2 * * * *',
        'desc': 'Kafka message consumer worker'
    },
    'HC_CHECK_MINIO': {
        'name': 'MinIO S3 Storage',
        'tags': 'minio storage s3 tier2',
        'timeout': 300,
        'grace': 600,
        'schedule': '*/5 * * * *',
        'desc': 'S3-compatible object storage'
    },
    'HC_CHECK_VAULT': {
        'name': 'Vault Secrets',
        'tags': 'vault security secrets tier2',
        'timeout': 300,
        'grace': 600,
        'schedule': '*/5 * * * *',
        'desc': 'HashiCorp Vault secrets management'
    },
    'HC_CHECK_SSO_TOKEN_REFRESH': {
        'name': 'SSO Token Refresh',
        'tags': 'task scheduled sso',
        'timeout': 900,
        'grace': 300,
        'schedule': '*/15 * * * *',
        'desc': 'Refresh expiring SSO tokens'
    },
    'HC_CHECK_HEALTH_TASK': {
        'name': 'Health Check Task',
        'tags': 'task scheduled monitoring',
        'timeout': 300,
        'grace': 120,
        'schedule': '*/5 * * * *',
        'desc': 'Regular system health check'
    },
    'HC_CHECK_TOKEN_CLEANUP': {
        'name': 'Token Cleanup',
        'tags': 'task scheduled maintenance',
        'timeout': 86400,
        'grace': 3600,
        'schedule': '0 2 * * *',
        'desc': 'Clean up expired tokens'
    },
    'HC_CHECK_KEY_ROTATION': {
        'name': 'Encryption Key Rotation',
        'tags': 'task scheduled security',
        'timeout': 2678400,  # 31 days
        'grace': 7200,
        'schedule': '0 3 1 * *',
        'desc': 'Rotate Vault encryption keys'
    },
    'HC_CHECK_COMPREHENSIVE': {
        'name': 'Comprehensive Health Check',
        'tags': 'monitoring global all',
        'timeout': 600,
        'grace': 600,
        'schedule': '*/10 * * * *',
        'desc': 'Full system health check'
    }
}


def load_env_file(env_file_path):
    """
    Charge les variables d'environnement depuis un fichier .env
    Sans dépendance à python-dotenv
    """
    env_vars = {}
    with open(env_file_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Ignorer les commentaires et lignes vides
            if not line or line.startswith('#'):
                continue
            # Parser la ligne KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def ensure_checks_with_uuid(env_file_path):
    """
    Crée ou met à jour les checks avec les UUIDs depuis .env.healthchecks
    Utilise directement Django ORM pour garantir les UUIDs
    """
    # Charger l'environnement
    if not os.path.exists(env_file_path):
        print(f"❌ File {env_file_path} not found")
        return False

    env_vars = load_env_file(env_file_path)

    # Importer Django models (doit être fait APRÈS le setup Django)
    try:
        from hc.api.models import Check, Project
        from django.contrib.auth import get_user_model
        from django.utils.timezone import now
        import django

        # Setup Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hc.settings')
        django.setup()

    except ImportError as e:
        print(f"❌ Cannot import Django models: {e}")
        print("   Make sure this script runs inside Healthchecks container")
        return False

    User = get_user_model()

    # Récupérer le projet par défaut
    try:
        user = User.objects.get(email='admin@example.com')
        project = Project.objects.filter(owner=user).first()

        if not project:
            project = Project.objects.create(
                owner=user,
                name='SaaS Backend',
                api_key=env_vars.get('HEALTHCHECKS_API_KEY', '')
            )
            print(f"✓ Created default project")
        else:
            print(f"✓ Using existing project: {project.name}")

    except User.DoesNotExist:
        print("❌ Admin user not found. Please run create-healthchecks-admin.sh first")
        return False

    success_count = 0
    failed_count = 0
    created_count = 0
    updated_count = 0

    # Traiter chaque check
    for env_var, check_config in CHECKS_CONFIG.items():
        check_uuid_str = env_vars.get(env_var)

        if not check_uuid_str:
            print(f"\n⚠️  No UUID found for {env_var}, skipping...")
            continue

        # Valider l'UUID
        try:
            check_uuid = uuid_lib.UUID(check_uuid_str)
        except ValueError:
            print(f"\n❌ Invalid UUID for {env_var}: {check_uuid_str}")
            failed_count += 1
            continue

        print(f"\n📊 Processing {check_config['name']} ({env_var})")
        print(f"   UUID: {check_uuid}")

        # Vérifier si le check existe
        try:
            check = Check.objects.get(code=check_uuid)
            print(f"   ✓ Check exists")

            # Mettre à jour si nécessaire
            needs_update = False
            if check.name != check_config['name']:
                check.name = check_config['name']
                needs_update = True
                print(f"   🔄 Updating name: {check_config['name']}")

            if check.desc != check_config.get('desc', ''):
                check.desc = check_config.get('desc', '')
                needs_update = True

            if check.timeout != timedelta(seconds=check_config['timeout']):
                check.timeout = timedelta(seconds=check_config['timeout'])
                needs_update = True

            if check.grace != timedelta(seconds=check_config['grace']):
                check.grace = timedelta(seconds=check_config['grace'])
                needs_update = True

            if check.schedule != check_config.get('schedule', ''):
                check.schedule = check_config.get('schedule', '')
                check.kind = 'cron'  # Force cron kind
                needs_update = True

            if needs_update:
                check.save()
                print(f"   ✓ Check updated")
                updated_count += 1
            else:
                print(f"   ✓ Check is up-to-date")

            success_count += 1

        except Check.DoesNotExist:
            # Créer le check avec l'UUID spécifié
            print(f"   📝 Creating new check with UUID {check_uuid}...")

            try:
                check = Check(
                    code=check_uuid,
                    project=project,
                    name=check_config['name'],
                    desc=check_config.get('desc', ''),
                    tags=check_config.get('tags', ''),
                    timeout=timedelta(seconds=check_config.get('timeout', 3600)),
                    grace=timedelta(seconds=check_config.get('grace', 3600)),
                    schedule=check_config.get('schedule', ''),
                    kind='cron' if 'schedule' in check_config else 'simple',
                    tz='UTC'
                )
                check.save()

                print(f"   ✓ Check created successfully")
                created_count += 1
                success_count += 1

            except Exception as e:
                print(f"   ❌ Failed to create check: {e}")
                failed_count += 1

    # Résumé
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"✓ Success: {success_count} checks")
    print(f"📝 Created: {created_count} new checks")
    print(f"🔄 Updated: {updated_count} checks")
    print(f"❌ Failed: {failed_count} checks")

    if success_count > 0:
        print(f"\n🎯 Next steps:")
        print(f"1. Access Healthchecks UI at http://localhost:8000")
        print(f"2. Restart API and Celery workers to start monitoring")
        print(f"3. Test with: docker-compose exec api python -m app.tasks.monitoring_tasks")

    return failed_count == 0


# Point d'entrée pour le script standalone
if __name__ == '__main__':
    # Ce script doit être exécuté DANS le conteneur Healthchecks via Django shell
    env_file = os.getenv('ENV_FILE', '/opt/healthchecks/.env.healthchecks')
    success = ensure_checks_with_uuid(env_file)
    sys.exit(0 if success else 1)
