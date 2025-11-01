"""
Services Package - Business Logic Layer

This package contains service classes that implement business logic for the application.
Services sit between routes (controllers) and models (data layer), handling complex
operations, validation, and orchestration.

Architecture:
- Routes call service methods instead of directly manipulating models
- Services encapsulate business logic and validation
- Services can call other services for complex workflows
- Services handle transactions and error handling

Available Services:
- AuthService: Authentication, registration, token management, logout
- UserService: User management, profile updates, tenant associations
- TenantService: Tenant management, database provisioning, user associations
- DocumentService: Document management, file deduplication, S3/Kafka integration
- FileService: File uploads, downloads, deduplication, orphaned file cleanup
- KafkaService: Message production/consumption, event-driven architecture
"""

from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.tenant_service import TenantService
from app.services.document_service import DocumentService
from app.services.file_service import FileService
from app.services.kafka_service import KafkaService

__all__ = [
    'AuthService',
    'UserService',
    'TenantService',
    'DocumentService',
    'FileService',
    'KafkaService',
]
