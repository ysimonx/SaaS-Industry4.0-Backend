"""
Tenant Database Migrations Package

This package contains the tenant-specific database migration system
for tables that are created dynamically in each tenant's database
(File, Document, etc.).

The main module is tenant_migrations.py which provides:
- TenantSchemaMigration: Migration manager class
- register_migration: Decorator to register migrations
- get_migrator: Factory function to create migrator instances

See tenant_migrations_examples.py for usage examples.
"""

from app.tenant_db.tenant_migrations import (
    TenantSchemaMigration,
    register_migration,
    get_migrator
)

__all__ = [
    'TenantSchemaMigration',
    'register_migration',
    'get_migrator'
]
