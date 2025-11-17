#!/usr/bin/env python3
"""
Script pour synchroniser les checks Healthchecks.io avec les UUIDs depuis .env.healthchecks
Crée les checks s'ils n'existent pas, ou les met à jour avec les UUIDs fournis.

Usage: python scripts/sync_healthchecks_uuids.py
"""

import os
import sys
import requests
import time
from typing import Dict, Optional
from dotenv import load_dotenv

# Ajouter le backend au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration des checks avec leurs paramètres par défaut
CHECKS_CONFIG = {
    'HC_CHECK_POSTGRES': {
        'name': 'PostgreSQL Database',
        'tags': 'database infrastructure tier1',
        'schedule': '*/2 * * * *',
        'grace': 240,
        'desc': 'Main PostgreSQL database health'
    },
    'HC_CHECK_REDIS': {
        'name': 'Redis Cache/Broker',
        'tags': 'cache redis infrastructure tier1',
        'schedule': '*/2 * * * *',
        'grace': 240,
        'desc': 'Redis for caching and Celery broker'
    },
    'HC_CHECK_API': {
        'name': 'Flask API',
        'tags': 'api application tier1',
        'schedule': '*/3 * * * *',
        'grace': 360,
        'desc': 'Main Flask API endpoints'
    },
    'HC_CHECK_CELERY_WORKER': {
        'name': 'Celery Worker SSO',
        'tags': 'celery worker sso tier1',
        'schedule': '*/5 * * * *',
        'grace': 600,
        'desc': 'SSO background task worker'
    },
    'HC_CHECK_CELERY_BEAT': {
        'name': 'Celery Beat Scheduler',
        'tags': 'celery beat scheduler tier1',
        'schedule': '*/5 * * * *',
        'grace': 600,
        'desc': 'Task scheduler'
    },
    'HC_CHECK_KAFKA': {
        'name': 'Kafka Broker',
        'tags': 'kafka messaging tier2',
        'schedule': '*/2 * * * *',
        'grace': 300,
        'desc': 'Apache Kafka message broker'
    },
    'HC_CHECK_KAFKA_CONSUMER': {
        'name': 'Kafka Consumer',
        'tags': 'kafka consumer worker tier2',
        'schedule': '*/2 * * * *',
        'grace': 300,
        'desc': 'Kafka message consumer worker'
    },
    'HC_CHECK_MINIO': {
        'name': 'MinIO S3 Storage',
        'tags': 'minio storage s3 tier2',
        'schedule': '*/5 * * * *',
        'grace': 600,
        'desc': 'S3-compatible object storage'
    },
    'HC_CHECK_VAULT': {
        'name': 'Vault Secrets',
        'tags': 'vault security secrets tier2',
        'schedule': '*/5 * * * *',
        'grace': 600,
        'desc': 'HashiCorp Vault secrets management'
    },
    'HC_CHECK_SSO_TOKEN_REFRESH': {
        'name': 'SSO Token Refresh',
        'tags': 'task scheduled sso',
        'schedule': '*/15 * * * *',
        'grace': 300,
        'desc': 'Refresh expiring SSO tokens'
    },
    'HC_CHECK_HEALTH_TASK': {
        'name': 'Health Check Task',
        'tags': 'task scheduled monitoring',
        'schedule': '*/5 * * * *',
        'grace': 120,
        'desc': 'Regular system health check'
    },
    'HC_CHECK_TOKEN_CLEANUP': {
        'name': 'Token Cleanup',
        'tags': 'task scheduled maintenance',
        'schedule': '0 2 * * *',
        'grace': 3600,
        'desc': 'Clean up expired tokens'
    },
    'HC_CHECK_KEY_ROTATION': {
        'name': 'Encryption Key Rotation',
        'tags': 'task scheduled security',
        'schedule': '0 3 1 * *',
        'grace': 7200,
        'desc': 'Rotate Vault encryption keys'
    },
    'HC_CHECK_COMPREHENSIVE': {
        'name': 'Comprehensive Health Check',
        'tags': 'monitoring global all',
        'schedule': '*/10 * * * *',
        'grace': 600,
        'desc': 'Full system health check'
    }
}


def load_healthchecks_config() -> Dict[str, str]:
    """Charge la configuration depuis .env.healthchecks"""
    # Charger les variables d'environnement depuis .env.healthchecks
    env_path = '.env.healthchecks'
    if not os.path.exists(env_path):
        print(f"❌ File {env_path} not found")
        return {}

    load_dotenv(env_path)

    config = {
        'api_key': os.getenv('HEALTHCHECKS_API_KEY'),
        'api_url': os.getenv('HEALTHCHECKS_API_URL', 'http://healthchecks:8000/api/v1'),
        'host': os.getenv('HEALTHCHECKS_HOST', 'http://healthchecks:8000')
    }

    # Charger les UUIDs des checks
    uuids = {}
    for env_var in CHECKS_CONFIG.keys():
        uuid = os.getenv(env_var)
        if uuid:
            uuids[env_var] = uuid

    config['uuids'] = uuids
    return config


def create_or_update_check(api_url: str, api_key: str, uuid: str, check_config: dict) -> bool:
    """
    Crée ou met à jour un check avec l'UUID spécifié
    """
    headers = {
        'X-Api-Key': api_key
    }

    # D'abord essayer de récupérer le check existant
    check_url = f"{api_url}/checks/{uuid}"

    try:
        # Vérifier si le check existe
        response = requests.get(check_url, headers=headers, timeout=10)

        if response.status_code == 200:
            # Le check existe, on le met à jour
            print(f"  ✓ Check exists with UUID {uuid}, updating...")
            update_data = {
                'name': check_config['name'],
                'tags': check_config['tags'],
                'desc': check_config['desc'],
                'schedule': check_config['schedule'],
                'grace': check_config['grace']
            }

            response = requests.post(check_url, json=update_data, headers=headers, timeout=10)
            if response.status_code == 200:
                print(f"  ✓ Check updated successfully")
                return True
            else:
                print(f"  ❌ Failed to update check: {response.status_code}")
                return False

        elif response.status_code == 404:
            # Le check n'existe pas, on le crée avec l'UUID spécifié
            print(f"  📝 Check does not exist, creating with UUID {uuid}...")

            # Healthchecks.io permet de spécifier l'UUID lors de la création via l'API
            create_data = {
                'name': check_config['name'],
                'tags': check_config['tags'],
                'desc': check_config['desc'],
                'schedule': check_config['schedule'],
                'grace': check_config['grace'],
                'unique': [uuid],  # Spécifier l'UUID unique
                'channels': '*'  # Utiliser tous les canaux configurés
            }

            # Créer le check avec POST sur /checks/
            response = requests.post(f"{api_url}/checks/", json=create_data, headers=headers, timeout=10)

            if response.status_code in [200, 201]:
                created_check = response.json()
                # Vérifier que l'UUID correspond
                created_uuid = created_check.get('ping_url', '').split('/')[-1]
                if created_uuid == uuid:
                    print(f"  ✓ Check created successfully with UUID {uuid}")
                    return True
                else:
                    print(f"  ⚠️  Check created but with different UUID: {created_uuid}")
                    # Essayer de supprimer et recréer avec le bon UUID
                    return recreate_check_with_uuid(api_url, api_key, uuid, check_config, created_uuid)
            else:
                print(f"  ❌ Failed to create check: {response.status_code}")
                if response.text:
                    print(f"     Error: {response.text}")
                return False
        else:
            print(f"  ❌ Unexpected response: {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"  ❌ Request failed: {e}")
        return False


def recreate_check_with_uuid(api_url: str, api_key: str, target_uuid: str, check_config: dict, current_uuid: str) -> bool:
    """
    Supprime un check existant et le recrée avec l'UUID cible
    """
    headers = {
        'X-Api-Key': api_key
    }

    print(f"  🔄 Recreating check with correct UUID...")

    # Supprimer l'ancien check
    delete_url = f"{api_url}/checks/{current_uuid}"
    try:
        response = requests.delete(delete_url, headers=headers, timeout=10)
        if response.status_code not in [200, 204]:
            print(f"  ❌ Failed to delete old check: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Failed to delete old check: {e}")
        return False

    # Attendre un peu avant de recréer
    time.sleep(1)

    # Recréer avec le bon UUID via l'API de création manuelle
    # Healthchecks.io n'offre pas de moyen direct de spécifier l'UUID via l'API standard
    # On doit utiliser une approche différente

    # Alternativement, créer via l'API management si disponible
    print(f"  ⚠️  Note: Healthchecks.io may not allow custom UUIDs via API")
    print(f"     You might need to manually create the check with UUID {target_uuid}")
    print(f"     Or use the Healthchecks.io management command in the container")

    return False


def sync_all_checks():
    """Synchronise tous les checks avec les UUIDs depuis .env.healthchecks"""

    print("🏥 Syncing Healthchecks.io checks with UUIDs from .env.healthchecks...")

    # Charger la configuration
    config = load_healthchecks_config()

    if not config.get('api_key'):
        print("❌ HEALTHCHECKS_API_KEY not found in .env.healthchecks")
        return False

    api_url = config['api_url']
    api_key = config['api_key']
    uuids = config['uuids']

    print(f"📡 API URL: {api_url}")
    print(f"🔑 API Key: {api_key[:10]}...")
    print(f"📊 Found {len(uuids)} check UUIDs in .env.healthchecks\n")

    success_count = 0
    failed_count = 0

    # Traiter chaque check
    for env_var, uuid in uuids.items():
        if env_var not in CHECKS_CONFIG:
            print(f"⚠️  Unknown check: {env_var}")
            continue

        check_config = CHECKS_CONFIG[env_var]
        print(f"\n📊 Processing {check_config['name']} ({env_var})")
        print(f"   UUID: {uuid}")

        if create_or_update_check(api_url, api_key, uuid, check_config):
            success_count += 1
        else:
            failed_count += 1

        # Pause entre les opérations pour éviter le rate limiting
        time.sleep(0.5)

    # Résumé
    print("\n" + "="*60)
    print("📊 SYNC SUMMARY")
    print("="*60)
    print(f"✓ Success: {success_count} checks")
    print(f"❌ Failed: {failed_count} checks")

    if success_count > 0:
        print(f"\n🎯 Next steps:")
        print(f"1. Access Healthchecks UI at http://localhost:8000")
        print(f"2. Verify all checks are configured correctly")
        print(f"3. Restart API and Celery workers to start pinging")
        print(f"4. Test with: docker-compose exec api python -m app.tasks.monitoring_tasks")

    return failed_count == 0


def create_check_via_management_command(container_name: str, uuid: str, check_config: dict):
    """
    Crée un check via la commande de gestion Django dans le conteneur Healthchecks
    (Alternative si l'API ne permet pas de spécifier l'UUID)
    """
    import subprocess

    # Construction de la commande Django management
    cmd = [
        'docker-compose', 'exec', '-T', container_name,
        'python', 'manage.py', 'shell', '-c',
        f"""
from hc.api.models import Check
from django.contrib.auth.models import User

# Récupérer ou créer l'utilisateur admin
user = User.objects.first()
if not user:
    print("No user found")
    exit(1)

# Créer ou mettre à jour le check avec l'UUID spécifié
check, created = Check.objects.update_or_create(
    code='{uuid}',
    defaults={{
        'user': user,
        'name': '{check_config['name']}',
        'tags': '{check_config['tags']}',
        'desc': '{check_config['desc']}',
        'schedule': '{check_config['schedule']}',
        'grace': {check_config['grace']}
    }}
)
if created:
    print(f"Created check with UUID {uuid}")
else:
    print(f"Updated check with UUID {uuid}")
"""
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"  ✓ Check created/updated via management command")
            return True
        else:
            print(f"  ❌ Management command failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ Management command timed out")
        return False
    except Exception as e:
        print(f"  ❌ Failed to run management command: {e}")
        return False


if __name__ == '__main__':
    # Vérifier si on est dans le bon répertoire
    if not os.path.exists('scripts/sync_healthchecks_uuids.py'):
        print("❌ Please run this script from the backend directory")
        sys.exit(1)

    # Synchroniser les checks
    success = sync_all_checks()

    # Si certains checks ont échoué, proposer l'alternative via management command
    if not success:
        print("\n💡 Alternative: You can create checks with specific UUIDs using the Django management command")
        print("   Run: docker-compose exec healthchecks python manage.py shell")
        print("   Then manually create checks with the desired UUIDs")

    sys.exit(0 if success else 1)