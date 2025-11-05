# Implémentation URL Pré-signée S3 pour Téléchargement sans Bearer Token

## Table des matières

- [Contexte et Objectifs](#contexte-et-objectifs)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Modifications par fichier](#modifications-par-fichier)
- [Exemples d'utilisation](#exemples-dutilisation)
- [Tests](#tests)
- [Migration production](#migration-production)
- [Dépannage](#dépannage)

---

## Contexte et Objectifs

### Problème actuel

La route existante `/api/tenants/{tenant_id}/documents/{document_id}/download` nécessite un **Bearer Token dans le header HTTP**. Cela pose des problèmes dans certains cas d'usage :

- 📧 **Liens email** : Impossible d'inclure un Bearer Token dans un lien email
- 🌐 **Partage URL** : Les URLs partagées exposent le JWT complet (risque sécurité)
- 📱 **Applications mobiles** : Certains navigateurs in-app ne permettent pas les headers personnalisés
- 🔗 **Intégrations externes** : Systèmes tiers qui ne peuvent pas gérer l'authentification JWT

### Solution proposée

Implémenter une route qui génère des **URLs pré-signées S3 temporaires** permettant le téléchargement sans authentification dans l'URL elle-même.

**Flux à deux étapes** :
1. **Étape 1** (authentifiée) : Client appelle `/download-url` avec Bearer Token → reçoit URL temporaire
2. **Étape 2** (publique) : Client télécharge directement depuis S3/MinIO avec l'URL temporaire → pas de Bearer Token nécessaire

### Avantages

✅ **Sécurité** :
- URLs temporaires avec expiration configurable (défaut : 1h, max : 24h)
- Bucket MinIO privé (nécessite pré-signed URLs valides)
- Isolation multi-tenant garantie
- Révocation automatique après expiration

✅ **Performance** :
- Téléchargement direct depuis S3/MinIO (pas de proxy via Flask)
- Décharge la bande passante du serveur API
- Meilleure scalabilité

✅ **Audit & Compliance** :
- Logging complet des générations d'URLs
- Tracking : qui, quand, quel document, durée d'expiration
- Permissions RBAC appliquées (read required)

---

## Architecture

### Diagramme de séquence

```
┌──────────┐         ┌─────────────┐         ┌──────────┐         ┌─────────┐
│  Client  │         │  Flask API  │         │ Tenant DB│         │  MinIO  │
└────┬─────┘         └──────┬──────┘         └────┬─────┘         └────┬────┘
     │                      │                     │                    │
     │  1. POST /auth/login │                     │                    │
     ├─────────────────────>│                     │                    │
     │                      │                     │                    │
     │  2. JWT Token        │                     │                    │
     │<─────────────────────┤                     │                    │
     │                      │                     │                    │
     │  3. GET /download-url│                     │                    │
     │     + Bearer Token   │                     │                    │
     ├─────────────────────>│                     │                    │
     │                      │                     │                    │
     │                      │  4. Check tenant    │                    │
     │                      │     access & perms  │                    │
     │                      ├────────────────────>│                    │
     │                      │<────────────────────┤                    │
     │                      │                     │                    │
     │                      │  5. Get document    │                    │
     │                      │     & file details  │                    │
     │                      ├────────────────────>│                    │
     │                      │<────────────────────┤                    │
     │                      │                     │                    │
     │                      │  6. Generate presigned URL               │
     │                      ├──────────────────────────────────────────>│
     │                      │<──────────────────────────────────────────┤
     │                      │                     │                    │
     │                      │  7. Replace minio:9000                   │
     │                      │     → localhost:9000 │                    │
     │                      │                     │                    │
     │  8. Presigned URL    │                     │                    │
     │    (expires in 1h)   │                     │                    │
     │<─────────────────────┤                     │                    │
     │                      │                     │                    │
     │  9. Download file directly (NO Bearer Token!)                  │
     ├────────────────────────────────────────────────────────────────>│
     │                      │                     │                    │
     │ 10. File stream      │                     │                    │
     │<────────────────────────────────────────────────────────────────┤
     │                      │                     │                    │
```

### Configuration : URLs internes vs publiques

**Problème** :
- Le container Flask communique avec MinIO via l'URL Docker interne : `http://minio:9000`
- Le client (navigateur, curl, etc.) ne peut pas résoudre `minio` (nom de container Docker)
- Le client doit utiliser l'URL publique : `http://localhost:9000` (dev) ou `https://documents.example.com` (prod)

**Solution** :
Deux variables d'environnement distinctes :

| Variable | Utilisation | Dev | Production |
|----------|-------------|-----|------------|
| `S3_ENDPOINT_URL` | Backend → MinIO (upload, operations internes) | `http://minio:9000` | `http://minio:9000` |
| `S3_PUBLIC_URL` | Client → MinIO (pré-signed URLs) | `http://localhost:9000` | `https://documents.example.com` |

Le code remplace automatiquement `S3_ENDPOINT_URL` par `S3_PUBLIC_URL` dans les URLs pré-signées générées.

---

## Configuration

### Étape 1 : Variables d'environnement

#### Fichier `.env` (développement local)

```bash
# S3 Configuration (NON-SECRET)
# Note: S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY are stored in Vault
S3_ENDPOINT_URL=http://minio:9000          # URL interne (backend → MinIO)
S3_PUBLIC_URL=http://localhost:9000        # URL publique (client → MinIO) ← NOUVEAU
S3_BUCKET=saas-documents
S3_REGION=us-east-1
S3_USE_SSL=false
```

#### Fichier `.env.docker` (Docker sans Vault)

```bash
# S3 Configuration (fallback if Vault disabled)
S3_ENDPOINT_URL=http://minio:9000
S3_PUBLIC_URL=http://localhost:9000        # ← NOUVEAU
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents
S3_REGION=us-east-1
S3_USE_SSL=false
```

#### Fichier `.env.docker.minimal` (Docker avec Vault)

```bash
# S3 Configuration (NON-SECRET)
# Note: S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY are stored in Vault
S3_ENDPOINT_URL=http://minio:9000
S3_PUBLIC_URL=http://localhost:9000        # ← NOUVEAU
S3_BUCKET=saas-documents
S3_REGION=us-east-1
S3_USE_SSL=false
```

#### Fichier `.env.example` (documentation)

```bash
# S3 Configuration
S3_ENDPOINT_URL=http://minio:9000          # Internal URL (backend to MinIO)
S3_PUBLIC_URL=http://localhost:9000        # Public URL (client to MinIO) - Use https://documents.example.com in production
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents
S3_REGION=us-east-1
S3_USE_SSL=false
```

### Étape 2 : Production

Pour la production, dans votre serveur/Vault :

```bash
# Production environment
S3_ENDPOINT_URL=http://minio:9000                    # Interne Docker
S3_PUBLIC_URL=https://documents.example.com          # Domaine public
S3_BUCKET=saas-documents-prod
S3_REGION=eu-west-1
S3_USE_SSL=true
```

**Important** : Si vous utilisez HashiCorp Vault, ajoutez `S3_PUBLIC_URL` dans le secret path `secret/saas-project/production/s3`.

---

## Modifications par fichier

### 1. Configuration - `backend/app/config.py`

**Localisation** : Ligne ~80 dans la classe `Config`

**Ajouter après `S3_REGION`** :

```python
# S3 Configuration
S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL', 'http://localhost:9000')
S3_ACCESS_KEY_ID = os.environ.get('S3_ACCESS_KEY_ID')
S3_SECRET_ACCESS_KEY = os.environ.get('S3_SECRET_ACCESS_KEY')
S3_BUCKET = os.environ.get('S3_BUCKET', 'saas-documents')
S3_BUCKET_NAME = S3_BUCKET  # Alias for backward compatibility
S3_REGION = os.environ.get('S3_REGION', 'us-east-1')
S3_USE_SSL = os.environ.get('S3_USE_SSL', 'True').lower() == 'true'
S3_PUBLIC_URL = os.environ.get('S3_PUBLIC_URL', S3_ENDPOINT_URL)  # ← NOUVEAU
```

**Mettre à jour `load_from_vault()`** (ligne ~165) :

```python
# Configuration S3
if "s3" in secrets:
    s3_secrets = secrets["s3"]
    cls.S3_ENDPOINT_URL = s3_secrets.get("endpoint_url")
    cls.S3_ACCESS_KEY_ID = s3_secrets.get("access_key_id")
    cls.S3_SECRET_ACCESS_KEY = s3_secrets.get("secret_access_key")
    cls.S3_BUCKET_NAME = s3_secrets.get("bucket_name")
    cls.S3_REGION = s3_secrets.get("region")
    cls.S3_PUBLIC_URL = s3_secrets.get("public_url", cls.S3_ENDPOINT_URL)  # ← NOUVEAU
    logger.info("Configuration S3 chargée depuis Vault")
```

---

### 2. S3 Client - `backend/app/utils/s3_client.py`

#### Modification 1 : `_ensure_initialized()` (ligne ~110)

**Ajouter après `self._bucket`** :

```python
def _ensure_initialized(self) -> Tuple[bool, Optional[str]]:
    """..."""
    if self._initialized:
        return True, None

    try:
        config = current_app.config

        # Extract S3 configuration
        self._bucket = config.get('S3_BUCKET') or config.get('S3_BUCKET_NAME', 'default-bucket')
        endpoint_url = config.get('S3_ENDPOINT_URL')
        public_url = config.get('S3_PUBLIC_URL', endpoint_url)  # ← NOUVEAU
        region = config.get('S3_REGION', 'us-east-1')
        # ...

        self._client = boto3.client(...)

        # ← NOUVEAU : Stocker l'URL publique
        self._endpoint_url = endpoint_url
        self._public_url = public_url

        logger.debug(
            f"S3 client initialized: bucket={self._bucket}, "
            f"region={region}, endpoint={endpoint_url}, "
            f"public_url={public_url}, use_ssl={use_ssl}"  # ← NOUVEAU
        )

        self._initialized = True
        return True, None
```

#### Modification 2 : `generate_presigned_url()` (ligne ~390)

**Remplacer le return par** :

```python
def generate_presigned_url(
    self,
    s3_path: str,
    expires_in: int = 3600,
    response_content_disposition: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """..."""
    # Ensure S3 client is initialized
    initialized, error = self._ensure_initialized()
    if error:
        return None, error

    try:
        # Build parameters for pre-signed URL
        params = {
            'Bucket': self._bucket,
            'Key': s3_path
        }

        if response_content_disposition:
            params['ResponseContentDisposition'] = response_content_disposition

        # Generate pre-signed URL
        url = self._client.generate_presigned_url(
            ClientMethod='get_object',
            Params=params,
            ExpiresIn=expires_in,
            HttpMethod='GET'
        )

        # ← NOUVEAU : Remplacer l'endpoint interne par l'URL publique
        if self._endpoint_url and self._public_url and self._endpoint_url != self._public_url:
            original_url = url
            url = url.replace(self._endpoint_url, self._public_url)
            logger.debug(
                f"Replaced endpoint URL with public URL: "
                f"{self._endpoint_url} → {self._public_url}"
            )
            logger.debug(f"Original URL: {original_url}")
            logger.debug(f"Public URL: {url}")

        logger.info(
            f"Pre-signed URL generated: {s3_path} "
            f"(expires in {expires_in}s)"
        )

        return url, None

    except Exception as e:
        logger.error(
            f"Error generating pre-signed URL (path: {s3_path}): {str(e)}",
            exc_info=True
        )
        return None, f'Pre-signed URL generation failed: {str(e)}'
```

---

### 3. Schema - `backend/app/schemas/document_schema.py`

**Ajouter avant les instanciations (ligne ~470)** :

```python
class DocumentDownloadUrlResponseSchema(Schema):
    """
    Schema for pre-signed download URL response.

    This schema validates the response from the GET /download-url endpoint.
    It returns a temporary pre-signed URL that allows downloading the document
    without authentication.

    Fields:
        download_url (str): Temporary pre-signed S3 URL for download
        expires_in (int): Time until URL expires (seconds)
        expires_at (datetime): Exact timestamp when URL expires (ISO 8601)
        filename (str): Document filename
        mime_type (str): MIME type of the document
        file_size (int): File size in bytes

    Example response:
        {
            "download_url": "http://localhost:9000/saas-documents/tenants/.../file.pdf?Signature=...",
            "expires_in": 3600,
            "expires_at": "2024-01-01T01:00:00Z",
            "filename": "report.pdf",
            "mime_type": "application/pdf",
            "file_size": 1048576
        }

    Security notes:
        - The download_url is temporary and expires after expires_in seconds
        - Anyone with the URL can download the file until expiration
        - URLs should not be logged or stored permanently
        - Consider using short expiration times for sensitive documents
    """
    download_url = fields.Str(dump_only=True, required=True)
    expires_in = fields.Int(dump_only=True)
    expires_at = fields.DateTime(dump_only=True)
    filename = fields.Str(dump_only=True)
    mime_type = fields.Str(dump_only=True)
    file_size = fields.Int(dump_only=True)


# Pre-instantiated schema instances for convenient import
# ...

# Pre-signed URL schema
document_download_url_schema = DocumentDownloadUrlResponseSchema()
```

**Mettre à jour `__all__`** (ligne ~493) :

```python
__all__ = [
    # Schema classes
    'DocumentSchema',
    'DocumentUploadSchema',
    'DocumentUpdateSchema',
    'DocumentResponseSchema',
    'DocumentWithFileResponseSchema',
    'DocumentDownloadUrlResponseSchema',  # ← NOUVEAU

    # Pre-instantiated schema instances
    'document_schema',
    'document_upload_schema',
    'document_update_schema',
    'document_response_schema',
    'document_with_file_response_schema',
    'documents_response_schema',
    'document_download_url_schema',  # ← NOUVEAU
]
```

---

### 4. Route - `backend/app/routes/documents.py`

**Ajouter après la route `download_document()` (ligne ~636)** :

```python
@documents_bp.route('/<tenant_id>/documents/<document_id>/download-url', methods=['GET'])
@jwt_required_custom
def get_download_url(tenant_id: str, document_id: str):
    """
    Generate pre-signed S3 URL for document download.

    Returns a temporary URL that allows downloading the document without authentication.
    The URL expires after the specified time (default: 1 hour, max: 24 hours).

    This is useful for scenarios where including a Bearer Token in the URL is not
    practical or secure (e.g., email links, browser downloads, external integrations).

    **Workflow**:
    1. Client calls this endpoint with JWT Bearer Token (authenticated)
    2. API validates permissions and generates temporary S3 pre-signed URL
    3. Client downloads file directly from S3 using the URL (no authentication needed)
    4. URL expires after the specified time

    **Authentication**: JWT required
    **Authorization**: Must have read permission on tenant

    **URL Parameters**:
        tenant_id: UUID of the tenant
        document_id: UUID of the document

    **Query Parameters**:
        expires_in: URL expiration time in seconds (default: 3600, min: 60, max: 86400)

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Download URL generated successfully",
                "data": {
                    "download_url": "http://localhost:9000/saas-documents/tenants/.../file.pdf?Signature=...",
                    "expires_in": 3600,
                    "expires_at": "2024-01-01T01:00:00Z",
                    "filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 1048576
                }
            }

        400 Bad Request: Invalid expires_in parameter
        403 Forbidden: User does not have read permission
        404 Not Found: Tenant or document not found
        500 Internal Server Error: Failed to generate URL

    **Example**:
        GET /api/tenants/123e4567-e89b-12d3-a456-426614174000/documents/456e7890-e89b-12d3-a456-426614174001/download-url?expires_in=3600
        Authorization: Bearer <access_token>

    **Security**:
        - Requires JWT authentication to generate URL
        - Verifies tenant access and read permission
        - URLs are temporary and expire automatically
        - Downloads are logged for audit purposes
        - S3 bucket must be private (pre-signed URLs required)

    **Use cases**:
        - Email links for document sharing
        - Browser downloads without custom headers
        - Mobile app downloads
        - External system integrations
        - Temporary public access to private documents
    """
    try:
        user_id = g.user_id

        # Validate expires_in parameter
        expires_in = request.args.get('expires_in', 3600, type=int)
        if expires_in < 60 or expires_in > 86400:  # 1 min to 24 hours
            logger.warning(f"Invalid expires_in parameter: {expires_in}")
            return bad_request('expires_in must be between 60 and 86400 seconds (1 min to 24 hours)')

        logger.info(
            f"Download URL request: tenant_id={tenant_id}, document_id={document_id}, "
            f"user_id={user_id}, expires_in={expires_in}s"
        )

        # Check tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            logger.warning(f"Tenant access denied: user_id={user_id}, tenant_id={tenant_id}")
            return error_response

        # Check read permission
        association = UserTenantAssociation.query.filter_by(
            user_id=user_id,
            tenant_id=tenant_id
        ).first()

        if not association.has_permission('read'):
            logger.warning(
                f"Read permission denied: user_id={user_id}, tenant_id={tenant_id}, "
                f"role={association.role}"
            )
            from app.utils.responses import forbidden
            return forbidden('You do not have permission to download files from this tenant')

        # Get tenant database name
        tenant = Tenant.query.get(tenant_id)
        database_name = tenant.database_name

        logger.info(
            f"Access granted: user_id={user_id}, tenant_id={tenant_id}, "
            f"role={association.role}, database={database_name}"
        )

        # Switch to tenant database
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Fetch document with file relationship
            document = session.query(Document).filter_by(id=document_id).first()

            if not document:
                logger.warning(f"Document not found: document_id={document_id}")
                return not_found('Document not found')

            # Get file details
            s3_path = document.file.s3_path
            filename = document.filename
            mime_type = document.mime_type
            file_size = document.file.file_size

            # Generate pre-signed URL
            from datetime import datetime, timedelta

            presigned_url, error = s3_client.generate_presigned_url(
                s3_path=s3_path,
                expires_in=expires_in,
                response_content_disposition=f'attachment; filename="{filename}"'
            )

            if error:
                logger.error(
                    f"Failed to generate pre-signed URL: document_id={document_id}, "
                    f"s3_path={s3_path}, error={error}"
                )
                return internal_error(f'Failed to generate download URL: {error}')

            # Build response
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            response_data = {
                'download_url': presigned_url,
                'expires_in': expires_in,
                'expires_at': expires_at.isoformat() + 'Z',
                'filename': filename,
                'mime_type': mime_type,
                'file_size': file_size
            }

            # Audit log: record URL generation
            logger.info(
                f"AUDIT: Download URL generated - "
                f"user_id={user_id}, "
                f"tenant_id={tenant_id}, "
                f"document_id={document_id}, "
                f"filename={filename}, "
                f"expires_in={expires_in}s, "
                f"role={association.role}"
            )

            return ok(response_data, 'Download URL generated successfully')

    except Exception as e:
        logger.error(f"Error generating download URL: {str(e)}", exc_info=True)
        return internal_error('Failed to generate download URL')
```

---

### 5. Sécurité - `docker-compose.yml`

**Ligne 114 - Modifier la politique du bucket** :

```yaml
# MinIO Client - Create buckets on startup
minio-init:
  image: minio/mc:latest
  container_name: saas-minio-init
  depends_on:
    minio:
      condition: service_healthy
  entrypoint: >
    /bin/sh -c "
    /usr/bin/mc alias set myminio http://minio:9000 minioadmin minioadmin;
    /usr/bin/mc mb myminio/saas-documents --ignore-existing;
    /usr/bin/mc policy set private myminio/saas-documents;
    exit 0;
    "
  networks:
    - saas-network
```

**Changement** : `public` → `private`

**Options de politique MinIO** :
- `private` : Accès uniquement avec credentials/pré-signed URLs (RECOMMANDÉ pour SaaS)
- `download` : Lecture publique, écriture avec auth
- `upload` : Écriture publique, lecture avec auth
- `public` : Lecture/écriture publique (DANGEREUX, actuel)

**Après modification, redémarrer** :

```bash
docker-compose restart minio minio-init
```

---

## Exemples d'utilisation

### Exemple 1 : Client curl (développement)

```bash
# Étape 1 : Authentification
TOKEN=$(curl -s -X POST http://localhost:4999/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "admin123"
  }' | jq -r '.data.access_token')

echo "Token: $TOKEN"

# Étape 2 : Obtenir l'URL pré-signée (expire dans 1h)
DOWNLOAD_RESPONSE=$(curl -s -X GET \
  "http://localhost:4999/api/tenants/9b2cf18a-243d-4ceb-8b87-9fcc4babbb54/documents/542cec7a-751b-4543-8207-531d6769a978/download-url?expires_in=3600" \
  -H "Authorization: Bearer $TOKEN")

echo "Response: $DOWNLOAD_RESPONSE"

# Extraire l'URL de téléchargement
DOWNLOAD_URL=$(echo $DOWNLOAD_RESPONSE | jq -r '.data.download_url')
FILENAME=$(echo $DOWNLOAD_RESPONSE | jq -r '.data.filename')

echo "Download URL: $DOWNLOAD_URL"
echo "Filename: $FILENAME"

# Étape 3 : Télécharger le fichier (SANS Bearer Token !)
curl -o "/tmp/$FILENAME" "$DOWNLOAD_URL"

echo "File downloaded to: /tmp/$FILENAME"
```

### Exemple 2 : Client JavaScript (frontend)

```javascript
// Étape 1 : Obtenir l'URL pré-signée (avec JWT)
async function getDownloadUrl(tenantId, documentId) {
  const response = await fetch(
    `http://localhost:4999/api/tenants/${tenantId}/documents/${documentId}/download-url?expires_in=3600`,
    {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = await response.json();
  return data.data;
}

// Étape 2 : Télécharger le fichier (sans JWT)
async function downloadDocument(tenantId, documentId) {
  try {
    // Obtenir l'URL pré-signée
    const { download_url, filename, expires_at } = await getDownloadUrl(tenantId, documentId);

    console.log('Download URL:', download_url);
    console.log('Expires at:', expires_at);

    // Option A : Ouvrir dans un nouvel onglet
    window.open(download_url, '_blank');

    // Option B : Télécharger via anchor tag
    const link = document.createElement('a');
    link.href = download_url;
    link.download = filename;
    link.click();

    // Option C : Fetch et créer blob (pour traitement custom)
    const fileResponse = await fetch(download_url);
    const blob = await fileResponse.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);

  } catch (error) {
    console.error('Download failed:', error);
    alert('Failed to download document');
  }
}

// Utilisation
downloadDocument('9b2cf18a-243d-4ceb-8b87-9fcc4babbb54', '542cec7a-751b-4543-8207-531d6769a978');
```

### Exemple 3 : Lien email

```html
<!-- Backend génère l'URL et l'envoie par email -->
<!-- L'URL expire dans 24h (86400 secondes) -->

<html>
  <body>
    <h2>Document partagé : {{ filename }}</h2>
    <p>Vous avez reçu un document de {{ sender_name }}.</p>

    <p>
      <a href="{{ download_url }}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
        Télécharger le document
      </a>
    </p>

    <p style="color: #666; font-size: 12px;">
      Ce lien expire le {{ expires_at }} (dans 24 heures).<br>
      Taille du fichier : {{ file_size_mb }} MB
    </p>
  </body>
</html>
```

**Code backend pour générer le lien email** :

```python
from flask import current_app
import requests

def send_document_email(user_email, tenant_id, document_id):
    # Générer URL pré-signée (expire dans 24h)
    url = f"{current_app.config['API_BASE_URL']}/api/tenants/{tenant_id}/documents/{document_id}/download-url?expires_in=86400"

    response = requests.get(
        url,
        headers={'Authorization': f'Bearer {get_admin_token()}'}
    )

    data = response.json()['data']

    # Envoyer email avec l'URL
    send_email(
        to=user_email,
        subject=f"Document: {data['filename']}",
        template='document_share.html',
        context={
            'download_url': data['download_url'],
            'filename': data['filename'],
            'expires_at': data['expires_at'],
            'file_size_mb': round(data['file_size'] / (1024 * 1024), 2)
        }
    )
```

### Exemple 4 : Python avec requests

```python
import requests
import os

# Configuration
API_BASE_URL = "http://localhost:4999"
TENANT_ID = "9b2cf18a-243d-4ceb-8b87-9fcc4babbb54"
DOCUMENT_ID = "542cec7a-751b-4543-8207-531d6769a978"

# Étape 1 : Authentification
login_response = requests.post(
    f"{API_BASE_URL}/api/auth/login",
    json={
        "email": "admin@example.com",
        "password": "admin123"
    }
)
token = login_response.json()["data"]["access_token"]

# Étape 2 : Obtenir URL pré-signée
download_url_response = requests.get(
    f"{API_BASE_URL}/api/tenants/{TENANT_ID}/documents/{DOCUMENT_ID}/download-url",
    headers={"Authorization": f"Bearer {token}"},
    params={"expires_in": 3600}
)

data = download_url_response.json()["data"]
download_url = data["download_url"]
filename = data["filename"]

print(f"Download URL: {download_url}")
print(f"Expires at: {data['expires_at']}")

# Étape 3 : Télécharger le fichier (SANS authentification)
file_response = requests.get(download_url, stream=True)

with open(f"/tmp/{filename}", "wb") as f:
    for chunk in file_response.iter_content(chunk_size=8192):
        f.write(chunk)

print(f"File downloaded: /tmp/{filename}")
```

---

## Tests

### Tests unitaires

**Fichier** : `backend/tests/unit/test_s3_client_public_url.py`

```python
"""
Unit tests for S3 client public URL replacement functionality.
"""
import pytest
from unittest.mock import Mock, patch
from app.utils.s3_client import S3Client


class TestS3ClientPublicUrl:
    """Test S3 client public URL replacement in pre-signed URLs."""

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_generate_presigned_url_replaces_internal_url(self, mock_boto3, mock_app):
        """Test that internal endpoint URL is replaced with public URL."""
        # Setup
        mock_app.config = {
            'S3_BUCKET': 'test-bucket',
            'S3_ENDPOINT_URL': 'http://minio:9000',
            'S3_PUBLIC_URL': 'http://localhost:9000',
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': False
        }

        # Mock boto3 client
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # Mock presigned URL with internal endpoint
        internal_url = 'http://minio:9000/test-bucket/file.pdf?Signature=abc123'
        mock_client.generate_presigned_url.return_value = internal_url

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='tenants/test/file.pdf',
            expires_in=3600
        )

        # Assert
        assert error is None
        assert url is not None
        assert 'localhost:9000' in url
        assert 'minio:9000' not in url
        assert url == 'http://localhost:9000/test-bucket/file.pdf?Signature=abc123'

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_generate_presigned_url_no_replacement_when_same(self, mock_boto3, mock_app):
        """Test that URL is not modified when endpoint and public URL are the same."""
        # Setup
        mock_app.config = {
            'S3_BUCKET': 'test-bucket',
            'S3_ENDPOINT_URL': 'http://localhost:9000',
            'S3_PUBLIC_URL': 'http://localhost:9000',  # Same as endpoint
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': False
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        original_url = 'http://localhost:9000/test-bucket/file.pdf?Signature=abc123'
        mock_client.generate_presigned_url.return_value = original_url

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='tenants/test/file.pdf',
            expires_in=3600
        )

        # Assert
        assert error is None
        assert url == original_url

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_generate_presigned_url_production_https(self, mock_boto3, mock_app):
        """Test URL replacement with production HTTPS domain."""
        # Setup
        mock_app.config = {
            'S3_BUCKET': 'prod-bucket',
            'S3_ENDPOINT_URL': 'http://minio:9000',
            'S3_PUBLIC_URL': 'https://documents.example.com',
            'S3_REGION': 'eu-west-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': True
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        internal_url = 'http://minio:9000/prod-bucket/file.pdf?Signature=xyz789'
        mock_client.generate_presigned_url.return_value = internal_url

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='tenants/acme/file.pdf',
            expires_in=7200
        )

        # Assert
        assert error is None
        assert url == 'https://documents.example.com/prod-bucket/file.pdf?Signature=xyz789'
        assert 'minio:9000' not in url
```

### Tests d'intégration

**Fichier** : `backend/tests/integration/test_document_download_url.py`

```python
"""
Integration tests for document download URL endpoint.
"""
import pytest
from app import create_app
from app.models.user import User
from app.models.tenant import Tenant
from app.models.user_tenant_association import UserTenantAssociation


class TestDocumentDownloadUrl:
    """Integration tests for GET /download-url endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        app = create_app('testing')
        with app.test_client() as client:
            yield client

    @pytest.fixture
    def auth_headers(self, client):
        """Get authentication headers with valid JWT token."""
        response = client.post('/api/auth/login', json={
            'email': 'admin@example.com',
            'password': 'admin123'
        })
        token = response.json['data']['access_token']
        return {'Authorization': f'Bearer {token}'}

    def test_get_download_url_success(self, client, auth_headers, tenant_id, document_id):
        """Test successful download URL generation."""
        response = client.get(
            f'/api/tenants/{tenant_id}/documents/{document_id}/download-url',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json['data']
        assert 'download_url' in data
        assert 'expires_in' in data
        assert 'expires_at' in data
        assert 'filename' in data
        assert 'mime_type' in data
        assert 'file_size' in data

        # Verify URL is public (contains localhost:9000, not minio:9000)
        assert 'localhost:9000' in data['download_url']
        assert 'minio:9000' not in data['download_url']

    def test_get_download_url_with_custom_expiration(self, client, auth_headers, tenant_id, document_id):
        """Test URL generation with custom expiration time."""
        response = client.get(
            f'/api/tenants/{tenant_id}/documents/{document_id}/download-url?expires_in=7200',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json['data']
        assert data['expires_in'] == 7200

    def test_get_download_url_invalid_expiration(self, client, auth_headers, tenant_id, document_id):
        """Test that invalid expiration time is rejected."""
        # Too short
        response = client.get(
            f'/api/tenants/{tenant_id}/documents/{document_id}/download-url?expires_in=30',
            headers=auth_headers
        )
        assert response.status_code == 400

        # Too long
        response = client.get(
            f'/api/tenants/{tenant_id}/documents/{document_id}/download-url?expires_in=100000',
            headers=auth_headers
        )
        assert response.status_code == 400

    def test_get_download_url_no_auth(self, client, tenant_id, document_id):
        """Test that endpoint requires authentication."""
        response = client.get(
            f'/api/tenants/{tenant_id}/documents/{document_id}/download-url'
        )
        assert response.status_code == 401

    def test_get_download_url_no_read_permission(self, client, tenant_id, document_id):
        """Test that read permission is required."""
        # Login as user without read permission (if such user exists in test data)
        # This test depends on your test data setup
        pass

    def test_get_download_url_document_not_found(self, client, auth_headers, tenant_id):
        """Test 404 when document doesn't exist."""
        fake_document_id = '00000000-0000-0000-0000-000000000000'
        response = client.get(
            f'/api/tenants/{tenant_id}/documents/{fake_document_id}/download-url',
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_download_with_presigned_url(self, client, auth_headers, tenant_id, document_id):
        """Test that generated URL actually works for download."""
        # Step 1: Get download URL
        response = client.get(
            f'/api/tenants/{tenant_id}/documents/{document_id}/download-url',
            headers=auth_headers
        )
        assert response.status_code == 200
        download_url = response.json['data']['download_url']

        # Step 2: Download file using the URL (without auth!)
        import requests
        file_response = requests.get(download_url)

        assert file_response.status_code == 200
        assert len(file_response.content) > 0
        assert file_response.headers['Content-Type'] == response.json['data']['mime_type']
```

### Tests manuels

**Script de test complet** : `backend/scripts/test_download_url.sh`

```bash
#!/bin/bash

# Test complet de la fonctionnalité d'URL pré-signée
# Usage: ./scripts/test_download_url.sh

set -e  # Exit on error

API_BASE_URL="http://localhost:4999"
TENANT_ID="9b2cf18a-243d-4ceb-8b87-9fcc4babbb54"
DOCUMENT_ID="542cec7a-751b-4543-8207-531d6769a978"

echo "=== Test Download URL Feature ==="
echo ""

# Couleurs pour output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Étape 1 : Authentification
echo -e "${YELLOW}Step 1: Authentication${NC}"
TOKEN=$(curl -s -X POST "$API_BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "admin123"
  }' | jq -r '.data.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo -e "${RED}❌ Authentication failed${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Authenticated successfully${NC}"
echo "Token: ${TOKEN:0:20}..."
echo ""

# Étape 2 : Obtenir URL pré-signée
echo -e "${YELLOW}Step 2: Get pre-signed download URL${NC}"
DOWNLOAD_RESPONSE=$(curl -s -X GET \
  "$API_BASE_URL/api/tenants/$TENANT_ID/documents/$DOCUMENT_ID/download-url?expires_in=3600" \
  -H "Authorization: Bearer $TOKEN")

echo "Response: $DOWNLOAD_RESPONSE"

DOWNLOAD_URL=$(echo $DOWNLOAD_RESPONSE | jq -r '.data.download_url')
FILENAME=$(echo $DOWNLOAD_RESPONSE | jq -r '.data.filename')
EXPIRES_AT=$(echo $DOWNLOAD_RESPONSE | jq -r '.data.expires_at')
FILE_SIZE=$(echo $DOWNLOAD_RESPONSE | jq -r '.data.file_size')

if [ -z "$DOWNLOAD_URL" ] || [ "$DOWNLOAD_URL" = "null" ]; then
  echo -e "${RED}❌ Failed to get download URL${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Download URL generated${NC}"
echo "Filename: $FILENAME"
echo "Expires at: $EXPIRES_AT"
echo "File size: $FILE_SIZE bytes"
echo "URL: $DOWNLOAD_URL"
echo ""

# Vérifier que l'URL est publique (localhost:9000, pas minio:9000)
if [[ $DOWNLOAD_URL == *"localhost:9000"* ]]; then
  echo -e "${GREEN}✓ URL is public (contains localhost:9000)${NC}"
elif [[ $DOWNLOAD_URL == *"minio:9000"* ]]; then
  echo -e "${RED}❌ URL is internal (contains minio:9000)${NC}"
  exit 1
else
  echo -e "${YELLOW}⚠ URL format unexpected${NC}"
fi
echo ""

# Étape 3 : Télécharger le fichier (SANS Bearer Token)
echo -e "${YELLOW}Step 3: Download file using pre-signed URL (no auth required)${NC}"
OUTPUT_FILE="/tmp/$FILENAME"

HTTP_CODE=$(curl -s -w "%{http_code}" -o "$OUTPUT_FILE" "$DOWNLOAD_URL")

if [ "$HTTP_CODE" = "200" ]; then
  echo -e "${GREEN}✓ File downloaded successfully${NC}"
  echo "Saved to: $OUTPUT_FILE"
  echo "File size: $(wc -c < "$OUTPUT_FILE") bytes"

  # Vérifier le hash MD5 si possible
  if command -v md5sum &> /dev/null; then
    MD5=$(md5sum "$OUTPUT_FILE" | awk '{print $1}')
    echo "MD5: $MD5"
  fi

  # Vérifier le type MIME
  if command -v file &> /dev/null; then
    FILE_TYPE=$(file -b --mime-type "$OUTPUT_FILE")
    echo "MIME type: $FILE_TYPE"
  fi
else
  echo -e "${RED}❌ Download failed (HTTP $HTTP_CODE)${NC}"
  cat "$OUTPUT_FILE"
  exit 1
fi
echo ""

# Étape 4 : Tester expiration invalide
echo -e "${YELLOW}Step 4: Test invalid expiration parameter${NC}"
INVALID_RESPONSE=$(curl -s -X GET \
  "$API_BASE_URL/api/tenants/$TENANT_ID/documents/$DOCUMENT_ID/download-url?expires_in=30" \
  -H "Authorization: Bearer $TOKEN")

if echo "$INVALID_RESPONSE" | jq -e '.success == false' > /dev/null; then
  echo -e "${GREEN}✓ Invalid expiration correctly rejected${NC}"
else
  echo -e "${RED}❌ Invalid expiration should be rejected${NC}"
  exit 1
fi
echo ""

# Étape 5 : Tester sans authentification
echo -e "${YELLOW}Step 5: Test without authentication${NC}"
UNAUTH_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
  "$API_BASE_URL/api/tenants/$TENANT_ID/documents/$DOCUMENT_ID/download-url")

HTTP_CODE=$(echo "$UNAUTH_RESPONSE" | tail -n 1)
if [ "$HTTP_CODE" = "401" ]; then
  echo -e "${GREEN}✓ Unauthenticated request correctly rejected${NC}"
else
  echo -e "${RED}❌ Should require authentication (got HTTP $HTTP_CODE)${NC}"
  exit 1
fi
echo ""

echo -e "${GREEN}=== All tests passed! ===${NC}"
```

**Rendre exécutable** :

```bash
chmod +x backend/scripts/test_download_url.sh
```

**Exécuter** :

```bash
./backend/scripts/test_download_url.sh
```

---

## Migration production

### Checklist de déploiement

- [ ] **Configuration** :
  - [ ] Ajouter `S3_PUBLIC_URL=https://documents.example.com` dans variables d'environnement production
  - [ ] Si Vault : ajouter `public_url` dans `secret/saas-project/production/s3`
  - [ ] Vérifier que le DNS `documents.example.com` pointe vers MinIO/S3

- [ ] **DNS & SSL** :
  - [ ] Configurer DNS pour `documents.example.com`
  - [ ] Obtenir certificat SSL (Let's Encrypt, AWS Certificate Manager, etc.)
  - [ ] Configurer reverse proxy (Nginx, CloudFront, etc.) si nécessaire

- [ ] **Sécurité** :
  - [ ] Bucket MinIO/S3 en mode `private` (pas `public`)
  - [ ] Vérifier CORS si téléchargements cross-origin
  - [ ] Configurer Content-Security-Policy si applicable
  - [ ] Activer logging des accès S3 (audit trail)

- [ ] **Tests** :
  - [ ] Tester génération d'URL avec domaine production
  - [ ] Vérifier que les URLs expirées retournent 403 Forbidden
  - [ ] Tester download depuis différents clients (navigateurs, mobile, curl)
  - [ ] Load testing : générer 1000 URLs et télécharger en parallèle

- [ ] **Monitoring** :
  - [ ] Ajouter alertes sur erreurs génération d'URLs
  - [ ] Surveiller latence endpoint `/download-url`
  - [ ] Tracking usage : nombre d'URLs générées par jour
  - [ ] Monitoring bande passante S3

### Configuration Nginx (reverse proxy pour MinIO)

Si vous utilisez Nginx comme reverse proxy devant MinIO :

```nginx
# /etc/nginx/sites-available/documents.example.com

upstream minio_backend {
    server minio:9000;
}

server {
    listen 443 ssl http2;
    server_name documents.example.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/documents.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/documents.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";

    # Proxy to MinIO
    location / {
        proxy_pass http://minio_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Important for large files
        client_max_body_size 100M;
        proxy_buffering off;

        # CORS (if needed)
        add_header Access-Control-Allow-Origin * always;
        add_header Access-Control-Allow-Methods "GET, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Range" always;
    }

    # Health check
    location /health {
        access_log off;
        return 200 "healthy\n";
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name documents.example.com;
    return 301 https://$host$request_uri;
}
```

### Configuration CORS MinIO

Si les téléchargements se font depuis un domaine différent (cross-origin) :

```bash
# Configurer CORS sur le bucket MinIO
mc alias set myminio https://documents.example.com minioadmin minioadmin

mc admin config set myminio api cors_allow_origin="https://app.example.com"
mc admin service restart myminio
```

---

## Dépannage

### Problème 1 : URL contient `minio:9000` au lieu de `localhost:9000`

**Symptôme** :
```json
{
  "download_url": "http://minio:9000/saas-documents/file.pdf?Signature=..."
}
```

**Cause** : `S3_PUBLIC_URL` n'est pas configurée ou le remplacement ne fonctionne pas.

**Solutions** :
1. Vérifier que `S3_PUBLIC_URL` est dans `.env` :
   ```bash
   grep S3_PUBLIC_URL .env
   ```

2. Vérifier que l'application charge la variable :
   ```bash
   docker-compose exec api python -c "from flask import current_app; from app import create_app; app = create_app(); print(app.config.get('S3_PUBLIC_URL'))"
   ```

3. Redémarrer l'API après modification :
   ```bash
   docker-compose restart api
   ```

---

### Problème 2 : Téléchargement retourne 403 Forbidden

**Symptôme** :
```bash
curl -O "http://localhost:9000/saas-documents/file.pdf?Signature=..."
# <?xml version="1.0"?><Error><Code>AccessDenied</Code></Error>
```

**Causes possibles** :

1. **Bucket est privé mais signature invalide** :
   - Vérifier que l'URL est complète (ne pas tronquer les paramètres)
   - Vérifier que l'URL n'a pas expiré

2. **Credentials S3 incorrects** :
   ```bash
   # Vérifier credentials dans Vault/env
   docker-compose exec api env | grep S3_
   ```

3. **Politique bucket incorrecte** :
   ```bash
   # Vérifier politique
   docker exec -it saas-minio mc policy get myminio/saas-documents
   ```

---

### Problème 3 : URL expire trop vite/trop lentement

**Configuration** :

- **Min** : 60 secondes (1 minute)
- **Max** : 86400 secondes (24 heures)
- **Défaut** : 3600 secondes (1 heure)

**Changer pour une requête** :
```bash
curl "...download-url?expires_in=7200"  # 2 heures
```

**Changer le défaut** : Modifier ligne dans `documents.py` :
```python
expires_in = request.args.get('expires_in', 7200, type=int)  # 2h par défaut
```

---

### Problème 4 : Production - DNS ne résout pas

**Symptôme** : `documents.example.com` ne résout pas ou pointe vers mauvaise IP.

**Diagnostic** :
```bash
# Tester résolution DNS
dig documents.example.com

# Tester connexion
curl -I https://documents.example.com/saas-documents/
```

**Solutions** :
1. Vérifier enregistrement DNS (A ou CNAME)
2. Attendre propagation DNS (jusqu'à 48h)
3. Tester avec IP directe temporairement
4. Vérifier firewall/security groups

---

### Problème 5 : Logs montrent erreurs génération d'URL

**Logs à vérifier** :
```bash
# Logs Flask API
docker-compose logs -f api | grep "download-url"

# Logs MinIO
docker-compose logs -f minio
```

**Erreurs communes** :

1. **`NoSuchKey`** : Fichier n'existe pas dans S3
2. **`SignatureDoesNotMatch`** : Credentials S3 incorrects
3. **`InvalidArgument`** : Paramètres génération URL invalides

---

## Annexes

### Diagramme d'architecture global

```
                    ┌────────────────────────────────────────┐
                    │          Client Browser/App            │
                    └──────────────┬────────────────────────┘
                                   │
                    ┌──────────────┴────────────────────┐
                    │                                   │
                    │  1. GET /download-url             │  3. GET /bucket/file.pdf
                    │     Authorization: Bearer JWT     │     ?Signature=xxx (no auth!)
                    │                                   │
          ┌─────────▼──────────┐            ┌──────────▼──────────┐
          │   Flask API        │            │   MinIO (S3)        │
          │   Port: 4999       │            │   Port: 9000        │
          │                    │            │                     │
          │  Routes:           │            │  Bucket: private    │
          │  - /download       │            │  - saas-documents   │
          │  - /download-url   │◄───────────┤                     │
          │                    │  2. Sign   │  Policy: private    │
          └─────────┬──────────┘            └─────────────────────┘
                    │
                    │ 4. Check permissions
                    │    & Get document
                    │
          ┌─────────▼──────────┐
          │  PostgreSQL        │
          │  Port: 5432        │
          │                    │
          │  - saas_platform   │ (main DB)
          │  - tenant_xxx      │ (tenant DBs)
          └────────────────────┘
```

### Comparaison : Routes `/download` vs `/download-url`

| Critère | `/download` (proxy) | `/download-url` (pré-signée) |
|---------|---------------------|------------------------------|
| **Authentification** | Bearer Token requis | JWT pour obtenir URL, puis public |
| **Performance** | Proxy via Flask (lent) | Direct S3 (rapide) |
| **Bande passante serveur** | Haute | Basse |
| **Cas d'usage** | Apps avec auth | Emails, partage, intégrations |
| **Sécurité** | Token dans header | URL temporaire |
| **Expiration** | N/A (token expire) | Configurable (1h-24h) |
| **Scalabilité** | Limitée (bottleneck) | Excellente |
| **Audit** | Log chaque download | Log génération URL |

### Références

- [AWS S3 Pre-signed URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ShareObjectPreSignedURL.html)
- [MinIO Pre-signed URLs](https://min.io/docs/minio/linux/developers/python/API.html#presigned_get_object)
- [Boto3 generate_presigned_url](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.generate_presigned_url)

---

## Changelog

### Version 1.0 (2024-01-XX)

- Implémentation initiale
- Support dev (localhost:9000) et production (https://documents.example.com)
- Bucket privé MinIO
- Route `/download-url` avec JWT
- Expiration configurable 60s - 24h
- Audit logging complet
- Tests unitaires et intégration

---

**Document créé le** : 2024-01-XX
**Dernière mise à jour** : 2024-01-XX
**Mainteneur** : Équipe Backend
