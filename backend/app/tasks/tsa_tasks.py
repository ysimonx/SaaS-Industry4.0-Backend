"""
TSA (Time-Stamp Authority) Celery tasks for RFC 3161 timestamping.

This module handles:
- Asynchronous file timestamping with DigiCert TSA
- Retry logic with exponential backoff
- Error handling and metadata storage
- Idempotent task execution
"""

import logging
from datetime import datetime
from typing import Dict, Any

from celery import current_task
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.models.file import File
from app.utils.database import tenant_db_manager
from app.services.digicert_tsa_service import (
    digicert_tsa_service,
    TSAException,
    TSAConnectionError,
    TSAInvalidResponseError,
    TSAQuotaExceededError
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name='app.tasks.tsa_tasks.timestamp_file',
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute
    autoretry_for=(TSAConnectionError,),
    retry_backoff=True,
    retry_backoff_max=600,  # 10 minutes max
    retry_jitter=True
)
def timestamp_file(
    self,
    file_id: str,
    tenant_database_name: str,
    sha256_hash: str
) -> Dict[str, Any]:
    """
    Request TSA RFC3161 timestamp from DigiCert for uploaded file.

    This task is idempotent - if a file already has a successful timestamp,
    it will not request a new one.

    Flow:
    1. Verify file exists in tenant database
    2. Check if already timestamped (idempotence)
    3. Request timestamp from DigiCert TSA (using SHA-256)
    4. Store timestamp token + certificate chain in file_metadata
    5. Return success status

    Args:
        file_id: UUID of the File record in tenant database
        tenant_database_name: Name of tenant database (e.g., 'tenant_acme_123')
        sha256_hash: SHA-256 hash of the file content (64 hex chars)

    Returns:
        Dictionary with result:
        {
            'success': True,
            'file_id': 'uuid',
            'timestamp_serial': '0x123456789',
            'already_timestamped': False  # If file was already timestamped
        }

    Raises:
        TSAConnectionError: If connection to TSA fails (will retry)
        TSAInvalidResponseError: If TSA response is invalid (won't retry)
        TSAQuotaExceededError: If TSA quota exceeded (won't retry)
    """
    task_id = current_task.request.id
    logger.info(
        f"Starting timestamp task for file {file_id} in {tenant_database_name} "
        f"(task_id: {task_id})"
    )

    try:
        # 1. Verify file exists and get current timestamp status
        with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
            file = session.query(File).filter_by(id=file_id).first()

            if not file:
                error_msg = f"File {file_id} not found in {tenant_database_name}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 2. Check if already timestamped (idempotence)
            existing_tsa = file.get_metadata('tsa_timestamp')
            if existing_tsa and existing_tsa.get('status') == 'success':
                logger.info(
                    f"File {file_id} already timestamped "
                    f"(serial: {existing_tsa.get('serial_number')}), skipping"
                )
                return {
                    'success': True,
                    'file_id': file_id,
                    'timestamp_serial': existing_tsa.get('serial_number'),
                    'already_timestamped': True,
                    'task_id': task_id
                }

            # Mark as in-progress
            file.set_metadata('tsa_timestamp', {
                'status': 'in_progress',
                'started_at': datetime.utcnow().isoformat(),
                'task_id': task_id,
                'retry_count': self.request.retries
            })
            session.commit()

        # 3. Request timestamp from DigiCert TSA (outside session to avoid long transaction)
        logger.info(f"Requesting SHA-256 timestamp from DigiCert for file {file_id}")
        tsa_response = digicert_tsa_service.get_rfc3161_timestamp(sha256_hash, algorithm='sha256')

        if not tsa_response.get('success'):
            raise TSAInvalidResponseError("TSA request failed without exception")

        # 4. Store timestamp in File metadata
        with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
            file = session.query(File).filter_by(id=file_id).first()

            if not file:
                raise ValueError(f"File {file_id} disappeared during timestamp request")

            # Store complete timestamp data
            file.set_metadata('tsa_timestamp', {
                'token': tsa_response['timestamp_token'],
                'algorithm': tsa_response['algorithm'],
                'serial_number': tsa_response['serial_number'],
                'gen_time': tsa_response['gen_time'],
                'tsa_authority': tsa_response['tsa_authority'],
                'policy_oid': tsa_response.get('policy_oid'),
                'provider': 'digicert',
                'timestamped_at': datetime.utcnow().isoformat(),
                'status': 'success',
                'task_id': task_id,
                # Archive complete certificate chain for long-term verification
                'tsa_certificate': tsa_response.get('tsa_certificate'),
                'certificate_chain': tsa_response.get('certificate_chain', [])
            })

            session.commit()

        logger.info(
            f"Successfully timestamped file {file_id} "
            f"(serial: {tsa_response['serial_number']}, "
            f"gen_time: {tsa_response['gen_time']})"
        )

        return {
            'success': True,
            'file_id': file_id,
            'timestamp_serial': tsa_response['serial_number'],
            'gen_time': tsa_response['gen_time'],
            'task_id': task_id,
            'already_timestamped': False
        }

    except TSAConnectionError as e:
        # Connection errors - retry with exponential backoff
        logger.warning(
            f"TSA connection error for file {file_id} "
            f"(attempt {self.request.retries + 1}/{self.max_retries}): {e}"
        )

        # Store error status in metadata
        _store_error_metadata(
            file_id,
            tenant_database_name,
            str(e),
            self.request.retries,
            'connection_error',
            task_id
        )

        # Retry with exponential backoff
        raise self.retry(exc=e)

    except (TSAInvalidResponseError, TSAQuotaExceededError) as e:
        # Invalid response or quota exceeded - don't retry
        logger.error(
            f"TSA request failed for file {file_id} (won't retry): {e}",
            exc_info=True
        )

        _store_error_metadata(
            file_id,
            tenant_database_name,
            str(e),
            self.request.retries,
            'permanent_error',
            task_id
        )

        return {
            'success': False,
            'file_id': file_id,
            'error': str(e),
            'error_type': type(e).__name__,
            'task_id': task_id
        }

    except Exception as e:
        # Unexpected errors - log and store, but don't retry
        logger.error(
            f"Unexpected error timestamping file {file_id}: {e}",
            exc_info=True
        )

        _store_error_metadata(
            file_id,
            tenant_database_name,
            str(e),
            self.request.retries,
            'unexpected_error',
            task_id
        )

        return {
            'success': False,
            'file_id': file_id,
            'error': str(e),
            'error_type': 'unexpected',
            'task_id': task_id
        }


def _store_error_metadata(
    file_id: str,
    tenant_database_name: str,
    error_message: str,
    retry_count: int,
    error_type: str,
    task_id: str
) -> None:
    """
    Store error information in file metadata.

    This helper function is called when timestamp request fails,
    to track the error for debugging and monitoring.

    Args:
        file_id: File UUID
        tenant_database_name: Tenant database name
        error_message: Error description
        retry_count: Number of retries attempted
        error_type: Type of error (connection_error, permanent_error, etc.)
        task_id: Celery task ID
    """
    try:
        with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
            file = session.query(File).filter_by(id=file_id).first()

            if file:
                file.set_metadata('tsa_timestamp', {
                    'status': 'error',
                    'error_message': error_message,
                    'error_type': error_type,
                    'last_attempt': datetime.utcnow().isoformat(),
                    'retry_count': retry_count,
                    'task_id': task_id
                })
                session.commit()

                logger.info(f"Stored error metadata for file {file_id}")

    except Exception as meta_error:
        # Don't fail the task if we can't store metadata
        logger.error(
            f"Failed to store error metadata for file {file_id}: {meta_error}",
            exc_info=True
        )


@celery_app.task(name='app.tasks.tsa_tasks.bulk_timestamp_files', bind=True)
def bulk_timestamp_files(
    self,
    file_ids: list,
    tenant_database_name: str,
    stagger_seconds: int = 2
) -> Dict[str, Any]:
    """
    Timestamp multiple files in bulk with staggered scheduling.

    This task schedules individual timestamp tasks for each file,
    with a delay between each to avoid overwhelming the TSA service.

    Args:
        file_ids: List of file UUIDs to timestamp
        tenant_database_name: Tenant database name
        stagger_seconds: Seconds to wait between each task (default: 2)

    Returns:
        Dictionary with scheduling results:
        {
            'success': True,
            'total_files': 100,
            'tasks_scheduled': 95,
            'already_timestamped': 5,
            'task_ids': ['task-uuid-1', 'task-uuid-2', ...]
        }
    """
    task_id = current_task.request.id
    logger.info(
        f"Starting bulk timestamp for {len(file_ids)} files "
        f"in {tenant_database_name} (task_id: {task_id})"
    )

    results = {
        'success': True,
        'total_files': len(file_ids),
        'tasks_scheduled': 0,
        'already_timestamped': 0,
        'errors': 0,
        'task_ids': [],
        'bulk_task_id': task_id
    }

    # Get file information from tenant database
    with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
        files = session.query(File).filter(File.id.in_(file_ids)).all()

        for idx, file in enumerate(files):
            try:
                # Check if already timestamped
                existing_tsa = file.get_metadata('tsa_timestamp')
                if existing_tsa and existing_tsa.get('status') == 'success':
                    logger.debug(f"File {file.id} already timestamped, skipping")
                    results['already_timestamped'] += 1
                    continue

                # Schedule timestamp task with stagger
                countdown = idx * stagger_seconds

                task = timestamp_file.apply_async(
                    args=[str(file.id), tenant_database_name, file.md5_hash],
                    countdown=countdown
                )

                results['tasks_scheduled'] += 1
                results['task_ids'].append(task.id)

                logger.debug(
                    f"Scheduled timestamp task for file {file.id} "
                    f"(countdown: {countdown}s, task_id: {task.id})"
                )

            except Exception as e:
                logger.error(f"Failed to schedule timestamp for file {file.id}: {e}")
                results['errors'] += 1

    logger.info(
        f"Bulk timestamp scheduling complete: "
        f"{results['tasks_scheduled']} scheduled, "
        f"{results['already_timestamped']} already done, "
        f"{results['errors']} errors"
    )

    return results
