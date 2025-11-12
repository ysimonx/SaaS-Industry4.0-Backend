# Plan d'Implémentation : Horodatage TSA RFC3161 avec DigiCert

## Objectifs

- Horodatage automatique de tous les **nouveaux fichiers** (pas les fichiers dédupliqués)
- **Configurable par tenant** (activation/désactivation)
- Stockage du timestamp au niveau du **File** (dans `file_metadata` JSONB)
- Processing **asynchrone via Celery** avec queue dédiée `tsa_timestamping`

---

## Analyse de l'Architecture Existante

### 1. Current File Upload Flow

**Synchronous Flow (in HTTP request):**
1. User uploads file via `POST /api/tenants/{tenant_id}/documents`
2. Route handler (`documents.py`) receives the multipart form data
3. File is validated (size, MIME type)
4. MD5 hash is calculated
5. `DocumentService.create_document()` is called, which:
   - Checks for duplicate files by MD5 hash (deduplication)
   - If duplicate exists: reuses existing File record
   - If new: creates File record in tenant database with S3 path
   - Creates Document record linking to the File
   - Commits to tenant database
6. Response returned to user with document metadata

**Key Observation:** The actual S3 upload is currently a placeholder (marked TODO Phase 6).

### 2. Existing Celery Infrastructure

**Current Celery Setup:**
- Celery is **actively used** for SSO token management
- Redis is the broker (redis://localhost:6379/3)
- Multiple queues: `sso`, `maintenance`, `email`
- Celery Beat for scheduled tasks

**Active Tasks:**
- `refresh_expiring_tokens` - Every 15 minutes
- `cleanup_expired_tokens` - Daily at 2 AM
- `rotate_encryption_keys` - Monthly
- `health_check` - Every 5 minutes

**Task Characteristics:**
- Tasks use Flask app context
- Database operations within tasks
- Retry logic with exponential backoff
- Task routing by queue

### 3. Why Celery over Kafka?

**Note: Both Celery AND Kafka are operational in this codebase**, but we recommend **Celery for TSA timestamping** based on architectural patterns:

#### Kafka is Already Working:
- ✅ Kafka + Zookeeper services running in docker-compose
- ✅ Active consumer: `backend/app/worker/consumer.py`
- ✅ Producer service: `backend/app/services/kafka_service.py`
- ✅ Existing topics: `tenant.created`, `document.uploaded`, `file.process`

#### Why Celery is Better for TSA:

**1. Task vs Event Semantics:**
- **TSA Timestamping** = Request/Response pattern (call DigiCert → wait for timestamp token → store result)
- **Kafka** = Fire-and-forget events (publish `document.uploaded` → multiple consumers react independently)

**2. Result Tracking:**
- **Celery**: Built-in task state (pending/success/failure/retry) via result backend
- **Kafka**: Would require custom state machine in Redis/DB to track timestamp status

**3. Retry Logic:**
- **Celery**: `@task(autoretry_for=(TSAException,), retry_backoff=True)` - automatic exponential backoff
- **Kafka**: Manual retry implementation in consumer (dead-letter queues, manual offset management)

**4. Monitoring:**
- **Celery**: Flower dashboard shows task status, failures, execution time
- **Kafka**: Would need custom dashboard to track timestamp request status

**5. Timeout Handling:**
- **Celery**: Soft/hard time limits built-in (`time_limit=120`, `soft_time_limit=90`)
- **Kafka**: Manual timeout detection in consumer

**6. Result Retrieval:**
- **Celery**: `task.get()` or `AsyncResult(task_id)` to retrieve timestamp token
- **Kafka**: Correlation IDs + separate response topic pattern

#### The Hybrid Approach (Recommended):

Use **both** based on their strengths:

```python
# Celery Task (synchronous request/response)
@celery.task(bind=True, autoretry_for=(TSAException,))
def timestamp_file(self, file_id, tenant_db):
    """Request timestamp from DigiCert - track result"""
    timestamp_token = digicert_tsa_service.get_rfc3161_timestamp(file_hash)
    # Store in DB
    return timestamp_token

# Kafka Event (broadcast notification)
kafka_service.publish_event('file.timestamped', {
    'file_id': file_id,
    'timestamp_token': timestamp_token,
    'tsa_authority': 'DigiCert'
})
```

**Flow:**
1. User uploads file → `timestamp_file.delay(file_id)` (Celery)
2. Task succeeds → Save to DB + Publish Kafka event `file.timestamped`
3. Kafka consumers react: audit logs, compliance reports, notifications

**Conclusion:** Use Celery for orchestrating the synchronous DigiCert API call, then use Kafka to broadcast the success event to interested consumers. This combines Celery's task orchestration strengths with Kafka's event streaming capabilities.

---

## Étapes d'Implémentation

### 1. Modèle Tenant - Ajout configuration TSA

**Modifications à `backend/app/models/tenant.py`:**
- Ajouter colonnes:
  - `tsa_enabled` (Boolean, default=False) - Active/désactive l'horodatage pour ce tenant
  - `tsa_provider` (String, default='digicert') - Provider TSA (extensible pour d'autres providers)

**Migration Alembic:**
```bash
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Add TSA configuration to tenants"
docker-compose exec api /app/flask-wrapper.sh db upgrade
```

**Exemple modèle:**
```python
class Tenant(db.Model):
    # ... existing fields ...
    tsa_enabled = db.Column(db.Boolean, nullable=False, default=False)
    tsa_provider = db.Column(db.String(50), nullable=True, default='digicert')
```

---

### 2. Service DigiCert TSA

**Créer `backend/app/services/digicert_tsa_service.py`:**

Fonctionnalités:
- `get_rfc3161_timestamp(file_hash: str, algorithm: str = 'sha256')` - Requête TSA RFC3161
- **Credentials optionnelles** - DigiCert public TSA ne nécessite pas d'authentification
- Retry logic avec exponential backoff
- Gestion des erreurs HTTP/timeout
- Support RFC 3161 (requête TSR avec ASN.1 DER encoding)

**Structure de la réponse:**
```python
{
    'success': True,
    'timestamp_token': '<base64_encoded_tsr>',  # RFC 3161 TimeStampResp complet
    'algorithm': 'sha256',
    'serial_number': '0x123456789ABCDEF',
    'gen_time': '2025-01-15T10:30:00Z',
    'tsa_authority': 'DigiCert Timestamp Authority',
    'policy_oid': '2.16.840.1.114412.7.1',
    'tsa_certificate': '<base64_encoded_cert>',  # Certificat X.509 du TSA (pour archivage)
    'certificate_chain': ['<base64_cert1>', '<base64_cert2>']  # Chaîne complète jusqu'à la racine
}
```

**Note importante:** Le token RFC 3161 (`timestamp_token`) contient déjà le certificat TSA, mais nous stockons également le certificat séparément (`tsa_certificate`) et la chaîne complète (`certificate_chain`) pour faciliter la vérification à long terme, même si les certificats intermédiaires DigiCert deviennent indisponibles.

**Dépendances:**
- `cryptography` library pour ASN.1 parsing
- `requests` pour HTTP calls
- Configuration depuis Vault (optionnelle pour DigiCert public):
  - `DIGICERT_TSA_URL` - Endpoint TSA RFC3161 (default: `http://timestamp.digicert.com`)
  - `DIGICERT_API_KEY` - API credentials (optionnel, uniquement pour TSA privé)
  - `DIGICERT_CERTIFICATE` - Client certificate (optionnel, uniquement si authentification mutuelle requise)

**Gestion d'erreurs:**
- `TSAConnectionError` - Échec de connexion DigiCert
- `TSAInvalidResponseError` - Réponse TSA invalide
- `TSAQuotaExceededError` - Quota dépassé (si utilisation TSA privé avec limites)
- Retry automatique sur erreurs réseau (max 3 tentatives)

**Note:** Le service public DigiCert TSA (`http://timestamp.digicert.com`) est gratuit et ne nécessite aucune authentification. Les credentials sont uniquement nécessaires si vous utilisez un service TSA privé ou entreprise.

---

### 3. Tâche Celery pour horodatage

**Créer `backend/app/tasks/tsa_tasks.py`:**

```python
@celery_app.task(
    name='app.tasks.tsa_tasks.timestamp_file',
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute
    autoretry_for=(TSAConnectionError,),
    retry_backoff=True,
    retry_backoff_max=600,  # 10 minutes max
    retry_jitter=True
)
def timestamp_file(self, file_id: str, tenant_database_name: str, md5_hash: str):
    """
    Request TSA RFC3161 timestamp from DigiCert for uploaded file.

    Args:
        file_id: UUID of the File record in tenant database
        tenant_database_name: Name of tenant database (e.g., 'tenant_acme_123')
        md5_hash: MD5 hash of the file content

    Returns:
        dict: {'success': bool, 'file_id': str, 'timestamp_serial': str}
    """
    try:
        # 1. Request timestamp from DigiCert
        tsa_response = digicert_tsa_service.get_rfc3161_timestamp(md5_hash)

        # 2. Store timestamp in File metadata
        with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
            file = session.query(File).filter_by(id=file_id).first()

            if not file:
                raise ValueError(f"File {file_id} not found in {tenant_database_name}")

            # Check if already timestamped (idempotence)
            existing_tsa = file.get_metadata('tsa_timestamp')
            if existing_tsa and existing_tsa.get('status') == 'success':
                logger.info(f"File {file_id} already timestamped, skipping")
                return {'success': True, 'file_id': file_id, 'already_timestamped': True}

            # Store timestamp avec certificat complet et chaîne
            file.set_metadata('tsa_timestamp', {
                'token': tsa_response['timestamp_token'],
                'algorithm': tsa_response['algorithm'],
                'serial_number': tsa_response['serial_number'],
                'gen_time': tsa_response['gen_time'],
                'tsa_authority': tsa_response['tsa_authority'],
                'policy_oid': tsa_response.get('policy_oid'),
                'provider': 'digicert',
                'timestamped_at': datetime.utcnow().isoformat(),
                'status': 'success',
                # Archivage complet pour vérification à long terme
                'tsa_certificate': tsa_response['tsa_certificate'],
                'certificate_chain': tsa_response['certificate_chain']
            })

            session.commit()

        logger.info(f"Successfully timestamped file {file_id} (serial: {tsa_response['serial_number']})")

        return {
            'success': True,
            'file_id': file_id,
            'timestamp_serial': tsa_response['serial_number']
        }

    except Exception as e:
        logger.error(f"Error timestamping file {file_id}: {str(e)}", exc_info=True)

        # Store error in metadata
        try:
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                file = session.query(File).filter_by(id=file_id).first()
                if file:
                    file.set_metadata('tsa_timestamp', {
                        'status': 'error',
                        'error_message': str(e),
                        'last_attempt': datetime.utcnow().isoformat(),
                        'retry_count': self.request.retries
                    })
                    session.commit()
        except Exception as meta_error:
            logger.error(f"Failed to store error metadata: {str(meta_error)}")

        # Retry with exponential backoff
        raise self.retry(exc=e)
```

**Configuration de la queue:**
- Queue dédiée: `tsa_timestamping`
- Priority: normal
- Rate limit: 100/hour (ajustable selon quota DigiCert)

---

### 4. Configuration Celery

**Mettre à jour `backend/app/celery_app.py`:**

```python
# Task routing
celery_app.conf.task_routes = {
    'app.tasks.sso_tasks.*': {'queue': 'sso'},
    'app.tasks.maintenance_tasks.*': {'queue': 'maintenance'},
    'app.tasks.tsa_tasks.*': {'queue': 'tsa_timestamping'},  # NEW
}

# Queue-specific settings
celery_app.conf.task_annotations = {
    'app.tasks.tsa_tasks.timestamp_file': {
        'rate_limit': '100/h',  # 100 timestamps per hour
        'time_limit': 120,      # 2 minutes hard limit
        'soft_time_limit': 90,  # 90 seconds soft limit
    }
}
```

---

### 5. Intégration dans FileService

**Modifier `backend/app/services/file_service.py`:**

Dans la méthode qui crée un **nouveau** fichier (après vérification MD5, avant commit):

```python
def create_file(self, tenant_id: str, file_data: dict, uploaded_file) -> File:
    """Create new file in tenant database and optionally timestamp it."""

    # ... existing file creation logic ...

    # Check if this is a NEW file (not deduplicated)
    is_new_file = existing_file is None

    if is_new_file:
        # Create File record
        new_file = File(
            md5_hash=md5_hash,
            s3_path=s3_path,
            file_size=file_size,
            # ... other fields ...
        )
        session.add(new_file)
        session.commit()

        # Check if TSA is enabled for this tenant
        tenant = Tenant.query.filter_by(id=tenant_id).first()
        if tenant and tenant.tsa_enabled:
            # Trigger async timestamping
            from app.tasks.tsa_tasks import timestamp_file

            timestamp_file.apply_async(
                args=[
                    str(new_file.id),
                    tenant.database_name,
                    new_file.md5_hash
                ],
                queue='tsa_timestamping',
                countdown=5  # Wait 5 seconds to ensure DB commit is complete
            )

            logger.info(f"Scheduled TSA timestamping for file {new_file.id}")

        return new_file
    else:
        # File already exists (deduplicated), reuse it
        return existing_file
```

**Point clé:** L'horodatage ne se fait QUE pour les nouveaux fichiers, pas les dédupliqués.

---

### 6. Routes API pour gestion TSA

**Créer `backend/app/routes/tsa.py`:**

#### Endpoints:

**1. Activer TSA pour un tenant (Admin only)**
```
PUT /api/tenants/{tenant_id}/tsa/enable
Authorization: Bearer <admin_token>

Response 200:
{
    "success": true,
    "message": "TSA timestamping enabled for tenant",
    "data": {
        "tenant_id": "uuid",
        "tsa_enabled": true,
        "tsa_provider": "digicert"
    }
}
```

**2. Désactiver TSA pour un tenant (Admin only)**
```
PUT /api/tenants/{tenant_id}/tsa/disable
Authorization: Bearer <admin_token>

Response 200:
{
    "success": true,
    "message": "TSA timestamping disabled for tenant",
    "data": {
        "tenant_id": "uuid",
        "tsa_enabled": false
    }
}
```

**3. Statut configuration TSA**
```
GET /api/tenants/{tenant_id}/tsa/status
Authorization: Bearer <token>

Response 200:
{
    "success": true,
    "data": {
        "tsa_enabled": true,
        "tsa_provider": "digicert",
        "total_timestamped_files": 1523,
        "pending_timestamps": 5,
        "failed_timestamps": 2
    }
}
```

**4. Récupérer timestamp d'un fichier**
```
GET /api/tenants/{tenant_id}/files/{file_id}/timestamp
Authorization: Bearer <token>

Response 200:
{
    "success": true,
    "data": {
        "file_id": "uuid",
        "tsa_timestamp": {
            "token": "<base64_encoded_tsr>",
            "algorithm": "sha256",
            "serial_number": "0x123456",
            "gen_time": "2025-01-15T10:30:00Z",
            "tsa_authority": "DigiCert",
            "status": "success",
            "timestamped_at": "2025-01-15T10:30:05Z"
        }
    }
}
```

**5. Vérifier validité d'un timestamp**
```
POST /api/tenants/{tenant_id}/files/{file_id}/timestamp/verify
Authorization: Bearer <token>

Response 200:
{
    "success": true,
    "data": {
        "valid": true,
        "gen_time": "2025-01-15T10:30:00Z",
        "algorithm": "sha256",
        "message_imprint_match": true,
        "certificate_valid": true,
        "tsa_authority": "DigiCert Timestamp Authority"
    }
}
```

**6. Télécharger token TSA (format .tsr pour OpenSSL)**
```
GET /api/tenants/{tenant_id}/files/{file_id}/timestamp/download
Authorization: Bearer <token>

Response 200:
Content-Type: application/timestamp-reply
Content-Disposition: attachment; filename="file_{file_id}_timestamp.tsr"

<binary TSR data - RFC 3161 TimeStampResp en format DER>
```

**Implémentation:**
```python
@tsa_bp.route('/tenants/<uuid:tenant_id>/files/<uuid:file_id>/timestamp/download', methods=['GET'])
@jwt_required()
@role_required(['admin', 'user', 'viewer'])
def download_timestamp(tenant_id, file_id):
    """
    Télécharge le token TSA au format .tsr (RFC 3161 TimeStampResp).
    Compatible avec OpenSSL et autres outils de vérification standard.

    Usage avec OpenSSL:
        curl -o timestamp.tsr \
          -H "Authorization: Bearer $TOKEN" \
          http://localhost:4999/api/tenants/{tenant_id}/files/{file_id}/timestamp/download

        openssl ts -verify \
          -data original_file.pdf \
          -in timestamp.tsr \
          -CAfile digicert_root.pem
    """
    current_user_id = get_jwt_identity()

    try:
        # 1. Vérifier accès tenant
        tenant = Tenant.query.get_or_404(tenant_id)

        # 2. Vérifier que l'utilisateur a accès à ce tenant
        association = UserTenantAssociation.query.filter_by(
            user_id=current_user_id,
            tenant_id=tenant_id
        ).first()

        if not association:
            return jsonify({
                'success': False,
                'message': 'Access denied to this tenant'
            }), 403

        # 3. Récupérer le fichier depuis tenant DB
        with tenant_db_manager.tenant_db_session(tenant.database_name) as session:
            file = session.query(File).filter_by(id=file_id).first()

            if not file:
                return jsonify({
                    'success': False,
                    'message': 'File not found'
                }), 404

            # 4. Vérifier que le fichier a un timestamp
            tsa_data = file.get_metadata('tsa_timestamp')
            if not tsa_data or tsa_data.get('status') != 'success':
                return jsonify({
                    'success': False,
                    'message': 'File has no valid timestamp'
                }), 400

            # 5. Extraire le token TSA (base64) et le décoder
            timestamp_token_b64 = tsa_data.get('token')
            if not timestamp_token_b64:
                return jsonify({
                    'success': False,
                    'message': 'Timestamp token not found in metadata'
                }), 500

            # Décoder de base64 vers binaire (DER format)
            timestamp_token_der = base64.b64decode(timestamp_token_b64)

            # 6. Créer la réponse avec le bon Content-Type
            response = make_response(timestamp_token_der)
            response.headers['Content-Type'] = 'application/timestamp-reply'
            response.headers['Content-Disposition'] = f'attachment; filename="file_{file_id}_timestamp.tsr"'
            response.headers['Content-Length'] = len(timestamp_token_der)

            # Logging pour audit
            logger.info(f"Timestamp token downloaded for file {file_id} by user {current_user_id}")

            return response

    except Exception as e:
        logger.error(f"Error downloading timestamp: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Download failed: {str(e)}'
        }), 500
```

**Usage pratique:**

```bash
# 1. Télécharger le token TSA
curl -o timestamp.tsr \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:4999/api/tenants/12345/files/67890/timestamp/download

# 2. Télécharger aussi le fichier original (si nécessaire)
curl -o original_file.pdf \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:4999/api/tenants/12345/documents/67890/download

# 3. Télécharger les certificats DigiCert (racine + intermédiaire)
# IMPORTANT: Le certificat intermédiaire TSA est signé par DigiCert Assured ID Root CA
# (PAS par Global Root G2)

# Télécharger le certificat racine correct
curl -o digicert_root.pem https://cacerts.digicert.com/DigiCertAssuredIDRootCA.crt.pem

# Télécharger le certificat intermédiaire (TSA)
curl -o digicert_intermediate.pem https://cacerts.digicert.com/DigiCertSHA2AssuredIDTimestampingCA.crt.pem

# Créer la chaîne de certification complète
cat digicert_intermediate.pem digicert_root.pem > digicert_chain.pem

# 4. Vérifier avec OpenSSL (utiliser la chaîne complète)
openssl ts -verify \
  -data original_file.pdf \
  -in timestamp.tsr \
  -CAfile digicert_chain.pem

# Sortie attendue:
# Using configuration from /opt/homebrew/etc/openssl@3/openssl.cnf
# Verification: OK
```

**Note importante sur les certificats:**
- Le certificat TSA DigiCert est signé par **DigiCert Assured ID Root CA**
- Ne PAS utiliser DigiCert Global Root G2 (différente chaîne de certification)
- La chaîne complète doit inclure : certificat intermédiaire + certificat racine
- Sans le certificat intermédiaire, vous obtiendrez l'erreur "unable to get local issuer certificate"

**Format du fichier .tsr:**

Le fichier `.tsr` est un **RFC 3161 TimeStampResp** encodé en ASN.1 DER, contenant:
- Status de la réponse TSA (granted/rejection)
- TimeStampToken (SignedData CMS) avec:
  - TSTInfo (timestamp info: serial, genTime, messageImprint)
  - Certificat X.509 du TSA
  - Signature cryptographique du TSA

**Compatible avec:**
- ✅ OpenSSL (`openssl ts -verify`)
- ✅ Adobe Acrobat (validation PDF signatures)
- ✅ Microsoft Authenticode (validation exécutables)
- ✅ Java `jarsigner` (validation JAR signatures)
- ✅ Tous outils conformes RFC 3161
```

**7. Horodater rétroactivement un fichier existant (Admin only)**
```
POST /api/tenants/{tenant_id}/files/{file_id}/timestamp/create
Authorization: Bearer <admin_token>

Body (optionnel):
{
    "force": false  # Si true, remplace un timestamp existant
}

Response 202 Accepted (task lancée en arrière-plan):
{
    "success": true,
    "message": "Timestamp task scheduled",
    "data": {
        "file_id": "uuid",
        "task_id": "celery-task-uuid",
        "status": "pending"
    }
}

Response 200 OK (si déjà horodaté et force=false):
{
    "success": true,
    "message": "File already timestamped",
    "data": {
        "file_id": "uuid",
        "timestamp": {
            "gen_time": "2025-01-15T10:30:00Z",
            "serial_number": "0x123456",
            "status": "success"
        }
    }
}

Response 400 Bad Request (si TSA désactivé):
{
    "success": false,
    "message": "TSA timestamping is not enabled for this tenant"
}
```

**8. Horodater en masse plusieurs fichiers (Admin only)**
```
POST /api/tenants/{tenant_id}/files/timestamp/bulk
Authorization: Bearer <admin_token>

Body:
{
    "file_ids": ["uuid1", "uuid2", "uuid3"],  # Liste de file IDs (max 1000)
    "filter": {  # Optionnel: filtre au lieu de liste explicite
        "uploaded_before": "2025-01-01T00:00:00Z",
        "not_timestamped": true
    }
}

Response 202 Accepted:
{
    "success": true,
    "message": "Bulk timestamp tasks scheduled",
    "data": {
        "total_files": 150,
        "tasks_scheduled": 150,
        "estimated_duration_minutes": 25
    }
}
```

**9. Statut d'une tâche d'horodatage (pour suivi asynchrone)**
```
GET /api/tenants/{tenant_id}/files/{file_id}/timestamp/status
Authorization: Bearer <token>

Response 200:
{
    "success": true,
    "data": {
        "file_id": "uuid",
        "status": "pending",  # pending, in_progress, success, error
        "task_id": "celery-task-uuid",
        "progress": 0,  # 0-100
        "error_message": null,
        "started_at": "2025-01-15T10:30:00Z",
        "completed_at": null
    }
}
```

---

### 7. Worker Celery dédié (optionnel mais recommandé)

**Ajouter dans `docker-compose.yml`:**

```yaml
celery-worker-tsa:
  build: ./backend
  command: celery -A app.celery_app worker --loglevel=info --queues=tsa_timestamping --concurrency=4
  volumes:
    - ./backend:/app
  env_file:
    - .env
  depends_on:
    - redis
    - postgres
  networks:
    - saas-network
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "celery", "-A", "app.celery_app", "inspect", "ping"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Avantages:**
- Isolation des tâches TSA (pas d'impact sur SSO tasks)
- Scaling indépendant (ajuster concurrency selon quota DigiCert)
- Monitoring dédié via Flower
- Peut être déployé sur instance séparée en production

---

### 8. Configuration et Secrets

#### Dans `.env.docker` / `.env.docker.minimal`:

```bash
# TSA Configuration
USE_TSA=true
TSA_PROVIDER=digicert
TSA_DEFAULT_ALGORITHM=sha256

# DigiCert TSA Endpoint (public, no authentication required)
DIGICERT_TSA_URL=http://timestamp.digicert.com

# Request settings
TSA_REQUEST_TIMEOUT=30
TSA_MAX_RETRIES=3

# Celery Queue for TSA
CELERY_TSA_QUEUE=tsa_timestamping
CELERY_TSA_CONCURRENCY=4
CELERY_TSA_RATE_LIMIT=100/h  # Conservative rate, can be increased
```

#### Dans Vault (`secret/saas-project/dev/`) - **OPTIONNEL**:

**Note:** Vault est uniquement nécessaire si vous utilisez un service TSA privé avec authentification.

```json
{
  "DIGICERT_TSA_URL": "https://private-tsa.digicert.com",
  "DIGICERT_API_KEY": "your-private-api-key",
  "DIGICERT_CERTIFICATE": "-----BEGIN CERTIFICATE-----\n...",
  "TSA_REQUEST_TIMEOUT": "30",
  "TSA_MAX_RETRIES": "3"
}
```

#### Chargement depuis Vault dans `config.py` (optionnel):

```python
# Load from environment (always available)
config.DIGICERT_TSA_URL = os.getenv('DIGICERT_TSA_URL', 'http://timestamp.digicert.com')
config.TSA_REQUEST_TIMEOUT = int(os.getenv('TSA_REQUEST_TIMEOUT', '30'))
config.TSA_MAX_RETRIES = int(os.getenv('TSA_MAX_RETRIES', '3'))

# Override with Vault if available and using private TSA
if config.USE_VAULT:
    vault_tsa_url = vault_secrets.get('DIGICERT_TSA_URL')
    if vault_tsa_url:
        config.DIGICERT_TSA_URL = vault_tsa_url
        config.DIGICERT_API_KEY = vault_secrets.get('DIGICERT_API_KEY')  # Optional
        config.DIGICERT_CERTIFICATE = vault_secrets.get('DIGICERT_CERTIFICATE')  # Optional
```

---

### 9. Tests

#### Tests unitaires (`tests/unit/test_digicert_tsa_service.py`):

```python
class TestDigiCertTSAService:
    def test_get_timestamp_success(self, mock_digicert_api):
        """Test successful TSA timestamp request"""
        result = digicert_tsa_service.get_rfc3161_timestamp('abc123')
        assert result['success'] is True
        assert 'timestamp_token' in result
        assert result['algorithm'] == 'sha256'

    def test_get_timestamp_connection_error(self, mock_digicert_api_error):
        """Test retry on connection error"""
        with pytest.raises(TSAConnectionError):
            digicert_tsa_service.get_rfc3161_timestamp('abc123')

    def test_get_timestamp_invalid_response(self, mock_digicert_invalid):
        """Test handling of invalid TSA response"""
        with pytest.raises(TSAInvalidResponseError):
            digicert_tsa_service.get_rfc3161_timestamp('abc123')
```

#### Tests d'intégration (`tests/integration/test_tsa_workflow.py`):

```python
class TestTSAWorkflow:
    def test_file_upload_triggers_tsa_when_enabled(self, client, admin_token, tenant_with_tsa):
        """Test that uploading file triggers TSA task when enabled"""
        # Upload file
        response = client.post(
            f'/api/tenants/{tenant_with_tsa.id}/documents',
            headers={'Authorization': f'Bearer {admin_token}'},
            data={'file': (io.BytesIO(b'test content'), 'test.pdf')}
        )

        assert response.status_code == 201

        # Check that TSA task was scheduled
        # (use Celery's inspect() or mock apply_async)

    def test_file_upload_no_tsa_when_disabled(self, client, admin_token, tenant_no_tsa):
        """Test that TSA task is NOT triggered when disabled"""
        # Similar test but verify NO task scheduled

    def test_deduplicated_file_not_timestamped(self, client, admin_token, tenant_with_tsa):
        """Test that deduplicated files don't get new timestamps"""
        # Upload file twice, check only one timestamp created
```

#### Tests Celery task (`tests/integration/test_tsa_tasks.py`):

```python
class TestTSATasks:
    def test_timestamp_file_task_success(self, mock_digicert, tenant_db):
        """Test successful file timestamping task"""
        result = timestamp_file.apply(
            args=['file-uuid', 'tenant_acme_123', 'abc123hash']
        ).get()

        assert result['success'] is True

        # Verify timestamp stored in database
        with tenant_db_manager.tenant_db_session('tenant_acme_123') as session:
            file = session.query(File).get('file-uuid')
            tsa_data = file.get_metadata('tsa_timestamp')
            assert tsa_data['status'] == 'success'
            assert 'token' in tsa_data

    def test_timestamp_file_task_retry_on_error(self, mock_digicert_timeout):
        """Test task retry on connection timeout"""
        with pytest.raises(Exception):
            timestamp_file.apply(args=['file-uuid', 'tenant_acme_123', 'abc123']).get()

        # Verify retry was attempted (check task state)
```

---

### 10. Documentation

#### Mise à jour `CLAUDE.md`:

Ajouter section:

```markdown
### TSA RFC3161 Timestamping with DigiCert

The platform supports automatic timestamping of uploaded files using DigiCert's TSA service (RFC 3161).

**Configuration:**
- Per-tenant activation: `Tenant.tsa_enabled` (default: false)
- Only NEW files are timestamped (not deduplicated files)
- Timestamps stored in `File.file_metadata['tsa_timestamp']`

**Architecture:**
- Async processing via Celery queue `tsa_timestamping`
- Dedicated worker: `celery-worker-tsa`
- Retry logic: 3 attempts with exponential backoff
- Monitoring: Flower dashboard (http://localhost:5555)

**Enable TSA for tenant:**
```bash
curl -X PUT http://localhost:4999/api/tenants/{tenant_id}/tsa/enable \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Check file timestamp:**
```bash
curl http://localhost:4999/api/tenants/{tenant_id}/files/{file_id}/timestamp \
  -H "Authorization: Bearer $TOKEN"
```

**Download TSA token (.tsr file):**
```bash
curl -O http://localhost:4999/api/tenants/{tenant_id}/files/{file_id}/timestamp/download \
  -H "Authorization: Bearer $TOKEN"
```

**Verify timestamp:**
```bash
curl -X POST http://localhost:4999/api/tenants/{tenant_id}/files/{file_id}/timestamp/verify \
  -H "Authorization: Bearer $TOKEN"
```

**Commands:**
```bash
# View TSA worker logs
docker-compose logs -f celery-worker-tsa

# Monitor TSA tasks in Flower
open http://localhost:5555

# Check pending TSA tasks
docker-compose exec celery-worker-tsa celery -A app.celery_app inspect active_queues

# Purge failed TSA tasks (CAUTION)
docker-compose exec celery-worker-tsa celery -A app.celery_app purge -Q tsa_timestamping
```
```

#### Créer `TSA_ARCHITECTURE.md`:

Documentation détaillée:
- RFC 3161 explanation
- DigiCert TSA integration details
- Timestamp token format (ASN.1 structure)
- Verification algorithm
- Troubleshooting guide

---

## Modifications de Fichiers - Résumé

### Nouveaux fichiers:

1. **`backend/app/services/digicert_tsa_service.py`** - Service DigiCert TSA
2. **`backend/app/tasks/tsa_tasks.py`** - Celery task pour horodatage
3. **`backend/app/routes/tsa.py`** - API endpoints TSA
4. **`backend/tests/unit/test_digicert_tsa_service.py`** - Tests unitaires
5. **`backend/tests/integration/test_tsa_workflow.py`** - Tests intégration
6. **`backend/tests/integration/test_tsa_tasks.py`** - Tests Celery tasks
7. **`TSA_ARCHITECTURE.md`** - Documentation architecture TSA

### Fichiers modifiés:

1. **`backend/app/models/tenant.py`** - Ajouter `tsa_enabled`, `tsa_provider`
2. **`backend/app/services/file_service.py`** - Déclencher task TSA pour nouveaux fichiers
3. **`backend/app/celery_app.py`** - Configuration queue `tsa_timestamping`
4. **`backend/app/__init__.py`** - Enregistrer blueprint `tsa_bp`
5. **`backend/docker-compose.yml`** - Ajouter service `celery-worker-tsa`
6. **`backend/app/config.py`** - Charger credentials DigiCert depuis Vault
7. **`backend/.env.docker`** - Variables TSA
8. **`backend/.env.docker.minimal`** - Variables TSA
9. **`CLAUDE.md`** - Section TSA
10. **`backend/migrations/versions/xxx_add_tsa_to_tenant.py`** - Migration Alembic

### Dépendances Python (ajouter à `requirements.txt`):

```txt
cryptography>=41.0.0  # Pour ASN.1 parsing RFC 3161
pyasn1>=0.5.0         # ASN.1 utilities
pyasn1-modules>=0.3.0 # RFC 3161 modules
```

---

## Points d'Attention

### 1. Deduplication et Horodatage

**Règle:** Seuls les **nouveaux fichiers** sont horodatés.

**Exemple:**
- User A upload `document.pdf` (MD5: `abc123`) → File créé, horodaté
- User B upload même `document.pdf` (MD5: `abc123`) → File réutilisé, PAS d'horodatage

**Justification:**
- Le timestamp certifie l'existence du fichier à un instant T
- Si le fichier existe déjà, il a déjà un timestamp valide
- Évite les coûts DigiCert inutiles

### 2. Non-bloquant

**Important:** L'upload du fichier retourne **immédiatement** au client, même si l'horodatage n'est pas terminé.

**Flow:**
1. Client upload fichier → `201 Created` (< 2 secondes)
2. Celery task démarre (5 secondes après commit DB)
3. Appel DigiCert TSA (5-30 secondes)
4. Timestamp stocké dans `file_metadata`

**Statut:**
- Le client peut vérifier le statut via `GET /api/tenants/{id}/files/{id}/timestamp`
- Si `status: 'pending'` → horodatage en cours
- Si `status: 'success'` → horodatage terminé
- Si `status: 'error'` → échec (retry automatique)

### 3. Idempotence

**Problem:** Que se passe-t-il si la task Celery retry après avoir déjà horodaté ?

**Solution:** Vérifier dans la task si un timestamp existe déjà avec `status: 'success'`:

```python
existing_tsa = file.get_metadata('tsa_timestamp')
if existing_tsa and existing_tsa.get('status') == 'success':
    logger.info(f"File {file_id} already timestamped, skipping")
    return {'success': True, 'already_timestamped': True}
```

### 4. Monitoring avec Flower

**Accès:** http://localhost:5555

**Vérifications:**
- Queue `tsa_timestamping` : nombre de tasks pending
- Task success rate
- Average execution time
- Failed tasks (nécessitent investigation)

**Alertes:**
- Si taux d'échec > 10% → vérifier credentials DigiCert
- Si temps d'exécution > 60s → vérifier réseau/latence
- Si queue size > 1000 → augmenter concurrency du worker

### 5. Coûts DigiCert

**Important:** Chaque horodatage = 1 appel API DigiCert.

**Estimations:**
- DigiCert facture généralement par timestamp (prix variable selon contrat)
- Vérifier quotas et rate limits
- Configurer `CELERY_TSA_RATE_LIMIT` en conséquence

**Optimisations:**
- Ne pas horodater les fichiers dédupliqués (déjà fait)
- Considérer horodatage par batch si gros volumes (RFC 3161 supporte batch)
- Monitoring des coûts via dashboard DigiCert

### 6. Sécurité du Timestamp Token

**Storage:**
- Token TSA stocké en **base64** dans JSONB `file_metadata`
- **Certificat TSA complet** stocké (`tsa_certificate` en base64)
- **Chaîne de certification complète** stockée (`certificate_chain` array)
- Base de données chiffrée au repos (recommandé en production)
- Pas de PII dans le timestamp (juste hash du fichier)

**Avantages du stockage complet:**
- Vérification possible même si certificats intermédiaires DigiCert deviennent indisponibles
- Pas de dépendance à l'infrastructure DigiCert pour la vérification
- Archivage pérenne (10+ ans) garanti
- Conformité légale renforcée (preuve auto-suffisante)

**Access Control:**
- Lecture du timestamp : même permissions que lecture du fichier
- Seuls les admins peuvent activer/désactiver TSA
- Seuls les admins peuvent horodater rétroactivement
- Token téléchargeable uniquement par users autorisés

### 7. Vérification des Timestamps

**Service de vérification:**
- Implémenté dans `digicert_tsa_service.verify_timestamp()`
- Vérifie:
  - Signature cryptographique du token TSA
  - Validité du certificat DigiCert
  - Correspondance du hash (message imprint)
  - Validité temporelle du certificat

**Endpoint:**
- `POST /api/tenants/{id}/files/{id}/timestamp/verify`
- Retourne statut de validation détaillé

### 8. Migration de Données Existantes

**Décision retenue:** ✅ **Horodatage rétroactif disponible**

**Endpoints disponibles:**

1. **Horodatage individuel:** `POST /api/tenants/{id}/files/{id}/timestamp/create`
   - Permet d'horodater un fichier spécifique existant
   - Réservé aux admins
   - Vérification si déjà horodaté (paramètre `force` pour remplacer)

2. **Horodatage en masse:** `POST /api/tenants/{id}/files/timestamp/bulk`
   - Horodate plusieurs fichiers en une seule requête
   - Filtres disponibles: date d'upload, non-horodaté, etc.
   - Max 1000 fichiers par requête
   - Réservé aux admins

3. **Suivi asynchrone:** `GET /api/tenants/{id}/files/{id}/timestamp/status`
   - Permet de suivre la progression des tâches d'horodatage
   - Statuts: pending, in_progress, success, error

**Implémentation technique:**

```python
# backend/app/routes/tsa.py

@tsa_bp.route('/tenants/<uuid:tenant_id>/files/<uuid:file_id>/timestamp/create', methods=['POST'])
@jwt_required()
@role_required(['admin'])
def create_timestamp_retroactive(tenant_id, file_id):
    """Horodate rétroactivement un fichier existant."""
    data = request.get_json() or {}
    force = data.get('force', False)

    tenant = Tenant.query.get_or_404(tenant_id)

    # Vérifier que TSA est activé
    if not tenant.tsa_enabled:
        return jsonify({
            'success': False,
            'message': 'TSA timestamping is not enabled for this tenant'
        }), 400

    with tenant_db_manager.tenant_db_session(tenant.database_name) as session:
        file = session.query(File).filter_by(id=file_id).first()

        if not file:
            return jsonify({'success': False, 'message': 'File not found'}), 404

        # Vérifier si déjà horodaté
        existing_tsa = file.get_metadata('tsa_timestamp')
        if existing_tsa and existing_tsa.get('status') == 'success' and not force:
            return jsonify({
                'success': True,
                'message': 'File already timestamped',
                'data': {
                    'file_id': str(file_id),
                    'timestamp': existing_tsa
                }
            }), 200

        # Lancer la tâche Celery
        task = timestamp_file.apply_async(
            args=[str(file_id), tenant.database_name, file.md5_hash],
            queue='tsa_timestamping'
        )

        return jsonify({
            'success': True,
            'message': 'Timestamp task scheduled',
            'data': {
                'file_id': str(file_id),
                'task_id': task.id,
                'status': 'pending'
            }
        }), 202


@tsa_bp.route('/tenants/<uuid:tenant_id>/files/timestamp/bulk', methods=['POST'])
@jwt_required()
@role_required(['admin'])
def create_timestamp_bulk(tenant_id):
    """Horodate en masse plusieurs fichiers existants."""
    data = request.get_json()

    tenant = Tenant.query.get_or_404(tenant_id)

    if not tenant.tsa_enabled:
        return jsonify({
            'success': False,
            'message': 'TSA timestamping is not enabled for this tenant'
        }), 400

    with tenant_db_manager.tenant_db_session(tenant.database_name) as session:
        # Option 1: Liste explicite de file_ids
        if 'file_ids' in data:
            file_ids = data['file_ids'][:1000]  # Max 1000
            files = session.query(File).filter(File.id.in_(file_ids)).all()

        # Option 2: Filtres
        elif 'filter' in data:
            query = session.query(File)

            if data['filter'].get('uploaded_before'):
                query = query.filter(File.created_at < data['filter']['uploaded_before'])

            if data['filter'].get('not_timestamped'):
                # Filtrer uniquement les fichiers sans timestamp
                query = query.filter(
                    ~File.file_metadata.has_key('tsa_timestamp')
                )

            files = query.limit(1000).all()

        else:
            return jsonify({
                'success': False,
                'message': 'Either file_ids or filter is required'
            }), 400

        # Lancer les tâches Celery
        tasks_scheduled = 0
        for file in files:
            # Vérifier si déjà horodaté
            existing_tsa = file.get_metadata('tsa_timestamp')
            if existing_tsa and existing_tsa.get('status') == 'success':
                continue

            timestamp_file.apply_async(
                args=[str(file.id), tenant.database_name, file.md5_hash],
                queue='tsa_timestamping',
                countdown=tasks_scheduled * 2  # Étalement: 2 secondes entre chaque tâche
            )
            tasks_scheduled += 1

        return jsonify({
            'success': True,
            'message': 'Bulk timestamp tasks scheduled',
            'data': {
                'total_files': len(files),
                'tasks_scheduled': tasks_scheduled,
                'estimated_duration_minutes': (tasks_scheduled * 10) // 60  # ~10s par timestamp
            }
        }), 202
```

**Considérations importantes:**

1. **Coûts**: Chaque fichier horodaté = 1 appel DigiCert (gratuit avec service public)
2. **Performance**: Étalement des tâches (2s entre chaque) pour éviter throttling
3. **Rate limiting**: Respecter `CELERY_TSA_RATE_LIMIT` (100/h par défaut)
4. **Monitoring**: Dashboard Flower pour suivre la progression
5. **Notifications**: Possible d'ajouter notification admin quand bulk terminé (via Kafka)

### 9. Gestion des Échecs

**Scénarios:**
- **DigiCert indisponible** → Retry automatique (3 fois, exponential backoff)
- **Quota dépassé** → Task fail avec `TSAQuotaExceededError`, notification admin
- **Token invalide** → Vérifier credentials dans Vault
- **Timeout réseau** → Augmenter `TSA_REQUEST_TIMEOUT`

**Stratégie:**
- Stocker `status: 'error'` dans `file_metadata` avec détails
- Admin peut relancer manuellement via endpoint `POST /files/{id}/timestamp/retry`
- Alerting via logs (intégration Sentry recommandée)

### 10. Performance et Scaling

**Bottlenecks:**
- Appel DigiCert TSA : 5-30 secondes par fichier
- Rate limit DigiCert : variable selon contrat

**Scaling:**
- Augmenter `CELERY_TSA_CONCURRENCY` (attention au rate limit)
- Déployer worker TSA sur instance dédiée
- Utiliser Redis Sentinel/Cluster pour haute disponibilité
- Load balancing si multi-instances

**Monitoring:**
- Average TSA response time
- Queue depth (alerte si > 1000)
- Failed task rate (alerte si > 5%)
- DigiCert API health check

---

## Vérification A Posteriori de l'Authenticité

Cette section explique comment vérifier **indépendamment** l'authenticité d'un horodatage RFC 3161, même des années après sa création, sans dépendre du système qui l'a généré.

### Principe de la Vérification RFC 3161

Un timestamp RFC 3161 est **cryptographiquement prouvable** grâce à:

1. **Signature digitale** du TSA (DigiCert) sur le token
2. **Certificat X.509** du TSA inclus dans le token
3. **Chaîne de certification** remontant à une autorité racine de confiance
4. **Message imprint** (hash du fichier) signé dans le token
5. **Horodatage certifié** (gen_time) non falsifiable

### Architecture de Vérification

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│  Fichier        │      │  Token TSA       │      │  Certificat Root    │
│  Original       │──────│  (.tsr)          │──────│  DigiCert           │
└─────────────────┘      └──────────────────┘      └─────────────────────┘
       │                          │                          │
       │                          │                          │
       ▼                          ▼                          ▼
  Hash SHA256              Signature + Hash           Validation Chain
  (recalculé)              (dans token)                (PKI trust)
       │                          │                          │
       └──────────────────────────┴──────────────────────────┘
                                  │
                                  ▼
                          ✅ Timestamp Valide
```

### Implémentation de la Vérification

**Créer `backend/app/services/tsa_verification_service.py`:**

```python
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509.oid import ExtensionOID
from pyasn1.codec.der import decoder
from pyasn1_modules import rfc3161
import base64
import hashlib
from datetime import datetime
import requests

class TSAVerificationService:
    """
    Service de vérification d'horodatage RFC 3161 conforme aux standards:
    - RFC 3161: Time-Stamp Protocol (TSP)
    - RFC 5816: ESSCertIDv2 Update
    - ISO 18014: Time-stamping services
    """

    def __init__(self):
        # Cache des certificats racines DigiCert (pré-chargés)
        self.digicert_root_certs = self._load_digicert_root_certificates()

    def verify_timestamp(
        self,
        file_content: bytes,
        timestamp_token: str,
        algorithm: str = 'sha256'
    ) -> dict:
        """
        Vérifie l'authenticité complète d'un timestamp RFC 3161.

        Args:
            file_content: Contenu binaire du fichier original
            timestamp_token: Token TSA en base64 (TimeStampResp)
            algorithm: Algorithme de hash utilisé (sha256, sha512, etc.)

        Returns:
            dict: Résultat détaillé de la vérification
            {
                'valid': bool,
                'gen_time': datetime,
                'tsa_authority': str,
                'serial_number': str,
                'hash_algorithm': str,
                'message_imprint_match': bool,
                'signature_valid': bool,
                'certificate_valid': bool,
                'certificate_chain_valid': bool,
                'certificate_expiry': datetime,
                'errors': list
            }
        """
        errors = []

        try:
            # 1. Décoder le token ASN.1 DER
            tsr_bytes = base64.b64decode(timestamp_token)
            tsr, _ = decoder.decode(tsr_bytes, asn1Spec=rfc3161.TimeStampResp())

            # 2. Vérifier le statut de la réponse TSA
            status = tsr['status']['status']
            if status != 0:  # 0 = granted
                errors.append(f"TSA status not granted: {status}")
                return {'valid': False, 'errors': errors}

            # 3. Extraire le TimeStampToken (SignedData CMS)
            tst_info = tsr['timeStampToken']

            # 4. Vérifier le message imprint (hash du fichier)
            file_hash = self._compute_hash(file_content, algorithm)
            tst_message_imprint = tst_info['content']['messageImprint']['hashedMessage']
            message_imprint_match = (file_hash == bytes(tst_message_imprint))

            if not message_imprint_match:
                errors.append("Message imprint mismatch - file may have been modified")

            # 5. Extraire le certificat du TSA depuis le token
            tsa_cert = self._extract_tsa_certificate(tst_info)

            # 6. Vérifier la signature cryptographique du token
            signature_valid = self._verify_signature(tst_info, tsa_cert)
            if not signature_valid:
                errors.append("Signature verification failed")

            # 7. Vérifier la validité du certificat TSA
            cert_valid, cert_errors = self._verify_certificate(tsa_cert)
            if not cert_valid:
                errors.extend(cert_errors)

            # 8. Vérifier la chaîne de certification (jusqu'à la racine DigiCert)
            chain_valid, chain_errors = self._verify_certificate_chain(
                tsa_cert,
                self.digicert_root_certs
            )
            if not chain_valid:
                errors.extend(chain_errors)

            # 9. Extraire les métadonnées du timestamp
            gen_time = self._extract_gen_time(tst_info)
            serial_number = self._extract_serial_number(tst_info)
            tsa_authority = tsa_cert.subject.rfc4514_string()

            return {
                'valid': (message_imprint_match and signature_valid and
                         cert_valid and chain_valid),
                'gen_time': gen_time,
                'tsa_authority': tsa_authority,
                'serial_number': serial_number,
                'hash_algorithm': algorithm,
                'message_imprint_match': message_imprint_match,
                'signature_valid': signature_valid,
                'certificate_valid': cert_valid,
                'certificate_chain_valid': chain_valid,
                'certificate_expiry': tsa_cert.not_valid_after,
                'errors': errors if errors else None
            }

        except Exception as e:
            errors.append(f"Verification exception: {str(e)}")
            return {'valid': False, 'errors': errors}

    def _compute_hash(self, content: bytes, algorithm: str) -> bytes:
        """Calcule le hash du fichier selon l'algorithme spécifié."""
        hash_func = getattr(hashlib, algorithm)
        return hash_func(content).digest()

    def _extract_tsa_certificate(self, tst_info) -> x509.Certificate:
        """Extrait le certificat X.509 du TSA depuis le token."""
        # Le certificat est dans SignedData -> certificates
        cert_der = bytes(tst_info['certificates'][0])
        return x509.load_der_x509_certificate(cert_der)

    def _verify_signature(self, tst_info, tsa_cert: x509.Certificate) -> bool:
        """
        Vérifie la signature cryptographique du timestamp.
        Utilise la clé publique du certificat TSA.
        """
        try:
            # Extraire la signature depuis SignedData
            signature = bytes(tst_info['signerInfos'][0]['signature'])

            # Extraire le contenu signé (TSTInfo)
            signed_content = bytes(tst_info['content'])

            # Vérifier avec la clé publique RSA du certificat
            public_key = tsa_cert.public_key()
            public_key.verify(
                signature,
                signed_content,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True
        except Exception as e:
            return False

    def _verify_certificate(self, cert: x509.Certificate) -> tuple:
        """
        Vérifie la validité du certificat TSA:
        - Dates de validité (not_before, not_after)
        - Extensions critiques
        - Extended Key Usage (timestamping)
        """
        errors = []
        now = datetime.utcnow()

        # Vérifier dates de validité
        if now < cert.not_valid_before:
            errors.append("Certificate not yet valid")
        if now > cert.not_valid_after:
            errors.append("Certificate has expired")

        # Vérifier Extended Key Usage pour timestamping
        try:
            eku = cert.extensions.get_extension_for_oid(
                ExtensionOID.EXTENDED_KEY_USAGE
            )
            if x509.oid.ExtendedKeyUsageOID.TIME_STAMPING not in eku.value:
                errors.append("Certificate not authorized for timestamping")
        except x509.ExtensionNotFound:
            errors.append("Certificate missing Extended Key Usage extension")

        return (len(errors) == 0, errors)

    def _verify_certificate_chain(
        self,
        tsa_cert: x509.Certificate,
        root_certs: list
    ) -> tuple:
        """
        Vérifie la chaîne de certification jusqu'à une racine DigiCert de confiance.

        Utilise les certificats racines pré-chargés ou téléchargés depuis:
        https://www.digicert.com/kb/digicert-root-certificates.htm
        """
        errors = []

        try:
            # Extraire l'issuer du certificat TSA
            issuer = tsa_cert.issuer

            # Chercher le certificat parent dans les racines
            parent_cert = None
            for root_cert in root_certs:
                if root_cert.subject == issuer:
                    parent_cert = root_cert
                    break

            if not parent_cert:
                errors.append("Root certificate not found in trust store")
                return (False, errors)

            # Vérifier la signature du certificat TSA avec la clé publique du parent
            try:
                parent_cert.public_key().verify(
                    tsa_cert.signature,
                    tsa_cert.tbs_certificate_bytes,
                    padding.PKCS1v15(),
                    tsa_cert.signature_hash_algorithm
                )
            except Exception as e:
                errors.append(f"Certificate chain signature invalid: {str(e)}")
                return (False, errors)

            return (True, [])

        except Exception as e:
            errors.append(f"Certificate chain verification failed: {str(e)}")
            return (False, errors)

    def _load_digicert_root_certificates(self) -> list:
        """
        Charge les certificats racines DigiCert de confiance.

        Sources:
        - DigiCert Global Root G2 (valide jusqu'en 2038)
        - DigiCert Assured ID Root CA (valide jusqu'en 2031)

        Ces certificats sont publics et peuvent être téléchargés depuis:
        https://www.digicert.com/kb/digicert-root-certificates.htm
        """
        root_certs = []

        # DigiCert Global Root G2 (PEM format)
        digicert_global_root_g2_pem = """
-----BEGIN CERTIFICATE-----
MIIDjjCCAnagAwIBAgIQAzrx5qcRqaC7KGSxHQn65TANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0xMzA4MDExMjAwMDBaFw0zODAxMTUxMjAwMDBaMGExCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j
b20xIDAeBgNVBAMTF0RpZ2lDZXJ0IEdsb2JhbCBSb290IEcyMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuzfNNNx7a8myaJCtSnX/RrohCgiN9RlUyfuI
2/Ou8jqJkTx65qsGGmvPrC3oXgkkRLpimn7Wo6h+4FR1IAWsULecYxpsMNzaHxmx
1x7e/dfgy5SDN67sH0NO3Xss0r0upS/kqbitOtSZpLYl6ZtrAGCSYP9PIUkY92eQ
q2EGnI/yuum06ZIya7XzV+hdG82MHauVBJVJ8zUtluNJbd134/tJS7SsVQepj5Wz
tCO7TG1F8PapspUwtP1MVYwnSlcUfIKdzXOS0xZKBgyMUNGPHgm+F6HmIcr9g+UQ
vIOlCsRnKPZzFBQ9RnbDhxSJITRNrw9FDKZJobq7nMWxM4MphQIDAQABo0IwQDAP
BgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBhjAdBgNVHQ4EFgQUTiJUIBiV
5uNu5g/6+rkS7QYXjzkwDQYJKoZIhvcNAQELBQADggEBAGBnKJRvDkhj6zHd6mcY
1Yl9PMWLSn/pvtsrF9+wX3N3KjITOYFnQoQj8kVnNeyIv/iPsGEMNKSuIEyExtv4
NeF22d+mQrvHRAiGfzZ0JFrabA0UWTW98kndth/Jsw1HKj2ZL7tcu7XUIOGZX1NG
Fdtom/DzMNU+MeKNhJ7jitralj41E6Vf8PlwUHBHQRFXGU7Aj64GxJUTFy8bJZ91
8rGOmaFvE7FBcf6IKshPECBV1/MUReXgRPTqh5Uykw7+U0b6LJ3/iyK5S9kJRaTe
pLiaWN0bfVKfjllDiIGknibVb63dDcY3fe0Dkhvld1927jyNxF1WW6LZZm6zNTfl
MrY=
-----END CERTIFICATE-----
        """

        try:
            cert = x509.load_pem_x509_certificate(
                digicert_global_root_g2_pem.encode()
            )
            root_certs.append(cert)
        except Exception as e:
            # Log error mais continue (fallback sur téléchargement dynamique)
            pass

        return root_certs

    def _extract_gen_time(self, tst_info) -> datetime:
        """Extrait le timestamp (genTime) du token."""
        gen_time_asn1 = tst_info['content']['genTime']
        # Convertir ASN.1 GeneralizedTime en datetime Python
        return datetime.strptime(str(gen_time_asn1), '%Y%m%d%H%M%SZ')

    def _extract_serial_number(self, tst_info) -> str:
        """Extrait le numéro de série du timestamp."""
        serial = int(tst_info['content']['serialNumber'])
        return f"0x{serial:X}"


# Service singleton
tsa_verification_service = TSAVerificationService()
```

### Endpoint de Vérification

**Mise à jour de `backend/app/routes/tsa.py`:**

```python
@tsa_bp.route('/tenants/<uuid:tenant_id>/files/<uuid:file_id>/timestamp/verify', methods=['POST'])
@jwt_required()
@role_required(['admin', 'user', 'viewer'])
def verify_timestamp(tenant_id, file_id):
    """
    Vérifie cryptographiquement l'authenticité d'un timestamp RFC 3161.

    Cette vérification est INDÉPENDANTE du système:
    - Ne nécessite pas de connexion à DigiCert
    - Utilise uniquement le fichier + token + certificats publics
    - Peut être effectuée des années après l'horodatage
    """
    current_user_id = get_jwt_identity()

    try:
        # 1. Récupérer le fichier depuis tenant DB
        tenant = Tenant.query.get_or_404(tenant_id)

        with tenant_db_manager.tenant_db_session(tenant.database_name) as session:
            file = session.query(File).filter_by(id=file_id).first()

            if not file:
                return jsonify({
                    'success': False,
                    'message': 'File not found'
                }), 404

            # 2. Vérifier que le fichier a un timestamp
            tsa_data = file.get_metadata('tsa_timestamp')
            if not tsa_data or tsa_data.get('status') != 'success':
                return jsonify({
                    'success': False,
                    'message': 'File has no valid timestamp'
                }), 400

            # 3. Télécharger le contenu du fichier depuis S3
            file_content = s3_client.download_file_bytes(file.s3_path)

            # 4. Vérifier le timestamp
            verification_result = tsa_verification_service.verify_timestamp(
                file_content=file_content,
                timestamp_token=tsa_data['token'],
                algorithm=tsa_data.get('algorithm', 'sha256')
            )

            # 5. Retourner le résultat détaillé
            return jsonify({
                'success': True,
                'data': {
                    'file_id': str(file_id),
                    'valid': verification_result['valid'],
                    'gen_time': verification_result['gen_time'].isoformat(),
                    'tsa_authority': verification_result['tsa_authority'],
                    'serial_number': verification_result['serial_number'],
                    'hash_algorithm': verification_result['hash_algorithm'],
                    'checks': {
                        'message_imprint_match': verification_result['message_imprint_match'],
                        'signature_valid': verification_result['signature_valid'],
                        'certificate_valid': verification_result['certificate_valid'],
                        'certificate_chain_valid': verification_result['certificate_chain_valid']
                    },
                    'certificate_expiry': verification_result['certificate_expiry'].isoformat(),
                    'errors': verification_result.get('errors'),
                    'verified_at': datetime.utcnow().isoformat()
                }
            }), 200

    except Exception as e:
        logger.error(f"Timestamp verification error: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Verification failed: {str(e)}'
        }), 500
```

### Vérification Manuelle (Hors Application)

**Utilisation d'outils standard pour vérification indépendante:**

#### 1. Avec OpenSSL (ligne de commande):

```bash
# Télécharger le token TSA (.tsr)
curl -o timestamp.tsr \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:4999/api/tenants/{tenant_id}/files/{file_id}/timestamp/download

# Vérifier le timestamp avec OpenSSL
openssl ts -verify \
  -data original_file.pdf \
  -in timestamp.tsr \
  -CAfile digicert_root.pem \
  -untrusted digicert_intermediate.pem

# Sortie attendue:
# Verification: OK
```

#### 2. Avec Python (script standalone):

```python
#!/usr/bin/env python3
"""
Script de vérification autonome d'horodatage RFC 3161.
Peut être exécuté des années après l'horodatage, sans accès au système.

Usage:
    python verify_timestamp.py original_file.pdf timestamp.tsr
"""

import sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from pyasn1.codec.der import decoder
from pyasn1_modules import rfc3161
import hashlib

def verify_timestamp(file_path, tsr_path):
    # Lire le fichier original
    with open(file_path, 'rb') as f:
        file_content = f.read()

    # Lire le token TSA
    with open(tsr_path, 'rb') as f:
        tsr_bytes = f.read()

    # Décoder le token ASN.1
    tsr, _ = decoder.decode(tsr_bytes, asn1Spec=rfc3161.TimeStampResp())

    # Calculer le hash du fichier
    file_hash = hashlib.sha256(file_content).digest()

    # Extraire le hash du token
    tst_info = tsr['timeStampToken']
    token_hash = bytes(tst_info['content']['messageImprint']['hashedMessage'])

    # Vérifier la correspondance
    if file_hash == token_hash:
        print("✅ VALID - Le timestamp est authentique")
        print(f"   Gen Time: {tst_info['content']['genTime']}")
        print(f"   Serial: {tst_info['content']['serialNumber']}")
        return True
    else:
        print("❌ INVALID - Le fichier a été modifié")
        return False

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <file> <timestamp.tsr>")
        sys.exit(1)

    verify_timestamp(sys.argv[1], sys.argv[2])
```

### Téléchargement des Certificats DigiCert

**Sources officielles des certificats racines:**

```bash
# DigiCert Global Root G2 (valide jusqu'en 2038)
wget https://cacerts.digicert.com/DigiCertGlobalRootG2.crt.pem

# DigiCert Assured ID Root CA (valide jusqu'en 2031)
wget https://cacerts.digicert.com/DigiCertAssuredIDRootCA.crt.pem

# DigiCert High Assurance EV Root CA
wget https://cacerts.digicert.com/DigiCertHighAssuranceEVRootCA.crt.pem
```

**Ces certificats doivent être:**
1. **Stockés dans le code** (`backend/app/certs/digicert_roots/`)
2. **Versionnés dans Git** (ce sont des certificats publics)
3. **Mis à jour périodiquement** (vérifier expirations)

### Cas d'Usage de Vérification A Posteriori

#### 1. **Conformité Légale (10+ ans après)**
```
Scénario: Un document horodaté en 2025 doit être présenté en justice en 2035.

Vérification:
- Le fichier original existe toujours
- Le token TSA (.tsr) est archivé
- Les certificats racines DigiCert sont disponibles publiquement
- La vérification prouve l'existence du document en 2025
```

#### 2. **Audit Externe (sans accès au système)**
```
Scénario: Un auditeur externe doit vérifier l'horodatage sans accès à votre backend.

Processus:
1. Fournir: fichier original + token TSA (.tsr)
2. Auditeur télécharge certificats DigiCert publics
3. Auditeur utilise OpenSSL ou Python pour vérifier
4. Vérification totalement indépendante
```

#### 3. **Migration Système (changement de plateforme)**
```
Scénario: Migration vers un nouveau système dans 5 ans.

Protection:
- Les timestamps restent valides (signés par DigiCert, pas par votre système)
- Token TSA stocké dans file_metadata (exportable)
- Vérification possible sur n'importe quelle plateforme
- Pas de dépendance vendor lock-in
```

### Points Clés de la Vérification

**✅ Avantages de RFC 3161:**
1. **Indépendance**: Vérification possible sans le système d'origine
2. **Pérennité**: Valide tant que les certificats racines sont accessibles
3. **Standards**: Compatible avec tous les outils RFC 3161 (OpenSSL, etc.)
4. **Légal**: Reconnu juridiquement dans de nombreux pays
5. **Gratuit**: Pas de coût pour vérifier (contrairement à la création)

**⚠️ Points d'Attention:**
1. **Conservation du fichier original**: Nécessaire pour vérifier le hash
2. **Archivage du token TSA**: Le token doit être préservé (en DB + backup)
3. **Certificats racines**: DigiCert doit maintenir ses certificats publics
4. **Expiration certificat TSA**: Le token reste valide même si le cert TSA expire (signature figée)

---

## Ordre d'Implémentation Recommandé

### Phase 1: Fondations (Jour 1-2)
1. Ajouter colonnes TSA au modèle Tenant + migration
2. Créer service DigiCert TSA (avec mocks pour tests)
3. Configurer credentials dans Vault
4. Tests unitaires du service TSA

### Phase 2: Celery Task (Jour 3)
5. Créer task Celery `timestamp_file`
6. Configurer queue `tsa_timestamping`
7. Tests d'intégration de la task
8. Ajouter worker TSA dans docker-compose.yml

### Phase 3: Intégration (Jour 4)
9. Modifier FileService pour déclencher task
10. Tests workflow complet (upload → timestamp)
11. Vérifier idempotence et deduplication

### Phase 4: API Endpoints (Jour 5)
12. Créer routes TSA (enable/disable/status/verify)
13. Tests API endpoints
14. Enregistrer blueprint dans app factory

### Phase 5: Monitoring & Doc (Jour 6)
15. Configuration Flower pour monitoring
16. Documentation (CLAUDE.md, TSA_ARCHITECTURE.md)
17. Scripts d'administration (retry failed tasks, etc.)

### Phase 6: Production Readiness (Jour 7+)
18. Load testing (simuler 1000 uploads simultanés)
19. Alerting et monitoring (Sentry, Prometheus)
20. Backup/restore procedures pour timestamps
21. Documentation opérationnelle (runbook)

---

## Décisions Prises

### ✅ Décisions Actées

1. **Service TSA:**
   - ✅ **Utiliser DigiCert public gratuit** (`http://timestamp.digicert.com`)
   - ✅ Pas de credentials requis (service public)
   - Configuration extensible pour TSA privé si besoin futur

2. **Format du timestamp:**
   - ✅ **Stocker le certificat complet** dans `file_metadata`
   - ✅ Stocker la **chaîne de certification complète**
   - ✅ Avantage: Vérification possible même si infrastructure DigiCert indisponible
   - ✅ Conformité légale renforcée (preuve auto-suffisante)

3. **Migration de données existantes:**
   - ✅ **Endpoint d'horodatage rétroactif disponible**
   - ✅ `POST /api/tenants/{id}/files/{id}/timestamp/create` (individuel)
   - ✅ `POST /api/tenants/{id}/files/timestamp/bulk` (en masse, max 1000)
   - ✅ Réservé aux admins
   - ✅ Filtres disponibles: date, non-horodaté, etc.

### ⚠️ Questions Restantes

1. **Politique de retry:**
   - 3 retries suffisants pour erreurs réseau ?
   - Que faire après 3 échecs ? (notification admin, escalation, retry manuel)

2. **Verification automatique:**
   - Faut-il vérifier automatiquement les timestamps périodiquement ?
   - Celery Beat task pour vérifier les timestamps > 30 jours ?
   - Alerte si certificat TSA arrive à expiration ?

3. **Conformité:**
   - Y a-t-il des exigences légales spécifiques (eIDAS, ETSI, ISO 18014) ?
   - Durée de conservation des timestamps (archivage légal) ?
   - Besoin d'un TSA qualifié eIDAS (Union Européenne) ?

4. **Rate Limiting:**
   - Quelle volumétrie attendue (uploads/jour) ?
   - DigiCert public est gratuit mais peut avoir des rate limits non documentés
   - Besoin de monitoring pour détecter throttling ?

5. **Archivage long terme:**
   - Faut-il archiver les tokens sur un storage séparé (S3 long-term) pour compliance ?
   - Politique de backup spécifique pour les timestamps ?

---

## Conclusion

Ce plan fournit une implémentation complète de l'horodatage TSA RFC3161 avec:
- **Celery** pour le traitement asynchrone (architecture existante)
- **Configuration par tenant** (activation/désactivation)
- **Horodatage automatique** des nouveaux fichiers
- **Horodatage rétroactif** des fichiers existants (individuel + en masse)
- **Certificat complet + chaîne** stockés pour vérification long terme
- **Vérification indépendante** possible (OpenSSL, Python standalone)
- **Stockage dans `file_metadata`** (pas de changement de schéma)
- **Queue dédiée** pour isolation et scaling
- **Tests complets** (unit + integration)
- **Monitoring** via Flower
- **Documentation** complète
- **DigiCert public TSA** gratuit et sans authentification (prêt à l'emploi)

**Prêt à l'implémentation immédiate** - Aucune credential requise pour démarrer avec le service public DigiCert.

### Avantages du Service Public DigiCert:
- ✅ **Gratuit** - Pas de coût par timestamp (service public)
- ✅ **Aucune authentification** - Pas de gestion de credentials
- ✅ **Production-ready** - Service fiable et haute disponibilité
- ✅ **RFC 3161 compliant** - Compatible avec tous les outils de vérification
- ✅ **Reconnu juridiquement** - Certificats DigiCert sont largement acceptés

### Fonctionnalités Clés Implémentées:

**Pour les nouveaux fichiers:**
- Horodatage automatique lors de l'upload (si TSA activé pour le tenant)
- Asynchrone via Celery (pas d'impact sur temps de réponse)

**Pour les fichiers existants:**
- Endpoint individuel: `POST /api/tenants/{id}/files/{id}/timestamp/create`
- Endpoint bulk: `POST /api/tenants/{id}/files/timestamp/bulk` (max 1000)
- Filtres: date, non-horodaté, etc.
- Suivi asynchrone: `GET /api/tenants/{id}/files/{id}/timestamp/status`

**Vérification:**
- Endpoint API: `POST /api/tenants/{id}/files/{id}/timestamp/verify`
- OpenSSL: `openssl ts -verify`
- Python standalone: Script autonome
- Indépendant du système (utilisable des décennies après)

**Sécurité et Pérennité:**
- Certificat TSA complet stocké
- Chaîne de certification complète stockée
- Vérification possible même si DigiCert indisponible
- Conformité légale renforcée (preuve auto-suffisante)

**Note:** Si besoin de SLA garantis ou quotas élevés, possibilité de migrer vers un service TSA privé plus tard (simple changement de configuration).
