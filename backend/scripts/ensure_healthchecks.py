#!/usr/bin/env python3
"""
Script pour s'assurer que les checks Healthchecks.io existent avec les UUIDs depuis .env.healthchecks
Utilise l'API Healthchecks pour créer les checks manquants.

Usage: python scripts/ensure_healthchecks.py [--force-recreate]
"""

import os
import sys
import requests
import time
import argparse
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Ajouter le backend au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration des checks
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


class HealthchecksManager:
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.api_url = api_url
        self.headers = {'X-Api-Key': api_key}

    def list_checks(self) -> List[Dict]:
        """Liste tous les checks existants"""
        try:
            response = requests.get(f"{self.api_url}/checks/", headers=self.headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('checks', [])
            else:
                print(f"❌ Failed to list checks: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error listing checks: {e}")
            return []

    def get_check(self, uuid: str) -> Optional[Dict]:
        """Récupère un check spécifique par UUID"""
        try:
            response = requests.get(f"{self.api_url}/checks/{uuid}", headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                print(f"❌ Failed to get check {uuid}: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error getting check {uuid}: {e}")
            return None

    def create_check(self, check_config: Dict, uuid: str = None) -> Optional[Dict]:
        """Crée un nouveau check"""
        data = {
            'name': check_config['name'],
            'tags': check_config['tags'],
            'timeout': check_config.get('timeout', 3600),
            'grace': check_config.get('grace', 3600),
            'desc': check_config.get('desc', ''),
            'channels': '*'
        }

        # Si on a un schedule cron, l'ajouter
        if 'schedule' in check_config:
            data['schedule'] = check_config['schedule']
            data['tz'] = 'UTC'

        # Si on veut un UUID spécifique (ne fonctionne pas toujours avec l'API publique)
        if uuid:
            data['unique'] = [uuid]

        try:
            response = requests.post(f"{self.api_url}/checks/", json=data, headers=self.headers, timeout=10)
            if response.status_code in [200, 201]:
                return response.json()
            else:
                print(f"❌ Failed to create check: {response.status_code}")
                if response.text:
                    print(f"   Error: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Error creating check: {e}")
            return None

    def update_check(self, uuid: str, check_config: Dict) -> bool:
        """Met à jour un check existant"""
        data = {
            'name': check_config['name'],
            'tags': check_config['tags'],
            'timeout': check_config.get('timeout', 3600),
            'grace': check_config.get('grace', 3600),
            'desc': check_config.get('desc', '')
        }

        if 'schedule' in check_config:
            data['schedule'] = check_config['schedule']
            data['tz'] = 'UTC'

        try:
            response = requests.post(f"{self.api_url}/checks/{uuid}", json=data, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return True
            else:
                print(f"❌ Failed to update check {uuid}: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error updating check {uuid}: {e}")
            return False

    def delete_check(self, uuid: str) -> bool:
        """Supprime un check"""
        try:
            response = requests.delete(f"{self.api_url}/checks/{uuid}", headers=self.headers, timeout=10)
            if response.status_code in [200, 204]:
                return True
            else:
                print(f"❌ Failed to delete check {uuid}: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error deleting check {uuid}: {e}")
            return False

    def pause_check(self, uuid: str) -> bool:
        """Met en pause un check"""
        try:
            response = requests.post(f"{self.api_url}/checks/{uuid}/pause", headers=self.headers, timeout=10)
            if response.status_code == 200:
                return True
            else:
                print(f"❌ Failed to pause check {uuid}: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error pausing check {uuid}: {e}")
            return False


def ensure_check_exists(manager: HealthchecksManager, env_var: str, uuid: str, check_config: Dict, force_recreate: bool = False) -> bool:
    """
    S'assure qu'un check existe avec l'UUID spécifié
    """
    print(f"\n📊 Checking {check_config['name']} ({env_var})")
    print(f"   UUID: {uuid}")

    # Vérifier si le check existe
    existing_check = manager.get_check(uuid)

    if existing_check:
        print(f"   ✓ Check exists")

        if force_recreate:
            print(f"   🔄 Force recreate enabled, updating check...")
            if manager.update_check(uuid, check_config):
                print(f"   ✓ Check updated successfully")
                return True
            else:
                print(f"   ❌ Failed to update check")
                return False
        else:
            # Vérifier si les paramètres sont corrects
            needs_update = False
            if existing_check.get('name') != check_config['name']:
                needs_update = True
                print(f"   ⚠️  Name mismatch: '{existing_check.get('name')}' vs '{check_config['name']}'")

            if needs_update:
                print(f"   🔄 Updating check...")
                if manager.update_check(uuid, check_config):
                    print(f"   ✓ Check updated successfully")
                    return True
                else:
                    print(f"   ❌ Failed to update check")
                    return False
            else:
                print(f"   ✓ Check configuration is correct")
                return True
    else:
        print(f"   ⚠️  Check does not exist")

        # Essayer de créer le check
        # Note: L'API publique de Healthchecks.io ne permet pas toujours de spécifier l'UUID
        # On va créer le check et récupérer l'UUID généré

        print(f"   📝 Creating new check...")
        created_check = manager.create_check(check_config)

        if created_check:
            created_uuid = created_check.get('ping_url', '').split('/')[-1]
            if created_uuid == uuid:
                print(f"   ✓ Check created with correct UUID: {uuid}")
                return True
            else:
                print(f"   ⚠️  Check created with different UUID: {created_uuid}")
                print(f"   ℹ️  Update .env.healthchecks with: {env_var}={created_uuid}")

                # Proposer de mettre à jour le fichier .env.healthchecks
                update_env_file(env_var, created_uuid)
                return True
        else:
            print(f"   ❌ Failed to create check")
            return False


def update_env_file(env_var: str, new_uuid: str):
    """Met à jour le fichier .env.healthchecks avec le nouvel UUID"""
    env_file = '.env.healthchecks'

    # Lire le fichier
    with open(env_file, 'r') as f:
        lines = f.readlines()

    # Chercher et remplacer la ligne
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{env_var}="):
            lines[i] = f"{env_var}={new_uuid}\n"
            updated = True
            break

    # Si pas trouvé, ajouter à la fin
    if not updated:
        # Trouver la section des check IDs
        insert_index = len(lines)
        for i, line in enumerate(lines):
            if "Check IDs" in line:
                # Chercher la fin de cette section
                for j in range(i+1, len(lines)):
                    if lines[j].strip() == "" or lines[j].startswith("#"):
                        continue
                    if not lines[j].startswith("HC_CHECK_"):
                        insert_index = j
                        break
                break

        lines.insert(insert_index, f"{env_var}={new_uuid}\n")

    # Écrire le fichier mis à jour
    with open(env_file, 'w') as f:
        f.writelines(lines)

    print(f"   ✓ Updated {env_file} with new UUID")


def main():
    parser = argparse.ArgumentParser(description='Ensure Healthchecks.io checks exist with specified UUIDs')
    parser.add_argument('--force-recreate', action='store_true', help='Force recreate all checks')
    parser.add_argument('--env-file', default='.env.healthchecks', help='Path to environment file')
    args = parser.parse_args()

    print("🏥 Ensuring Healthchecks.io checks exist with UUIDs from .env.healthchecks...")

    # Charger la configuration
    if not os.path.exists(args.env_file):
        print(f"❌ File {args.env_file} not found")
        return False

    load_dotenv(args.env_file)

    api_key = os.getenv('HEALTHCHECKS_API_KEY')
    api_url = os.getenv('HEALTHCHECKS_API_URL', 'http://healthchecks:8000/api/v1')

    if not api_key:
        print("❌ HEALTHCHECKS_API_KEY not found in .env.healthchecks")
        return False

    print(f"📡 API URL: {api_url}")
    print(f"🔑 API Key: {api_key[:10]}...")

    # Créer le manager
    manager = HealthchecksManager(api_key, api_url)

    # Lister les checks existants
    existing_checks = manager.list_checks()
    print(f"📊 Found {len(existing_checks)} existing checks in Healthchecks.io")

    success_count = 0
    failed_count = 0
    created_count = 0
    updated_count = 0

    # Traiter chaque check
    for env_var, check_config in CHECKS_CONFIG.items():
        uuid = os.getenv(env_var)

        if not uuid:
            print(f"\n⚠️  No UUID found for {env_var}, creating new check...")
            created_check = manager.create_check(check_config)
            if created_check:
                new_uuid = created_check.get('ping_url', '').split('/')[-1]
                update_env_file(env_var, new_uuid)
                created_count += 1
                success_count += 1
            else:
                failed_count += 1
        else:
            result = ensure_check_exists(manager, env_var, uuid, check_config, args.force_recreate)
            if result:
                success_count += 1
            else:
                failed_count += 1

        # Pause entre les opérations
        time.sleep(0.5)

    # Résumé
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"✓ Success: {success_count} checks")
    print(f"📝 Created: {created_count} new checks")
    print(f"❌ Failed: {failed_count} checks")

    if success_count > 0:
        print(f"\n🎯 Next steps:")
        print(f"1. Review updated .env.healthchecks file")
        print(f"2. Restart API and Celery workers to use new check IDs")
        print(f"3. Access Healthchecks UI at http://localhost:8000")
        print(f"4. Test with: docker-compose exec api python -m app.tasks.monitoring_tasks")

    return failed_count == 0


if __name__ == '__main__':
    # Vérifier si on est dans le bon répertoire
    if not os.path.exists('scripts/ensure_healthchecks.py'):
        print("❌ Please run this script from the backend directory")
        sys.exit(1)

    success = main()
    sys.exit(0 if success else 1)