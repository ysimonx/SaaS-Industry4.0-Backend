# Guide de connexion PostgreSQL

## Configuration actuelle
- **Container**: saas-postgres
- **Port**: 5432 (exposé sur localhost)
- **Base de données**: saas_platform
- **Utilisateur**: postgres
- **Mot de passe**: postgres

## Méthodes de connexion

### 1. Depuis l'intérieur du container (pour debug)
```bash
docker exec -it saas-postgres psql -U postgres -d saas_platform
```

### 2. Depuis la machine hôte avec Docker
```bash
# Méthode simple avec URL de connexion
docker run --rm --network host postgres:14-alpine \
  psql postgresql://postgres:postgres@localhost:5432/saas_platform

# Méthode avec variables d'environnement
PGPASSWORD=postgres docker run --rm --network host postgres:14-alpine \
  psql -h localhost -p 5432 -U postgres -d saas_platform
```

### 3. Avec un client PostgreSQL natif (si installé)

Si vous avez `psql` installé sur votre machine :
```bash
PGPASSWORD=postgres psql -h localhost -p 5432 -U postgres -d saas_platform
```

Pour installer psql sur macOS :
```bash
brew install postgresql
```

### 4. Avec un client GUI

Vous pouvez utiliser des clients graphiques comme :
- **DBeaver** : https://dbeaver.io/
- **pgAdmin** : https://www.pgadmin.org/
- **TablePlus** : https://tableplus.com/

Paramètres de connexion :
- Host: `localhost` ou `127.0.0.1`
- Port: `5432`
- Database: `saas_platform`
- Username: `postgres`
- Password: `postgres`

### 5. Avec Python (nécessite un environnement virtuel)

```bash
# Créer un environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer psycopg2
pip install psycopg2-binary

# Connexion Python
python3 << 'EOF'
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="saas_platform",
    user="postgres",
    password="postgres"
)
print("Connexion réussie!")
conn.close()
EOF
```

## Résolution de problèmes

### Erreur "role postgres does not exist"
Cette erreur peut survenir si :
1. Le container n'est pas démarré : `docker-compose up -d postgres`
2. Vous essayez de vous connecter sans spécifier le mot de passe
3. Le container a été recréé sans les données initiales

### Vérifications de base
```bash
# Container en cours d'exécution ?
docker ps | grep saas-postgres

# Port accessible ?
docker port saas-postgres

# Logs du container
docker logs saas-postgres

# Tester la connexion
docker exec saas-postgres pg_isready -U postgres
```

## URL de connexion pour applications
```
postgresql://postgres:postgres@localhost:5432/saas_platform
```

Cette URL peut être utilisée dans vos applications Flask, Django, ou tout autre framework.

## Commandes Flask avec Vault

**Important**: Si vous utilisez l'intégration Vault, les commandes Flask doivent utiliser le script wrapper pour charger les variables d'environnement :

```bash
# Au lieu de :
docker-compose exec api flask db migrate -m "Message"

# Utilisez :
docker-compose exec api /app/flask-wrapper.sh db migrate -m "Message"

# Exemples courants :
docker-compose exec api /app/flask-wrapper.sh db init
docker-compose exec api /app/flask-wrapper.sh db upgrade
docker-compose exec api /app/flask-wrapper.sh db current
docker-compose exec api /app/flask-wrapper.sh db history
```

Le script wrapper `/app/flask-wrapper.sh` charge automatiquement les variables depuis le fichier `.env.vault` avant d'exécuter les commandes Flask.