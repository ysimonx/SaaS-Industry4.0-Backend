# Implementation Plan - SaaS Multi-Tenant Backend Platform

## Project Overview
Building a multi-tenant SaaS backend platform with Flask, PostgreSQL, Kafka, and S3 storage. The platform supports isolated tenant databases, JWT authentication, asynchronous document processing, and RESTful APIs.

**Key Architectural Principle**: Strict layered architecture
```
Routes (Controllers) → Services (Business Logic) → Models → Database
```

---

## Implementation Progress

### Completed Tasks
- ✅ **Task 1**: Create Base Project Structure (Phase 1) - *Completed*
  - All directories created with proper `__init__.py` files
  - Directory structure: backend/app/{routes,services,models,schemas,utils,worker}, backend/{migrations,tests/{unit,integration},docker,docs}
- ✅ **Task 2**: Configuration Setup (Phase 1) - *Completed*
  - `.env.example` with all environment variables documented
  - `backend/app/config.py` with Development, Production, and Testing configurations
- ✅ **Task 3**: Create Requirements File (Phase 1) - *Completed*
  - `backend/requirements.txt` with all Python dependencies and pinned versions
  - 89 lines organized into sections: Web Framework, Database & ORM, Authentication, Kafka, S3, Development/Testing

### In Progress
- 🔄 **Task 4**: Create Core Utilities (Phase 1) - *Next*

### Pending
- ⏳ Tasks 4-44: Remaining implementation tasks

---

## Phase 1: Project Foundation & Core Infrastructure

### Task 1: Create Base Project Structure ✅ COMPLETED
**Priority**: Critical
**Dependencies**: None
**Status**: ✅ Completed

Create the complete directory structure:
```
backend/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── routes/
│   │   └── __init__.py
│   ├── services/
│   │   └── __init__.py
│   ├── models/
│   │   └── __init__.py
│   ├── schemas/
│   │   └── __init__.py
│   ├── utils/
│   │   └── __init__.py
│   └── worker/
│       └── __init__.py
├── migrations/
├── tests/
│   ├── __init__.py
│   ├── unit/
│   └── integration/
├── docker/
└── docs/
```

**Deliverables**:
- ✅ All directories created with proper `__init__.py` files
- ✅ Empty placeholder files for main modules

**Completion Notes**:
- Created complete directory structure under `backend/`
- All Python packages initialized with `__init__.py` files
- Test directories (unit/integration) ready for future tests
- Docker and docs folders prepared for Phase 8 and 9

---

### Task 2: Configuration Setup ✅ COMPLETED
**Priority**: Critical
**Dependencies**: 1
**Status**: ✅ Completed

**Files to create**:
1. **`.env.example`** - Template for environment variables
2. **`app/config.py`** - Configuration class with environment-based settings

**Configuration sections**:
- Database connection (main + tenant databases)
- JWT settings (secret key, token expiration times)
- Kafka broker settings
- S3 connection details (endpoint, credentials, bucket, region)
- Flask settings (port 4999, debug mode, etc.)
- Logging configuration

**Key configurations**:
```python
# Database
DATABASE_URL = postgresql://user:pass@localhost/saas_platform
DATABASE_POOL_SIZE = 10

# JWT
JWT_SECRET_KEY = (secure random key)
JWT_ACCESS_TOKEN_EXPIRES = 900  # 15 minutes
JWT_REFRESH_TOKEN_EXPIRES = 604800  # 7 days

# Flask
FLASK_PORT = 4999  # NOT 5000!
```

**Deliverables**:
- ✅ `.env.example` with all required variables documented
- ✅ `config.py` with Config classes (Development, Production, Testing)

**Completion Notes**:
- Created comprehensive `.env.example` with 100+ documented environment variables
- Implemented `Config` base class with all settings loaded from environment
- Created `DevelopmentConfig` with debug mode and verbose logging
- Created `ProductionConfig` with security validation and required var checks
- Created `TestingConfig` optimized for fast unit/integration tests
- All configurations support: Database, JWT, Kafka, S3, CORS, Logging, Rate Limiting
- Flask runs on port 4999 (not 5000) as specified
- JWT tokens: 15min access, 7 days refresh
- Config dictionary for easy access: `config['development']`, etc.

---

### Task 3: Create Requirements File ✅ COMPLETED
**Priority**: High
**Dependencies**: 1
**Status**: ✅ Completed

Create `backend/requirements.txt` by installing packages and freezing dependencies.

**Process**:
1. Create virtual environment: `python -m venv venv`
2. Activate virtual environment
3. Install required packages:
```bash
pip install Flask>=2.3.0
pip install SQLAlchemy>=2.0.0
pip install Flask-Migrate
pip install Flask-JWT-Extended
pip install marshmallow>=3.20.0
pip install kafka-python
pip install boto3
pip install psycopg2-binary
pip install gunicorn
pip install python-dotenv
pip install Flask-CORS
pip install bcrypt
```
4. Generate requirements file: `pip freeze > requirements.txt`
5. Move to `backend/requirements.txt`

**Required packages**:
- Flask >= 2.3.0 - Web framework
- SQLAlchemy >= 2.0.0 - ORM
- Flask-Migrate - Database migrations
- Flask-JWT-Extended - JWT authentication
- Marshmallow >= 3.20.0 - Data validation/serialization
- kafka-python - Kafka integration
- boto3 - S3 client
- psycopg2-binary - PostgreSQL adapter
- gunicorn - WSGI server
- python-dotenv - Environment variables
- Flask-CORS - CORS support
- bcrypt - Password hashing

**Deliverables**:
- ✅ `backend/requirements.txt` with all dependencies and pinned versions from pip freeze
- ✅ Virtual environment setup instructions in README
- ✅ Clean, reproducible dependency list

**Completion Notes**:
- Created comprehensive `backend/requirements.txt` with 89 lines of dependencies
- All packages have specific version pinning for reproducibility:
  - Flask 3.0.0, SQLAlchemy 2.0.25, Flask-Migrate 4.0.5
  - Flask-JWT-Extended 4.6.0, bcrypt 4.1.2, cryptography 42.0.0
  - marshmallow 3.20.2, kafka-python 2.0.2, boto3 1.34.34
  - psycopg2-binary 2.9.9, gunicorn 21.2.0, python-dotenv 1.0.1
- Organized into clear sections: Web Framework, Database & ORM, Authentication & Security, Data Validation, Kafka, AWS S3, HTTP & CORS, Environment, WSGI Server, Utilities
- Included development/testing packages: pytest 7.4.4, black 24.1.1, flake8 7.0.0, mypy 1.8.0
- Added type stubs for better IDE support and type checking

---

### Task 4: Create Core Utilities
**Priority**: High
**Dependencies**: 2

**Files to create**:

1. **`app/utils/responses.py`**
   - `success_response(data, message, status_code)` - Standard success format
   - `error_response(code, message, details, status_code)` - Standard error format
   - Helper functions for common HTTP responses

2. **`app/utils/database.py`**
   - Database session management
   - Multi-database connection factory
   - Tenant database creation utility
   - Connection pooling configuration

3. **`app/utils/decorators.py`**
   - `@jwt_required_custom` - JWT validation decorator
   - `@tenant_required` - Tenant context validation
   - `@role_required(role)` - Role-based access control

**Deliverables**:
- Standardized JSON response format for all API endpoints
- Database utility functions for multi-tenant support
- Security decorators for routes

---

## Phase 2: SQLAlchemy Models (PRIORITY)

### Task 5: Create BaseModel Abstract Class
**Priority**: Critical
**Dependencies**: 3, 4

**File**: `app/models/base.py`

**Implementation**:
```python
class BaseModel:
    """Abstract base model with common fields"""
    id: UUID (primary_key, default=uuid4)
    created_at: DateTime (UTC, default=utcnow)
    updated_at: DateTime (UTC, onupdate=utcnow)
    created_by: UUID (nullable for self-registration)
```

**Features**:
- UUID primary key generation
- Automatic timestamp management
- Audit trail support with created_by field
- `to_dict()` method for serialization
- `__repr__()` for debugging

**Deliverables**:
- `BaseModel` class with all common fields
- Helper methods for JSON serialization
- Proper UTC timezone handling

---

### Task 6: Create User Model
**Priority**: Critical
**Dependencies**: 5

**File**: `app/models/user.py`

**Schema**:
```python
class User(BaseModel, db.Model):
    __tablename__ = 'users'
    __bind_key__ = 'main'  # Main database

    first_name: String(100), required
    last_name: String(100), required
    email: String(255), unique, indexed, required
    password_hash: String(255), required
    is_active: Boolean, default=True

    # Relationships
    tenant_associations: relationship('UserTenantAssociation')
```

**Methods to implement**:
- `set_password(password)` - Hash password with bcrypt
- `check_password(password)` - Verify password
- `get_tenants()` - Return list of associated tenants
- `has_access_to_tenant(tenant_id)` - Check tenant membership

**Validations**:
- Email must be valid format and unique
- Password minimum 8 characters
- Names must be non-empty

**Deliverables**:
- Complete User model with password hashing
- Relationship to tenants via association table
- Utility methods for authentication

---

### Task 7: Create Tenant Model
**Priority**: Critical
**Dependencies**: 5

**File**: `app/models/tenant.py`

**Schema**:
```python
class Tenant(BaseModel, db.Model):
    __tablename__ = 'tenants'
    __bind_key__ = 'main'  # Main database

    name: String(255), required
    database_name: String(63), unique, required  # PostgreSQL max 63 chars
    is_active: Boolean, default=True

    # Relationships
    user_associations: relationship('UserTenantAssociation')
```

**Methods to implement**:
- `generate_database_name()` - Create unique DB name from tenant name
- `create_database()` - Create isolated tenant database
- `get_connection_string()` - Return tenant-specific connection URL
- `get_users()` - Return all associated users
- `delete_database()` - Drop tenant database (with safety checks)

**Validations**:
- Database name must be PostgreSQL-compatible (alphanumeric + underscore)
- Tenant name required and non-empty
- Database name must be unique

**Deliverables**:
- Complete Tenant model with database management
- Auto-generation of database names
- Safety checks for database operations

---

### Task 8: Create UserTenantAssociation Model
**Priority**: Critical
**Dependencies**: 6, 7

**File**: `app/models/user_tenant_association.py`

**Schema**:
```python
class UserTenantAssociation(db.Model):
    __tablename__ = 'user_tenant_associations'
    __bind_key__ = 'main'  # Main database

    user_id: UUID, ForeignKey('users.id'), primary_key
    tenant_id: UUID, ForeignKey('tenants.id'), primary_key
    role: String(50), required  # 'admin', 'user', 'viewer'
    joined_at: DateTime (UTC, default=utcnow)

    # Relationships
    user: relationship('User')
    tenant: relationship('Tenant')
```

**Validations**:
- Role must be one of: 'admin', 'user', 'viewer'
- Composite primary key prevents duplicate associations
- Cascading delete when user or tenant is removed

**Deliverables**:
- Association model with role-based access
- Proper foreign key relationships
- Role validation

---

### Task 9: Create File Model (Tenant Database)
**Priority**: Critical
**Dependencies**: 5

**File**: `app/models/file.py`

**Schema**:
```python
class File(BaseModel, db.Model):
    __tablename__ = 'files'
    __bind_key__ = None  # Dynamic binding to tenant database

    md5_hash: String(32), indexed, required
    s3_path: String(500), required
    file_size: BigInteger, required

    # Relationships
    documents: relationship('Document', back_populates='file')
```

**Methods to implement**:
- `check_duplicate(tenant_id, md5_hash)` - Check if file exists
- `get_s3_url()` - Generate pre-signed S3 URL
- `is_orphaned()` - Check if file has no document references
- `delete_from_s3()` - Remove file from S3 storage

**Validations**:
- MD5 hash must be 32 hex characters
- S3 path must be valid
- File size must be positive

**Deliverables**:
- File model with deduplication support
- S3 integration methods
- Orphan detection logic

---

### Task 10: Create Document Model (Tenant Database)
**Priority**: Critical
**Dependencies**: 5, 9

**File**: `app/models/document.py`

**Schema**:
```python
class Document(BaseModel, db.Model):
    __tablename__ = 'documents'
    __bind_key__ = None  # Dynamic binding to tenant database

    filename: String(255), required
    mime_type: String(100), required
    file_id: UUID, ForeignKey('files.id'), required
    user_id: UUID, required  # Reference to user in main DB

    # Relationships
    file: relationship('File', back_populates='documents')
```

**Methods to implement**:
- `get_download_url()` - Generate pre-signed download URL
- `get_owner()` - Fetch user from main database
- `update_metadata(filename, mime_type)` - Update document info

**Validations**:
- Filename required and non-empty
- MIME type must be valid format
- file_id must reference existing file

**Deliverables**:
- Document model with file relationship
- Cross-database user reference
- Download URL generation

---

### Task 11: Configure Multi-Database Bindings
**Priority**: Critical
**Dependencies**: 6, 7, 8, 9, 10

**File**: `app/utils/database.py` (enhancement)

**Implementation**:
1. Configure SQLAlchemy with `SQLALCHEMY_BINDS`
2. Create dynamic tenant database connection factory
3. Implement context manager for tenant database sessions
4. Set up connection pooling for main and tenant databases

**Key features**:
```python
# Main database
db.session  # Default session for User, Tenant, Association

# Tenant database (dynamic)
with tenant_db_session(tenant_id) as session:
    # Work with Documents and Files
    documents = session.query(Document).all()
```

**Deliverables**:
- Multi-database configuration in SQLAlchemy
- Tenant database session factory
- Proper connection pooling
- Context managers for safe database access

---

## Phase 3: Marshmallow Schemas

### Task 12: Create UserSchema
**Priority**: High
**Dependencies**: 6

**File**: `app/schemas/user_schema.py`

**Implementation**:
```python
class UserSchema(Schema):
    id = fields.UUID(dump_only=True)
    first_name = fields.Str(required=True, validate=Length(min=1, max=100))
    last_name = fields.Str(required=True, validate=Length(min=1, max=100))
    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True, validate=Length(min=8))
    is_active = fields.Boolean(load_default=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
```

**Variants**:
- `UserCreateSchema` - For registration (with password)
- `UserUpdateSchema` - For profile updates (no password)
- `UserResponseSchema` - For API responses (no sensitive data)

**Deliverables**:
- Complete validation schemas for User operations
- Password handling (load_only, never dumped)
- Email format validation

---

### Task 13: Create TenantSchema
**Priority**: High
**Dependencies**: 7

**File**: `app/schemas/tenant_schema.py`

**Implementation**:
```python
class TenantSchema(Schema):
    id = fields.UUID(dump_only=True)
    name = fields.Str(required=True, validate=Length(min=1, max=255))
    database_name = fields.Str(dump_only=True)  # Auto-generated
    is_active = fields.Boolean(load_default=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
```

**Deliverables**:
- Tenant validation schema
- Auto-generated fields marked as dump_only

---

### Task 14: Create DocumentSchema
**Priority**: High
**Dependencies**: 10

**File**: `app/schemas/document_schema.py`

**Implementation**:
```python
class DocumentSchema(Schema):
    id = fields.UUID(dump_only=True)
    filename = fields.Str(required=True, validate=Length(min=1, max=255))
    mime_type = fields.Str(required=True)
    file_id = fields.UUID(dump_only=True)  # Auto-assigned
    user_id = fields.UUID(dump_only=True)  # From JWT
    created_at = fields.DateTime(dump_only=True)
```

**Deliverables**:
- Document validation schema
- File upload handling schema

---

### Task 15: Create FileSchema
**Priority**: High
**Dependencies**: 9

**File**: `app/schemas/file_schema.py`

**Implementation**:
```python
class FileSchema(Schema):
    id = fields.UUID(dump_only=True)
    md5_hash = fields.Str(dump_only=True)
    s3_path = fields.Str(dump_only=True)
    file_size = fields.Integer(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
```

**Deliverables**:
- File metadata schema
- All fields dump_only (files are immutable)

---

## Phase 4: Flask Application Setup

### Task 16: Create Flask App Factory
**Priority**: Critical
**Dependencies**: 2, 11

**File**: `app/__init__.py`

**Implementation**:
```python
def create_app(config_name='development'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app)

    # Register blueprints
    from app.routes import auth, users, tenants, documents, files
    app.register_blueprint(auth.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(tenants.bp)
    app.register_blueprint(documents.bp)
    app.register_blueprint(files.bp)

    return app
```

**Deliverables**:
- App factory pattern implementation
- Extension initialization
- Blueprint registration
- Configuration loading

---

### Task 17: Initialize Database Extensions
**Priority**: Critical
**Dependencies**: 16

**Files to update**:
- `app/__init__.py` - Extension instances
- `app/models/__init__.py` - Import all models

**Extensions to initialize**:
- SQLAlchemy (db)
- Flask-Migrate (migrate)
- Flask-JWT-Extended (jwt)
- Flask-CORS (cors)

**Deliverables**:
- All extensions properly initialized
- Models imported for migration detection

---

### Task 18: Set Up Database Migrations
**Priority**: High
**Dependencies**: 17

**Commands to run**:
```bash
flask db init
flask db migrate -m "Initial migration: users, tenants, associations"
flask db upgrade
```

**Migration strategy**:
- Main database: User, Tenant, UserTenantAssociation tables
- Tenant databases: Created dynamically via TenantService
- Separate migration scripts for tenant database schema

**Deliverables**:
- Initial migration for main database
- Migration script template for tenant databases
- Database initialization script

---

## Phase 5: Flask Routes/Blueprints (PRIORITY)

### Task 19: Create Auth Blueprint
**Priority**: Critical
**Dependencies**: 12, 16

**File**: `app/routes/auth.py`

**Endpoints**:

1. **POST /api/auth/register**
   - Input: email, password, first_name, last_name
   - Validation: UserCreateSchema
   - Action: Create new user account
   - Response: User object (without password)

2. **POST /api/auth/login**
   - Input: email, password
   - Validation: Email format, password presence
   - Action: Authenticate user, generate tokens
   - Response:
     ```json
     {
       "access_token": "...",
       "refresh_token": "...",
       "user": {...},
       "tenants": [...]
     }
     ```

3. **POST /api/auth/refresh**
   - Input: refresh_token (from header or body)
   - Validation: JWT refresh token
   - Action: Generate new access token
   - Response: New access_token

4. **POST /api/auth/logout**
   - Input: access_token (from header)
   - Validation: JWT required
   - Action: Add token to blacklist
   - Response: Success message

**Security**:
- Password hashing with bcrypt
- JWT with 15min access token, 7 day refresh token
- Token blacklist for logout
- Rate limiting on login endpoint

**Deliverables**:
- Complete auth blueprint with 4 endpoints
- JWT token generation and validation
- Secure password handling

---

### Task 20: Create Users Blueprint
**Priority**: High
**Dependencies**: 12, 16, 19

**File**: `app/routes/users.py`

**Endpoints**:

1. **GET /api/users/me**
   - Auth: JWT required
   - Action: Return current user profile
   - Response: User object

2. **PUT /api/users/me**
   - Auth: JWT required
   - Input: first_name, last_name (email not changeable)
   - Validation: UserUpdateSchema
   - Action: Update user profile
   - Response: Updated user object

3. **GET /api/users/me/tenants**
   - Auth: JWT required
   - Action: Return list of user's tenants with roles
   - Response: List of tenants with user's role in each

**Deliverables**:
- Users blueprint with 3 endpoints
- JWT-protected routes
- User profile management

---

### Task 21: Create Tenants Blueprint
**Priority**: High
**Dependencies**: 13, 16, 19

**File**: `app/routes/tenants.py`

**Endpoints**:

1. **GET /api/tenants**
   - Auth: JWT required
   - Action: List all tenants user has access to
   - Response: List of tenants

2. **POST /api/tenants**
   - Auth: JWT required
   - Input: name
   - Validation: TenantSchema
   - Action: Create tenant + database + make user admin
   - Response: Created tenant object

3. **GET /api/tenants/{tenant_id}**
   - Auth: JWT + tenant membership required
   - Action: Get tenant details
   - Response: Tenant object with member list

4. **PUT /api/tenants/{tenant_id}**
   - Auth: JWT + admin role required
   - Input: name, is_active
   - Validation: TenantSchema
   - Action: Update tenant
   - Response: Updated tenant object

5. **DELETE /api/tenants/{tenant_id}**
   - Auth: JWT + admin role required
   - Action: Soft delete tenant (mark inactive)
   - Response: Success message

6. **POST /api/tenants/{tenant_id}/users**
   - Auth: JWT + admin role required
   - Input: user_id, role
   - Action: Add user to tenant with role
   - Response: Association created

7. **DELETE /api/tenants/{tenant_id}/users/{user_id}**
   - Auth: JWT + admin role required
   - Action: Remove user from tenant
   - Response: Success message

**Role-based access control**:
- admin: All operations
- user: Read tenant info
- viewer: Read-only access

**Deliverables**:
- Complete tenant management blueprint
- Role-based access control
- Tenant member management

---

### Task 22: Create Documents Blueprint
**Priority**: High
**Dependencies**: 14, 16, 19, 21

**File**: `app/routes/documents.py`

**Endpoints**:

1. **GET /api/tenants/{tenant_id}/documents**
   - Auth: JWT + tenant membership required
   - Query params: page, per_page, filename (filter)
   - Action: List documents with pagination
   - Response: Paginated document list

2. **POST /api/tenants/{tenant_id}/documents**
   - Auth: JWT + tenant membership required
   - Input: multipart/form-data with file + metadata
   - Validation: File size (max 100MB), DocumentSchema
   - Action: Upload file to S3, create document record, send Kafka message
   - Response: Created document object

3. **GET /api/tenants/{tenant_id}/documents/{document_id}**
   - Auth: JWT + tenant membership required
   - Action: Get document details
   - Response: Document object with file info

4. **GET /api/tenants/{tenant_id}/documents/{document_id}/download**
   - Auth: JWT + tenant membership required
   - Action: Generate pre-signed S3 URL
   - Response: Redirect to S3 URL or return URL

5. **PUT /api/tenants/{tenant_id}/documents/{document_id}**
   - Auth: JWT + tenant membership required
   - Input: filename, mime_type (metadata only)
   - Validation: DocumentSchema
   - Action: Update document metadata
   - Response: Updated document object

6. **DELETE /api/tenants/{tenant_id}/documents/{document_id}**
   - Auth: JWT + tenant membership required
   - Action: Delete document record, send Kafka message
   - Response: Success message

**Features**:
- Multipart file upload handling
- File size validation (100MB limit)
- S3 pre-signed URL generation
- Kafka integration for async processing
- Pagination for list endpoint

**Deliverables**:
- Complete document management blueprint
- File upload/download handling
- Tenant context validation

---

### Task 23: Create Files Blueprint
**Priority**: Medium
**Dependencies**: 15, 16, 19, 21

**File**: `app/routes/files.py`

**Endpoints**:

1. **GET /api/tenants/{tenant_id}/files**
   - Auth: JWT + tenant membership required
   - Query params: page, per_page
   - Action: List all files in tenant database
   - Response: Paginated file list

2. **GET /api/tenants/{tenant_id}/files/{file_id}**
   - Auth: JWT + tenant membership required
   - Action: Get file details with document references
   - Response: File object with list of documents using it

3. **DELETE /api/tenants/{tenant_id}/files/{file_id}**
   - Auth: JWT + admin role required
   - Validation: Check if file is orphaned (no document references)
   - Action: Delete file record + S3 object
   - Response: Success message or error if file in use

**Safety checks**:
- Cannot delete file with document references
- Orphan detection before deletion
- S3 cleanup on successful deletion

**Deliverables**:
- File management blueprint
- Orphan file detection
- Safe deletion with validation

---

### Task 24: Create Kafka Demo Blueprint
**Priority**: Low
**Dependencies**: 16, 19

**File**: `app/routes/kafka_demo.py`

**Endpoints**:

1. **POST /api/demo/kafka/produce**
   - Auth: JWT required
   - Input: topic, message
   - Action: Produce test message to Kafka
   - Response: Message sent confirmation

2. **GET /api/demo/kafka/consume**
   - Auth: JWT required
   - Action: Return status of Kafka consumer
   - Response: Consumer status, last messages

**Purpose**: Testing and demonstration of Kafka integration

**Deliverables**:
- Demo endpoints for Kafka testing
- Simple message producer/consumer examples

---

## Phase 6: Services Layer

### Task 25: Create AuthService
**Priority**: Critical
**Dependencies**: 6, 12

**File**: `app/services/auth_service.py`

**Methods**:

1. **authenticate(email, password)**
   - Validate email/password
   - Check user exists and is active
   - Verify password hash
   - Generate access + refresh tokens
   - Fetch user's tenants
   - Return tokens + user + tenants

2. **refresh_token(refresh_token)**
   - Validate refresh token
   - Check token not blacklisted
   - Generate new access token
   - Return new access token

3. **logout(user_id, token_jti)**
   - Add token JTI to blacklist
   - Set expiration on blacklist entry
   - Return success

4. **register(user_data)**
   - Validate user data
   - Check email uniqueness
   - Hash password
   - Create user record
   - Return user object

**Deliverables**:
- Complete authentication service
- JWT token management
- Token blacklist implementation
- Password hashing/verification

---

### Task 26: Create UserService
**Priority**: High
**Dependencies**: 6, 8

**File**: `app/services/user_service.py`

**Methods**:

1. **get_user_by_id(user_id)**
   - Fetch user by UUID
   - Return user object or None

2. **get_user_by_email(email)**
   - Fetch user by email
   - Return user object or None

3. **update_user(user_id, user_data)**
   - Validate update data
   - Update user fields
   - Commit transaction
   - Return updated user

4. **get_user_tenants(user_id)**
   - Join User → UserTenantAssociation → Tenant
   - Return list of tenants with roles
   - Include tenant active status

**Deliverables**:
- User CRUD operations
- Tenant membership queries
- Transaction management

---

### Task 27: Create TenantService
**Priority**: Critical
**Dependencies**: 7, 8, 9, 10

**File**: `app/services/tenant_service.py`

**Methods**:

1. **create_tenant(tenant_data, creator_user_id)**
   - Validate tenant data
   - Generate unique database_name
   - Create tenant record in main DB
   - **Create tenant database** with Document/File tables
   - Add creator as admin to tenant
   - Send Kafka message (tenant.created)
   - Return tenant object

2. **get_tenant(tenant_id)**
   - Fetch tenant by ID
   - Return tenant object

3. **update_tenant(tenant_id, tenant_data)**
   - Validate update data
   - Update tenant fields
   - Commit transaction
   - Return updated tenant

4. **delete_tenant(tenant_id)**
   - Soft delete (set is_active = False)
   - OR hard delete with database drop
   - Send Kafka message (tenant.deleted)
   - Return success

5. **add_user_to_tenant(tenant_id, user_id, role)**
   - Validate user and tenant exist
   - Check no existing association
   - Create UserTenantAssociation
   - Return association object

6. **remove_user_from_tenant(tenant_id, user_id)**
   - Find association
   - Delete association
   - Return success

7. **get_tenant_users(tenant_id)**
   - Fetch all users in tenant
   - Include roles
   - Return user list

**Database creation logic**:
```python
def create_tenant_database(database_name):
    # 1. Create PostgreSQL database
    # 2. Run migrations to create Document/File tables
    # 3. Set up proper permissions
```

**Deliverables**:
- Complete tenant management service
- Dynamic database creation
- User association management
- Kafka integration for tenant events

---

### Task 28: Create DocumentService
**Priority**: Critical
**Dependencies**: 10, 29, 30

**File**: `app/services/document_service.py`

**Methods**:

1. **create_document(tenant_id, file_obj, metadata, user_id)**
   - Calculate file MD5 hash
   - Check for duplicate file in tenant
   - If duplicate: reuse existing file_id
   - If new: upload to S3, create File record
   - Create Document record
   - Send Kafka message (document.uploaded)
   - Return document object

2. **get_document(tenant_id, document_id)**
   - Switch to tenant database context
   - Fetch document with file relationship
   - Return document object

3. **list_documents(tenant_id, filters, pagination)**
   - Switch to tenant database context
   - Apply filters (filename, user_id, date range)
   - Apply pagination
   - Return paginated results

4. **update_document(tenant_id, document_id, metadata)**
   - Switch to tenant database context
   - Update filename/mime_type
   - Commit transaction
   - Return updated document

5. **delete_document(tenant_id, document_id)**
   - Switch to tenant database context
   - Delete document record
   - Check if file is orphaned
   - If orphaned: schedule file cleanup
   - Send Kafka message (document.deleted)
   - Return success

**Deliverables**:
- Document CRUD with tenant context
- File deduplication logic
- Kafka integration for document events
- Tenant database session management

---

### Task 29: Create FileService
**Priority**: Critical
**Dependencies**: 9, 31

**File**: `app/services/file_service.py`

**Methods**:

1. **upload_file(tenant_id, file_obj)**
   - Calculate MD5 hash
   - Check duplicate via check_duplicate()
   - If duplicate: return existing file_id
   - If new:
     - Generate S3 path: `tenants/{tenant_id}/files/{year}/{month}/{file_id}_{md5_hash}`
     - Upload to S3 with metadata
     - Create File record
     - Return file_id

2. **get_file(tenant_id, file_id)**
   - Switch to tenant database context
   - Fetch file record
   - Return file object

3. **check_duplicate(tenant_id, md5_hash)**
   - Switch to tenant database context
   - Query File by md5_hash
   - Return file_id if exists, None otherwise

4. **delete_file(tenant_id, file_id)**
   - Check if file is orphaned
   - If yes:
     - Delete S3 object
     - Delete File record
     - Return success
   - If no: raise error "File in use"

5. **delete_orphaned_files(tenant_id)**
   - Find all files with no document references
   - Delete from S3
   - Delete File records
   - Return count of deleted files

6. **generate_download_url(tenant_id, file_id, expires_in=3600)**
   - Fetch file record
   - Generate pre-signed S3 URL
   - Return URL

**S3 path structure**:
```
bucket/tenants/{tenant_id}/files/{year}/{month}/{file_id}_{md5_hash}
```

**Deliverables**:
- File upload with deduplication
- S3 integration with proper paths
- Pre-signed URL generation
- Orphan file cleanup

---

### Task 30: Create KafkaService
**Priority**: High
**Dependencies**: None

**File**: `app/services/kafka_service.py`

**Methods**:

1. **produce_message(topic, event_type, tenant_id, user_id, data)**
   - Generate event_id (UUID)
   - Format message:
     ```json
     {
       "event_id": "uuid",
       "event_type": "document.uploaded",
       "tenant_id": "uuid",
       "user_id": "uuid",
       "timestamp": "2024-01-01T00:00:00Z",
       "data": {...}
     }
     ```
   - Send to Kafka topic
   - Return event_id

2. **consume_messages(topic, callback)**
   - Subscribe to topic
   - Poll for messages
   - Call callback(message) for each message
   - Handle errors and retries

**Topics**:
- `tenant.created`
- `tenant.deleted`
- `document.uploaded`
- `document.deleted`
- `file.process`
- `audit.log`

**Deliverables**:
- Kafka producer wrapper
- Kafka consumer wrapper
- Standard message format
- Error handling and retries

---

### Task 31: Create S3 Client Utility
**Priority**: Critical
**Dependencies**: 2

**File**: `app/utils/s3_client.py`

**Methods**:

1. **upload_file(file_obj, s3_path)**
   - Upload file to S3 bucket
   - Set content type
   - Return S3 path

2. **delete_file(s3_path)**
   - Delete object from S3
   - Return success

3. **generate_presigned_url(s3_path, expires_in=3600)**
   - Generate pre-signed GET URL
   - Set expiration time
   - Return URL

4. **check_file_exists(s3_path)**
   - Check if object exists in S3
   - Return boolean

**Configuration**:
- Use boto3 client
- Load credentials from environment
- Handle S3-compatible endpoints

**Deliverables**:
- S3 client wrapper with error handling
- Pre-signed URL generation
- File existence checks

---

## Phase 7: Infrastructure & External Services

### Task 32: Implement JWT Middleware
**Priority**: Critical
**Dependencies**: 17, 25

**File**: `app/utils/decorators.py` (enhancement)

**Implementation**:
- JWT token validation decorator
- Token blacklist checking
- User context injection into request
- Tenant context validation
- Role-based access control decorator

**Decorators**:
```python
@jwt_required_custom
@tenant_required(tenant_id_param='tenant_id')
@role_required(['admin', 'user'])
```

**Deliverables**:
- JWT validation middleware
- Token blacklist integration
- Request context management

---

### Task 33: Create Kafka Producer
**Priority**: High
**Dependencies**: 30

**File**: `app/worker/producer.py`

**Implementation**:
- Initialize Kafka producer
- Connection pooling
- Message serialization (JSON)
- Error handling and retries
- Logging

**Deliverables**:
- Kafka producer initialization
- Message formatting
- Error handling

---

### Task 34: Create Kafka Consumer Worker
**Priority**: High
**Dependencies**: 30, 33

**File**: `app/worker/consumer.py`

**Implementation**:
- Standalone Python process
- Subscribe to all topics
- Route messages to handlers based on event_type
- Process tenant.created → create tenant database
- Process document.uploaded → async S3 upload (if needed)
- Process document.deleted → cleanup orphaned files

**Message handlers**:
```python
def handle_tenant_created(message):
    # Create tenant database with Document/File tables

def handle_document_deleted(message):
    # Check if file is orphaned, cleanup if needed
```

**Deliverables**:
- Kafka consumer worker process
- Event handlers for each message type
- Error handling and dead letter queue
- Logging and monitoring

---

### Task 35: Create Startup Script
**Priority**: Medium
**Dependencies**: 18

**File**: `backend/scripts/init_db.py`

**Implementation**:
```python
# 1. Create main database if not exists
# 2. Run migrations
# 3. Create initial admin user (optional)
# 4. Create test tenant (optional)
```

**Deliverables**:
- Database initialization script
- Migration runner
- Optional seed data

---

## Phase 8: Docker Configuration

### Task 36: Create Dockerfile.api
**Priority**: High
**Dependencies**: 3

**File**: `docker/Dockerfile.api`

**Implementation**:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 4999
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:4999", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
```

**Deliverables**:
- Optimized Docker image for Flask API
- Multi-stage build (optional)
- Port 4999 exposed

---

### Task 37: Create Dockerfile.worker
**Priority**: High
**Dependencies**: 34

**File**: `docker/Dockerfile.worker`

**Implementation**:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "-m", "app.worker.consumer"]
```

**Deliverables**:
- Docker image for Kafka consumer worker
- Shared codebase with API

---

### Task 38: Create docker-compose.yml
**Priority**: High
**Dependencies**: 36, 37

**File**: `docker-compose.yml`

**Services**:
```yaml
services:
  postgres:
    image: postgres:14
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: saas_platform
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data

  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:latest
    ports: ["9092:9092"]
    depends_on: [zookeeper]
    environment:
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    ports: ["4999:4999"]
    depends_on: [postgres, kafka]
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres/saas_platform
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    volumes:
      - ./backend:/app

  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    depends_on: [postgres, kafka]
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres/saas_platform
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    volumes:
      - ./backend:/app

volumes:
  postgres_data:
```

**Deliverables**:
- Complete Docker Compose configuration
- All services properly networked
- Volume persistence for PostgreSQL

---

### Task 39: Create Environment Files
**Priority**: High
**Dependencies**: 2

**Files**:
1. `.env.example` - Template with all variables
2. `.env.development` - Development defaults
3. `.env.production` - Production template

**Variables to include**:
- Database URLs
- JWT secret key
- Kafka brokers
- S3 credentials
- Flask settings

**Deliverables**:
- Environment file templates
- Documentation for each variable

---

## Phase 9: Documentation & Testing

### Task 40: Create Swagger/OpenAPI Specification
**Priority**: Medium
**Dependencies**: 19, 20, 21, 22, 23

**File**: `swagger.yaml`

**Implementation**:
- OpenAPI 3.0 format
- All endpoints documented
- Request/response schemas
- Authentication schemes
- Example requests/responses

**Sections**:
- Info (title, version, description)
- Servers (development, production)
- Security schemes (JWT Bearer)
- Paths (all endpoints)
- Components (schemas, responses, parameters)

**Deliverables**:
- Complete OpenAPI 3.0 specification
- Swagger UI integration (optional)

---

### Task 41: Create README.md
**Priority**: High
**Dependencies**: 38

**File**: `README.md`

**Sections**:
1. Project Overview
2. Architecture Diagram
3. Tech Stack
4. Prerequisites
5. Installation Instructions
6. Environment Variables
7. Running with Docker
8. Running Locally
9. Database Migrations
10. API Documentation
11. Testing
12. Deployment
13. Contributing Guidelines

**Deliverables**:
- Comprehensive README
- Setup instructions
- Usage examples

---

### Task 42: Create Unit Tests
**Priority**: Medium
**Dependencies**: 25, 26, 27, 28, 29

**Files**: `tests/unit/test_*.py`

**Test coverage**:
- AuthService: authenticate, register, token refresh
- UserService: CRUD operations
- TenantService: tenant creation, user associations
- DocumentService: document upload, deduplication
- FileService: S3 upload, MD5 checking

**Test framework**: pytest

**Deliverables**:
- Unit tests for all services
- Mocking of external dependencies
- 80%+ code coverage

---

### Task 43: Create Integration Tests
**Priority**: Medium
**Dependencies**: 19, 20, 21, 22, 23

**Files**: `tests/integration/test_*.py`

**Test coverage**:
- Auth flow: register → login → access protected route
- Tenant creation: create tenant → verify database created
- Document upload: upload → verify in DB and S3
- Multi-tenancy isolation: verify data isolation between tenants

**Deliverables**:
- Integration tests for critical flows
- Test database setup/teardown
- S3 mocking for tests

---

### Task 44: Create Architecture Documentation
**Priority**: Low
**Dependencies**: All phases

**File**: `docs/ARCHITECTURE.md`

**Content**:
- Layered architecture explanation
- Multi-tenancy strategy
- Database schema diagrams
- Kafka message flows
- S3 storage structure
- Security considerations

**Deliverables**:
- Detailed architecture documentation
- Diagrams (ERD, sequence diagrams)

---

## Implementation Priorities Summary

### Critical Path (Must implement first):
1. **Models** (Phase 2): BaseModel → User → Tenant → Association → File → Document
2. **Config & Database** (Phase 1, 4): Config setup, app factory, multi-DB bindings
3. **Auth** (Phase 5.1, 6.1): Authentication service + routes
4. **Tenant Management** (Phase 5.3, 6.3): Tenant creation with database
5. **File/Document Services** (Phase 6.4, 6.5, 6.7): S3 + deduplication
6. **Document Routes** (Phase 5.4): File upload/download endpoints

### Secondary Priority:
7. Marshmallow schemas (Phase 3)
8. User routes (Phase 5.2)
9. File routes (Phase 5.5)
10. Kafka integration (Phase 6.6, 7.2, 7.3)
11. Docker setup (Phase 8)

### Low Priority:
12. Kafka demo routes
13. Tests (Phase 9.3, 9.4)
14. Documentation (Phase 9.1, 9.2, 9.5)

---

## Testing Strategy

### Unit Tests:
- All service methods
- Model methods (password hashing, validation)
- Utility functions (S3 client, response formatting)

### Integration Tests:
- Full API flows (register → login → upload → download)
- Multi-tenancy isolation
- Database operations

### Manual Testing Checklist:
- [ ] User registration and login
- [ ] JWT token refresh
- [ ] Tenant creation (verify database created)
- [ ] Add user to tenant with role
- [ ] Upload document (verify S3 + deduplication)
- [ ] Download document (pre-signed URL)
- [ ] Delete document (verify orphan cleanup)
- [ ] Multi-tenant isolation (users can't access other tenant data)
- [ ] Role-based access (viewer can't delete, admin can)

---

## Deployment Checklist

### Development:
- [ ] docker-compose up -d
- [ ] Run migrations
- [ ] Create test users and tenants
- [ ] Test API endpoints with Postman/curl

### Production:
- [ ] Set environment variables
- [ ] Configure S3 bucket and permissions
- [ ] Set up Kafka cluster
- [ ] Configure PostgreSQL with backups
- [ ] Set JWT secret (secure random key)
- [ ] Enable HTTPS
- [ ] Set up monitoring and logging
- [ ] Configure rate limiting
- [ ] Database backups automated

---

## Key Design Decisions

1. **Multi-Database Strategy**: Each tenant gets isolated PostgreSQL database for complete data separation
2. **File Deduplication**: MD5-based within tenant, no cross-tenant deduplication
3. **Async Processing**: Kafka for tenant creation, file processing, audit logs
4. **Authentication**: JWT with short-lived access tokens (15min) and refresh tokens (7 days)
5. **Port 4999**: Non-standard port to avoid conflicts with other Flask apps
6. **Soft Deletes**: Tenants marked inactive rather than hard deleted (preserves audit trail)
7. **Layered Architecture**: Strict separation - routes never access DB directly

---

## Future Enhancements (Phase 2+)

- WebSockets for real-time notifications
- Full-text search with Elasticsearch
- Document versioning
- Document sharing between users
- Analytics dashboard
- Bulk export functionality
- GraphQL API alternative
- Mobile SDK
- Redis caching for frequently accessed data
- Rate limiting per user/tenant

---

## Estimated Timeline

- **Phase 1**: 2 days - Foundation
- **Phase 2**: 3 days - Models & Database
- **Phase 3**: 1 day - Schemas
- **Phase 4**: 1 day - Flask setup
- **Phase 5**: 4 days - Routes (critical)
- **Phase 6**: 5 days - Services (critical)
- **Phase 7**: 2 days - Infrastructure
- **Phase 8**: 2 days - Docker
- **Phase 9**: 3 days - Docs & Testing

**Total**: ~23 days for full implementation

---

## Success Criteria

- [ ] All models implemented with proper relationships
- [ ] All API endpoints functional and documented
- [ ] JWT authentication working
- [ ] Multi-tenant database isolation verified
- [ ] File upload/download with S3 working
- [ ] Kafka producer/consumer operational
- [ ] Docker Compose brings up entire stack
- [ ] 80%+ test coverage
- [ ] Swagger documentation complete
- [ ] README with clear setup instructions

---

End of Implementation Plan
