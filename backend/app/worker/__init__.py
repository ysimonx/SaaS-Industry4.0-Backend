"""
Worker Package - Background Task Processing

This package contains worker modules for asynchronous background task processing
using Kafka message queue. Workers run as separate processes outside the main
Flask application for scalability and fault isolation.

Architecture:
- Producer: Sends messages to Kafka topics from Flask app
- Consumer: Processes messages from Kafka topics in separate worker process
- Event-driven: Decouples request handling from long-running tasks

Components:
- producer.py: Kafka producer wrapper for message production
- consumer.py: Kafka consumer worker for message consumption

Message Flow:
1. Flask app produces messages via producer.produce_message()
2. Messages sent to Kafka broker topics
3. Consumer worker polls topics and processes messages
4. Results/errors logged and optionally sent to callback topics

Worker Deployment:
- Producer: Runs inside Flask app process (singleton instance)
- Consumer: Runs as separate Python process (python -m app.worker.consumer)
- Scaling: Multiple consumer processes can run in same consumer group
- Monitoring: Health checks, metrics, logging

Event Handlers:
- tenant.created: Create tenant database with Document/File tables
- tenant.deleted: Mark tenant as deleted, optionally drop database
- document.uploaded: Process document (OCR, thumbnails, indexing)
- document.deleted: Check for orphaned files and schedule cleanup
- file.process: Background file processing (virus scan, metadata extraction)
- audit.log: Write audit events to logging system

Usage (Producer):
    from app.worker.producer import produce_message

    success, error = produce_message(
        topic='tenant.created',
        message={'event_id': '...', 'event_type': 'tenant.created', ...},
        key='event-id'
    )

Usage (Consumer):
    # Run consumer worker in separate terminal
    python -m app.worker.consumer

    # Or run in background
    nohup python -m app.worker.consumer &

    # Graceful shutdown
    kill -TERM <pid>
"""

from app.worker.producer import (
    KafkaProducerWrapper,
    get_producer,
    produce_message,
    flush_producer,
    close_producer,
    get_producer_metrics,
)

# Consumer is not imported here as it's meant to be run as standalone process
# Import consumer module directly: from app.worker import consumer

__all__ = [
    'KafkaProducerWrapper',
    'get_producer',
    'produce_message',
    'flush_producer',
    'close_producer',
    'get_producer_metrics',
]
