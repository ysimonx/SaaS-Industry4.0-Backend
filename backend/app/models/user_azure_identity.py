"""
User Azure Identity Model

This module defines the UserAzureIdentity model for managing Azure AD identities
for users across different tenants in the multi-tenant SaaS platform.

Key features:
- Links users to their Azure AD identities per tenant
- A user can have different Azure Object IDs for different tenants
- Stores encrypted OAuth2 tokens (access, refresh, ID tokens)
- Supports token encryption via HashiCorp Vault Transit Engine
- Tracks token expiration and last synchronization times
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, UniqueConstraint, Index
from sqlalchemy.orm import relationship

from .base import BaseModel
from ..extensions import db

logger = logging.getLogger(__name__)


class UserAzureIdentity(BaseModel, db.Model):
    """
    Table linking users to their Azure AD identities per tenant.

    A user can have different Object IDs in different Azure AD instances.
    This model maintains that mapping and stores encrypted OAuth2 tokens.

    Attributes:
        user_id (UUID): Foreign key to the user
        tenant_id (UUID): Foreign key to the tenant
        azure_object_id (str): Object ID in the Azure AD instance
        azure_tenant_id (str): Azure AD tenant ID
        azure_upn (str): UserPrincipalName in Azure AD
        azure_display_name (str): Display name in Azure AD
        encrypted_access_token (str): Encrypted access token (Vault format)
        encrypted_refresh_token (str): Encrypted refresh token
        encrypted_id_token (str): Encrypted ID token
        token_expires_at (datetime): Access token expiration time
        refresh_token_expires_at (datetime): Refresh token expiration time
        last_sync (datetime): Last synchronization with Azure AD
        sso_metadata (dict): Additional SSO metadata (job title, department, etc.)

    Relationships:
        user: Many-to-one relationship with User model
        tenant: Many-to-one relationship with Tenant model

    Inherited from BaseModel:
        id (UUID): Primary key
        created_at (datetime): Creation timestamp (UTC)
        updated_at (datetime): Last update timestamp (UTC)
        created_by (UUID): User who created this record
    """

    __tablename__ = 'user_azure_identities'

    # Foreign keys
    user_id = db.Column(
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    tenant_id = db.Column(
        db.ForeignKey('tenants.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Azure AD identifiers
    azure_object_id = db.Column(String(255), nullable=False, index=True)
    # Object ID in the Azure AD instance

    azure_tenant_id = db.Column(String(255), nullable=False, index=True)
    # ID of the Azure AD tenant

    azure_upn = db.Column(String(255))
    # UserPrincipalName in Azure AD (e.g., user@company.com)

    azure_display_name = db.Column(String(255))
    # Display name in Azure AD

    # Encrypted OAuth2 tokens (using Vault Transit Engine)
    encrypted_access_token = db.Column(Text)
    # Access token encrypted by Vault (format: vault:v1:...)

    encrypted_refresh_token = db.Column(Text)
    # Refresh token encrypted by Vault

    encrypted_id_token = db.Column(Text)
    # ID token encrypted by Vault

    # Token expiration tracking
    token_expires_at = db.Column(db.DateTime(timezone=True))
    # Expiration time of the access token

    refresh_token_expires_at = db.Column(db.DateTime(timezone=True))
    # Expiration time of the refresh token

    # Synchronization tracking
    last_sync = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    # SSO metadata (job title, department, etc. from Microsoft Graph)
    sso_metadata = db.Column(db.JSON, default=dict)
    # Additional SSO metadata specific to this Azure identity

    # Relationships
    user = relationship('User', back_populates='azure_identities')
    tenant = relationship('Tenant')

    # Constraints
    __table_args__ = (
        # A user can have only one Azure identity per tenant
        UniqueConstraint('user_id', 'tenant_id', name='_user_tenant_azure_uc'),
    )

    def __init__(self, **kwargs):
        """
        Initialize a new Azure identity record.

        Sets last_sync to current time if not provided.
        """
        if 'last_sync' not in kwargs:
            kwargs['last_sync'] = datetime.utcnow()

        super().__init__(**kwargs)
        logger.info(
            f"UserAzureIdentity initialized: user_id={self.user_id}, "
            f"tenant_id={self.tenant_id}, azure_object_id={self.azure_object_id}"
        )

    @classmethod
    def find_or_create(cls, user_id: str, tenant_id: str,
                      azure_object_id: str, azure_tenant_id: str,
                      **kwargs) -> 'UserAzureIdentity':
        """
        Find or create an Azure identity for a user on a tenant.

        Args:
            user_id: UUID of the user
            tenant_id: UUID of the tenant
            azure_object_id: Azure AD Object ID
            azure_tenant_id: Azure AD tenant ID
            **kwargs: Additional fields to set on creation

        Returns:
            UserAzureIdentity instance (existing or newly created)
        """
        identity = cls.query.filter_by(
            user_id=user_id,
            tenant_id=tenant_id
        ).first()

        if not identity:
            identity = cls(
                user_id=user_id,
                tenant_id=tenant_id,
                azure_object_id=azure_object_id,
                azure_tenant_id=azure_tenant_id,
                **kwargs
            )
            db.session.add(identity)
            logger.info(f"Created new Azure identity for user {user_id} on tenant {tenant_id}")
        else:
            # Update Azure identifiers if they've changed
            if identity.azure_object_id != azure_object_id:
                logger.warning(
                    f"Azure Object ID changed for user {user_id} on tenant {tenant_id}: "
                    f"{identity.azure_object_id} -> {azure_object_id}"
                )
                identity.azure_object_id = azure_object_id

            if identity.azure_tenant_id != azure_tenant_id:
                logger.warning(
                    f"Azure Tenant ID changed for user {user_id} on tenant {tenant_id}: "
                    f"{identity.azure_tenant_id} -> {azure_tenant_id}"
                )
                identity.azure_tenant_id = azure_tenant_id

            # Update additional fields
            for key, value in kwargs.items():
                if hasattr(identity, key):
                    setattr(identity, key, value)

            identity.last_sync = datetime.utcnow()
            logger.info(f"Updated existing Azure identity for user {user_id} on tenant {tenant_id}")

        return identity

    def save_tokens(self, access_token: str, refresh_token: str, id_token: str,
                   expires_in: int, refresh_expires_in: int = None) -> None:
        """
        Save OAuth2 tokens securely using encryption.

        This method should be extended to use Vault Transit Engine for encryption
        in production environments.

        Args:
            access_token: Azure AD access token
            refresh_token: Azure AD refresh token
            id_token: Azure AD ID token
            expires_in: Access token lifetime in seconds
            refresh_expires_in: Refresh token lifetime in seconds (optional)
        """
        try:
            # In production, these should be encrypted using Vault Transit Engine
            # For now, we'll store them as-is with a warning
            logger.warning(
                "Tokens are being stored without Vault encryption. "
                "Implement VaultEncryptionService for production use."
            )

            # For development - store tokens directly (NOT FOR PRODUCTION!)
            self.encrypted_access_token = f"dev:{access_token}"
            self.encrypted_refresh_token = f"dev:{refresh_token}"
            self.encrypted_id_token = f"dev:{id_token}"

            # Calculate expiration times
            now = datetime.utcnow()
            self.token_expires_at = now + timedelta(seconds=expires_in)

            if refresh_expires_in:
                self.refresh_token_expires_at = now + timedelta(seconds=refresh_expires_in)
            else:
                # Default refresh token expiration (7 days)
                self.refresh_token_expires_at = now + timedelta(days=7)

            self.last_sync = now

            logger.info(
                f"Tokens saved for user {self.user_id} on tenant {self.tenant_id}. "
                f"Access token expires at {self.token_expires_at}"
            )

        except Exception as e:
            logger.error(f"Error saving tokens: {str(e)}", exc_info=True)
            raise

    def get_decrypted_tokens(self) -> Dict[str, Optional[str]]:
        """
        Get decrypted OAuth2 tokens.

        This method should be extended to use Vault Transit Engine for decryption
        in production environments.

        Returns:
            Dictionary with decrypted tokens (access_token, refresh_token, id_token)
        """
        try:
            # In production, these should be decrypted using Vault Transit Engine
            # For development, we're using a simple prefix
            tokens = {
                'access_token': None,
                'refresh_token': None,
                'id_token': None
            }

            if self.encrypted_access_token and self.encrypted_access_token.startswith('dev:'):
                tokens['access_token'] = self.encrypted_access_token[4:]

            if self.encrypted_refresh_token and self.encrypted_refresh_token.startswith('dev:'):
                tokens['refresh_token'] = self.encrypted_refresh_token[4:]

            if self.encrypted_id_token and self.encrypted_id_token.startswith('dev:'):
                tokens['id_token'] = self.encrypted_id_token[4:]

            return tokens

        except Exception as e:
            logger.error(f"Error decrypting tokens: {str(e)}", exc_info=True)
            return {'access_token': None, 'refresh_token': None, 'id_token': None}

    def is_access_token_expired(self) -> bool:
        """
        Check if the access token is expired.

        Returns:
            True if expired or no expiration set, False otherwise
        """
        if not self.token_expires_at:
            return True

        return datetime.utcnow() > self.token_expires_at

    def is_refresh_token_expired(self) -> bool:
        """
        Check if the refresh token is expired.

        Returns:
            True if expired or no expiration set, False otherwise
        """
        if not self.refresh_token_expires_at:
            return True

        return datetime.utcnow() > self.refresh_token_expires_at

    def needs_token_refresh(self, buffer_minutes: int = 5) -> bool:
        """
        Check if the access token needs refreshing.

        Args:
            buffer_minutes: Minutes before expiration to trigger refresh

        Returns:
            True if token needs refresh, False otherwise
        """
        if not self.token_expires_at:
            return True

        buffer = timedelta(minutes=buffer_minutes)
        return datetime.utcnow() + buffer > self.token_expires_at

    def update_from_azure_claims(self, azure_claims: dict) -> None:
        """
        Update identity information from Azure AD claims.

        Args:
            azure_claims: Dictionary of claims from Azure AD token
        """
        # Update Azure AD attributes
        if 'upn' in azure_claims:
            self.azure_upn = azure_claims['upn']
        elif 'preferred_username' in azure_claims:
            self.azure_upn = azure_claims['preferred_username']

        if 'name' in azure_claims:
            self.azure_display_name = azure_claims['name']

        # Update object and tenant IDs if present
        if 'oid' in azure_claims:
            if self.azure_object_id != azure_claims['oid']:
                logger.warning(
                    f"Azure Object ID mismatch for user {self.user_id}: "
                    f"expected {self.azure_object_id}, got {azure_claims['oid']}"
                )

        if 'tid' in azure_claims:
            if self.azure_tenant_id != azure_claims['tid']:
                logger.warning(
                    f"Azure Tenant ID mismatch for user {self.user_id}: "
                    f"expected {self.azure_tenant_id}, got {azure_claims['tid']}"
                )

        self.last_sync = datetime.utcnow()
        logger.info(f"Updated Azure identity from claims for user {self.user_id}")

    def clear_tokens(self) -> None:
        """
        Clear all stored tokens (used on logout or revocation).
        """
        self.encrypted_access_token = None
        self.encrypted_refresh_token = None
        self.encrypted_id_token = None
        self.token_expires_at = None
        self.refresh_token_expires_at = None

        logger.info(f"Cleared tokens for user {self.user_id} on tenant {self.tenant_id}")

    @classmethod
    def find_by_azure_id(cls, azure_object_id: str, azure_tenant_id: str) -> Optional['UserAzureIdentity']:
        """
        Find a user's Azure identity by Azure AD identifiers.

        Args:
            azure_object_id: Azure AD Object ID
            azure_tenant_id: Azure AD Tenant ID

        Returns:
            UserAzureIdentity instance if found, None otherwise
        """
        return cls.query.filter_by(
            azure_object_id=azure_object_id,
            azure_tenant_id=azure_tenant_id
        ).first()

    @classmethod
    def get_user_identities(cls, user_id: str) -> list['UserAzureIdentity']:
        """
        Get all Azure identities for a user across all tenants.

        Args:
            user_id: UUID of the user

        Returns:
            List of UserAzureIdentity instances
        """
        return cls.query.filter_by(user_id=user_id).all()

    @classmethod
    def get_tenant_identities(cls, tenant_id: str) -> list['UserAzureIdentity']:
        """
        Get all Azure identities for a specific tenant.

        Args:
            tenant_id: UUID of the tenant

        Returns:
            List of UserAzureIdentity instances
        """
        return cls.query.filter_by(tenant_id=tenant_id).all()

    def to_dict(self, exclude: list = None, include_tokens: bool = False) -> dict:
        """
        Convert Azure identity to dictionary for JSON serialization.

        Args:
            exclude: List of fields to exclude from output
            include_tokens: If True, include token expiration info (not the tokens themselves)

        Returns:
            Dictionary representation of the Azure identity
        """
        # Never include encrypted tokens in serialization
        if exclude is None:
            exclude = []
        exclude.extend(['encrypted_access_token', 'encrypted_refresh_token', 'encrypted_id_token'])

        data = super().to_dict(exclude=exclude)

        if include_tokens:
            data['access_token_expired'] = self.is_access_token_expired()
            data['refresh_token_expired'] = self.is_refresh_token_expired()
            data['needs_refresh'] = self.needs_token_refresh()

        return data

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<UserAzureIdentity(id={self.id}, user_id={self.user_id}, "
            f"tenant_id={self.tenant_id}, azure_object_id={self.azure_object_id})>"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        return (
            f"Azure Identity for user {self.user_id} on tenant {self.tenant_id} "
            f"(Azure ID: {self.azure_object_id})"
        )