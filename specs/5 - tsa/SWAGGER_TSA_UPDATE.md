# Swagger.yaml - Mise à jour TSA Timestamping

## Résumé des modifications

Le fichier `backend/swagger.yaml` a été mis à jour pour documenter l'intégralité de la fonctionnalité d'horodatage TSA RFC 3161 implémentée dans le projet.

## Nouveautés

### 1. Nouveau tag

```yaml
- name: TSA Timestamping
  description: RFC 3161 timestamp authority integration for file timestamping
```

### 2. Nouveaux schémas

#### TSATimestamp
Schema complet pour les métadonnées de timestamp :
- `status` : success | error | pending
- `token` : Token RFC 3161 encodé en base64
- `algorithm` : sha256
- `serial_number` : Numéro de série hexadécimal
- `gen_time` : Horodatage ISO 8601
- `tsa_authority` : "DigiCert Timestamp Authority"
- `policy_oid` : "2.16.840.1.114412.7.1"
- `tsa_certificate` : Certificat X.509 en base64
- `certificate_chain` : Chaîne complète (intermédiaire + racine)
- `timestamped_at` : Date d'horodatage
- `task_id` : ID Celery pour suivi
- `error_message` : Message d'erreur éventuel

#### File (mis à jour)
- Ajout du champ `sha256_hash` pour l'horodatage TSA
- Ajout de `file_metadata.tsa_timestamp` référençant le schéma TSATimestamp

### 3. Nouvelles routes

#### GET /api/tenants/{tenant_id}/files/{file_id}/timestamp/download

**Description** : Télécharge le token TSA au format .tsr (RFC 3161 TimeStampResp)

**Authentification** : JWT Bearer token requis

**Réponse 200** :
- Content-Type: `application/timestamp-reply`
- Content-Disposition: `attachment; filename="file_{file_id}_timestamp.tsr"`
- Corps : Fichier binaire .tsr (~6 KB)

**Exemple d'utilisation** :
```bash
# Télécharger le timestamp
curl -o timestamp.tsr \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:4999/api/tenants/{tenant_id}/files/{file_id}/timestamp/download

# Vérifier avec OpenSSL
openssl ts -verify \
  -data original_file.pdf \
  -in timestamp.tsr \
  -CAfile digicert_chain.pem
```

**Réponses** :
- 200 : Timestamp téléchargé avec succès
- 400 : Fichier sans timestamp valide
- 403 : Non autorisé
- 404 : Fichier introuvable

---

#### POST /api/tenants/{tenant_id}/files/{file_id}/timestamp/create

**Description** : Déclenche manuellement l'horodatage d'un fichier (admin uniquement)

**Authentification** : JWT Bearer token + rôle admin

**Corps de requête** (optionnel) :
```json
{
  "force": false
}
```

**Réponse 201** (tâche planifiée) :
```json
{
  "success": true,
  "message": "Timestamp task scheduled",
  "data": {
    "file_id": "uuid",
    "task_id": "celery-task-uuid",
    "status": "pending"
  }
}
```

**Réponse 200** (déjà horodaté avec force=false) :
```json
{
  "success": true,
  "message": "File already timestamped",
  "data": {
    "file_id": "uuid",
    "timestamp": {
      "gen_time": "2025-11-12T13:31:10Z",
      "serial_number": "0x9714975F...",
      "status": "success",
      "tsa_authority": "DigiCert Timestamp Authority"
    }
  }
}
```

**Cas d'usage** :
- Horodatage rétroactif de fichiers existants
- Réessai après échec
- Horodatage de fichiers uploadés avant activation TSA

**Réponses** :
- 201 : Tâche planifiée
- 200 : Déjà horodaté
- 400 : TSA désactivé ou hash SHA-256 manquant
- 403 : Pas admin
- 404 : Fichier introuvable

---

#### POST /api/tenants/{tenant_id}/files/timestamp/bulk

**Description** : Horodatage en masse de plusieurs fichiers (admin uniquement)

**Authentification** : JWT Bearer token + rôle admin

**Corps de requête** :

**Mode 1 - Liste explicite** :
```json
{
  "file_ids": ["uuid1", "uuid2", "uuid3"]
}
```

**Mode 2 - Filtres** :
```json
{
  "filter": {
    "not_timestamped": true,
    "uploaded_before": "2025-01-01T00:00:00Z",
    "uploaded_after": "2024-01-01T00:00:00Z"
  }
}
```

**Mode 3 - Combiné** :
```json
{
  "file_ids": ["uuid1", "uuid2"],
  "filter": {
    "uploaded_before": "2025-01-01T00:00:00Z"
  }
}
```

**Réponse 201** :
```json
{
  "success": true,
  "message": "Bulk timestamp tasks scheduled",
  "data": {
    "total_files": 14,
    "tasks_scheduled": 14,
    "estimated_duration_minutes": 2.4
  }
}
```

**Caractéristiques** :
- Maximum 1000 fichiers par requête
- Tâches espacées de 10 secondes pour respecter les limites API DigiCert
- Traitement asynchrone via Celery
- Estimation de durée fournie

**Réponses** :
- 201 : Tâches planifiées
- 200 : Aucun fichier trouvé
- 400 : Trop de fichiers (>1000), TSA désactivé, ou corps manquant
- 403 : Pas admin

## Exemples de réponses d'erreur

### TSA désactivé
```json
{
  "success": false,
  "message": "TSA timestamping is not enabled for this tenant"
}
```

### Trop de fichiers
```json
{
  "success": false,
  "message": "Maximum 1000 file IDs allowed per bulk request"
}
```

### Corps de requête manquant
```json
{
  "success": false,
  "message": "Request body is required"
}
```

## Documentation OpenSSL

Le swagger inclut un exemple complet de vérification avec OpenSSL :

```bash
# 1. Télécharger le timestamp
curl -o timestamp.tsr \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:4999/api/tenants/{tenant_id}/files/{file_id}/timestamp/download

# 2. Télécharger le fichier original
curl -o original_file.pdf \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:4999/api/tenants/{tenant_id}/documents/{doc_id}/download

# 3. Télécharger la chaîne de certificats DigiCert
curl -o digicert_root.pem https://cacerts.digicert.com/DigiCertAssuredIDRootCA.crt.pem
curl -o digicert_intermediate.pem https://cacerts.digicert.com/DigiCertSHA2AssuredIDTimestampingCA.crt.pem
cat digicert_intermediate.pem digicert_root.pem > digicert_chain.pem

# 4. Vérifier le timestamp
openssl ts -verify \
  -data original_file.pdf \
  -in timestamp.tsr \
  -CAfile digicert_chain.pem

# Sortie attendue : "Verification: OK"
```

## Validation

Le fichier swagger.yaml a été validé avec succès :
```bash
docker run --rm -v "$(pwd)/backend:/workspace" \
  openapitools/openapi-generator-cli validate \
  -i /workspace/swagger.yaml

# Résultat : No validation issues detected.
```

## Accès à la documentation

La documentation Swagger UI est accessible à :
- **Développement** : http://localhost:4999/api/docs
- **Production** : https://api.example.com/api/docs

## Notes de sécurité documentées

Toutes les routes incluent des notes de sécurité explicites :
- Authentification JWT requise
- Restriction par rôle (admin pour create/bulk)
- Validation des permissions sur le tenant
- Audit logging de toutes les opérations
- Protection contre les abus (limite 1000 fichiers, espacement 10s)

## Compatibilité

- OpenAPI 3.0.3
- Conforme RFC 3161 (Time-Stamp Protocol)
- Compatible OpenSSL, Adobe Acrobat, Microsoft Authenticode
- Format MIME standard : `application/timestamp-reply`
