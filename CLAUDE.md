# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **production-ready multi-tenant SaaS backend platform** built with Flask, PostgreSQL, Kafka, MinIO (S3), Redis, and Celery. The platform provides complete data isolation between tenants using separate PostgreSQL databases per tenant, with enterprise SSO support via Azure AD.

**Key Architecture Pattern**: Strict layered architecture with clear separation
```
Routes (HTTP handlers) → Services (Business Logic) → Models (Data) → Database
         ↓                       ↓                        ↓
    Schemas (Validation)   Kafka/Celery (Async)    TenantDBManager (Isolation)
```

## Common Commands

### Build and Run

```bash
# Start all services (with Vault for production-like setup)
cp .env.docker.minimal .env
docker-compose up -d

# Start services (simple development without Vault)
cp .env.docker .env
docker-compose up -d postgres redis kafka zookeeper minio api worker celery-worker-sso celery-beat flower

# Rebuild specific service after code changes
docker-compose build api && docker-compose up -d api

# View logs
docker-compose logs -f api              # API logs
docker-compose logs -f celery-worker-sso # SSO worker logs
docker-compose logs -f celery-beat      # Scheduler logs

# Access containers
docker-compose exec api bash
docker-compose exec postgres psql -U postgres -d saas_platform
```

### Database Operations

```bash
# Generate new migration (with Vault)
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Description"

# Generate new migration (without Vault)
docker-compose exec api flask db migrate -m "Description"

# Apply migrations to main database
docker-compose exec api /app/flask-wrapper.sh db upgrade

# Apply migrations to all tenant databases
docker-compose exec api python scripts/migrate_all_tenants.py

# Initialize database with test data
docker-compose exec api python scripts/init_db.py --create-admin --create-test-tenant

# Setup SSO test tenant
docker-compose exec api python scripts/setup_sso_test.py

# Reset database (CAUTION: deletes all data)
./backend/scripts/reset_db.sh
```

### Testing

```bash
# Run all tests
docker-compose exec api pytest

# Run with coverage report
docker-compose exec api pytest --cov=app --cov-report=html --cov-report=term

# Run specific test file
docker-compose exec api pytest tests/unit/test_auth.py

# Run specific test function
docker-compose exec api pytest tests/unit/test_auth.py::TestAuthService::test_login_success

# Run tests matching pattern
docker-compose exec api pytest -k "test_user"

# Run only unit tests
docker-compose exec api pytest tests/unit/

# Run only integration tests
docker-compose exec api pytest tests/integration/

# Run tests with verbose output
docker-compose exec api pytest -v

# Run tests and stop on first failure
docker-compose exec api pytest -x
```

### Code Quality

```bash
# Format code with Black
docker-compose exec api black app/ tests/

# Check formatting without changes
docker-compose exec api black --check app/ tests/

# Run linting with flake8
docker-compose exec api flake8 app/ tests/

# Type checking with mypy
docker-compose exec api mypy app/

# Run all quality checks
docker-compose exec api sh -c "black --check app/ tests/ && flake8 app/ tests/ && mypy app/"
```

### Monitoring and Debugging

```bash
# Access Flower (Celery monitoring dashboard)
open http://localhost:5555

# Access MinIO Console
open http://localhost:9001
# Username: minioadmin
# Password: minioadmin

# Access Vault UI (if using Vault)
open http://localhost:8201
# Use root token from docker/volumes/vault/init-data/.vault-token

# Monitor Redis
docker-compose exec redis redis-cli
> KEYS *              # List all keys
> MONITOR            # Real-time command stream
> INFO               # Server statistics

# Monitor Kafka topics
docker-compose exec kafka kafka-topics.sh --list --bootstrap-server localhost:9092
docker-compose exec kafka kafka-console-consumer.sh --topic tenant.created --from-beginning --bootstrap-server localhost:9092

# Check API health
curl http://localhost:4999/health

# Test SSO availability
curl http://localhost:4999/api/auth/sso/check-availability/{tenant_id}
```

### Flask CLI Commands

```bash
# List all Flask commands
docker-compose exec api flask --help

# Database commands
docker-compose exec api flask db init      # Initialize migrations
docker-compose exec api flask db migrate   # Create migration
docker-compose exec api flask db upgrade   # Apply migrations
docker-compose exec api flask db downgrade # Rollback migration
docker-compose exec api flask db current   # Show current revision
docker-compose exec api flask db history   # Show migration history

# Flask shell with app context
docker-compose exec api flask shell
>>> from app.models import User, Tenant
>>> User.query.all()
>>> tenant = Tenant.query.first()
>>> tenant.create_database()
```

## Core Architecture Principles

### Multi-Tenant Database Isolation

The platform uses a **two-tier database architecture** for maximum tenant isolation:

1. **Main Database** (`saas_platform`):
   - Stores: User, Tenant, UserTenantAssociation models
   - Managed via Alembic migrations
   - Location: [backend/migrations/](backend/migrations/)

2. **Tenant Databases** (dynamically created per tenant):
   - Stores: File, Document models (isolated per tenant)
   - Each tenant gets database named: `tenant_{slug}_{uuid}`
   - Managed via custom migration system in [backend/app/tenant_db/tenant_migrations.py](backend/app/tenant_db/tenant_migrations.py)
   - Tables created programmatically when tenant is provisioned

**Critical**: File and Document models are NEVER migrated in the main database. They exist only in tenant-specific databases. The migration system automatically excludes them via `include_object` filter in [backend/migrations/env.py](backend/migrations/env.py).

### TenantDatabaseManager

The `TenantDatabaseManager` class ([backend/app/utils/database.py](backend/app/utils/database.py)) manages all tenant database operations:

```python
# Get tenant-specific session
with tenant_db_manager.tenant_db_session('tenant_acme_123') as session:
    documents = session.query(Document).filter_by(user_id=user_id).all()
```

Key methods:
- `create_tenant_database(database_name)` - Creates PostgreSQL database
- `create_tenant_tables(database_name)` - Creates File and Document tables
- `tenant_db_session(database_name)` - Context manager for safe operations
- `drop_tenant_database(database_name, force=True)` - Deletes database

## Common Development Commands

### Docker Deployment (Recommended)

**With HashiCorp Vault** (production-like setup):
```bash
# 1. Setup environment
cp .env.docker.minimal .env

# 2. Start Vault and initialize
docker-compose up -d vault vault-unseal
sleep 30
docker-compose up -d vault-init
sleep 20

# 3. Start all services
docker-compose up -d

# 4. Initialize database (IMPORTANT: Remove old migrations first)
rm -f backend/migrations/versions/*
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Initial migration"
docker-compose exec api /app/flask-wrapper.sh db upgrade
docker-compose exec api python scripts/init_db.py --create-admin --create-test-tenant
```

**Without Vault** (simple development):
```bash
# 1. Setup environment
cp .env.docker .env

# 2. Start services (exclude Vault)
docker-compose up -d postgres kafka zookeeper minio api worker

# 3. Initialize database
rm -f backend/migrations/versions/*
docker-compose exec api flask db migrate -m "Initial migration"
docker-compose exec api flask db upgrade
docker-compose exec api python scripts/init_db.py --create-admin --create-test-tenant
```

### Database Migrations

**Main Database (Alembic for User, Tenant, UserTenantAssociation)**:
```bash
# With Vault - ALWAYS use flask-wrapper.sh
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Add column to users"
docker-compose exec api /app/flask-wrapper.sh db upgrade
docker-compose exec api /app/flask-wrapper.sh db current

# Without Vault
docker-compose exec api flask db migrate -m "Add column to users"
docker-compose exec api flask db upgrade
docker-compose exec api flask db current
```

**Tenant Databases (Custom system for File, Document)**:
```bash
# Apply migrations to all tenant databases
docker-compose exec api python scripts/migrate_all_tenants.py

# Dry-run to preview changes
docker-compose exec api python scripts/migrate_all_tenants.py --dry-run

# Migrate specific tenant
docker-compose exec api python scripts/migrate_all_tenants.py --tenant-id <uuid>

# View migration history
docker-compose exec api python scripts/migrate_all_tenants.py --history
```

**Complete Database Reset** (development only):
```bash
# Automated reset (recommended)
./backend/scripts/reset_db.sh

# Manual reset
docker-compose exec postgres psql -U postgres -c "DROP DATABASE IF EXISTS saas_platform;"
docker-compose exec postgres psql -U postgres -c "CREATE DATABASE saas_platform;"
rm -f backend/migrations/versions/*
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Initial migration"
docker-compose exec api /app/flask-wrapper.sh db upgrade
```

### Testing

```bash
# Run all tests
cd backend && pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_auth.py

# Run tests matching pattern
pytest -k "test_user"
```

### Service Management

```bash
# View logs
docker-compose logs -f api
docker-compose logs -f worker

# Restart service
docker-compose restart api

# Check service status
docker-compose ps

# Execute commands in container
docker-compose exec api bash
```

## Important Architecture Details

### Vault Integration

When `USE_VAULT=true`, the application loads secrets from HashiCorp Vault instead of environment variables:

- **Flask commands** in Docker MUST use `/app/flask-wrapper.sh` prefix
- Secrets are loaded from `secret/saas-project/{environment}/` path
- Supports: database credentials, JWT keys, S3 credentials
- AppRole authentication with auto-renewal
- Falls back to environment variables if Vault unavailable

Configuration: [backend/app/config.py](backend/app/config.py:122-181) `load_from_vault()` method

### File Upload & S3 Storage

Files use **MD5-based deduplication** and **sharded S3 paths**:

```
S3 Path Pattern:
tenants/{database_name}/files/{md5[:2]}/{md5[2:4]}/{md5}_{uuid}

Example:
tenants/tenant_acme_a1b2/files/a1/b2/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6_<uuid>
```

Flow:
1. File uploaded via multipart/form-data
2. MD5 hash calculated during upload
3. Check if file with same MD5 exists in tenant DB
4. If exists: reuse File record, create new Document
5. If new: upload to S3, create File record, create Document

Implementation: [backend/app/services/file_service.py](backend/app/services/file_service.py)

#### Pre-signed URLs for Download

For downloading documents without Bearer Token in URL (useful for email links, browser downloads, external integrations):

**Two-step workflow**:
1. **Get pre-signed URL** (authenticated with JWT):
   ```bash
   curl -X GET \
     "http://localhost:4999/api/tenants/{tenant_id}/documents/{doc_id}/download-url?expires_in=3600" \
     -H "Authorization: Bearer $TOKEN"
   ```

2. **Download file** (public URL, no authentication required):
   ```bash
   curl -O "{download_url_from_response}"
   ```

**Configuration** (Docker internal vs. public URLs):
- `S3_ENDPOINT_URL`: Internal URL for backend → MinIO communication (`http://minio:9000`)
- `S3_PUBLIC_URL`: Public URL for client → MinIO downloads (`http://localhost:9000` in dev, `https://documents.example.com` in prod)

The S3Client automatically replaces the internal endpoint URL with the public URL in generated pre-signed URLs.

**Security**:
- JWT required to generate URL (validates tenant access + read permission)
- URLs expire after specified time (default: 3600s = 1 hour, max: 86400s = 24 hours)
- MinIO bucket is **private** (pre-signed URLs required)
- All URL generations are audit-logged

**Routes**:
- `GET /api/tenants/{id}/documents/{id}/download` - Direct download (proxy via Flask, Bearer Token required)
- `GET /api/tenants/{id}/documents/{id}/download-url` - Generate pre-signed URL (Bearer Token required)

**Documentation**: See [document_url_signee.md](document_url_signee.md) for complete implementation details, examples, and troubleshooting.

### Role-Based Access Control

Three roles with hierarchical permissions:

- **admin**: Full access (create, read, update, delete)
- **user**: Can create and manage own documents
- **viewer**: Read-only access

Enforcement:
- Route level: `@role_required(['admin'])` decorator
- Service level: `UserTenantAssociation.has_permission()` checks
- Database level: `user_id` foreign keys for ownership

### JWT Authentication

- **Access tokens**: 15 minutes expiry (for API requests)
- **Refresh tokens**: 7 days expiry (to get new access tokens)
- **Token blacklist**: In-memory during development (use Redis in production)

Endpoints:
- `POST /api/auth/login` - Returns both tokens
- `POST /api/auth/refresh` - Exchange refresh token for new access token
- `POST /api/auth/logout` - Blacklist both tokens

Configuration: [backend/app/__init__.py](backend/app/__init__.py:158-223) `configure_jwt()`

### Kafka Event Processing

**Producer** (synchronous):
- Service methods publish events after successful operations
- Topics: `tenant.created`, `document.uploaded`, `file.process`, etc.
- Location: [backend/app/services/kafka_service.py](backend/app/services/kafka_service.py)

**Consumer** (background worker):
- Runs as separate container: `saas-worker`
- Processes events asynchronously
- Handles: notifications, webhooks, audit logs
- Location: [backend/app/worker/consumer.py](backend/app/worker/consumer.py)

Enable/disable: `ENABLE_KAFKA_EVENTS` environment variable

### Azure AD SSO (Single Sign-On)

The platform supports **multi-tenant Azure AD SSO** with per-tenant configuration:

**Architecture**:
- **Public Application Mode**: Uses OAuth2 with PKCE (no client_secret required)
- **Multi-Tenant Support**: Each tenant configures their own Azure AD instance
- **User Identity Mapping**: Users can have different Azure Object IDs per tenant
- **Auto-Provisioning**: Automatically create users on first SSO login (configurable)
- **Hybrid Authentication**: Support both SSO and local password authentication

**Models**:
- `TenantSSOConfig`: Stores SSO configuration per tenant (1-to-1 relationship)
- `UserAzureIdentity`: Maps users to Azure AD identities per tenant
- Extended `Tenant` model: Added `auth_method`, `sso_domain_whitelist`, `auto_provisioning_enabled`
- Extended `User` model: Added `sso_provider`, nullable `password_hash` for SSO-only users

**Services**:
- [backend/app/services/azure_ad_service.py](backend/app/services/azure_ad_service.py) - OAuth2 flow with PKCE, token management
- [backend/app/services/tenant_sso_config_service.py](backend/app/services/tenant_sso_config_service.py) - SSO configuration management
- [backend/app/services/microsoft_graph_service.py](backend/app/services/microsoft_graph_service.py) - Microsoft Graph API integration

**Key Endpoints**:
- `GET /api/auth/sso/azure/login/{tenant_id}` - Initiate Azure AD login
- `GET /api/auth/sso/azure/callback` - OAuth2 callback handler
- `POST /api/auth/sso/detect` - Detect SSO for email domain
- `GET /api/tenants/{id}/sso/config` - Manage SSO configuration

**Token Management**:
- **Vault Transit Engine**: Encrypts Azure AD tokens at rest
- **Redis Session Store**: Manages PKCE parameters and state tokens
- **Celery Background Tasks**: Automated token refresh before expiry
- **Hybrid Refresh Strategy**: Proactive (30 min before expiry) + Lazy (on API call)

**Setup for Testing**:
```bash
# Set Azure AD credentials
export AZURE_CLIENT_ID="your-client-id"
export AZURE_TENANT_ID="your-azure-tenant-id"

# Run setup script
docker-compose exec api python scripts/setup_sso_test.py

# Test SSO availability
curl http://localhost:4999/api/auth/sso/check-availability/{tenant_id}
```

**Security Features**:
- PKCE (Proof Key for Code Exchange) for secure public client flow
- State token validation prevents CSRF attacks
- Token encryption with Vault Transit Engine
- Domain whitelisting for auto-provisioning
- Azure AD group to role mapping

**Celery Tasks**:
The platform includes Celery workers for SSO token management:
- `celery-worker-sso`: Handles SSO token refresh tasks
- `celery-beat`: Schedules periodic token refresh checks
- `flower`: Web dashboard for monitoring tasks (http://localhost:5555)

```bash
# Monitor Celery tasks
docker-compose logs -f celery-worker-sso
docker-compose logs -f celery-beat

# Access Flower dashboard
open http://localhost:5555
```

## Key Files to Understand

When making changes, review these files first:

**Application Core**:
- [backend/app/__init__.py](backend/app/__init__.py) - App factory, blueprint registration, JWT setup
- [backend/app/config.py](backend/app/config.py) - Configuration with Vault support
- [backend/run.py](backend/run.py) - Application entry point

**Multi-Tenant Database**:
- [backend/app/utils/database.py](backend/app/utils/database.py) - `TenantDatabaseManager` class
- [backend/app/models/tenant.py](backend/app/models/tenant.py) - Tenant model with DB lifecycle
- [backend/app/tenant_db/tenant_migrations.py](backend/app/tenant_db/tenant_migrations.py) - Custom migration system

**Models** (carefully consider which database):
- Main DB: [backend/app/models/user.py](backend/app/models/user.py), [backend/app/models/tenant.py](backend/app/models/tenant.py), [backend/app/models/user_tenant_association.py](backend/app/models/user_tenant_association.py)
- Main DB (SSO): [backend/app/models/tenant_sso_config.py](backend/app/models/tenant_sso_config.py), [backend/app/models/user_azure_identity.py](backend/app/models/user_azure_identity.py)
- Tenant DB: [backend/app/models/file.py](backend/app/models/file.py), [backend/app/models/document.py](backend/app/models/document.py)

**Security**:
- [backend/app/utils/decorators.py](backend/app/utils/decorators.py) - JWT and RBAC decorators
- [backend/app/services/auth_service.py](backend/app/services/auth_service.py) - Token blacklist, login logic
- [backend/app/services/azure_ad_service.py](backend/app/services/azure_ad_service.py) - Azure AD OAuth2 with PKCE
- [backend/app/services/microsoft_graph_service.py](backend/app/services/microsoft_graph_service.py) - Microsoft Graph API client

**Infrastructure**:
- [docker-compose.yml](docker-compose.yml) - Service orchestration (11 services including Celery, Redis, Flower)
- [backend/migrations/env.py](backend/migrations/env.py) - Migration configuration with table exclusion
- [backend/app/celery_app.py](backend/app/celery_app.py) - Celery application factory
- [backend/app/tasks/sso_tasks.py](backend/app/tasks/sso_tasks.py) - SSO token refresh tasks

## Development Workflow

### Adding a New API Endpoint

1. **Define Schema** in `backend/app/schemas/` (request validation, response serialization)
2. **Implement Service** in `backend/app/services/` (business logic)
3. **Create Route** in `backend/app/routes/` (HTTP handling)
4. **Add Tests** in `backend/tests/` (unit + integration)

### Adding a Field to User Model

```bash
# 1. Edit the model
nano backend/app/models/user.py

# 2. Generate migration (with Vault)
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Add phone_number to users"

# 3. Review generated migration
nano backend/migrations/versions/xxx_add_phone_number_to_users.py

# 4. Apply migration
docker-compose exec api /app/flask-wrapper.sh db upgrade

# 5. Update schema
nano backend/app/schemas/user_schema.py
```

### Adding a Field to Document Model (Tenant DB)

```bash
# 1. Edit the model
nano backend/app/models/document.py

# 2. Edit tenant migration file
nano backend/app/tenant_db/tenant_migrations.py

# 3. Add migration function
@register_migration(2)  # Next version number
def add_document_status_column(db):
    """Add status column to documents table"""
    db.execute(text("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'active'
    """))

# 4. Apply to all tenants (dry-run first!)
docker-compose exec api python scripts/migrate_all_tenants.py --dry-run
docker-compose exec api python scripts/migrate_all_tenants.py
```

### Creating a New Tenant Programmatically

```python
from app.models.tenant import Tenant
from app.extensions import db

# Create tenant (automatically creates database and tables)
tenant = Tenant(name="Acme Corp")
db.session.add(tenant)
db.session.commit()

# Database created: tenant_acmecorp_<uuid>
# Tables created: files, documents
```

## Common Issues and Solutions

### Issue: Flask commands fail with "No such command 'db'"
**Solution**: Use flask-wrapper.sh when Vault is enabled:
```bash
docker-compose exec api /app/flask-wrapper.sh db upgrade
```

### Issue: Migration creates documents/files tables in main DB
**Solution**: These tables should NOT be in main DB. They're excluded by design.
- Check [backend/migrations/env.py](backend/migrations/env.py) has `include_object` filter
- Delete migration and regenerate
- Verify: `docker-compose exec postgres psql -U postgres -d saas_platform -c "\dt"`

### Issue: Tenant database already exists error
**Solution**: Drop and recreate:
```python
tenant_db_manager.drop_tenant_database('tenant_xyz', force=True)
tenant.create_database()
```

### Issue: Token blacklist not working across API instances
**Solution**: In production, replace in-memory blacklist with Redis:
- Update [backend/app/services/auth_service.py](backend/app/services/auth_service.py)
- Replace `TOKEN_BLACKLIST` set with Redis commands
- Uncomment Redis service in [docker-compose.yml](docker-compose.yml)

### Issue: S3 upload fails with "Bucket does not exist"
**Solution**: MinIO bucket initialization might have failed:
```bash
docker-compose restart minio-init
docker-compose logs minio-init
```

## Environment-Specific Notes

### Development (FLASK_ENV=development)
- Debug mode enabled
- Verbose SQL logging available (SQLALCHEMY_ECHO=true)
- In-memory token blacklist (resets on restart)
- CORS allows localhost:3000
- Hot reload enabled in Docker volumes

### Production (FLASK_ENV=production)
- Debug mode disabled
- Requires: SECRET_KEY, JWT_SECRET_KEY, DATABASE_URL, S3 credentials
- Session cookies require HTTPS (SESSION_COOKIE_SECURE=true)
- Use Redis for token blacklist
- Use Vault for secrets management
- Enable rate limiting

### Testing (FLASK_ENV=testing)
- SQLite in-memory database (fast)
- Kafka events disabled by default
- Fast bcrypt hashing (4 rounds)
- Rate limiting disabled
- Short token expiry (1 min access, 5 min refresh)

## Port Mappings

- **4999**: Flask API (NOT 5000 - avoids Airplay conflict on macOS)
- **5432**: PostgreSQL database
- **5555**: Flower dashboard (Celery monitoring)
- **6379**: Redis (cache, sessions, Celery broker)
- **8201**: Vault UI (NOT 8200 - avoids OneDrive conflict on macOS)
- **9000**: MinIO API (S3-compatible storage)
- **9001**: MinIO Console (web UI)
- **9092**: Kafka broker (event streaming)
- **2181**: Zookeeper (Kafka coordination)

## Critical Architecture Decisions

### Database Isolation Strategy
- **Main DB**: Only stores Users, Tenants, UserTenantAssociations, TenantSSOConfig, UserAzureIdentity
- **Tenant DBs**: Only store Files and Documents (never in main DB)
- **Migration Filter**: The `include_object` filter in migrations/env.py prevents File/Document tables from being created in main DB

### Service Dependencies
When working with services, understand their dependencies:
```python
# Services should NEVER import from routes
# Services can import from: models, schemas, utils, other services
# Routes should import from: services, schemas, decorators
```

### Flask Context in Celery
Celery workers need a minimal Flask app without routes to avoid conflicts:
```python
# backend/celery_worker.py creates minimal app
# backend/app/celery_app.py manages Celery configuration
```

### Token Storage Strategy
- **JWT Access Tokens**: Short-lived (15 min), stateless
- **JWT Refresh Tokens**: Long-lived (7 days), tracked in blacklist
- **Azure AD Tokens**: Encrypted with Vault Transit, stored in UserAzureIdentity
- **SSO Sessions**: Stored in Redis with TTL

## Additional Resources

- **Architecture**: See [README.md](README.md) for comprehensive overview
- **Docker Deployment**: See [DOCKER.md](DOCKER.md) for production setup
- **Database Design**: See [DATABASES.md](DATABASES.md) for schema details
- **Testing**: See [TESTS.md](TESTS.md) for test strategy
- **API Docs**: See [swagger.yaml](swagger.yaml) or http://localhost:4999/api/docs
