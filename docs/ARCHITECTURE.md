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
       ┌───────────────────────┼───────────────────────┐
       │                       │                       │
       ▼                       ▼                       ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ PostgreSQL   │        │ Apache Kafka │        │   AWS S3     │
│ Main DB      │        │  Message     │        │   Object     │
│ + Tenant DBs │        │  Broker      │        │   Storage    │
└──────────────┘        └──────┬───────┘        └──────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │ Kafka Worker │
                        │  (Consumer)  │
                        └──────────────┘
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

### Environment Security

```
Required Environment Variables (Secrets):
- JWT_SECRET_KEY           (64+ character random string)
- DATABASE_URL             (PostgreSQL connection string)
- AWS_ACCESS_KEY_ID        (S3 access)
- AWS_SECRET_ACCESS_KEY    (S3 secret)
- S3_BUCKET_NAME
- KAFKA_BOOTSTRAP_SERVERS

Production Checklist:
✓ Change all default passwords
✓ Generate strong JWT secret
✓ Use IAM roles instead of AWS keys (if on EC2)
✓ Enable database SSL connections
✓ Configure firewall rules (only allow necessary ports)
✓ Enable API rate limiting
✓ Configure CORS properly
✓ Use secrets management (AWS Secrets Manager, HashiCorp Vault)
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
        db.session.execute('SELECT 1')
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
