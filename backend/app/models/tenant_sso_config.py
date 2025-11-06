"""
Tenant SSO Configuration Model

This module defines the TenantSSOConfig model for managing SSO configurations
for each tenant in the multi-tenant SaaS platform.

Key features:
- One-to-one relationship with Tenant (a tenant can have only one SSO config)
- Supports Azure AD / Microsoft Entra ID in Public Application mode (no client_secret)
- Uses PKCE (Proof Key for Code Exchange) for secure OAuth2 flow
- Stores provider-specific configuration (client_id, redirect_uri, etc.)
- Flexible configuration metadata storage for additional options
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import BaseModel
from ..extensions import db

logger = logging.getLogger(__name__)


class TenantSSOConfig(BaseModel, db.Model):
    """
    SSO Configuration for each tenant.

    Implements a 1-to-1 relationship: A tenant can have only one SSO configuration.
    Uses the "Public Application" mode (Public Client) without client_secret.

    Attributes:
        tenant_id (UUID): Foreign key to the tenant (unique constraint ensures 1-to-1)
        provider_type (str): Type of SSO provider (default: 'azure_ad')
        provider_tenant_id (str): Azure tenant ID (GUID or domain)
        client_id (str): Application (client) ID from Azure Portal
        redirect_uri (str): OAuth2 callback URL
        is_enabled (bool): Whether SSO is enabled for this tenant
        config_metadata (JSONB): Additional configuration (role mapping, auto-provisioning, etc.)

    Relationships:
        tenant: One-to-one relationship with Tenant model

    Inherited from BaseModel:
        id (UUID): Primary key
        created_at (datetime): Creation timestamp (UTC)
        updated_at (datetime): Last update timestamp (UTC)
        created_by (UUID): User who created this configuration
    """

    __tablename__ = 'tenant_sso_configs'

    # Foreign key with unique constraint for 1-to-1 relationship
    tenant_id = db.Column(
        db.ForeignKey('tenants.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True
    )

    # Provider configuration
    provider_type = db.Column(String(50), nullable=False, default='azure_ad', index=True)

    # Azure AD specific configuration (Public Application mode)
    provider_tenant_id = db.Column(String(255), nullable=False)
    # For Azure: GUID (12345678-1234-1234-1234-123456789abc) or domain (contoso.onmicrosoft.com)

    client_id = db.Column(String(255), nullable=False)
    # Application (client) ID from Azure Portal

    redirect_uri = db.Column(String(500), nullable=False)
    # OAuth2 callback URL

    # Status and configuration
    is_enabled = db.Column(Boolean, default=False, nullable=False, index=True)

    # Flexible configuration storage for additional SSO settings
    config_metadata = db.Column(JSONB, default=dict)
    # Expected structure:
    # {
    #   "app_type": "public",  # Always "public" for this implementation
    #   "auto_provisioning": {
    #     "enabled": true,
    #     "default_role": "viewer",
    #     "sync_attributes_on_login": true,
    #     "allowed_email_domains": ["@company.com"],
    #     "allowed_azure_groups": ["All-Employees"],
    #     "group_role_mapping": {
    #       "IT-Admins": "admin",
    #       "Developers": "user"
    #     }
    #   }
    # }

    # Relationships
    tenant = relationship(
        'Tenant',
        back_populates='sso_config',
        uselist=False  # Ensures one-to-one relationship
    )

    def __init__(self, **kwargs):
        """
        Initialize a new SSO configuration.

        Sets default config_metadata values if not provided.
        """
        # Set default config_metadata
        if 'config_metadata' not in kwargs:
            kwargs['config_metadata'] = {}

        # Ensure app_type is always 'public' for this implementation
        if 'config_metadata' in kwargs:
            kwargs['config_metadata']['app_type'] = 'public'

        super().__init__(**kwargs)
        logger.info(f"TenantSSOConfig initialized for tenant_id={self.tenant_id}")

    def get_authority_url(self) -> str:
        """
        Get the Azure AD authority URL for this configuration.

        Returns:
            Authority URL for Azure AD authentication
        """
        if self.provider_type == 'azure_ad':
            return f"https://login.microsoftonline.com/{self.provider_tenant_id}"
        else:
            raise NotImplementedError(f"Provider type {self.provider_type} not supported")

    def get_authorization_url(self) -> str:
        """
        Get the OAuth2 authorization endpoint URL.

        Returns:
            Authorization endpoint URL
        """
        return f"{self.get_authority_url()}/oauth2/v2.0/authorize"

    def get_token_url(self) -> str:
        """
        Get the OAuth2 token endpoint URL.

        Returns:
            Token endpoint URL
        """
        return f"{self.get_authority_url()}/oauth2/v2.0/token"

    def get_logout_url(self) -> str:
        """
        Get the logout URL for Azure AD.

        Returns:
            Logout endpoint URL
        """
        return f"{self.get_authority_url()}/oauth2/v2.0/logout"

    def get_auto_provisioning_config(self) -> Dict[str, Any]:
        """
        Get the auto-provisioning configuration from config_metadata.

        Returns:
            Auto-provisioning configuration dictionary
        """
        return self.config_metadata.get('auto_provisioning', {
            'enabled': False,
            'default_role': 'viewer',
            'sync_attributes_on_login': True
        })

    def is_email_domain_allowed(self, email: str) -> bool:
        """
        Check if an email domain is allowed for SSO.

        Args:
            email: Email address to check

        Returns:
            True if email domain is allowed, False otherwise
        """
        auto_prov = self.get_auto_provisioning_config()
        allowed_domains = auto_prov.get('allowed_email_domains', [])

        if not allowed_domains:
            # No domain restrictions
            return True

        email_domain = email.split('@')[-1] if '@' in email else ''

        for allowed_domain in allowed_domains:
            if allowed_domain.startswith('@'):
                # Domain format: @company.com
                if email.endswith(allowed_domain[1:]):
                    return True
            elif email_domain == allowed_domain:
                # Full domain match
                return True

        return False

    def get_role_from_azure_groups(self, azure_groups: list) -> str:
        """
        Determine user role based on Azure AD group membership.

        Args:
            azure_groups: List of Azure AD groups the user belongs to

        Returns:
            Role name based on group mapping or default role
        """
        auto_prov = self.get_auto_provisioning_config()
        group_role_mapping = auto_prov.get('group_role_mapping', {})

        # Check group mappings in priority order (admin > user > viewer)
        role_priority = ['admin', 'user', 'viewer']

        for role in role_priority:
            for group_name, mapped_role in group_role_mapping.items():
                if mapped_role == role and group_name in azure_groups:
                    logger.info(f"User role '{role}' determined from Azure AD group '{group_name}'")
                    return role

        # Return default role if no group matches
        default_role = auto_prov.get('default_role', 'viewer')
        logger.info(f"No Azure AD group mapping found, using default role '{default_role}'")
        return default_role

    def validate_configuration(self) -> tuple[bool, Optional[str]]:
        """
        Validate the SSO configuration completeness and correctness.

        Returns:
            Tuple of (is_valid, error_message)
        """
        errors = []

        # Check required fields
        if not self.provider_tenant_id:
            errors.append("Provider tenant ID is required")

        if not self.client_id:
            errors.append("Client ID is required")

        if not self.redirect_uri:
            errors.append("Redirect URI is required")

        # Validate provider-specific requirements
        if self.provider_type == 'azure_ad':
            # Validate Azure tenant ID format (GUID or domain)
            import re
            guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
            domain_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$'

            if not (re.match(guid_pattern, self.provider_tenant_id) or
                   re.match(domain_pattern, self.provider_tenant_id)):
                errors.append("Invalid Azure tenant ID format (must be GUID or domain)")

        # Check config_metadata structure
        if self.config_metadata and self.config_metadata.get('app_type') != 'public':
            errors.append("App type must be 'public' for this implementation")

        if errors:
            return False, "; ".join(errors)

        return True, None

    def before_insert(self) -> None:
        """
        Lifecycle hook called before inserting a new SSO configuration.

        Validates configuration and ensures one SSO config per tenant.
        """
        super().before_insert()

        # Validate configuration
        is_valid, error_msg = self.validate_configuration()
        if not is_valid:
            raise ValueError(f"Invalid SSO configuration: {error_msg}")

        # Check if tenant already has an SSO configuration
        existing = TenantSSOConfig.query.filter_by(tenant_id=self.tenant_id).first()
        if existing:
            raise ValueError(
                f"Tenant already has an SSO configuration. "
                f"Delete the existing configuration before creating a new one."
            )

        logger.debug(f"SSO configuration pre-insert validation passed for tenant {self.tenant_id}")

    def before_update(self) -> None:
        """
        Lifecycle hook called before updating an SSO configuration.

        Validates updated configuration.
        """
        super().before_update()

        # Validate configuration
        is_valid, error_msg = self.validate_configuration()
        if not is_valid:
            raise ValueError(f"Invalid SSO configuration: {error_msg}")

        logger.debug(f"SSO configuration pre-update validation passed for tenant {self.tenant_id}")

    def to_dict(self, exclude: list = None, include_urls: bool = False) -> dict:
        """
        Convert SSO configuration to dictionary for JSON serialization.

        Args:
            exclude: List of fields to exclude from output
            include_urls: If True, include computed OAuth2 URLs

        Returns:
            Dictionary representation of the SSO configuration
        """
        data = super().to_dict(exclude=exclude)

        if include_urls:
            try:
                data['authority_url'] = self.get_authority_url()
                data['authorization_url'] = self.get_authorization_url()
                data['token_url'] = self.get_token_url()
                data['logout_url'] = self.get_logout_url()
            except Exception as e:
                logger.warning(f"Could not generate URLs: {str(e)}")

        return data

    @classmethod
    def find_by_tenant_id(cls, tenant_id: str) -> Optional['TenantSSOConfig']:
        """
        Find SSO configuration by tenant ID.

        Args:
            tenant_id: UUID of the tenant

        Returns:
            TenantSSOConfig object if found, None otherwise
        """
        return cls.query.filter_by(tenant_id=tenant_id).first()

    @classmethod
    def find_enabled_by_tenant_id(cls, tenant_id: str) -> Optional['TenantSSOConfig']:
        """
        Find enabled SSO configuration by tenant ID.

        Args:
            tenant_id: UUID of the tenant

        Returns:
            Enabled TenantSSOConfig object if found, None otherwise
        """
        return cls.query.filter_by(tenant_id=tenant_id, is_enabled=True).first()

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<TenantSSOConfig(id={self.id}, tenant_id={self.tenant_id}, "
            f"provider={self.provider_type}, enabled={self.is_enabled})>"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        status = "enabled" if self.is_enabled else "disabled"
        return f"SSO Config for tenant {self.tenant_id} ({self.provider_type}, {status})"