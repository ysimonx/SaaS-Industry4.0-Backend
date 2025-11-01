# Database Migrations

This directory contains Flask-Migrate (Alembic) migrations for the SaaS Multi-Tenant Platform.

## Overview

The platform uses a **multi-database architecture**:

- **Main Database** (`saas_platform`): Contains User, Tenant, and UserTenantAssociation tables
- **Tenant Databases** (dynamic): Each tenant gets an isolated database containing File and Document tables

## Migration Strategy

### Main Database Migrations

Migrations in this directory apply to the **main database only** (User, Tenant, UserTenantAssociation).

### Tenant Database Schema

Tenant databases are created dynamically and their schema is managed differently:

1. **Automatic Schema Creation**: When a new tenant is created via `Tenant.create_database()`, the File and Document tables are automatically created using `create_tenant_tables()` from `app/utils/database.py`

2. **No Alembic Migrations for Tenant DBs**: Tenant databases do not use Alembic migrations. Schema changes must be applied programmatically.

3. **Schema Updates**: If you need to update the File or Document schema:
   - Update the model in `app/models/file.py` or `app/models/document.py`
   - Create a migration script in `scripts/migrate_tenant_schemas.py` to apply changes to all existing tenant databases
   - Run the script to update all tenants

## Setup Instructions

### 1. Initialize Migrations (First Time Only)

```bash
cd backend
source venv/bin/activate  # Activate virtual environment
export FLASK_APP=run
flask db init
```

Or use the provided script:

```bash
./scripts/init_migrations.sh
```

### 2. Create a Migration

After modifying models in the main database:

```bash
flask db migrate -m "Description of changes"
```

### 3. Apply Migration

```bash
flask db upgrade
```

### 4. Rollback Migration

```bash
flask db downgrade
```

## Common Commands

```bash
# Show migration history
flask db history

# Show current migration version
flask db current

# Upgrade to specific version
flask db upgrade <revision>

# Downgrade to specific version
flask db downgrade <revision>

# Generate SQL for migration (don't apply)
flask db upgrade --sql

# Show pending migrations
flask db heads
```

## Important Notes

1. **Always Review Generated Migrations**: Flask-Migrate auto-generates migrations but they may need manual adjustments
2. **Test Migrations**: Always test migrations on a development database before applying to production
3. **Backup Before Migration**: Always backup your production database before running migrations
4. **Tenant Databases Not Included**: Migrations here do NOT affect tenant databases
5. **Models Must Be Imported**: Ensure all models are imported in `app/models/__init__.py` for migration detection

## Multi-Tenant Considerations

### When Adding a New Main Database Table

1. Create the model in `app/models/`
2. Set `__bind_key__ = 'main'`
3. Import in `app/models/__init__.py`
4. Run `flask db migrate` to create migration
5. Run `flask db upgrade` to apply

### When Adding a New Tenant Database Table

1. Create the model in `app/models/`
2. Set `__bind_key__ = None` for dynamic binding
3. Update `create_tenant_tables()` in `app/utils/database.py` to create the table
4. Create a script to migrate existing tenant databases
5. No Alembic migration needed

### When Modifying Existing Tables

**Main Database (User, Tenant, UserTenantAssociation)**:
- Modify the model
- Run `flask db migrate`
- Run `flask db upgrade`

**Tenant Database (File, Document)**:
- Modify the model
- Create a script in `scripts/` to apply schema changes to all tenant databases
- Example: `scripts/migrate_tenant_add_column.py`

## Troubleshooting

### Migration Not Detecting Model Changes

1. Ensure model is imported in `app/models/__init__.py`
2. Ensure model inherits from `db.Model`
3. Check `__bind_key__` is set correctly
4. Try `flask db migrate --autogenerate`

### Migration Fails to Apply

1. Check database connection settings in `.env`
2. Ensure database user has proper permissions
3. Review migration file for errors
4. Check migration history: `flask db current`

### Tenant Database Schema Out of Sync

1. Create a script to check schema version across all tenants
2. Apply schema updates programmatically
3. Consider versioning tenant database schemas separately

## Migration File Structure

```
migrations/
├── README.md                 # This file
├── alembic.ini              # Alembic configuration
├── env.py                   # Migration environment
├── script.py.mako           # Migration template
└── versions/                # Migration versions
    ├── <hash>_initial_migration.py
    ├── <hash>_add_user_field.py
    └── ...
```

## Best Practices

1. **Descriptive Messages**: Use clear, descriptive migration messages
2. **One Change Per Migration**: Keep migrations focused on a single change
3. **Test Rollbacks**: Ensure downgrades work correctly
4. **Version Control**: Commit migration files to git
5. **Review Before Merge**: Have migrations reviewed in code review
6. **Database Backups**: Always backup before running migrations in production
7. **Gradual Deployment**: Deploy schema changes before code changes when possible

## Example: Creating and Applying a Migration

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Set Flask app
export FLASK_APP=run

# 3. Make changes to models (e.g., add field to User model)
# Edit app/models/user.py

# 4. Generate migration
flask db migrate -m "Add phone_number to User model"

# 5. Review the generated migration
# Check migrations/versions/<hash>_add_phone_number_to_user_model.py

# 6. Apply migration
flask db upgrade

# 7. Verify
flask db current
```

## Production Deployment

For production deployments:

1. **Stop Application**: Ensure application is not running during migration
2. **Backup Database**: Create full database backup
3. **Test Migration**: Test on staging environment first
4. **Apply Migration**: Run `flask db upgrade`
5. **Verify**: Check migration applied successfully
6. **Deploy Code**: Deploy new application code
7. **Start Application**: Restart application services

## Rollback Plan

If a migration fails in production:

```bash
# 1. Stop application
systemctl stop saas-backend

# 2. Rollback migration
FLASK_APP=run flask db downgrade

# 3. Restore from backup if needed
psql saas_platform < backup.sql

# 4. Restart application with previous code version
systemctl start saas-backend
```
