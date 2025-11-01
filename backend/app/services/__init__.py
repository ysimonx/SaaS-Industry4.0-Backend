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
"""

from app.services.auth_service import AuthService
from app.services.user_service import UserService

__all__ = [
    'AuthService',
    'UserService',
]
