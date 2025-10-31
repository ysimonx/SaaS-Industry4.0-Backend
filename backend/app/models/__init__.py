"""
SQLAlchemy models for the SaaS Multi-Tenant Platform.

This package contains all database models:
- BaseModel: Abstract base class with common fields
- User: User accounts (main database)
- Tenant: Tenant organizations (main database)
- UserTenantAssociation: User-to-tenant membership with roles (main database)
- File: Physical files in S3 (tenant databases)
- Document: Document metadata with file references (tenant databases)
"""

from app.models.base import BaseModel, register_base_model_events
from app.models.user import User
from app.models.tenant import Tenant
from app.models.user_tenant_association import UserTenantAssociation
from app.models.file import File

__all__ = [
    'BaseModel',
    'register_base_model_events',
    'User',
    'Tenant',
    'UserTenantAssociation',
    'File',
]

# Models will be imported here as they are created:
# from app.models.document import Document
