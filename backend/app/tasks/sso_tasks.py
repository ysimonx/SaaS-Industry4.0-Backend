"""
SSO-related Celery tasks for token management.

This module handles:
- Automatic token refresh before expiration
- Cleanup of expired tokens
- Vault key rotation for token encryption
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from celery import current_task
from app.celery_app import celery_app
from app.extensions import db
from app.models import UserAzureIdentity, TenantSSOConfig
from app.services.azure_ad_service import AzureADService

logger = logging.getLogger(__name__)


@celery_app.task(name='app.tasks.sso_tasks.refresh_expiring_tokens', bind=True, max_retries=3)
def refresh_expiring_tokens(self) -> Dict[str, Any]:
    """
    Refresh SSO tokens that are about to expire.

    This task runs every 15 minutes and refreshes tokens that will expire
    within the next 30 minutes. Uses exponential backoff for retries.

    Returns:
        Dictionary with refresh statistics
    """
    try:
        threshold = datetime.utcnow() + timedelta(minutes=30)

        # Find all tokens expiring soon
        expiring_identities = UserAzureIdentity.query.filter(
            UserAzureIdentity.token_expires_at < threshold,
            UserAzureIdentity.token_expires_at > datetime.utcnow(),
            UserAzureIdentity.encrypted_refresh_token.isnot(None)
        ).all()

        results = {
            'task_id': current_task.request.id,
            'timestamp': datetime.utcnow().isoformat(),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'total': len(expiring_identities)
        }

        for identity in expiring_identities:
            try:
                # Check if refresh token is still valid
                if identity.refresh_token_expires_at <= datetime.utcnow():
                    logger.info(f"Refresh token expired for identity {identity.id}")
                    results['skipped'] += 1
                    continue

                # Get SSO configuration for the tenant
                sso_config = TenantSSOConfig.query.filter_by(
                    tenant_id=identity.tenant_id,
                    is_enabled=True
                ).first()

                if not sso_config:
                    logger.warning(f"No SSO config found for tenant {identity.tenant_id}")
                    results['skipped'] += 1
                    continue

                # Refresh based on provider type
                if sso_config.provider_type == 'azure_ad':
                    azure_service = AzureADService(identity.tenant_id)

                    # Get the decrypted refresh token
                    refresh_token = identity.get_refresh_token()
                    if not refresh_token:
                        logger.error(f"Failed to decrypt refresh token for identity {identity.id}")
                        results['failed'] += 1
                        continue

                    # Refresh the token
                    new_tokens = azure_service.refresh_access_token(refresh_token)

                    if new_tokens and 'access_token' in new_tokens:
                        # Save new tokens
                        identity.save_tokens(
                            access_token=new_tokens['access_token'],
                            refresh_token=new_tokens.get('refresh_token', refresh_token),
                            id_token=new_tokens.get('id_token'),
                            expires_in=new_tokens.get('expires_in', 3600)
                        )
                        results['success'] += 1
                        logger.info(f"Successfully refreshed token for identity {identity.id}")
                    else:
                        results['failed'] += 1
                        logger.error(f"Token refresh failed for identity {identity.id}")

            except Exception as e:
                logger.error(f"Error refreshing token for identity {identity.id}: {str(e)}")
                results['failed'] += 1

                # Retry with exponential backoff
                if self.request.retries < self.max_retries:
                    raise self.retry(exc=e, countdown=2 ** self.request.retries)

        # Commit all changes
        db.session.commit()

        logger.info(f"Token refresh completed: {results}")
        return results

    except Exception as e:
        logger.error(f"Token refresh task failed: {str(e)}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(name='app.tasks.sso_tasks.cleanup_expired_tokens')
def cleanup_expired_tokens() -> Dict[str, Any]:
    """
    Clean up expired tokens that cannot be refreshed.

    This task runs daily and removes tokens where the refresh token
    has expired, requiring users to re-authenticate.

    Returns:
        Dictionary with cleanup statistics
    """
    try:
        expired_threshold = datetime.utcnow()

        # Find all identities with expired refresh tokens
        expired_identities = UserAzureIdentity.query.filter(
            UserAzureIdentity.refresh_token_expires_at < expired_threshold,
            UserAzureIdentity.encrypted_refresh_token.isnot(None)
        ).all()

        results = {
            'task_id': current_task.request.id,
            'timestamp': datetime.utcnow().isoformat(),
            'cleaned': 0,
            'total': len(expired_identities)
        }

        for identity in expired_identities:
            try:
                identity.clear_tokens()
                results['cleaned'] += 1
                logger.info(f"Cleared expired tokens for identity {identity.id}")
            except Exception as e:
                logger.error(f"Failed to clear tokens for identity {identity.id}: {str(e)}")

        db.session.commit()

        logger.info(f"Token cleanup completed: {results}")
        return results

    except Exception as e:
        logger.error(f"Token cleanup task failed: {str(e)}")
        raise


@celery_app.task(name='app.tasks.sso_tasks.rotate_encryption_keys')
def rotate_encryption_keys() -> Dict[str, Any]:
    """
    Rotate Vault encryption keys for enhanced security.

    This task runs monthly and rotates the encryption keys used for
    storing SSO tokens, then re-encrypts existing tokens with the new key.

    Returns:
        Dictionary with rotation statistics
    """
    try:
        from app.services.vault_service import VaultService

        vault_service = VaultService()

        # Get all enabled SSO configurations
        sso_configs = TenantSSOConfig.query.filter_by(is_enabled=True).all()

        results = {
            'task_id': current_task.request.id,
            'timestamp': datetime.utcnow().isoformat(),
            'rotated_tenants': 0,
            'rewrapped_tokens': 0,
            'total_tenants': len(sso_configs)
        }

        for config in sso_configs:
            try:
                tenant_id = str(config.tenant_id)

                # Rotate the encryption key for this tenant
                vault_service.rotate_encryption_key(tenant_id)

                # Re-wrap all tokens for this tenant
                identities = UserAzureIdentity.query.filter_by(
                    tenant_id=config.tenant_id
                ).all()

                for identity in identities:
                    if identity.encrypted_access_token or identity.encrypted_refresh_token:
                        # Re-wrap tokens with new key version
                        tokens_to_rewrap = [
                            identity.encrypted_access_token,
                            identity.encrypted_refresh_token,
                            identity.encrypted_id_token
                        ]

                        rewrapped = vault_service.rewrap_tokens(tenant_id, tokens_to_rewrap)

                        identity.encrypted_access_token = rewrapped[0]
                        identity.encrypted_refresh_token = rewrapped[1]
                        identity.encrypted_id_token = rewrapped[2]

                        results['rewrapped_tokens'] += 1

                results['rotated_tenants'] += 1
                logger.info(f"Rotated keys for tenant {tenant_id}")

            except Exception as e:
                logger.error(f"Failed to rotate keys for tenant {config.tenant_id}: {str(e)}")

        db.session.commit()

        logger.info(f"Key rotation completed: {results}")
        return results

    except Exception as e:
        logger.error(f"Key rotation task failed: {str(e)}")
        raise


@celery_app.task(name='app.tasks.sso_tasks.refresh_user_token', bind=True, max_retries=3)
def refresh_user_token(self, user_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Refresh a specific user's SSO token on demand.

    This task is triggered when a user's token needs immediate refresh,
    such as when accessing a protected resource.

    Args:
        user_id: UUID of the user
        tenant_id: UUID of the tenant

    Returns:
        Dictionary with refresh status
    """
    try:
        identity = UserAzureIdentity.query.filter_by(
            user_id=user_id,
            tenant_id=tenant_id
        ).first()

        if not identity:
            return {
                'success': False,
                'error': 'Identity not found'
            }

        # Check if token actually needs refresh
        if identity.token_expires_at and identity.token_expires_at > datetime.utcnow():
            return {
                'success': True,
                'message': 'Token still valid',
                'expires_at': identity.token_expires_at.isoformat()
            }

        # Get SSO configuration
        sso_config = TenantSSOConfig.query.filter_by(
            tenant_id=tenant_id,
            is_enabled=True
        ).first()

        if not sso_config:
            return {
                'success': False,
                'error': 'SSO not configured for tenant'
            }

        # Refresh the token
        if sso_config.provider_type == 'azure_ad':
            azure_service = AzureADService(tenant_id)

            refresh_token = identity.get_refresh_token()
            if not refresh_token:
                return {
                    'success': False,
                    'error': 'No valid refresh token',
                    'requires_reauth': True
                }

            new_tokens = azure_service.refresh_access_token(refresh_token)

            if new_tokens and 'access_token' in new_tokens:
                identity.save_tokens(
                    access_token=new_tokens['access_token'],
                    refresh_token=new_tokens.get('refresh_token', refresh_token),
                    id_token=new_tokens.get('id_token'),
                    expires_in=new_tokens.get('expires_in', 3600)
                )
                db.session.commit()

                return {
                    'success': True,
                    'message': 'Token refreshed successfully',
                    'expires_at': identity.token_expires_at.isoformat()
                }
            else:
                return {
                    'success': False,
                    'error': 'Token refresh failed',
                    'requires_reauth': True
                }

    except Exception as e:
        logger.error(f"On-demand token refresh failed: {str(e)}")

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=2 ** self.request.retries)

        return {
            'success': False,
            'error': str(e)
        }