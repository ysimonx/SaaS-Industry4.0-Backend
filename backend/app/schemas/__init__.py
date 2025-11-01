"""
Marshmallow schemas for data validation and serialization.

This package contains all validation schemas for the SaaS Multi-Tenant Platform:
- user_schema: User registration, login, updates, and responses
- tenant_schema: Tenant creation, updates, and responses
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

from app.schemas.tenant_schema import (
    TenantSchema,
    TenantCreateSchema,
    TenantUpdateSchema,
    TenantResponseSchema,
    TenantWithUsersResponseSchema,
    tenant_schema,
    tenant_create_schema,
    tenant_update_schema,
    tenant_response_schema,
    tenant_with_users_response_schema,
    tenants_response_schema,
)

__all__ = [
    # User schemas
    'UserSchema',
    'UserCreateSchema',
    'UserUpdateSchema',
    'UserResponseSchema',
    'UserLoginSchema',
    # Tenant schemas
    'TenantSchema',
    'TenantCreateSchema',
    'TenantUpdateSchema',
    'TenantResponseSchema',
    'TenantWithUsersResponseSchema',
    # Pre-instantiated user schemas
    'user_schema',
    'user_create_schema',
    'user_update_schema',
    'user_response_schema',
    'user_login_schema',
    'users_response_schema',
    # Pre-instantiated tenant schemas
    'tenant_schema',
    'tenant_create_schema',
    'tenant_update_schema',
    'tenant_response_schema',
    'tenant_with_users_response_schema',
    'tenants_response_schema',
]
