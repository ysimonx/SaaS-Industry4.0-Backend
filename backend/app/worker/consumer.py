"""
Kafka Consumer Worker - Message Consumption and Event Processing

This module provides a standalone Kafka consumer worker that runs as a separate
Python process to consume and process messages from Kafka topics asynchronously.
It routes messages to appropriate handlers based on event type and handles errors
with dead-letter queue support.

Architecture:
- Runs as separate process outside Flask app (python -m app.worker.consumer)
- Subscribes to multiple Kafka topics simultaneously
- Routes messages to handlers based on event_type field
- Supports graceful shutdown on SIGTERM/SIGINT
- Dead-letter queue for failed message processing
- Automatic retries with exponential backoff

Message Flow:
1. Consumer polls Kafka topics for new messages
2. Deserializes JSON message to Python dict
3. Extracts event_type and routes to appropriate handler
4. Handler processes message (database operations, file cleanup, etc.)
5. On success: commit offset and continue
6. On error: retry with backoff or send to dead-letter queue
7. Graceful shutdown on signals (SIGTERM, SIGINT)

Event Handlers:
- tenant.created: Create tenant database with Document/File tables
- tenant.deleted: Mark tenant as deleted, optionally drop database
- document.uploaded: Process document (OCR, thumbnails, indexing)
- document.deleted: Check for orphaned files and schedule cleanup
- file.process: Background file processing (virus scan, metadata extraction)
- audit.log: Write audit events to logging system

Configuration (environment variables):
- KAFKA_BOOTSTRAP_SERVERS: Comma-separated list of Kafka broker addresses
- KAFKA_CONSUMER_GROUP_ID: Consumer group ID (default: 'saas-consumer-group')
- KAFKA_AUTO_OFFSET_RESET: Where to start reading ('earliest', 'latest', 'none')
- KAFKA_ENABLE_AUTO_COMMIT: Auto-commit offsets (default: True)
- KAFKA_MAX_POLL_RECORDS: Max records per poll (default: 100)
- DATABASE_URL: Main database connection URL for Flask app context

Worker Deployment:
- Run in separate terminal: python -m app.worker.consumer
- Run as background process: nohup python -m app.worker.consumer &
- Run with supervisor/systemd for production
- Scale horizontally: multiple workers in same consumer group

Graceful Shutdown:
- Catch SIGTERM/SIGINT signals
- Finish processing current message
- Commit offsets
- Close consumer connection
- Exit cleanly

Phase 6 Implementation:
- This is a PLACEHOLDER implementation for development
- Real implementation will use kafka-python library with KafkaConsumer
- Consumer loop with graceful shutdown and signal handling
- Dead-letter queue for failed messages
- Metrics collection for monitoring
"""

import logging
import signal
import sys
import os
import json
from typing import Dict, Any, Callable, Optional
from datetime import datetime

# Placeholder: In Phase 6, import KafkaConsumer from kafka-python
# from kafka import KafkaConsumer
# from kafka.errors import KafkaError

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
_shutdown_requested = False


def handle_shutdown_signal(signum, frame):
    """
    Signal handler for graceful shutdown.

    Called when SIGTERM or SIGINT is received. Sets global flag to stop
    consumer loop and allows current message to finish processing.

    Args:
        signum: Signal number
        frame: Current stack frame

    Usage:
        signal.signal(signal.SIGTERM, handle_shutdown_signal)
        signal.signal(signal.SIGINT, handle_shutdown_signal)
    """
    global _shutdown_requested
    signal_name = signal.Signals(signum).name
    logger.info(f"Received {signal_name} signal, initiating graceful shutdown...")
    _shutdown_requested = True


def handle_tenant_created(message: Dict[str, Any]) -> bool:
    """
    Handle tenant.created event.

    Creates tenant database with Document and File tables when a new tenant
    is created. This is typically called after the tenant record is created
    in the main database.

    Args:
        message: Kafka message with standardized event format
            {
                'event_id': 'uuid',
                'event_type': 'tenant.created',
                'tenant_id': 'uuid',
                'user_id': 'uuid',  # Creator user ID
                'timestamp': 'ISO 8601 UTC',
                'data': {
                    'tenant_name': 'Acme Corp',
                    'database_name': 'tenant_acme_corp_a1b2c3d4',
                    'creator_email': 'admin@acme.com'
                }
            }

    Returns:
        bool: True if processing succeeded, False if failed

    Business Logic:
        1. Extract tenant_id and database_name from message
        2. Verify tenant exists in main database
        3. Create tenant database using TenantDatabaseManager
        4. Create Document and File tables in tenant database
        5. Log success or error

    Error Handling:
        - Database already exists: Log warning and return True (idempotent)
        - Tenant not found: Log error and return False
        - Database creation failed: Log error and return False

    Phase 6 Implementation:
        - Use TenantDatabaseManager.create_tenant_database()
        - Use TenantDatabaseManager.create_tenant_tables()
        - Add retry logic for transient database errors
        - Send confirmation event to callback topic
    """
    try:
        event_id = message.get('event_id')
        tenant_id = message.get('tenant_id')
        data = message.get('data', {})
        database_name = data.get('database_name')

        logger.info(
            f"Processing tenant.created: event_id={event_id}, tenant_id={tenant_id}, "
            f"database_name={database_name}"
        )

        # TODO Phase 6: Create tenant database with tables
        # from app.utils.database import tenant_db_manager
        #
        # # Create PostgreSQL database
        # success, error = tenant_db_manager.create_tenant_database(database_name)
        # if not success:
        #     if 'already exists' in error:
        #         logger.warning(f"Tenant database already exists: {database_name}")
        #         return True  # Idempotent
        #     logger.error(f"Failed to create tenant database: {error}")
        #     return False
        #
        # # Create Document and File tables
        # success, error = tenant_db_manager.create_tenant_tables(database_name)
        # if not success:
        #     logger.error(f"Failed to create tenant tables: {error}")
        #     return False

        logger.info(
            f"[PLACEHOLDER] Would create tenant database: {database_name} "
            f"with Document/File tables"
        )

        logger.info(
            f"Successfully processed tenant.created: event_id={event_id}, "
            f"tenant_id={tenant_id}"
        )

        return True

    except Exception as e:
        logger.error(
            f"Error processing tenant.created: {str(e)}",
            exc_info=True
        )
        return False


def handle_tenant_deleted(message: Dict[str, Any]) -> bool:
    """
    Handle tenant.deleted event.

    Marks tenant as deleted and optionally drops the tenant database.
    This is typically called after a tenant is soft-deleted or hard-deleted.

    Args:
        message: Kafka message with standardized event format
            {
                'event_id': 'uuid',
                'event_type': 'tenant.deleted',
                'tenant_id': 'uuid',
                'user_id': 'uuid',  # User who deleted tenant
                'timestamp': 'ISO 8601 UTC',
                'data': {
                    'database_name': 'tenant_acme_corp_a1b2c3d4',
                    'hard_delete': False  # If True, drop database
                }
            }

    Returns:
        bool: True if processing succeeded, False if failed

    Business Logic:
        1. Extract tenant_id and hard_delete flag from message
        2. If hard_delete=False: Just log the soft delete (no action needed)
        3. If hard_delete=True: Drop tenant database
        4. Log success or error

    Error Handling:
        - Database doesn't exist: Log warning and return True (idempotent)
        - Database drop failed: Log error and return False

    Phase 6 Implementation:
        - Use TenantDatabaseManager.drop_tenant_database()
        - Add confirmation prompt for hard delete in production
        - Archive database backup before dropping
        - Send confirmation event to callback topic
    """
    try:
        event_id = message.get('event_id')
        tenant_id = message.get('tenant_id')
        data = message.get('data', {})
        database_name = data.get('database_name')
        hard_delete = data.get('hard_delete', False)

        logger.info(
            f"Processing tenant.deleted: event_id={event_id}, tenant_id={tenant_id}, "
            f"database_name={database_name}, hard_delete={hard_delete}"
        )

        if hard_delete:
            # TODO Phase 6: Drop tenant database
            # from app.utils.database import tenant_db_manager
            #
            # success, error = tenant_db_manager.drop_tenant_database(database_name)
            # if not success:
            #     if 'does not exist' in error:
            #         logger.warning(f"Tenant database already deleted: {database_name}")
            #         return True  # Idempotent
            #     logger.error(f"Failed to drop tenant database: {error}")
            #     return False

            logger.info(
                f"[PLACEHOLDER] Would drop tenant database: {database_name}"
            )
        else:
            logger.info(
                f"Tenant soft-deleted (database retained): tenant_id={tenant_id}, "
                f"database_name={database_name}"
            )

        logger.info(
            f"Successfully processed tenant.deleted: event_id={event_id}, "
            f"tenant_id={tenant_id}"
        )

        return True

    except Exception as e:
        logger.error(
            f"Error processing tenant.deleted: {str(e)}",
            exc_info=True
        )
        return False


def handle_document_uploaded(message: Dict[str, Any]) -> bool:
    """
    Handle document.uploaded event.

    Processes uploaded document asynchronously (OCR, thumbnail generation,
    full-text indexing, virus scanning, metadata extraction).

    Args:
        message: Kafka message with standardized event format
            {
                'event_id': 'uuid',
                'event_type': 'document.uploaded',
                'tenant_id': 'uuid',
                'user_id': 'uuid',
                'timestamp': 'ISO 8601 UTC',
                'data': {
                    'document_id': 'uuid',
                    'filename': 'report.pdf',
                    'mime_type': 'application/pdf',
                    'file_id': 'uuid',
                    'file_size': 1024000,
                    's3_path': 'tenants/uuid/files/...'
                }
            }

    Returns:
        bool: True if processing succeeded, False if failed

    Business Logic:
        1. Extract document_id, file_id, s3_path from message
        2. Download file from S3 (if needed)
        3. Run OCR if document is image or PDF
        4. Generate thumbnail for preview
        5. Extract metadata (author, creation date, etc.)
        6. Run virus scan (optional)
        7. Index document for full-text search
        8. Update document record with processing results

    Error Handling:
        - S3 download failed: Log error and return False
        - Processing failed: Log error and return False
        - Update failed: Log error and return False

    Phase 6 Implementation:
        - Download file from S3 using S3Client
        - Use Tesseract for OCR (PDF, images)
        - Use Pillow/ImageMagick for thumbnail generation
        - Use ClamAV or similar for virus scanning
        - Use Elasticsearch/Solr for full-text indexing
        - Update document record in tenant database
    """
    try:
        event_id = message.get('event_id')
        tenant_id = message.get('tenant_id')
        data = message.get('data', {})
        document_id = data.get('document_id')
        filename = data.get('filename')
        mime_type = data.get('mime_type')

        logger.info(
            f"Processing document.uploaded: event_id={event_id}, "
            f"tenant_id={tenant_id}, document_id={document_id}, "
            f"filename={filename}, mime_type={mime_type}"
        )

        # TODO Phase 6: Process document
        # 1. Download from S3 if needed
        # 2. Run OCR for PDF/images
        # 3. Generate thumbnail
        # 4. Extract metadata
        # 5. Virus scan
        # 6. Full-text indexing

        logger.info(
            f"[PLACEHOLDER] Would process document: OCR, thumbnails, indexing, etc."
        )

        logger.info(
            f"Successfully processed document.uploaded: event_id={event_id}, "
            f"document_id={document_id}"
        )

        return True

    except Exception as e:
        logger.error(
            f"Error processing document.uploaded: {str(e)}",
            exc_info=True
        )
        return False


def handle_document_deleted(message: Dict[str, Any]) -> bool:
    """
    Handle document.deleted event.

    Checks if the underlying file is orphaned (no other documents reference it)
    and schedules cleanup if needed. This prevents accumulation of unused files.

    Args:
        message: Kafka message with standardized event format
            {
                'event_id': 'uuid',
                'event_type': 'document.deleted',
                'tenant_id': 'uuid',
                'user_id': 'uuid',
                'timestamp': 'ISO 8601 UTC',
                'data': {
                    'document_id': 'uuid',
                    'file_id': 'uuid',
                    'orphaned': True  # If file has no other document references
                }
            }

    Returns:
        bool: True if processing succeeded, False if failed

    Business Logic:
        1. Extract file_id and orphaned flag from message
        2. If orphaned=True: Delete file from S3 and database
        3. If orphaned=False: No action needed (file still in use)
        4. Log success or error

    Error Handling:
        - File not found: Log warning and return True (idempotent)
        - S3 deletion failed: Log error and return False
        - Database deletion failed: Log error and return False

    Phase 6 Implementation:
        - Use FileService.delete_file() to remove orphaned file
        - Delete from S3 using S3Client
        - Delete from tenant database
        - Add confirmation before deletion in production
    """
    try:
        event_id = message.get('event_id')
        tenant_id = message.get('tenant_id')
        data = message.get('data', {})
        document_id = data.get('document_id')
        file_id = data.get('file_id')
        orphaned = data.get('orphaned', False)

        logger.info(
            f"Processing document.deleted: event_id={event_id}, "
            f"tenant_id={tenant_id}, document_id={document_id}, "
            f"file_id={file_id}, orphaned={orphaned}"
        )

        if orphaned:
            # TODO Phase 6: Delete orphaned file
            # from app.services.file_service import FileService
            # from app.models import Tenant
            #
            # tenant = Tenant.query.filter_by(id=tenant_id).first()
            # if not tenant:
            #     logger.error(f"Tenant not found: {tenant_id}")
            #     return False
            #
            # success, error = FileService.delete_file(
            #     tenant_id=tenant_id,
            #     tenant_database_name=tenant.database_name,
            #     file_id=file_id,
            #     force=True  # Force delete even if not orphaned
            # )
            #
            # if not success:
            #     logger.error(f"Failed to delete orphaned file: {error}")
            #     return False

            logger.info(
                f"[PLACEHOLDER] Would delete orphaned file: file_id={file_id} "
                f"from S3 and database"
            )
        else:
            logger.info(
                f"File still in use, skipping cleanup: file_id={file_id}"
            )

        logger.info(
            f"Successfully processed document.deleted: event_id={event_id}, "
            f"document_id={document_id}"
        )

        return True

    except Exception as e:
        logger.error(
            f"Error processing document.deleted: {str(e)}",
            exc_info=True
        )
        return False


def handle_file_process(message: Dict[str, Any]) -> bool:
    """
    Handle file.process event.

    Background processing for uploaded files (virus scan, metadata extraction,
    format conversion, etc.).

    Args:
        message: Kafka message with standardized event format

    Returns:
        bool: True if processing succeeded, False if failed

    Phase 6 Implementation:
        - Download file from S3
        - Run virus scan
        - Extract metadata
        - Convert to different formats if needed
        - Update file record with results
    """
    try:
        event_id = message.get('event_id')
        tenant_id = message.get('tenant_id')
        data = message.get('data', {})
        file_id = data.get('file_id')

        logger.info(
            f"Processing file.process: event_id={event_id}, "
            f"tenant_id={tenant_id}, file_id={file_id}"
        )

        # TODO Phase 6: Process file
        logger.info("[PLACEHOLDER] Would process file: virus scan, metadata extraction")

        logger.info(
            f"Successfully processed file.process: event_id={event_id}, "
            f"file_id={file_id}"
        )

        return True

    except Exception as e:
        logger.error(f"Error processing file.process: {str(e)}", exc_info=True)
        return False


def handle_audit_log(message: Dict[str, Any]) -> bool:
    """
    Handle audit.log event.

    Writes audit events to logging system for security monitoring and compliance.

    Args:
        message: Kafka message with standardized event format

    Returns:
        bool: True if processing succeeded, False if failed

    Phase 6 Implementation:
        - Write to dedicated audit log file
        - Send to external logging service (Splunk, ELK, etc.)
        - Store in audit database table
    """
    try:
        event_id = message.get('event_id')
        tenant_id = message.get('tenant_id')
        user_id = message.get('user_id')
        data = message.get('data', {})

        logger.info(
            f"Processing audit.log: event_id={event_id}, "
            f"tenant_id={tenant_id}, user_id={user_id}"
        )

        # TODO Phase 6: Write to audit log
        logger.info(f"[PLACEHOLDER] Would write audit log: {data}")

        return True

    except Exception as e:
        logger.error(f"Error processing audit.log: {str(e)}", exc_info=True)
        return False


# Event handler registry
EVENT_HANDLERS: Dict[str, Callable[[Dict[str, Any]], bool]] = {
    'tenant.created': handle_tenant_created,
    'tenant.deleted': handle_tenant_deleted,
    'document.uploaded': handle_document_uploaded,
    'document.deleted': handle_document_deleted,
    'file.process': handle_file_process,
    'audit.log': handle_audit_log,
}


def process_message(message: Dict[str, Any]) -> bool:
    """
    Process Kafka message by routing to appropriate handler.

    Extracts event_type from message and calls corresponding handler function.
    Returns True if processing succeeded, False if failed.

    Args:
        message: Kafka message with standardized event format
            {
                'event_id': 'uuid',
                'event_type': 'domain.action',
                'tenant_id': 'uuid',
                'user_id': 'uuid',
                'timestamp': 'ISO 8601 UTC',
                'data': {...}
            }

    Returns:
        bool: True if processing succeeded, False if failed

    Error Handling:
        - Unknown event_type: Log warning and return True (skip message)
        - Handler raised exception: Log error and return False (retry)
        - Handler returned False: Log error and return False (retry)

    Dead Letter Queue:
        - If handler fails after max retries, send to dead-letter topic
        - Manual intervention required to reprocess dead-letter messages
    """
    try:
        event_type = message.get('event_type')
        event_id = message.get('event_id')

        if not event_type:
            logger.warning(f"Message missing event_type: event_id={event_id}")
            return True  # Skip malformed message

        handler = EVENT_HANDLERS.get(event_type)

        if not handler:
            logger.warning(
                f"No handler registered for event_type: {event_type}, "
                f"event_id={event_id}"
            )
            return True  # Skip unknown event type

        logger.debug(
            f"Routing message to handler: event_type={event_type}, "
            f"event_id={event_id}"
        )

        success = handler(message)

        if not success:
            logger.error(
                f"Handler failed: event_type={event_type}, event_id={event_id}"
            )
            return False

        return True

    except Exception as e:
        logger.error(
            f"Error processing message: {str(e)}",
            exc_info=True
        )
        return False


def run_consumer():
    """
    Main consumer loop that polls Kafka topics and processes messages.

    Subscribes to all relevant Kafka topics, polls for messages, and routes
    them to appropriate handlers. Supports graceful shutdown on SIGTERM/SIGINT.

    Configuration:
        - KAFKA_BOOTSTRAP_SERVERS: Kafka broker addresses
        - KAFKA_CONSUMER_GROUP_ID: Consumer group ID
        - KAFKA_AUTO_OFFSET_RESET: Offset reset behavior
        - KAFKA_ENABLE_AUTO_COMMIT: Auto-commit offsets
        - KAFKA_MAX_POLL_RECORDS: Max records per poll

    Consumer Loop:
        1. Subscribe to topics
        2. Poll for messages
        3. Process each message via process_message()
        4. Commit offsets (auto or manual)
        5. Check shutdown flag
        6. Repeat until shutdown requested

    Graceful Shutdown:
        1. Catch SIGTERM/SIGINT signal
        2. Set shutdown flag
        3. Finish processing current message
        4. Commit offsets
        5. Close consumer
        6. Exit cleanly

    Phase 6 Implementation:
        - Use KafkaConsumer from kafka-python library
        - Subscribe to all topics: tenant.*, document.*, file.*, audit.log
        - Consumer group enables parallel processing
        - Manual commit for at-least-once delivery
        - Dead-letter queue for failed messages after max retries
        - Metrics collection for monitoring
    """
    global _shutdown_requested

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)

    # Topics to subscribe to
    topics = [
        'tenant.created',
        'tenant.deleted',
        'document.uploaded',
        'document.deleted',
        'file.process',
        'audit.log',
    ]

    # Configuration from environment variables
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092').split(',')
    group_id = os.getenv('KAFKA_CONSUMER_GROUP_ID', 'saas-consumer-group')
    auto_offset_reset = os.getenv('KAFKA_AUTO_OFFSET_RESET', 'earliest')
    enable_auto_commit = os.getenv('KAFKA_ENABLE_AUTO_COMMIT', 'True').lower() == 'true'
    max_poll_records = int(os.getenv('KAFKA_MAX_POLL_RECORDS', '100'))

    logger.info(
        f"Starting Kafka consumer worker: "
        f"bootstrap_servers={bootstrap_servers}, "
        f"group_id={group_id}, "
        f"topics={topics}"
    )

    try:
        # TODO Phase 6: Create KafkaConsumer
        # consumer = KafkaConsumer(
        #     *topics,
        #     bootstrap_servers=bootstrap_servers,
        #     group_id=group_id,
        #     auto_offset_reset=auto_offset_reset,
        #     enable_auto_commit=enable_auto_commit,
        #     max_poll_records=max_poll_records,
        #     value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        # )

        logger.info(
            f"[PLACEHOLDER] Would start Kafka consumer: topics={topics}, "
            f"group_id={group_id}"
        )

        # Consumer loop
        # while not _shutdown_requested:
        #     try:
        #         # Poll for messages
        #         message_batch = consumer.poll(timeout_ms=1000, max_records=max_poll_records)
        #
        #         for topic_partition, messages in message_batch.items():
        #             for message in messages:
        #                 try:
        #                     # Extract message value (already deserialized)
        #                     message_data = message.value
        #                     event_id = message_data.get('event_id')
        #                     event_type = message_data.get('event_type')
        #
        #                     logger.debug(
        #                         f"Received message: topic={topic_partition.topic}, "
        #                         f"partition={topic_partition.partition}, "
        #                         f"offset={message.offset}, "
        #                         f"event_id={event_id}, "
        #                         f"event_type={event_type}"
        #                     )
        #
        #                     # Process message
        #                     success = process_message(message_data)
        #
        #                     if not success:
        #                         # TODO: Implement retry logic with exponential backoff
        #                         # TODO: Send to dead-letter queue after max retries
        #                         logger.error(
        #                             f"Failed to process message: event_id={event_id}, "
        #                             f"event_type={event_type}"
        #                         )
        #
        #                     # Manual commit if auto-commit disabled
        #                     if not enable_auto_commit and success:
        #                         consumer.commit()
        #
        #                 except Exception as e:
        #                     logger.error(
        #                         f"Error processing message from Kafka: {str(e)}",
        #                         exc_info=True
        #                     )
        #
        #     except Exception as e:
        #         logger.error(f"Error polling Kafka: {str(e)}", exc_info=True)

        logger.info("Kafka consumer worker placeholder running...")
        logger.info("Press Ctrl+C to stop")

        # Placeholder: sleep until shutdown signal
        import time
        while not _shutdown_requested:
            time.sleep(1)

        logger.info("Shutdown signal received, stopping consumer worker...")

    except KeyboardInterrupt:
        logger.info("Consumer interrupted by keyboard, shutting down...")

    except Exception as e:
        logger.error(f"Fatal error in consumer worker: {str(e)}", exc_info=True)
        return 1

    finally:
        # TODO Phase 6: Close consumer
        # try:
        #     logger.info("Closing Kafka consumer...")
        #     consumer.close()
        #     logger.info("Kafka consumer closed successfully")
        # except Exception as e:
        #     logger.error(f"Error closing consumer: {str(e)}")

        logger.info("[PLACEHOLDER] Would close Kafka consumer")
        logger.info("Consumer worker shutdown complete")

    return 0


def main():
    """
    Entry point for Kafka consumer worker.

    Configures logging and starts the consumer loop.

    Usage:
        python -m app.worker.consumer
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            # logging.FileHandler('logs/consumer.log')  # Optional file logging
        ]
    )

    logger.info("=" * 80)
    logger.info("Starting Kafka Consumer Worker")
    logger.info("=" * 80)

    # Run consumer
    exit_code = run_consumer()

    logger.info("=" * 80)
    logger.info(f"Kafka Consumer Worker stopped (exit code: {exit_code})")
    logger.info("=" * 80)

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
