"""
Celery tasks package for asynchronous operations.

This package contains all background tasks including:
- SSO token management
- System maintenance
- Email notifications
- TSA timestamping (RFC 3161)
"""

# Import tasks to register them with Celery
from app.tasks.sso_tasks import refresh_expiring_tokens, cleanup_expired_tokens, rotate_encryption_keys
from app.tasks.maintenance_tasks import health_check
from app.tasks.tsa_tasks import timestamp_file, bulk_timestamp_files

__all__ = [
    'refresh_expiring_tokens',
    'cleanup_expired_tokens',
    'rotate_encryption_keys',
    'health_check',
    'timestamp_file',
    'bulk_timestamp_files',
]