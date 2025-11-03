"""
SQLAlchemy models for the SaaS Multi-Tenant Platform.

This package contains all database models:
- BaseModel: Abstract base class with common fields
- User: User accounts (main database)
- Tenant: Tenant organizations (main database)
- UserTenantAssociation: User-to-tenant membership with roles (main database)
- File: Physical files in S3 (tenant databases) - NOT included in main DB migrations
- Document: Document metadata with file references (tenant databases) - NOT included in main DB migrations

IMPORTANT: File and Document are imported separately to avoid creating them
in the main database migrations. They are ONLY for tenant databases.
"""

from app.models.base import BaseModel, register_base_model_events
from app.models.user import User
from app.models.tenant import Tenant
from app.models.user_tenant_association import UserTenantAssociation

# File and Document are NOT imported here to exclude them from main DB migrations
# Import them explicitly where needed: from app.models.file import File
# from app.models.document import Document

__all__ = [
    'BaseModel',
    'register_base_model_events',
    'User',
    'Tenant',
    'UserTenantAssociation',
    # 'File',  # Tenant database only - import separately
    # 'Document',  # Tenant database only - import separately
]
