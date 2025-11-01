"""
Marshmallow schemas for data validation and serialization.

This package contains all validation schemas for the SaaS Multi-Tenant Platform:
- user_schema: User registration, login, updates, and responses
"""

from app.schemas.user_schema import (
    UserSchema,
    UserCreateSchema,
    UserUpdateSchema,
    UserResponseSchema,
    UserLoginSchema,
    user_schema,
    user_create_schema,
    user_update_schema,
    user_response_schema,
    user_login_schema,
    users_response_schema,
)

__all__ = [
    # User schemas
    'UserSchema',
    'UserCreateSchema',
    'UserUpdateSchema',
    'UserResponseSchema',
    'UserLoginSchema',
    # Pre-instantiated schemas
    'user_schema',
    'user_create_schema',
    'user_update_schema',
    'user_response_schema',
    'user_login_schema',
    'users_response_schema',
]
