# Guide de Tests

Ce document décrit comment exécuter et maintenir les tests pour la plateforme SaaS Multi-Tenant Backend.

## Table des Matières

- [Prérequis](#prérequis)
- [Installation](#installation)
- [Exécution des Tests](#exécution-des-tests)
- [Structure des Tests](#structure-des-tests)
- [Types de Tests](#types-de-tests)
- [Fixtures](#fixtures)
- [Écriture de Nouveaux Tests](#écriture-de-nouveaux-tests)
- [Bonnes Pratiques](#bonnes-pratiques)
- [Résolution de Problèmes](#résolution-de-problèmes)

## Prérequis

- Docker et Docker Compose installés
- Les conteneurs de l'application en cours d'exécution (`docker-compose up -d`)
- pytest installé dans le conteneur (voir [Installation](#installation))

## Installation

### Installation de pytest dans le conteneur

Les dépendances de test ne sont pas incluses dans l'image Docker de production. Pour les installer :

```bash
# Installer pytest et ses plugins
docker exec -u root saas-api pip install pytest pytest-flask pytest-mock pytest-cov
```

Ou installer toutes les dépendances de développement :

```bash
docker exec -u root saas-api pip install -r requirements-dev.txt
```

### Base de données de test

Une base de données SQLite en mémoire est utilisée par défaut pour les tests. Aucune configuration supplémentaire n'est nécessaire.

Si vous souhaitez utiliser PostgreSQL pour les tests :

```bash
# Créer la base de données de test
docker exec saas-postgres psql -U postgres -c "CREATE DATABASE saas_platform_test;"

# Configurer la variable d'environnement
export TEST_DATABASE_URL="postgresql://postgres:postgres@postgres:5432/saas_platform_test"
```

## Exécution des Tests

### Commandes de Base

**Exécuter tous les tests :**

```bash
docker exec saas-api python -m pytest tests/ -v
```

**Exécuter les tests d'un fichier spécifique :**

```bash
docker exec saas-api python -m pytest tests/integration/test_auth_flow.py -v
```

**Exécuter une classe de tests spécifique :**

```bash
docker exec saas-api python -m pytest tests/integration/test_auth_flow.py::TestLoginFlow -v
```

**Exécuter un test spécifique :**

```bash
docker exec saas-api python -m pytest tests/integration/test_auth_flow.py::TestLoginFlow::test_login_success -v
```

### Options Avancées

**Tests avec sortie détaillée (afficher les print) :**

```bash
docker exec saas-api python -m pytest tests/ -v -s
```

**Tests avec couverture de code :**

```bash
docker exec saas-api python -m pytest tests/ --cov=app --cov-report=html
```

Le rapport de couverture sera généré dans `htmlcov/index.html`.

**Arrêter au premier échec :**

```bash
docker exec saas-api python -m pytest tests/ -x
```

**Exécuter uniquement les tests qui ont échoué lors de la dernière exécution :**

```bash
docker exec saas-api python -m pytest tests/ --lf
```

**Mode verbose avec affichage des variables locales en cas d'échec :**

```bash
docker exec saas-api python -m pytest tests/ -vv --tb=long
```

**Exécuter les tests en parallèle (nécessite pytest-xdist) :**

```bash
docker exec -u root saas-api pip install pytest-xdist
docker exec saas-api python -m pytest tests/ -n auto
```

## Structure des Tests

```
backend/tests/
├── conftest.py                 # Fixtures partagées pour tous les tests
├── integration/               # Tests d'intégration (full stack)
│   ├── test_auth_flow.py     # Tests du flux d'authentification
│   ├── test_tenant_flow.py   # Tests de gestion des tenants
│   └── test_document_flow.py # Tests de gestion des documents
└── unit/                      # Tests unitaires (composants isolés)
    ├── test_models.py         # Tests des modèles
    ├── test_services.py       # Tests des services
    └── test_utils.py          # Tests des utilitaires
```

## Types de Tests

### Tests d'Intégration

Les tests d'intégration vérifient le fonctionnement complet de l'application, de la requête HTTP à la base de données.

**Exemple :** [test_auth_flow.py](backend/tests/integration/test_auth_flow.py)

```python
def test_login_success(client, session, test_user):
    """Test successful login returns tokens"""
    login_data = {
        'email': test_user.email,
        'password': 'TestPass123'
    }

    response = client.post(
        '/api/auth/login',
        data=json.dumps(login_data),
        content_type='application/json'
    )

    assert response.status_code == 200
    data = response.get_json()
    assert 'access_token' in data
    assert 'refresh_token' in data
```

### Tests Unitaires

Les tests unitaires vérifient des composants isolés (fonctions, méthodes, classes).

**Exemple :**

```python
def test_user_password_hashing():
    """Test that passwords are properly hashed"""
    user = User(email='test@example.com')
    user.set_password('SecurePass123')

    assert user.password_hash is not None
    assert user.password_hash != 'SecurePass123'
    assert user.check_password('SecurePass123') is True
    assert user.check_password('WrongPassword') is False
```

## Fixtures

Les fixtures pytest sont définies dans [conftest.py](backend/tests/conftest.py) et fournissent des ressources réutilisables pour les tests.

### Fixtures Disponibles

#### `app`
Crée une instance Flask configurée pour les tests.

```python
def test_something(app):
    assert app.config['TESTING'] is True
```

#### `client`
Fournit un client Flask pour effectuer des requêtes HTTP.

```python
def test_endpoint(client):
    response = client.get('/api/health')
    assert response.status_code == 200
```

#### `session`
Fournit une session de base de données avec rollback automatique.

```python
def test_create_user(session):
    user = User(email='test@example.com')
    session.add(user)
    session.commit()
    # Le rollback est automatique après le test
```

#### `test_user`
Crée un utilisateur de test.

```python
def test_login(client, test_user):
    response = client.post('/api/auth/login', json={
        'email': test_user.email,
        'password': 'TestPass123'
    })
    assert response.status_code == 200
```

#### `test_admin_user`
Crée un utilisateur admin de test.

```python
def test_admin_action(client, test_admin_user):
    # Actions nécessitant des privilèges admin
    pass
```

#### `test_tenant`
Crée un tenant de test avec un utilisateur admin associé.

```python
def test_tenant_creation(session, test_tenant):
    tenant, association = test_tenant
    assert tenant.name == 'Test Company'
    assert association.role == 'admin'
```

#### `auth_headers`
Fournit des en-têtes d'authentification avec un token JWT valide.

```python
def test_protected_route(client, auth_headers):
    response = client.get('/api/users/me', headers=auth_headers)
    assert response.status_code == 200
```

#### `admin_headers`
Fournit des en-têtes d'authentification pour un utilisateur admin.

```python
def test_admin_route(client, admin_headers):
    response = client.get('/api/admin/dashboard', headers=admin_headers)
    assert response.status_code == 200
```

## Écriture de Nouveaux Tests

### Template de Test d'Intégration

```python
"""
Description du module de test
"""

import pytest
import json


class TestMyFeature:
    """Test complete feature flow"""

    def test_success_case(self, client, session, test_user):
        """Test successful operation"""
        # Arrange
        data = {
            'field': 'value'
        }

        # Act
        response = client.post(
            '/api/endpoint',
            data=json.dumps(data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code == 200
        result = response.get_json()
        assert result['field'] == 'expected_value'

    def test_error_case(self, client, session):
        """Test error handling"""
        # Arrange
        invalid_data = {}

        # Act
        response = client.post(
            '/api/endpoint',
            data=json.dumps(invalid_data),
            content_type='application/json'
        )

        # Assert
        assert response.status_code == 400
        error = response.get_json()
        assert 'error' in error
```

### Template de Test Unitaire

```python
"""
Tests unitaires pour le module X
"""

import pytest
from app.utils.my_module import my_function


class TestMyFunction:
    """Test my_function utility"""

    def test_valid_input(self):
        """Test with valid input"""
        result = my_function('valid_input')
        assert result == 'expected_output'

    def test_invalid_input(self):
        """Test with invalid input"""
        with pytest.raises(ValueError):
            my_function('invalid_input')

    def test_edge_case(self):
        """Test edge case"""
        result = my_function('')
        assert result is None
```

## Bonnes Pratiques

### 1. Organisation des Tests

- **Arrange-Act-Assert (AAA)** : Structurez vos tests en trois sections claires
  - **Arrange** : Préparez les données et l'état
  - **Act** : Exécutez l'action à tester
  - **Assert** : Vérifiez les résultats

### 2. Nommage

- Utilisez des noms descriptifs : `test_login_with_invalid_password` plutôt que `test_login_2`
- Les classes de tests commencent par `Test`
- Les fonctions de test commencent par `test_`

### 3. Isolation

- Chaque test doit être indépendant
- Utilisez les fixtures pour l'état partagé
- Ne dépendez pas de l'ordre d'exécution des tests

### 4. Documentation

- Ajoutez des docstrings à chaque test
- Expliquez le **pourquoi**, pas le **comment**
- Documentez les cas limites et les comportements attendus

### 5. Assertions

- Une assertion par test si possible
- Utilisez des messages d'erreur explicites :
  ```python
  assert user.is_active is True, f"User {user.email} should be active"
  ```

### 6. Mocking

- Mockez les dépendances externes (S3, Kafka, etc.)
- Utilisez `pytest-mock` pour les mocks simples
- Exemples de mocks disponibles dans [conftest.py](backend/tests/conftest.py) :
  - `mock_s3_client`
  - `mock_kafka_producer`
  - `mock_kafka_consumer`

### 7. Couverture de Code

- Visez au moins 80% de couverture
- Testez les cas nominaux ET les cas d'erreur
- Testez les cas limites (edge cases)

## Résolution de Problèmes

### Erreur : `ModuleNotFoundError: No module named 'pytest'`

**Solution :**
```bash
docker exec -u root saas-api pip install pytest pytest-flask pytest-mock
```

### Erreur : `database "saas_platform_test" does not exist`

**Solution :**
```bash
docker exec saas-postgres psql -U postgres -c "CREATE DATABASE saas_platform_test;"
```

### Erreur : `FAILED ... TypeError: Invalid argument(s) 'pool_size','pool_timeout','max_overflow'`

**Cause :** Configuration PostgreSQL utilisée avec SQLite.

**Solution :** Vérifiez que `TestingConfig` dans [config.py](backend/app/config.py) a bien `SQLALCHEMY_ENGINE_OPTIONS = {}`.

### Erreur : `AttributeError: 'Tenant' object has no attribute 'subdomain'`

**Cause :** Code utilisant un attribut qui n'existe pas dans le modèle.

**Solution :** Utilisez `database_name` au lieu de `subdomain` dans le modèle Tenant.

### Erreur : `ValidationError: unexpected keyword argument 'data_key'`

**Cause :** Méthodes `@validates` dans les schémas Marshmallow ne supportent pas les arguments supplémentaires.

**Solution :** Ajoutez `**kwargs` à toutes les méthodes décorées avec `@validates` :

```python
@validates('email')
def validate_email_format(self, value, **kwargs):
    # validation logic
    pass
```

### Tests Lents

**Solutions :**

1. Utilisez SQLite en mémoire (par défaut)
2. Exécutez les tests en parallèle :
   ```bash
   docker exec saas-api python -m pytest tests/ -n auto
   ```
3. Exécutez uniquement les tests modifiés :
   ```bash
   docker exec saas-api python -m pytest tests/ --lf
   ```

### Déboguer un Test

**Avec pdb (Python debugger) :**

```python
def test_something(client):
    import pdb; pdb.set_trace()
    response = client.get('/api/endpoint')
    assert response.status_code == 200
```

**Avec pytest en mode verbose :**

```bash
docker exec saas-api python -m pytest tests/path/to/test.py -vv -s
```

## Intégration Continue (CI/CD)

### GitHub Actions

Exemple de workflow `.github/workflows/tests.yml` :

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests
        env:
          TEST_DATABASE_URL: postgresql://postgres:postgres@localhost/test_db
        run: |
          cd backend
          pytest tests/ -v --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./backend/coverage.xml
```

## Ressources

- [Documentation pytest](https://docs.pytest.org/)
- [Documentation Flask Testing](https://flask.palletsprojects.com/en/latest/testing/)
- [Documentation pytest-flask](https://pytest-flask.readthedocs.io/)
- [Documentation Marshmallow](https://marshmallow.readthedocs.io/)

## Suivi des Tests

### Exécution Régulière

Il est recommandé d'exécuter les tests :

- **Avant chaque commit** : Tests unitaires et tests d'intégration critiques
- **Avant chaque push** : Suite complète de tests
- **En CI/CD** : Suite complète à chaque push/PR

### Commande Rapide

Créez un alias pour une exécution rapide :

```bash
# Dans votre ~/.bashrc ou ~/.zshrc
alias test-backend="docker exec saas-api python -m pytest tests/ -v"
alias test-quick="docker exec saas-api python -m pytest tests/ -x --lf"
alias test-cov="docker exec saas-api python -m pytest tests/ --cov=app --cov-report=html"
```

## Contribution

Lors de l'ajout de nouvelles fonctionnalités :

1. ✅ Écrivez les tests **avant** le code (TDD)
2. ✅ Assurez-vous que tous les tests passent
3. ✅ Maintenez une couverture de code > 80%
4. ✅ Documentez les nouveaux tests
5. ✅ Ajoutez des fixtures si nécessaire

---

**Dernière mise à jour :** 2025-11-04
