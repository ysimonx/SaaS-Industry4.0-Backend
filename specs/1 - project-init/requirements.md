# Requirements - Backend SaaS Multi-tenant Platform

## 1. Vue d'ensemble

### 1.1 Description
Backend d'une plateforme SaaS multi-tenant permettant la gestion de tenants (clients), d'utilisateurs et de documents avec stockage S3 et traitement asynchrone via Kafka.

### 1.2 Stack Technique
- **Langage** : Python 3.11+
- **Framework Web** : Flask
- **Base de données** : PostgreSQL
- **ORM** : SQLAlchemy
- **Migration** : Flask-Migrate (Alembic)
- **Message Broker** : Apache Kafka
- **Stockage** : S3-compatible object storage
- **Serveur WSGI** : Gunicorn
- **Containerisation** : Docker & Docker Compose
- **Validation** : Marshmallow
- **Documentation API** : Swagger/OpenAPI 3.0
- **Authentification** : JWT (Access Token + Refresh Token)

### 1.3 Port Configuration
- Backend Flask : **4999** (et non 5000)

## 2. Architecture

### 2.1 Architecture en Couches
L'application doit strictement respecter l'architecture suivante :

```
Routes (Controllers) → Services (Business Logic) → Models → Database
```

#### Responsabilités par couche :
1. **Routes Layer** (Controllers)
   - Gestion des endpoints HTTP
   - Validation des permissions/authentification
   - Appel des services
   - Formatage des réponses JSON
   - **NE DOIT PAS** accéder directement à la base de données

2. **Services Layer** (Business Logic)
   - Logique métier
   - Orchestration des opérations complexes
   - Gestion des transactions
   - Communication avec Kafka
   - Seule couche autorisée à manipuler les modèles

3. **Models Layer**
   - Définition des entités SQLAlchemy
   - Relations entre tables
   - Méthodes utilitaires simples sur les modèles

4. **Database Layer**
   - Gestion des connexions
   - Configuration des pools de connexions

### 2.2 Structure des Répertoires
```
backend/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── tenants.py
│   │   ├── documents.py
│   │   └── files.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   ├── tenant_service.py
│   │   ├── document_service.py
│   │   ├── file_service.py
│   │   └── kafka_service.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── user.py
│   │   ├── tenant.py
│   │   ├── document.py
│   │   └── file.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user_schema.py
│   │   ├── tenant_schema.py
│   │   ├── document_schema.py
│   │   └── file_schema.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── s3_client.py
│   │   └── responses.py
│   └── worker/
│       ├── __init__.py
│       ├── consumer.py
│       └── producer.py
├── migrations/
├── tests/
├── docker/
│   ├── Dockerfile.api
│   └── Dockerfile.worker
├── docker-compose.yml
├── requirements.txt
├── swagger.yaml
├── .env.example
└── README.md
```

## 3. Modèles de Données

### 3.1 Base de Données Multi-tenant

#### Architecture Multi-Database
- **Database principale** : `saas_platform`
  - Contient : `users`, `tenants`, `user_tenant_associations`
- **Database par tenant** : `{tenant.database_name}`
  - Contient : `documents`, `files`

### 3.2 Classe Générique (BaseModel)
Tous les modèles héritent de cette classe :
```python
class BaseModel:
    created_at: datetime (UTC)
    updated_at: datetime (UTC)
    created_by: UUID (référence user.id)
```

### 3.3 Modèles Détaillés

#### User (table: users)
```python
- id: UUID (primary key)
- first_name: String(100)
- last_name: String(100)
- email: String(255) (unique, index)
- password_hash: String(255)
- is_active: Boolean (default: True)
- created_at: DateTime (UTC)
- updated_at: DateTime (UTC)
- created_by: UUID (nullable pour auto-création)
```

#### Tenant (table: tenants)
```python
- id: UUID (primary key)
- name: String(255)
- database_name: String(63) (unique, postgres compatible)
- is_active: Boolean (default: True)
- created_at: DateTime (UTC)
- updated_at: DateTime (UTC)
- created_by: UUID
```

#### UserTenantAssociation (table: user_tenant_associations)
```python
- user_id: UUID (FK → users.id)
- tenant_id: UUID (FK → tenants.id)
- role: String(50) (admin, user, viewer)
- joined_at: DateTime (UTC)
- PRIMARY KEY (user_id, tenant_id)
```

#### File (table: files) - Dans chaque database tenant
```python
- id: UUID (primary key)
- md5_hash: String(32) (index)
- s3_path: String(500)
- file_size: BigInteger
- created_at: DateTime (UTC)
- updated_at: DateTime (UTC)
- created_by: UUID
```

#### Document (table: documents) - Dans chaque database tenant
```python
- id: UUID (primary key)
- filename: String(255)
- mime_type: String(100)
- file_id: UUID (FK → files.id)
- user_id: UUID (référence users.id dans saas_platform)
- created_at: DateTime (UTC)
- updated_at: DateTime (UTC)
- created_by: UUID
```

## 4. Endpoints API

### 4.1 Standards de Réponse
Toutes les routes doivent renvoyer une réponse JSON standardisée :

**Succès** :
```json
{
    "success": true,
    "data": {...},
    "message": "Operation successful"
}
```

**Erreur** :
```json
{
    "success": false,
    "error": {
        "code": "ERROR_CODE",
        "message": "Detailed error message",
        "details": {...}
    }
}
```

### 4.2 Codes HTTP Standards
- 200: OK
- 201: Created
- 204: No Content
- 400: Bad Request
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 409: Conflict
- 422: Unprocessable Entity
- 500: Internal Server Error

### 4.3 Blueprints et Routes

#### Auth Blueprint (/api/auth)
- `POST /login` - Authentification (retourne access_token + refresh_token + tenants list)
- `POST /refresh` - Rafraîchir l'access token
- `POST /logout` - Déconnexion
- `POST /register` - Création de compte

#### Users Blueprint (/api/users)
- `GET /me` - Profil utilisateur courant
- `PUT /me` - Modifier le profil
- `GET /me/tenants` - Liste des tenants de l'utilisateur

#### Tenants Blueprint (/api/tenants)
- `GET /` - Liste des tenants
- `POST /` - Créer un tenant
- `GET /{tenant_id}` - Détails d'un tenant
- `PUT /{tenant_id}` - Modifier un tenant
- `DELETE /{tenant_id}` - Supprimer un tenant
- `POST /{tenant_id}/users` - Ajouter un utilisateur au tenant
- `DELETE /{tenant_id}/users/{user_id}` - Retirer un utilisateur

#### Documents Blueprint (/api/tenants/{tenant_id}/documents)
- `GET /` - Liste des documents
- `POST /` - Uploader un document
- `GET /{document_id}` - Détails d'un document
- `GET /{document_id}/download` - Télécharger un document
- `PUT /{document_id}` - Modifier les métadonnées
- `DELETE /{document_id}` - Supprimer un document

#### Files Blueprint (/api/tenants/{tenant_id}/files)
- `GET /` - Liste des fichiers
- `GET /{file_id}` - Détails d'un fichier
- `DELETE /{file_id}` - Supprimer un fichier (si non référencé)

#### Kafka Demo Blueprint (/api/demo/kafka)
- `POST /produce` - Produire un message de test
- `GET /consume` - Statut du consumer de test

## 5. Services (Business Logic Layer)

### 5.1 AuthService
- `authenticate(email, password)` → tokens + tenants
- `refresh_token(refresh_token)` → new access_token
- `logout(user_id)`
- `register(user_data)`

### 5.2 UserService
- `get_user_by_id(user_id)`
- `update_user(user_id, user_data)`
- `get_user_tenants(user_id)`

### 5.3 TenantService
- `create_tenant(tenant_data)` - Crée tenant + database
- `get_tenant(tenant_id)`
- `update_tenant(tenant_id, tenant_data)`
- `delete_tenant(tenant_id)`
- `add_user_to_tenant(tenant_id, user_id, role)`
- `remove_user_from_tenant(tenant_id, user_id)`

### 5.4 DocumentService
- `create_document(tenant_id, file, metadata)`
- `get_document(tenant_id, document_id)`
- `list_documents(tenant_id, filters)`
- `update_document(tenant_id, document_id, metadata)`
- `delete_document(tenant_id, document_id)`

### 5.5 FileService
- `upload_file(tenant_id, file_content)` → file_id
- `get_file(tenant_id, file_id)`
- `check_duplicate(tenant_id, md5_hash)`
- `delete_orphaned_files(tenant_id)`

### 5.6 KafkaService
- `produce_message(topic, message)`
- `consume_messages(topic, callback)`

## 6. Kafka Integration

### 6.1 Topics
- `tenant.created` - Création d'un tenant
- `tenant.deleted` - Suppression d'un tenant
- `document.uploaded` - Upload de document
- `document.deleted` - Suppression de document
- `file.process` - Traitement asynchrone de fichier
- `audit.log` - Logs d'audit

### 6.2 Message Format
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

### 6.3 Worker Container
Programme Python séparé qui :
- Consomme les messages Kafka
- Utilise les mêmes services que l'API
- Traite les tâches asynchrones (upload S3, création de database, etc.)

## 7. Stockage S3

### 7.1 Structure des Répertoires
```
bucket/
├── tenants/
│   ├── {tenant_id}/
│   │   ├── files/
│   │   │   ├── {year}/
│   │   │   │   ├── {month}/
│   │   │   │   │   └── {file_id}_{md5_hash}
```

### 7.2 Configuration
Les informations de connexion S3 sont déjà disponibles et doivent être configurées via variables d'environnement :
- `S3_ENDPOINT`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `S3_BUCKET`
- `S3_REGION`

### 7.3 Stratégie de Déduplication
- Au sein d'un tenant : déduplication basée sur MD5
- Entre tenants : isolation complète (duplication acceptée)

## 8. Validation des Données

### 8.1 Marshmallow Schemas
Utiliser Marshmallow pour la validation avec `load_default` (et non `missing`) :

```python
class UserSchema(Schema):
    email = fields.Email(required=True)
    first_name = fields.Str(required=True, validate=Length(min=1, max=100))
    last_name = fields.Str(required=True, validate=Length(min=1, max=100))
    password = fields.Str(required=True, load_only=True, validate=Length(min=8))
```

### 8.2 Validation Points
- Validation à l'entrée (routes)
- Validation avant sauvegarde (services)
- Validation des réponses (serialization)

## 9. Sécurité

### 9.1 Authentification JWT
- Access Token : durée de vie 15 minutes
- Refresh Token : durée de vie 7 jours
- Stockage des tokens côté client uniquement
- Blacklist pour les tokens révoqués

### 9.2 Multi-tenancy Isolation
- Vérification systématique de l'appartenance user/tenant
- Connection string dynamique par tenant
- Isolation complète des données entre tenants

### 9.3 Permissions
- Vérification des rôles (admin, user, viewer)
- Middleware de vérification des permissions
- Audit trail de toutes les actions

## 10. Docker Configuration

### 10.1 Services Docker Compose
```yaml
services:
  - postgresql (port 5432)
  - kafka + zookeeper
  - api (Flask/Gunicorn sur port 4999)
  - worker (Python Kafka consumer)
```

### 10.2 Dockerfiles
- `Dockerfile.api` : Image pour l'API Flask
- `Dockerfile.worker` : Image pour le worker Kafka

## 11. Documentation

### 11.1 Swagger/OpenAPI
- Fichier `swagger.yaml` au format OpenAPI 3.0
- Documentation de tous les endpoints
- Schémas de requête/réponse
- Exemples d'utilisation

### 11.2 Code Documentation
- Docstrings Python pour toutes les fonctions
- README.md avec instructions de démarrage
- Documentation d'architecture

## 12. Configuration et Variables d'Environnement

### 12.1 Variables Requises
```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/saas_platform
DATABASE_POOL_SIZE=10

# JWT
JWT_SECRET_KEY=your-secret-key
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=604800

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# S3
S3_ENDPOINT=https://s3.amazonaws.com
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_BUCKET=your-bucket
S3_REGION=eu-west-1

# Flask
FLASK_ENV=development
FLASK_PORT=4999
```

## 13. Commandes de Démarrage

### 13.1 API Flask avec Gunicorn
```bash
gunicorn -w 4 -b 0.0.0.0:4999 --access-logfile - --error-logfile - app:create_app()
```

### 13.2 Worker Kafka
```bash
python -m app.worker.consumer
```

### 13.3 Docker Compose
```bash
docker-compose up -d
```

## 14. Tests

### 14.1 Structure des Tests
- Tests unitaires pour les services
- Tests d'intégration pour les routes
- Tests de validation des schémas
- Tests de multi-tenancy isolation

### 14.2 Coverage Minimum
- Code coverage : 80% minimum
- Tous les endpoints testés
- Tous les cas d'erreur couverts

## 15. Monitoring et Logging

### 15.1 Logging
- Utilisation du module `logging` Python
- Logs structurés en JSON
- Niveaux : DEBUG, INFO, WARNING, ERROR, CRITICAL

### 15.2 Métriques
- Temps de réponse des endpoints
- Nombre de requêtes par tenant
- Taille des fichiers uploadés
- Messages Kafka produits/consommés

## 16. Performance

### 16.1 Optimisations
- Pooling des connexions database
- Cache Redis pour les données fréquentes
- Pagination sur toutes les listes
- Index sur les colonnes fréquemment requêtées

### 16.2 Limites
- Taille max upload : 100MB par fichier
- Rate limiting : 1000 requêtes/heure par user
- Timeout requêtes : 30 secondes

## 17. Évolutions Futures

### 17.1 Phase 2
- WebSockets pour notifications temps réel
- Full-text search avec Elasticsearch
- Versioning des documents
- Partage de documents entre users

### 17.2 Phase 3
- Analytics dashboard
- Export bulk des données
- API GraphQL alternative
- Mobile SDK

## 18. Contraintes Techniques

### 18.1 Contraintes Obligatoires
- Python 3.11 minimum
- PostgreSQL 14 minimum
- Kafka 3.0 minimum
- Docker et Docker Compose obligatoires
- Respect strict de l'architecture en couches
- Pas d'accès direct à la DB depuis les routes

### 18.2 Bonnes Pratiques
- Code PEP8 compliant
- Type hints Python
- Gestion des erreurs systématique
- Transactions database appropriées
- Logs détaillés mais sans données sensibles

---

## Annexes

### A. Exemple de Flux Complet

1. User login → JWT tokens
2. Select tenant → Switch database context
3. Upload document → Validate → Store metadata → Kafka message
4. Worker processes → Upload to S3 → Update file record
5. User downloads → Check permissions → Generate S3 URL → Redirect

### B. Checklist de Développement

- [ ] Setup projet Python avec structure de répertoires
- [ ] Configuration Flask avec Blueprints
- [ ] Modèles SQLAlchemy avec BaseModel
- [ ] Schemas Marshmallow pour validation
- [ ] Services layer implementation
- [ ] Routes avec gestion d'erreurs
- [ ] JWT authentication
- [ ] Multi-database support
- [ ] Kafka producer/consumer
- [ ] S3 integration
- [ ] Docker configuration
- [ ] Swagger documentation
- [ ] Tests unitaires et intégration
- [ ] Documentation README

### C. Ressources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [SQLAlchemy Documentation](https://www.sqlalchemy.org/)
- [Marshmallow Documentation](https://marshmallow.readthedocs.io/)
- [Flask-JWT-Extended](https://flask-jwt-extended.readthedocs.io/)
- [Kafka Python Client](https://kafka-python.readthedocs.io/)
- [Boto3 S3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3.html)
