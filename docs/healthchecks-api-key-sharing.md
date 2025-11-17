# Partage de clé API Healthchecks.io entre instances

## Vue d'ensemble

**OUI**, vous pouvez et devriez partager la même clé API Healthchecks.io entre différentes instances de conteneurs Docker. C'est même la pratique recommandée pour maintenir une configuration cohérente.

## Comment fonctionne Healthchecks.io

### Architecture multi-instances

```
┌─────────────────────────────────────────────────┐
│           Instance Healthchecks.io              │
│                 (Serveur Central)                │
│                                                  │
│  API Key: hVIB-d9ihVotUKFmoiwAKNH5JBVmra4j     │
│                                                  │
│  Checks:                                         │
│  ├── PostgreSQL     (UUID-1)                    │
│  ├── Redis          (UUID-2)                    │
│  ├── API            (UUID-3)                    │
│  └── Celery         (UUID-4)                    │
└─────────────────────────────────────────────────┘
                    ▲        ▲        ▲
                    │        │        │
         Même clé API     Même clé    Même clé
                    │        │        │
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ Machine 1│  │ Machine 2│  │ Machine 3│
    │  Docker  │  │  Docker  │  │  Docker  │
    └──────────┘  └──────────┘  └──────────┘
```

### Points clés

1. **Une seule instance Healthchecks.io** : Vous avez UN serveur Healthchecks central
2. **Une clé API partagée** : Toutes les machines utilisent la MÊME clé API
3. **UUIDs uniques par check** : Chaque check a un UUID unique, partagé entre toutes les instances
4. **Pings depuis n'importe où** : N'importe quelle machine peut pinger n'importe quel check

## Configuration recommandée

### 1. Serveur Healthchecks.io centralisé

**Option A : Hébergé localement (Docker)**
```yaml
# docker-compose.yml sur UN serveur dédié
services:
  healthchecks:
    image: healthchecks/healthchecks:latest
    ports:
      - "8000:8000"
    environment:
      - ALLOWED_HOSTS=*
      - SITE_ROOT=https://monitoring.votredomaine.com
```

**Option B : Service cloud**
- Utilisez https://healthchecks.io (service SaaS)
- Ou auto-hébergez sur un VPS/Cloud

### 2. Configuration partagée (.env.healthchecks)

```bash
# Ce fichier est IDENTIQUE sur toutes les machines
# ============================================================================
# Healthchecks.io Configuration
# ============================================================================

# URL du serveur Healthchecks UNIQUE
HEALTHCHECKS_ENABLED=true
HEALTHCHECKS_HOST=https://monitoring.votredomaine.com  # ou http://healthchecks:8000 en local
HEALTHCHECKS_API_URL=https://monitoring.votredomaine.com/api/v1
HEALTHCHECKS_PING_URL=https://monitoring.votredomaine.com/ping

# Clé API PARTAGÉE entre toutes les instances
HEALTHCHECKS_API_KEY=hVIB-d9ihVotUKFmoiwAKNH5JBVmra4j
HEALTHCHECKS_READ_KEY=MoT6b6wH1mAdzuUdDiMQyvGq01ETFuzn

# UUIDs des checks IDENTIQUES partout
HC_CHECK_API=0cab08fe-03f4-48c2-a927-90493fa0b2f2
HC_CHECK_POSTGRES=8d634561-7bb5-461c-84f3-596982e1f80e
HC_CHECK_REDIS=5f671802-21f2-4c94-91b6-0d4b1648f9c3
# ... etc
```

### 3. Déploiement multi-machines

```bash
# Sur CHAQUE machine qui exécute votre application :

# 1. Copiez le même .env.healthchecks
scp .env.healthchecks user@machine2:/path/to/project/
scp .env.healthchecks user@machine3:/path/to/project/

# 2. Démarrez l'application (sans Healthchecks server)
docker-compose up -d api worker celery-beat  # PAS healthchecks

# 3. Les conteneurs pingeront le serveur Healthchecks central
```

## Scénarios d'utilisation

### Scénario 1 : Développement local + Production

```bash
# .env.healthchecks.dev (pour développement local)
HEALTHCHECKS_HOST=http://localhost:8000
HEALTHCHECKS_API_KEY=dev-api-key-12345

# .env.healthchecks.prod (pour production)
HEALTHCHECKS_HOST=https://monitoring.production.com
HEALTHCHECKS_API_KEY=prod-api-key-67890
```

### Scénario 2 : Multi-environnements (Dev/Staging/Prod)

```bash
# Utilisez différents PROJETS dans Healthchecks.io
# Chaque projet a sa propre clé API

# Dev Team Project
HEALTHCHECKS_API_KEY=dev-team-api-key

# Staging Project
HEALTHCHECKS_API_KEY=staging-api-key

# Production Project
HEALTHCHECKS_API_KEY=production-api-key
```

### Scénario 3 : Architecture distribuée

```yaml
# Machine 1 : Base de données
services:
  postgres:
    # Pinge HC_CHECK_POSTGRES

# Machine 2 : API
services:
  api:
    # Pinge HC_CHECK_API

# Machine 3 : Workers
services:
  celery:
    # Pinge HC_CHECK_CELERY_WORKER

# Tous utilisent la MÊME clé API et les MÊMES UUIDs
```

## Sécurité et bonnes pratiques

### 1. Gestion sécurisée de la clé API

**❌ Ne PAS faire :**
```bash
# Ne commitez jamais la clé API dans git
git add .env.healthchecks  # Contient la clé API
```

**✅ À faire :**
```bash
# .gitignore
.env.healthchecks
*.healthchecks

# Utilisez un gestionnaire de secrets
# Option 1 : Variables d'environnement CI/CD
# Option 2 : HashiCorp Vault
# Option 3 : AWS Secrets Manager
# Option 4 : Kubernetes Secrets
```

### 2. Template pour le partage

Créez un fichier template sans secrets :

```bash
# .env.healthchecks.template
HEALTHCHECKS_ENABLED=true
HEALTHCHECKS_HOST=__HEALTHCHECKS_HOST__
HEALTHCHECKS_API_KEY=__YOUR_API_KEY_HERE__

# Check IDs (peuvent être commitées)
HC_CHECK_API=0cab08fe-03f4-48c2-a927-90493fa0b2f2
HC_CHECK_POSTGRES=8d634561-7bb5-461c-84f3-596982e1f80e
# ... etc
```

### 3. Rotation de clés API

Si vous devez changer la clé API :

1. Créez une nouvelle clé dans Healthchecks.io
2. Mettez à jour sur toutes les machines :
   ```bash
   # Script de mise à jour
   #!/bin/bash
   NEW_API_KEY="nouvelle-cle-api"

   for machine in machine1 machine2 machine3; do
     ssh $machine "sed -i 's/HEALTHCHECKS_API_KEY=.*/HEALTHCHECKS_API_KEY=$NEW_API_KEY/' /path/to/.env.healthchecks"
     ssh $machine "docker-compose restart api worker"
   done
   ```
3. Supprimez l'ancienne clé

## Architecture recommandée pour production

### Option 1 : Healthchecks.io SaaS

```
Internet
    │
    ▼
┌─────────────────────────┐
│   healthchecks.io       │
│   (Service Cloud)       │
└─────────────────────────┘
    ▲         ▲         ▲
    │         │         │
Machine1  Machine2  Machine3
(AWS)     (GCP)     (Azure)
```

**Avantages :**
- Pas d'infrastructure à gérer
- Haute disponibilité garantie
- Accessible depuis n'importe où

**Configuration :**
```bash
HEALTHCHECKS_HOST=https://hc-ping.com
HEALTHCHECKS_API_URL=https://healthchecks.io/api/v1
HEALTHCHECKS_PING_URL=https://hc-ping.com
```

### Option 2 : Auto-hébergement centralisé

```
┌─────────────────────────┐
│  VPS/Cloud Dédié        │
│  - Healthchecks Docker  │
│  - PostgreSQL           │
│  - Nginx + SSL          │
└─────────────────────────┘
    ▲         ▲         ▲
    │         │         │
App Server1  Server2  Server3
```

**docker-compose.yml sur le serveur de monitoring :**
```yaml
version: '3.8'

services:
  healthchecks:
    image: healthchecks/healthchecks:latest
    environment:
      - DB=postgres
      - DB_NAME=healthchecks
      - DB_USER=healthchecks
      - DB_PASSWORD=${DB_PASSWORD}
      - SECRET_KEY=${SECRET_KEY}
      - ALLOWED_HOSTS=monitoring.example.com
      - SITE_ROOT=https://monitoring.example.com
    depends_on:
      - healthchecks-db
    ports:
      - "8000:8000"

  healthchecks-db:
    image: postgres:13
    environment:
      - POSTGRES_DB=healthchecks
      - POSTGRES_USER=healthchecks
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - healthchecks-data:/var/lib/postgresql/data

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl

volumes:
  healthchecks-data:
```

## FAQ

### Q : Puis-je avoir plusieurs clés API pour le même projet ?

**R :** Oui, Healthchecks.io permet de créer plusieurs clés API (Read-Write et Read-Only) pour le même projet. Utile pour :
- Donner un accès read-only aux équipes de monitoring
- Séparer les permissions par environnement
- Rotation de clés sans interruption

### Q : Que se passe-t-il si deux instances pinguent le même check ?

**R :** C'est parfaitement normal et attendu ! Par exemple :
- Si vous avez 3 serveurs API, tous les 3 peuvent pinger `HC_CHECK_API`
- Healthchecks considère le check comme "up" tant qu'au moins UN ping arrive dans l'intervalle
- C'est idéal pour la haute disponibilité

### Q : Comment gérer les checks spécifiques à une machine ?

**R :** Créez des checks séparés :
```bash
# Checks partagés (dans .env.healthchecks)
HC_CHECK_API=uuid-1  # Tous les serveurs API

# Checks spécifiques (variables d'environnement locales)
HC_CHECK_API_SERVER1=uuid-2  # Seulement serveur 1
HC_CHECK_API_SERVER2=uuid-3  # Seulement serveur 2
```

### Q : Puis-je utiliser différentes clés API par environnement ?

**R :** Oui, c'est même recommandé :
```bash
# Structure de fichiers
.env.healthchecks.dev    # Clé API dev
.env.healthchecks.staging # Clé API staging
.env.healthchecks.prod   # Clé API production

# Dans docker-compose.yml
env_file:
  - .env.healthchecks.${ENVIRONMENT:-dev}
```

## Exemple de déploiement complet

```bash
#!/bin/bash
# deploy-with-healthchecks.sh

# 1. Configuration commune
cat > .env.healthchecks.shared <<EOF
HEALTHCHECKS_ENABLED=true
HEALTHCHECKS_HOST=https://monitoring.company.com
HC_CHECK_API=0cab08fe-03f4-48c2-a927-90493fa0b2f2
HC_CHECK_POSTGRES=8d634561-7bb5-461c-84f3-596982e1f80e
EOF

# 2. Déploiement sur chaque machine
MACHINES="server1.com server2.com server3.com"
API_KEY="your-shared-api-key"

for machine in $MACHINES; do
  echo "Deploying to $machine..."

  # Copier la configuration
  scp .env.healthchecks.shared user@$machine:/app/.env.healthchecks

  # Ajouter la clé API (via SSH pour sécurité)
  ssh user@$machine "echo 'HEALTHCHECKS_API_KEY=$API_KEY' >> /app/.env.healthchecks"

  # Redémarrer les services
  ssh user@$machine "cd /app && docker-compose restart"
done

echo "✅ Deployment complete!"
```

## Conclusion

- **OUI**, partagez la même clé API entre toutes vos instances
- **OUI**, utilisez les mêmes UUIDs de checks partout
- **NON**, n'exécutez pas plusieurs serveurs Healthchecks (un seul suffit)
- **OUI**, centralisez le monitoring pour une vue d'ensemble cohérente

Cette approche vous donne un monitoring unifié et cohérent de toute votre infrastructure distribuée.