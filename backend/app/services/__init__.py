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
"""

from app.services.auth_service import AuthService

__all__ = [
    'AuthService',
]
