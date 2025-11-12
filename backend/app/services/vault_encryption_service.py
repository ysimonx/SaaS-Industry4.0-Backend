"""
Service de chiffrement/déchiffrement utilisant Vault Transit Engine.
Les tokens Azure AD sont chiffrés avec une clé spécifique par tenant pour isolation maximale.
"""

import hvac
import base64
import logging
from typing import Optional, List
from flask import current_app

logger = logging.getLogger(__name__)


class VaultEncryptionService:
    """
    Service de chiffrement/déchiffrement utilisant Vault Transit Engine.
    Les tokens sont chiffrés avec une clé spécifique par tenant pour isolation maximale.
    """

    def __init__(self):
        """
        Initialise le service avec le client Vault.
        Utilise la configuration Vault depuis les variables d'environnement.
        """
        from app.utils.vault_client import VaultClient
        import os

        # Initialiser le client Vault
        vault_addr = os.environ.get("VAULT_ADDR")
        role_id = os.environ.get("VAULT_ROLE_ID")
        secret_id = os.environ.get("VAULT_SECRET_ID")

        if not all([vault_addr, role_id, secret_id]):
            raise ValueError(
                "VAULT_ADDR, VAULT_ROLE_ID et VAULT_SECRET_ID doivent être définis"
            )

        self.vault_client = VaultClient(
            vault_addr=vault_addr,
            role_id=role_id,
            secret_id=secret_id
        )

        # Authentifier si pas déjà fait
        if not self.vault_client.is_authenticated():
            self.vault_client.authenticate()

        self.client = self.vault_client.client
        self.transit_mount = 'transit'

        logger.info("VaultEncryptionService initialized")

    def _get_encryption_key_name(self, tenant_id: str) -> str:
        """
        Génère le nom de la clé de chiffrement pour un tenant.
        Chaque tenant a sa propre clé de chiffrement dans Vault.

        Args:
            tenant_id: UUID du tenant

        Returns:
            Nom de la clé Vault pour ce tenant
        """
        return f"azure-tokens-{tenant_id}"

    def ensure_encryption_key(self, tenant_id: str) -> None:
        """
        Crée la clé de chiffrement pour un tenant si elle n'existe pas.
        Appelé lors de la configuration SSO du tenant.

        Args:
            tenant_id: UUID du tenant

        Raises:
            hvac.exceptions.VaultError: En cas d'erreur Vault
        """
        key_name = self._get_encryption_key_name(tenant_id)

        try:
            # Vérifier si la clé existe
            self.client.secrets.transit.read_key(
                name=key_name,
                mount_point=self.transit_mount
            )
            logger.info(f"Encryption key already exists for tenant {tenant_id}")

        except hvac.exceptions.InvalidPath:
            # Créer la clé si elle n'existe pas
            logger.info(f"Creating encryption key for tenant {tenant_id}")

            self.client.secrets.transit.create_key(
                name=key_name,
                mount_point=self.transit_mount,
                convergent_encryption=False,  # Tokens uniques
                derived=False,
                exportable=False,  # Clé non exportable pour sécurité
                allow_plaintext_backup=False
            )

            # Configurer auto-rotation (optionnel)
            self.client.secrets.transit.configure_key(
                name=key_name,
                mount_point=self.transit_mount,
                min_decryption_version=1,
                min_encryption_version=0,
                auto_rotate_period='30d'  # Rotation automatique tous les 30 jours
            )

            logger.info(f"Encryption key created for tenant {tenant_id}")

    def encrypt_token(self, tenant_id: str, token: str) -> Optional[str]:
        """
        Chiffre un token Azure AD avec la clé du tenant.
        Retourne le token chiffré au format Vault (vault:v1:...).

        Args:
            tenant_id: UUID du tenant
            token: Token en clair à chiffrer

        Returns:
            Token chiffré au format Vault, ou None si token est vide

        Raises:
            hvac.exceptions.VaultError: En cas d'erreur Vault
        """
        if not token:
            return None

        key_name = self._get_encryption_key_name(tenant_id)

        try:
            # Encoder le token en base64 (requis par Vault)
            plaintext_b64 = base64.b64encode(token.encode()).decode()

            # Chiffrer avec Vault
            response = self.client.secrets.transit.encrypt_data(
                name=key_name,
                mount_point=self.transit_mount,
                plaintext=plaintext_b64
            )

            encrypted_token = response['data']['ciphertext']
            logger.debug(f"Token encrypted for tenant {tenant_id}")

            return encrypted_token

        except Exception as e:
            logger.error(f"Token encryption failed for tenant {tenant_id}: {str(e)}")
            raise

    def decrypt_token(self, tenant_id: str, encrypted_token: str) -> Optional[str]:
        """
        Déchiffre un token Azure AD avec la clé du tenant.

        Args:
            tenant_id: UUID du tenant
            encrypted_token: Token chiffré au format Vault

        Returns:
            Token en clair, ou None si le token est vide ou déchiffrement échoue

        Raises:
            hvac.exceptions.VaultError: En cas d'erreur Vault
        """
        if not encrypted_token:
            return None

        key_name = self._get_encryption_key_name(tenant_id)

        try:
            # Déchiffrer avec Vault
            response = self.client.secrets.transit.decrypt_data(
                name=key_name,
                mount_point=self.transit_mount,
                ciphertext=encrypted_token
            )

            # Décoder depuis base64
            plaintext_b64 = response['data']['plaintext']
            decrypted_token = base64.b64decode(plaintext_b64).decode()

            logger.debug(f"Token decrypted for tenant {tenant_id}")
            return decrypted_token

        except Exception as e:
            # Log l'erreur mais ne pas exposer les détails
            logger.error(f"Token decryption failed for tenant {tenant_id}: {str(e)}")
            return None

    def rotate_encryption_key(self, tenant_id: str) -> None:
        """
        Effectue une rotation de la clé de chiffrement du tenant.
        Les anciens tokens restent déchiffrables.

        Args:
            tenant_id: UUID du tenant

        Raises:
            hvac.exceptions.VaultError: En cas d'erreur Vault
        """
        key_name = self._get_encryption_key_name(tenant_id)

        try:
            self.client.secrets.transit.rotate_key(
                name=key_name,
                mount_point=self.transit_mount
            )
            logger.info(f"Encryption key rotated for tenant {tenant_id}")

        except Exception as e:
            logger.error(f"Key rotation failed for tenant {tenant_id}: {str(e)}")
            raise

    def rewrap_tokens(self, tenant_id: str, encrypted_tokens: List[Optional[str]]) -> List[Optional[str]]:
        """
        Re-chiffre les tokens avec la dernière version de la clé après rotation.
        Améliore la sécurité en utilisant la clé la plus récente.

        Args:
            tenant_id: UUID du tenant
            encrypted_tokens: Liste de tokens chiffrés à re-wrapper

        Returns:
            Liste de tokens re-chiffrés avec la nouvelle version de clé

        Raises:
            hvac.exceptions.VaultError: En cas d'erreur Vault
        """
        key_name = self._get_encryption_key_name(tenant_id)

        rewrapped = []
        for token in encrypted_tokens:
            if token:
                try:
                    response = self.client.secrets.transit.rewrap_data(
                        name=key_name,
                        mount_point=self.transit_mount,
                        ciphertext=token
                    )
                    rewrapped.append(response['data']['ciphertext'])
                    logger.debug(f"Token rewrapped for tenant {tenant_id}")

                except Exception as e:
                    logger.error(f"Token rewrap failed for tenant {tenant_id}: {str(e)}")
                    # En cas d'erreur, garder le token original
                    rewrapped.append(token)
            else:
                rewrapped.append(None)

        return rewrapped

    def is_healthy(self) -> bool:
        """
        Vérifie que le service Vault est accessible et opérationnel.

        Returns:
            True si Vault est accessible, False sinon
        """
        try:
            # Vérifier la connexion à Vault
            if not self.vault_client.is_authenticated():
                logger.warning("Vault client not authenticated")
                return False

            # Vérifier que Transit Engine est accessible
            # On tente de lister les clés, mais on accepte une liste vide
            try:
                self.client.secrets.transit.list_keys(
                    mount_point=self.transit_mount
                )
            except hvac.exceptions.InvalidPath:
                # Pas de clés = Transit Engine vide, mais accessible
                logger.debug("Transit Engine is empty but accessible")
                pass

            logger.debug("Vault health check passed")
            return True

        except Exception as e:
            logger.error(f"Vault health check failed: {str(e)}")
            return False
