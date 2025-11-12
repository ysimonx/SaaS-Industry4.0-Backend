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

**Recommendation: Use Celery** for the following reasons:

1. **Already Active and Working** - Celery is production-ready (SSO tasks prove it works)
2. **Task Characteristics Match** - TSA timestamping is a task (request/response with retry logic)
3. **Operational Simplicity** - Redis infrastructure already in place, Flower dashboard available
4. **Integration with Existing Patterns** - Already have `app/tasks/` structure
5. **DigiCert API Characteristics** - TSA timestamping is a synchronous HTTP API call with retry needs

Kafka would be better for event-driven workflows, but it's not yet operational in this codebase.

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
- Gestion des credentials DigiCert depuis Vault
- Retry logic avec exponential backoff
- Gestion des erreurs HTTP/timeout
- Support RFC 3161 (requête TSR avec ASN.1 DER encoding)

**Structure de la réponse:**
```python
{
    'success': True,
    'timestamp_token': '<base64_encoded_tsr>',  # RFC 3161 TimeStampResp
    'algorithm': 'sha256',
    'serial_number': '0x123456789ABCDEF',
    'gen_time': '2025-01-15T10:30:00Z',
    'tsa_authority': 'DigiCert Timestamp Authority',
    'policy_oid': '2.16.840.1.114412.7.1'
}
```

**Dépendances:**
- `cryptography` library pour ASN.1 parsing
- `requests` pour HTTP calls
- Configuration depuis Vault:
  - `DIGICERT_TSA_URL` - Endpoint TSA RFC3161
  - `DIGICERT_API_KEY` - API credentials
  - `DIGICERT_CERTIFICATE` - Client certificate (si requis)

**Gestion d'erreurs:**
- `TSAConnectionError` - Échec de connexion DigiCert
- `TSAInvalidResponseError` - Réponse TSA invalide
- `TSAQuotaExceededError` - Quota dépassé
- Retry automatique sur erreurs réseau (max 3 tentatives)

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

            # Store timestamp
            file.set_metadata('tsa_timestamp', {
                'token': tsa_response['timestamp_token'],
                'algorithm': tsa_response['algorithm'],
                'serial_number': tsa_response['serial_number'],
                'gen_time': tsa_response['gen_time'],
                'tsa_authority': tsa_response['tsa_authority'],
                'policy_oid': tsa_response.get('policy_oid'),
                'provider': 'digicert',
                'timestamped_at': datetime.utcnow().isoformat(),
                'status': 'success'
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

**6. Télécharger token TSA (format .tsr)**
```
GET /api/tenants/{tenant_id}/files/{file_id}/timestamp/download
Authorization: Bearer <token>

Response 200:
Content-Type: application/timestamp-reply
Content-Disposition: attachment; filename="file_{file_id}_timestamp.tsr"

<binary TSR data>
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

#### Dans Vault (`secret/saas-project/dev/`):

```json
{
  "DIGICERT_TSA_URL": "http://timestamp.digicert.com",
  "DIGICERT_API_KEY": "your-api-key-here",
  "DIGICERT_CERTIFICATE": "-----BEGIN CERTIFICATE-----\n...",
  "TSA_REQUEST_TIMEOUT": "30",
  "TSA_MAX_RETRIES": "3"
}
```

#### Dans `.env.docker` / `.env.docker.minimal`:

```bash
# TSA Configuration
USE_TSA=true
TSA_PROVIDER=digicert
TSA_DEFAULT_ALGORITHM=sha256

# Celery Queue for TSA
CELERY_TSA_QUEUE=tsa_timestamping
CELERY_TSA_CONCURRENCY=4
CELERY_TSA_RATE_LIMIT=100/h
```

#### Chargement depuis Vault dans `config.py`:

```python
if config.USE_VAULT:
    config.DIGICERT_TSA_URL = vault_secrets.get('DIGICERT_TSA_URL')
    config.DIGICERT_API_KEY = vault_secrets.get('DIGICERT_API_KEY')
    config.DIGICERT_CERTIFICATE = vault_secrets.get('DIGICERT_CERTIFICATE')
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
- Base de données chiffrée au repos (recommandé en production)
- Pas de PII dans le timestamp (juste hash du fichier)

**Access Control:**
- Lecture du timestamp : même permissions que lecture du fichier
- Seuls les admins peuvent activer/désactiver TSA
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

**Question:** Que faire des fichiers uploadés AVANT activation TSA ?

**Options:**
1. **Ne rien faire** - Seuls les nouveaux fichiers sont horodatés
2. **Script de migration** - Horodater tous les fichiers existants (coûteux)
3. **Horodatage à la demande** - Ajouter endpoint `POST /files/{id}/timestamp/create`

**Recommandation:** Option 1 (ne rien faire) pour minimiser les coûts.

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

## Questions Ouvertes / À Discuter

1. **Credentials DigiCert:**
   - Avez-vous déjà un compte et API key ?
   - Quel est l'endpoint TSA exact ?
   - Y a-t-il un environnement de test/sandbox ?

2. **Format du timestamp:**
   - Stocker uniquement le token TSA, ou aussi le certificat complet ?
   - Faut-il archiver les tokens sur un storage séparé (S3 long-term) ?

3. **Politique de retry:**
   - 3 retries suffisants ?
   - Que faire après 3 échecs ? (notification admin, escalation)

4. **Verification automatique:**
   - Faut-il vérifier automatiquement les timestamps périodiquement ?
   - Celery Beat task pour vérifier les timestamps > 30 jours ?

5. **Migration de données existantes:**
   - Faut-il un endpoint pour horodater rétroactivement des fichiers ?
   - Quel est le budget pour horodater l'historique ?

6. **Conformité:**
   - Y a-t-il des exigences légales spécifiques (eIDAS, ETSI) ?
   - Durée de conservation des timestamps ?

---

## Conclusion

Ce plan fournit une implémentation complète de l'horodatage TSA RFC3161 avec:
- **Celery** pour le traitement asynchrone (architecture existante)
- **Configuration par tenant** (activation/désactivation)
- **Horodatage des nouveaux fichiers uniquement** (évite coûts inutiles)
- **Stockage dans `file_metadata`** (pas de changement de schéma)
- **Queue dédiée** pour isolation et scaling
- **Tests complets** (unit + integration)
- **Monitoring** via Flower
- **Documentation** complète

**Prêt à l'implémentation** dès que les credentials DigiCert sont disponibles.
