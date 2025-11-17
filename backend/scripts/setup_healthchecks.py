#!/usr/bin/env python3
"""
Script pour initialiser les checks Healthchecks.io
Usage: python scripts/setup_healthchecks.py
"""

import os
import sys
import time
from typing import Dict, List

# Ajouter le backend au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration des checks à créer
CHECKS_CONFIG = [
    # Services Infrastructure Tier 1 (Critiques)
    # NOTE: Timing must match Celery Beat schedules in celery_app.py
    {
        'name': 'PostgreSQL Database',
        'tags': 'database infrastructure tier1',
        'schedule': '*/2 * * * *',  # Every 2 minutes (matches crontab(minute='*/2'))
        'grace': 240,  # 4 minutes (2x timeout for buffer)
        'desc': 'Main PostgreSQL database health'
    },
    {
        'name': 'Redis Cache/Broker',
        'tags': 'cache redis infrastructure tier1',
        'schedule': '*/2 * * * *',  # Every 2 minutes (matches crontab(minute='*/2'))
        'grace': 240,  # 4 minutes (2x timeout for buffer)
        'desc': 'Redis for caching and Celery broker'
    },
    {
        'name': 'Flask API',
        'tags': 'api application tier1',
        'schedule': '*/3 * * * *',  # Every 3 minutes (matches crontab(minute='*/3'))
        'grace': 360,  # 6 minutes (2x timeout for buffer)
        'desc': 'Main Flask API endpoints'
    },
    {
        'name': 'Celery Worker SSO',
        'tags': 'celery worker sso tier1',
        'schedule': '*/5 * * * *',  # Every 5 minutes (checked by monitor-celery task)
        'grace': 600,  # 10 minutes (2x timeout for buffer)
        'desc': 'SSO background task worker'
    },
    {
        'name': 'Celery Beat Scheduler',
        'tags': 'celery beat scheduler tier1',
        'schedule': '*/5 * * * *',  # Every 5 minutes (checked by monitor-celery task)
        'grace': 600,  # 10 minutes (2x timeout for buffer)
        'desc': 'Task scheduler'
    },

    # Services Tier 2 (Essentiels)
    {
        'name': 'Kafka Broker',
        'tags': 'kafka messaging tier2',
        'schedule': '*/2 * * * *',  # Every 2 minutes
        'grace': 300,
        'desc': 'Apache Kafka message broker'
    },
    {
        'name': 'Kafka Consumer',
        'tags': 'kafka consumer worker tier2',
        'schedule': '*/2 * * * *',  # Every 2 minutes
        'grace': 300,
        'desc': 'Kafka message consumer worker'
    },
    {
        'name': 'MinIO S3 Storage',
        'tags': 'minio storage s3 tier2',
        'schedule': '*/5 * * * *',  # Every 5 minutes
        'grace': 600,
        'desc': 'S3-compatible object storage'
    },
    {
        'name': 'Vault Secrets',
        'tags': 'vault security secrets tier2',
        'schedule': '*/5 * * * *',  # Every 5 minutes
        'grace': 600,
        'desc': 'HashiCorp Vault secrets management'
    },

    # Tâches planifiées (Cron)
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
        'schedule': '*/10 * * * *',  # Every 10 minutes
        'grace': 600,
        'desc': 'Full system health check'
    }
]


def setup_healthchecks():
    """Configure tous les checks Healthchecks.io"""

    print("🏥 Setting up Healthchecks.io monitoring...")

    # Import ici pour avoir le contexte Flask
    from app.monitoring.healthchecks_client import healthchecks

    if not healthchecks.enabled:
        print("❌ Healthchecks is not enabled. Set HEALTHCHECKS_ENABLED=true")
        return False

    # Vérifier la connexion
    print("📡 Connecting to Healthchecks API...")
    existing_checks = healthchecks.list_checks()
    print(f"✓ Connected to Healthchecks. Found {len(existing_checks)} existing checks.")

    created_checks = []
    failed_checks = []
    skipped_checks = []

    for check_config in CHECKS_CONFIG:
        print(f"\n📊 Processing check: {check_config['name']}")

        # Vérifier si le check existe déjà
        existing = [c for c in existing_checks if c['name'] == check_config['name']]
        if existing:
            check_id = existing[0].get('ping_url', '').split('/')[-1]
            print(f"  ⚠️  Check already exists with ID: {check_id}")
            skipped_checks.append(existing[0])
            continue

        # Créer le nouveau check
        print(f"  Creating new check...")
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

    # Générer le fichier de configuration avec les IDs
    print("\n📝 Generating environment variables...")
    env_vars = []

    # Mapper les noms de checks aux variables d'environnement
    check_name_to_env = {
        'PostgreSQL Database': 'HC_CHECK_POSTGRES',
        'Redis Cache/Broker': 'HC_CHECK_REDIS',
        'Flask API': 'HC_CHECK_API',
        'Kafka Broker': 'HC_CHECK_KAFKA',
        'Kafka Consumer': 'HC_CHECK_KAFKA_CONSUMER',
        'MinIO S3 Storage': 'HC_CHECK_MINIO',
        'Vault Secrets': 'HC_CHECK_VAULT',
        'Celery Worker SSO': 'HC_CHECK_CELERY_WORKER',
        'Celery Beat Scheduler': 'HC_CHECK_CELERY_BEAT',
        'SSO Token Refresh': 'HC_CHECK_SSO_TOKEN_REFRESH',
        'Health Check Task': 'HC_CHECK_HEALTH_TASK',
        'Token Cleanup': 'HC_CHECK_TOKEN_CLEANUP',
        'Encryption Key Rotation': 'HC_CHECK_KEY_ROTATION',
        'Comprehensive Health Check': 'HC_CHECK_COMPREHENSIVE'
    }

    all_checks = created_checks + skipped_checks
    for check in all_checks:
        check_name = check.get('name', '')
        if check_name in check_name_to_env:
            env_var = check_name_to_env[check_name]
            check_id = check.get('ping_url', '').split('/')[-1]
            if check_id:
                env_vars.append(f"{env_var}={check_id}")

    # Écrire le fichier .env.healthchecks
    env_file = '.env.healthchecks'
    with open(env_file, 'a') as f:  # Append mode to preserve existing config
        f.write("\n# ============================================================================\n")
        f.write("# Healthchecks.io Check IDs\n")
        f.write("# Generated by setup_healthchecks.py\n")
        f.write("# These IDs are automatically loaded when using scripts/start-healthchecks.sh\n")
        f.write("# ============================================================================\n\n")
        for var in sorted(env_vars):
            f.write(f"{var}\n")

    print(f"✓ Environment variables written to {env_file}")

    # Résumé
    print("\n" + "="*60)
    print("📊 SETUP SUMMARY")
    print("="*60)
    print(f"✓ Created: {len(created_checks)} new checks")
    print(f"⚠️  Skipped: {len(skipped_checks)} existing checks")
    if failed_checks:
        print(f"❌ Failed: {len(failed_checks)} checks")
        for name in failed_checks:
            print(f"   - {name}")

    print(f"\n🎯 Next steps:")
    print(f"1. Check IDs have been added to {env_file}")
    print(f"2. Start Healthchecks using: ./scripts/start-healthchecks.sh")
    print(f"3. Access Healthchecks UI at http://localhost:8000")
    print(f"4. Configure alert channels (Email, Slack, etc.)")
    print(f"5. Restart the API and Celery workers to apply changes")
    print(f"6. Run 'docker-compose exec api python -m app.tasks.monitoring_tasks' to test")

    # Afficher l'état actuel si des checks existent
    if all_checks:
        print(f"\n📊 Current Healthchecks Status:")
        status = healthchecks.get_status()
        if status:
            print(f"   Total checks: {status.get('total', 0)}")
            print(f"   Up: {status.get('up', 0)}")
            print(f"   Down: {status.get('down', 0)}")
            print(f"   New/Paused: {status.get('new', 0) + status.get('paused', 0)}")

    return len(failed_checks) == 0


if __name__ == '__main__':
    # Vérifier si on est dans le bon répertoire
    if not os.path.exists('scripts/setup_healthchecks.py'):
        print("❌ Please run this script from the backend directory")
        sys.exit(1)

    # Setup Flask app context
    try:
        from app import create_app
        app = create_app()
        with app.app_context():
            success = setup_healthchecks()
            sys.exit(0 if success else 1)
    except ImportError as e:
        print(f"❌ Could not import Flask app: {e}")
        print("Make sure you're running from the backend directory and have all dependencies installed")
        sys.exit(1)