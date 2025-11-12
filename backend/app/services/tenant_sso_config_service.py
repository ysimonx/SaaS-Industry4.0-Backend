"""
Tenant SSO Configuration Service

This service manages SSO configurations for tenants, including creation,
updates, validation, and statistics.
"""

import logging
from typing import Dict, List, Optional, Any
from flask import current_app

from app.models import Tenant, TenantSSOConfig, UserAzureIdentity
from app.extensions import db

logger = logging.getLogger(__name__)


class TenantSSOConfigService:
    """
    Service for managing tenant SSO configurations.

    Handles CRUD operations and validation for SSO configurations.
    """

    @staticmethod
    def create_sso_config(tenant_id: str, client_id: str, client_secret: str,
                         provider_tenant_id: str, config_metadata: Dict = None,
                         enable: bool = False) -> TenantSSOConfig:
        """
        Create a new SSO configuration for a tenant.

        Args:
            tenant_id: UUID of the tenant
            client_id: Azure AD Application (client) ID
            client_secret: Azure AD Application client secret (required for confidential apps)
            provider_tenant_id: Azure AD tenant ID (GUID or domain)
            config_metadata: Additional configuration metadata
            enable: Whether to enable SSO immediately

        Returns:
            Created TenantSSOConfig object

        Raises:
            ValueError: If tenant not found or already has SSO config
        """
        # Check if tenant exists
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant not found: {tenant_id}")

        # Check if tenant already has SSO configuration
        existing_config = TenantSSOConfig.find_by_tenant_id(tenant_id)
        if existing_config:
            raise ValueError(
                f"Tenant {tenant_id} already has an SSO configuration. "
                "Delete the existing configuration before creating a new one."
            )

        # Prepare redirect URI
        app_base_url = current_app.config.get('APP_BASE_URL', 'http://localhost:4999')
        sso_callback_path = current_app.config.get('SSO_CALLBACK_PATH', '/api/auth/sso/azure/callback')
        redirect_uri = f"{app_base_url}{sso_callback_path}"

        # Prepare configuration metadata
        if config_metadata is None:
            config_metadata = {}

        # Set app_type to 'confidential' since we require client_secret
        config_metadata['app_type'] = 'confidential'

        # Set default auto-provisioning if not specified
        if 'auto_provisioning' not in config_metadata:
            config_metadata['auto_provisioning'] = {
                'enabled': False,
                'default_role': 'viewer',
                'sync_attributes_on_login': True
            }

        # Create SSO configuration
        sso_config = TenantSSOConfig(
            tenant_id=tenant_id,
            provider_type='azure_ad',
            provider_tenant_id=provider_tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            is_enabled=enable,
            config_metadata=config_metadata
        )

        # Validate configuration
        is_valid, error_msg = sso_config.validate_configuration()
        if not is_valid:
            raise ValueError(f"Invalid SSO configuration: {error_msg}")

        # Update tenant auth method if SSO is enabled
        if enable:
            if tenant.auth_method == 'local':
                tenant.auth_method = 'both'  # Keep local auth + add SSO
                logger.info(f"Updated tenant {tenant_id} auth_method to 'both'")

            # Synchronize auto_provisioning settings with tenant model
            if config_metadata.get('auto_provisioning', {}).get('enabled', False):
                tenant.sso_auto_provisioning = True
                tenant.sso_default_role = config_metadata['auto_provisioning'].get('default_role', 'viewer')
                logger.info(f"Enabled auto-provisioning for tenant {tenant_id} with role '{tenant.sso_default_role}'")

        try:
            db.session.add(sso_config)
            db.session.commit()
            logger.info(f"Created SSO configuration for tenant {tenant_id}")
            return sso_config

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create SSO configuration: {str(e)}")
            raise

    @staticmethod
    def update_sso_config(tenant_id: str, updates: Dict[str, Any]) -> TenantSSOConfig:
        """
        Update an existing SSO configuration.

        Args:
            tenant_id: UUID of the tenant
            updates: Dictionary of fields to update

        Returns:
            Updated TenantSSOConfig object

        Raises:
            ValueError: If configuration not found or invalid
        """
        sso_config = TenantSSOConfig.find_by_tenant_id(tenant_id)
        if not sso_config:
            raise ValueError(f"No SSO configuration found for tenant {tenant_id}")

        # Update allowed fields
        allowed_fields = [
            'client_id', 'client_secret', 'provider_tenant_id', 'is_enabled', 'config_metadata'
        ]

        for field, value in updates.items():
            if field in allowed_fields:
                if field == 'config_metadata':
                    # Merge metadata instead of replacing
                    current_metadata = sso_config.config_metadata or {}
                    current_metadata.update(value)
                    # Preserve app_type
                    if 'app_type' not in value:
                        current_metadata['app_type'] = current_metadata.get('app_type', 'confidential')
                    sso_config.config_metadata = current_metadata
                else:
                    setattr(sso_config, field, value)

        # Update redirect URI if base URL changed
        if 'redirect_uri' not in updates:
            app_base_url = current_app.config.get('APP_BASE_URL', 'http://localhost:4999')
            sso_callback_path = current_app.config.get('SSO_CALLBACK_PATH', '/api/auth/sso/azure/callback')
            sso_config.redirect_uri = f"{app_base_url}{sso_callback_path}"

        # Validate updated configuration
        is_valid, error_msg = sso_config.validate_configuration()
        if not is_valid:
            db.session.rollback()
            raise ValueError(f"Invalid SSO configuration: {error_msg}")

        # Update tenant auth method based on SSO status
        tenant = Tenant.query.get(tenant_id)
        if tenant:
            if sso_config.is_enabled and tenant.auth_method == 'local':
                tenant.auth_method = 'both'
            elif not sso_config.is_enabled and tenant.auth_method == 'sso':
                tenant.auth_method = 'local'

        try:
            db.session.commit()
            logger.info(f"Updated SSO configuration for tenant {tenant_id}")
            return sso_config

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update SSO configuration: {str(e)}")
            raise

    @staticmethod
    def delete_sso_config(tenant_id: str, force: bool = False) -> bool:
        """
        Delete SSO configuration for a tenant.

        Args:
            tenant_id: UUID of the tenant
            force: Force deletion even if users have Azure identities

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If configuration not found or has dependencies
        """
        sso_config = TenantSSOConfig.find_by_tenant_id(tenant_id)
        if not sso_config:
            raise ValueError(f"No SSO configuration found for tenant {tenant_id}")

        # Check for existing Azure identities
        azure_identities = UserAzureIdentity.get_tenant_identities(tenant_id)
        if azure_identities and not force:
            raise ValueError(
                f"Cannot delete SSO configuration: {len(azure_identities)} users "
                f"have Azure identities. Use force=True to delete anyway."
            )

        # Update tenant auth method
        tenant = Tenant.query.get(tenant_id)
        if tenant:
            if tenant.auth_method in ['sso', 'both']:
                tenant.auth_method = 'local'
                tenant.sso_auto_provisioning = False
                logger.info(f"Reset tenant {tenant_id} to local authentication")

        # Delete Azure identities if forcing
        if force and azure_identities:
            for identity in azure_identities:
                db.session.delete(identity)
            logger.warning(f"Deleted {len(azure_identities)} Azure identities for tenant {tenant_id}")

        try:
            db.session.delete(sso_config)
            db.session.commit()
            logger.info(f"Deleted SSO configuration for tenant {tenant_id}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete SSO configuration: {str(e)}")
            raise

    @staticmethod
    def enable_sso(tenant_id: str, auth_method: str = 'both') -> TenantSSOConfig:
        """
        Enable SSO for a tenant.

        Args:
            tenant_id: UUID of the tenant
            auth_method: Authentication method ('sso' or 'both')

        Returns:
            Updated TenantSSOConfig object

        Raises:
            ValueError: If configuration not found or invalid auth_method
        """
        if auth_method not in ['sso', 'both']:
            raise ValueError("auth_method must be 'sso' or 'both'")

        sso_config = TenantSSOConfig.find_by_tenant_id(tenant_id)
        if not sso_config:
            raise ValueError(f"No SSO configuration found for tenant {tenant_id}")

        # Validate configuration before enabling
        is_valid, error_msg = sso_config.validate_configuration()
        if not is_valid:
            raise ValueError(f"Cannot enable SSO - configuration is invalid: {error_msg}")

        sso_config.is_enabled = True

        # Update tenant
        tenant = Tenant.query.get(tenant_id)
        if tenant:
            tenant.auth_method = auth_method
            logger.info(f"Enabled SSO for tenant {tenant_id} with auth_method='{auth_method}'")

        try:
            db.session.commit()
            return sso_config

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to enable SSO: {str(e)}")
            raise

    @staticmethod
    def disable_sso(tenant_id: str, keep_azure_identities: bool = True) -> TenantSSOConfig:
        """
        Disable SSO for a tenant.

        Args:
            tenant_id: UUID of the tenant
            keep_azure_identities: Whether to keep Azure identities

        Returns:
            Updated TenantSSOConfig object
        """
        sso_config = TenantSSOConfig.find_by_tenant_id(tenant_id)
        if not sso_config:
            raise ValueError(f"No SSO configuration found for tenant {tenant_id}")

        sso_config.is_enabled = False

        # Update tenant to local auth
        tenant = Tenant.query.get(tenant_id)
        if tenant:
            tenant.auth_method = 'local'
            tenant.sso_auto_provisioning = False
            logger.info(f"Disabled SSO for tenant {tenant_id}")

        # Clear tokens from Azure identities if requested
        if not keep_azure_identities:
            azure_identities = UserAzureIdentity.get_tenant_identities(tenant_id)
            for identity in azure_identities:
                identity.clear_tokens()
            logger.info(f"Cleared tokens for {len(azure_identities)} Azure identities")

        try:
            db.session.commit()
            return sso_config

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to disable SSO: {str(e)}")
            raise

    @staticmethod
    def get_sso_config(tenant_id: str, include_stats: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get SSO configuration for a tenant.

        Args:
            tenant_id: UUID of the tenant
            include_stats: Include usage statistics

        Returns:
            SSO configuration dictionary or None
        """
        sso_config = TenantSSOConfig.find_by_tenant_id(tenant_id)
        if not sso_config:
            return None

        config_dict = sso_config.to_dict(include_urls=True)

        if include_stats:
            # Add statistics
            azure_identities = UserAzureIdentity.get_tenant_identities(tenant_id)
            config_dict['statistics'] = {
                'total_azure_identities': len(azure_identities),
                'active_users': len([i for i in azure_identities if not i.is_access_token_expired()]),
                'azure_tenants': list(set(i.azure_tenant_id for i in azure_identities))
            }

        return config_dict

    @staticmethod
    def validate_sso_config(tenant_id: str) -> Dict[str, Any]:
        """
        Validate SSO configuration and test connectivity.

        Args:
            tenant_id: UUID of the tenant

        Returns:
            Validation result dictionary
        """
        sso_config = TenantSSOConfig.find_by_tenant_id(tenant_id)
        if not sso_config:
            return {
                'valid': False,
                'error': 'No SSO configuration found'
            }

        # Basic validation
        is_valid, error_msg = sso_config.validate_configuration()
        if not is_valid:
            return {
                'valid': False,
                'error': error_msg
            }

        # Test Azure AD endpoint accessibility
        try:
            import requests
            discovery_url = f"{sso_config.get_authority_url()}/.well-known/openid-configuration"
            response = requests.get(discovery_url, timeout=5)

            if response.status_code == 200:
                return {
                    'valid': True,
                    'authority_url': sso_config.get_authority_url(),
                    'authorization_url': sso_config.get_authorization_url(),
                    'token_url': sso_config.get_token_url()
                }
            else:
                return {
                    'valid': False,
                    'error': f"Azure AD endpoint returned status {response.status_code}"
                }

        except Exception as e:
            return {
                'valid': False,
                'error': f"Failed to connect to Azure AD: {str(e)}"
            }

    @staticmethod
    def get_all_sso_configs(only_enabled: bool = False) -> List[Dict[str, Any]]:
        """
        Get all SSO configurations.

        Args:
            only_enabled: Only return enabled configurations

        Returns:
            List of SSO configuration dictionaries
        """
        query = TenantSSOConfig.query

        if only_enabled:
            query = query.filter_by(is_enabled=True)

        configs = query.all()

        return [
            {
                'tenant_id': str(config.tenant_id),
                'tenant_name': config.tenant.name if config.tenant else 'Unknown',
                'provider_type': config.provider_type,
                'is_enabled': config.is_enabled,
                'client_id': config.client_id,
                'provider_tenant_id': config.provider_tenant_id,
                'created_at': config.created_at.isoformat() if config.created_at else None
            }
            for config in configs
        ]

    @staticmethod
    def update_auto_provisioning(tenant_id: str, auto_provisioning_config: Dict[str, Any]) -> TenantSSOConfig:
        """
        Update auto-provisioning settings for a tenant.

        Args:
            tenant_id: UUID of the tenant
            auto_provisioning_config: Auto-provisioning configuration

        Returns:
            Updated TenantSSOConfig object
        """
        sso_config = TenantSSOConfig.find_by_tenant_id(tenant_id)
        if not sso_config:
            raise ValueError(f"No SSO configuration found for tenant {tenant_id}")

        # Update config_metadata
        if not sso_config.config_metadata:
            sso_config.config_metadata = {}

        sso_config.config_metadata['auto_provisioning'] = auto_provisioning_config

        # Update tenant settings
        tenant = Tenant.query.get(tenant_id)
        if tenant:
            tenant.sso_auto_provisioning = auto_provisioning_config.get('enabled', False)
            tenant.sso_default_role = auto_provisioning_config.get('default_role', 'viewer')

            # Update domain whitelist
            allowed_domains = auto_provisioning_config.get('allowed_email_domains', [])
            tenant.sso_domain_whitelist = allowed_domains

        try:
            db.session.commit()
            logger.info(f"Updated auto-provisioning for tenant {tenant_id}")
            return sso_config

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update auto-provisioning: {str(e)}")
            raise

    @staticmethod
    def get_sso_statistics(tenant_id: str) -> Dict[str, Any]:
        """
        Get detailed SSO usage statistics for a tenant.

        Args:
            tenant_id: UUID of the tenant

        Returns:
            Statistics dictionary
        """
        sso_config = TenantSSOConfig.find_by_tenant_id(tenant_id)
        if not sso_config:
            return {'error': 'No SSO configuration found'}

        azure_identities = UserAzureIdentity.get_tenant_identities(tenant_id)

        # Group by Azure tenant
        azure_tenants = {}
        for identity in azure_identities:
            azure_tenant_id = identity.azure_tenant_id
            if azure_tenant_id not in azure_tenants:
                azure_tenants[azure_tenant_id] = {
                    'count': 0,
                    'users': []
                }
            azure_tenants[azure_tenant_id]['count'] += 1
            azure_tenants[azure_tenant_id]['users'].append({
                'email': identity.user.email if identity.user else 'Unknown',
                'azure_upn': identity.azure_upn,
                'last_sync': identity.last_sync.isoformat() if identity.last_sync else None,
                'token_expired': identity.is_access_token_expired()
            })

        # Recent logins (last 30 days)
        from datetime import datetime, timedelta
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_logins = [
            {
                'user_email': identity.user.email if identity.user else 'Unknown',
                'azure_upn': identity.azure_upn,
                'last_sync': identity.last_sync.isoformat() if identity.last_sync else None
            }
            for identity in azure_identities
            if identity.last_sync and identity.last_sync > thirty_days_ago
        ]

        return {
            'configuration': {
                'provider_type': sso_config.provider_type,
                'is_enabled': sso_config.is_enabled,
                'client_id': sso_config.client_id,
                'provider_tenant_id': sso_config.provider_tenant_id,
                'auto_provisioning_enabled': sso_config.config_metadata.get('auto_provisioning', {}).get('enabled', False)
            },
            'usage': {
                'total_sso_users': len(azure_identities),
                'active_tokens': len([i for i in azure_identities if not i.is_access_token_expired()]),
                'expired_tokens': len([i for i in azure_identities if i.is_access_token_expired()]),
                'recent_logins_30d': len(recent_logins),
                'by_azure_tenant': azure_tenants
            },
            'recent_logins': recent_logins[:10]  # Last 10 logins
        }