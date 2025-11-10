# Architecture Documentation

## Table of Contents

1. [System Overview](#system-overview)
2. [Layered Architecture](#layered-architecture)
3. [Multi-Tenancy Strategy](#multi-tenancy-strategy)
4. [Database Architecture](#database-architecture)
5. [Authentication & Authorization](#authentication--authorization)
6. [File Storage Architecture](#file-storage-architecture)
7. [Kafka Message Processing](#kafka-message-processing)
8. [API Design](#api-design)
9. [Security Considerations](#security-considerations)
10. [Scalability & Performance](#scalability--performance)
11. [Deployment Architecture](#deployment-architecture)

---

## System Overview

### Purpose

The SaaS Multi-Tenant Backend Platform is a production-ready backend infrastructure designed to support multi-tenant SaaS applications with isolated data storage, asynchronous processing, and secure document management.

### Core Capabilities

- **Multi-Tenant Isolation**: Complete data isolation with dedicated databases per tenant
- **Authentication & Authorization**: JWT-based authentication with role-based access control (RBAC)
- **Document Management**: S3-based storage with MD5 deduplication within tenant boundaries
- **Asynchronous Processing**: Kafka-based message queue for background tasks
- **RESTful APIs**: Comprehensive REST APIs following OpenAPI 3.0 specification
- **Horizontal Scalability**: Stateless design supporting multiple API instances

### Technology Stack

```
┌─────────────────────────────────────────────────────────────┐
│                     Technology Stack                         │
├─────────────────────────────────────────────────────────────┤
│ Application Layer:   Flask 3.0.0 + Flask-RESTful            │
│ Authentication:      Flask-JWT-Extended (JWT tokens)         │
│ ORM:                 SQLAlchemy 2.0.23 + Flask-SQLAlchemy    │
│ Database:            PostgreSQL 15+ (Main + Tenant DBs)      │
│ Validation:          Marshmallow 3.20.1                      │
│ Message Queue:       Apache Kafka (aiokafka)                 │
│ Object Storage:      AWS S3 (boto3)                          │
│ WSGI Server:         Gunicorn (Production)                   │
│ Containerization:    Docker + Docker Compose                 │
│ Testing:             pytest + pytest-flask + pytest-asyncio  │
└─────────────────────────────────────────────────────────────┘
```

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Client Applications                             │
│                     (Web, Mobile, Third-party APIs)                      │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS/REST
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Load Balancer / API Gateway                     │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│  Flask API   │        │  Flask API   │        │  Flask API   │
│  Instance 1  │        │  Instance 2  │        │  Instance N  │
└──────┬───────┘        └──────┬───────┘        └──────┬───────┘
       │                       │                       │
       └───────────────────────┼───────────────────────┘
                               │
       ┌───────────────────────┼───────────────────────┬───────────────┐
       │                       │                       │               │
       ▼                       ▼                       ▼               ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐ ┌──────────────┐
│ PostgreSQL   │        │ Apache Kafka │        │   AWS S3     │ │    Redis     │
│ Main DB      │        │  Message     │        │   Object     │ │  Cache/Queue │
│ + Tenant DBs │        │  Broker      │        │   Storage    │ │  + Sessions  │
└──────────────┘        └──────┬───────┘        └──────────────┘ └─────┬────────┘
                               │                                        │
                               ▼                                        ▼
                        ┌──────────────┐                        ┌──────────────┐
                        │ Kafka Worker │                        │Celery Workers│
                        │  (Consumer)  │                        │  (SSO/Tasks) │
                        └──────────────┘                        └──────────────┘
```

---

## Layered Architecture

### Architectural Principle

The platform follows a **strict layered architecture** to ensure separation of concerns, testability, and maintainability:

```
┌─────────────────────────────────────────────────────────────┐
│                    Routes Layer (Controllers)                │
│  Responsibilities:                                           │
│  - HTTP request handling                                     │
│  - Request validation (schemas)                              │
│  - Response formatting                                       │
│  - Authentication/authorization decorators                   │
│  Files: backend/app/routes/*.py                              │
└────────────────────────┬────────────────────────────────────┘
                         │ Calls
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Services Layer (Business Logic)            │
│  Responsibilities:                                           │
│  - Business logic implementation                             │
│  - Transaction management                                    │
│  - Cross-model operations                                    │
│  - External service integration (S3, Kafka)                  │
│  Files: backend/app/services/*.py                            │
└────────────────────────┬────────────────────────────────────┘
                         │ Uses
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      Models Layer (Data Access)              │
│  Responsibilities:                                           │
│  - Database schema definitions                               │
│  - Data validation                                           │
│  - Query methods                                             │
│  - Model-specific business rules                             │
│  Files: backend/app/models/*.py                              │
└────────────────────────┬────────────────────────────────────┘
                         │ Queries
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                         Database Layer                       │
│  - PostgreSQL main database (users, tenants, associations)  │
│  - PostgreSQL tenant databases (files, documents)            │
└─────────────────────────────────────────────────────────────┘
```

### Layer Communication Rules

1. **Routes → Services**: Routes MUST call services, NEVER directly access models
2. **Services → Models**: Services use models for data operations
3. **No Reverse Dependencies**: Lower layers MUST NOT depend on upper layers
4. **Cross-Layer Communication**: Only adjacent layers communicate directly

### Example Request Flow

```python
# Example: User registration flow

# 1. Routes Layer (backend/app/routes/auth.py)
@auth_bp.route('/register', methods=['POST'])
def register():
    data = user_create_schema.load(request.get_json())  # Validation
    user, error = AuthService.register(data)             # Delegate to service
    if error:
        return error_response(...)
    return success_response(user.to_dict(), status_code=201)

# 2. Services Layer (backend/app/services/auth_service.py)
@staticmethod
def register(user_data: dict):
    # Check if user exists
    if User.query.filter_by(email=user_data['email']).first():
        return None, "User already exists"

    # Create user
    user = User(**user_data)
    user.set_password(user_data['password'])
    db.session.add(user)
    db.session.commit()
    return user, None

# 3. Models Layer (backend/app/models/user.py)
class User(BaseModel):
    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(...)
```

---

## Multi-Tenancy Strategy

### Database-per-Tenant Architecture

The platform implements **database-per-tenant isolation** for maximum security and data separation:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Main PostgreSQL Database                      │
│  Database: saas_main                                             │
├─────────────────────────────────────────────────────────────────┤
│  Tables:                                                         │
│  - users              (all platform users)                       │
│  - tenants            (tenant metadata + db names)               │
│  - user_tenant_assoc  (many-to-many with roles)                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              Tenant Database: tenant_acme_corp_abc123            │
│  Created dynamically when tenant is created                      │
├─────────────────────────────────────────────────────────────────┤
│  Tables:                                                         │
│  - files              (physical file metadata + S3 paths)        │
│  - documents          (user-visible document metadata)           │
│                                                                  │
│  Note: user_id in documents references users.id in main DB      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              Tenant Database: tenant_globex_xyz789               │
│  Completely isolated from other tenants                          │
├─────────────────────────────────────────────────────────────────┤
│  Tables:                                                         │
│  - files              (separate file storage)                    │
│  - documents          (separate document storage)                │
└─────────────────────────────────────────────────────────────────┘
```

### Database Naming Convention

Tenant databases follow a strict naming convention:

```python
# Format: tenant_{sanitized_name}_{short_uuid}
# Example: tenant_acme_corp_a1b2c3d4

# Generation logic (backend/app/models/tenant.py):
def _generate_database_name(self) -> str:
    # Sanitize name: lowercase, alphanumeric + underscores only
    clean_name = re.sub(r'[^a-z0-9_]', '_', self.name.lower())
    clean_name = re.sub(r'_+', '_', clean_name).strip('_')

    # Add unique identifier
    unique_id = str(uuid.uuid4())[:8]
    db_name = f"tenant_{clean_name}_{unique_id}"

    # PostgreSQL limit: 63 characters
    return db_name[:63]
```

### Multi-Database Binding Strategy

SQLAlchemy is configured to route models to the correct database:

```python
# Models in Main Database
class User(BaseModel):
    __tablename__ = 'users'
    # Stored in main database (default bind)

class Tenant(BaseModel):
    __tablename__ = 'tenants'
    # Stored in main database (default bind)

# Models in Tenant Databases
class File(BaseModel):
    __tablename__ = 'files'
    __bind_key__ = None  # Dynamic binding at runtime

class Document(BaseModel):
    __tablename__ = 'documents'
    __bind_key__ = None  # Dynamic binding at runtime

# Runtime binding (backend/app/utils/database.py):
@contextmanager
def tenant_db_session(tenant_db_name: str):
    """Context manager for tenant database sessions"""
    engine = create_engine(get_connection_string(tenant_db_name))
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

### Tenant Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                     Tenant Creation Flow                         │
└─────────────────────────────────────────────────────────────────┘

1. User creates tenant via POST /api/tenants
   ↓
2. TenantService.create_tenant() called
   ↓
3. Create Tenant record in main database
   ├─ Generate unique database name
   ├─ Save tenant metadata
   └─ Create UserTenantAssociation (creator = admin)
   ↓
4. Create physical PostgreSQL database
   ├─ Execute: CREATE DATABASE tenant_name
   └─ Set ownership and permissions
   ↓
5. Initialize tenant database schema
   ├─ Create files table
   ├─ Create documents table
   ├─ Create indexes
   └─ Create foreign key constraints
   ↓
6. Return tenant metadata to user
```

### Access Control Flow

```python
# Role-based access within tenant (backend/app/utils/decorators.py)

@jwt_required_custom
@tenant_access_required(['admin', 'user'])  # Allowed roles
def upload_document(tenant_id):
    # 1. JWT decorator extracts user_id from token → g.user_id
    # 2. Tenant decorator verifies:
    #    - User has association with tenant_id
    #    - User's role is in allowed_roles
    # 3. If authorized, set g.tenant_id and g.user_role
    # 4. Execute route logic
    pass
```

---

## Database Architecture

### Entity Relationship Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Main Database Schema                           │
└────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────┐
│         users           │
├─────────────────────────┤
│ id (UUID) PK            │
│ email (unique, indexed) │
│ password_hash           │
│ first_name              │
│ last_name               │
│ is_active               │
│ created_at              │
│ updated_at              │
└───────────┬─────────────┘
            │
            │ 1
            │
            │ N
┌───────────▼─────────────────────┐
│   user_tenant_association       │
├─────────────────────────────────┤
│ user_id (UUID) PK, FK           │
│ tenant_id (UUID) PK, FK         │
│ role (admin/user/viewer)        │
│ joined_at                       │
└───────────┬─────────────────────┘
            │ N
            │
            │ 1
┌───────────▼─────────────┐
│       tenants           │
├─────────────────────────┤
│ id (UUID) PK            │
│ name                    │
│ database_name (unique)  │
│ is_active               │
│ created_at              │
│ updated_at              │
└─────────────────────────┘


┌────────────────────────────────────────────────────────────────────────┐
│                      Tenant Database Schema                             │
│                   (Replicated per tenant database)                      │
└────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────┐
│         files           │
├─────────────────────────┤
│ id (UUID) PK            │
│ md5_hash (indexed)      │
│ s3_path (unique)        │
│ file_size               │
│ created_at              │
│ updated_at              │
└───────────┬─────────────┘
            │ 1
            │
            │ N
┌───────────▼─────────────┐
│      documents          │
├─────────────────────────┤
│ id (UUID) PK            │
│ filename (indexed)      │
│ mime_type               │
│ file_id (UUID) FK       │◄─── References files.id (same tenant DB)
│ user_id (UUID) indexed  │◄─── References users.id (main DB, no FK)
│ created_at (indexed)    │
│ updated_at              │
└─────────────────────────┘

Indexes:
- documents: (user_id, filename) composite
- documents: created_at DESC
- files: md5_hash
```

### Cross-Database References

Documents store `user_id` as a UUID reference to the main database's `users` table, but **without a foreign key constraint** (PostgreSQL doesn't support cross-database FKs):

```python
# backend/app/models/document.py
class Document(BaseModel):
    user_id = db.Column(
        db.UUID(as_uuid=True),
        nullable=False,
        index=True
        # NO FOREIGN KEY - cross-database reference
    )

    def get_owner(self):
        """Fetch user from main database"""
        from app.models.user import User
        return User.query.get(self.user_id)
```

### Database Constraints

```sql
-- Main Database Constraints

ALTER TABLE users
  ADD CONSTRAINT users_email_key UNIQUE (email);

ALTER TABLE tenants
  ADD CONSTRAINT tenants_database_name_key UNIQUE (database_name);

ALTER TABLE user_tenant_association
  ADD CONSTRAINT uta_pkey PRIMARY KEY (user_id, tenant_id);

ALTER TABLE user_tenant_association
  ADD CONSTRAINT uta_user_fk FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE user_tenant_association
  ADD CONSTRAINT uta_tenant_fk FOREIGN KEY (tenant_id)
    REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE user_tenant_association
  ADD CONSTRAINT uta_role_check CHECK (role IN ('admin', 'user', 'viewer'));

-- Tenant Database Constraints

ALTER TABLE files
  ADD CONSTRAINT files_s3_path_key UNIQUE (s3_path);

ALTER TABLE documents
  ADD CONSTRAINT documents_file_fk FOREIGN KEY (file_id)
    REFERENCES files(id) ON DELETE RESTRICT;
```

---

## Authentication & Authorization

### JWT-Based Authentication

The platform uses **JWT (JSON Web Tokens)** for stateless authentication:

```
┌────────────────────────────────────────────────────────────────┐
│                    Authentication Flow                          │
└────────────────────────────────────────────────────────────────┘

1. Registration (POST /api/auth/register)
   ├─ User submits email, password, names
   ├─ Password hashed with bcrypt
   ├─ User record created in database
   └─ JWT access + refresh tokens returned

2. Login (POST /api/auth/login)
   ├─ User submits email, password
   ├─ Password verified with bcrypt
   ├─ JWT access + refresh tokens generated
   └─ Tokens returned to client

3. Token Structure
   Access Token (15 minutes):
   {
     "sub": "user-uuid-here",      # User ID
     "type": "access",
     "exp": 1234567890,             # Expiration
     "iat": 1234567000,             # Issued at
     "fresh": true                  # Fresh login
   }

   Refresh Token (30 days):
   {
     "sub": "user-uuid-here",
     "type": "refresh",
     "exp": 1237159000
   }

4. Protected Route Access
   ├─ Client sends: Authorization: Bearer <access_token>
   ├─ @jwt_required_custom decorator validates token
   ├─ User ID extracted and stored in g.user_id
   └─ Route executes with authenticated context

5. Token Refresh (POST /api/auth/refresh)
   ├─ Client sends refresh token
   ├─ New access token generated
   └─ Extended session without re-login
```

### Role-Based Access Control (RBAC)

Three roles with hierarchical permissions:

```python
# Role Hierarchy (highest to lowest)
ROLES = {
    'admin': {
        'permissions': ['read', 'write', 'delete', 'manage_users'],
        'description': 'Full tenant administration'
    },
    'user': {
        'permissions': ['read', 'write'],
        'description': 'Create and manage own documents'
    },
    'viewer': {
        'permissions': ['read'],
        'description': 'Read-only access to documents'
    }
}

# Permission checking (backend/app/models/user_tenant_association.py)
def has_permission(self, permission: str) -> bool:
    if self.role == 'admin':
        return True
    elif self.role == 'user':
        return permission in ['read', 'write']
    elif self.role == 'viewer':
        return permission == 'read'
    return False
```

### Authorization Decorators

```python
# backend/app/utils/decorators.py

# 1. JWT Authentication
@jwt_required_custom
def protected_route():
    user_id = g.user_id  # Set by decorator
    # Only authenticated users can access

# 2. Tenant Access Control
@jwt_required_custom
@tenant_access_required(['admin', 'user'])
def upload_document(tenant_id):
    user_id = g.user_id        # From JWT
    tenant_id = g.tenant_id    # Validated by decorator
    role = g.user_role         # User's role in this tenant
    # User must be admin or user in this tenant

# 3. Admin-Only Access
@jwt_required_custom
@tenant_access_required(['admin'])
def delete_tenant(tenant_id):
    # Only tenant admins can delete
```

### Security Implementation

```python
# Password Hashing (backend/app/models/user.py)
import bcrypt

def set_password(self, password: str):
    """Hash password with bcrypt (cost factor 12)"""
    salt = bcrypt.gensalt(rounds=12)
    self.password_hash = bcrypt.hashpw(
        password.encode('utf-8'),
        salt
    ).decode('utf-8')

def check_password(self, password: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(
        password.encode('utf-8'),
        self.password_hash.encode('utf-8')
    )

# JWT Configuration (backend/app/config.py)
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')  # Must be strong random key
JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
JWT_ALGORITHM = 'HS256'
```

### Azure AD Single Sign-On (SSO)

The platform supports **Azure AD / Microsoft Entra ID** SSO for enterprise authentication:

```
┌────────────────────────────────────────────────────────────────┐
│                     Azure AD SSO Flow                           │
└────────────────────────────────────────────────────────────────┘

1. SSO Initiation (GET /api/auth/sso/azure/login/{tenant_id})
   ├─ Check tenant SSO configuration
   ├─ Verify client_secret is configured (REQUIRED)
   ├─ Create state token for CSRF protection
   └─ Redirect to Azure AD authorization endpoint

2. Azure AD Authentication
   ├─ User authenticates in Azure AD
   ├─ Azure AD validates against tenant directory
   ├─ Authorization code returned to callback URL
   └─ State token verified for security

3. Token Exchange (GET /api/auth/sso/azure/callback)
   ├─ Exchange authorization code for tokens using client_secret
   ├─ Validate ID token signature and claims
   ├─ Extract user information (email, name, object ID)
   └─ Create or update user in local database

4. User Provisioning
   ├─ Check if user exists (by email)
   ├─ If new: auto-provision if enabled
   ├─ Map Azure AD groups to roles
   ├─ Create UserAzureIdentity mapping
   └─ Store encrypted Azure tokens

5. JWT Generation
   ├─ Create platform JWT tokens
   ├─ Include tenant_id and auth_method
   └─ Return access + refresh tokens
```

#### SSO Configuration Model

Each tenant can configure Azure AD SSO independently:

```python
# TenantSSOConfig Model
class TenantSSOConfig:
    tenant_id           # One-to-one with Tenant
    provider_type       # 'azure_ad' (extensible)
    provider_tenant_id  # Azure AD tenant ID/domain
    client_id          # Azure app registration ID
    client_secret      # REQUIRED - Azure client secret (confidential mode)
    redirect_uri       # OAuth callback URL
    is_enabled         # Enable/disable SSO
    config_metadata    # JSONB for additional settings:
                      # - app_type: 'confidential' (REQUIRED)
                      # - auto_provisioning settings
                      # - allowed email domains
                      # - group role mappings
```

#### Multi-Tenant Azure Identity

Users can have different Azure identities per tenant:

```python
# UserAzureIdentity Model
class UserAzureIdentity:
    user_id             # Local user ID
    tenant_id           # Tenant context
    azure_tenant_id     # Azure AD tenant
    azure_object_id     # User's object ID in Azure
    azure_upn          # User Principal Name
    encrypted_tokens   # Vault-encrypted OAuth tokens
    token_expires_at   # Access token expiration
    last_sync          # Last attributes sync

    # Unique constraint: (user_id, tenant_id)
    # User can have different Azure IDs per tenant
```

#### Authentication Modes

Tenants can configure three authentication modes:

```python
AUTHENTICATION_MODES = {
    'local': 'Username/password only',
    'sso': 'Azure AD only (no passwords)',
    'both': 'Either method allowed'
}

# Tenant.auth_method determines available options
# SSO-only users have nullable password_hash
```

#### Security - Confidential Application Mode

**CRITICAL: This platform uses Confidential Application mode, NOT Public Client mode**

```python
# OAuth2 Authorization Code Flow with Client Secret (NOT PKCE)

1. Application Type: Confidential (Web Application)
   - Requires client_secret for token exchange
   - Does NOT use PKCE (Proof Key for Code Exchange)
   - PKCE is only for public clients (SPAs, mobile apps)

2. Token Exchange Requirements:
   - Authorization code from Azure AD
   - client_id (Application ID)
   - client_secret (REQUIRED - stored securely in database)
   - redirect_uri (must match Azure AD configuration)

3. Security Features:
   - State token for CSRF protection
   - Client secret encrypted at rest (via Vault Transit)
   - Secure server-to-server communication
   - No secret exposure to client-side code

4. Why Confidential Mode:
   - Backend server can securely store client_secret
   - More secure than PKCE for server-side applications
   - Aligns with enterprise security requirements
   - Allows use of client credentials grant (future)
```

#### Auto-Provisioning

SSO supports automatic user provisioning:

```python
# Auto-provisioning configuration
{
    "enabled": true,
    "default_role": "viewer",
    "sync_attributes_on_login": true,
    "allowed_email_domains": ["@company.com"],
    "allowed_azure_groups": ["All-Employees"],
    "group_role_mapping": {
        "IT-Admins": "admin",
        "Developers": "user",
        "Support": "viewer"
    }
}

# Provisioning flow:
1. User authenticates via Azure AD
2. Check email domain whitelist
3. Verify Azure AD group membership
4. Create user with mapped role
5. Sync profile attributes
```

#### Token Management

Azure tokens are securely stored and managed:

```python
# Token encryption via Vault Transit
1. Access token: Encrypted, short-lived (1 hour)
2. Refresh token: Encrypted, long-lived (90 days)
3. ID token: Encrypted, contains user claims

# Automatic refresh before expiration
if azure_identity.is_access_token_expired():
    new_tokens = azure_service.refresh_access_token()
    azure_identity.save_tokens(new_tokens)
```

#### SSO API Endpoints

```python
# Configuration Management
GET    /api/tenants/{id}/sso/config          # Get SSO configuration
POST   /api/tenants/{id}/sso/config          # Create SSO configuration
PUT    /api/tenants/{id}/sso/config          # Update SSO configuration
DELETE /api/tenants/{id}/sso/config          # Delete SSO configuration
POST   /api/tenants/{id}/sso/config/enable   # Enable SSO
POST   /api/tenants/{id}/sso/config/disable  # Disable SSO
GET    /api/tenants/{id}/sso/config/validate # Validate configuration

# Authentication Flow
GET    /api/auth/sso/azure/login/{tenant_id}       # Initiate login
GET    /api/auth/sso/azure/callback                # OAuth callback
POST   /api/auth/sso/azure/refresh                 # Refresh tokens
POST   /api/auth/sso/azure/logout/{tenant_id}      # SSO logout
GET    /api/auth/sso/azure/user-info              # Get Azure profile
GET    /api/auth/sso/check-availability/{tenant_id} # Check SSO status
```

---

## Redis Cache & Session Store

### Redis Architecture Overview

The platform uses **Redis** as a high-performance cache and session store for:

```
┌────────────────────────────────────────────────────────────────┐
│                      Redis Usage Patterns                        │
└────────────────────────────────────────────────────────────────┘

1. Token Blacklist Storage
   ├─ JWT tokens marked for revocation
   ├─ TTL matches token expiration (24 hours)
   ├─ Key pattern: token_blacklist:{jti}
   └─ Distributed across multiple API instances

2. SSO Session Management
   ├─ PKCE parameters during OAuth flow
   ├─ State tokens for CSRF protection
   ├─ TTL: 10 minutes (OAuth flow timeout)
   ├─ Key pattern: sso_session:{state}
   └─ Automatic cleanup after use

3. API Response Caching (Future)
   ├─ Cache frequently accessed data
   ├─ Reduce database load
   ├─ Key pattern: cache:api:{endpoint}:{params}
   └─ TTL based on data volatility

4. Rate Limiting (Future)
   ├─ Track API requests per user/IP
   ├─ Sliding window algorithm
   ├─ Key pattern: rate_limit:{user_id}:{window}
   └─ TTL: Rate limit window duration
```

### Redis Integration

#### RedisManager Class

The platform provides a centralized Redis manager with automatic fallback:

```python
# backend/app/extensions.py

class RedisManager:
    """Manager for Redis connections with graceful fallback"""

    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self.enabled: bool = False

    def init_app(self, app):
        """Initialize Redis with connection pooling"""
        redis_url = app.config.get('REDIS_URL')

        if redis_url:
            self.client = redis.from_url(
                redis_url,
                max_connections=20,
                decode_responses=True,
                health_check_interval=30
            )
            # Test connection
            self.client.ping()
            self.enabled = True
```

#### Token Blacklist Implementation

JWT token revocation using Redis:

```python
# backend/app/services/auth_service.py

# Add token to blacklist
def _add_to_blacklist(jti: str) -> bool:
    redis_client = redis_manager.get_client()
    if redis_client:
        # Store in Redis with TTL
        expire_time = 86400  # 24 hours
        redis_key = f"token_blacklist:{jti}"
        redis_client.setex(redis_key, expire_time, "1")
    else:
        # Fallback to in-memory set
        TOKEN_BLACKLIST.add(jti)

# Check if token is blacklisted
def _is_token_blacklisted(jti: str) -> bool:
    redis_client = redis_manager.get_client()
    if redis_client:
        redis_key = f"token_blacklist:{jti}"
        return redis_client.exists(redis_key) > 0
    else:
        return jti in TOKEN_BLACKLIST
```

#### SSO Session Storage

Secure PKCE parameter storage for OAuth flows:

```python
# backend/app/services/azure_ad_service.py

def store_pkce_in_session(code_verifier: str, state: str):
    redis_client = redis_manager.get_client()

    if redis_client:
        # Store in Redis with 10-minute TTL
        session_data = {
            'code_verifier': code_verifier,
            'state': state,
            'timestamp': datetime.utcnow().isoformat()
        }

        redis_key = f"sso_session:{state}"
        redis_client.setex(
            redis_key,
            600,  # 10 minutes
            json.dumps(session_data)
        )
    else:
        # Fallback to Flask session
        session['oauth_state'] = state
        session['oauth_code_verifier'] = code_verifier
```

### Redis Configuration

#### Docker Deployment

```yaml
# docker-compose.yml

redis:
  image: redis:7-alpine
  container_name: saas-redis
  restart: unless-stopped
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  networks:
    - saas-network
  command: >
    redis-server
    --appendonly yes
    --maxmemory 256mb
    --maxmemory-policy allkeys-lru
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5
```

#### Application Configuration

```python
# backend/app/config.py

# Redis Configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
REDIS_MAX_CONNECTIONS = int(os.environ.get('REDIS_MAX_CONNECTIONS', 20))
REDIS_DECODE_RESPONSES = True
REDIS_TOKEN_BLACKLIST_EXPIRE = 86400  # 24 hours
REDIS_SESSION_EXPIRE = 600  # 10 minutes
```

### High Availability Considerations

#### Redis Persistence

Two persistence options configured:

1. **AOF (Append-Only File)**: Every write operation logged
   - Configured with `--appendonly yes`
   - Better durability, slight performance impact

2. **Memory Management**: LRU eviction policy
   - `--maxmemory 256mb`: Memory limit
   - `--maxmemory-policy allkeys-lru`: Least Recently Used eviction

#### Graceful Degradation

The platform operates without Redis, with reduced functionality:

```
With Redis:
✓ Token blacklist shared across instances
✓ SSO sessions persist across requests
✓ Scalable to multiple API instances
✓ Tokens survive API restarts

Without Redis (Fallback):
✗ Token blacklist in-memory only
✗ SSO sessions in Flask session
✗ Single instance limitation
✗ Tokens lost on restart
```

### Redis Monitoring

Key metrics to monitor:

```bash
# Check Redis status
docker exec saas-redis redis-cli INFO stats

# Monitor memory usage
docker exec saas-redis redis-cli INFO memory

# View all keys (development only)
docker exec saas-redis redis-cli KEYS "*"

# Check specific key TTL
docker exec saas-redis redis-cli TTL "token_blacklist:abc123"

# Monitor connections
docker exec saas-redis redis-cli CLIENT LIST
```

### Future Redis Use Cases

Planned Redis implementations:

1. **API Response Caching**
   - Cache expensive queries
   - Reduce database load
   - Invalidation strategies

2. **Rate Limiting**
   - Per-user/IP request tracking
   - Sliding window algorithm
   - DDoS protection

3. **Session Storage**
   - User session data
   - Shopping cart persistence
   - Activity tracking

4. **Real-time Features**
   - Pub/Sub for notifications
   - WebSocket state management
   - Live updates

5. **Distributed Locks**
   - Prevent concurrent operations
   - Job queue coordination
   - Resource locking

---

## Celery Task Queue Architecture

### Celery Overview

The platform uses **Celery** for asynchronous task processing, complementing Kafka for different use cases:

```
┌────────────────────────────────────────────────────────────────┐
│                    Task Processing Architecture                  │
└────────────────────────────────────────────────────────────────┘

Kafka (Event Streaming):
├─ Real-time event processing
├─ High-throughput message streaming
├─ Event sourcing and audit logs
└─ Fire-and-forget notifications

Celery (Task Queue):
├─ Scheduled periodic tasks
├─ Long-running background jobs
├─ Tasks requiring retry logic
├─ SSO token refresh automation
└─ System maintenance operations
```

### Celery Components

#### Task Queues

The platform uses multiple Celery queues for task organization:

```python
# Queue Configuration
CELERY_TASK_ROUTES = {
    'app.tasks.sso_tasks.*': {'queue': 'sso'},
    'app.tasks.maintenance_tasks.*': {'queue': 'maintenance'},
    'app.tasks.email_tasks.*': {'queue': 'email'},
}

# Queue Priorities:
# - sso: High priority (token refresh)
# - email: Medium priority (notifications)
# - maintenance: Low priority (cleanup)
```

#### Workers

Three types of Celery workers handle different workloads:

1. **SSO Worker** (`celery-worker-sso`):
   - Processes SSO token refresh tasks
   - Handles Azure AD token management
   - Manages Vault key rotation

2. **Beat Scheduler** (`celery-beat`):
   - Schedules periodic tasks
   - Manages cron-like job execution
   - Coordinates task timing

3. **Flower Monitor** (`flower`):
   - Web-based monitoring dashboard
   - Real-time task tracking
   - Performance metrics

### SSO Token Refresh Strategy

#### Hybrid Refresh Implementation

The platform implements a hybrid token refresh strategy using Celery:

```python
# Scheduled Tasks (via Celery Beat)

# Every 15 minutes - Refresh expiring tokens
@celery_app.task
def refresh_expiring_tokens():
    """
    Proactively refresh tokens expiring in next 30 minutes
    """
    threshold = datetime.utcnow() + timedelta(minutes=30)
    expiring_identities = UserAzureIdentity.query.filter(
        UserAzureIdentity.token_expires_at < threshold
    )
    # Refresh logic...

# Daily at 2 AM - Cleanup expired tokens
@celery_app.task
def cleanup_expired_tokens():
    """
    Remove tokens that cannot be refreshed
    """
    expired_identities = UserAzureIdentity.query.filter(
        UserAzureIdentity.refresh_token_expires_at < datetime.utcnow()
    )
    # Cleanup logic...

# Monthly - Rotate encryption keys
@celery_app.task
def rotate_encryption_keys():
    """
    Rotate Vault Transit keys for enhanced security
    """
    # Key rotation and token re-wrapping...
```

### Celery Configuration

#### Broker and Backend

```yaml
# Redis Database Allocation

DB 0: Application cache
DB 1: Session storage
DB 2: SSO PKCE flows
DB 3: Celery broker (task queue)
DB 4: Celery results backend
DB 5: Rate limiting
```

#### Docker Services

```yaml
# docker-compose.yml

celery-worker-sso:
  command: celery -A app.celery_app worker -Q sso,maintenance
  environment:
    CELERY_BROKER_URL: redis://redis:6379/3
    CELERY_RESULT_BACKEND: redis://redis:6379/4

celery-beat:
  command: celery -A app.celery_app beat
  volumes:
    - celery_beat_schedule:/var/lib/celery

flower:
  command: celery -A app.celery_app flower
  ports:
    - "5555:5555"  # Monitoring dashboard
```

### Task Scheduling

#### Beat Schedule Configuration

```python
CELERYBEAT_SCHEDULE = {
    'refresh-expiring-tokens': {
        'task': 'app.tasks.sso_tasks.refresh_expiring_tokens',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {'queue': 'sso', 'priority': 7}
    },

    'cleanup-expired-tokens': {
        'task': 'app.tasks.sso_tasks.cleanup_expired_tokens',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
        'options': {'queue': 'maintenance', 'priority': 3}
    },

    'rotate-vault-keys': {
        'task': 'app.tasks.sso_tasks.rotate_encryption_keys',
        'schedule': crontab(day_of_month=1, hour=3),  # Monthly
        'options': {'queue': 'maintenance', 'priority': 2}
    },

    'health-check': {
        'task': 'app.tasks.maintenance_tasks.health_check',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
        'options': {'queue': 'maintenance', 'priority': 1}
    }
}
```

### Error Handling and Retries

#### Exponential Backoff

```python
@celery_app.task(bind=True, max_retries=3)
def refresh_user_token(self, user_id, tenant_id):
    try:
        # Token refresh logic...
    except NetworkError as e:
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
```

#### Dead Letter Queue

Failed tasks after max retries are moved to a dead letter queue for investigation:

```python
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
```

### Monitoring and Metrics

#### Flower Dashboard

Access monitoring at: `http://localhost:5555`

Features:
- Real-time task monitoring
- Worker status and pool stats
- Task execution history
- Performance graphs
- Failed task inspection

#### Task Metrics

```python
# Track task performance
@celery_app.task
def refresh_expiring_tokens():
    results = {
        'task_id': current_task.request.id,
        'timestamp': datetime.utcnow().isoformat(),
        'success': 0,
        'failed': 0,
        'skipped': 0
    }
    # Process tokens...
    return results
```

### Kafka vs Celery Usage

#### When to Use Kafka

- **Event streaming**: Real-time data processing
- **High throughput**: Millions of messages per second
- **Event sourcing**: Maintaining event history
- **Pub/Sub patterns**: Multiple consumers for same event

#### When to Use Celery

- **Scheduled tasks**: Cron-like periodic jobs
- **Long-running tasks**: Complex processing with progress tracking
- **Retry logic**: Tasks needing sophisticated retry strategies
- **Task routing**: Different queues for different priorities

### Production Considerations

1. **Worker Scaling**
   ```bash
   # Scale SSO workers during peak hours
   docker-compose up -d --scale celery-worker-sso=3
   ```

2. **Resource Limits**
   ```yaml
   celery-worker-sso:
     deploy:
       resources:
         limits:
           cpus: '1.0'
           memory: 512M
   ```

3. **Monitoring Alerts**
   - Queue length thresholds
   - Task failure rates
   - Worker memory usage
   - Redis connection pool

---

## File Storage Architecture

### S3-Based Storage with MD5 Deduplication

The platform uses AWS S3 for file storage with intelligent deduplication:

```
┌────────────────────────────────────────────────────────────────┐
│                    File Upload Flow                             │
└────────────────────────────────────────────────────────────────┘

1. Client uploads file to POST /api/tenants/{id}/documents
   ↓
2. Calculate MD5 hash of file content
   ↓
3. Check for duplicate in tenant database
   ├─ Query: SELECT * FROM files WHERE md5_hash = ?
   └─ If found → Skip S3 upload, reuse existing file
   ↓
4. If new file:
   ├─ Generate sharded S3 path
   ├─ Upload to S3 bucket
   ├─ Create File record (md5_hash, s3_path, file_size)
   └─ Create Document record (filename, mime_type, file_id, user_id)
   ↓
5. Return document metadata to client

Deduplication Benefits:
- 2 users upload identical file → 1 copy in S3
- Saves storage costs
- Faster uploads (if duplicate found)
- Maintains user-specific document metadata
```

### S3 Path Sharding Strategy

Files are organized using a sharded directory structure for performance:

```
S3 Bucket Structure:
s3://your-bucket/
└── tenants/
    ├── {tenant_id}/
    │   └── files/
    │       ├── ab/                    ← First 2 chars of MD5
    │       │   ├── c1/                ← Next 2 chars of MD5
    │       │   │   └── abc123..._{uuid}_{filename}
    │       │   └── cd/
    │       ├── de/
    │       └── ...

Example:
- MD5: abc123def456789abcdef0123456789
- Tenant ID: 550e8400-e29b-41d4-a716-446655440000
- Filename: report.pdf

S3 Path:
s3://bucket/tenants/550e8400-e29b-41d4-a716-446655440000/files/ab/c1/abc123def456789abcdef0123456789_f8e7d6c5-b4a3-9281-7060-504030201000_report.pdf

Benefits:
- Prevents "too many files in one directory" issues
- Enables efficient S3 prefix searches
- Distributes load across S3 partitions
```

### File vs. Document Models

The architecture separates **physical files** from **user documents**:

```
┌─────────────────────────────────────────────────────────────────┐
│  File Model (Physical Storage)                                  │
│  - One record per unique file (by MD5)                          │
│  - Stores: md5_hash, s3_path, file_size                         │
│  - Shared across multiple documents                             │
└─────────────────────────────────────────────────────────────────┘
                          ▲
                          │ Many-to-One
                          │
┌─────────────────────────┴───────────────────────────────────────┐
│  Document Model (User Metadata)                                 │
│  - One record per user upload                                   │
│  - Stores: filename, mime_type, file_id, user_id                │
│  - User can rename document without affecting file              │
└─────────────────────────────────────────────────────────────────┘

Example:
User A uploads "Q1_Report.pdf" (MD5: abc123...)
User B uploads "Financial_Report.pdf" (same content, MD5: abc123...)

Database:
files table:
  id: file-uuid-1
  md5_hash: abc123...
  s3_path: s3://bucket/tenants/.../abc123...
  file_size: 1048576

documents table:
  id: doc-uuid-1
  filename: Q1_Report.pdf
  file_id: file-uuid-1
  user_id: user-a-uuid

  id: doc-uuid-2
  filename: Financial_Report.pdf
  file_id: file-uuid-1  ← Same file!
  user_id: user-b-uuid

Result: 1 file in S3, 2 document records
```

### S3 Client Implementation

```python
# backend/app/utils/s3_client.py

class S3Client:
    def __init__(self):
        self.client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
        self.bucket = os.getenv('S3_BUCKET_NAME')

    def upload_file(self, file_obj, s3_path: str) -> bool:
        """Upload file to S3"""
        self.client.upload_fileobj(file_obj, self.bucket, s3_path)
        return True

    def generate_presigned_url(self, s3_path: str, expiration: int = 3600):
        """Generate temporary download URL"""
        return self.client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': s3_path},
            ExpiresIn=expiration
        )

    def delete_file(self, s3_path: str) -> bool:
        """Delete file from S3"""
        self.client.delete_object(Bucket=self.bucket, Key=s3_path)
        return True
```

### Orphaned File Management

Files without any document references are considered orphaned:

```python
# backend/app/models/file.py

def is_orphaned(self) -> bool:
    """Check if file has no document references"""
    return self.documents.count() == 0

@classmethod
def find_orphaned_files(cls, min_age_hours: int = 24):
    """Find files orphaned for at least N hours"""
    cutoff = datetime.utcnow() - timedelta(hours=min_age_hours)
    return cls.query.filter(
        ~cls.documents.any(),
        cls.created_at < cutoff
    ).all()

# Cleanup job (run periodically)
orphaned = File.find_orphaned_files(min_age_hours=24)
for file in orphaned:
    file.delete_from_s3()
    db.session.delete(file)
db.session.commit()
```

---

## Kafka Message Processing

### Architecture Overview

Kafka enables asynchronous processing of document-related tasks:

```
┌────────────────────────────────────────────────────────────────┐
│                   Kafka Message Flow                            │
└────────────────────────────────────────────────────────────────┘

1. API receives document upload
   ↓
2. API saves document to database
   ↓
3. Producer sends message to Kafka topic
   {
     "event_type": "document.uploaded",
     "tenant_id": "...",
     "document_id": "...",
     "user_id": "...",
     "filename": "...",
     "timestamp": "2024-01-15T10:30:00Z"
   }
   ↓
4. Kafka stores message in topic partition
   ↓
5. Consumer worker polls for messages
   ↓
6. Consumer processes message
   ├─ Send notification email
   ├─ Generate thumbnail
   ├─ Extract text for search indexing
   ├─ Run virus scan
   └─ Update document metadata
   ↓
7. Consumer commits offset (message processed)
```

### Kafka Configuration

```python
# Kafka Topics
DOCUMENT_EVENTS_TOPIC = 'document-events'
TENANT_EVENTS_TOPIC = 'tenant-events'
USER_EVENTS_TOPIC = 'user-events'

# Producer Configuration (backend/app/worker/producer.py)
KAFKA_BROKERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
PRODUCER_CONFIG = {
    'bootstrap_servers': KAFKA_BROKERS,
    'value_serializer': lambda v: json.dumps(v).encode('utf-8'),
    'acks': 'all',  # Wait for all replicas
    'retries': 3,
    'compression_type': 'gzip'
}

# Consumer Configuration (backend/app/worker/consumer.py)
CONSUMER_CONFIG = {
    'bootstrap_servers': KAFKA_BROKERS,
    'group_id': 'document-processor-group',
    'auto_offset_reset': 'earliest',
    'enable_auto_commit': False,  # Manual commit after processing
    'value_deserializer': lambda m: json.loads(m.decode('utf-8'))
}
```

### Producer Implementation

```python
# backend/app/worker/producer.py

class KafkaProducerService:
    def __init__(self):
        self.producer = AIOKafkaProducer(**PRODUCER_CONFIG)
        self._started = False

    async def start(self):
        if not self._started:
            await self.producer.start()
            self._started = True

    async def send_document_event(self, event_type: str, document_data: dict):
        """Send document event to Kafka"""
        message = {
            'event_type': event_type,
            'tenant_id': document_data['tenant_id'],
            'document_id': document_data['document_id'],
            'user_id': document_data['user_id'],
            'filename': document_data['filename'],
            'mime_type': document_data.get('mime_type'),
            'timestamp': datetime.utcnow().isoformat()
        }

        await self.producer.send(
            'document-events',
            value=message,
            key=document_data['tenant_id'].encode('utf-8')  # Partition by tenant
        )

        logger.info(f"Sent event: {event_type} for document {document_data['document_id']}")

# Usage in services (backend/app/services/document_service.py)
async def create_document(...):
    # 1. Save to database
    document = Document(...)
    db.session.add(document)
    db.session.commit()

    # 2. Send async event
    await kafka_producer.send_document_event('document.uploaded', {
        'document_id': str(document.id),
        'tenant_id': str(tenant_id),
        ...
    })
```

### Consumer Implementation

```python
# backend/app/worker/consumer.py

class KafkaConsumerWorker:
    def __init__(self):
        self.consumer = AIOKafkaConsumer(
            'document-events',
            **CONSUMER_CONFIG
        )

    async def start(self):
        await self.consumer.start()
        logger.info("Kafka consumer started")

        try:
            async for message in self.consumer:
                await self.process_message(message)
        finally:
            await self.consumer.stop()

    async def process_message(self, message):
        """Process single Kafka message"""
        try:
            event = message.value
            event_type = event['event_type']

            if event_type == 'document.uploaded':
                await self.handle_document_uploaded(event)
            elif event_type == 'document.deleted':
                await self.handle_document_deleted(event)

            # Commit offset after successful processing
            await self.consumer.commit()

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Don't commit - message will be reprocessed

    async def handle_document_uploaded(self, event):
        """Process document upload event"""
        document_id = event['document_id']

        # Example processing tasks:
        # 1. Send notification
        await self.send_notification(event['user_id'], f"Document {event['filename']} uploaded")

        # 2. Generate thumbnail (if image)
        if event['mime_type'].startswith('image/'):
            await self.generate_thumbnail(document_id)

        # 3. Extract text (if PDF)
        if event['mime_type'] == 'application/pdf':
            await self.extract_text(document_id)

        logger.info(f"Processed document upload: {document_id}")
```

### Message Partitioning Strategy

Messages are partitioned by `tenant_id` to ensure:
- All events for a tenant go to same partition
- Ordered processing per tenant
- Parallel processing across tenants

```python
# Partition key = tenant_id
await producer.send(
    'document-events',
    value=message,
    key=tenant_id.encode('utf-8')  # Ensures same partition
)

# Example with 3 partitions:
# Tenant A (key: tenant-a) → Partition 0
# Tenant B (key: tenant-b) → Partition 1
# Tenant C (key: tenant-c) → Partition 2
# Tenant D (key: tenant-d) → Partition 0
```

---

## API Design

### RESTful Principles

The API follows REST best practices:

```
Resource-Based URLs:
✓ /api/users              (collection)
✓ /api/users/{id}         (specific resource)
✓ /api/tenants/{id}/documents    (nested resources)

✗ /api/getUser            (avoid RPC-style)
✗ /api/createDocument     (avoid action names)

HTTP Methods:
GET    - Retrieve resources
POST   - Create new resources
PUT    - Replace entire resource
PATCH  - Partial update
DELETE - Remove resource

Status Codes:
200 OK              - Successful GET, PATCH, DELETE
201 Created         - Successful POST
204 No Content      - Successful DELETE (no body)
400 Bad Request     - Validation error
401 Unauthorized    - Missing/invalid token
403 Forbidden       - Insufficient permissions
404 Not Found       - Resource doesn't exist
409 Conflict        - Duplicate resource
500 Internal Error  - Server error
```

### API Response Format

All responses follow a standardized format:

```json
// Success Response
{
  "success": true,
  "message": "Operation successful",
  "data": {
    "id": "uuid-here",
    "name": "Example"
  }
}

// Error Response
{
  "success": false,
  "error": "validation_error",
  "message": "Invalid input data",
  "details": {
    "email": "Email is required",
    "password": "Password must be at least 8 characters"
  }
}

// List Response
{
  "success": true,
  "message": "Documents retrieved",
  "data": {
    "items": [...],
    "total": 42,
    "page": 1,
    "per_page": 20
  }
}
```

### API Endpoints Overview

```
Authentication:
POST   /api/auth/register          - Register new user
POST   /api/auth/login             - Login and get tokens
POST   /api/auth/refresh           - Refresh access token
POST   /api/auth/logout            - Invalidate refresh token

Users:
GET    /api/users/me               - Get current user profile
PATCH  /api/users/me               - Update profile
GET    /api/users/me/tenants       - List user's tenants

Tenants:
POST   /api/tenants                - Create new tenant
GET    /api/tenants                - List user's tenants
GET    /api/tenants/{id}           - Get tenant details
PATCH  /api/tenants/{id}           - Update tenant
DELETE /api/tenants/{id}           - Delete tenant (admin only)
GET    /api/tenants/{id}/users     - List tenant users
POST   /api/tenants/{id}/users     - Add user to tenant
PATCH  /api/tenants/{id}/users/{user_id}  - Update user role
DELETE /api/tenants/{id}/users/{user_id}  - Remove user

Documents:
POST   /api/tenants/{id}/documents           - Upload document
GET    /api/tenants/{id}/documents           - List documents
GET    /api/tenants/{id}/documents/{doc_id}  - Get document
PATCH  /api/tenants/{id}/documents/{doc_id}  - Update metadata
DELETE /api/tenants/{id}/documents/{doc_id}  - Delete document
GET    /api/tenants/{id}/documents/{doc_id}/download  - Get download URL

Files:
GET    /api/tenants/{id}/files               - List files
GET    /api/tenants/{id}/files/{file_id}     - Get file info
DELETE /api/tenants/{id}/files/{file_id}     - Delete file (if no docs)
GET    /api/tenants/{id}/files/orphaned      - List orphaned files
DELETE /api/tenants/{id}/files/orphaned      - Clean up orphaned files

Health & Demo:
GET    /api/health                 - Health check
POST   /api/kafka/demo/produce     - Demo Kafka producer
GET    /api/kafka/demo/status      - Demo Kafka status
```

### Request Validation

Input validation using Marshmallow schemas:

```python
# Example: Document upload validation

# Schema definition (backend/app/schemas/document_schema.py)
class DocumentUploadSchema(Schema):
    filename = fields.String(required=True, validate=Length(min=1, max=255))
    mime_type = fields.String(required=True, validate=Regexp(r'^\w+/\w+$'))
    file_size = fields.Integer(validate=Range(min=1, max=100*1024*1024))  # Max 100MB

# Route usage (backend/app/routes/documents.py)
@documents_bp.route('/tenants/<tenant_id>/documents', methods=['POST'])
@jwt_required_custom
@tenant_access_required(['admin', 'user'])
def upload_document(tenant_id):
    # Validate request data
    try:
        data = document_upload_schema.load(request.get_json())
    except ValidationError as e:
        return bad_request("Validation failed", details=e.messages)

    # Process upload
    document, error = DocumentService.create_document(tenant_id, g.user_id, data)
    ...
```

### Pagination

List endpoints support pagination:

```python
# Query parameters
GET /api/tenants/{id}/documents?page=2&per_page=20&sort=created_at&order=desc

# Response
{
  "success": true,
  "data": {
    "items": [...],
    "total": 150,
    "page": 2,
    "per_page": 20,
    "total_pages": 8,
    "has_next": true,
    "has_prev": true
  }
}

# Implementation (backend/app/services/document_service.py)
@staticmethod
def list_documents(tenant_id, page=1, per_page=20, sort='created_at', order='desc'):
    query = Document.query

    # Sorting
    if order == 'desc':
        query = query.order_by(getattr(Document, sort).desc())
    else:
        query = query.order_by(getattr(Document, sort).asc())

    # Pagination
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        'items': [doc.to_dict() for doc in paginated.items],
        'total': paginated.total,
        'page': page,
        'per_page': per_page,
        'total_pages': paginated.pages,
        'has_next': paginated.has_next,
        'has_prev': paginated.has_prev
    }
```

---

## Security Considerations

### Authentication Security

```
1. Password Storage:
   - Bcrypt hashing with cost factor 12
   - Salting automatically handled by bcrypt
   - Passwords never stored in plain text
   - Password hashes never returned in API responses

2. JWT Token Security:
   - HS256 signing algorithm
   - Strong secret key (64+ character random string)
   - Short-lived access tokens (15 minutes)
   - Refresh tokens with longer expiry (30 days)
   - Token blacklisting on logout (future enhancement)

3. Password Validation:
   - Minimum 8 characters
   - Must contain at least one letter
   - Must contain at least one number
   - Validated at schema level and model level
```

### Authorization Security

```
1. Multi-Tenancy Isolation:
   - Database-per-tenant ensures complete data isolation
   - Cross-tenant access prevented at decorator level
   - All tenant operations verify user membership
   - SQL injection protected by SQLAlchemy ORM

2. Role-Based Access Control:
   - Admin: Full tenant control
   - User: Create and manage own documents
   - Viewer: Read-only access
   - Role checked on every protected route

3. Access Verification:
   @tenant_access_required decorator ensures:
   - User is authenticated (valid JWT)
   - User has association with tenant
   - User's role meets required level
   - Sets g.tenant_id, g.user_id, g.user_role
```

### Data Security

```
1. Input Validation:
   - All inputs validated with Marshmallow schemas
   - SQL injection protected by ORM parameterization
   - XSS protection via JSON responses (not HTML)
   - File upload validation (size, MIME type)

2. Data Transmission:
   - HTTPS enforced in production (load balancer)
   - Secure headers configured
   - CORS policy enforced

3. Data at Rest:
   - Database encryption (PostgreSQL transparent encryption)
   - S3 bucket encryption (AES-256)
   - Secrets stored in environment variables (not code)

4. Sensitive Data Handling:
   - Password hashes excluded from API responses
   - JWT secrets never exposed
   - AWS credentials in environment only
   - Database credentials in environment only
```

### S3 Security

```
1. Bucket Access:
   - Private bucket (no public access)
   - IAM role-based access for API servers
   - Pre-signed URLs for temporary download access
   - URL expiration (default 1 hour)

2. File Isolation:
   - Tenant-specific S3 prefixes
   - Path validation prevents directory traversal
   - No direct S3 access from clients

3. Upload Security:
   - File size limits enforced
   - MIME type validation
   - Virus scanning (future enhancement via Kafka consumer)
```

### Kafka Security

```
1. Message Security:
   - Kafka within private network (no external access)
   - Messages contain IDs only (not sensitive data)
   - Consumer group isolation

2. Error Handling:
   - Failed messages logged for investigation
   - No auto-commit (manual commit after processing)
   - Dead letter queue (future enhancement)
```

### Environment Security with HashiCorp Vault

The platform integrates **HashiCorp Vault** for centralized secrets management, providing secure storage and access control for sensitive configuration data.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Vault Secrets Architecture                    │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐         ┌──────────────────┐
│  HashiCorp Vault │         │   Application    │
│                  │         │                  │
│  KV Secrets:     │◄────────│  vault-wrapper.sh│
│  - JWT_SECRET    │  HTTPS  │  loads secrets   │
│  - DB_PASSWORD   │         │  at startup      │
│  - AWS_KEYS      │         │                  │
│  - API_TOKENS    │         │  Flask API       │
└──────────────────┘         │  Workers         │
                             └──────────────────┘

Benefits:
- Centralized secrets management
- Audit logging of all secret access
- Dynamic secret rotation capability
- Encryption at rest and in transit
- Fine-grained access control policies
```

#### Vault Storage Backend Configuration

The platform uses HashiCorp Vault with **persistent file storage** for development and production, ensuring secrets survive container restarts.

```hcl
# vault/config/vault.hcl - Configuration de Vault

# Interface d'écoute HTTP
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1  # TLS géré par le load balancer en production
}

# Backend de stockage persistant sur disque
storage "file" {
  path = "/vault/data"
}

# Configuration API
api_addr = "http://0.0.0.0:8200"

# Interface utilisateur Web activée
ui = true

# Désactiver mlock pour Docker (géré par IPC_LOCK capability)
disable_mlock = true

# Niveau de logs
log_level = "info"
```

**Bénéfices du stockage File:**
- Persistance des secrets entre redémarrages de conteneurs
- Simplicité de déploiement (pas de dépendance externe)
- Facilite la sauvegarde (simple copie du répertoire `/vault/data`)
- Convient pour développement et petite production

**Note:** En production à grande échelle, envisager Consul ou Integrated Storage (Raft) pour haute disponibilité.

#### Vault Initialization and Unseal Process

Vault requires initialization and unsealing before use. The platform automates this with dedicated containers:

**1. Initialization Process** ([vault/scripts/unseal-vault.sh](vault/scripts/unseal-vault.sh)):
```bash
# Automatically initializes Vault with:
# - 5 unseal keys (Shamir's Secret Sharing)
# - Threshold of 3 keys required to unseal
# - Saves unseal keys to /vault/data/unseal-keys.json
# - Saves root token to /vault/data/root-token.txt
# - Automatically unseals Vault after initialization

vault operator init -key-shares=5 -key-threshold=3 -format=json
```

**2. Auto-Unseal on Restart** ([vault/scripts/unseal-vault.sh](vault/scripts/unseal-vault.sh)):
```bash
# On container restart, automatically:
# - Detects if Vault is sealed
# - Reads unseal keys from persisted file
# - Applies 3 of 5 keys to unseal Vault
# - Makes Vault ready for application use

vault operator unseal $UNSEAL_KEY_1
vault operator unseal $UNSEAL_KEY_2
vault operator unseal $UNSEAL_KEY_3
```

**3. Secrets Injection** ([vault/scripts/init-vault.sh](vault/scripts/init-vault.sh)):
```bash
# Injects application secrets into Vault from environment-specific files
# Source: vault/init-data/{environment}.env (docker, dev, prod)

# Database secrets
vault kv put secret/saas-project/${VAULT_ENV}/database \
  main_url="$DATABASE_URL" \
  tenant_url_template="$TENANT_DATABASE_URL_TEMPLATE"

# JWT secrets
vault kv put secret/saas-project/${VAULT_ENV}/jwt \
  secret_key="$JWT_SECRET_KEY" \
  access_token_expires="900"

# S3 secrets
vault kv put secret/saas-project/${VAULT_ENV}/s3 \
  endpoint_url="$S3_ENDPOINT_URL" \
  access_key_id="$S3_ACCESS_KEY_ID" \
  secret_access_key="$S3_SECRET_ACCESS_KEY" \
  bucket_name="saas-documents" \
  region="us-east-1"
```

#### AppRole Authentication Method

The platform uses **AppRole** authentication (recommended for applications) instead of root tokens:

```bash
# 1. Enable AppRole authentication
vault auth enable approle

# 2. Create access policy for the application
vault policy write saas-app-policy-${VAULT_ENV} - <<EOF
# Read access to application secrets
path "secret/data/saas-project/${VAULT_ENV}/*" {
  capabilities = ["read"]
}

# List access to secret metadata
path "secret/metadata/saas-project/${VAULT_ENV}/*" {
  capabilities = ["list", "read"]
}

# Token renewal capability
path "auth/token/renew-self" {
  capabilities = ["update"]
}

# Token lookup capability
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF

# 3. Create AppRole with policy
vault write auth/approle/role/saas-app-role-${VAULT_ENV} \
  token_policies="saas-app-policy-${VAULT_ENV}" \
  token_ttl=1h \
  token_max_ttl=4h \
  secret_id_ttl=0 \
  secret_id_num_uses=0

# 4. Generate credentials for application
ROLE_ID=$(vault read -field=role_id auth/approle/role/saas-app-role-${VAULT_ENV}/role-id)
SECRET_ID=$(vault write -field=secret_id -f auth/approle/role/saas-app-role-${VAULT_ENV}/secret-id)
```

**AppRole Benefits:**
- No need to distribute root token
- Scoped permissions (least privilege)
- Audit trail per role
- Renewable tokens with TTL
- Separate credentials per environment

#### Docker Integration with Vault

```yaml
# docker-compose.yml - Complete Vault setup with auto-initialization

services:
  # 1. Main Vault Server with persistent storage
  vault:
    image: hashicorp/vault:1.15
    container_name: saas-vault
    cap_add:
      - IPC_LOCK  # Prevent memory swapping for secrets
    environment:
      VAULT_ADDR: "http://0.0.0.0:8200"
      VAULT_API_ADDR: "http://0.0.0.0:8200"
    ports:
      - "8201:8200"  # Port 8201 on host (8200 often used by OneDrive on macOS)
    volumes:
      - ./vault/config:/vault/config:ro      # Vault configuration
      - ./vault/data:/vault/data             # Persistent storage for secrets
      - ./vault/logs:/vault/logs             # Audit logs
    command: sh -c "chown -R vault:vault /vault/data && exec su-exec vault vault server -config=/vault/config"
    healthcheck:
      test: ["CMD", "vault", "status", "-format=json"]
      interval: 10s
      timeout: 5s
      retries: 5

  # 2. Auto-unseal container (runs once on startup)
  vault-unseal:
    image: hashicorp/vault:1.15
    container_name: saas-vault-unseal
    depends_on:
      vault:
        condition: service_healthy
    environment:
      VAULT_ADDR: "http://vault:8200"
    volumes:
      - ./vault/scripts:/scripts:ro
      - ./vault/data:/vault/data  # Access to unseal keys
    command: /scripts/unseal-vault.sh
    restart: "no"  # Run once only

  # 3. Secrets initialization container (runs once after unseal)
  vault-init:
    image: hashicorp/vault:1.15
    container_name: saas-vault-init
    depends_on:
      vault-unseal:
        condition: service_completed_successfully
    environment:
      VAULT_ADDR: "http://vault:8200"
      VAULT_ENV: "${VAULT_ENV:-docker}"  # Environment: dev, docker, prod
    volumes:
      - ./vault/scripts:/scripts:ro
      - ./vault/init-data:/init-data:ro   # Source .env files with secrets
      - ./vault/data:/vault/data          # Access to root token
      - ./.env.vault:/.env.vault:rw       # Output AppRole credentials
    command: /scripts/init-vault.sh
    restart: "no"  # Run once only

  # 4. Application API (uses Vault)
  api:
    depends_on:
      vault:
        condition: service_healthy
      vault-init:
        condition: service_completed_successfully
    environment:
      USE_VAULT: "true"
      VAULT_ENVIRONMENT: "docker"
    volumes:
      - ./.env.vault:/.env.vault:ro  # AppRole credentials (read-only)
      - ./backend/flask-wrapper.sh:/app/flask-wrapper.sh  # Loads Vault vars
```

**Container Orchestration Flow:**
```
1. vault          → Starts, healthcheck waits for ready
2. vault-unseal   → Waits for vault healthy, then unseals
3. vault-init     → Waits for unseal complete, injects secrets & creates AppRole
4. api/worker     → Waits for init complete, connects with AppRole credentials
```

#### Secret Storage Structure in Vault

```bash
# Vault KV secrets path structure
secret/
├── saas-platform/           # Main application secrets
│   ├── jwt_secret           # JWT signing key
│   ├── db_password          # PostgreSQL password
│   ├── db_user              # PostgreSQL username
│   ├── aws_access_key       # AWS access key ID
│   ├── aws_secret          # AWS secret access key
│   └── kafka_credentials    # Kafka authentication
├── saas-platform/tenants/   # Per-tenant secrets (if needed)
│   └── {tenant_id}/
│       └── encryption_key   # Tenant-specific encryption
└── saas-platform/api-keys/  # Third-party API keys
    ├── sendgrid_key
    ├── stripe_key
    └── oauth_secrets
```

#### Vault Commands for Secret Management

**Essential Vault CLI Commands:**

```bash
# 1. Check Vault status
docker-compose exec vault vault status

# 2. List all secrets (requires authentication)
docker-compose exec vault vault kv list secret/saas-project/

# 3. Read secrets for a specific environment
docker-compose exec vault vault kv get secret/saas-project/docker/database
docker-compose exec vault vault kv get secret/saas-project/docker/jwt
docker-compose exec vault vault kv get secret/saas-project/docker/s3

# 4. Update a specific secret field
docker-compose exec vault vault kv patch secret/saas-project/docker/jwt \
  secret_key="new_jwt_secret_$(openssl rand -base64 64)"

# 5. Add a new secret category
docker-compose exec vault vault kv put secret/saas-project/docker/email \
  smtp_host="smtp.gmail.com" \
  smtp_port="587" \
  smtp_user="your-email@gmail.com" \
  smtp_password="your-app-password"

# 6. Delete a secret (use with caution!)
docker-compose exec vault vault kv delete secret/saas-project/docker/database

# 7. View secret metadata (versions, created_time, etc.)
docker-compose exec vault vault kv metadata get secret/saas-project/docker/database

# 8. Retrieve a specific secret version
docker-compose exec vault vault kv get -version=2 secret/saas-project/docker/jwt

# 9. Enable audit logging
docker-compose exec vault vault audit enable file \
  file_path=/vault/logs/audit.log

# 10. View Vault policies
docker-compose exec vault vault policy list
docker-compose exec vault vault policy read saas-app-policy-docker

# 11. List AppRole roles
docker-compose exec vault vault list auth/approle/role

# 12. Rotate Secret ID for AppRole (invalidates old credentials)
docker-compose exec vault vault write -f auth/approle/role/saas-app-role-docker/secret-id

# 13. Access Vault Web UI
# Navigate to: http://localhost:8201/ui
# Login with root token from: ./vault/data/root-token.txt
```

**Secrets Initialization from File:**

```bash
# Create environment-specific secrets file
cat > vault/init-data/docker.env <<EOF
DATABASE_URL=postgresql://saas_user:saas_password@postgres:5432/saas_main
TENANT_DATABASE_URL_TEMPLATE=postgresql://saas_user:saas_password@postgres:5432/{database_name}
JWT_SECRET_KEY=$(openssl rand -base64 64)
JWT_ACCESS_TOKEN_EXPIRES=900
S3_ENDPOINT_URL=http://localstack:4566
S3_ACCESS_KEY_ID=test_key
S3_SECRET_ACCESS_KEY=test_secret
S3_BUCKET=saas-documents
S3_REGION=us-east-1
EOF

# Reinitialize Vault with new secrets (requires restart)
docker-compose restart vault-init
```

#### Flask Command Wrapper for Vault

The Flask wrapper script simplifies running Flask CLI commands with Vault-sourced credentials.

**Implementation** ([backend/flask-wrapper.sh](backend/flask-wrapper.sh)):

```bash
#!/bin/sh
# Script wrapper pour exécuter les commandes Flask avec les variables Vault

# Load Vault variables from .env.vault if file exists
if [ -f /.env.vault ]; then
    echo "Loading Vault variables..."

    # Export each line from .env.vault
    while IFS='=' read -r key value; do
        # Ignore empty lines and comments
        case "$key" in
            ''|\#*) continue ;;
        esac

        # Remove spaces and potential quotes
        key=$(echo "$key" | sed 's/^[ \t]*//;s/[ \t]*$//')
        value=$(echo "$value" | sed 's/^[ \t]*//;s/[ \t]*$//')

        # Export variable
        if [ -n "$key" ] && [ -n "$value" ]; then
            export "$key=$value"
        fi
    done < /.env.vault

    echo "Vault variables loaded successfully"
fi

# Execute Flask command passed as argument
exec flask "$@"
```

**Usage:**

```bash
# Inside container, use wrapper for Flask commands
docker-compose exec api /app/flask-wrapper.sh db upgrade
docker-compose exec api /app/flask-wrapper.sh shell
docker-compose exec api /app/flask-wrapper.sh routes

# The wrapper:
# 1. Loads VAULT_ADDR, VAULT_ROLE_ID, VAULT_SECRET_ID from .env.vault
# 2. Application code authenticates with Vault using these credentials
# 3. Secrets are loaded from Vault at runtime
# 4. Flask command executes with full access to secrets
```

**Why This Approach:**

- **Security**: No secrets in Docker environment variables
- **Simplicity**: .env.vault contains only AppRole credentials (not actual secrets)
- **Flexibility**: Same wrapper works for all Flask commands
- **Auditability**: All secret access goes through Vault (can be audited)
- **Fallback**: Application still works with .env if Vault unavailable

#### Application Code Integration

The platform provides a complete VaultClient implementation with AppRole authentication and automatic token renewal.

**VaultClient Implementation** ([backend/app/utils/vault_client.py](backend/app/utils/vault_client.py)):

```python
import hvac
import os
import logging
from typing import Dict, Any, Optional
from hvac.exceptions import VaultError, InvalidPath

logger = logging.getLogger(__name__)

class VaultClient:
    """
    Client Vault pour l'authentification AppRole et la récupération de secrets.

    Features:
    - AppRole authentication (more secure than token-based)
    - Automatic token renewal
    - Multi-environment support (dev, docker, prod)
    - Graceful fallback to environment variables
    - Comprehensive error handling
    """

    def __init__(
        self,
        vault_addr: Optional[str] = None,
        role_id: Optional[str] = None,
        secret_id: Optional[str] = None,
    ):
        """
        Initialize Vault client with AppRole credentials.

        Args:
            vault_addr: Vault server URL (e.g., http://vault:8200)
            role_id: AppRole Role ID for authentication
            secret_id: AppRole Secret ID for authentication
        """
        self.vault_addr = vault_addr or os.environ.get("VAULT_ADDR")
        self.role_id = role_id or os.environ.get("VAULT_ROLE_ID")
        self.secret_id = secret_id or os.environ.get("VAULT_SECRET_ID")

        if not all([self.vault_addr, self.role_id, self.secret_id]):
            raise ValueError(
                "VAULT_ADDR, VAULT_ROLE_ID, and VAULT_SECRET_ID must be defined"
            )

        self.client: Optional[hvac.Client] = None
        self.token: Optional[str] = None
        self.token_ttl: int = 0

        logger.info(f"VaultClient initialized with address: {self.vault_addr}")

    def authenticate(self) -> str:
        """
        Authenticate with Vault using AppRole method.

        Returns:
            str: Vault token obtained from authentication

        Raises:
            VaultError: If authentication fails
        """
        try:
            # Create unauthenticated client
            self.client = hvac.Client(url=self.vault_addr)

            # Check Vault status
            if not self.client.sys.is_initialized():
                raise VaultError("Vault is not initialized")

            if self.client.sys.is_sealed():
                raise VaultError("Vault is sealed")

            logger.info("Connected to Vault, attempting AppRole authentication...")

            # Authenticate with AppRole
            auth_response = self.client.auth.approle.login(
                role_id=self.role_id,
                secret_id=self.secret_id,
            )

            # Extract token and TTL
            self.token = auth_response["auth"]["client_token"]
            self.token_ttl = auth_response["auth"]["lease_duration"]

            # Set token on client
            self.client.token = self.token

            logger.info(
                f"AppRole authentication successful. Token TTL: {self.token_ttl}s"
            )

            return self.token

        except VaultError as e:
            logger.error(f"Vault authentication error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Vault authentication: {e}")
            raise VaultError(f"Unexpected error: {e}")

    def get_secret(self, path: str) -> Dict[str, Any]:
        """
        Retrieve a secret from Vault KV v2 store.

        Args:
            path: Secret path (e.g., "saas-project/docker/database")

        Returns:
            Dict containing secret data

        Raises:
            VaultError: If secret retrieval fails
        """
        if not self.client or not self.client.is_authenticated():
            logger.warning("Client not authenticated, attempting authentication...")
            self.authenticate()

        try:
            logger.debug(f"Reading secret: secret/data/{path}")

            response = self.client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point="secret",
            )

            secret_data = response["data"]["data"]
            logger.info(f"Secret retrieved successfully: {path}")

            return secret_data

        except InvalidPath:
            logger.error(f"Invalid or non-existent secret path: {path}")
            raise VaultError(f"Secret not found: {path}")
        except VaultError as e:
            logger.error(f"Error retrieving secret {path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error reading secret {path}: {e}")
            raise VaultError(f"Unexpected error: {e}")

    def get_all_secrets(self, environment: str = "docker") -> Dict[str, Any]:
        """
        Retrieve all application secrets for a given environment.

        Args:
            environment: Environment name (dev, docker, prod)

        Returns:
            Dict with all secrets organized by category
        """
        secrets = {}

        # Define secret paths to retrieve
        secret_paths = {
            "database": f"saas-project/{environment}/database",
            "jwt": f"saas-project/{environment}/jwt",
            "s3": f"saas-project/{environment}/s3",
        }

        for category, path in secret_paths.items():
            try:
                secrets[category] = self.get_secret(path)
            except VaultError as e:
                logger.error(f"Failed to retrieve {category} secrets: {e}")
                raise

        logger.info(f"All secrets for environment '{environment}' retrieved")
        return secrets

    def renew_token(self) -> int:
        """
        Renew the current Vault token.

        Returns:
            int: New token TTL in seconds

        Raises:
            VaultError: If renewal fails
        """
        if not self.client or not self.token:
            raise VaultError("Client not authenticated, cannot renew token")

        try:
            logger.info("Renewing Vault token...")

            response = self.client.auth.token.renew_self()
            self.token_ttl = response["auth"]["lease_duration"]

            logger.info(f"Token renewed successfully. New TTL: {self.token_ttl}s")

            return self.token_ttl

        except VaultError as e:
            logger.error(f"Error renewing token: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during renewal: {e}")
            raise VaultError(f"Unexpected error: {e}")

    def get_token_ttl(self) -> int:
        """
        Get remaining TTL of the current token.

        Returns:
            int: TTL in seconds
        """
        if not self.client or not self.token:
            return 0

        try:
            response = self.client.auth.token.lookup_self()
            return response["data"]["ttl"]
        except Exception as e:
            logger.warning(f"Cannot retrieve token TTL: {e}")
            return 0

    def is_authenticated(self) -> bool:
        """
        Check if client is authenticated.

        Returns:
            bool: True if authenticated, False otherwise
        """
        return self.client is not None and self.client.is_authenticated()
```

**Configuration Integration** ([backend/app/config.py](backend/app/config.py)):

```python
from app.utils.vault_client import VaultClient, VaultError
import logging

class Config:
    """Base configuration with Vault integration"""

    # Vault Configuration
    USE_VAULT = os.environ.get('USE_VAULT', 'false').lower() == 'true'
    VAULT_ENVIRONMENT = os.environ.get('VAULT_ENVIRONMENT', 'docker')

    # Default configuration from environment variables
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:postgres@localhost:5432/saas_platform'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or secrets.token_urlsafe(32)
    S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL', 'https://s3.amazonaws.com')
    # ... other default config ...

    @classmethod
    def load_from_vault(cls, vault_client):
        """
        Load configuration from HashiCorp Vault.

        Args:
            vault_client: Authenticated VaultClient instance
        """
        logger = logging.getLogger(__name__)

        try:
            logger.info(
                f"Loading configuration from Vault (env: {cls.VAULT_ENVIRONMENT})"
            )

            # Retrieve all secrets
            secrets = vault_client.get_all_secrets(environment=cls.VAULT_ENVIRONMENT)

            # Database configuration
            if "database" in secrets:
                db_secrets = secrets["database"]
                cls.SQLALCHEMY_DATABASE_URI = db_secrets.get("main_url")
                cls.TENANT_DATABASE_URL_TEMPLATE = db_secrets.get("tenant_url_template")
                logger.info("Database configuration loaded from Vault")

            # JWT configuration
            if "jwt" in secrets:
                jwt_secrets = secrets["jwt"]
                cls.JWT_SECRET_KEY = jwt_secrets.get("secret_key")
                cls.SECRET_KEY = jwt_secrets.get("secret_key")  # Use same key

                # Handle TTL
                access_token_expires = jwt_secrets.get("access_token_expires")
                if access_token_expires:
                    cls.JWT_ACCESS_TOKEN_EXPIRES = timedelta(
                        seconds=int(access_token_expires)
                    )
                logger.info("JWT configuration loaded from Vault")

            # S3 configuration
            if "s3" in secrets:
                s3_secrets = secrets["s3"]
                cls.S3_ENDPOINT_URL = s3_secrets.get("endpoint_url")
                cls.S3_ACCESS_KEY_ID = s3_secrets.get("access_key_id")
                cls.S3_SECRET_ACCESS_KEY = s3_secrets.get("secret_access_key")
                cls.S3_BUCKET_NAME = s3_secrets.get("bucket_name")
                cls.S3_REGION = s3_secrets.get("region")
                logger.info("S3 configuration loaded from Vault")

            logger.info("Complete configuration loaded from Vault successfully")

        except VaultError as e:
            logger.error(f"Error loading configuration from Vault: {e}")
            logger.warning("Using default configuration (environment variables)")
            # Keep default values loaded from .env
        except Exception as e:
            logger.error(f"Unexpected error loading from Vault: {e}")
            raise
```

**Application Initialization with Vault** ([backend/app/\_\_init\_\_.py](backend/app/__init__.py)):

```python
from flask import Flask
from app.config import get_config
from app.utils.vault_client import VaultClient, VaultError
import logging

def create_app(config_name=None):
    """Application factory with Vault integration"""

    app = Flask(__name__)

    # Load base configuration
    config_class = get_config(config_name)
    app.config.from_object(config_class)

    # Initialize Vault if enabled
    if app.config.get('USE_VAULT'):
        try:
            logger.info("Initializing Vault client...")
            vault_client = VaultClient()
            vault_client.authenticate()

            # Load secrets from Vault
            config_class.load_from_vault(vault_client)
            app.config.from_object(config_class)

            logger.info("Application configured with Vault secrets")

        except VaultError as e:
            logger.error(f"Vault initialization failed: {e}")
            logger.warning("Falling back to environment variables")
        except Exception as e:
            logger.error(f"Unexpected Vault error: {e}")
            raise

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    # ...

    return app
```

#### Vault Troubleshooting Guide

**Common Issues and Solutions:**

```bash
# Problem: Vault is sealed after restart
# Solution: Run the unseal script
docker-compose up vault-unseal

# Problem: Cannot authenticate with AppRole
# Symptom: "permission denied" or "invalid role_id"
# Solution 1: Check credentials in .env.vault
cat .env.vault

# Solution 2: Regenerate AppRole credentials
docker-compose restart vault-init

# Problem: Secrets not found
# Symptom: "secret not found at path..."
# Solution: Verify secrets exist
docker-compose exec vault vault kv list secret/saas-project/docker/
docker-compose exec vault vault kv get secret/saas-project/docker/database

# Problem: Token expired
# Symptom: "permission denied" after working previously
# Solution: Token renewal is automatic, but check TTL
# VaultClient automatically renews tokens, but verify:
docker-compose logs api | grep -i "token"

# Problem: Vault data lost after restart
# Symptom: Vault requires reinitialization
# Solution: Check persistent volume
ls -la ./vault/data/
# Should contain: unseal-keys.json, root-token.txt, vault.db

# Problem: Application using env vars instead of Vault
# Symptom: Old secrets still in use after Vault update
# Solution: Verify USE_VAULT=true in environment
docker-compose exec api env | grep USE_VAULT
docker-compose exec api env | grep VAULT

# Problem: Cannot access Vault UI
# Solution: Check port mapping and token
# URL: http://localhost:8201/ui
# Token: cat ./vault/data/root-token.txt

# Problem: High memory usage
# Solution: Vault file backend has cache, adjust in production
# For production, use Integrated Storage (Raft) instead of file
```

**Debugging Commands:**

```bash
# Check Vault container logs
docker-compose logs -f vault

# Check initialization logs
docker-compose logs vault-init

# Check unseal logs
docker-compose logs vault-unseal

# Verify Vault health
docker-compose exec vault vault status

# Check application Vault connection
docker-compose exec api python -c "
from app.utils.vault_client import VaultClient
try:
    client = VaultClient()
    client.authenticate()
    print('✓ Vault authentication successful')
    secrets = client.get_all_secrets('docker')
    print(f'✓ Loaded {len(secrets)} secret categories')
except Exception as e:
    print(f'✗ Error: {e}')
"

# Monitor Vault audit logs (if enabled)
docker-compose exec vault tail -f /vault/logs/audit.log
```

#### Security Best Practices with Vault

**Development Environment:**

```
✓ Use file storage backend for simplicity
✓ Auto-unseal for convenience
✓ Separate .env.vault from version control (.gitignore)
✓ Use docker environment for local testing
✓ Commit vault/init-data/*.env.example templates (not actual secrets)
✓ Document secret structure for team members
```

**Production Environment Checklist:**

```
✓ Use Vault in production mode (not dev mode)
✓ Configure proper Vault backend:
  - Integrated Storage (Raft) for HA
  - Or: Consul/etcd for existing infrastructure
✓ Enable TLS for all Vault API endpoints
✓ Use Auto-unseal with cloud KMS:
  - AWS KMS
  - Azure Key Vault
  - GCP Cloud KMS
✓ Use AppRole authentication (not root tokens)
✓ Implement secret rotation policies
✓ Enable comprehensive audit logging
✓ Use separate Vault namespaces per environment
✓ Implement least-privilege access policies
✓ Regular backup of Vault data:
  - Use vault operator raft snapshot save
  - Store backups in encrypted, off-site location
  - Test backup restoration regularly
✓ Monitor Vault metrics and health:
  - Token expiration rates
  - Secret access patterns
  - Seal/unseal events
  - Authentication failures
✓ Implement disaster recovery plan
✓ Use Network policies to restrict Vault access
✓ Enable MFA for Vault UI access
✓ Rotate AppRole Secret IDs periodically
✓ Review and audit Vault policies quarterly
```

**Vault Policy Example** (vault/policies/saas-app-policy.hcl):

```hcl
# Production-ready policy for SaaS application

# Allow reading application secrets for specific environment
path "secret/data/saas-project/prod/*" {
  capabilities = ["read"]
}

# Allow listing secret metadata (for discovery)
path "secret/metadata/saas-project/prod/*" {
  capabilities = ["list", "read"]
}

# Allow token renewal (keep sessions alive)
path "auth/token/renew-self" {
  capabilities = ["update"]
}

# Allow token lookup (check TTL)
path "auth/token/lookup-self" {
  capabilities = ["read"]
}

# Deny access to other environments
path "secret/data/saas-project/dev/*" {
  capabilities = ["deny"]
}

path "secret/data/saas-project/staging/*" {
  capabilities = ["deny"]
}

# Deny write access (secrets managed separately)
path "secret/data/*" {
  capabilities = ["deny"]
}

# Deny access to Vault system paths
path "sys/*" {
  capabilities = ["deny"]
}
```

**Secret Rotation Strategy:**

```bash
# 1. Generate new secret
NEW_JWT_SECRET=$(openssl rand -base64 64)

# 2. Update Vault with new secret (creates new version)
docker-compose exec vault vault kv put secret/saas-project/prod/jwt \
  secret_key="$NEW_JWT_SECRET" \
  access_token_expires="900"

# 3. Restart application to load new secret
docker-compose restart api worker

# 4. Verify application using new secret
docker-compose exec api python -c "
from app import create_app
app = create_app()
print(f'JWT Secret (first 10 chars): {app.config[\"JWT_SECRET_KEY\"][:10]}...')
"

# 5. Old tokens remain valid until expiration
# 6. After grace period, old secret version is deleted
docker-compose exec vault vault kv delete -versions=1 secret/saas-project/prod/jwt
```

**Environment Separation:**

```
vault/
└── init-data/
    ├── docker.env       # Local development (committed as .example)
    ├── staging.env      # Staging secrets (not committed)
    └── prod.env         # Production secrets (not committed)

Workflow:
1. Developer creates docker.env from docker.env.example
2. CI/CD pipeline uses staging.env for staging deployments
3. Production uses prod.env (managed by DevOps/Security team)
4. Each environment has separate AppRole with scoped policies
```

**Vault High Availability Setup (Production):**

```yaml
# Production Vault with Integrated Storage (Raft)
vault-1:
  image: hashicorp/vault:1.15
  environment:
    VAULT_CLUSTER_ADDR: https://vault-1:8201
  volumes:
    - ./vault/config/vault-raft.hcl:/vault/config/vault.hcl:ro
  command: vault server -config=/vault/config/vault.hcl

vault-2:
  image: hashicorp/vault:1.15
  environment:
    VAULT_CLUSTER_ADDR: https://vault-2:8201
  volumes:
    - ./vault/config/vault-raft.hcl:/vault/config/vault.hcl:ro
  command: vault server -config=/vault/config/vault.hcl

vault-3:
  image: hashicorp/vault:1.15
  environment:
    VAULT_CLUSTER_ADDR: https://vault-3:8201
  volumes:
    - ./vault/config/vault-raft.hcl:/vault/config/vault.hcl:ro
  command: vault server -config=/vault/config/vault.hcl
```

#### Migration from Environment Variables to Vault

```bash
# Script to migrate existing .env to Vault
#!/bin/bash
# backend/scripts/migrate_to_vault.sh

# Read .env file and push to Vault
while IFS='=' read -r key value; do
    if [[ ! -z "$key" && ! "$key" =~ ^# ]]; then
        # Convert key to lowercase for Vault
        vault_key=$(echo "$key" | tr '[:upper:]' '[:lower:]')
        # Remove quotes from value
        clean_value=$(echo "$value" | sed 's/^"//;s/"$//')
        # Store in Vault
        docker-compose exec vault vault kv patch secret/saas-platform \
            "${vault_key}=${clean_value}"
    fi
done < .env

echo "Secrets migrated to Vault successfully"
```

### Vault Integration Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Complete Vault Integration Flow                      │
└─────────────────────────────────────────────────────────────────────────┘

1. INITIALIZATION (First Time Setup)
   ┌──────────────┐
   │ docker-compose│
   │     up        │
   └───────┬───────┘
           │
           ▼
   ┌──────────────────────────────────────────┐
   │ Vault Container Starts                   │
   │ - Loads vault.hcl config                 │
   │ - Uses file storage: /vault/data         │
   │ - Listens on port 8200                   │
   └───────┬──────────────────────────────────┘
           │
           ▼
   ┌──────────────────────────────────────────┐
   │ vault-unseal Container                   │
   │ - Checks if Vault initialized            │
   │ - If NO: vault operator init             │
   │   • Generates 5 unseal keys              │
   │   • Generates root token                 │
   │   • Saves to /vault/data/                │
   │ - Unseals with 3 of 5 keys               │
   └───────┬──────────────────────────────────┘
           │
           ▼
   ┌──────────────────────────────────────────┐
   │ vault-init Container                     │
   │ 1. Authenticates with root token         │
   │ 2. Enables KV v2 secrets engine          │
   │ 3. Reads vault/init-data/{env}.env       │
   │ 4. Injects secrets to Vault:             │
   │    • secret/.../database                 │
   │    • secret/.../jwt                      │
   │    • secret/.../s3                       │
   │ 5. Enables AppRole auth method           │
   │ 6. Creates access policy                 │
   │ 7. Creates AppRole role                  │
   │ 8. Generates ROLE_ID and SECRET_ID       │
   │ 9. Writes to .env.vault:                 │
   │    VAULT_ADDR=http://vault:8200          │
   │    VAULT_ROLE_ID=xxx                     │
   │    VAULT_SECRET_ID=yyy                   │
   └───────┬──────────────────────────────────┘
           │
           ▼
   ✅ Vault Ready for Application Use


2. APPLICATION STARTUP
   ┌──────────────┐
   │  api/worker  │
   │  container   │
   └───────┬───────┘
           │
           ▼
   ┌──────────────────────────────────────────┐
   │ Load .env.vault file                     │
   │ - VAULT_ADDR                             │
   │ - VAULT_ROLE_ID                          │
   │ - VAULT_SECRET_ID                        │
   └───────┬──────────────────────────────────┘
           │
           ▼
   ┌──────────────────────────────────────────┐
   │ VaultClient.__init__()                   │
   │ - Reads env vars                         │
   │ - Creates hvac.Client instance           │
   └───────┬──────────────────────────────────┘
           │
           ▼
   ┌──────────────────────────────────────────┐
   │ VaultClient.authenticate()               │
   │ - client.auth.approle.login()            │
   │ - Receives temporary token (TTL: 1h)     │
   │ - Sets client.token                      │
   └───────┬──────────────────────────────────┘
           │
           ▼
   ┌──────────────────────────────────────────┐
   │ Config.load_from_vault()                 │
   │ - get_all_secrets('docker')              │
   │   • Reads database secrets               │
   │   • Reads JWT secrets                    │
   │   • Reads S3 secrets                     │
   │ - Updates Flask config                   │
   └───────┬──────────────────────────────────┘
           │
           ▼
   ✅ Application Running with Vault Secrets


3. RUNTIME OPERATIONS
   ┌──────────────────────────────────────────┐
   │ Token Management (automatic)             │
   │ - VaultClient.get_token_ttl()            │
   │ - If TTL < threshold:                    │
   │   VaultClient.renew_token()              │
   └──────────────────────────────────────────┘

   ┌──────────────────────────────────────────┐
   │ Secret Access (on-demand)                │
   │ - VaultClient.get_secret(path)           │
   │ - Auto-authenticate if needed            │
   │ - Returns secret data as dict            │
   └──────────────────────────────────────────┘


4. RESTART/RECOVERY
   ┌──────────────────────────────────────────┐
   │ Container Restart                        │
   │ - Vault data persisted in ./vault/data   │
   │ - vault-unseal detects sealed state      │
   │ - Reads unseal keys from file            │
   │ - Auto-unseals Vault                     │
   │ - Application reconnects                 │
   └──────────────────────────────────────────┘
```

### Vault Integration Summary

**Key Components:**

| Component | Purpose | Persistence |
|-----------|---------|-------------|
| `vault` service | Main Vault server | Persistent (file backend) |
| `vault-unseal` | Auto-unseal on restart | Run-once container |
| `vault-init` | Inject secrets & create AppRole | Run-once container |
| `.env.vault` | AppRole credentials | Generated, gitignored |
| `VaultClient` | Python client for Vault | Application code |
| `Config.load_from_vault()` | Load secrets to Flask config | Application startup |

**Secret Paths:**

| Path | Contents | Used By |
|------|----------|---------|
| `secret/saas-project/docker/database` | Database URLs | API, Worker |
| `secret/saas-project/docker/jwt` | JWT signing key | API |
| `secret/saas-project/docker/s3` | S3 credentials | API, Worker |

**Authentication Flow:**

1. **AppRole Credentials** (.env.vault) → **VaultClient.authenticate()** → **Temporary Token** (1h TTL)
2. **Token** → **VaultClient.get_secret()** → **Application Secrets**
3. **Token expiring** → **VaultClient.renew_token()** → **Extended Session**

**Benefits of This Approach:**

✅ **Security:**
- Secrets never in code or Docker env vars
- AppRole provides scoped, auditable access
- Automatic token renewal prevents expiration
- Secrets encrypted at rest in Vault

✅ **Operational:**
- Persistent storage survives restarts
- Auto-unseal for convenience
- Centralized secret management
- Easy secret rotation without code changes

✅ **Development:**
- Simple local setup (docker-compose up)
- Environment-specific secrets (dev/staging/prod)
- Fallback to .env if Vault unavailable
- Clear separation of concerns

**Environment Variables Used:**

| Variable | Source | Purpose |
|----------|--------|---------|
| `USE_VAULT` | .env | Enable/disable Vault integration |
| `VAULT_ENVIRONMENT` | .env | Environment name (dev/docker/prod) |
| `VAULT_ADDR` | .env.vault | Vault server URL |
| `VAULT_ROLE_ID` | .env.vault | AppRole authentication |
| `VAULT_SECRET_ID` | .env.vault | AppRole authentication |

### Vault File Structure

```
SaaSBackendWithClaude/
├── vault/
│   ├── config/
│   │   └── vault.hcl                    # Vault server configuration
│   ├── data/                            # Persistent storage (DO NOT COMMIT)
│   │   ├── unseal-keys.json             # 5 unseal keys (Shamir split)
│   │   ├── root-token.txt               # Root token for admin access
│   │   └── vault.db/                    # File backend database
│   ├── scripts/
│   │   ├── unseal-vault.sh              # Auto-unseal script
│   │   └── init-vault.sh                # Secrets injection script
│   ├── init-data/
│   │   ├── docker.env.example           # Template (committed)
│   │   ├── docker.env                   # Actual secrets (NOT committed)
│   │   ├── staging.env                  # Staging secrets (NOT committed)
│   │   └── prod.env                     # Production secrets (NOT committed)
│   └── logs/
│       └── audit.log                    # Vault audit logs (if enabled)
├── .env.vault                           # AppRole credentials (NOT committed)
└── backend/
    ├── app/
    │   ├── utils/
    │   │   └── vault_client.py          # VaultClient implementation
    │   └── config.py                    # Config with Vault integration
    └── flask-wrapper.sh                 # CLI wrapper for Vault vars
```

### Environment Security Summary

```
Secret Management Architecture:
├── Development Environment
│   ├── HashiCorp Vault with file storage
│   ├── Auto-unseal for convenience
│   ├── AppRole authentication
│   └── Fallback to .env files if Vault unavailable
├── Testing/Staging
│   ├── Vault with file backend
│   ├── Separate secret paths per environment
│   ├── Environment-specific AppRole policies
│   └── Separate .env.vault credentials
└── Production
    ├── Vault cluster (HA mode with Raft)
    ├── Auto-unseal with cloud KMS (AWS/Azure/GCP)
    ├── TLS-encrypted communication
    ├── Comprehensive audit logging to SIEM
    ├── Automated secret rotation
    ├── Network isolation and access control
    └── Regular backup and disaster recovery testing
```

---

## Scalability & Performance

### Horizontal Scaling

The platform is designed for horizontal scalability:

```
┌────────────────────────────────────────────────────────────────┐
│                    Scaling Strategy                             │
└────────────────────────────────────────────────────────────────┘

Stateless API Servers:
- No session state stored in memory
- JWT tokens eliminate server-side sessions
- Scale API instances independently
- Load balancer distributes requests

Database Scaling:
- Read replicas for read-heavy workloads
- Connection pooling (SQLAlchemy)
- Main DB can be scaled separately from tenant DBs
- Consider sharding tenants across DB instances (future)

Kafka Scaling:
- Add more consumer instances
- Partition topics for parallel processing
- Consumer group coordination via Kafka

S3 Scaling:
- S3 scales automatically
- Use CloudFront CDN for downloads (future)
- Multipart uploads for large files (future)
```

### Performance Optimizations

```
1. Database Query Optimization:
   - Indexes on frequently queried fields:
     - users.email
     - documents.filename
     - documents.user_id
     - documents.created_at
     - files.md5_hash
   - Composite index: (user_id, filename)
   - Query only needed fields (avoid SELECT *)
   - Lazy loading relationships

2. Caching Strategy (Future Enhancement):
   - Redis for session data
   - Cache tenant metadata
   - Cache user-tenant associations
   - Cache file metadata

3. Connection Pooling:
   SQLALCHEMY_POOL_SIZE = 20
   SQLALCHEMY_MAX_OVERFLOW = 40
   SQLALCHEMY_POOL_TIMEOUT = 30
   SQLALCHEMY_POOL_RECYCLE = 3600

4. File Upload Optimization:
   - MD5 check before upload (deduplication)
   - Streaming uploads (not loading entire file in memory)
   - Async S3 uploads (non-blocking)
   - Pre-signed POST for direct browser uploads (future)

5. API Performance:
   - Pagination on all list endpoints
   - Limit response payload size
   - Gzip compression
   - ETags for conditional requests (future)
```

### Monitoring & Metrics

```
Key Metrics to Monitor:

Application:
- Request rate (requests/second)
- Response time (p50, p95, p99)
- Error rate (4xx, 5xx)
- Active users
- Tenant count

Database:
- Connection pool usage
- Query execution time
- Slow query log
- Database size per tenant
- Active connections

Kafka:
- Message lag per consumer group
- Messages/second
- Failed messages
- Consumer processing time

S3:
- Upload rate
- Download rate
- Total storage used
- Storage cost per tenant

Infrastructure:
- CPU usage
- Memory usage
- Disk I/O
- Network I/O
```

---

## Deployment Architecture

### Docker Compose Setup

Development and testing environment:

```yaml
# docker-compose.yml

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: saas_user
      POSTGRES_PASSWORD: saas_password
      POSTGRES_DB: saas_main
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  # Kafka + Zookeeper
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
    ports:
      - "9092:9092"

  # LocalStack (S3 emulation for development)
  localstack:
    image: localstack/localstack:latest
    environment:
      SERVICES: s3
      DEFAULT_REGION: us-east-1
    ports:
      - "4566:4566"

  # Flask API
  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    depends_on:
      - postgres
      - kafka
      - localstack
    environment:
      FLASK_APP: run.py
      FLASK_ENV: development
      DATABASE_URL: postgresql://saas_user:saas_password@postgres:5432/saas_main
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      AWS_ENDPOINT_URL: http://localstack:4566
    ports:
      - "5000:5000"
    volumes:
      - ./backend:/app
    command: gunicorn -w 4 -b 0.0.0.0:5000 run:app

  # Kafka Consumer Worker
  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    depends_on:
      - postgres
      - kafka
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      DATABASE_URL: postgresql://saas_user:saas_password@postgres:5432/saas_main
    command: python -m app.worker.consumer

volumes:
  postgres_data:
```

### Production Deployment (AWS)

```
┌────────────────────────────────────────────────────────────────┐
│                    AWS Production Architecture                  │
└────────────────────────────────────────────────────────────────┘

┌─────────────────────────┐
│   Route 53 (DNS)        │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   CloudFront (CDN)      │  ← Optional for static assets
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Application Load        │
│ Balancer (ALB)          │
│ - HTTPS termination     │
│ - Health checks         │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│  ECS Fargate / EKS                      │
│  ┌────────┐  ┌────────┐  ┌────────┐    │
│  │ API    │  │ API    │  │ Worker │    │
│  │ Task 1 │  │ Task 2 │  │ Task   │    │
│  └────────┘  └────────┘  └────────┘    │
│  Auto-scaling based on CPU/Memory       │
└─────────────────────────────────────────┘
            │
    ┌───────┼───────┐
    ▼       ▼       ▼
┌─────┐ ┌─────┐ ┌─────┐
│ RDS │ │ MSK │ │ S3  │
│ PG  │ │Kafka│ │     │
└─────┘ └─────┘ └─────┘

Components:
- RDS PostgreSQL Multi-AZ (main + tenant databases)
- Amazon MSK (Managed Kafka)
- S3 bucket (private, versioned, encrypted)
- ECS Fargate or EKS for container orchestration
- Application Load Balancer
- CloudWatch for logging and monitoring
- Secrets Manager for credentials
```

### Environment-Specific Configuration

```python
# backend/app/config.py

class DevelopmentConfig:
    DEBUG = True
    TESTING = False
    SQLALCHEMY_ECHO = True  # Log all queries

class ProductionConfig:
    DEBUG = False
    TESTING = False
    SQLALCHEMY_ECHO = False

    # Security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Performance
    SQLALCHEMY_POOL_SIZE = 20
    SQLALCHEMY_MAX_OVERFLOW = 40
    SQLALCHEMY_POOL_PRE_PING = True

class TestingConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    JWT_SECRET_KEY = 'test-secret-key'
```

### Health Checks

```python
# backend/app/routes/health.py

@app.route('/api/health', methods=['GET'])
def health_check():
    """Comprehensive health check for load balancer"""
    health = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'checks': {}
    }

    # Database check
    try:
        db.session.execute(text('SELECT 1'))
        health['checks']['database'] = 'ok'
    except Exception as e:
        health['status'] = 'unhealthy'
        health['checks']['database'] = f'error: {str(e)}'

    # S3 check (optional)
    try:
        s3_client.list_buckets()
        health['checks']['s3'] = 'ok'
    except Exception as e:
        health['checks']['s3'] = f'warning: {str(e)}'

    # Kafka check (optional)
    try:
        # Check Kafka connectivity
        health['checks']['kafka'] = 'ok'
    except Exception as e:
        health['checks']['kafka'] = f'warning: {str(e)}'

    status_code = 200 if health['status'] == 'healthy' else 503
    return jsonify(health), status_code
```

### Deployment Checklist

```
Pre-Deployment:
□ Run all tests (unit + integration)
□ Update requirements.txt
□ Update environment variables in .env
□ Generate strong JWT secret
□ Review and update database migrations
□ Build and test Docker images
□ Run security scan on dependencies
□ Update API documentation (swagger.yaml)

Production Deployment:
□ Set up RDS PostgreSQL instance
□ Set up Amazon MSK (Kafka)
□ Create S3 bucket with encryption
□ Configure IAM roles and policies
□ Set up Application Load Balancer
□ Configure SSL certificate (ACM)
□ Deploy container tasks (ECS/EKS)
□ Configure auto-scaling policies
□ Set up CloudWatch alarms
□ Configure log aggregation
□ Set up backup policies
□ Configure monitoring dashboards

Post-Deployment:
□ Verify health checks
□ Test authentication flow
□ Test tenant creation
□ Test document upload
□ Verify Kafka message processing
□ Monitor error rates
□ Monitor performance metrics
□ Set up on-call rotation
```

---

## Appendix: File Organization

```
SaaSBackendWithClaude/
├── backend/
│   ├── app/
│   │   ├── __init__.py                 # Application factory
│   │   ├── config.py                   # Configuration classes
│   │   ├── extensions.py               # Flask extensions
│   │   ├── models/                     # Database models
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # BaseModel abstract class
│   │   │   ├── user.py                 # User model (main DB)
│   │   │   ├── tenant.py               # Tenant model (main DB)
│   │   │   ├── user_tenant_association.py  # Association model
│   │   │   ├── file.py                 # File model (tenant DBs)
│   │   │   └── document.py             # Document model (tenant DBs)
│   │   ├── schemas/                    # Marshmallow validation schemas
│   │   │   ├── __init__.py
│   │   │   ├── user_schema.py
│   │   │   ├── tenant_schema.py
│   │   │   ├── document_schema.py
│   │   │   ├── file_schema.py
│   │   │   └── user_tenant_association_schema.py
│   │   ├── routes/                     # API endpoints (controllers)
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                 # Authentication routes
│   │   │   ├── users.py                # User management routes
│   │   │   ├── tenants.py              # Tenant management routes
│   │   │   ├── documents.py            # Document routes
│   │   │   ├── files.py                # File routes
│   │   │   └── kafka_demo.py           # Kafka demo routes
│   │   ├── services/                   # Business logic layer
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py         # Authentication logic
│   │   │   ├── user_service.py         # User operations
│   │   │   ├── tenant_service.py       # Tenant operations
│   │   │   ├── document_service.py     # Document operations
│   │   │   ├── file_service.py         # File operations
│   │   │   └── kafka_service.py        # Kafka producer
│   │   ├── utils/                      # Utility modules
│   │   │   ├── __init__.py
│   │   │   ├── responses.py            # JSON response helpers
│   │   │   ├── decorators.py           # Custom decorators
│   │   │   ├── database.py             # Multi-tenant DB manager
│   │   │   └── s3_client.py            # S3 client wrapper
│   │   └── worker/                     # Kafka consumers
│   │       ├── __init__.py
│   │       ├── producer.py             # Kafka producer
│   │       └── consumer.py             # Kafka consumer worker
│   ├── migrations/                     # Alembic database migrations
│   ├── tests/
│   │   ├── unit/                       # Unit tests
│   │   │   ├── test_models.py
│   │   │   ├── test_schemas.py
│   │   │   ├── test_services.py
│   │   │   └── test_utils.py
│   │   ├── integration/                # Integration tests
│   │   │   ├── test_auth_flow.py
│   │   │   ├── test_tenant_operations.py
│   │   │   └── test_document_operations.py
│   │   └── conftest.py                 # Pytest fixtures
│   ├── scripts/
│   │   └── init_db.py                  # Database initialization
│   ├── requirements.txt                # Python dependencies
│   ├── Dockerfile                      # Docker image definition
│   └── run.py                          # Application entry point
├── docker/                             # Additional Docker files
├── docs/
│   ├── ARCHITECTURE.md                 # This file
│   └── API.md                          # API documentation (optional)
├── .env.example                        # Environment variables template
├── .env.docker                         # Docker environment
├── docker-compose.yml                  # Multi-container setup
├── swagger.yaml                        # OpenAPI specification
├── README.md                           # Project documentation
└── plan.md                             # Implementation plan
```

---

## Summary

This architecture document provides a comprehensive overview of the SaaS Multi-Tenant Backend Platform, including:

1. **Layered Architecture**: Strict separation between routes, services, and models
2. **Multi-Tenancy**: Database-per-tenant isolation with dynamic binding
3. **Database Design**: Main database for users/tenants, separate databases for tenant data
4. **Authentication**: JWT-based with bcrypt password hashing
5. **Authorization**: Role-based access control (admin, user, viewer)
6. **File Storage**: S3 with MD5 deduplication and sharded paths
7. **Async Processing**: Kafka for background tasks
8. **Security**: Multiple layers of security controls
9. **Scalability**: Horizontal scaling with stateless design
10. **Deployment**: Docker Compose for development, AWS for production

For API details, see [swagger.yaml](../swagger.yaml). For setup instructions, see [README.md](../README.md).
