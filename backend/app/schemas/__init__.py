"""
Marshmallow schemas for data validation and serialization.

This package contains all validation schemas for the SaaS Multi-Tenant Platform:
- user_schema: User registration, login, updates, and responses
- tenant_schema: Tenant creation, updates, and responses
- document_schema: Document upload, metadata updates, and responses
- file_schema: File metadata serialization (read-only)
- user_tenant_association_schema: User-tenant associations with role management
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

from app.schemas.document_schema import (
    DocumentSchema,
    DocumentUploadSchema,
    DocumentUpdateSchema,
    DocumentResponseSchema,
    DocumentWithFileResponseSchema,
    document_schema,
    document_upload_schema,
    document_update_schema,
    document_response_schema,
    document_with_file_response_schema,
    documents_response_schema,
)

from app.schemas.file_schema import (
    FileSchema,
    FileResponseSchema,
    file_schema,
    file_response_schema,
    files_response_schema,
)

from app.schemas.user_tenant_association_schema import (
    UserTenantAssociationSchema,
    UserTenantAssociationCreateSchema,
    UserTenantAssociationUpdateSchema,
    UserTenantAssociationResponseSchema,
    user_tenant_association_schema,
    user_tenant_association_create_schema,
    user_tenant_association_update_schema,
    user_tenant_association_response_schema,
    user_tenant_associations_response_schema,
    ROLE_ADMIN,
    ROLE_USER,
    ROLE_VIEWER,
    VALID_ROLES,
)

from app.schemas.sso_config_schema import (
    TenantSSOConfigSchema,
    TenantSSOConfigCreateSchema,
    TenantSSOConfigUpdateSchema,
    AutoProvisioningSchema,
    ConfigMetadataSchema,
    SSOStatisticsSchema,
    SSOAvailabilitySchema,
)

from app.schemas.user_azure_identity_schema import (
    UserAzureIdentitySchema,
    UserAzureIdentityCreateSchema,
    UserAzureIdentityUpdateSchema,
    UserAzureIdentityListSchema,
    AzureTokenRefreshRequestSchema,
    AzureTokenRefreshResponseSchema,
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
    # Document schemas
    'DocumentSchema',
    'DocumentUploadSchema',
    'DocumentUpdateSchema',
    'DocumentResponseSchema',
    'DocumentWithFileResponseSchema',
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
    # Pre-instantiated document schemas
    'document_schema',
    'document_upload_schema',
    'document_update_schema',
    'document_response_schema',
    'document_with_file_response_schema',
    'documents_response_schema',
    # File schemas
    'FileSchema',
    'FileResponseSchema',
    # Pre-instantiated file schemas
    'file_schema',
    'file_response_schema',
    'files_response_schema',
    # UserTenantAssociation schemas
    'UserTenantAssociationSchema',
    'UserTenantAssociationCreateSchema',
    'UserTenantAssociationUpdateSchema',
    'UserTenantAssociationResponseSchema',
    # Pre-instantiated user-tenant association schemas
    'user_tenant_association_schema',
    'user_tenant_association_create_schema',
    'user_tenant_association_update_schema',
    'user_tenant_association_response_schema',
    'user_tenant_associations_response_schema',
    # Role constants
    'ROLE_ADMIN',
    'ROLE_USER',
    'ROLE_VIEWER',
    'VALID_ROLES',
    # SSO Config schemas
    'TenantSSOConfigSchema',
    'TenantSSOConfigCreateSchema',
    'TenantSSOConfigUpdateSchema',
    'AutoProvisioningSchema',
    'ConfigMetadataSchema',
    'SSOStatisticsSchema',
    'SSOAvailabilitySchema',
    # Azure Identity schemas
    'UserAzureIdentitySchema',
    'UserAzureIdentityCreateSchema',
    'UserAzureIdentityUpdateSchema',
    'UserAzureIdentityListSchema',
    'AzureTokenRefreshRequestSchema',
    'AzureTokenRefreshResponseSchema',
]
