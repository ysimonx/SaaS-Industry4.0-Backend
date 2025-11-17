# Partage de projets Healthchecks.io entre instances Docker

## Le Problème

Quand vous avez plusieurs instances Docker de Healthchecks.io (par exemple, une en local et une en production), elles ont chacune leur propre base de données avec leurs propres projets et clés API. Vous voulez synchroniser ces projets pour avoir les mêmes clés API partout.

## Solutions

### Solution 1 : Une seule instance Healthchecks (RECOMMANDÉE)

**C'est la meilleure approche** : N'utilisez qu'UNE SEULE instance Healthchecks.io accessible par tous vos environnements.

```
┌────────────────────────────────────────────┐
│     Instance Healthchecks.io UNIQUE        │
│         (Serveur Central)                  │
│                                            │
│  Projet: "Mon Application"                │
│  API Key: hVIB-d9ihVotUKFmoiwAKNH5JBVmra4j│
└────────────────────────────────────────────┘
           ▲            ▲            ▲
           │            │            │
    Environnement  Environnement  Environnement
        Local         Staging      Production
```

**Mise en place :**

1. **Option A : Utilisez healthchecks.io (SaaS)**
   ```bash
   # .env.healthchecks (identique partout)
   HEALTHCHECKS_HOST=https://healthchecks.io
   HEALTHCHECKS_API_URL=https://healthchecks.io/api/v1
   HEALTHCHECKS_PING_URL=https://hc-ping.com
   HEALTHCHECKS_API_KEY=votre-cle-api-saas
   ```

2. **Option B : Auto-hébergez sur un serveur accessible**
   ```bash
   # Sur un VPS ou serveur dédié
   docker-compose up -d healthchecks healthchecks-db

   # Configurez un domaine
   # monitoring.votredomaine.com → votre serveur
   ```

### Solution 2 : Synchronisation via export/import de base de données

Si vous DEVEZ avoir plusieurs instances, synchronisez les bases de données :

#### Script d'export depuis l'instance source

```bash
#!/bin/bash
# export-healthchecks-project.sh

echo "🔄 Exporting Healthchecks project data..."

# 1. Export de la base de données (projets, checks, clés API)
docker-compose exec healthchecks-db pg_dump \
  -U healthchecks \
  -d healthchecks \
  --data-only \
  -t api_project \
  -t api_check \
  -t api_channel \
  -t api_notification \
  > healthchecks_project_export.sql

echo "✅ Export completed to healthchecks_project_export.sql"
```

#### Script d'import dans l'instance cible

```bash
#!/bin/bash
# import-healthchecks-project.sh

echo "📥 Importing Healthchecks project data..."

# 1. Importer les données
docker-compose exec -T healthchecks-db psql \
  -U healthchecks \
  -d healthchecks \
  < healthchecks_project_export.sql

# 2. Redémarrer Healthchecks pour rafraîchir le cache
docker-compose restart healthchecks

echo "✅ Import completed"
```

### Solution 3 : Configuration via l'API Management

Créez automatiquement le même projet avec les mêmes clés sur chaque instance :

```python
#!/usr/bin/env python3
# sync-healthchecks-projects.py

import requests
import json
import os

class HealthchecksProjectSync:
    def __init__(self, instance_url, superuser_email, superuser_password):
        self.instance_url = instance_url
        self.session = requests.Session()
        self.login(superuser_email, superuser_password)

    def login(self, email, password):
        """Connexion à l'interface d'administration"""
        # Note: Healthchecks.io n'a pas d'API admin publique
        # Cette approche utilise l'interface web
        login_url = f"{self.instance_url}/accounts/login/"

        # Récupérer le token CSRF
        response = self.session.get(login_url)
        csrf_token = response.cookies.get('csrftoken')

        # Se connecter
        login_data = {
            'email': email,
            'password': password,
            'csrfmiddlewaretoken': csrf_token
        }
        self.session.post(login_url, data=login_data)

    def create_project(self, project_name, api_key=None):
        """Créer un projet avec une clé API spécifique"""
        # Utiliser l'API pour créer le projet
        # Note: L'API standard ne permet pas de spécifier la clé
        # Il faut utiliser des méthodes alternatives
        pass

# Configuration à synchroniser
PROJECT_CONFIG = {
    'name': 'Production Monitoring',
    'api_key': 'hVIB-d9ihVotUKFmoiwAKNH5JBVmra4j',
    'checks': [
        {
            'name': 'PostgreSQL',
            'tags': 'database',
            'schedule': '*/2 * * * *',
            'grace': 240
        },
        # ... autres checks
    ]
}

# Synchroniser sur toutes les instances
INSTANCES = [
    {'url': 'http://localhost:8000', 'email': 'admin@local.com', 'password': 'admin123'},
    {'url': 'https://monitoring.prod.com', 'email': 'admin@prod.com', 'password': 'prodpass'}
]

for instance in INSTANCES:
    sync = HealthchecksProjectSync(
        instance['url'],
        instance['email'],
        instance['password']
    )
    sync.create_project(PROJECT_CONFIG['name'], PROJECT_CONFIG['api_key'])
```

### Solution 4 : Utilisation de volumes Docker partagés

Pour des instances sur le même hôte, partagez la base de données :

```yaml
# docker-compose.yml
version: '3.8'

services:
  # Base de données PARTAGÉE
  healthchecks-db:
    image: postgres:13
    volumes:
      - shared-healthchecks-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=healthchecks
      - POSTGRES_USER=healthchecks
      - POSTGRES_PASSWORD=secret

  # Instance 1
  healthchecks-1:
    image: healthchecks/healthchecks
    ports:
      - "8001:8000"
    environment:
      - DB=postgres
      - DB_HOST=healthchecks-db
      - DB_NAME=healthchecks
      - DB_USER=healthchecks
      - DB_PASSWORD=secret
    depends_on:
      - healthchecks-db

  # Instance 2 (même DB)
  healthchecks-2:
    image: healthchecks/healthchecks
    ports:
      - "8002:8000"
    environment:
      - DB=postgres
      - DB_HOST=healthchecks-db  # Même DB !
      - DB_NAME=healthchecks
      - DB_USER=healthchecks
      - DB_PASSWORD=secret
    depends_on:
      - healthchecks-db

volumes:
  shared-healthchecks-data:  # Volume partagé
```

### Solution 5 : Script de création avec Django Management

Utilisez les commandes Django pour créer des projets identiques :

```bash
#!/bin/bash
# create-identical-project.sh

PROJECT_NAME="Mon Projet"
API_KEY="hVIB-d9ihVotUKFmoiwAKNH5JBVmra4j"
USER_EMAIL="admin@example.com"

# Créer le projet via Django shell
docker-compose exec healthchecks python manage.py shell <<EOF
from django.contrib.auth.models import User
from hc.accounts.models import Project
from hc.api.models import Check
import uuid

# Récupérer l'utilisateur
user = User.objects.get(email='$USER_EMAIL')

# Créer ou récupérer le projet
project, created = Project.objects.get_or_create(
    owner=user,
    name='$PROJECT_NAME'
)

# Définir la clé API manuellement (ATTENTION: non standard)
# Healthchecks génère normalement ses propres clés
# Vous devrez peut-être modifier le code source pour permettre cela

if created:
    print(f"Project created: {project.name}")
    print(f"API Key: {project.api_key}")
else:
    print(f"Project exists: {project.name}")
    print(f"API Key: {project.api_key}")
EOF
```

## Approche RECOMMANDÉE : Architecture Master-Slave

La meilleure solution est d'avoir une architecture master-slave :

```
┌─────────────────────────────────┐
│   MASTER Healthchecks Instance  │
│        (Production)              │
│   - Source de vérité             │
│   - Génère les API keys          │
└─────────────────────────────────┘
           │
           │ Export périodique
           ▼
    ┌──────────────┐
    │ Fichier JSON │
    │ config.json  │
    └──────────────┘
           │
           │ Import
           ▼
┌─────────────────────────────────┐
│   SLAVE Healthchecks Instances  │
│     (Dev, Staging, Local)       │
│   - Importent la config         │
│   - Read-only ou test only      │
└─────────────────────────────────┘
```

### Script de synchronisation Master → Slaves

```bash
#!/bin/bash
# sync-healthchecks-config.sh

MASTER_URL="https://monitoring.production.com"
MASTER_API_KEY="master-admin-key"

# 1. Exporter depuis le master
echo "📥 Fetching configuration from master..."
curl -H "X-Api-Key: $MASTER_API_KEY" \
     "$MASTER_URL/api/v1/checks/" \
     > checks.json

# 2. Pour chaque instance slave
SLAVES=("http://localhost:8000" "http://staging:8000")

for slave_url in "${SLAVES[@]}"; do
    echo "📤 Syncing to $slave_url..."

    # Importer les checks
    # Note: Nécessite une API custom ou script Django
    docker-compose exec healthchecks python manage.py import_checks < checks.json
done

echo "✅ Synchronization complete"
```

## Configuration recommandée pour votre cas

### Étape 1 : Choisissez votre architecture

**Pour le développement local + production :**

```bash
# Option A : Utilisez healthchecks.io (SaaS) pour TOUS les environnements
# - Créez un compte sur healthchecks.io
# - Créez un projet "Mon Application"
# - Utilisez la même API key partout

# Option B : Une instance auto-hébergée accessible partout
# - Déployez Healthchecks sur un VPS
# - Ouvrez les ports nécessaires
# - Utilisez un nom de domaine
```

### Étape 2 : Configuration unifiée

```bash
# .env.healthchecks (IDENTIQUE sur toutes les machines)
# ============================================

# Si vous utilisez healthchecks.io (SaaS)
HEALTHCHECKS_HOST=https://healthchecks.io
HEALTHCHECKS_API_URL=https://healthchecks.io/api/v1
HEALTHCHECKS_PING_URL=https://hc-ping.com
HEALTHCHECKS_API_KEY=votre-cle-projet  # Depuis l'interface healthchecks.io

# OU si vous auto-hébergez
HEALTHCHECKS_HOST=https://monitoring.votredomaine.com
HEALTHCHECKS_API_URL=https://monitoring.votredomaine.com/api/v1
HEALTHCHECKS_PING_URL=https://monitoring.votredomaine.com/ping
HEALTHCHECKS_API_KEY=votre-cle-projet  # Depuis votre instance

# UUIDs des checks (identiques partout)
HC_CHECK_API=uuid-1
HC_CHECK_POSTGRES=uuid-2
# ...
```

### Étape 3 : Ne PAS lancer Healthchecks localement

```yaml
# docker-compose.override.yml (local)
version: '3.8'

services:
  # Désactiver healthchecks en local
  healthchecks:
    deploy:
      replicas: 0  # Ne pas démarrer

  healthchecks-db:
    deploy:
      replicas: 0  # Ne pas démarrer
```

Ou simplement :

```bash
# Démarrer SANS healthchecks
docker-compose up -d api worker celery-beat  # PAS healthchecks
```

## Script complet de setup

```bash
#!/bin/bash
# setup-shared-healthchecks.sh

echo "🏥 Configuration de Healthchecks.io partagé"
echo "=========================================="
echo ""
echo "Choisissez votre configuration :"
echo "1) Utiliser healthchecks.io (SaaS)"
echo "2) Utiliser une instance auto-hébergée existante"
echo "3) Créer une nouvelle instance centrale"
read -p "Votre choix (1-3): " choice

case $choice in
    1)
        echo "Configuration pour healthchecks.io..."
        read -p "Entrez votre API key depuis healthchecks.io: " api_key

        cat > .env.healthchecks <<EOF
HEALTHCHECKS_ENABLED=true
HEALTHCHECKS_HOST=https://healthchecks.io
HEALTHCHECKS_API_URL=https://healthchecks.io/api/v1
HEALTHCHECKS_PING_URL=https://hc-ping.com
HEALTHCHECKS_API_KEY=$api_key
EOF
        ;;

    2)
        echo "Configuration pour instance existante..."
        read -p "URL de votre instance: " instance_url
        read -p "API key: " api_key

        cat > .env.healthchecks <<EOF
HEALTHCHECKS_ENABLED=true
HEALTHCHECKS_HOST=$instance_url
HEALTHCHECKS_API_URL=$instance_url/api/v1
HEALTHCHECKS_PING_URL=$instance_url/ping
HEALTHCHECKS_API_KEY=$api_key
EOF
        ;;

    3)
        echo "Création d'une instance centrale..."
        # Déployer sur un serveur accessible
        echo "Suivez le guide de déploiement dans la documentation"
        ;;
esac

echo ""
echo "✅ Configuration créée dans .env.healthchecks"
echo "📋 Copiez ce fichier sur toutes vos machines"
echo "🚀 Démarrez vos applications SANS le service healthchecks local"
```

## Résumé

**La meilleure approche est de NE PAS avoir plusieurs instances Healthchecks**, mais plutôt :

1. **Une seule instance Healthchecks.io** (SaaS ou auto-hébergée)
2. **Un seul projet** avec une API key
3. **Partager cette API key** entre tous vos environnements
4. **Ne PAS lancer Healthchecks** localement, juste pinger l'instance centrale

Si vous DEVEZ absolument avoir plusieurs instances, utilisez les scripts de synchronisation ci-dessus, mais c'est plus complexe et non recommandé.