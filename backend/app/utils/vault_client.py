"""
Module de gestion de l'authentification et des interactions avec HashiCorp Vault.
Utilise la méthode AppRole pour l'authentification.
"""

import os
import logging
from typing import Dict, Any, Optional
import hvac
from hvac.exceptions import VaultError, InvalidPath

logger = logging.getLogger(__name__)


class VaultClient:
    """
    Client Vault pour l'authentification AppRole et la récupération de secrets.
    """

    def __init__(
        self,
        vault_addr: Optional[str] = None,
        role_id: Optional[str] = None,
        secret_id: Optional[str] = None,
    ):
        """
        Initialise le client Vault.

        Args:
            vault_addr: URL du serveur Vault (ex: http://vault:8200)
            role_id: Role ID pour l'authentification AppRole
            secret_id: Secret ID pour l'authentification AppRole
        """
        self.vault_addr = vault_addr or os.environ.get("VAULT_ADDR")
        self.role_id = role_id or os.environ.get("VAULT_ROLE_ID")
        self.secret_id = secret_id or os.environ.get("VAULT_SECRET_ID")

        if not all([self.vault_addr, self.role_id, self.secret_id]):
            raise ValueError(
                "VAULT_ADDR, VAULT_ROLE_ID et VAULT_SECRET_ID doivent être définis"
            )

        self.client: Optional[hvac.Client] = None
        self.token: Optional[str] = None
        self.token_ttl: int = 0

        logger.info(f"VaultClient initialisé avec l'adresse: {self.vault_addr}")

    def authenticate(self) -> str:
        """
        Authentifie l'application auprès de Vault en utilisant AppRole.

        Returns:
            str: Token Vault obtenu

        Raises:
            VaultError: En cas d'erreur d'authentification
        """
        try:
            # Créer un client Vault non authentifié
            self.client = hvac.Client(url=self.vault_addr)

            # Vérifier que Vault est accessible
            if not self.client.sys.is_initialized():
                raise VaultError("Vault n'est pas initialisé")

            if self.client.sys.is_sealed():
                raise VaultError("Vault est scellé (sealed)")

            logger.info("Connexion à Vault établie, tentative d'authentification AppRole...")

            # Authentification avec AppRole
            auth_response = self.client.auth.approle.login(
                role_id=self.role_id,
                secret_id=self.secret_id,
            )

            # Extraire le token et le TTL
            self.token = auth_response["auth"]["client_token"]
            self.token_ttl = auth_response["auth"]["lease_duration"]

            # Définir le token sur le client
            self.client.token = self.token

            logger.info(
                f"Authentification AppRole réussie. Token TTL: {self.token_ttl}s"
            )

            return self.token

        except VaultError as e:
            logger.error(f"Erreur d'authentification Vault: {e}")
            raise
        except Exception as e:
            logger.error(f"Erreur inattendue lors de l'authentification Vault: {e}")
            raise VaultError(f"Erreur inattendue: {e}")

    def get_secret(self, path: str) -> Dict[str, Any]:
        """
        Récupère un secret depuis Vault.

        Args:
            path: Chemin du secret (ex: "saas-project/docker/database")

        Returns:
            Dict contenant les données du secret

        Raises:
            VaultError: En cas d'erreur de récupération
        """
        if not self.client or not self.client.is_authenticated():
            logger.warning("Client non authentifié, tentative d'authentification...")
            self.authenticate()

        try:
            # Le chemin KV v2 nécessite le préfixe "secret/data/"
            logger.debug(f"Lecture du secret: secret/data/{path}")

            response = self.client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point="secret",
            )

            secret_data = response["data"]["data"]
            logger.info(f"Secret récupéré avec succès: {path}")

            return secret_data

        except InvalidPath:
            logger.error(f"Chemin de secret invalide ou inexistant: {path}")
            raise VaultError(f"Secret non trouvé: {path}")
        except VaultError as e:
            logger.error(f"Erreur lors de la récupération du secret {path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la lecture du secret {path}: {e}")
            raise VaultError(f"Erreur inattendue: {e}")

    def get_all_secrets(self, environment: str = "docker") -> Dict[str, Any]:
        """
        Récupère tous les secrets nécessaires pour l'application.

        Args:
            environment: Environnement (dev, docker, prod)

        Returns:
            Dict avec tous les secrets organisés par catégorie
        """
        secrets = {}

        # Liste des chemins de secrets à récupérer
        secret_paths = {
            "database": f"saas-project/{environment}/database",
            "jwt": f"saas-project/{environment}/jwt",
            "s3": f"saas-project/{environment}/s3",
        }

        for category, path in secret_paths.items():
            try:
                secrets[category] = self.get_secret(path)
            except VaultError as e:
                logger.error(f"Impossible de récupérer les secrets {category}: {e}")
                raise

        logger.info(f"Tous les secrets de l'environnement '{environment}' récupérés")
        return secrets

    def renew_token(self) -> int:
        """
        Renouvelle le token Vault actuel.

        Returns:
            int: Nouveau TTL du token en secondes

        Raises:
            VaultError: En cas d'erreur de renouvellement
        """
        if not self.client or not self.token:
            raise VaultError("Client non authentifié, impossible de renouveler le token")

        try:
            logger.info("Renouvellement du token Vault...")

            response = self.client.auth.token.renew_self()
            self.token_ttl = response["auth"]["lease_duration"]

            logger.info(f"Token renouvelé avec succès. Nouveau TTL: {self.token_ttl}s")

            return self.token_ttl

        except VaultError as e:
            logger.error(f"Erreur lors du renouvellement du token: {e}")
            raise
        except Exception as e:
            logger.error(f"Erreur inattendue lors du renouvellement: {e}")
            raise VaultError(f"Erreur inattendue: {e}")

    def get_token_ttl(self) -> int:
        """
        Récupère le TTL restant du token actuel.

        Returns:
            int: TTL en secondes
        """
        if not self.client or not self.token:
            return 0

        try:
            response = self.client.auth.token.lookup_self()
            return response["data"]["ttl"]
        except Exception as e:
            logger.warning(f"Impossible de récupérer le TTL du token: {e}")
            return 0

    def is_authenticated(self) -> bool:
        """
        Vérifie si le client est authentifié.

        Returns:
            bool: True si authentifié, False sinon
        """
        return self.client is not None and self.client.is_authenticated()
