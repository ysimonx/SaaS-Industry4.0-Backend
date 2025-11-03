# Database Architecture Guide

This document explains the multi-tenant database architecture used in this SaaS platform.

## Overview

The platform uses a **database-per-tenant** isolation strategy, where:
- **Main database** (`saas_platform`): Stores global data (users, tenants, associations)
- **Tenant databases** (`tenant_<name>_<uuid>`): Each tenant gets an isolated database for their data

## Database Structure

### Main Database (`saas_platform`)

The main database contains three core tables:

#### 1. `users`
Stores all user accounts across all tenants.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by UUID
);
```

#### 2. `tenants`
Stores tenant (organization) metadata.

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    database_name VARCHAR(63) UNIQUE NOT NULL,  -- PostgreSQL database name
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by UUID
);
```

#### 3. `user_tenant_associations`
Many-to-many relationship linking users to tenants with roles.

```sql
CREATE TABLE user_tenant_associations (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('admin', 'user', 'viewer')),
    joined_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (user_id, tenant_id)
);
```

### Tenant Databases (`tenant_<name>_<uuid>`)

Each tenant gets an isolated PostgreSQL database containing:

#### 1. `files`
Physical file metadata and S3 references.

```sql
CREATE TABLE files (
    id UUID PRIMARY KEY,
    s3_path VARCHAR(1024) UNIQUE NOT NULL,  -- S3 object key
    md5_hash VARCHAR(32) UNIQUE NOT NULL,   -- For deduplication
    size_bytes BIGINT NOT NULL,
    mime_type VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by UUID
);
```

#### 2. `documents`
Document metadata with file references and user ownership.

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_id UUID REFERENCES files(id),
    user_id UUID NOT NULL,  -- User who uploaded
    mime_type VARCHAR(255),
    size_bytes BIGINT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by UUID,
    UNIQUE (user_id, filename)  -- Prevent duplicate filenames per user
);
```

## Why File and Document Are NOT in Main Database

**Critical Design Decision**: The `files` and `documents` tables are **tenant-specific** and must **NOT** be created in the main database.

### Reasons:

1. **Data Isolation**: Each tenant's files and documents are completely isolated in their own database
2. **Scalability**: Tenant databases can be scaled, backed up, or migrated independently
3. **Security**: No risk of cross-tenant data access or leakage
4. **Compliance**: Meets strict data residency and isolation requirements (GDPR, HIPAA)

### How It's Enforced:

1. **Models are not exported** in `app/models/__init__.py`:
   ```python
   # File and Document are NOT imported to exclude from main DB migrations
   __all__ = ['BaseModel', 'User', 'Tenant', 'UserTenantAssociation']
   ```

2. **Migration filter** in `migrations/env.py`:
   ```python
   def include_object(object, name, type_, reflected, compare_to):
       if type_ == "table" and name in ("files", "documents"):
           return False  # Exclude from main DB migrations
       return True
   ```

3. **No `__bind_key__`** on Tenant/UserTenantAssociation models:
   ```python
   # Correct - uses default (main) database
   class Tenant(BaseModel, db.Model):
       __tablename__ = 'tenants'
       # No __bind_key__ attribute
   ```

## Database Creation Flow

### 1. Initial Setup

When setting up the platform for the first time:

```bash
# Create main database and apply migrations
docker-compose exec api python scripts/init_db.py

# Or step by step:
docker-compose exec api flask db migrate -m "Initial migration"
docker-compose exec api flask db upgrade
```

This creates:
- Main database: `saas_platform`
- Tables: `users`, `tenants`, `user_tenant_associations`

### 2. Tenant Creation

When a new tenant is created via API:

```python
# In TenantService.create_tenant()
tenant = Tenant(name="Acme Corp", ...)
db.session.add(tenant)
db.session.commit()  # Creates tenant record in main DB

# Create isolated tenant database
tenant_db_manager.create_tenant_database(tenant)
# This creates database: tenant_acme_corp_a1b2c3d4
# And creates tables: files, documents
```

### 3. Tenant Database Lifecycle

```python
# Create tenant database
tenant_db_manager.create_tenant_database(tenant)

# Switch to tenant database for operations
with tenant_db_manager.connect_to_tenant(tenant.database_name):
    # All queries here run against tenant database
    documents = Document.query.all()

# Delete tenant database (soft delete)
tenant_db_manager.drop_tenant_database(tenant.database_name)
```

## Migration Management

### Main Database Migrations

```bash
# Create migration for main DB models only
docker-compose exec api flask db migrate -m "Add field to User"

# Apply migration
docker-compose exec api flask db upgrade
```

The migration system automatically excludes File and Document models.

### Tenant Database Migrations

Tenant databases are created with a fixed schema. If you need to update tenant schemas:

```python
# In TenantDatabaseManager
def update_tenant_schema(self, database_name: str):
    """Apply schema updates to existing tenant database."""
    with self.connect_to_tenant(database_name):
        # Run schema updates here
        pass
```

## Reset Database (Development)

To completely reset the database:

```bash
# Automated script (recommended)
./backend/scripts/reset_db.sh

# Manual steps:
docker-compose exec postgres psql -U postgres -c "DROP DATABASE IF EXISTS saas_platform;"
docker-compose exec postgres psql -U postgres -c "CREATE DATABASE saas_platform;"
docker-compose exec api flask db migrate -m "Initial migration"
docker-compose exec api flask db upgrade
```

## Common Pitfalls

### ❌ Wrong: Importing File/Document in Main Models

```python
# app/models/__init__.py - DON'T DO THIS
from app.models.file import File
from app.models.document import Document

__all__ = ['User', 'Tenant', 'File', 'Document']  # WRONG!
```

This causes File and Document to be registered in main database migrations.

### ✅ Correct: Import Only Where Needed

```python
# app/routes/files.py
from app.models.file import File  # Import in specific modules
from app.models.document import Document
```

### ❌ Wrong: Using `__bind_key__` on Main Models

```python
class Tenant(db.Model):
    __bind_key__ = 'main'  # DON'T DO THIS
```

Flask-Migrate won't detect models with bind keys.

### ✅ Correct: No Bind Key for Main Models

```python
class Tenant(db.Model):
    __tablename__ = 'tenants'
    # No __bind_key__ - uses default database
```

## Troubleshooting

### Problem: Migration creates File/Document in main DB

**Cause**: Models are being imported during app initialization.

**Solution**:
1. Check `app/models/__init__.py` - File/Document should NOT be in `__all__`
2. Check `app/__init__.py` - Don't import File/Document in shell context
3. Verify `migrations/env.py` has the `include_object` filter

### Problem: Tenant/UserTenantAssociation not in migration

**Cause**: Models have `__bind_key__` attribute.

**Solution**: Remove `__bind_key__` from these models or set to `None`.

### Problem: Can't query tenant data

**Cause**: Not connected to tenant database.

**Solution**: Use `tenant_db_manager.connect_to_tenant()`:
```python
with tenant_db_manager.connect_to_tenant(tenant.database_name):
    documents = Document.query.all()
```

## Best Practices

1. **Never manually create File/Document in main DB** - They belong only in tenant databases
2. **Always use TenantDatabaseManager** for tenant database operations
3. **Test migrations** before applying to production
4. **Backup tenant databases** independently - they can be large
5. **Monitor tenant database sizes** for capacity planning
6. **Use connection pooling** efficiently with multiple tenant databases

## References

- [Flask-Migrate Documentation](https://flask-migrate.readthedocs.io/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Multi-Tenant Data Architecture](https://docs.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/tenancy-models)
