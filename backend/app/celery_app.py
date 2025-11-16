"""
Celery application factory for asynchronous task processing.

This module configures Celery for handling background tasks including:
- SSO token refresh
- Scheduled maintenance tasks
- TSA timestamping (RFC 3161)
- Future async operations
"""

import os
from celery import Celery
from celery.schedules import crontab
from flask import Flask
import logging

logger = logging.getLogger(__name__)


def create_celery_app(app: Flask = None) -> Celery:
    """
    Create and configure a Celery application instance.

    Args:
        app: Optional Flask application instance for configuration

    Returns:
        Configured Celery application
    """
    # Get broker URL from environment or use default Redis
    broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/3')
    result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/4')

    celery = Celery(
        'saas_platform',
        broker=broker_url,
        backend=result_backend,
        include=['app.tasks.sso_tasks', 'app.tasks.maintenance_tasks', 'app.tasks.tsa_tasks', 'app.tasks.monitoring_tasks']
    )

    # Update configuration
    celery.conf.update(
        # Task execution settings
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,

        # Task routing
        task_routes={
            'app.tasks.sso_tasks.*': {'queue': 'sso'},
            'app.tasks.maintenance_tasks.*': {'queue': 'maintenance'},
            'app.tasks.email_tasks.*': {'queue': 'email'},
            'app.tasks.tsa_tasks.*': {'queue': 'tsa_timestamping'},
            'app.tasks.monitoring_tasks.*': {'queue': 'monitoring'},
        },

        # Task-specific settings (rate limiting, timeouts)
        task_annotations={
            'app.tasks.tsa_tasks.timestamp_file': {
                'rate_limit': '100/h',  # 100 timestamps per hour (conservative)
                'time_limit': 120,      # 2 minutes hard limit
                'soft_time_limit': 90,  # 90 seconds soft limit
            },
            'app.tasks.tsa_tasks.bulk_timestamp_files': {
                'time_limit': 300,      # 5 minutes for scheduling
                'soft_time_limit': 240,
            }
        },

        # Task priorities
        task_default_priority=5,
        task_acks_late=True,
        worker_prefetch_multiplier=1,

        # Result backend settings
        result_expires=3600,  # Results expire after 1 hour

        # Error handling
        task_reject_on_worker_lost=True,
        task_ignore_result=False,

        # Beat schedule for periodic tasks
        beat_schedule={
            # Refresh expiring SSO tokens - every 15 minutes
            'refresh-expiring-sso-tokens': {
                'task': 'app.tasks.sso_tasks.refresh_expiring_tokens',
                'schedule': crontab(minute='*/15'),
                'options': {
                    'queue': 'sso',
                    'priority': 7,
                }
            },

            # Clean up expired tokens - daily at 2 AM
            'cleanup-expired-tokens': {
                'task': 'app.tasks.sso_tasks.cleanup_expired_tokens',
                'schedule': crontab(hour=2, minute=0),
                'options': {
                    'queue': 'maintenance',
                    'priority': 3,
                }
            },

            # Rotate Vault encryption keys - monthly on the 1st at 3 AM
            'rotate-vault-keys': {
                'task': 'app.tasks.sso_tasks.rotate_encryption_keys',
                'schedule': crontab(day_of_month=1, hour=3, minute=0),
                'options': {
                    'queue': 'maintenance',
                    'priority': 2,
                }
            },

            # Health check for monitoring - every 5 minutes
            'health-check': {
                'task': 'app.tasks.maintenance_tasks.health_check',
                'schedule': crontab(minute='*/5'),
                'options': {
                    'queue': 'maintenance',
                    'priority': 1,
                }
            },

            # Comprehensive system health check - every 10 minutes
            'comprehensive-health-check': {
                'task': 'monitoring.comprehensive_health_check',
                'schedule': crontab(minute='*/10'),
                'options': {
                    'queue': 'monitoring',
                    'priority': 2,
                }
            },

            # Individual service monitoring tasks
            'monitor-postgres': {
                'task': 'monitoring.check_postgres',
                'schedule': crontab(minute='*/2'),  # Every 2 minutes
                'options': {
                    'queue': 'monitoring',
                    'priority': 3,
                }
            },

            'monitor-redis': {
                'task': 'monitoring.check_redis',
                'schedule': crontab(minute='*/2'),  # Every 2 minutes
                'options': {
                    'queue': 'monitoring',
                    'priority': 3,
                }
            },

            'monitor-api': {
                'task': 'monitoring.check_api',
                'schedule': crontab(minute='*/3'),  # Every 3 minutes
                'options': {
                    'queue': 'monitoring',
                    'priority': 3,
                }
            },

            'monitor-celery': {
                'task': 'monitoring.check_celery',
                'schedule': crontab(minute='*/5'),  # Every 5 minutes
                'options': {
                    'queue': 'monitoring',
                    'priority': 3,
                }
            },
        }
    )

    # Configure Celery with Flask app context if provided
    if app:
        class ContextTask(celery.Task):
            """Make celery tasks work with Flask app context."""
            abstract = True

            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery.Task = ContextTask

        # Update configuration from Flask config
        celery.conf.update(
            broker_url=app.config.get('CELERY_BROKER_URL', broker_url),
            result_backend=app.config.get('CELERY_RESULT_BACKEND', result_backend),
        )

    logger.info(f"Celery configured with broker: {broker_url}")
    return celery


# Create a default Celery instance
celery_app = create_celery_app()