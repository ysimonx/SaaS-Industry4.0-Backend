"""
Enhanced Healthchecks.io API client with auto-provisioning
"""

import os
import time
import requests
import logging
from typing import Optional, Dict, Any
from threading import Lock

logger = logging.getLogger(__name__)


# Configuration par défaut des checks
DEFAULT_CHECKS = {
    'HC_CHECK_POSTGRES': {
        'name': 'PostgreSQL Database',
        'tags': 'database infrastructure tier1',
        'timeout': 120,
        'grace': 240,
        'schedule': '*/2 * * * *'
    },
    'HC_CHECK_REDIS': {
        'name': 'Redis Cache/Broker',
        'tags': 'cache redis infrastructure tier1',
        'timeout': 120,
        'grace': 240,
        'schedule': '*/2 * * * *'
    },
    'HC_CHECK_API': {
        'name': 'Flask API',
        'tags': 'api application tier1',
        'timeout': 180,
        'grace': 360,
        'schedule': '*/3 * * * *'
    },
    'HC_CHECK_CELERY_WORKER': {
        'name': 'Celery Worker SSO',
        'tags': 'celery worker sso tier1',
        'timeout': 300,
        'grace': 600,
        'schedule': '*/5 * * * *'
    },
    'HC_CHECK_CELERY_BEAT': {
        'name': 'Celery Beat Scheduler',
        'tags': 'celery beat scheduler tier1',
        'timeout': 300,
        'grace': 600,
        'schedule': '*/5 * * * *'
    },
    'HC_CHECK_KAFKA': {
        'name': 'Kafka Broker',
        'tags': 'kafka messaging tier2',
        'timeout': 120,
        'grace': 300,
        'schedule': '*/2 * * * *'
    },
    'HC_CHECK_KAFKA_CONSUMER': {
        'name': 'Kafka Consumer',
        'tags': 'kafka consumer worker tier2',
        'timeout': 120,
        'grace': 300,
        'schedule': '*/2 * * * *'
    },
    'HC_CHECK_MINIO': {
        'name': 'MinIO S3 Storage',
        'tags': 'minio storage s3 tier2',
        'timeout': 300,
        'grace': 600,
        'schedule': '*/5 * * * *'
    },
    'HC_CHECK_VAULT': {
        'name': 'Vault Secrets',
        'tags': 'vault security secrets tier2',
        'timeout': 300,
        'grace': 600,
        'schedule': '*/5 * * * *'
    },
    'HC_CHECK_SSO_TOKEN_REFRESH': {
        'name': 'SSO Token Refresh',
        'tags': 'task scheduled sso',
        'timeout': 900,
        'grace': 300,
        'schedule': '*/15 * * * *'
    },
    'HC_CHECK_HEALTH_TASK': {
        'name': 'Health Check Task',
        'tags': 'task scheduled monitoring',
        'timeout': 300,
        'grace': 120,
        'schedule': '*/5 * * * *'
    },
    'HC_CHECK_TOKEN_CLEANUP': {
        'name': 'Token Cleanup',
        'tags': 'task scheduled maintenance',
        'timeout': 86400,
        'grace': 3600,
        'schedule': '0 2 * * *'
    },
    'HC_CHECK_KEY_ROTATION': {
        'name': 'Encryption Key Rotation',
        'tags': 'task scheduled security',
        'timeout': 2678400,
        'grace': 7200,
        'schedule': '0 3 1 * *'
    },
    'HC_CHECK_COMPREHENSIVE': {
        'name': 'Comprehensive Health Check',
        'tags': 'monitoring global all',
        'timeout': 600,
        'grace': 600,
        'schedule': '*/10 * * * *'
    }
}


class EnhancedHealthchecksClient:
    """Enhanced client for Healthchecks.io with auto-provisioning"""

    def __init__(self):
        self.enabled = os.getenv('HEALTHCHECKS_ENABLED', 'false').lower() == 'true'
        self.api_url = os.getenv('HEALTHCHECKS_API_URL', 'http://healthchecks:8000/api/v1')
        self.ping_url = os.getenv('HEALTHCHECKS_PING_URL', 'http://healthchecks:8000/ping')
        self.api_key = os.getenv('HEALTHCHECKS_API_KEY')
        self.timeout = int(os.getenv('HEALTHCHECKS_CHECK_TIMEOUT', '30'))
        self.retry_count = int(os.getenv('HEALTHCHECKS_RETRY_COUNT', '3'))
        self.retry_delay = int(os.getenv('HEALTHCHECKS_RETRY_DELAY', '10'))

        # Auto-provisioning settings
        self.auto_provision = os.getenv('HEALTHCHECKS_AUTO_PROVISION', 'true').lower() == 'true'
        self._check_cache = {}  # Cache pour éviter les requêtes répétées
        self._cache_lock = Lock()
        self._provisioned_checks = set()  # Track checks we've already tried to provision

        if self.enabled and not self.api_key:
            logger.warning("Healthchecks enabled but API key not configured")
            self.enabled = False

        if self.enabled:
            logger.info(f"Enhanced Healthchecks client initialized (API: {self.api_url}, auto-provision: {self.auto_provision})")

    def _get_check_env_var(self, check_id: str) -> Optional[str]:
        """Trouve la variable d'environnement correspondant à un check ID"""
        for env_var in DEFAULT_CHECKS.keys():
            if os.getenv(env_var) == check_id:
                return env_var
        return None

    def _ensure_check_exists(self, check_id: str) -> bool:
        """
        S'assure qu'un check existe, le crée si nécessaire et si auto-provision est activé

        Returns:
            True si le check existe ou a été créé, False sinon
        """
        if not self.auto_provision:
            return True  # Assume it exists if auto-provision is disabled

        # Check if we've already tried to provision this check
        if check_id in self._provisioned_checks:
            return check_id in self._check_cache

        self._provisioned_checks.add(check_id)

        # Vérifier le cache
        with self._cache_lock:
            if check_id in self._check_cache:
                return True

        # Vérifier si le check existe
        url = f"{self.api_url}/checks/{check_id}"
        headers = {'X-Api-Key': self.api_key}

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            if response.status_code == 200:
                # Le check existe, le mettre en cache
                with self._cache_lock:
                    self._check_cache[check_id] = response.json()
                return True
            elif response.status_code == 404:
                # Le check n'existe pas, essayer de le créer
                logger.info(f"Check {check_id} not found, attempting to create...")

                # Trouver la configuration pour ce check
                env_var = self._get_check_env_var(check_id)
                if env_var and env_var in DEFAULT_CHECKS:
                    config = DEFAULT_CHECKS[env_var]
                    created = self._create_check_with_id(check_id, config)
                    if created:
                        logger.info(f"Successfully created check {check_id}")
                        with self._cache_lock:
                            self._check_cache[check_id] = created
                        return True
                    else:
                        logger.warning(f"Failed to create check {check_id}")
                else:
                    logger.warning(f"No configuration found for check {check_id}")

                return False
            else:
                logger.warning(f"Unexpected response when checking {check_id}: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking if {check_id} exists: {str(e)}")
            return False

    def _create_check_with_id(self, check_id: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Tente de créer un check avec un ID spécifique
        Note: L'API publique de Healthchecks.io ne permet pas toujours de spécifier l'UUID
        """
        url = f"{self.api_url}/checks/"
        headers = {
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        }

        data = {
            'name': config['name'],
            'tags': config['tags'],
            'timeout': config.get('timeout', 3600),
            'grace': config.get('grace', 3600),
            'schedule': config.get('schedule', '* * * * *'),
            'tz': 'UTC',
            'channels': '*'
        }

        # Tentative de spécifier l'UUID (ne fonctionne pas toujours)
        data['unique'] = [check_id]

        try:
            response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
            if response.status_code in [200, 201]:
                check = response.json()
                created_id = check.get('ping_url', '').split('/')[-1]

                if created_id == check_id:
                    logger.info(f"Check created with correct ID: {check_id}")
                    return check
                else:
                    # L'UUID ne correspond pas, essayer de mettre à jour .env.healthchecks
                    logger.warning(f"Check created with different ID: {created_id} (wanted: {check_id})")
                    env_var = self._get_check_env_var(check_id)
                    if env_var:
                        logger.info(f"Update your .env.healthchecks: {env_var}={created_id}")
                        self._update_env_file(env_var, created_id)
                    # On retourne quand même le check créé
                    return check
            else:
                logger.error(f"Failed to create check: {response.status_code} - {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating check: {str(e)}")
            return None

    def _update_env_file(self, env_var: str, new_uuid: str):
        """Met à jour le fichier .env.healthchecks avec le nouvel UUID"""
        try:
            env_file = '.env.healthchecks'
            if not os.path.exists(env_file):
                logger.warning(f"File {env_file} not found, cannot update UUID")
                return

            with open(env_file, 'r') as f:
                lines = f.readlines()

            updated = False
            for i, line in enumerate(lines):
                if line.startswith(f"{env_var}="):
                    lines[i] = f"{env_var}={new_uuid}\n"
                    updated = True
                    break

            if updated:
                with open(env_file, 'w') as f:
                    f.writelines(lines)
                logger.info(f"Updated {env_file} with new UUID for {env_var}")
            else:
                # Ajouter à la fin si non trouvé
                with open(env_file, 'a') as f:
                    f.write(f"\n{env_var}={new_uuid}\n")
                logger.info(f"Added {env_var} to {env_file}")

        except Exception as e:
            logger.error(f"Failed to update .env.healthchecks: {str(e)}")

    def ping(self, check_id: str, status: str = '') -> bool:
        """
        Envoie un ping à Healthchecks, crée le check si nécessaire

        Args:
            check_id: UUID du check
            status: '', '/start', '/fail', ou code de sortie

        Returns:
            True si succès, False sinon
        """
        if not self.enabled:
            return True

        # Validate check_id format
        if not check_id or len(check_id) != 36 or check_id.count('-') != 4:
            logger.warning(f"Invalid check_id format, skipping ping: {check_id}")
            return False

        # Ensure check exists (create if necessary and auto-provision is enabled)
        if self.auto_provision:
            if not self._ensure_check_exists(check_id):
                logger.warning(f"Check {check_id} does not exist and could not be created")
                # Continue anyway, maybe it will work

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
                elif response.status_code == 404 and self.auto_provision and attempt == 0:
                    # Try to create the check on first attempt
                    logger.info(f"Check {check_id} returned 404, attempting to create...")
                    if self._ensure_check_exists(check_id):
                        # Retry the ping
                        continue
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

    def list_checks(self, tag: Optional[str] = None) -> list:
        """Liste tous les checks, optionnellement filtrés par tag"""
        if not self.enabled:
            return []

        url = f"{self.api_url}/checks/"
        headers = {'X-Api-Key': self.api_key}
        params = {'tag': tag} if tag else {}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
            if response.status_code == 200:
                return response.json().get('checks', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing checks: {str(e)}")

        return []

    def get_status(self) -> Optional[Dict[str, Any]]:
        """Récupère le statut global de tous les checks"""
        if not self.enabled:
            return None

        url = f"{self.api_url}/checks/"
        headers = {'X-Api-Key': self.api_key}

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            if response.status_code == 200:
                checks = response.json().get('checks', [])

                status = {
                    'total': len(checks),
                    'up': sum(1 for c in checks if c.get('status') == 'up'),
                    'down': sum(1 for c in checks if c.get('status') == 'down'),
                    'paused': sum(1 for c in checks if c.get('status') == 'paused'),
                    'new': sum(1 for c in checks if c.get('status') == 'new'),
                    'checks': checks
                }

                return status
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting status: {str(e)}")

        return None


# Instance singleton avec auto-provisioning
enhanced_healthchecks = EnhancedHealthchecksClient()