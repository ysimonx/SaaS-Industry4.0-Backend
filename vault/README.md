# HashiCorp Vault Configuration

Ce répertoire contient la configuration complète de HashiCorp Vault pour la gestion sécurisée des secrets.

## 🔐 Architecture Vault

```
vault/
├── config/
│   └── vault.hcl              # Configuration Vault (stockage persistant)
├── scripts/
│   ├── unseal-vault.sh        # Script d'auto-unseal au démarrage
│   └── init-vault.sh          # Script d'injection des secrets
├── init-data/
│   ├── README.md              # Documentation des secrets
│   ├── docker.env             # Secrets pour environnement Docker (à créer)
│   ├── dev.env                # Secrets pour environnement Dev (à créer)
│   └── prod.env               # Secrets pour environnement Prod (à créer)
├── data/                      # Stockage persistant Vault (généré automatiquement)
│   ├── unseal-keys.json       # Clés de déverrouillage (généré)
│   └── root-token.txt         # Token administrateur (généré)
└── logs/                      # Logs Vault

⚠️  Les répertoires data/, logs/, et init-data/ sont exclus de Git (.gitignore)
```

## 🚀 Quick Start

### 1. Créer le fichier de secrets

```bash
# Créer le fichier de secrets pour Docker (développement)
cat > vault/init-data/docker.env <<'SECRETS'
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/saas_platform
TENANT_DATABASE_URL_TEMPLATE=postgresql://postgres:postgres@postgres:5432/{database_name}
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ACCESS_TOKEN_EXPIRES=900
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET=saas-documents
S3_REGION=us-east-1
SECRETS
```

### 2. Démarrer Vault avec auto-unseal

```bash
# Démarrer Vault et le service d'auto-unseal
docker-compose up -d vault vault-unseal

# Vérifier les logs d'unseal
docker logs -f saas-vault-unseal

# Vérifier que Vault est déverrouillé
docker exec saas-vault vault status
# Attendu: "Sealed: false"
```

### 3. Initialiser les secrets dans Vault

```bash
# Démarrer le service d'initialisation
docker-compose up -d vault-init

# Vérifier les logs
docker logs -f saas-vault-init

# Vérifier que .env.vault a été créé
cat .env.vault
```

### 4. Vérifier les secrets

```bash
# Se connecter avec le token root
VAULT_TOKEN=$(cat vault/data/root-token.txt)
docker exec -e VAULT_TOKEN=$VAULT_TOKEN saas-vault vault kv get secret/saas-project/docker/database

# Lister tous les secrets
docker exec -e VAULT_TOKEN=$VAULT_TOKEN saas-vault vault kv list secret/saas-project/docker
```

## 📋 Fichiers Générés Automatiquement

Après le premier démarrage, ces fichiers sont créés automatiquement :

- `vault/data/unseal-keys.json` - 5 clés d'unseal (seuil de 3 requis)
- `vault/data/root-token.txt` - Token administrateur Vault
- `.env.vault` - Credentials AppRole pour l'application

**⚠️ CRITIQUE**: Ces fichiers ne doivent JAMAIS être committés dans Git !

## 🔄 Fonctionnement

### Au Premier Démarrage

1. **vault-unseal** détecte que Vault n'est pas initialisé
2. Initialise Vault avec 5 clés (seuil de 3)
3. Sauvegarde les clés dans `vault/data/unseal-keys.json`
4. Sauvegarde le token root dans `vault/data/root-token.txt`
5. Déverrouille Vault automatiquement

### Aux Redémarrages Suivants

1. **vault-unseal** détecte que Vault est initialisé
2. Lit les clés depuis `vault/data/unseal-keys.json`
3. Déverrouille Vault automatiquement
4. Pas d'intervention manuelle nécessaire

## 🔧 Configuration

### Stockage Persistant

Le stockage `file` est utilisé pour persister les données Vault :

```hcl
storage "file" {
  path = "/vault/data"
}
```

Les données survivent aux redémarrages et reconstructions de conteneurs.

### Auto-Unseal

Le script `unseal-vault.sh` :
- S'exécute automatiquement au démarrage de Vault
- Initialise Vault si nécessaire (premier démarrage)
- Déverrouille Vault avec les clés sauvegardées

### Injection de Secrets

Le script `init-vault.sh` :
- Lit les secrets depuis `vault/init-data/${VAULT_ENV}.env`
- Crée les chemins secrets dans Vault
- Configure l'authentification AppRole
- Génère les credentials dans `.env.vault`

## 🔒 Sécurité

### Fichiers Sensibles

Ces fichiers contiennent des secrets critiques :

1. **vault/data/unseal-keys.json**
   - Clés pour déverrouiller Vault
   - Si perdu, Vault ne peut plus être déverrouillé
   - Sauvegarder dans un gestionnaire de mots de passe

2. **vault/data/root-token.txt**
   - Token administrateur avec tous les droits
   - Ne jamais l'exposer
   - Sauvegarder dans un gestionnaire de mots de passe

3. **.env.vault**
   - Credentials AppRole pour l'application
   - Permet l'accès aux secrets Vault
   - Régénérable si perdu

4. **vault/init-data/*.env**
   - Secrets sources avant injection dans Vault
   - Supprimer après migration vers Vault
   - Ne jamais commiter

### Bonnes Pratiques

- ✅ Sauvegarder `unseal-keys.json` et `root-token.txt` dans un gestionnaire de mots de passe
- ✅ Utiliser des mots de passe forts et uniques
- ✅ Créer les fichiers `prod.env` directement sur le serveur de production
- ✅ Activer TLS en production
- ✅ Configurer les politiques d'accès restrictives
- ❌ Ne jamais commiter les fichiers de secrets dans Git
- ❌ Ne jamais exposer le token root
- ❌ Ne pas utiliser le mode dev en production

## 🌐 Interface Web Vault

Vault fournit une interface web pour gérer les secrets :

- **URL**: http://localhost:8201/ui
- **Token**: Contenu de `vault/data/root-token.txt`

## 📚 Documentation

- [Plan complet d'intégration Vault](../specs/vault/plan-vault.md)
- [Documentation officielle Vault](https://developer.hashicorp.com/vault/docs)
- [Guide QuickStart](../README.md#quick-start)

## 🐛 Dépannage

### Vault est scellé (sealed) après redémarrage

```bash
# Relancer le service d'auto-unseal
docker-compose up -d vault-unseal
docker logs -f saas-vault-unseal
```

### Clés d'unseal perdues

Si les clés d'unseal sont perdues, il est **impossible** de déverrouiller Vault. Seule solution :
1. Sauvegarder les données importantes
2. Réinitialiser Vault complètement
3. Reconfigurer tous les secrets

**⚠️ C'est pourquoi il est CRITIQUE de sauvegarder les clés !**

### Regénérer les credentials AppRole

```bash
# Se connecter à Vault
VAULT_TOKEN=$(cat vault/data/root-token.txt)
docker exec -e VAULT_TOKEN=$VAULT_TOKEN saas-vault sh

# Relancer l'initialisation
docker-compose up -d vault-init
```

## 🔄 Migration depuis .env

Si vous avez des fichiers `.env` existants :

```bash
# 1. Copier les secrets dans vault/init-data/docker.env
# 2. Lancer l'initialisation
docker-compose up -d vault-init

# 3. Vérifier que l'application utilise Vault
docker-compose logs api | grep Vault

# 4. (Optionnel) Supprimer les anciens .env
mv .env.docker .env.docker.backup
```

## 🎯 Environnements

Vault supporte plusieurs environnements isolés :

- **docker** - Développement local avec Docker Compose
- **dev** - Développement local sans Docker
- **prod** - Production

Chaque environnement a ses propres secrets dans :
- `secret/saas-project/docker/*`
- `secret/saas-project/dev/*`
- `secret/saas-project/prod/*`
