"""
Kafka Demo Blueprint - API Routes for Testing Kafka Integration

This blueprint provides demonstration endpoints for testing Kafka message production
and consumption. These endpoints are meant for development and testing purposes only.

Key features:
- Simple message producer for sending test messages to Kafka
- Consumer status endpoint to check last consumed messages
- In-memory message buffer for demo purposes
- JWT authentication required for all endpoints

Endpoints:
1. POST /api/demo/kafka/produce - Send test message to Kafka topic
2. GET /api/demo/kafka/consume - Get consumer status and last messages

WARNING: This is a demo/testing blueprint. Do not use in production without proper
Kafka consumer implementation, error handling, and message persistence.

Architecture notes:
- Uses placeholder Kafka producer/consumer (TODO for Phase 6)
- In-memory message buffer (last 10 messages) for demo purposes
- Real implementation will use kafka-python library
- Consumer should run in separate worker process (app/worker/)
"""

import logging
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify
from marshmallow import Schema, fields, ValidationError

from app.utils.responses import success, created, bad_request, server_error
from app.utils.decorators import jwt_required_custom

logger = logging.getLogger(__name__)

# Create Blueprint
kafka_demo_bp = Blueprint('kafka_demo', __name__, url_prefix='/api/demo/kafka')

# In-memory message buffer for demo purposes (last 10 messages)
# In production, this would be replaced by actual Kafka consumer
MESSAGE_BUFFER = []
MAX_BUFFER_SIZE = 10


class KafkaProduceSchema(Schema):
    """
    Schema for producing Kafka messages.

    Fields:
        topic: Kafka topic name (required)
        message: Message payload as dictionary (required)
        key: Optional message key for partitioning
    """
    topic = fields.Str(required=True)
    message = fields.Dict(required=True)
    key = fields.Str(required=False, load_default=None)


# Pre-instantiate schema
kafka_produce_schema = KafkaProduceSchema()


def produce_kafka_message(topic: str, message: dict, key: str = None, user_id: str = None) -> dict:
    """
    Produce a message to Kafka topic (placeholder implementation).

    This is a placeholder implementation for Phase 6. In production, this will:
    1. Connect to actual Kafka broker using kafka-python
    2. Serialize message to JSON
    3. Send to specified topic with optional key for partitioning
    4. Handle errors and retries

    Args:
        topic: Kafka topic name
        message: Message payload (dict)
        key: Optional message key for partitioning
        user_id: User ID from JWT token (for audit trail)

    Returns:
        Dict with event_id, topic, timestamp, and status

    Example:
        result = produce_kafka_message(
            topic='document.uploaded',
            message={'document_id': '123', 'filename': 'test.pdf'},
            key='tenant_456',
            user_id='user_789'
        )
    """
    # Generate event metadata
    event_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat() + 'Z'

    # Format message with metadata
    formatted_message = {
        'event_id': event_id,
        'topic': topic,
        'timestamp': timestamp,
        'user_id': user_id,
        'key': key,
        'payload': message
    }

    # TODO: Implement actual Kafka producer in Phase 6
    # from kafka import KafkaProducer
    # producer = KafkaProducer(
    #     bootstrap_servers=app.config['KAFKA_BOOTSTRAP_SERVERS'],
    #     value_serializer=lambda v: json.dumps(v).encode('utf-8')
    # )
    # future = producer.send(topic, value=formatted_message, key=key.encode() if key else None)
    # result = future.get(timeout=10)

    logger.info(f"[DEMO] Kafka message produced: topic={topic}, event_id={event_id}")
    logger.debug(f"[DEMO] Message payload: {message}")

    # Store in buffer for demo consumption endpoint
    global MESSAGE_BUFFER
    MESSAGE_BUFFER.append(formatted_message)
    if len(MESSAGE_BUFFER) > MAX_BUFFER_SIZE:
        MESSAGE_BUFFER.pop(0)  # Remove oldest message

    return {
        'event_id': event_id,
        'topic': topic,
        'timestamp': timestamp,
        'status': 'sent',
        'note': 'This is a placeholder implementation. Kafka integration will be added in Phase 6.'
    }


@kafka_demo_bp.route('/produce', methods=['POST'])
@jwt_required_custom
def produce_message():
    """
    Produce a test message to Kafka topic.

    POST /api/demo/kafka/produce

    Request Body:
        {
            "topic": "test.topic",
            "message": {
                "event_type": "test",
                "data": "Hello Kafka"
            },
            "key": "partition-key-123"  // optional
        }

    Returns:
        201 Created: Message sent successfully
        {
            "success": true,
            "message": "Kafka message sent successfully",
            "data": {
                "event_id": "uuid",
                "topic": "test.topic",
                "timestamp": "2024-01-01T00:00:00Z",
                "status": "sent",
                "note": "This is a placeholder implementation..."
            }
        }
        400 Bad Request: Invalid input (missing topic or message)
        401 Unauthorized: Missing or invalid JWT token
        500 Internal Server Error: Kafka producer error

    Authorization:
        Requires JWT token with valid user_id

    Example:
        curl -X POST http://localhost:4999/api/demo/kafka/produce \
          -H "Authorization: Bearer <token>" \
          -H "Content-Type: application/json" \
          -d '{"topic": "test.events", "message": {"type": "ping", "data": "test"}}'

    Notes:
        - This is a demo endpoint for testing Kafka integration
        - Messages are stored in in-memory buffer (last 10 messages)
        - Real Kafka producer will be implemented in Phase 6
    """
    try:
        # Get current user from JWT token
        user_id = request.user_id

        # Parse and validate request body
        try:
            validated_data = kafka_produce_schema.load(request.json)
        except ValidationError as err:
            logger.warning(f"Kafka produce validation error: {err.messages}")
            return bad_request(f'Validation error: {err.messages}')

        # Extract fields
        topic = validated_data['topic']
        message = validated_data['message']
        key = validated_data.get('key')

        # Produce message to Kafka
        result = produce_kafka_message(
            topic=topic,
            message=message,
            key=key,
            user_id=user_id
        )

        logger.info(f"Kafka message sent: topic={topic}, event_id={result['event_id']}, user={user_id}")

        return created(
            message='Kafka message sent successfully',
            data=result
        )

    except Exception as e:
        logger.error(f"Error producing Kafka message: {str(e)}", exc_info=True)
        return server_error(f'Failed to send Kafka message: {str(e)}')


@kafka_demo_bp.route('/consume', methods=['GET'])
@jwt_required_custom
def consume_messages():
    """
    Get Kafka consumer status and last consumed messages.

    GET /api/demo/kafka/consume

    Query Parameters:
        limit (int, optional): Maximum number of messages to return (default: 10, max: 50)

    Returns:
        200 OK: Consumer status with recent messages
        {
            "success": true,
            "message": "Kafka consumer status retrieved",
            "data": {
                "status": "running",
                "message_count": 5,
                "buffer_size": 10,
                "messages": [
                    {
                        "event_id": "uuid",
                        "topic": "test.topic",
                        "timestamp": "2024-01-01T00:00:00Z",
                        "user_id": "user-uuid",
                        "key": "partition-key",
                        "payload": {
                            "event_type": "test",
                            "data": "Hello Kafka"
                        }
                    }
                ],
                "note": "This is a demo implementation showing in-memory buffer..."
            }
        }
        400 Bad Request: Invalid limit parameter
        401 Unauthorized: Missing or invalid JWT token
        500 Internal Server Error: Consumer error

    Authorization:
        Requires JWT token with valid user_id

    Example:
        curl -X GET http://localhost:4999/api/demo/kafka/consume?limit=5 \
          -H "Authorization: Bearer <token>"

    Notes:
        - This is a demo endpoint showing in-memory message buffer
        - Real Kafka consumer will run in separate worker process (app/worker/)
        - Consumer will persist messages to database or cache
        - Messages shown here are those produced via /api/demo/kafka/produce
    """
    try:
        # Get current user from JWT token
        user_id = request.user_id

        # Parse query parameters
        limit = request.args.get('limit', 10, type=int)

        # Validate limit
        if limit < 1 or limit > 50:
            return bad_request('Limit must be between 1 and 50')

        # Get messages from buffer
        global MESSAGE_BUFFER
        messages = MESSAGE_BUFFER[-limit:] if MESSAGE_BUFFER else []

        logger.info(f"Kafka consumer status requested by user={user_id}, returned {len(messages)} messages")

        return success(
            message='Kafka consumer status retrieved',
            data={
                'status': 'running',
                'message_count': len(messages),
                'buffer_size': MAX_BUFFER_SIZE,
                'messages': messages,
                'note': 'This is a demo implementation showing in-memory buffer. '
                        'Real Kafka consumer will be implemented in Phase 6 using kafka-python library '
                        'and will run in a separate worker process.'
            }
        )

    except Exception as e:
        logger.error(f"Error retrieving Kafka consumer status: {str(e)}", exc_info=True)
        return server_error(f'Failed to get consumer status: {str(e)}')


@kafka_demo_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for Kafka demo service.

    GET /api/demo/kafka/health

    Returns:
        200 OK: Service is healthy
        {
            "status": "healthy",
            "service": "kafka_demo",
            "buffer_count": 5,
            "note": "Demo implementation - Kafka integration pending Phase 6"
        }

    Notes:
        - No authentication required for health checks
        - Shows current message buffer count
    """
    return jsonify({
        'status': 'healthy',
        'service': 'kafka_demo',
        'buffer_count': len(MESSAGE_BUFFER),
        'note': 'Demo implementation - Kafka integration pending Phase 6'
    }), 200


# Export blueprint
__all__ = ['kafka_demo_bp']
