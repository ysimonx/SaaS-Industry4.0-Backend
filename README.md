# SaaS Multi-Tenant Backend Industry 4.0 Platform

**A Production-Ready Foundation for Industry 4.0 SaaS Applications**

- [Quick Start avec Docker (Recommended)](#quick-start)
- **Approach A: With Vault** - See [Quick Start - Option A](#option-a-with-hashicorp-vault-recommended-for-production-like-setup) for detailed setup
- **Approach B: Without Vault** - See [Quick Start - Option B](#option-b-without-vault-simple-setup-for-development) for simple development setup


## Features

### ✅ User Management
- User registration with email validation
- Secure login with JWT tokens (15-min access, 7-day refresh)
- Password hashing with bcrypt
- User profile management
- Token refresh and logout (blacklist)

### ✅ Multi-Tenant System
- Dynamic tenant creation with isolated databases
- Automatic database provisioning
- Role-based access control (admin, user, viewer)
- User-tenant associations
- Tenant member management

### ✅ Enterprise Authentication (SSO)
- Azure AD / Microsoft Entra ID integration
- Per-tenant SSO configuration
- **Confidential Application mode (client_secret REQUIRED)**
- **NOT using PKCE - requires client_secret for secure authentication**
- Auto-provisioning with configurable rules
- Azure AD group to role mapping
- Hybrid authentication modes (local, SSO, or both)
- Encrypted token storage via HashiCorp Vault
- Multi-tenant identity mapping (different Azure IDs per tenant)
- Azure AD's token refresh with a celery worker

### ✅ Document Management
- Document upload with multipart/form-data
- MD5-based file deduplication (storage optimization)
- S3-compatible storage with sharded paths
- Document metadata management
- Pre-signed URL generation for downloads
- Pagination and filtering

### ✅ File Management
- Immutable file storage
- Reference counting (shared files across documents)
- Orphaned file detection and cleanup
- Storage statistics per tenant

### ✅ Async Processing
- **Kafka**: Event streaming for real-time data processing
  - Event topics: tenant.created, document.uploaded, etc.
  - Background worker for event consumption
- **Celery**: Distributed task queue for scheduled jobs
  - SSO token refresh (automatic renewal before expiry)
  - Expired token cleanup
  - Encryption key rotation
  - Scheduled maintenance tasks
- **Flower**: Real-time monitoring dashboard for Celery tasks

- *** ✅ celery-worker-sso : Exécute les tâches de rafraîchissement
- *** ✅ celery-beat : Schedule les tâches périodiques
- *** ✅ flower : Dashboard de monitoring (http://localhost:5555)


### ✅ API Features
- RESTful API design
- OpenAPI 3.0 specification (Swagger)
- Standardized response formats
- Comprehensive error handling
- Request validation with Marshmallow schemas
- CORS support

### ✅ Security
- JWT-based authentication
- Password strength validation
- Azure AD / Microsoft Entra ID SSO support
- Multi-factor authentication (via Azure AD)
- Rate limiting (configurable)
- SQL injection prevention (SQLAlchemy ORM)
- XSS protection
- HTTPS/TLS support (production)

### ✅ DevOps Ready
- Docker and Docker Compose support
- Multi-stage Docker builds
- Health check endpoints
- Logging and monitoring hooks
- Environment-based configuration
- Database migration system

## SaaS Backend for Industry 4.0

This platform is specifically designed to support the development of backend systems for Industry 4.0 SaaS applications. As of today, it provides:

- **Mobile Application Foundation**: Serves as the backbone for modern mobile and web applications in industrial contexts
- **Flexible Cloud Deployment**: Can be hosted on French sovereign cloud, European cloud providers, or GAFAM platforms (AWS, Azure, GCP)
- **Multi-Tenant Architecture**: Complete data and file isolation between tenants for maximum security and compliance
- **Enterprise Security Standards**: Uses HashiCorp Vault for secrets management and data encryption at rest and in transit
- **Enterprise SSO Integration**: Seamlessly integrates with Microsoft Entra ID (Azure SSO) for enterprise authentication
- **Comprehensive API Documentation**: Fully documented RESTful APIs with OpenAPI/Swagger specification

A production-ready, scalable multi-tenant SaaS backend platform built with Flask, PostgreSQL, Kafka, and S3 storage. Features isolated tenant databases, JWT authentication, asynchronous document processing, and RESTful APIs.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Flask 3.0](https://img.shields.io/badge/flask-3.0-green.svg)](https://flask.palletsprojects.com/)
[![PostgreSQL 14+](https://img.shields.io/badge/postgresql-14+-blue.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start avec Docker (Recommended)](#quick-start)
- [Installation Sans Docker](#installation)
- [Environment Variables](#environment-variables)
- [HashiCorp Vault Integration](#hashicorp-vault-integration)
- [Database Migrations](#database-migrations)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

---


---

## Project Overview

This platform provides a complete SaaS backend solution with the following capabilities:

- **Multi-Tenant Architecture**: Each tenant (organization) gets an isolated PostgreSQL database for data isolation and security
- **User Management**: User registration, authentication, and profile management with JWT tokens
- **Tenant Management**: Create organizations, manage members with role-based access control (admin, user, viewer)
- **Document Management**: Upload, store, and manage documents with MD5-based deduplication
- **File Storage**: S3-compatible storage (MinIO) with sharded path strategy for efficient file organization
- **Async Processing**: Kafka-based message queue for asynchronous event processing
- **RESTful APIs**: Well-documented REST APIs with OpenAPI/Swagger specification

### Use Cases

- SaaS applications requiring data isolation per customer
- Document management systems with multi-tenant support
- Enterprise applications with organization-based access control
- B2B platforms with separate data domains per client

---

## Industry 4.0 Target Functionalities

This platform is designed as a foundation to support advanced Industry 4.0 capabilities. The following functionalities represent the strategic roadmap for industrial IoT and smart manufacturing applications:

### A) Connectivity and Massive Data Ingestion (Big Data)

**IoT Integration**:
- Receive and process high-throughput real-time data streams from thousands of sensors, equipment, and industrial systems
- Support for industrial protocols: MQTT, OPC-UA, Modbus, SCADA systems
- Integration with ERP, MES (Manufacturing Execution Systems), and CMMS (Computerized Maintenance Management Systems)

**Robust Gateways/APIs**:
- Secure interfaces for bidirectional integration with on-premise client systems
- Edge computing support for data preprocessing at the source
- Protocol translation and data normalization layers

**Scalable Storage**:
- Manage exponentially growing data volumes with high availability
- Time-series database optimization for sensor data
- Hot/Cold storage strategies for cost optimization

### B) Intelligence and Advanced Analytics (AI/ML)

**Analytics Engine**:
- Implement Artificial Intelligence and Machine Learning algorithms for data analysis
- Real-time stream processing with Apache Kafka
- Batch processing for historical data analysis

**Predictive Maintenance**:
- Detect and predict equipment anomalies and failures
- Quality drift detection and alerting
- Remaining Useful Life (RUL) estimation
- Root cause analysis automation

**Real-Time Optimization**:
- Calculate and prescribe actions (e.g., energy efficiency optimization, production adjustments)
- Closed-loop control integration to reinject decisions into operational systems
- Digital twin synchronization for simulation and optimization

### C) Security and Compliance

**Industrial Security (OT)**:
- Ensure security of critical data and operational technology systems
- Identity and Access Management (IAM) for industrial environments
- Network segmentation and zero-trust architecture
- Compliance with IEC 62443 industrial security standards

**Traceability and Audit**:
- Log all operations with immutable audit trails
- Compliance with industrial standards and regulations (ISO 50001, ISO 9001, ISO 27001)
- ESG (Environmental, Social, Governance) reporting capabilities
- GDPR, HIPAA, and sector-specific compliance support

### D) Platform Management (SaaS)

**Multi-Tenancy** (✅ Currently Implemented):
- Complete data isolation for multiple clients on shared infrastructure
- Per-tenant customization and configuration
- Tenant-specific database schemas for regulatory compliance

**Scalability** (✅ Currently Implemented):
- Rapid scaling of compute and storage capacity based on load
- Cloud-native architecture with Kubernetes support
- Elastic resource allocation

**DevOps/SRE Operations** (✅ Currently Implemented):
- Continuous Integration/Continuous Deployment (CI/CD) pipelines
- Infrastructure as Code (IaC) with Docker and Docker Compose
- Monitoring, alerting, and observability (ready for Prometheus, Grafana)
- High availability and disaster recovery strategies

### Current Implementation Status

| Category | Capability | Status |
|----------|-----------|--------|
| **Foundation** | Multi-tenant architecture | ✅ Production-ready |
| | User authentication & RBAC | ✅ Production-ready |
| | Azure AD SSO integration | ✅ Production-ready |
| | RESTful API with documentation | ✅ Production-ready |
| | Vault secrets management | ✅ Production-ready |
| | File storage with S3 | ✅ Production-ready |
| **Async Processing** | Kafka event streaming | ✅ Production-ready |
| | Celery task queue | ✅ Production-ready |
| | Background workers | ✅ Production-ready |
| **IoT & Big Data** | High-throughput data ingestion | 🚧 Roadmap |
| | Time-series database | 🚧 Roadmap |
| | Industrial protocol support | 🚧 Roadmap |
| **AI/ML** | Predictive maintenance | 🚧 Roadmap |
| | Real-time analytics | 🚧 Roadmap |
| | Digital twin integration | 🚧 Roadmap |
| **Advanced Features** | Edge computing gateway | 🚧 Roadmap |
| | Closed-loop control | 🚧 Roadmap |
| | ESG reporting | 🚧 Roadmap |

**Legend**:
- ✅ Production-ready: Implemented and tested
- 🚧 Roadmap: Planned for future releases

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Client Layer                           │
│                     (Web/Mobile/Desktop)                        │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS/REST
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Load Balancer / CDN                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Flask API Server (Gunicorn)                  │
│  ┌─────────────┐  ┌────────────────┐  ┌─────────────────────┐   │
│  │   Routes    │→ │   Services     │→ │  Models/Schemas     │   │
│  │ (REST APIs) │  │(Business Logic)│  │  (Validation)       │   │
│  └─────────────┘  └────────────────┘  └─────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┬────────────────┐
         │                   │                   │                │
         ▼                   ▼                   ▼                ▼
┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐  ┌───────────────┐
│   PostgreSQL    │  │    Kafka     │  │  MinIO (S3)     │  │HashiCorp Vault│
│                 │  │              │  │                 │  │               │
│  Main Database: │  │  Message     │  │  File Storage:  │  │Secrets Mgmt:  │
│  - Users        │  │  Broker:     │  │  - Documents    │  │  - DB Creds   │
│  - Tenants      │  │  - Events    │  │  - Uploads      │  │  - JWT Keys   │
│  - Associations │  │  - Async Jobs│  │  - Backups      │  │  - S3 Keys    │
│                 │  │              │  │                 │  │  - Encryption │
│  Tenant DBs:    │  └──────┬───────┘  └─────────────────┘  │  - Audit Log  │
│  - Documents    │         │                               └───────────────┘
│  - Files        │         │         ┌───────────────────┐
│  (Isolated)     │         │         │     Redis         │
└─────────────────┘         │         │                   │
                            │         │  Cache & Session  │
                     ┌──────▼───────┐ │  - Token Blacklist│
                     │Kafka Consumer│ │  - SSO Sessions   │
                     │   Worker     │ │  - API Cache      │
                     │ (Background) │ └───────────────────┘
                     └──────────────┘
```

### Multi-Tenant Database Strategy

Each tenant has an isolated PostgreSQL database:

- **Main Database** (`saas_platform`): Stores users, tenants, and user-tenant associations
- **Tenant Databases** (`tenant_<name>_<uuid>`): Each tenant gets a separate database for documents and files

This approach provides:
- **Strong Data Isolation**: Complete database separation per tenant
- **Security**: No risk of cross-tenant data leakage
- **Scalability**: Easy to scale individual tenant databases
- **Compliance**: Meets strict data isolation requirements (GDPR, HIPAA, etc.)

---

## Tech Stack

### Backend Framework
- **Flask 3.0**: Lightweight Python web framework
- **Gunicorn 21.2**: Production WSGI HTTP server
- **SQLAlchemy 2.0**: SQL toolkit and ORM
- **Flask-Migrate 4.0**: Database migration management (Alembic)

### Authentication & Security
- **Flask-JWT-Extended 4.6**: JWT token management
- **bcrypt 4.1**: Password hashing
- **cryptography 42.0**: Encryption utilities
- **HashiCorp Vault**: Centralized secrets management and encryption

### Database
- **PostgreSQL 14+**: Primary database (multi-database support)
- **psycopg2-binary 2.9**: PostgreSQL adapter

### Cache & Session Store
- **Redis 7.0**: High-performance cache and session store
- **redis-py 5.0**: Python Redis client
- Token blacklist storage with TTL
- SSO session management
- API response caching (planned)

### Message Queue & Task Processing
- **Apache Kafka**: Event streaming and async processing
- **kafka-python 2.0**: Python Kafka client
- **Zookeeper**: Kafka coordination
- **Celery 5.3**: Distributed task queue for scheduled jobs
- **Flower 2.0**: Real-time Celery monitoring dashboard

### Object Storage
- **MinIO**: S3-compatible object storage
- **boto3 1.34**: AWS SDK for Python (S3 client)

### Data Validation
- **marshmallow 3.20**: Object serialization and validation
- **marshmallow-sqlalchemy**: SQLAlchemy integration

### Development Tools
- **pytest 7.4**: Testing framework
- **black 24.1**: Code formatter
- **flake8 7.0**: Linting
- **mypy 1.8**: Static type checking

### Containerization
- **Docker 20.10+**: Containerization
- **Docker Compose 2.0+**: Multi-container orchestration

---

## Prerequisites

### For Docker Deployment (Recommended)
- **Docker**: 20.10 or higher
- **Docker Compose**: 2.0 or higher
- **System Requirements**: 4GB RAM minimum
- **Ports**: 4999, 5432, 6379, 9000, 9001, 9092, 9093 available

### For Local Development
- **Python**: 3.11 or higher
- **PostgreSQL**: 14 or higher
- **Redis**: 7.0 or higher
- **Kafka**: 3.0+ with Zookeeper
- **MinIO**: Latest version (or AWS S3 account)
- **virtualenv**: For Python virtual environment

---

## Quick Start

Get the platform running in 5 minutes with Docker. **Choose your setup:**


- **Approach A: With Vault** - See [Quick Start - Option A](#option-a-with-hashicorp-vault-recommended-for-production-like-setup) for detailed setup
- **Approach B: Without Vault** - See [Quick Start - Option B](#option-b-without-vault-simple-setup-for-development) for simple development setup


### Option A: With HashiCorp Vault (Recommended for Production-like Setup)

**Why use Vault?** Centralized secrets management, encryption at rest/transit, audit logging, and automatic rotation.

```bash
# ============================================================================
# ÉTAPE 1: Configuration initiale
# ============================================================================

# 1.1. Clone the repository
git clone https://github.com/your-org/SaaSBackendWithClaude.git
cd SaaSBackendWithClaude

# 1.2. Copy minimal environment file (NO SECRETS - configuration only)
cp .env.docker.minimal .env
# Note: Secrets will be managed by Vault, NOT by .env file

# 1.3. Create secrets file for Vault (OBLIGATOIRE)
# Les scripts Vault sont déjà dans le repo (vault/config/, vault/scripts/)
mkdir -p docker/volumes/vault/init-data/
cat > docker/volumes/vault/init-data/docker.env <<'EOF'
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/saas_platform
TENANT_DATABASE_URL_TEMPLATE=postgresql://postgres:postgres@postgres:5432/{database_name}
JWT_SECRET_KEY=$(head -c 32 /dev/urandom | xxd -p -c 64)
JWT_ACCESS_TOKEN_EXPIRES=900
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents
S3_REGION=us-east-1
EOF

# ============================================================================
# ÉTAPE 2: Démarrage de Vault avec auto-unseal
# ============================================================================

# 2.0. (Optional) Réinitialisation complète de Vault
# ⚠️  ATTENTION: Cette opération supprime TOUTES les données Vault !
# Utilisez ceci uniquement si vous voulez recommencer à zéro
rm -Rf docker/volumes/vault/data
docker-compose down vault vault-unseal
docker volume rm saasbackendwithclaude_vault_data 2>/dev/null || true

# 2.1. Start Vault and auto-unseal services
docker-compose up -d vault vault-unseal

# 2.2. Wait for Vault to initialize and unseal (30 secondes environ)
sleep 30
docker logs saas-vault-unseal

# 2.3. Verify Vault is unsealed and ready
docker exec saas-vault vault status
# Expected: "Sealed: false"

# 2.4. IMPORTANT: Sauvegarder le token root (première fois seulement)
cat docker/volumes/vault/data/root-token.txt
# ⚠️  Sauvegarder ce token dans un gestionnaire de mots de passe !

# ============================================================================
# ÉTAPE 3: Initialisation des secrets dans Vault
# ============================================================================

# 3.1. Start vault-init service to inject secrets
docker-compose up -d vault-init

# 3.2. Wait for initialization (20 secondes environ)
sleep 20
docker logs saas-vault-init

# 3.3. Verify AppRole credentials were created
cat .env.vault
# Ce fichier contient VAULT_ROLE_ID et VAULT_SECRET_ID

# 3.4. (Optional) Verify secrets are stored in Vault
VAULT_TOKEN=$(cat docker/volumes/vault/data/root-token.txt)
docker exec -e VAULT_TOKEN=$VAULT_TOKEN saas-vault vault kv get secret/saas-project/docker/database

# ============================================================================
# ÉTAPE 4: Démarrage de l'application
# ============================================================================

# 4.1. Start all remaining services (API, Worker, PostgreSQL, Kafka, MinIO)
docker-compose up -d

# 4.2. Wait for services to be healthy (30 secondes environ)
sleep 30
docker-compose ps

# ============================================================================
# ÉTAPE 5: Initialisation de la base de données
# ============================================================================

# 5.0. (IMPORTANT) Remove old migration files if any exist
rm -f backend/migrations/versions/*

# 5.1. Create main database
docker-compose exec postgres psql -U postgres -c "CREATE DATABASE saas_platform;"

# 5.2. migration initiale
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Initial migration"

# 5.3. Run database migrations (using Vault secrets)
docker-compose exec api /app/flask-wrapper.sh db upgrade

# 5.4. Create admin user and test tenant
docker-compose exec api python scripts/init_db.py --create-admin --create-test-tenant

# 5.5. (Optional) Migrate tenant databases if needed
docker-compose exec api python scripts/migrate_all_tenants.py

# ============================================================================
# ÉTAPE 6: Vérification
# ============================================================================

# 6.1. Check API health
curl http://localhost:4999/health

# 6.2. View application logs
docker-compose logs -f api

# 6.3. Check all services status
docker-compose ps
```

**Default Admin Credentials** (change immediately!):
- Email: `admin@example.com`
- Password: `12345678`

**Access Services:**
- **API Server**: http://localhost:4999
- **API Documentation (Swagger)**: http://localhost:4999/api/docs
- **Vault UI**: http://localhost:8201/ui (use token from `vault/data/root-token.txt`)
  - Note: Port 8201 is used instead of the default 8200 to avoid conflicts with OneDrive on macOS
- **MinIO Console**: http://localhost:9001 (minioadmin / minioadmin)
- **Flower (Celery Monitor)**: http://localhost:5555 (real-time task monitoring)
- **PostgreSQL**: localhost:5432 (postgres / postgres)
- **Redis**: localhost:6379 (no authentication in dev)
- **Kafka**: localhost:9092

**Important Vault Files** (NE JAMAIS COMMITER):
- `vault/data/unseal-keys.json` - Clés pour déverrouiller Vault
- `vault/data/root-token.txt` - Token administrateur Vault
- `.env.vault` - Credentials AppRole pour l'application
- `vault/init-data/docker.env` - Secrets injectés dans Vault

**Au prochain redémarrage:**
```bash
# Tout redémarre automatiquement avec docker-compose up -d
docker-compose up -d

# Vault se déverrouille automatiquement (vault-unseal)
# Les secrets ne sont PAS réinjectés (vault-init est idempotent)
# L'application récupère automatiquement les secrets depuis Vault
```

**Notes importantes:**
- **vault-unseal** : S'exécute à chaque démarrage et déverrouille Vault automatiquement
- **vault-init** : S'exécute aussi mais ne modifie RIEN si les secrets existent déjà (idempotent)
- **Secrets protégés** : Les secrets ne seront jamais écrasés accidentellement

**Pour plus de détails sur Vault, consultez:**
- [specs/vault/plan-vault.md](specs/vault/plan-vault.md) - Plan complet d'intégration Vault

---

### Option B: Without Vault (Simple Setup for Development)

**When to use?** Quick local development, testing, or when you don't need enterprise-grade secrets management.

**⚠️ WARNING**: This approach stores secrets in `.env` file. Never commit this file or use in production!

```bash
# ============================================================================
# ÉTAPE 1: Configuration initiale
# ============================================================================

# 1.1. Clone the repository
git clone https://github.com/your-org/SaaSBackendWithClaude.git
cd SaaSBackendWithClaude

# 1.2. Copy environment file WITH secrets (for development only)
cp .env.docker .env

# 1.3. (Optional) Generate secure JWT secret
# Replace the JWT_SECRET_KEY in .env with this:
python -c "import secrets; print(secrets.token_urlsafe(64))"

# ============================================================================
# ÉTAPE 2: Démarrage des services
# ============================================================================

# 2.1. Start all services (excluding Vault services)
# The application will use secrets from .env file instead of Vault
docker-compose up -d postgres kafka zookeeper minio redis api worker celery-worker-sso celery-beat flower

# 2.2. Wait for services to be healthy (30 secondes environ)
sleep 30
docker-compose ps

# ============================================================================
# ÉTAPE 3: Initialisation de la base de données
# ============================================================================

# 3.0. (IMPORTANT) Remove old migration files if any exist
rm -f backend/migrations/versions/*

# 3.1. Create main database
docker-compose exec postgres psql -U postgres -c "CREATE DATABASE saas_platform;"

# 3.2. Run database migrations
docker-compose exec api flask db upgrade

# 3.3. Create admin user and test tenant
docker-compose exec api python scripts/init_db.py --create-admin --create-test-tenant

# ============================================================================
# ÉTAPE 4: Vérification
# ============================================================================

# 4.1. Check API health
curl http://localhost:4999/health

# 4.2. View application logs
docker-compose logs -f api

# 4.3. Check all services status
docker-compose ps
```

**Default Admin Credentials** (change immediately!):
- Email: `admin@example.com`
- Password: `12345678`

**Access Services:**
- **API Server**: http://localhost:4999
- **API Documentation (Swagger)**: http://localhost:4999/api/docs
- **MinIO Console**: http://localhost:9001 (minioadmin / minioadmin)
- **Flower (Celery Monitor)**: http://localhost:5555 (real-time task monitoring)
- **PostgreSQL**: localhost:5432 (postgres / postgres)
- **Redis**: localhost:6379 (no authentication in dev)
- **Kafka**: localhost:9092

**Important Security Notes:**
- `.env` file contains sensitive secrets - never commit it to Git
- Change default passwords before any real use
- Use Option A (Vault) for production or production-like environments

---

## Installation


### Local Development

For development without Docker:

#### 1. Clone Repository

```bash
git clone https://github.com/your-org/SaaSBackendWithClaude.git
cd SaaSBackendWithClaude
```

#### 2. Set Up Python Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/macOS
# OR
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r backend/requirements.txt
```

#### 3. Install and Configure PostgreSQL

```bash
# Install PostgreSQL (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install postgresql-14 postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create main database
sudo -u postgres psql -c "CREATE DATABASE saas_platform;"

# Create PostgreSQL user (optional, for security)
sudo -u postgres psql -c "CREATE USER saas_user WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE saas_platform TO saas_user;"
```

#### 4. Install and Configure Redis

```bash
# Install Redis (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install redis-server

# Start Redis service
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify Redis is running
redis-cli ping
# Should return: PONG
```

#### 5. Install and Configure Kafka

```bash
# Download Kafka (adjust version as needed)
wget https://downloads.apache.org/kafka/3.6.0/kafka_2.13-3.6.0.tgz
tar -xzf kafka_2.13-3.6.0.tgz
cd kafka_2.13-3.6.0

# Start Zookeeper (Terminal 1)
bin/zookeeper-server-start.sh config/zookeeper.properties

# Start Kafka (Terminal 2)
bin/kafka-server-start.sh config/server.properties
```

#### 6. Install and Configure MinIO

```bash
# Download MinIO (Linux)
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio

# Start MinIO
./minio server /mnt/data --console-address ":9001"

# Access MinIO Console at http://localhost:9001
# Default credentials: minioadmin / minioadmin

# Create bucket using mc client
wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc
./mc alias set myminio http://localhost:9000 minioadmin minioadmin
./mc mb myminio/saas-documents
```

#### 7. Configure Environment

```bash
# Copy development environment file
cp .env.development .env

# Edit .env with your local configuration
nano .env

# Important: Update these values
# - JWT_SECRET_KEY (generate with: python -c "import secrets; print(secrets.token_urlsafe(64))")
# - DATABASE_URL (postgresql://user:password@localhost:5432/saas_platform)
# - REDIS_URL (redis://localhost:6379/0)
# - KAFKA_BOOTSTRAP_SERVERS (localhost:9092)
# - S3_ENDPOINT_URL (http://localhost:9000)
```

#### 8. Initialize Database

```bash
# Navigate to backend directory
cd backend

# Run database initialization
python scripts/init_db.py --create-admin --create-test-tenant

# Follow prompts to create admin user
```

#### 9. Run Development Server

```bash
# Start Flask development server
python run.py

# Or use Gunicorn for production-like environment
gunicorn -w 4 -b 0.0.0.0:4999 run:app
```

#### 10. Run Kafka Consumer Worker (Separate Terminal)

```bash
# Activate virtual environment
source venv/bin/activate

# Navigate to backend directory
cd backend

# Run Kafka consumer
python -m app.worker.consumer
```

#### 11. Verify Installation

```bash
# Test API
curl http://localhost:4999/health

# Test authentication
curl -X POST http://localhost:4999/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"12345678"}'
```

---

## Azure SSO Configuration

The platform supports **Azure AD / Microsoft Entra ID** Single Sign-On (SSO) for enterprise authentication. Each tenant can independently configure SSO.

### Setting up Azure AD Application

1. **Register an Application in Azure AD**:
   ```bash
   # In Azure Portal (portal.azure.com):
   1. Go to Azure Active Directory → App registrations → New registration
   2. Name: "Your SaaS Platform"
   3. Supported account types: "Accounts in this organizational directory only"
   4. Redirect URI:
      - Type: Web
      - URI: http://localhost:4999/api/auth/sso/azure/callback (development)
      - URI: https://yourapp.com/api/auth/sso/azure/callback (production)
   5. Register the application
   ```

2. **Configure the Azure Application (Confidential Mode)**:
   ```bash
   # In Azure App Registration:
   1. Authentication tab:
      - ⚠️ IMPORTANT: Do NOT enable "Public client flows"
      - Add redirect URIs for all environments
      - Enable ID tokens and Access tokens

   2. Certificates & secrets tab:
      - ⚠️ CRITICAL: Click "New client secret"
      - Description: "SaaS Platform Secret"
      - Expiration: Choose appropriate duration (12-24 months)
      - Copy the secret value immediately (shown only once!)

   3. API Permissions tab:
      - Microsoft Graph → User.Read (default)
      - Microsoft Graph → email (optional)
      - Microsoft Graph → profile (optional)
      - Grant admin consent if required

   4. Copy these values:
      - Application (client) ID
      - Directory (tenant) ID
      - Client secret (from step 2)
   ```

### Configuring SSO for a Tenant

1. **Create SSO Configuration via API**:
   ```bash
   # As tenant admin, configure SSO:
   # ⚠️ IMPORTANT: client_secret is REQUIRED
   curl -X POST http://localhost:4999/api/tenants/{tenant_id}/sso/config \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "client_id": "your-azure-app-client-id",
       "client_secret": "your-azure-client-secret",
       "provider_tenant_id": "your-azure-tenant-id",
       "enable": true,
       "config_metadata": {
         "auto_provisioning": {
           "enabled": true,
           "default_role": "viewer",
           "sync_attributes_on_login": true,
           "allowed_email_domains": ["@yourcompany.com"],
           "allowed_azure_groups": ["All-Employees"],
           "group_role_mapping": {
             "IT-Admins": "admin",
             "Developers": "user",
             "Support": "viewer"
           }
         }
       }
     }'
   ```

2. **Set Authentication Mode**:
   ```bash
   # Enable SSO for the tenant:
   curl -X POST http://localhost:4999/api/tenants/{tenant_id}/sso/config/enable \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "auth_method": "both"  # Options: "sso", "local", "both"
     }'
   ```

### SSO Login Flow

1. **Initiate SSO Login**:
   ```javascript
   // Frontend redirects user to SSO login:
   window.location.href = `${API_URL}/api/auth/sso/azure/login/${tenantId}`;
   ```

2. **Handle Callback**:
   ```javascript
   // After Azure AD authentication, user returns with tokens:
   // GET /api/auth/sso/azure/callback?code=...&state=...

   // Response includes JWT tokens:
   {
     "access_token": "eyJ...",
     "refresh_token": "eyJ...",
     "user": {
       "id": "user-uuid",
       "email": "user@company.com",
       "first_name": "John",
       "last_name": "Doe"
     }
   }
   ```

### Auto-Provisioning Configuration

The platform can automatically create user accounts during SSO login:

```json
{
  "auto_provisioning": {
    "enabled": true,
    "default_role": "viewer",
    "sync_attributes_on_login": true,
    "allowed_email_domains": ["@company.com", "@partner.com"],
    "allowed_azure_groups": ["All-Employees", "Contractors"],
    "group_role_mapping": {
      "IT-Admins": "admin",
      "Developers": "user",
      "Support": "viewer",
      "Contractors": "viewer"
    }
  }
}
```

### Security Features

- **Confidential Application Mode**: MANDATORY use of client_secret for secure OAuth2 flow
- **Client Secret Required**: Application configured as confidential (NOT public client)
- **NO PKCE**: Platform does NOT use Proof Key for Code Exchange (PKCE is for public clients only)
- **State Token**: CSRF protection during OAuth flow
- **Encrypted Token Storage**: Azure tokens encrypted via HashiCorp Vault
- **Token Refresh**: Automatic token refresh before expiration via Celery workers
- **Multi-Factor Authentication**: Inherited from Azure AD configuration

### SSO Management Endpoints

```bash
# Configuration Management
GET    /api/tenants/{id}/sso/config          # Get current configuration
POST   /api/tenants/{id}/sso/config          # Create configuration
PUT    /api/tenants/{id}/sso/config          # Update configuration
DELETE /api/tenants/{id}/sso/config          # Remove configuration

# Enable/Disable SSO
POST   /api/tenants/{id}/sso/config/enable   # Enable SSO
POST   /api/tenants/{id}/sso/config/disable  # Disable SSO
GET    /api/tenants/{id}/sso/config/validate # Validate configuration

# Authentication Flow
GET    /api/auth/sso/azure/login/{tenant_id}       # Initiate login
GET    /api/auth/sso/azure/callback                # OAuth callback
POST   /api/auth/sso/azure/refresh                 # Refresh tokens
POST   /api/auth/sso/azure/logout/{tenant_id}      # SSO logout

# User Information
GET    /api/auth/sso/azure/user-info              # Get Azure profile
GET    /api/auth/sso/identities                   # List user's Azure identities
GET    /api/auth/sso/check-availability/{tenant_id} # Check SSO status

# Statistics
GET    /api/tenants/{id}/sso/statistics           # SSO usage stats
```

### Testing SSO Integration

A test script is provided to verify SSO configuration:

```bash
# Run the SSO setup test:
cd backend
python scripts/setup_sso_test.py

# The script will:
# 1. Create a test tenant with SSO configuration
# 2. Display the Azure AD login URL
# 3. Guide you through the authentication flow
# 4. Verify token exchange and user provisioning
```

### Troubleshooting SSO

Common issues and solutions:

1. **"redirect_uri_mismatch" error**:
   - Ensure the callback URL in Azure AD matches exactly
   - Check for trailing slashes and protocol (http vs https)

2. **"invalid_client" error**:
   - Verify the client_id is correct
   - Ensure client_secret is provided and valid
   - Check that "Public client flows" is DISABLED (we use confidential mode)

3. **Auto-provisioning not working**:
   - Check email domain is in allowed list
   - Verify Azure AD group membership
   - Ensure tenant has auto_provisioning enabled

4. **Token refresh failing**:
   - Check if refresh token has expired (90 days)
   - Verify Azure AD app permissions haven't changed

---

## Environment Variables

The platform uses environment variables for configuration. Three environment files are provided:

### `.env.development` - Local Development
Safe defaults for local development with localhost services.

### `.env.docker` - Docker Compose
Configuration for containerized deployment with service discovery.

### `.env.production` - Production Template
Security-hardened template with checklists and placeholders.

### Key Variables

#### Flask Configuration
```bash
FLASK_APP=run.py                    # Flask application entry point
FLASK_ENV=development               # Environment: development/production
FLASK_DEBUG=1                       # Debug mode: 1=enabled, 0=disabled
FLASK_PORT=4999                     # Server port
SECRET_KEY=your-secret-key          # Flask secret key (change in production!)
```

#### Database Configuration
```bash
# Main database for users and tenants
DATABASE_URL=postgresql://user:password@host:5432/saas_platform

# Tenant database template (dynamic substitution)
TENANT_DATABASE_URL_TEMPLATE=postgresql://user:password@host:5432/{database_name}

# Connection pooling
DATABASE_POOL_SIZE=10               # Connection pool size
DATABASE_POOL_TIMEOUT=30            # Pool timeout in seconds
DATABASE_MAX_OVERFLOW=20            # Max overflow connections
```

#### JWT Configuration
```bash
JWT_SECRET_KEY=your-jwt-secret      # CRITICAL: Generate secure key!
JWT_ACCESS_TOKEN_EXPIRES=900        # Access token expiry (15 minutes)
JWT_REFRESH_TOKEN_EXPIRES=604800   # Refresh token expiry (7 days)
JWT_ALGORITHM=HS256                 # JWT signing algorithm
```

#### Kafka Configuration
```bash
KAFKA_BOOTSTRAP_SERVERS=kafka:9092         # Kafka broker address
KAFKA_CLIENT_ID=saas-platform              # Client identifier
KAFKA_CONSUMER_GROUP_ID=saas-consumer-group # Consumer group
KAFKA_AUTO_OFFSET_RESET=earliest           # Offset reset strategy
KAFKA_ENABLE_AUTO_COMMIT=true              # Auto-commit offsets
KAFKA_MAX_POLL_RECORDS=100                 # Max records per poll
```

#### S3/MinIO Configuration
```bash
S3_ENDPOINT_URL=http://minio:9000   # S3 endpoint (blank for AWS S3)
S3_ACCESS_KEY_ID=minioadmin         # Access key
S3_SECRET_ACCESS_KEY=minioadmin     # Secret key
S3_BUCKET=saas-documents            # Bucket name
S3_REGION=us-east-1                 # Region
S3_USE_SSL=false                    # Use SSL/TLS (true for production)
```

#### Redis Configuration
```bash
REDIS_URL=redis://redis:6379/0      # Redis connection URL
REDIS_MAX_CONNECTIONS=20            # Maximum connection pool size
REDIS_DECODE_RESPONSES=true         # Auto-decode responses to strings
REDIS_TOKEN_BLACKLIST_EXPIRE=86400  # Token blacklist TTL (24 hours)
REDIS_SESSION_EXPIRE=600            # SSO session TTL (10 minutes)
```

#### CORS Configuration
```bash
CORS_ORIGINS=http://localhost:3000,http://localhost:4999
CORS_SUPPORTS_CREDENTIALS=true
CORS_MAX_AGE=3600
```

#### Logging Configuration
```bash
LOG_LEVEL=DEBUG                     # Logging level: DEBUG/INFO/WARNING/ERROR
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
LOG_FILE=logs/app.log              # Log file path
```

### Security Best Practices

**NEVER commit `.env` files with actual credentials to version control!**

1. **Generate Strong Secrets**:
   ```bash
   # JWT Secret (64 characters)
   python -c "import secrets; print(secrets.token_urlsafe(64))"

   # Database Password (32 characters)
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Use Environment-Specific Files**:
   - Development: `.env.development`
   - Production: `.env.production` (never commit with real values!)

3. **Enable SSL/TLS in Production**:
   - Set `S3_USE_SSL=true`
   - Use `sslmode=require` in `DATABASE_URL`
   - Configure HTTPS for API server

4. **Restrict CORS Origins**:
   - Development: Allow localhost
   - Production: Only allow production domains

---

## HashiCorp Vault Integration

The platform supports **HashiCorp Vault** for centralized, secure secrets management as an alternative to environment variables.

### Vault Features

- **Centralized Secrets**: All secrets stored in one secure location
- **Audit Logging**: Track all secret access and modifications
- **Dynamic Rotation**: Automatically rotate secrets without downtime
- **Encryption**: Secrets encrypted at rest and in transit
- **Access Control**: Fine-grained policies for secret access

### Vault Setup with Docker

The platform includes Vault as an optional service in Docker Compose:

```bash
# Start all services including Vault
docker-compose up -d

# Vault will be available at http://localhost:8201
# Default token (dev mode): root-token
```

### Storing Secrets in Vault

```bash
# Initialize secrets in Vault (run once)
docker-compose exec vault sh -c '
  vault kv put secret/saas-platform \
    jwt_secret="$(head -c 32 /dev/urandom | xxd -p -c 64)" \
    db_password="secure_password_here" \
    db_user="postgres" \
    aws_access_key="AKIA..." \
    aws_secret="secret_key_here"
'

# View stored secrets
docker-compose exec vault vault kv get secret/saas-platform

# Update a specific secret
docker-compose exec vault vault kv patch secret/saas-platform \
  jwt_secret="new_secret_value"
```

### Using Vault with Flask Commands

**Important**: When using Vault, Flask commands in Docker must use the wrapper script `/app/flask-wrapper.sh`:

```bash
# Database migrations with Vault
docker-compose exec api /app/flask-wrapper.sh db upgrade

# Create new migration with Vault
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Add new field"

# Any Flask command with Vault secrets
docker-compose exec api /app/flask-wrapper.sh <command>
```

The wrapper script automatically:
1. Connects to Vault
2. Retrieves secrets
3. Sets them as environment variables
4. Executes the Flask command

### Migrating from .env to Vault

If you have existing `.env` files, you can migrate them to Vault:

```bash
# Use the migration script
./backend/scripts/migrate_to_vault.sh

# Or manually migrate specific secrets
docker-compose exec vault vault kv put secret/saas-platform \
  jwt_secret="$JWT_SECRET_KEY" \
  db_password="$DATABASE_PASSWORD"
```

### Vault in Production

For production deployments:

1. **Use Production Mode**: Don't use dev mode
   ```yaml
   vault:
     command: server  # Remove -dev flag
   ```

2. **Configure Storage Backend**: Use Consul, etcd, or integrated storage
3. **Enable TLS**: Secure all Vault communications
4. **Use AppRole Authentication**: Instead of root tokens
5. **Set Up Policies**: Restrict access to specific paths
6. **Enable Audit Logging**: Track all operations
7. **Backup Regularly**: Ensure you can recover secrets

Example production policy:
```hcl
# backend/vault/policies/app-policy.hcl
path "secret/data/saas-platform/*" {
  capabilities = ["read", "list"]
}
```

### Application Integration

The application automatically detects and uses Vault if configured:

```python
# backend/app/config.py
# Automatically tries Vault first, falls back to env vars
if vault_available():
    load_secrets_from_vault()
else:
    load_from_environment()
```

### Vault UI Access

Vault provides a web UI for managing secrets:
- URL: http://localhost:8201/ui
- Token: `root-token` (dev mode)

---

## Database Migrations

The platform uses two different migration systems depending on the tables:

### 1. Main Database Migrations (Alembic)

For the main database tables (User, Tenant, UserTenantAssociation), we use **Flask-Migrate (Alembic)**.

> **IMPORTANT:** The `documents` and `files` tables are **NOT** migrated in the main database. These tables are tenant-specific and only exist in individual tenant databases. The migration system is configured to automatically exclude them from main database migrations via the `include_object` filter in `backend/migrations/env.py`.

#### Initialize Migrations (First Time Only)

```bash
# Navigate to backend directory
cd backend

# Initialize migrations folder
flask db init
```

#### Create Migration

```bash
# Auto-generate migration from model changes
flask db migrate -m "Description of changes"

# Example
flask db migrate -m "Add email verification field to User"
```

#### Apply Migration

```bash
# Upgrade to latest version
flask db upgrade

# Upgrade to specific version
flask db upgrade <revision>

# Downgrade to previous version
flask db downgrade

# Show current version
flask db current

# Show migration history
flask db history
```

#### Docker Migrations avec Vault

**⚠️ IMPORTANT**: Avec l'intégration Vault, utilisez le script wrapper `/app/flask-wrapper.sh` pour toutes les commandes Flask dans Docker :

```bash
# Run migrations in Docker container (avec Vault)
docker-compose exec api /app/flask-wrapper.sh db upgrade

# Create new migration in Docker (avec Vault)
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Add new field"

# Show current migration version
docker-compose exec api /app/flask-wrapper.sh db current

# Show migration history
docker-compose exec api /app/flask-wrapper.sh db history
```

Le script wrapper charge automatiquement les variables d'environnement Vault avant d'exécuter les commandes Flask.

#### Verify Table Exclusion

To verify that `documents` and `files` tables are correctly excluded from the main database:

```bash
# Check main database tables (should NOT include documents/files)
docker-compose exec postgres psql -U postgres -d saas_platform -c "\dt"

# Expected output: Only users, tenants, user_tenant_associations, alembic_version
# NOT documents or files

# When creating a migration, you should see exclusion logs:
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Test migration"
# Expected logs:
# INFO  [alembic.env] Excluding tenant-specific table 'documents' from main database migration
# INFO  [alembic.env] Excluding tenant-specific table 'files' from main database migration
```

If you accidentally have `documents` or `files` tables in the main database (from old migrations), remove them:

```bash
# Remove incorrect tables from main database
docker-compose exec postgres psql -U postgres -d saas_platform -c "DROP TABLE IF EXISTS documents CASCADE;"
docker-compose exec postgres psql -U postgres -d saas_platform -c "DROP TABLE IF EXISTS files CASCADE;"
```

### 2. Tenant-Specific Migrations (Manual)

For tenant-specific tables (File, Document), which are created dynamically in each tenant's database, we use a **custom versioning system**.

#### Why Not Alembic for Tenant Tables?

- Tenant databases are created dynamically when a tenant is created
- Each tenant has isolated File and Document tables
- Alembic doesn't manage these tables in the main database
- We need a system to evolve these schemas across all tenant databases

#### Creating a Tenant Migration

Edit [backend/app/tenant_db/tenant_migrations.py](backend/app/tenant_db/tenant_migrations.py) and add your migration:

```python
from app.tenant_db.tenant_migrations import register_migration
from sqlalchemy import text

@register_migration(2)  # Use next sequential version number
def add_file_metadata_column(db):
    """Ajoute une colonne metadata JSONB à la table files"""
    db.execute(text("""
        ALTER TABLE files
        ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb
    """))

@register_migration(3)
def add_document_version_column(db):
    """Ajoute une colonne version à la table documents"""
    db.execute(text("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1 CHECK (version > 0)
    """))
```

#### Applying Tenant Migrations

**Option 1: Automatic (for new tenants)**
- Migrations are automatically applied when creating a new tenant
- No action needed

**Option 2: Manual (for existing tenants)**

```bash
# Dry-run mode (preview changes without applying)
python backend/scripts/migrate_all_tenants.py --dry-run

# Apply migrations to all tenants
python backend/scripts/migrate_all_tenants.py

# Migrate a specific tenant
python backend/scripts/migrate_all_tenants.py --tenant-id <tenant_id>

# View migration history
python backend/scripts/migrate_all_tenants.py --history
```

**Docker:**
```bash
# Dry-run
docker-compose exec api python scripts/migrate_all_tenants.py --dry-run

# Apply to all tenants
docker-compose exec api python scripts/migrate_all_tenants.py

# View history
docker-compose exec api python scripts/migrate_all_tenants.py --history
```

#### Migration Examples

See [backend/app/tenant_db/tenant_migrations_examples.py](backend/app/tenant_db/tenant_migrations_examples.py) for 13+ examples including:

1. Adding simple columns
2. Adding columns with constraints
3. Creating indexes
4. Adding PostgreSQL arrays
5. Modifying column types
6. Data migrations
7. Creating related tables
8. Soft delete implementation
9. And more...

#### Tenant Migration Best Practices

1. **Always use IF NOT EXISTS**: Migrations must be idempotent
2. **Test in dry-run mode first**: Use `--dry-run` to preview changes
3. **Sequential version numbers**: Use v1, v2, v3... without gaps
4. **Document each migration**: Add clear docstrings
5. **Backup before migrating**: Tenant data is critical
6. **Test on one tenant first**: Use `--tenant-id` to test on a single tenant
7. **Handle failures gracefully**: Failed migrations don't affect other tenants

### Complete Database Reset (Development Only)

**⚠️ WARNING**: This will delete ALL data including all tenant databases!

Use this when you need to completely reset your development environment:
- After deleting the database manually
- When migrations are corrupted or out of sync
- To regenerate migrations from model changes
- To start fresh with a clean slate

```bash
# Option 1: Use automated reset script (recommended)
# IMPORTANT: Run this from the HOST machine, NOT from inside a container
./backend/scripts/reset_db.sh

# Option 2: Manual reset
# Step 1: Drop and recreate database
docker-compose exec postgres psql -U postgres -c "DROP DATABASE IF EXISTS saas_platform;"
docker-compose exec postgres psql -U postgres -c "CREATE DATABASE saas_platform;"

# Step 2: Generate migration from models
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Initial migration"

# Step 3: Apply migration
docker-compose exec api /app/flask-wrapper.sh db upgrade

# Step 4: (Optional) Create admin user and test tenant
docker-compose exec api python scripts/init_db.py --create-admin --create-test-tenant
```

**Note**: The reset script automatically handles:
- Database drop and recreation
- Migration generation from current models
- Table creation
- Excluding tenant-specific models (File, Document) from main database

### Migration Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                     Database Migrations                          │
└─────────────────────────────────────────────────────────────────┘

Main Database (saas_platform)
├── User, Tenant, UserTenantAssociation
├── Managed by: Alembic/Flask-Migrate
├── Location: backend/migrations/versions/
└── Commands: flask db migrate, flask db upgrade

Tenant Databases (tenant_xyz_*)
├── File, Document (per tenant)
├── Managed by: Custom Migration System
├── Location: backend/app/tenant_db/tenant_migrations.py
└── Commands: python scripts/migrate_all_tenants.py
```

### Migration Best Practices

1. **Always Review Auto-Generated Migrations**: Alembic may not capture all changes correctly
2. **Test Migrations**: Test upgrade and downgrade paths before production
3. **Backup Before Migrating**: Always backup databases before running migrations
4. **Version Control**: Commit migration files to Git
5. **Production Migrations**: Use maintenance windows for production migrations
6. **Tenant Migrations**: Always test in dry-run mode first

---

## API Documentation

### Interactive Swagger UI

The API includes an interactive Swagger UI interface for easy exploration and testing:

- **Swagger UI**: http://localhost:4999/api/docs
- **OpenAPI Specification**: http://localhost:4999/api/docs/swagger.yaml
- **API Root**: http://localhost:4999/

The Swagger UI provides:
- Complete endpoint documentation with request/response examples
- Interactive API testing directly from your browser
- JWT authentication support (use the "Authorize" button)
- Schema validation and example payloads
- Download OpenAPI specification

### OpenAPI/Swagger Specification

Complete API documentation is available in OpenAPI 3.0 format:

- **File**: [`swagger.yaml`](swagger.yaml)
- **Format**: OpenAPI 3.0.3
- **Endpoints**: 40+ documented endpoints
- **Schemas**: 20+ reusable components

### API Overview

#### Authentication Endpoints (`/api/auth`)
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - User login (returns JWT tokens)
- `POST /api/auth/refresh` - Refresh access token
- `POST /api/auth/logout` - Logout (blacklist token)

#### User Endpoints (`/api/users`)
- `GET /api/users/me` - Get current user profile
- `PUT /api/users/me` - Update user profile
- `GET /api/users/me/tenants` - Get user's tenants with roles

#### Tenant Endpoints (`/api/tenants`)
- `GET /api/tenants` - List user's tenants
- `POST /api/tenants` - Create new tenant
- `GET /api/tenants/{id}` - Get tenant details with members
- `PUT /api/tenants/{id}` - Update tenant (admin only)
- `DELETE /api/tenants/{id}` - Soft delete tenant (admin only)
- `POST /api/tenants/{id}/users` - Add user to tenant (admin only)
- `DELETE /api/tenants/{id}/users/{user_id}` - Remove user from tenant (admin only)

#### Document Endpoints (`/api/tenants/{tenant_id}/documents`)
- `GET /documents` - List documents (paginated)
- `POST /documents` - Upload document
- `GET /documents/{id}` - Get document details
- `PUT /documents/{id}` - Update document metadata
- `DELETE /documents/{id}` - Delete document
- `GET /documents/{id}/download` - Get download URL

#### File Endpoints (`/api/files/{tenant_id}/files`)
- `GET /files` - List files (paginated, with stats)
- `GET /files/{id}` - Get file details
- `DELETE /files/{id}` - Delete orphaned file (admin only)

### Authentication

All protected endpoints require a JWT access token:

```bash
# Include token in Authorization header
Authorization: Bearer <access_token>
```

### Example API Calls

#### Register User
```bash
curl -X POST http://localhost:4999/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "password": "SecurePass123"
  }'
```

#### Login
```bash
curl -X POST http://localhost:4999/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john.doe@example.com",
    "password": "SecurePass123"
  }'
```

#### Create Tenant
```bash
curl -X POST http://localhost:4999/api/tenants \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "name": "Acme Corp"
  }'
```

#### Upload Document
```bash
curl -X POST http://localhost:4999/api/tenants/<tenant_id>/documents \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/document.pdf"
```

For complete API documentation, see [`swagger.yaml`](swagger.yaml) or use Swagger UI.

---

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/unit/test_auth.py

# Run with verbose output
pytest -v

# Run and show print statements
pytest -s
```

### Test Structure

```
tests/
├── unit/               # Unit tests (isolated, mocked dependencies)
│   ├── test_models.py
│   ├── test_schemas.py
│   └── test_services.py
├── integration/        # Integration tests (with database)
│   ├── test_auth_api.py
│   ├── test_tenants_api.py
│   └── test_documents_api.py
└── conftest.py        # Pytest fixtures and configuration
```

### Writing Tests

```python
# Example unit test
def test_user_password_hashing():
    user = User(email="test@example.com")
    user.set_password("12345678")

    assert user.check_password("12345678") is True
    assert user.check_password("wrongpassword") is False

# Example integration test
def test_register_user(client):
    response = client.post('/api/auth/register', json={
        'first_name': 'John',
        'last_name': 'Doe',
        'email': 'john@example.com',
        'password': 'SecurePass123'
    })

    assert response.status_code == 201
    assert 'user' in response.json
```

### Test Coverage

Aim for 80%+ code coverage. Check coverage report:

```bash
# Generate coverage report
pytest --cov=app --cov-report=html tests/

# Open report in browser
open htmlcov/index.html
```

---

## Project Structure

```
SaaSBackendWithClaude/
├── backend/                      # Backend application
│   ├── app/                      # Main application package
│   │   ├── __init__.py           # App factory
│   │   ├── config.py             # Configuration classes
│   │   ├── extensions.py         # Flask extensions (db, jwt, etc.)
│   │   ├── models/               # SQLAlchemy models
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # Base model with common fields
│   │   │   ├── user.py           # User model
│   │   │   ├── tenant.py         # Tenant model
│   │   │   ├── user_tenant_association.py  # Many-to-many
│   │   │   ├── document.py       # Document model (tenant DB)
│   │   │   └── file.py           # File model (tenant DB)
│   │   ├── schemas/              # Marshmallow schemas
│   │   │   ├── __init__.py
│   │   │   ├── user_schema.py
│   │   │   ├── tenant_schema.py
│   │   │   ├── document_schema.py
│   │   │   └── file_schema.py
│   │   ├── routes/               # API routes (blueprints)
│   │   │   ├── __init__.py
│   │   │   ├── auth.py           # Authentication routes
│   │   │   ├── users.py          # User routes
│   │   │   ├── tenants.py        # Tenant routes
│   │   │   ├── documents.py      # Document routes
│   │   │   ├── files.py          # File routes
│   │   │   └── kafka_demo.py     # Kafka demo routes
│   │   ├── utils/                # Utility modules
│   │   │   ├── __init__.py
│   │   │   ├── responses.py      # Response helpers
│   │   │   ├── decorators.py     # Custom decorators
│   │   │   └── database.py       # Database utilities
│   │   └── worker/               # Background workers
│   │       ├── __init__.py
│   │       ├── consumer.py       # Kafka consumer
│   │       └── producer.py       # Kafka producer
│   ├── migrations/               # Database migrations (Alembic)
│   ├── scripts/                  # Utility scripts
│   │   └── init_db.py            # Database initialization
│   ├── tests/                    # Test suite
│   │   ├── unit/                 # Unit tests
│   │   ├── integration/          # Integration tests
│   │   └── conftest.py           # Pytest fixtures
│   ├── requirements.txt          # Python dependencies
│   └── run.py                    # Application entry point
├── docker/                       # Docker configuration
│   ├── Dockerfile.api            # API server Dockerfile
│   ├── Dockerfile.worker         # Worker Dockerfile
│   ├── build-api.sh              # API build script
│   └── build-worker.sh           # Worker build script
├── logs/                         # Application logs
├── uploads/                      # Temporary upload directory
├── .env.development              # Development environment
├── .env.docker                   # Docker environment
├── .env.production               # Production environment (template)
├── .dockerignore                 # Docker ignore file
├── .gitignore                    # Git ignore file
├── docker-compose.yml            # Docker Compose configuration
├── swagger.yaml                  # OpenAPI specification
├── DOCKER.md                     # Docker deployment guide
├── README.md                     # This file
└── plan.md                       # Implementation plan
```

### Key Directories

- **`backend/app/models/`**: Database models using SQLAlchemy ORM
- **`backend/app/schemas/`**: Request/response validation with Marshmallow
- **`backend/app/routes/`**: API endpoints organized by blueprint
- **`backend/app/utils/`**: Helper functions, decorators, and utilities
- **`backend/app/worker/`**: Kafka consumer for background processing
- **`backend/migrations/`**: Database migration files (Alembic)
- **`backend/scripts/`**: Administrative scripts (DB init, seeding, etc.)
- **`backend/tests/`**: Unit and integration tests
- **`docker/`**: Dockerfiles and build scripts

---

## Deployment

### Production Checklist

Before deploying to production, ensure:

- [ ] Change `JWT_SECRET_KEY` to a strong random value (64+ characters)
- [ ] Use strong database passwords (16+ characters, mixed case, numbers, symbols)
- [ ] Enable SSL/TLS for all connections (database, Redis, Kafka, S3, Vault)
- [ ] Restrict CORS origins to production domains only
- [ ] Set `FLASK_ENV=production` and `FLASK_DEBUG=0`
- [ ] Configure Redis for production (persistence, authentication, clustering if needed)
- [ ] Configure rate limiting with Redis
- [ ] Set up external logging service (Sentry, CloudWatch, etc.)
- [ ] Configure monitoring and alerting (Prometheus, Grafana, etc.)
- [ ] Implement backup strategy for databases, S3, and Vault
- [ ] Set up CDN for static assets
- [ ] Configure load balancer with health checks
- [ ] Enable auto-scaling policies
- [ ] Document disaster recovery plan
- [ ] Configure HashiCorp Vault for production (no dev mode, proper backend, TLS)
- [ ] Set up Vault policies and audit logging
- [ ] Implement secret rotation strategy with Vault
- [ ] Configure security headers (CSP, HSTS, etc.)
- [ ] Set up email service (SendGrid, Mailgun, etc.)
- [ ] Test all endpoints with production data volumes

### Docker Production Deployment

See [DOCKER.md](DOCKER.md) for detailed production deployment instructions with Docker Compose.

### Cloud Deployment Options

#### AWS
- **Compute**: ECS/Fargate for containers, EC2 for VMs
- **Database**: RDS for PostgreSQL (Multi-AZ for HA)
- **Storage**: S3 for file storage
- **Message Queue**: MSK (Managed Kafka) or Amazon MQ
- **Load Balancer**: ALB with health checks
- **Monitoring**: CloudWatch, X-Ray
- **Secrets**: AWS Secrets Manager

#### Google Cloud Platform
- **Compute**: GKE for Kubernetes, Cloud Run for containers
- **Database**: Cloud SQL for PostgreSQL
- **Storage**: Cloud Storage
- **Message Queue**: Pub/Sub or Confluent Cloud
- **Load Balancer**: Cloud Load Balancing
- **Monitoring**: Cloud Monitoring, Cloud Logging
- **Secrets**: Secret Manager

#### Azure
- **Compute**: AKS for Kubernetes, Container Instances
- **Database**: Azure Database for PostgreSQL
- **Storage**: Blob Storage
- **Message Queue**: Event Hubs (Kafka-compatible)
- **Load Balancer**: Azure Load Balancer
- **Monitoring**: Azure Monitor, Application Insights
- **Secrets**: Key Vault

### Kubernetes Deployment

For Kubernetes deployment:

1. Create Kubernetes manifests from Docker Compose:
   ```bash
   kompose convert -f docker-compose.yml
   ```

2. Adjust generated manifests for production requirements

3. Set up Helm charts for easier management

4. Configure Ingress for external access

5. Set up persistent volumes for databases

### Performance Optimization

- **Database**: Use connection pooling, read replicas, query optimization
- **Caching with Redis**:
  - Session storage for horizontal scaling
  - API response caching to reduce database load
  - Token blacklist management across instances
  - Rate limiting implementation
- **CDN**: Use CloudFront, Cloudflare for static assets
- **Load Balancing**: Distribute traffic across multiple API instances
- **Async Processing**: Offload heavy operations to Kafka workers
- **Monitoring**: Track API response times, database queries, error rates, Redis memory usage

---

## Contributing

We welcome contributions! Please follow these guidelines:

### Development Workflow

1. **Fork the Repository**
   ```bash
   git clone https://github.com/your-username/SaaSBackendWithClaude.git
   cd SaaSBackendWithClaude
   ```

2. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make Changes**
   - Follow existing code style
   - Add tests for new features
   - Update documentation

4. **Run Tests**
   ```bash
   pytest
   black backend/
   flake8 backend/
   ```

5. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: Add your feature description"
   ```

6. **Push and Create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

### Code Style

- **Python**: Follow PEP 8, use `black` for formatting
- **Imports**: Group by standard library, third-party, local
- **Docstrings**: Use Google-style docstrings
- **Type Hints**: Use type hints for function parameters and return values
- **Comments**: Explain "why", not "what"

### Commit Messages

Follow Conventional Commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

### Pull Request Process

1. Ensure all tests pass
2. Update documentation if needed
3. Add entry to CHANGELOG.md
4. Request review from maintainers
5. Address review feedback
6. Squash commits before merge

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2025 SaaS Platform Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Support

### Documentation
- **Architecture**: See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Docker Deployment**: See [DOCKER.md](DOCKER.md)
- **API Reference**: See [swagger.yaml](swagger.yaml)

### Getting Help
- **Issues**: [GitHub Issues](https://github.com/your-org/SaaSBackendWithClaude/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/SaaSBackendWithClaude/discussions)
- **Email**: support@saas-platform.example.com

### Reporting Bugs

When reporting bugs, please include:
1. Environment details (OS, Python version, Docker version)
2. Steps to reproduce the issue
3. Expected behavior
4. Actual behavior
5. Error messages and logs
6. Screenshots (if applicable)

### Suggesting Features

Feature requests are welcome! Please:
1. Check existing issues first
2. Describe the use case
3. Explain the expected behavior
4. Provide examples if possible

---

## Acknowledgments

- Flask framework and ecosystem
- PostgreSQL community
- Apache Kafka project
- MinIO team
- All open-source contributors

---

## Roadmap

### Version 1.1 (Upcoming)
- [ ] Swagger UI integration
- [ ] Advanced search and filtering
- [ ] Bulk operations API
- [ ] Audit logging UI
- [ ] Email notifications

### Version 1.2 (Future)
- [ ] Real-time notifications (WebSockets)
- [ ] Advanced analytics dashboard
- [ ] Multi-region support
- [ ] Data export/import tools
- [ ] OAuth2 provider integration

### Version 2.0 (Long-term)
- [ ] GraphQL API
- [ ] Mobile SDK
- [ ] Workflow automation
- [ ] AI/ML integrations
- [ ] Advanced reporting

---

**Built with ❤️ using Flask, PostgreSQL, Kafka, and S3**
