"""
System maintenance Celery tasks.

This module handles general maintenance tasks including:
- Health checks
- Database cleanup
- System monitoring
"""

import logging
from datetime import datetime
from typing import Dict, Any

from celery import current_task
from app.celery_app import celery_app
from app.extensions import db, redis_manager

logger = logging.getLogger(__name__)


@celery_app.task(name='app.tasks.maintenance_tasks.health_check')
def health_check() -> Dict[str, Any]:
    """
    Perform system health check.

    This task runs every 5 minutes to verify all components are operational.

    Returns:
        Dictionary with health status of all components
    """
    health_status = {
        'task_id': current_task.request.id,
        'timestamp': datetime.utcnow().isoformat(),
        'components': {}
    }

    # Check database
    try:
        db.session.execute('SELECT 1')
        health_status['components']['database'] = {
            'status': 'healthy',
            'message': 'Database connection successful'
        }
    except Exception as e:
        health_status['components']['database'] = {
            'status': 'unhealthy',
            'error': str(e)
        }

    # Check Redis
    try:
        redis_client = redis_manager.get_client()
        if redis_client and redis_client.ping():
            health_status['components']['redis'] = {
                'status': 'healthy',
                'message': 'Redis connection successful'
            }
        else:
            health_status['components']['redis'] = {
                'status': 'unhealthy',
                'error': 'Redis not available'
            }
    except Exception as e:
        health_status['components']['redis'] = {
            'status': 'unhealthy',
            'error': str(e)
        }

    # Check Vault (if configured)
    try:
        from app.services.vault_service import VaultService
        vault_service = VaultService()
        if vault_service.is_healthy():
            health_status['components']['vault'] = {
                'status': 'healthy',
                'message': 'Vault connection successful'
            }
        else:
            health_status['components']['vault'] = {
                'status': 'unhealthy',
                'error': 'Vault not accessible'
            }
    except Exception:
        health_status['components']['vault'] = {
            'status': 'warning',
            'message': 'Vault not configured'
        }

    # Overall health
    unhealthy_components = [
        name for name, status in health_status['components'].items()
        if status.get('status') == 'unhealthy'
    ]

    health_status['overall'] = {
        'status': 'unhealthy' if unhealthy_components else 'healthy',
        'unhealthy_components': unhealthy_components
    }

    logger.info(f"Health check completed: {health_status['overall']}")
    return health_status


@celery_app.task(name='app.tasks.maintenance_tasks.cleanup_orphaned_files')
def cleanup_orphaned_files() -> Dict[str, Any]:
    """
    Clean up orphaned files in S3 storage.

    This task runs weekly to identify and remove files that are no longer
    referenced by any documents.

    Returns:
        Dictionary with cleanup statistics
    """
    # This would be implemented based on your file management strategy
    # For now, returning a placeholder
    return {
        'task_id': current_task.request.id,
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'not_implemented',
        'message': 'File cleanup task pending implementation'
    }


@celery_app.task(name='app.tasks.maintenance_tasks.generate_usage_report')
def generate_usage_report(tenant_id: str = None) -> Dict[str, Any]:
    """
    Generate usage statistics report.

    Args:
        tenant_id: Optional tenant ID for tenant-specific report

    Returns:
        Dictionary with usage statistics
    """
    from app.models import User, Tenant, UserAzureIdentity

    report = {
        'task_id': current_task.request.id,
        'timestamp': datetime.utcnow().isoformat(),
        'statistics': {}
    }

    try:
        if tenant_id:
            # Tenant-specific statistics
            tenant = Tenant.query.get(tenant_id)
            if tenant:
                azure_identities = UserAzureIdentity.query.filter_by(
                    tenant_id=tenant_id
                ).count()

                report['statistics'] = {
                    'tenant_id': tenant_id,
                    'tenant_name': tenant.name,
                    'sso_users': azure_identities,
                    'auth_method': tenant.auth_method
                }
        else:
            # Global statistics
            total_users = User.query.count()
            total_tenants = Tenant.query.count()
            total_sso_identities = UserAzureIdentity.query.count()

            report['statistics'] = {
                'total_users': total_users,
                'total_tenants': total_tenants,
                'total_sso_identities': total_sso_identities
            }

        logger.info(f"Usage report generated: {report}")
        return report

    except Exception as e:
        logger.error(f"Failed to generate usage report: {str(e)}")
        return {
            'task_id': current_task.request.id,
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }