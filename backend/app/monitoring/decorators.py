"""
Decorators for monitoring tasks and endpoints with Healthchecks.io
"""

import time
import functools
import logging
from typing import Optional, Callable, Any
from .healthchecks_client import healthchecks

logger = logging.getLogger(__name__)


def monitor_task(check_id: Optional[str] = None,
                 check_name: Optional[str] = None,
                 auto_start: bool = True,
                 log_execution: bool = True):
    """
    Décorateur pour monitorer l'exécution d'une tâche

    Args:
        check_id: UUID du check Healthchecks
        check_name: Nom pour créer automatiquement le check
        auto_start: Envoyer un ping /start au début
        log_execution: Logger les détails d'exécution

    Usage:
        @monitor_task(check_id='abc-123-def')
        def my_task():
            pass

        @monitor_task(check_name='my-scheduled-task')
        def my_scheduled_task():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Résoudre le check_id
            actual_check_id = check_id
            if not actual_check_id and check_name:
                # Tenter de récupérer le check existant
                checks = healthchecks.list_checks(tag=check_name)
                if checks:
                    actual_check_id = checks[0].get('ping_url', '').split('/')[-1]
                else:
                    # Créer automatiquement le check s'il n'existe pas
                    check = healthchecks.create_check(
                        name=check_name,
                        tags=f'auto-created {func.__name__}',
                        schedule='* * * * *'  # Par défaut, à ajuster
                    )
                    if check:
                        actual_check_id = check.get('ping_url', '').split('/')[-1]

            if not actual_check_id:
                if healthchecks.enabled:
                    logger.warning(f"No check_id for monitoring {func.__name__}")
                return func(*args, **kwargs)

            # Signaler le début si demandé
            if auto_start:
                healthchecks.ping_start(actual_check_id)

            start_time = time.time()
            try:
                # Exécuter la fonction
                result = func(*args, **kwargs)

                # Signaler le succès
                execution_time = time.time() - start_time
                healthchecks.ping_success(actual_check_id)

                if log_execution:
                    logger.info(f"Task {func.__name__} completed successfully in {execution_time:.2f}s")

                return result

            except Exception as e:
                # Signaler l'échec
                execution_time = time.time() - start_time
                healthchecks.ping_fail(actual_check_id)

                if log_execution:
                    logger.error(f"Task {func.__name__} failed after {execution_time:.2f}s: {str(e)}")
                raise

        return wrapper
    return decorator


def monitor_endpoint(check_id: Optional[str] = None,
                     check_name: Optional[str] = None,
                     log_execution: bool = False):
    """
    Décorateur pour monitorer un endpoint Flask

    Args:
        check_id: UUID du check Healthchecks
        check_name: Nom pour identifier le check
        log_execution: Logger les détails d'exécution

    Usage:
        @app.route('/api/critical')
        @monitor_endpoint(check_name='critical-api-endpoint')
        def critical_endpoint():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Résoudre le check_id
            actual_check_id = check_id
            if not actual_check_id and check_name:
                checks = healthchecks.list_checks(tag=check_name)
                if checks:
                    actual_check_id = checks[0].get('ping_url', '').split('/')[-1]

            if actual_check_id:
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    healthchecks.ping_success(actual_check_id)

                    if log_execution:
                        execution_time = time.time() - start_time
                        logger.info(f"Endpoint {func.__name__} served successfully in {execution_time:.2f}s")

                    return result
                except Exception as e:
                    healthchecks.ping_fail(actual_check_id)

                    if log_execution:
                        execution_time = time.time() - start_time
                        logger.error(f"Endpoint {func.__name__} failed after {execution_time:.2f}s: {str(e)}")
                    raise

            return func(*args, **kwargs)

        return wrapper
    return decorator


def monitor_celery_task(check_id: Optional[str] = None,
                        check_name: Optional[str] = None,
                        auto_start: bool = True):
    """
    Décorateur spécifique pour les tâches Celery

    Args:
        check_id: UUID du check Healthchecks
        check_name: Nom pour identifier le check
        auto_start: Envoyer un ping /start au début

    Usage:
        @celery.task
        @monitor_celery_task(check_name='process-documents')
        def process_documents():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Utiliser le contexte Celery si disponible
            task_name = getattr(func, 'name', func.__name__)

            # Résoudre le check_id
            actual_check_id = check_id
            if not actual_check_id and check_name:
                checks = healthchecks.list_checks(tag=check_name)
                if checks:
                    actual_check_id = checks[0].get('ping_url', '').split('/')[-1]
                else:
                    # Créer le check pour la tâche Celery
                    check = healthchecks.create_check(
                        name=f"Celery: {check_name}",
                        tags=f'celery {task_name}',
                        schedule='* * * * *'  # Par défaut, à ajuster
                    )
                    if check:
                        actual_check_id = check.get('ping_url', '').split('/')[-1]

            if not actual_check_id:
                if healthchecks.enabled:
                    logger.warning(f"No check_id for monitoring Celery task {task_name}")
                return func(*args, **kwargs)

            # Signaler le début
            if auto_start:
                healthchecks.ping_start(actual_check_id)
                logger.info(f"Celery task {task_name} started")

            start_time = time.time()
            try:
                # Exécuter la tâche
                result = func(*args, **kwargs)

                # Signaler le succès
                execution_time = time.time() - start_time
                healthchecks.ping_success(actual_check_id)
                logger.info(f"Celery task {task_name} completed in {execution_time:.2f}s")

                return result

            except Exception as e:
                # Signaler l'échec
                execution_time = time.time() - start_time
                healthchecks.ping_fail(actual_check_id)
                logger.error(f"Celery task {task_name} failed after {execution_time:.2f}s: {str(e)}")
                raise

        return wrapper
    return decorator


def monitor_scheduled_task(schedule: str,
                          check_name: str,
                          grace: int = 3600):
    """
    Décorateur pour les tâches planifiées (cron-like)

    Args:
        schedule: Expression cron (ex: "0 2 * * *" pour 2h du matin)
        check_name: Nom du check
        grace: Grace period en secondes

    Usage:
        @celery.task
        @monitor_scheduled_task(schedule="0 2 * * *", check_name="daily-cleanup", grace=7200)
        def daily_cleanup():
            pass
    """
    def decorator(func: Callable) -> Callable:
        # Créer ou récupérer le check avec le bon schedule
        checks = healthchecks.list_checks(tag=check_name)

        if not checks and healthchecks.enabled:
            # Créer le check avec le schedule spécifié
            check = healthchecks.create_check(
                name=f"Scheduled: {check_name}",
                tags=f'scheduled cron {func.__name__}',
                schedule=schedule,
                grace=grace
            )
            if check:
                check_id = check.get('ping_url', '').split('/')[-1]
                logger.info(f"Created scheduled check for {func.__name__} with schedule {schedule}")
            else:
                check_id = None
        else:
            check_id = checks[0].get('ping_url', '').split('/')[-1] if checks else None

        # Appliquer le monitoring standard avec le check_id résolu
        return monitor_task(check_id=check_id, auto_start=False)(func)

    return decorator