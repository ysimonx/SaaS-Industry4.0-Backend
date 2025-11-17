"""
Healthchecks.io API client for monitoring services
"""

import os
import time
import requests
import logging
from typing import Optional, Dict, Any
# from urllib.parse import urljoin  # Not used anymore due to URL path issues

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

        if self.enabled:
            logger.info(f"Healthchecks client initialized (API: {self.api_url})")

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

        # IMPORTANT: Only ping if check_id is a valid UUID (not a slug)
        # This prevents auto-creation of checks when using API keys with auto-provisioning
        if not check_id or len(check_id) != 36 or check_id.count('-') != 4:
            logger.warning(f"Invalid check_id format, skipping ping: {check_id}")
            return False

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
        DEPRECATED: Check creation is disabled to prevent auto-creation issues.
        All checks should be created via scripts/setup_healthchecks.py

        This method now always returns None and logs a warning.
        """
        logger.error(
            f"BLOCKED: Attempted to create check '{name}' with tags '{tags}'. "
            f"Check creation is disabled. Use scripts/setup_healthchecks.py instead."
        )
        return None

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

    def get_check(self, check_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les détails d'un check"""
        if not self.enabled:
            return None

        url = f"{self.api_url}/checks/{check_id}"
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

    def delete_check(self, check_id: str) -> bool:
        """Supprime un check"""
        if not self.enabled:
            return False

        url = f"{self.api_url}/checks/{check_id}"
        headers = {'X-Api-Key': self.api_key}

        try:
            response = requests.delete(url, headers=headers, timeout=self.timeout)
            if response.status_code == 200:
                logger.info(f"Check {check_id} deleted")
                return True
            logger.error(f"Failed to delete check: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error deleting check: {str(e)}")

        return False

    def _update_check(self, check_id: str, data: Dict[str, Any]) -> bool:
        """Met à jour un check"""
        if not self.enabled:
            return False

        url = f"{self.api_url}/checks/{check_id}"
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


# Instance singleton
healthchecks = HealthchecksClient()