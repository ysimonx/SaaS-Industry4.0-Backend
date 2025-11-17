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
        check_id: UUID du check Healthchecks (requis)
        check_name: DEPRECATED - utilisé uniquement pour la compatibilité
        auto_start: Envoyer un ping /start au début
        log_execution: Logger les détails d'exécution

    Usage:
        @monitor_task(check_id='abc-123-def')
        def my_task():
            pass

    Note: Les checks doivent être créés via scripts/setup_healthchecks.py
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Utiliser le check_id fourni directement
            actual_check_id = check_id

            # Si check_name est fourni sans check_id, logger un warning
            if not actual_check_id and check_name:
                logger.warning(
                    f"Task {func.__name__} uses deprecated check_name='{check_name}'. "
                    f"Please use check_id instead. Run scripts/setup_healthchecks.py to create checks."
                )
                # Ne PAS créer de check automatiquement
                return func(*args, **kwargs)

            if not actual_check_id:
                # Si monitoring activé mais pas de check_id, logger un warning
                if healthchecks.enabled:
                    logger.debug("No check_id provided for monitoring %s", func.__name__)
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
                    logger.info(
                        "Task %s completed successfully in %.2fs",
                        func.__name__, execution_time
                    )

                return result

            except Exception as e:
                # Signaler l'échec
                execution_time = time.time() - start_time
                healthchecks.ping_fail(actual_check_id)

                if log_execution:
                    logger.error(
                        "Task %s failed after %.2fs: %s",
                        func.__name__, execution_time, str(e)
                    )
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
                        logger.info(
                            "Endpoint %s served successfully in %.2fs",
                            func.__name__, execution_time
                        )

                    return result
                except Exception as e:
                    healthchecks.ping_fail(actual_check_id)

                    if log_execution:
                        execution_time = time.time() - start_time
                        logger.error(
                            "Endpoint %s failed after %.2fs: %s",
                            func.__name__, execution_time, str(e)
                        )
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
        check_id: UUID du check Healthchecks (requis)
        check_name: DEPRECATED - utilisé uniquement pour la compatibilité
        auto_start: Envoyer un ping /start au début

    Usage:
        @celery.task
        @monitor_celery_task(check_id='abc-123-def')
        def process_documents():
            pass

    Note: Les checks doivent être créés via scripts/setup_healthchecks.py
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Utiliser le contexte Celery si disponible
            task_name = getattr(func, 'name', func.__name__)

            # Utiliser le check_id fourni directement
            actual_check_id = check_id

            # Si check_name est fourni sans check_id, logger un warning
            if not actual_check_id and check_name:
                logger.warning(
                    "Task %s uses deprecated check_name='%s'. "
                    "Use check_id instead. Run scripts/setup_healthchecks.py",
                    task_name, check_name
                )
                # Ne PAS créer de check automatiquement
                return func(*args, **kwargs)

            if not actual_check_id:
                if healthchecks.enabled:
                    logger.debug("No check_id for monitoring Celery task %s", task_name)
                return func(*args, **kwargs)

            # Signaler le début
            if auto_start:
                healthchecks.ping_start(actual_check_id)
                logger.info("Celery task %s started", task_name)

            start_time = time.time()
            try:
                # Exécuter la tâche
                result = func(*args, **kwargs)

                # Signaler le succès
                execution_time = time.time() - start_time
                healthchecks.ping_success(actual_check_id)
                logger.info("Celery task %s completed in %.2fs", task_name, execution_time)

                return result

            except Exception as e:
                # Signaler l'échec
                execution_time = time.time() - start_time
                healthchecks.ping_fail(actual_check_id)
                logger.error(
                    "Celery task %s failed after %.2fs: %s",
                    task_name, execution_time, str(e)
                )
                raise

        return wrapper
    return decorator


def monitor_scheduled_task(check_id: str,
                          schedule: Optional[str] = None,
                          check_name: Optional[str] = None,
                          grace: Optional[int] = None):
    """
    Décorateur pour les tâches planifiées (cron-like)

    Args:
        check_id: UUID du check Healthchecks (requis)
        schedule: DEPRECATED - Expression cron (utilisé uniquement pour doc)
        check_name: DEPRECATED - Nom du check (utilisé uniquement pour doc)
        grace: DEPRECATED - Grace period (utilisé uniquement pour doc)

    Usage:
        @celery.task
        @monitor_scheduled_task(check_id='abc-123-def')
        def daily_cleanup():
            pass

    Note: Les checks doivent être créés via scripts/setup_healthchecks.py
          avec le schedule et grace period appropriés
    """
    def decorator(func: Callable) -> Callable:
        # Log deprecated parameters
        if schedule or check_name or grace:
            logger.warning(
                "Task %s uses deprecated parameters in monitor_scheduled_task. "
                "Only check_id is required. Configure schedule/grace in Healthchecks.io",
                func.__name__
            )

        # Vérifier que check_id est fourni
        if not check_id:
            logger.error(
                "monitor_scheduled_task requires check_id for task %s. "
                "Run scripts/setup_healthchecks.py to create checks.",
                func.__name__
            )
            # Retourner la fonction sans monitoring
            return func

        # Appliquer le monitoring standard avec le check_id fourni
        return monitor_task(check_id=check_id, auto_start=False)(func)

    return decorator